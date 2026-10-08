"""Shared loading, cleaning and scoring for the alpha exploration (results/alpha/REPORT.md).

Market-only: nothing here reads a forecast, an observation or a model. Each weather ladder is
rebuilt from data/panel/*.parquet with every filter counted, so the report can list them.
"""

from __future__ import annotations

import pathlib
import sys

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from isotherm.metrics import date_bootstrap_mean  # noqa: E402
from isotherm.weather import (  # noqa: E402
    ALL_CITIES,
    CITIES,
    bucket_interval,
    is_partition,
    normalise_strikes,
)

OUT = ROOT / "results" / "alpha"
EPS = 1e-3  # same probability floor as isotherm.dataset
READS = ["d1_16", "d0_08", "d0_12", "d0_14"]


def load_ladders(cities, drops: dict) -> pd.DataFrame:
    """Long table, one row per (event, read, bucket), only ladders that pass every filter.

    Columns: city, day, event, read, read_ts, ticker, k (bucket index), n (buckets), lo, hi,
    bid, ask, mid, y, two_sided, tail, cum_volume, market_volume, regime.
    """

    def add(k, n):
        drops[k] = drops.get(k, 0) + int(n)

    out = []
    for c in cities:
        f = ROOT / "data" / "panel" / "{}.parquet".format(c)
        p = pd.read_parquet(f)
        add("panel rows (start)", len(p))
        dup = p.duplicated(["ticker", "read"])
        add("duplicate (ticker, read) rows", dup.sum())
        p = p[~dup]
        p = normalise_strikes(p)
        bad = p.loc[p["strike_type"].isna(), "event"].unique()
        add("events with unparseable strikes", len(bad))
        p = p[~p["event"].isin(bad)]
        if "candles_ok" in p:
            bad = p.loc[~p["candles_ok"], "event"].unique()
            add("events with a failed candle fetch", len(bad))
            p = p[~p["event"].isin(bad)]
        for (ev, read), g in p.groupby(["event", "read"], sort=False):
            iv = [
                bucket_interval(s, fl, cp)
                for s, fl, cp in zip(g.strike_type, g["floor"], g["cap"], strict=True)
            ]
            order = np.argsort([x for x, _ in iv])
            g = g.iloc[order]
            iv = [iv[i] for i in order]
            y = g["y"].to_numpy()
            if not is_partition(iv):
                add("(event, read) not a partition ladder", 1)
                continue
            if y.sum() != 1:
                add("(event, read) not exactly one YES", 1)
                continue
            b, a = g["bid"].to_numpy(float), g["ask"].to_numpy(float)
            if np.all(np.isnan(b) & np.isnan(a)):
                add("(event, read) book empty / not yet open", 1)
                continue
            two = (~np.isnan(b)) & (b > 0) & (~np.isnan(a)) & (a < 1)
            b = np.nan_to_num(b, nan=0.0)
            a = np.where(np.isnan(a) | (a <= 0), 1.0, a)
            mid = (a + b) / 2
            s = mid.sum()
            if s < 0.8 or s > 1.5:
                add("(event, read) sum of mids outside [0.8, 1.5] (flagged bad_sum, kept)", 1)
            n = len(g)
            rules = str(g["rules"].iloc[0])
            out.append(
                pd.DataFrame(
                    {
                        "city": c,
                        "day": g["day"].iloc[0],
                        "event": ev,
                        "read": read,
                        "read_ts": int(g["read_ts"].iloc[0]),
                        "ticker": g["ticker"].to_numpy(),
                        "k": np.arange(n),
                        "n": n,
                        "lo": [x for x, _ in iv],
                        "hi": [x for _, x in iv],
                        "bid": b,
                        "ask": a,
                        "mid": mid,
                        "y": y,
                        "two_sided": two,
                        "tail": np.isin(np.arange(n), [0, n - 1]),
                        "cum_volume": g["cum_volume"].to_numpy(float),
                        "market_volume": g["market_volume"].to_numpy(float),
                        "regime": "twc" if "Weather Company" in rules else "nws_cli",
                        "bad_sum": bool(s < 0.8 or s > 1.5),
                    }
                )
            )
    df = pd.concat(out, ignore_index=True)
    df["day"] = pd.to_datetime(df["day"])
    add("ladders kept (event x read)", df.groupby(["event", "read"]).ngroups)
    return df


def ladder_features(df: pd.DataFrame) -> pd.DataFrame:
    """Per-ladder structure: overround, spread, volume, one-sidedness, entropy of normalised mids."""
    g = df.groupby(["event", "read"], sort=False)
    df = df.copy()
    df["S"] = g["mid"].transform("sum")
    df["p_mkt"] = np.clip(df["mid"] / df["S"], EPS, None)
    df["p_mkt"] = df["p_mkt"] / df.groupby(["event", "read"], sort=False)["p_mkt"].transform("sum")
    df["spread"] = df["ask"] - df["bid"]
    df["lad_spread"] = df.groupby(["event", "read"], sort=False)["spread"].transform("median")
    df["lad_vol"] = np.log1p(g["cum_volume"].transform("sum"))
    df["lad_onesided"] = 1 - g["two_sided"].transform("mean")
    ent = -(df["p_mkt"] * np.log(df["p_mkt"]))
    df["lad_entropy"] = ent.groupby([df["event"], df["read"]], sort=False).transform("sum")
    return df


def ladder_logscore(df: pd.DataFrame, col: str) -> pd.Series:
    """Log score of the realised bucket under column `col` (already normalised per ladder)."""
    w = df[df["y"] == 1].set_index(["event", "read"])
    return np.log(np.clip(w[col], 1e-12, None))


def renorm(df: pd.DataFrame, logit_col: str) -> np.ndarray:
    """Softmax of a per-bucket score within each ladder."""
    s = df[logit_col].to_numpy()
    key = df["_lad"].to_numpy()
    mx = pd.Series(s).groupby(key).transform("max").to_numpy()
    e = np.exp(s - mx)
    z = pd.Series(e).groupby(key).transform("sum").to_numpy()
    return e / z


def ci(dates, vals, n=2000, seed=0):
    vals = np.asarray(vals, float)
    lo, hi = date_bootstrap_mean(np.asarray(dates), vals, n=n, seed=seed)
    return {
        "mean": float(vals.mean()),
        "lo": lo,
        "hi": hi,
        "n": int(len(vals)),
        "n_dates": int(len(np.unique(dates))),
    }


def fmt(r, nd=4):
    return "{:+.{nd}f} [{:+.{nd}f}, {:+.{nd}f}]".format(r["mean"], r["lo"], r["hi"], nd=nd)


__all__ = [
    "ALL_CITIES",
    "CITIES",
    "OUT",
    "READS",
    "EPS",
    "load_ladders",
    "ladder_features",
    "renorm",
    "ci",
    "fmt",
]
