"""MLB panel -> LadderSet: each game is a two-bucket ladder [away wins, home wins].

The two Kalshi markets are mutually exclusive and exhaustive (ties and voids are
excluded upstream), so a game is exactly the ladder the shared scoring, pooling and
backtest code already handle. `close_ts` is the scheduled first pitch: the strategy
only trades the pre-game market, and resting maker orders are cancelled at first pitch.

Sources (all fixed causal functions of the past, so valid for any fold):
  market    normalised mid at the read time
  elo       Elo, frozen before 2025
  elo_sp    Elo + starting pitchers, frozen before 2025
"""

from __future__ import annotations

import pathlib

import numpy as np
import pandas as pd

from ..dataset import LadderSet

D = pathlib.Path("data/sports")
EPS = 1e-3


def _norm(p):
    p = np.clip(p, EPS, None)
    return p / p.sum(1, keepdims=True)


def build(panel: pd.DataFrame | None = None, probs: pd.DataFrame | None = None) -> LadderSet:
    panel = panel if panel is not None else pd.read_parquet(D / "mlb_panel.parquet")
    probs = probs if probs is not None else pd.read_parquet(D / "mlb_game_probs.parquet")
    bad = panel.loc[~panel["candles_ok"], "event"].unique()
    panel = panel[~panel["event"].isin(bad)]
    gp = probs.set_index("game_pk")
    metas, bids, asks, vols, ys, pe, ps = [], [], [], [], [], [], []
    for (ev, read), g in panel.groupby(["event", "read"], sort=False):
        if len(g) != 2 or set(g["side"]) != {"away", "home"} or g["y"].sum() != 1:
            continue
        g = g.set_index("side").loc[["away", "home"]]
        b, a = g["bid"].to_numpy(float), g["ask"].to_numpy(float)
        if np.all(np.isnan(b) & np.isnan(a)):
            continue
        pk = int(g["game_pk"].iloc[0])
        if pk not in gp.index:
            continue
        x = gp.loc[pk]
        b = np.nan_to_num(b, nan=0.0)
        a = np.where(np.isnan(a) | (a <= 0), 1.0, a)
        mid = (a + b) / 2
        metas.append(
            {
                "event": ev,
                "city": "MLB",
                "day": pd.Timestamp(g["day"].iloc[0]),
                "read": read,
                "read_ts": int(g["read_ts"].iloc[0]),
                "close_ts": int(g["first_pitch_ts"].iloc[0]),
                "tickers": tuple(g["ticker"]),
                "period": g["period"].iloc[0],
                "regime": "mlb",
                "n_buckets": 2,
                "game_pk": pk,
                "spread": float(np.median(a - b)),
                "overround": float(mid.sum()),
                "label_agrees_mlb": bool(int(g.loc["home", "y"]) == int(x["home_won"])),
            }
        )
        bids.append(b)
        asks.append(a)
        vols.append(g["vol_after"].to_numpy(float))
        ys.append(int(g.loc["home", "y"]))
        pe.append([1 - x["p_elo"], x["p_elo"]])
        ps.append([1 - x["p_elo_sp"], x["p_elo_sp"]])
    meta = pd.DataFrame(metas)
    n = len(meta)
    lo = np.tile([0.0, 1.0], (n, 1))
    mid = (np.array(bids) + np.array(asks)) / 2
    mask = np.ones((n, 2), bool)
    return LadderSet(
        meta,
        lo,
        lo + 1,
        mask,
        np.array(ys),
        {"market": _norm(mid), "elo": _norm(np.array(pe)), "elo_sp": _norm(np.array(ps))},
        {"bid": np.array(bids), "ask": np.array(asks), "vol_after": np.array(vols)},
    )
