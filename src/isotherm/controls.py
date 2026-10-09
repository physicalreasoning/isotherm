"""Controls borrowed from financial representation learning (FINDINGS §45; Merchant et al. 2026).

- `RandomEncoderTransformer`: transformer-L with its encoder frozen at random initialisation; only
  the log pool and the output head are trained. How much of the transformer's gain is learned
  representation rather than architecture plus a fitted head?
- `SeedNet`: the per-read MLP with one network per run and a chosen seed offset, to separate
  seed-to-seed variation from month-to-month (regime) variation.

This module leaves `model.py` untouched on purpose: the walk-forward cache is keyed on its source.
"""

from __future__ import annotations

import torch

from .model import IsothermNet, IsothermTransformer


class RandomEncoderTransformer(IsothermTransformer):
    def __init__(self, name="isotherm · transformer-L · random encoder", **kw):
        kw = {"d": 128, "layers": 4, "ff": 256, **kw}
        super().__init__(name=name, **kw)

    def _init_net(self, f, cdim, s, seed):
        net = super()._init_net(f, cdim, s, seed)
        for part in (net.bucket, net.context, net.encoder):
            part.requires_grad_(False)  # AdamW skips parameters without gradients
        return net


class SeedNet(IsothermNet):
    def __init__(self, offset: int, name=None, **kw):
        kw = {"seeds": 1, **kw}
        super().__init__(name=name or "isotherm · seed {}".format(offset), **kw)
        self.offset = offset

    def _init_net(self, f, cdim, s, seed):
        torch.manual_seed(1000 * (self.offset + 1) + seed)
        return super()._init_net(f, cdim, s, seed)
