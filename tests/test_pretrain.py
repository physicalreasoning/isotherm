"""G3: synthetic ladders, the market simulator, and the pretrained-init hook."""

import numpy as np
import pandas as pd

from pmdecide import pretrain as P
from pmdecide.dataset import LadderSet
from pmdecide.model import LadderNet
from pmdecide.weather import CITIES, bucket_contains, is_partition


def test_no_kalshi_settlement_station_is_used_for_pretraining():
    kalshi = {c.station for c in CITIES.values()}
    assert kalshi == P.KALSHI_STATIONS
    assert not kalshi & set(P.STATIONS)


def test_synthetic_ladder_matches_kalshi_layout_and_labels():
    lo, hi = P.ladder(np.array([71.3, 40.0]))
    for i in range(2):
        assert is_partition(list(zip(lo[i], hi[i], strict=True)))
    assert np.allclose(hi[0, 1:-1] - lo[0, 1:-1], 2.0)
    assert np.allclose(hi[0, 4] - lo[0, 1], 8.0)
    assert np.allclose(lo[0, 1:] % 1, 0.5)  # edges at half degrees, like Kalshi's integer buckets
    # integer highs land in exactly one bucket, with Kalshi's strike semantics
    for high in range(55, 90):
        y = ((high >= lo[0]) & (high < hi[0])).argmax()
        assert lo[0, y] <= high < hi[0, y]
        if np.isfinite(lo[0, y]) and np.isfinite(hi[0, y]):
            assert bucket_contains("between", lo[0, y] + 0.5, hi[0, y] - 0.5, high)


def _base(n=400, seed=0):
    rng = np.random.default_rng(seed)
    mu = rng.normal(70, 10, n)
    lo, hi = P.ladder(mu + rng.normal(0, 1, n))
    high = np.round(mu + rng.normal(0, 2.5, n))
    y = ((high[:, None] >= lo) & (high[:, None] < hi)).argmax(1)
    meta = pd.DataFrame({"day": pd.date_range("2023-01-01", periods=n), "read": "d1_16", "city": "KXXX"})
    meta = meta.assign(mu_nbs=mu, sigma_nbs=2.5, high=high, overround=1.0, cum_volume=100.0)
    from scipy.stats import norm

    p = norm.cdf((hi - mu[:, None]) / 2.5) - norm.cdf((lo - mu[:, None]) / 2.5)
    probs = {
        k: p / p.sum(1, keepdims=True)
        for k in ("market", "emos_nbm", "emos_gfs", "emos_nbm_obs", "climatology")
    }
    q = {"bid": probs["market"] * 0.9, "ask": probs["market"] * 1.1 + 0.01, "vol_after": np.zeros_like(lo)}
    return LadderSet(meta, lo, hi, np.ones((n, 6), bool), y, probs, q)


def test_simulated_quotes_are_coherent():
    real = _base()
    sim = P.MarketSim().fit_empirical(real)
    syn = sim.simulate(real, np.random.default_rng(1), tau=3.0, lam=0.2)
    assert np.allclose(syn.probs["market"].sum(1), 1)
    assert (syn.quotes["ask"] > syn.quotes["bid"]).all()
    assert ((syn.quotes["bid"] >= 0) & (syn.quotes["ask"] <= 1)).all()


def test_private_signal_makes_the_simulated_market_sharper():
    real = _base(n=2000)
    sim = P.MarketSim().fit_empirical(real)
    sharp = sim.simulate(real, np.random.default_rng(2), tau=0.5, lam=0.0)
    blunt = sim.simulate(real, np.random.default_rng(2), tau=50.0, lam=0.0)
    from pmdecide.metrics import log_score

    assert log_score(sharp.probs["market"], sharp.y).mean() < log_score(blunt.probs["market"], blunt.y).mean()


def test_subsample_keeps_whole_dates():
    real = _base(n=300)
    real.meta["day"] = np.repeat(pd.date_range("2023-01-01", periods=100), 3)
    sub = P.subsample(real, 0.25, seed=3)
    counts = sub.meta.groupby("day").size()
    assert (counts == 3).all() and len(counts) == 25


def test_pretrained_hook_is_used_when_real_data_is_too_small():
    real = _base(n=600)
    states, stats = P.pretrain(real, seeds=2, epochs=2)
    tiny = real.take(np.arange(50))
    m = LadderNet(seeds=2, init_states=states, init_stats=stats).fit(tiny)
    assert len(m.nets) == 2  # falls back to the pretrained nets instead of the market
    assert not np.allclose(m.predict(real.take(np.arange(10))), real.probs["market"][:10])
    assert len(LadderNet(seeds=2).fit(tiny).nets) == 0  # default behaviour unchanged
