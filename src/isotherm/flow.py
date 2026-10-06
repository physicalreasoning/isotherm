"""Market dynamics as extra bucket features (FINDINGS §30): momentum and order flow.

  momentum   change in the market's log-odds for each bucket since the previous read of the
             same ladder (16:00 day before -> 08:00 -> 12:00 -> 14:00), and since 16:00 the day
             before; zero at the first read
  flow       taker order flow in each bucket over the `window` before the read: net taker-YES
             share of contracts (in [-1, 1]) and log contracts traded

Both use only what happened before the read: prices are the same point-in-time candle closes
the market probabilities come from, and trades are filtered on timestamp < read time.
Features are attached to `ls.quotes` under `x_*` names so that `take` slices them with the rows.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pandas as pd
import torch

from .dataset import LadderSet
from .model import IsothermNet, features

ORDER = ["d1_16", "d0_08", "d0_12", "d0_14"]
MOMENTUM = ["x_mom_prev", "x_mom_d1"]
FLOW = ["x_flow_imb", "x_flow_vol"]


def _logit(p):
    p = np.clip(np.nan_to_num(p, nan=0.5), 1e-3, 1 - 1e-3)
    return np.log(p / (1 - p))


def add_momentum(ls: LadderSet) -> None:
    n, k = ls.mask.shape
    lg = _logit(ls.probs["market"])
    prev, d1 = np.zeros((n, k)), np.zeros((n, k))
    m = ls.meta.reset_index(drop=True)
    pos = {(e, r): i for i, (e, r) in enumerate(zip(m["event"], m["read"], strict=True))}
    tick = m["tickers"].tolist()
    for i, (e, r) in enumerate(zip(m["event"], m["read"], strict=True)):
        j = ORDER.index(r) if r in ORDER else 0
        if j == 0:
            continue
        a = pos.get((e, ORDER[j - 1]))
        b = pos.get((e, ORDER[0]))
        if a is not None and tick[a] == tick[i]:
            prev[i] = lg[i] - lg[a]
        if b is not None and tick[b] == tick[i]:
            d1[i] = lg[i] - lg[b]
    ls.quotes["x_mom_prev"] = np.where(ls.mask, prev, 0.0)
    ls.quotes["x_mom_d1"] = np.where(ls.mask, d1, 0.0)


def add_flow(ls: LadderSet, trades_dir="data/trades", window_h: float = 3.0) -> None:
    n, k = ls.mask.shape
    imb, vol = np.zeros((n, k)), np.zeros((n, k))
    m = ls.meta.reset_index(drop=True)
    w = window_h * 3600
    for city in m["city"].unique():
        f = pathlib.Path(trades_dir) / "{}.parquet".format(city)
        if not f.exists():
            continue
        t = pd.read_parquet(f).sort_values(["ticker", "ts"])
        signed = np.where(t["taker_yes"].to_numpy(), 1.0, -1.0) * t["count"].to_numpy()
        groups = {}
        for tk, g in t.assign(s=signed).groupby("ticker", sort=False):
            ts = g["ts"].to_numpy()
            groups[tk] = (
                ts,
                np.concatenate([[0], np.cumsum(g["count"].to_numpy())]),
                np.concatenate([[0], np.cumsum(g["s"].to_numpy())]),
            )
        for i in np.flatnonzero((m["city"] == city).to_numpy()):
            rt = float(m.at[i, "read_ts"])
            for j, tk in enumerate(m.at[i, "tickers"]):
                g = groups.get(tk)
                if g is None:
                    continue
                ts, cv, cs = g
                lo, hi = np.searchsorted(ts, rt - w, "left"), np.searchsorted(ts, rt, "left")
                v, s = cv[hi] - cv[lo], cs[hi] - cs[lo]
                vol[i, j] = np.log1p(v)
                imb[i, j] = s / v if v > 0 else 0.0
    ls.quotes["x_flow_imb"] = np.where(ls.mask, imb, 0.0)
    ls.quotes["x_flow_vol"] = np.where(ls.mask, vol, 0.0)


class DynamicsNet(IsothermNet):
    """IsothermNet with `extra` bucket features appended from `ls.quotes`."""

    def __init__(self, name, extra, **kw):
        super().__init__(name=name, **kw)
        self.extra = list(extra)

    def _prep(self, ls):
        x, c, logp = features(ls)
        x = np.concatenate([x, np.stack([ls.quotes[e] for e in self.extra], -1).astype(np.float32)], -1)
        if self.stats is None:
            xm, xs = x[ls.mask].mean(0), x[ls.mask].std(0) + 1e-6
            self.stats = (xm, xs, c.mean(0), c.std(0) + 1e-6)
        xm, xs, cm, cs = self.stats
        x = np.where(ls.mask[..., None], (x - xm) / xs, 0.0).astype(np.float32)
        c = ((c - cm) / cs).astype(np.float32)
        return (torch.from_numpy(x), torch.from_numpy(c), torch.from_numpy(logp), torch.from_numpy(ls.mask))
