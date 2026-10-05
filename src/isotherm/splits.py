"""Walk-forward folds and the lockbox.

Every fold trains on rows strictly before `fold_start - embargo` and tests on
[fold_start, fold_end). The lockbox (default 2026-07-01 onward) is excluded
from every fold and from all model selection; `benchmark.py --lockbox` scores
it once, with the configuration frozen in docs/PLAN.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, List

import numpy as np
import pandas as pd

LOCKBOX_START = pd.Timestamp("2026-07-01")
EMBARGO = pd.Timedelta(days=2)


@dataclass
class Fold:
    name: str
    train: np.ndarray
    test: np.ndarray


def walk_forward(
    days: pd.Series,
    start: str = "2023-07-01",
    freq: str = "QS",
    min_train_days: int = 120,
    lockbox: bool = False,
    lockbox_start: pd.Timestamp | None = None,
) -> Iterator[Fold]:
    """`lockbox_start` overrides the weather lockbox for domains with other calendars."""
    lb = pd.Timestamp(lockbox_start) if lockbox_start is not None else LOCKBOX_START
    days = pd.to_datetime(pd.Series(days)).reset_index(drop=True)
    end = days.max() + pd.Timedelta(days=1) if lockbox else lb
    edges: List[pd.Timestamp] = list(pd.date_range(start, end, freq=freq))
    if not edges or edges[-1] < end:
        edges.append(end)
    if lockbox:
        edges = [e for e in edges if e < lb] + [lb, end]
        edges = sorted(set(edges))
    for a, b in zip(edges[:-1], edges[1:], strict=True):
        if not lockbox and a >= lb:
            break
        if lockbox and a < lb:
            continue
        tr = np.flatnonzero((days < a - EMBARGO).to_numpy())
        te = np.flatnonzero(((days >= a) & (days < b)).to_numpy())
        if len(te) == 0 or days.iloc[tr].nunique() < min_train_days:
            continue
        yield Fold("{}..{}".format(a.date(), (b - pd.Timedelta(days=1)).date()), tr, te)
