"""Nineteen cities: the twelve newer Kalshi cities as cities of their own (FINDINGS §36).

`model.features` one-hot encodes the seven scored cities, so a ladder from any other city gets
a blank city input. As extra training rows that blank input hurt (§21). Here the context gains
a one-hot over the twelve newer cities, so each of the nineteen has its own identity.

This module leaves `model.py` untouched on purpose: the walk-forward cache is keyed on its source.
"""

from __future__ import annotations

import numpy as np
import torch

from .dataset import LadderSet
from .model import IsothermNet, IsothermTransformer, features
from .weather import NEW_CITIES

NEW_KEYS = list(NEW_CITIES)


def new_city_onehot(ls: LadderSet) -> np.ndarray:
    return np.stack([(ls.meta["city"] == c).to_numpy(float) for c in NEW_KEYS], -1)


class _AllCities:
    """Mixin: appends the newer cities' one-hot to the context. Same as IsothermNet._prep otherwise."""

    def _prep(self, ls):
        x, c, logp = features(ls)
        c = np.column_stack([c, new_city_onehot(ls)]).astype(np.float32)
        if self.stats is None:
            xm, xs = x[ls.mask].mean(0), x[ls.mask].std(0) + 1e-6
            self.stats = (xm, xs, c.mean(0), c.std(0) + 1e-6)
        xm, xs, cm, cs = self.stats
        x = np.where(ls.mask[..., None], (x - xm) / xs, 0.0).astype(np.float32)
        c = ((c - cm) / cs).astype(np.float32)
        return (torch.from_numpy(x), torch.from_numpy(c), torch.from_numpy(logp), torch.from_numpy(ls.mask))


class Net19(_AllCities, IsothermNet):
    def __init__(self, name="isotherm · 19 cities", **kw):
        super().__init__(name=name, **kw)


class Transformer19(_AllCities, IsothermTransformer):
    def __init__(self, name="isotherm · transformer-L · 19 cities", **kw):
        kw = {"d": 128, "layers": 4, "ff": 256, **kw}
        super().__init__(name=name, **kw)
