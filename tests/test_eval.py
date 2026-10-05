"""Evaluation harness: scoring rules, splits, pooling, and the typed API."""

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from isotherm import metrics
from isotherm.api import Bucket, Choice, IntegerDistribution, Noul, Score, answer
from isotherm.baselines import LogPool, Source
from isotherm.dataset import LadderSet
from isotherm.splits import EMBARGO, LOCKBOX_START, walk_forward


def synthetic(n=600, k=6, seed=0, start="2023-01-01"):
    """Ladders whose true distribution is known; 'market' = truth, 'noise' = garbage."""
    rng = np.random.default_rng(seed)
    truth = rng.dirichlet(np.ones(k) * 2, n)
    y = np.array([rng.choice(k, p=p) for p in truth])
    noise = rng.dirichlet(np.ones(k), n)
    days = pd.date_range(start, periods=n, freq="D")
    meta = pd.DataFrame({"day": days, "city": "X", "read": "d0_08", "regime": "nws_cli"})
    lo = np.tile(np.arange(k, dtype=float), (n, 1))
    return LadderSet(meta, lo, lo + 1, np.ones((n, k), bool), y, {"market": truth, "noise": noise})


def test_log_score_is_proper():
    # Expected log score is minimised by reporting the true distribution.
    ls = synthetic(n=4000)
    honest = metrics.log_score(ls.probs["market"], ls.y).mean()
    sharpened = ls.probs["market"] ** 2
    sharpened /= sharpened.sum(1, keepdims=True)
    assert honest < metrics.log_score(sharpened, ls.y).mean()
    assert honest < metrics.log_score(ls.probs["noise"], ls.y).mean()


def test_rps_rewards_near_misses():
    mask = np.ones((2, 5), bool)
    near = np.array([[0, 0, 0, 1.0, 0], [0, 0, 0, 1.0, 0]])
    far = np.array([[0, 0, 0, 0, 1.0], [0, 0, 0, 0, 1.0]])
    y = np.array([2, 2])
    assert metrics.rps(near, y, mask).mean() < metrics.rps(far, y, mask).mean()


def test_debiased_ece_near_zero_when_calibrated_and_large_when_not():
    rng = np.random.default_rng(0)
    p = rng.uniform(0, 1, 20000)
    out = (rng.uniform(0, 1, 20000) < p).astype(float)
    assert metrics.ece_debiased(p, out) < 0.02
    assert metrics.ece_debiased(np.clip(p * 0.5 + 0.5, 0, 1), out) > 0.15


def test_date_bootstrap_covers_the_mean():
    v = np.random.default_rng(1).normal(0.3, 1, 3000)
    lo, hi = metrics.date_bootstrap_mean(np.repeat(np.arange(1000), 3), v, n=500)
    assert lo < v.mean() < hi


def test_diebold_mariano_sign():
    ls = synthetic(n=1500)
    a = metrics.log_score(ls.probs["market"], ls.y)
    b = metrics.log_score(ls.probs["noise"], ls.y)
    dm = metrics.diebold_mariano(ls.meta["day"], a, b)
    assert dm["stat"] < 0 and dm["p"] < 1e-3


def test_walk_forward_never_trains_on_the_future_or_the_lockbox():
    days = pd.Series(pd.date_range("2022-01-01", "2026-10-01", freq="D"))
    folds = list(walk_forward(days))
    assert folds
    for f in folds:
        assert days.iloc[f.train].max() < days.iloc[f.test].min() - EMBARGO + pd.Timedelta(days=1)
        assert days.iloc[f.test].max() < LOCKBOX_START
    lb = list(walk_forward(days, lockbox=True))
    assert lb and all(days.iloc[f.test].min() >= LOCKBOX_START for f in lb)


def test_pool_recovers_the_informative_source():
    ls = synthetic(n=2000)
    m = LogPool(["noise", "market"]).fit(ls.take(np.arange(1500)))
    w = m.weights["d0_08"]
    assert w[1] > 0.8 and abs(w[0]) < 0.2
    p = m.predict(ls.take(np.arange(1500, 2000)))
    assert np.allclose(p.sum(1), 1)


def test_source_is_passthrough():
    ls = synthetic(n=10)
    assert np.array_equal(Source("market").predict(ls), ls.probs["market"])


# ------------------------------------------------------------------ typed API


def test_answers_are_coherent_across_question_types():
    d = IntegerDistribution.gaussian(81.2, 2.4)
    ladder = Choice(options=[Bucket(hi=79), Bucket(lo=80, hi=81), Bucket(lo=82, hi=83), Bucket(lo=84)])
    (ch,) = answer(d, [ladder])
    assert np.isclose(sum(ch.probabilities), 1.0)
    # Noul thresholds are monotone and agree with the Choice tails
    ps = [answer(d, [Noul(set=Bucket(lo=k))])[0].probabilities[0] for k in range(75, 90)]
    assert all(a >= b for a, b in zip(ps, ps[1:], strict=False))
    assert np.isclose(answer(d, [Noul(set=Bucket(lo=84))])[0].probabilities[0], ch.probabilities[3])
    q = answer(d, [Score(stat="quantiles", q=[0.1, 0.5, 0.9])])[0].value
    assert q[0] <= q[1] <= q[2] and abs(q[1] - 81) <= 1


def test_schema_rejects_malformed_questions():
    with pytest.raises(ValidationError):
        Choice(options=[Bucket(lo=80, hi=82), Bucket(lo=82, hi=84)])  # overlap
    with pytest.raises(ValidationError):
        Bucket()  # unbounded
    with pytest.raises(ValidationError):
        Bucket(lo=5, hi=4)
    with pytest.raises(ValidationError):
        Choice(options=[Bucket(lo=1)])  # one option


def test_market_label_control_learns_nothing_beyond_the_market():
    # Synthetic ladders where the market IS the truth: a net trained on market-sampled labels
    # must not beat the market on real outcomes.
    from isotherm.model import IsothermNet

    ls = synthetic(n=900, k=6)
    ls.meta["city"] = "NY"
    ls.meta["day"] = pd.date_range("2024-01-01", periods=900, freq="D")
    for s in ("emos_gfs", "emos_nbm", "emos_nbm_obs", "climatology"):
        ls.probs[s] = ls.probs["noise"]
    ls.quotes = {
        "bid": ls.probs["market"] * 0.9,
        "ask": ls.probs["market"] * 1.1,
        "vol_after": np.ones_like(ls.lo),
    }
    tr, te = ls.take(np.arange(700)), ls.take(np.arange(700, 900))
    m = IsothermNet(market_labels=True, seeds=1, epochs=60).fit(tr)
    gain = metrics.log_score(te.probs["market"], te.y).mean() - metrics.log_score(m.predict(te), te.y).mean()
    assert gain < 0.02


def test_untrained_bucket_transformer_equals_the_market():
    import torch

    from isotherm.model import IsothermTransformer

    ls = synthetic(n=50, k=6)
    ls.meta["city"] = "NY"
    for s in ("emos_gfs", "emos_nbm", "emos_nbm_obs", "climatology"):
        ls.probs[s] = ls.probs["noise"]
    ls.quotes = {
        "bid": ls.probs["market"] * 0.9,
        "ask": ls.probs["market"] * 1.1,
        "vol_after": np.ones_like(ls.lo),
    }
    m = IsothermTransformer(seeds=1)
    x, c, lp, mk = m._prep(ls)
    net = m._init_net(x.shape[-1], c.shape[-1], lp.shape[-1], 0).eval()
    with torch.no_grad():
        p = net(x, c, lp, mk).exp().numpy()
    assert np.allclose(p, ls.probs["market"], atol=1e-5)
