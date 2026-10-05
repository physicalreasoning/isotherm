"""Out-of-sample predictions: the one code path both the benchmark and the backtest consume.

For each read time, every predictor is fit on rows before a walk-forward fold
and predicts the fold. Rows are kept only where every predictor produced a
forecast (the identical-rows rule), and each kept row remembers which fold
predicted it, so downstream selection can be nested: a choice made for fold i
may only look at folds < i.
"""
from __future__ import annotations

import hashlib
import inspect
import pathlib
import pickle
from dataclasses import dataclass
from typing import Dict, List

import numpy as np
import pandas as pd

from .dataset import LadderSet
from .splits import walk_forward


@dataclass
class OOS:
    read: str
    rows: LadderSet                 # scored rows only
    preds: Dict[str, np.ndarray]    # model name -> (n, K) bucket probs
    fold: np.ndarray                # (n,) fold index, increasing in time
    folds: List[dict]


def _cache_key(ls: LadderSet, suite, lockbox: bool) -> str:
    """Data identity + every predictor's config + the source of the modules that define them."""
    from . import baselines, model
    h = hashlib.sha256()
    h.update(repr((lockbox, [(m.name, sorted(vars(m).items(), key=str)) for m in suite])).encode())
    h.update(pd.util.hash_pandas_object(ls.meta[["event", "read", "day"]], index=False).values)
    for mod in (baselines, model):
        h.update(inspect.getsource(mod).encode())
    return h.hexdigest()[:16]


def oos_predictions(ls: LadderSet, suite, lockbox: bool = False,
                    cache_dir: str | None = "data/oos") -> Dict[str, OOS]:
    if cache_dir:
        f = pathlib.Path(cache_dir) / "{}.pkl".format(_cache_key(ls, suite, lockbox))
        if f.exists():
            return pickle.loads(f.read_bytes())
    out = _compute(ls, suite, lockbox)
    if cache_dir:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(pickle.dumps(out))
    return out


def _compute(ls: LadderSet, suite, lockbox: bool) -> Dict[str, OOS]:
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
