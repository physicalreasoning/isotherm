"""Out-of-sample predictions: the one code path both the benchmark and the backtest consume.

For each read time, every predictor is fit on rows before a walk-forward fold
and predicts the fold. Rows are kept only where every predictor produced a
forecast (the identical-rows rule), and each kept row remembers which fold
predicted it, so downstream selection can be nested: a choice made for fold i
may only look at folds < i.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import numpy as np

from .dataset import LadderSet
from .splits import walk_forward


@dataclass
class OOS:
    read: str
    rows: LadderSet                 # scored rows only
    preds: Dict[str, np.ndarray]    # model name -> (n, K) bucket probs
    fold: np.ndarray                # (n,) fold index, increasing in time
    folds: List[dict]


def oos_predictions(ls: LadderSet, suite, lockbox: bool = False) -> Dict[str, OOS]:
    out = {}
    for read in sorted(ls.meta["read"].unique()):
        sub = ls.take(np.flatnonzero(ls.meta["read"].to_numpy() == read))
        preds = {m.name: np.full(sub.mask.shape, np.nan) for m in suite}
        fold_of = np.full(len(sub), -1)
        folds = []
        for i, f in enumerate(walk_forward(sub.meta["day"], lockbox=lockbox)):
            tr, te = sub.take(f.train), sub.take(f.test)
            folds.append({"fold": f.name, "train": len(f.train), "test": len(f.test)})
            fold_of[f.test] = i
            for m in suite:
                preds[m.name][f.test] = m.fit(tr).predict(te)
        ok = fold_of >= 0
        for p in preds.values():
            ok &= np.isfinite(p).all(1)
        idx = np.flatnonzero(ok)
        out[read] = OOS(read, sub.take(idx), {k: v[idx] for k, v in preds.items()},
                        fold_of[idx], folds)
    return out
