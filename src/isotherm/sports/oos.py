"""Out-of-sample predictions on the MLB calendar.

Identical in logic to `isotherm.evaluation.oos_predictions` (one code path per row:
fit on earlier folds, predict the fold, keep only rows every predictor answered), but
with MLB splits: monthly folds and an MLB-specific lockbox. Kept separate so the shared
module stays untouched while the weather work evolves it.
"""

from __future__ import annotations

from typing import Dict

import numpy as np

from ..dataset import LadderSet
from ..evaluation import OOS
from ..splits import walk_forward


def oos_predictions(ls: LadderSet, suite, lockbox: bool = False, **split_kw) -> Dict[str, OOS]:
    out = {}
    for read in sorted(ls.meta["read"].unique()):
        sub = ls.take(np.flatnonzero(ls.meta["read"].to_numpy() == read))
        preds = {m.name: np.full(sub.mask.shape, np.nan) for m in suite}
        fold_of = np.full(len(sub), -1)
        folds = []
        for i, f in enumerate(walk_forward(sub.meta["day"], lockbox=lockbox, **split_kw)):
            tr, te = sub.take(f.train), sub.take(f.test)
            folds.append({"fold": f.name, "train": len(f.train), "test": len(f.test)})
            fold_of[f.test] = i
            for m in suite:
                preds[m.name][f.test] = m.fit(tr).predict(te)
        ok = fold_of >= 0
        for p in preds.values():
            ok &= np.isfinite(p).all(1)
        idx = np.flatnonzero(ok)
        out[read] = OOS(read, sub.take(idx), {k: v[idx] for k, v in preds.items()}, fold_of[idx], folds)
    return out
