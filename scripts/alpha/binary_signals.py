#!/usr/bin/env python3
"""Favourite-longshot bias and book-state signals on a Kalshi-wide sample of binary markets.

Input: results/alpha/binary_sample.parquet (fetch_binary_sample.py). One row per market per
horizon before close. Every arm is a logistic recalibration of the market's own mid at the same
timestamp, fit on markets that closed before the split date and scored on markets that closed
after it:
    P(yes) = sigmoid(a + b * logit(mid) + c . x)
  flb         a, b only
  flb_h       a, b per horizon group (<= 1 h, 6 h, 24 h, 72 h)
  flb_cat     a, b per category (+ horizon terms)
  book        flb_h + spread, log 24 h volume, log hours since last print, log hours since the
              last candle (quote age), and their products
              with logit(mid)
  drift       flb_h + change in logit(mid) since the market's previous (longer) horizon, and
              last print minus mid
Scores: log score and Brier against the mid, date-block bootstrap by close date.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from common import OUT, ci, fmt
from sklearn.linear_model import LogisticRegression

CLIP = 0.005
SPLIT = None  # set in main: the 60th percentile of close dates, rounded to a month start


def logit(p):
    p = np.clip(p, CLIP, 1 - CLIP)
    return np.log(p / (1 - p))


def clean(df, log, strict=False):
    def drop(name, mask):
        log[name] = int(mask.sum())
        return df[~mask]

    log["rows (market x horizon) fetched"] = len(df)
    log["markets fetched"] = int(df["ticker"].nunique())
    df = drop("duplicate (ticker, horizon)", df.duplicated(["ticker", "h"]))
    df = drop("no quote at all (bid and ask missing)", df["bid"].isna() & df["ask"].isna())
    df = df.assign(bid=df["bid"].fillna(0.0), ask=df["ask"].fillna(1.0))
    one = (df["bid"] <= 0) | (df["ask"] >= 1)
    near = ((df["bid"] <= 0) & (df["ask"] > 0) & (df["ask"] <= 0.05)) | (
        (df["ask"] >= 1) & (df["bid"] >= 0.95)
    )
    if strict:
        df = drop("one-sided or empty book (bid 0 or ask 1)", one)
    else:
        # A longshot quoted 0 / 1-5c (or a favourite at 95-99c / 100) is a real price at the tick
        # boundary, treated as the weather ladders treat it (mid = ask / 2). Only one-sided books
        # away from the boundary are dropped.
        log["one-sided book at the tick boundary (kept, mid imputed)"] = int((one & near).sum())
        df = drop("one-sided book away from the boundary, or empty", one & ~near)
    df = drop("crossed or locked book (ask <= bid)", df["ask"] <= df["bid"])
    # Kalshi emits a candle only when the book or tape changes, so an old last candle means a quiet
    # book, not a wrong one; it is kept as a feature (lage). Only books silent for > 24 h go.
    df = drop("stale quote (no candle in the 24 h before the horizon)", df["candle_age_h"] > 24)
    df = drop("spread > 0.30 (mid uninformative)", (df["ask"] - df["bid"]) > 0.30)
    log["rows kept"] = len(df)
    log["markets kept"] = int(df["ticker"].nunique())
    log["events kept"] = int(df["event"].nunique())
    return df


def features(df):
    df = df.copy()
    df["mid"] = (df["bid"] + df["ask"]) / 2
    df["lm"] = logit(df["mid"])
    df["hg"] = pd.cut(df["h"], [0, 1.01, 6.01, 24.01, 1e9], labels=["le1h", "6h", "24h", "72h"]).astype(str)
    df["spread"] = df["ask"] - df["bid"]
    df["lvol24"] = np.log1p(df["vol24"].fillna(0))
    df["lstale"] = np.log1p(df["stale_h"].fillna(24 * 8).clip(upper=24 * 8))
    df["lage"] = np.log1p(df["candle_age_h"].clip(lower=0))
    df["lastdev"] = (df["last"] - df["mid"]).fillna(0)
    df = df.sort_values(["ticker", "h"])
    nxt = df.groupby("ticker")["lm"].shift(-1)  # the same market at the next longer horizon
    df["drift"] = (df["lm"] - nxt).fillna(0)
    df["has_drift"] = nxt.notna().astype(float)
    df["day"] = pd.to_datetime(df["close_ts"], unit="s").dt.floor("D")
    return df


def design(df, arm, cats, hgs):
    cols = {"lm": df["lm"]}
    if arm in ("flb_h", "flb_cat", "book", "drift"):
        for h in hgs[1:]:
            d = (df["hg"] == h).astype(float)
            cols["h_" + h] = d
            cols["lm_h_" + h] = d * df["lm"]
    if arm == "flb_cat":
        for c in cats[1:]:
            d = (df["category"] == c).astype(float)
            cols["c_" + c] = d
            cols["lm_c_" + c] = d * df["lm"]
    if arm == "book":
        for x in ["spread", "lvol24", "lstale", "lage"]:
            cols[x] = df[x]
            cols["lm_" + x] = df[x] * df["lm"]
    if arm == "drift":
        cols["drift"] = df["drift"]
        cols["has_drift"] = df["has_drift"]
        cols["lastdev"] = df["lastdev"]
    return pd.DataFrame(cols)


def scores(p, y):
    p = np.clip(p, CLIP, 1 - CLIP)
    return np.where(y == 1, np.log(p), np.log(1 - p)), (p - y) ** 2


def main():
    import sys

    strict = "--strict" in sys.argv
    raw = pd.read_parquet(OUT / "binary_sample.parquet")
    log = {"spec": "strict two-sided books only" if strict else "main: boundary one-sided books kept"}
    df = features(clean(raw, log, strict))
    month = df["day"].quantile(0.6).to_period("M").start_time
    train, test = df[df["day"] < month - pd.Timedelta(days=2)], df[df["day"] >= month]
    log["split (train closes before, 2-day embargo; test closes on or after)"] = str(month.date())
    log["train rows / markets"] = [len(train), int(train["ticker"].nunique())]
    log["test rows / markets"] = [len(test), int(test["ticker"].nunique())]
    cats = sorted(df["category"].unique())
    hgs = ["le1h", "6h", "24h", "72h"]
    res = {"cleaning": log, "arms": {}, "reliability": [], "coefs": {}}
    ls_m, br_m = scores(test["mid"].to_numpy(), test["y"].to_numpy())
    preds = {}
    for arm in ["flb", "flb_h", "flb_cat", "book", "drift"]:
        Xtr, Xte = design(train, arm, cats, hgs), design(test, arm, cats, hgs)
        mu, sd = Xtr.mean(), Xtr.std().replace(0, 1)
        sd["lm"], mu["lm"] = 1.0, 0.0  # keep the slope on logit(mid) interpretable
        m = LogisticRegression(C=1.0, max_iter=2000).fit((Xtr - mu) / sd, train["y"])
        p = m.predict_proba((Xte - mu) / sd)[:, 1]
        preds[arm] = p
        ls, br = scores(p, test["y"].to_numpy())
        res["coefs"][arm] = dict(
            zip(
                ["intercept"] + list(Xtr.columns),
                [float(m.intercept_[0])] + [float(c) for c in m.coef_[0] / sd.to_numpy()],
            )
        )
        res["arms"][arm] = {
            "all": {"logscore_gain": ci(test["day"], ls - ls_m), "brier_gain": ci(test["day"], br_m - br)},
        }
        for key, col in [("hg", "hg"), ("category", "category")]:
            for v, idx in test.groupby(col).indices.items():
                res["arms"][arm]["{}={}".format(key, v)] = {
                    "logscore_gain": ci(test["day"].iloc[idx], (ls - ls_m)[idx]),
                    "brier_gain": ci(test["day"].iloc[idx], (br_m - br)[idx]),
                }
    # nested comparisons on identical rows
    for a_, b_ in [("book", "flb_h"), ("drift", "flb_h"), ("flb_cat", "flb_h"), ("flb_h", "flb")]:
        la, _ = scores(preds[a_], test["y"].to_numpy())
        lb, _ = scores(preds[b_], test["y"].to_numpy())
        res["arms"]["{}-minus-{}".format(a_, b_)] = {"all": {"logscore_gain": ci(test["day"], la - lb)}}
    # descriptive reliability, all clean rows (train + test), by price bin and horizon group
    bins = [0, 0.05, 0.15, 0.3, 0.5, 0.7, 0.85, 0.95, 1.0]
    df["bin"] = pd.cut(df["mid"], bins, include_lowest=True)
    for (hg, b), g in df.groupby(["hg", "bin"], observed=True):
        r = ci(g["day"], (g["y"] - g["mid"]).to_numpy(), n=1000)
        res["reliability"].append(
            {
                "hg": hg,
                "bin": str(b),
                "n": len(g),
                "mean_p": float(g["mid"].mean()),
                "freq": float(g["y"].mean()),
                "y_minus_p": r,
            }
        )
    for (c, b), g in df[df["hg"].isin(["6h", "24h"])].groupby(["category", "bin"], observed=True):
        if len(g) >= 20:
            r = ci(g["day"], (g["y"] - g["mid"]).to_numpy(), n=1000)
            res["reliability"].append(
                {
                    "category": c,
                    "hg": "6h+24h",
                    "bin": str(b),
                    "n": len(g),
                    "mean_p": float(g["mid"].mean()),
                    "freq": float(g["y"].mean()),
                    "y_minus_p": r,
                }
            )
    res["counts_by_category"] = (
        df.groupby("category")
        .agg(rows=("y", "size"), markets=("ticker", "nunique"), yes_rate=("y", "mean"))
        .to_dict(orient="index")
    )
    res["counts_by_series"] = (
        df.groupby("series")
        .agg(rows=("y", "size"), markets=("ticker", "nunique"), first=("day", "min"), last=("day", "max"))
        .astype(str)
        .to_dict(orient="index")
    )
    (OUT / ("binary_signals_strict.json" if strict else "binary_signals.json")).write_text(
        json.dumps(res, indent=1, default=str)
    )
    print(json.dumps(log, indent=1))
    for arm, v in res["arms"].items():
        for k, r in v.items():
            print(
                "{:22s} {:18s} {}  brier {}  n={}".format(
                    arm,
                    k,
                    fmt(r["logscore_gain"]),
                    fmt(r["brier_gain"], 5) if "brier_gain" in r else "",
                    r["logscore_gain"]["n"],
                )
            )
    for k, v in res["coefs"].items():
        print(k, {a: round(b, 3) for a, b in v.items()})
    for r in res["reliability"]:
        y = r["y_minus_p"]
        print(
            r.get("category", ""),
            r["hg"],
            r["bin"],
            r["n"],
            round(r["mean_p"], 3),
            round(r["freq"], 3),
            "{:+.3f} [{:+.3f}, {:+.3f}]".format(y["mean"], y["lo"], y["hi"]),
        )


if __name__ == "__main__":
    main()
