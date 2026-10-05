"""Baselines. Each is a Predictor: fit on earlier rows, predict bucket probs for later ones.

  Source(name)           a fixed causal forecast: market, emos_gfs, emos_nbm, climatology
  TemperedMarket         market^w renormalised: fixes the market's own calibration and
                         nothing else, so any gain over it from a pool is *new information*
  LogPool(names)         Π p_i^{w_i} renormalised, weights per read time: the two- or
                         three-parameter model that the neural model has to beat

The neural model implements the same two methods, so the benchmark treats it
exactly like these.
"""

from __future__ import annotations

from typing import Dict, Protocol, Sequence

import numpy as np
from scipy.optimize import minimize

from .dataset import LadderSet
from .metrics import log_score


class Predictor(Protocol):
    name: str

    def fit(self, train: LadderSet) -> "Predictor": ...

    def predict(self, test: LadderSet) -> np.ndarray: ...


class Source:
    def __init__(self, source: str, name: str | None = None):
        self.source, self.name = source, name or source

    def fit(self, train):
        return self

    def predict(self, test):
        return test.probs[self.source]


def pool(weights: np.ndarray, logs: Sequence[np.ndarray], mask: np.ndarray) -> np.ndarray:
    z = sum(w * lp for w, lp in zip(weights, logs, strict=True))
    z = np.where(mask, z, -np.inf)
    z = z - z.max(1, keepdims=True)
    p = np.exp(z)
    return p / p.sum(1, keepdims=True)


def _logs(ls: LadderSet, names):
    return [np.log(np.where(ls.mask, ls.probs[n], 1.0)) for n in names]


def fit_pool(ls: LadderSet, names, x0=None) -> np.ndarray:
    logs = _logs(ls, names)
    x0 = np.asarray(x0 if x0 is not None else [1.0] + [0.0] * (len(names) - 1))
    r = minimize(
        lambda w: log_score(pool(w, logs, ls.mask), ls.y).mean(),
        x0,
        method="L-BFGS-B",
        bounds=[(-1.0, 5.0)] * len(names),
    )
    return r.x


class LogPool:
    """`window_days` refits on the trailing window only: time-varying weights for a market
    whose biases decay (FINDINGS §3, §5)."""

    def __init__(
        self,
        names: Sequence[str],
        name: str | None = None,
        per_read: bool = True,
        window_days: int | None = None,
    ):
        self.names, self.per_read, self.window = list(names), per_read, window_days
        self.name = name or "pool(" + "+".join(self.names) + ")"
        self.weights: Dict[str, np.ndarray] = {}

    def _groups(self, ls):
        if not self.per_read:
            return {"all": np.arange(len(ls))}
        r = ls.meta["read"].to_numpy()
        return {k: np.flatnonzero(r == k) for k in np.unique(r)}

    def fit(self, train):
        self.weights = {}
        if self.window:
            d = train.meta["day"]
            train = train.take(np.flatnonzero((d > d.max() - np.timedelta64(self.window, "D")).to_numpy()))
        for k, idx in self._groups(train).items():
            if len(idx) >= 30:
                self.weights[k] = fit_pool(train.take(idx), self.names)
        return self

    def predict(self, test):
        out = np.full(test.mask.shape, np.nan)
        for k, idx in self._groups(test).items():
            w = self.weights.get(k)
            if w is None:
                w = np.array([1.0] + [0.0] * (len(self.names) - 1))
            sub = test.take(idx)
            out[idx] = pool(w, _logs(sub, self.names), sub.mask)
        return out


class TemperedMarket(LogPool):
    def __init__(self):
        super().__init__(["market"], name="market (tempered)")


def g2_suite():
    """G1 plus observation-aware and time-varying pools, and the learned model with its control."""
    from .model import IsothermNet

    return default_suite() + [
        LogPool(["market", "emos_gfs", "emos_nbm_obs"], "pool · market+GFS+obs"),
        LogPool(["market", "emos_gfs", "emos_nbm_obs"], "pool · market+GFS+obs · 365d", window_days=365),
        IsothermNet("isotherm"),
        IsothermNet("isotherm · market-sampled labels (control)", market_labels=True, seeds=3),
    ]


def default_suite():
    """The G1 bar, in increasing order of strength."""
    return [
        Source("climatology"),
        Source("emos_gfs", "EMOS · GFS MOS"),
        Source("emos_nbm", "EMOS · NBM"),
        Source("market"),
        TemperedMarket(),
        LogPool(["market", "emos_gfs"], "pool · market+GFS"),
        LogPool(["market", "emos_nbm"], "pool · market+NBM"),
        LogPool(["market", "emos_nbm", "emos_gfs", "climatology"], "pool · all"),
    ]
