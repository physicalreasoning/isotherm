#!/usr/bin/env python3
"""Weather ladders, market-only, with per-bucket trade features at each read.

Writes results/alpha/weather_long.parquet (one row per ladder bucket per read) and
results/alpha/weather_cleaning.json (every filter with its count).

Trade features use prints with ts strictly before the read (as isotherm.flow does):
  flow_{w}   net taker-YES share of contracts in the w hours before the read, in [-1, 1]
  lvol_{w}   log1p contracts in that window
  bigflow    net taker-YES share among "large" prints (>= the 90th percentile print size of
             trades before 2024-01-01, fixed once) in the 12 h before the read
  last_px    price of the last print before the read; stale_h hours since it
"""

from __future__ import annotations

import json
import time

import numpy as np
import pandas as pd
from common import ALL_CITIES, CITIES, OUT, ROOT, ladder_features, load_ladders

WINDOWS = [1, 3, 12, 48]


def trade_features(df: pd.DataFrame, city: str, big: float, stats: dict) -> pd.DataFrame:
    f = ROOT / "data" / "trades" / "{}.parquet".format(city)
    cols = ["flow_{}".format(w) for w in WINDOWS] + ["lvol_{}".format(w) for w in WINDOWS]
    cols += ["bigflow", "last_px", "stale_h", "has_trades"]
    res = pd.DataFrame(np.nan, index=df.index, columns=cols)
    if not f.exists():
        return res
    t = pd.read_parquet(f)
    # Identical rows are NOT dropped: they are genuine same-second fills (with them, per-market
    # trade sums match Kalshi's reported volume on 99.997% of NY markets; without, 98.8%).
    stats["identical trade rows kept (genuine fills)"] = stats.get(
        "identical trade rows kept (genuine fills)", 0
    ) + int(t.duplicated().sum())
    bad = (t["count"] <= 0) | (t["yes_price"] <= 0) | (t["yes_price"] >= 1)
    stats["trade rows with count<=0 or price outside (0,1)"] = stats.get(
        "trade rows with count<=0 or price outside (0,1)", 0
    ) + int(bad.sum())
    t = t[~bad].sort_values(["ticker", "ts"])
    t["s"] = np.where(t["taker_yes"], 1.0, -1.0) * t["count"]
    t["sb"] = np.where(t["count"] >= big, t["s"], 0.0)
    t["cb"] = np.where(t["count"] >= big, t["count"], 0.0)
    grp = {}
    for tk, g in t.groupby("ticker", sort=False):
        grp[tk] = (
            g["ts"].to_numpy(),
            np.r_[0, np.cumsum(g["count"].to_numpy())],
            np.r_[0, np.cumsum(g["s"].to_numpy())],
            np.r_[0, np.cumsum(g["sb"].to_numpy())],
            np.r_[0, np.cumsum(g["cb"].to_numpy())],
            g["yes_price"].to_numpy(),
        )
    tk = df["ticker"].to_numpy()
    rt = df["read_ts"].to_numpy()
    out = {c: np.full(len(df), np.nan) for c in cols}
    for i in range(len(df)):
        g = grp.get(tk[i])
        if g is None:
            out["has_trades"][i] = 0
            continue
        ts, cv, cs, csb, ccb, px = g
        hi = np.searchsorted(ts, rt[i], "left")
        out["has_trades"][i] = float(hi > 0)
        for w in WINDOWS:
            lo = np.searchsorted(ts, rt[i] - w * 3600, "left")
            v, s = cv[hi] - cv[lo], cs[hi] - cs[lo]
            out["lvol_{}".format(w)][i] = np.log1p(v)
            out["flow_{}".format(w)][i] = s / v if v > 0 else 0.0
        lo = np.searchsorted(ts, rt[i] - 12 * 3600, "left")
        vb = ccb[hi] - ccb[lo]
        out["bigflow"][i] = (csb[hi] - csb[lo]) / vb if vb > 0 else 0.0
        if hi > 0:
            out["last_px"][i] = px[hi - 1]
            out["stale_h"][i] = (rt[i] - ts[hi - 1]) / 3600
    for c in cols:
        res[c] = out[c]
    return res


def main():
    t0 = time.time()
    drops = {}
    df = load_ladders(list(ALL_CITIES), drops)
    df = ladder_features(df)
    df["scored7"] = df["city"].isin(list(CITIES))
    # big-print threshold, fixed on trades before 2024-01-01 (7 cities)
    sizes = []
    for c in CITIES:
        t = pd.read_parquet(ROOT / "data" / "trades" / "{}.parquet".format(c), columns=["ts", "count"])
        sizes.append(t.loc[t["ts"] < pd.Timestamp("2024-01-01", tz="UTC").timestamp(), "count"].to_numpy())
    big = float(np.quantile(np.concatenate(sizes), 0.9))
    tstats = {"big print threshold (contracts, p90 of pre-2024 prints)": big}
    parts = []
    for c in df["city"].unique():
        s = df[df["city"] == c]
        parts.append(trade_features(s, c, big, tstats))
        print(c, len(s), "{:.0f}s".format(time.time() - t0), flush=True)
    df = df.join(pd.concat(parts))
    df.to_parquet(OUT / "weather_long.parquet", index=False)
    lad = df.groupby(["event", "read"]).first()
    summary = {
        "filters": drops,
        "trades": tstats,
        "buckets_kept": int(len(df)),
        "buckets_one_sided_or_empty (kept, bid=0 / ask=1 imputed)": int((~df["two_sided"]).sum()),
        "ladders_by_city": lad.groupby("city").size().to_dict(),
        "ladders_settled_under_twc": int((lad["regime"] == "twc").sum()),
        "ladders_with_zero_cum_volume_at_read (kept, flagged)": int((lad["lad_vol"] == 0).sum()),
        "date_range": [str(df["day"].min().date()), str(df["day"].max().date())],
    }
    (OUT / "weather_cleaning.json").write_text(json.dumps(summary, indent=1, default=str))
    print(json.dumps(summary, indent=1, default=str))


if __name__ == "__main__":
    main()
