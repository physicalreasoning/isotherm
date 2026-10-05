"""G3: synthetic pretraining for LadderNet at the 16:00 day-before read.

Physics corpus  ASOS stations other than the seven Kalshi settlement stations, with real
                GFS MOS, NBM and NWS CLI highs from IEM. Real forecasts, real outcomes,
                no market.
Market sim      every synthetic station-day gets a Kalshi-style ladder (two tails and four
                2°F buckets, centred on the NBM forecast with Kalshi's own offset) quoted by
                a simulated crowd. The crowd anchors on the NBM EMOS posterior and also sees
                a private signal of the truth with noise `tau` (the real market is sharper
                than any public forecast, so a sim without private information would teach
                the wrong lesson), plus logit noise `lam`. `tau` and `lam` are fit so the
                simulated market's gap to EMOS-NBM and its own calibration match the real
                market on the training rows. Overround, spreads and volume are resampled
                from the real training rows.
Causality       every fold refits the simulator on that fold's real training rows and
                pretrains only on synthetic days on or before the fold's last training day,
                because same-day weather at a neighbouring station is close to the answer.
"""

from __future__ import annotations

import pathlib
import pickle
from dataclasses import dataclass

import numpy as np
import pandas as pd
import torch
from scipy.optimize import minimize_scalar

from . import dataset
from .dataset import LadderSet, _attach_gaussians, _normalise
from .emos import interval_probs
from .metrics import log_score
from .model import LadderNet, _Net
from .weather import City

# 55 airports across climates. None is a Kalshi settlement station (KNYC KMDW KMIA KAUS KLAX
# KDEN KPHL are excluded on purpose).
STATIONS = {
    "KATL": "America/New_York", "KBOS": "America/New_York", "KBWI": "America/New_York",
    "KCLT": "America/New_York", "KDCA": "America/New_York", "KDTW": "America/Detroit",
    "KJAX": "America/New_York", "KTPA": "America/New_York", "KRDU": "America/New_York",
    "KPIT": "America/New_York", "KCLE": "America/New_York", "KCMH": "America/New_York",
    "KBUF": "America/New_York", "KALB": "America/New_York", "KBTV": "America/New_York",
    "KPWM": "America/New_York", "KRIC": "America/New_York", "KORF": "America/New_York",
    "KCHS": "America/New_York", "KIND": "America/Indiana/Indianapolis",
    "KSDF": "America/Kentucky/Louisville", "KBNA": "America/Chicago", "KMEM": "America/Chicago",
    "KMSY": "America/Chicago", "KIAH": "America/Chicago", "KDFW": "America/Chicago",
    "KSAT": "America/Chicago", "KOKC": "America/Chicago", "KTUL": "America/Chicago",
    "KICT": "America/Chicago", "KMCI": "America/Chicago", "KSTL": "America/Chicago",
    "KMSP": "America/Chicago", "KMKE": "America/Chicago", "KDSM": "America/Chicago",
    "KOMA": "America/Chicago", "KBIS": "America/Chicago", "KFSD": "America/Chicago",
    "KLBB": "America/Chicago", "KBHM": "America/Chicago", "KABQ": "America/Denver",
    "KELP": "America/Denver", "KSLC": "America/Denver", "KBOI": "America/Boise",
    "KBIL": "America/Denver", "KPHX": "America/Phoenix", "KTUS": "America/Phoenix",
    "KLAS": "America/Los_Angeles", "KSAN": "America/Los_Angeles", "KSFO": "America/Los_Angeles",
    "KSMF": "America/Los_Angeles", "KFAT": "America/Los_Angeles", "KPDX": "America/Los_Angeles",
    "KSEA": "America/Los_Angeles", "KGEG": "America/Los_Angeles",
}  # fmt: skip
KALSHI_STATIONS = {"KNYC", "KMDW", "KMIA", "KAUS", "KLAX", "KDEN", "KPHL"}
assert not KALSHI_STATIONS & set(STATIONS)

READ = "d1_16"
FIRST_DAY = pd.Timestamp("2022-01-01")  # NBM archive starts 2021; EMOS needs a year first
N_BUCKETS, WIDTH = 6, 2.0  # 94% of real day-before ladders: two tails + four 2°F buckets
CACHE = pathlib.Path("data/g3")


# --------------------------------------------------------------------- ladder layout


def layout_offsets(real: LadderSet) -> np.ndarray:
    """Kalshi's ladder centre minus the NBM EMOS mean, on real 6-bucket ladders."""
    six = real.mask.sum(1) == N_BUCKETS
    lo = np.where(np.isfinite(real.lo), real.lo, np.nan)[six]
    hi = np.where(np.isfinite(real.hi), real.hi, np.nan)[six]
    centre = (np.nanmin(lo, 1) + np.nanmax(hi, 1)) / 2
    off = centre - real.meta["mu_nbs"].to_numpy()[six]
    return off[np.isfinite(off)]


def ladder(centre: np.ndarray):
    """(lo, hi) for 6-bucket ladders whose 8°F inner span is centred near `centre`."""
    inner_lo = np.round(np.asarray(centre) - 4.0 - 0.5) + 0.5
    edges = inner_lo[:, None] + WIDTH * np.arange(5)[None, :]
    n = len(inner_lo)
    lo = np.column_stack([np.full(n, -np.inf), edges])
    hi = np.column_stack([edges, np.full(n, np.inf)])
    return lo, hi


# --------------------------------------------------------------------- physics corpus


def station_base(station: str, tz: str, offsets: np.ndarray, seed: int = 0) -> LadderSet | None:
    """Synthetic day-before ladders for one station: real forecasts, real outcomes, no market.

    A first pass with a wide dummy ladder recovers the causal NBM EMOS mean; the ladder is
    then centred on it with an offset drawn from Kalshi's real offsets, and the EMOS and
    climatology probabilities are recomputed for that ladder.
    """
    f = pathlib.Path("data/forecasts/{}_cli.parquet".format(station))
    if not f.exists():
        return None
    cli = pd.read_parquet(f).dropna(subset=["high"])
    cli = cli[cli["valid"] >= FIRST_DAY].drop_duplicates("valid")
    if len(cli) < 365:
        return None
    city = City(station, "", station, tz, 0)
    n = len(cli)
    events = [station + "-" + d.strftime("%y%b%d").upper() for d in cli["valid"]]
    meta = pd.DataFrame(
        {"day": pd.to_datetime(cli["valid"].to_numpy()), "read": READ, "city": station, "event": events}
    )
    wide_lo, wide_hi = ladder(np.full(n, 60.0))
    probe = LadderSet(meta.copy(), wide_lo, wide_hi, np.ones((n, N_BUCKETS), bool), np.zeros(n, int))
    _attach_gaussians(probe, city)
    mu = probe.meta["mu_nbs"].to_numpy()
    ok = np.isfinite(mu) & np.isfinite(probe.meta["mu_gfs"].to_numpy())
    if ok.sum() < 300:
        return None
    rng = np.random.default_rng(seed)
    centre = mu[ok] + rng.choice(offsets, ok.sum())
    lo, hi = ladder(centre)
    high = cli["high"].to_numpy(float)[ok]
    y = ((high[:, None] >= lo) & (high[:, None] < hi)).argmax(1)
    ls = LadderSet(meta.iloc[np.flatnonzero(ok)].reset_index(drop=True), lo, hi,
                   np.ones((ok.sum(), N_BUCKETS), bool), y)  # fmt: skip
    _attach_gaussians(ls, city)
    ls.meta["high"] = high
    ls.probs["emos_nbm_obs"] = ls.probs["emos_nbm"].copy()  # no observations at the day-before read
    for c in ("obs_max", "obs_last"):
        ls.meta[c] = np.nan
    ls.meta["obs_n"] = 0.0
    keep = np.isfinite(ls.probs["emos_nbm"]).all(1) & np.isfinite(ls.probs["emos_gfs"]).all(1)
    keep &= np.isfinite(ls.probs["climatology"]).all(1)
    return ls.take(np.flatnonzero(keep))


def build_corpus(offsets: np.ndarray, stations=None) -> LadderSet:
    CACHE.mkdir(parents=True, exist_ok=True)
    parts = []
    for i, (st, tz) in enumerate((stations or STATIONS).items()):
        f = CACHE / "{}.pkl".format(st)
        if f.exists():
            parts.append(pickle.loads(f.read_bytes()))
            continue
        b = station_base(st, tz, offsets, seed=i)
        if b is not None and len(b):
            f.write_bytes(pickle.dumps(b))
            parts.append(b)
    return LadderSet.concat(parts)


# --------------------------------------------------------------------- market simulator


def _mid_bin(mid):
    return np.digitize(mid, [0.05, 0.2, 0.5])


@dataclass
class MarketSim:
    tau: float = 3.0
    lam: float = 0.2
    gap_real: float = 0.0
    temper_real: float = 1.0
    overround: np.ndarray = None
    volume: np.ndarray = None
    spreads: dict = None

    def fit_empirical(self, real: LadderSet) -> "MarketSim":
        """Resampling pools and the two targets the sim must match, from real training rows."""
        ok = np.isfinite(real.probs["emos_nbm"]).all(1)
        r = real.take(np.flatnonzero(ok))
        self.gap_real = float(
            log_score(r.probs["market"], r.y).mean() - log_score(r.probs["emos_nbm"], r.y).mean()
        )
        self.temper_real = _temper(r.probs["market"], r.y, r.mask)
        self.overround = r.meta["overround"].to_numpy()
        self.volume = r.meta["cum_volume"].to_numpy()
        mid = (r.quotes["bid"] + r.quotes["ask"]) / 2
        sp = r.quotes["ask"] - r.quotes["bid"]
        b = _mid_bin(mid)
        self.spreads = {k: sp[r.mask & (b == k)] for k in range(4)}
        return self

    def simulate(self, base: LadderSet, rng, tau=None, lam=None) -> LadderSet:
        tau = self.tau if tau is None else tau
        lam = self.lam if lam is None else lam
        n, k = base.mask.shape
        mu, sg = base.meta["mu_nbs"].to_numpy(), base.meta["sigma_nbs"].to_numpy()
        signal = base.meta["high"].to_numpy() + rng.normal(0, tau, n)
        prec = 1 / sg**2 + 1 / tau**2
        mu_p = (mu / sg**2 + signal / tau**2) / prec
        p = np.clip(interval_probs(mu_p, np.sqrt(1 / prec), base.lo, base.hi), 1e-4, None)
        z = np.log(p) + rng.normal(0, lam, (n, k))
        p = np.exp(z - z.max(1, keepdims=True))
        p /= p.sum(1, keepdims=True)
        mid = p * rng.choice(self.overround, n)[:, None]
        b = _mid_bin(mid)
        sp = np.zeros_like(mid)
        for kk, pool in self.spreads.items():
            m = b == kk
            if m.any() and len(pool):
                sp[m] = rng.choice(pool, m.sum())
        bid = np.clip(np.round(mid - sp / 2, 2), 0.0, 0.99)
        ask = np.clip(np.round(mid + sp / 2, 2), 0.01, 1.0)
        ask = np.maximum(ask, bid + 0.01)
        out = base.take(np.arange(n))
        out.probs["market"] = _normalise((bid + ask) / 2, out.mask)
        out.quotes = {"bid": bid, "ask": ask, "vol_after": np.zeros_like(bid)}
        out.meta["overround"] = ((bid + ask) / 2).sum(1)
        out.meta["cum_volume"] = rng.choice(self.volume, n)
        out.meta["spread"] = np.median(ask - bid, 1)
        return out

    def calibrate(self, base: LadderSet, seed=0, n_max=15_000) -> "MarketSim":
        """Pick tau, lam so the simulated market matches the real one on its gap to EMOS-NBM
        and on its own calibration (the weight w of the tempered market p^w)."""
        rng = np.random.default_rng(seed)
        b = base.take(rng.choice(len(base), min(n_max, len(base)), replace=False))
        best = None
        for lam in (0.0, 0.15, 0.3, 0.5):

            def gap_err(t, lam=lam):
                s = self.simulate(b, np.random.default_rng(seed), tau=t, lam=lam)
                g = log_score(s.probs["market"], s.y).mean() - log_score(s.probs["emos_nbm"], s.y).mean()
                return (g - self.gap_real) ** 2

            r = minimize_scalar(gap_err, bounds=(0.3, 30.0), method="bounded", options={"xatol": 0.05})
            s = self.simulate(b, np.random.default_rng(seed), tau=r.x, lam=lam)
            err = r.fun + 0.25 * (_temper(s.probs["market"], s.y, s.mask) - self.temper_real) ** 2
            if best is None or err < best[0]:
                best = (err, r.x, lam)
        self.tau, self.lam = float(best[1]), float(best[2])
        return self

    def stats(self, ls: LadderSet) -> dict:
        """Ladder statistics compared between the real panel and the simulated corpus."""
        return {"market_minus_emos_nbm_log_score": float(log_score(ls.probs["market"], ls.y).mean()
                                                         - log_score(ls.probs["emos_nbm"], ls.y).mean()),
                "market_log_score": float(log_score(ls.probs["market"], ls.y).mean()),
                "tempered_weight": _temper(ls.probs["market"], ls.y, ls.mask),
                "median_overround": float(np.median(ls.meta["overround"])),
                "median_spread": float(np.median(ls.meta["spread"])),
                "market_top1": float((ls.probs["market"].argmax(1) == ls.y).mean())}  # fmt: skip


def _temper(p, y, mask):
    lp = np.log(np.where(mask, np.clip(p, 1e-12, None), 1.0))

    def nll(w):
        z = np.where(mask, w * lp, -np.inf)
        z = z - z.max(1, keepdims=True)
        q = np.exp(z)
        q /= q.sum(1, keepdims=True)
        return log_score(q, y).mean()

    return float(minimize_scalar(nll, bounds=(0.2, 3.0), method="bounded").x)


# --------------------------------------------------------------------- pretraining


def pretrain(syn: LadderSet, seeds=3, hidden=64, epochs=25, batch=1024, lr=3e-3, wd=1e-3, patience=4,
             market_labels=False, seed0=0):  # fmt: skip
    """Mini-batch log-score training on synthetic ladders. Returns (state_dicts, feature stats)."""
    shell = LadderNet(hidden=hidden)
    x, c, lp, mk = shell._prep(syn)
    stats = shell.stats
    y = torch.from_numpy(syn.y.astype(np.int64))
    days = syn.meta["day"].to_numpy("datetime64[D]").astype(float)
    va = days >= np.quantile(days, 0.9)
    itr, iva = np.flatnonzero(~va), np.flatnonzero(va)
    states = []
    for s in range(seeds):
        torch.manual_seed(seed0 + s)
        rng = np.random.default_rng(seed0 + s)
        yy = y.clone()
        if market_labels:  # control: labels sampled from the simulated market itself
            pm = np.where(syn.mask, syn.probs["market"], 0.0)
            cum = np.cumsum(pm / pm.sum(1, keepdims=True), 1)
            yy = torch.from_numpy(
                (cum < rng.random((len(cum), 1))).sum(1).clip(0, N_BUCKETS - 1).astype(np.int64)
            )
        net = _Net(x.shape[-1], c.shape[-1], lp.shape[-1], hidden)
        opt = torch.optim.AdamW(net.parameters(), lr=lr, weight_decay=wd)
        best, best_state, bad = np.inf, None, 0
        for _ in range(epochs):
            net.train()
            for j in np.array_split(rng.permutation(itr), max(1, len(itr) // batch)):
                j = torch.from_numpy(j)
                opt.zero_grad()
                loss = -net(x[j], c[j], lp[j], mk[j]).gather(1, yy[j, None]).mean()
                loss.backward()
                opt.step()
            net.eval()
            with torch.no_grad():
                v = float(-net(x[iva], c[iva], lp[iva], mk[iva]).gather(1, yy[iva, None]).mean())
            if v < best - 1e-5:
                best, bad, best_state = v, 0, {k: t.clone() for k, t in net.state_dict().items()}
            else:
                bad += 1
                if bad >= patience:
                    break
        states.append(best_state)
    return states, stats


# --------------------------------------------------------------------- predictors


def subsample(train: LadderSet, frac: float, seed: int = 0) -> LadderSet:
    """A random `frac` of training dates (all cities on a kept date stay together)."""
    if frac >= 1:
        return train
    days = np.sort(train.meta["day"].unique())
    rng = np.random.default_rng(seed)
    keep = set(rng.choice(days, max(1, int(round(frac * len(days)))), replace=False))
    return train.take(np.flatnonzero(train.meta["day"].isin(keep).to_numpy()))


class Subsampled:
    """LadderNet trained on a fraction of the real training dates."""

    def __init__(self, frac, seeds=3, name=None):
        self.frac, self.seeds = frac, seeds
        self.name = name or "LadderNet · {:.0%} real".format(frac)

    def fit(self, train):
        self.net = LadderNet(seeds=self.seeds).fit(subsample(train, self.frac))
        return self

    def predict(self, test):
        return self.net.predict(test)


class Pretrained:
    """Pretrain on simulated ladders up to the fold's last training day, then fine-tune."""

    def __init__(self, corpus: LadderSet, frac, seeds=3, max_rows=30_000, market_labels=False, name=None):
        self.corpus, self.frac, self.seeds = corpus, frac, seeds
        self.max_rows, self.market_labels = max_rows, market_labels
        self.name = name or "LadderNet · pretrained · {:.0%} real".format(frac)
        self.log = []

    def fit(self, train):
        sub = subsample(train, self.frac)
        cutoff = train.meta["day"].max()
        base = self.corpus.take(np.flatnonzero((self.corpus.meta["day"] <= cutoff).to_numpy()))
        rng = np.random.default_rng(int(cutoff.value // 86_400_000_000_000))
        if len(base) > self.max_rows:
            base = base.take(np.sort(rng.choice(len(base), self.max_rows, replace=False)))
        sim = MarketSim().fit_empirical(sub).calibrate(base)
        syn = sim.simulate(base, rng)
        states, stats = pretrain(syn, seeds=self.seeds, market_labels=self.market_labels)
        self.net = LadderNet(seeds=self.seeds, init_states=states, init_stats=stats,
                             market_labels=self.market_labels).fit(sub)  # fmt: skip
        self.log.append({"cutoff": str(cutoff.date()), "real_rows": len(sub), "synthetic_rows": len(syn),
                         "tau": sim.tau, "lam": sim.lam, "gap_real": sim.gap_real})  # fmt: skip
        return self

    def predict(self, test):
        return self.net.predict(test)


def load_real(read=READ) -> LadderSet:
    ls = dataset.load()
    return ls.take(np.flatnonzero((ls.meta["read"] == read).to_numpy()))
