"""Pooled training: one network for every read time, optionally with extra ladders (FINDINGS §20).

The per-read models in `model.py` train a separate network for each read time on about 6,000
ladders. Here one network sees every read time at once, with the read as a one-hot context
input, so each fold trains on about four times as many ladders. `extra` ladders (daily lows,
new cities) join the training set only; scoring stays on the seven highs cities.

This module leaves `model.py` untouched on purpose: the walk-forward cache is keyed on its
source, and the per-read baselines here are read from that cache.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import torch

from .dataset import LadderSet
from .evaluation import OOS
from .model import SOURCES, IsothermNet, IsothermTransformer, features
from .splits import EMBARGO, walk_forward

READS = ["d1_16", "d1_22", "d0_08", "d0_12", "d0_14"]


def extra_context(ls: LadderSet) -> np.ndarray:
    r = ls.meta["read"].to_numpy()
    low = ls.meta["is_low"].to_numpy(float) if "is_low" in ls.meta else np.zeros(len(ls))
    return np.column_stack([(r == k).astype(float) for k in READS] + [np.nan_to_num(low)])


class _Pooled:
    """Mixin: adds the read and target flags to the context, and can subsample training dates."""

    frac: float = 1.0

    def _prep(self, ls):
        # Same as IsothermNet._prep, with `extra_context` appended to c.
        x, c, logp = features(ls)
        c = np.column_stack([c, extra_context(ls)]).astype(np.float32)
        if self.stats is None:
            xm, xs = x[ls.mask].mean(0), x[ls.mask].std(0) + 1e-6
            self.stats = (xm, xs, c.mean(0), c.std(0) + 1e-6)
        xm, xs, cm, cs = self.stats
        x = np.where(ls.mask[..., None], (x - xm) / xs, 0.0).astype(np.float32)
        c = ((c - cm) / cs).astype(np.float32)
        return (torch.from_numpy(x), torch.from_numpy(c), torch.from_numpy(logp), torch.from_numpy(ls.mask))

    def fit(self, train: LadderSet):
        if self.frac < 1:
            # Learning curve: keep a random fraction of training dates, every read of each.
            days = np.sort(train.meta["day"].unique())
            keep = np.random.default_rng(7).choice(days, int(round(len(days) * self.frac)), replace=False)
            train = train.take(np.flatnonzero(train.meta["day"].isin(keep).to_numpy()))
        return super().fit(train)


class PooledNet(_Pooled, IsothermNet):
    def __init__(self, name="isotherm · pooled", frac=1.0, **kw):
        super().__init__(name=name, **kw)
        self.frac = frac


class PooledTransformer(_Pooled, IsothermTransformer):
    def __init__(self, name="isotherm · transformer-L · pooled", frac=1.0, **kw):
        kw = {"d": 128, "layers": 4, "ff": 256, **kw}
        super().__init__(name=name, **kw)
        self.frac = frac


def as_extra(ls: LadderSet, is_low: bool) -> LadderSet:
    """Make lows or new-city ladders usable as training rows next to the highs."""
    ls = ls.complete([s for s in SOURCES if s in ls.probs])
    if "emos_nbm_obs" not in ls.probs:  # no same-day obs conditioning for lows: use plain NBM
        ls.probs["emos_nbm_obs"] = ls.probs["emos_nbm"].copy()
    m = ls.meta
    for mu, fc in (("mu_nbs", "fcst_nbs"), ("mu_gfs", "fcst_gfs")):
        if mu not in m and fc in m:
            m[mu] = m[fc]  # raw forecast as the centre; sigma falls back to the feature default
    m["is_low"] = float(is_low)
    return ls


def pooled_oos(ls: LadderSet, model, extra: LadderSet | None = None, folds=None) -> dict:
    """Walk-forward predictions for every read at once, split by read like `oos_predictions`.

    `folds` restricts which fold indices are computed (the rest are left out of the rows).
    """
    days = ls.meta["day"]
    preds = np.full(ls.mask.shape, np.nan)
    fold_of = np.full(len(ls), -1)
    info = []
    for i, f in enumerate(walk_forward(days)):
        info.append({"fold": f.name, "train": len(f.train), "test": len(f.test)})
        if folds is not None and i not in folds:
            continue
        tr = ls.take(f.train)
        if extra is not None:
            start = pd.Timestamp(f.name.split("..")[0])
            e = extra.take(np.flatnonzero((extra.meta["day"] < start - EMBARGO).to_numpy()))
            if len(e):
                tr = LadderSet.concat([tr, e])
        preds[f.test] = model.fit(tr).predict(ls.take(f.test))
        fold_of[f.test] = i
    out = {}
    for read in sorted(ls.meta["read"].unique()):
        idx = np.flatnonzero((ls.meta["read"] == read).to_numpy() & (fold_of >= 0))
        idx = idx[np.isfinite(preds[idx]).all(1)]
        out[read] = OOS(read, ls.take(idx), {model.name: preds[idx]}, fold_of[idx], info)
    return out
