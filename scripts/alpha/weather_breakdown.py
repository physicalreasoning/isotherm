#!/usr/bin/env python3
"""Breakdowns of the weather OOS gains (weather_signals.py output) and market-structure context.

- gain by half-year, city and settlement regime for the main arms
- reliability of the market's bucket probabilities by price level (favourite-longshot shape)
- book quality by half-year (spread, one-sided share, |last print - mid|)
- executable incoherence: sum of bids > 1 or sum of asks < 1 within a ladder
"""

from __future__ import annotations

import json

import pandas as pd
from common import CITIES, OUT, ci


def main():
    res = {}
    R = pd.concat(
        [
            pd.read_parquet(OUT / "weather_oos_dev.parquet"),
            pd.read_parquet(OUT / "weather_oos_holdout7.parquet"),
        ]
    )
    R["half"] = R["day"].dt.year.astype(str) + "H" + (1 + (R["day"].dt.month > 6)).astype(str)
    res["by_half"] = {}
    for arm in ["temper", "flow_stale", "flow_dir"]:
        for (read, half), g in R[R["arm"] == arm].groupby(["read", "half"]):
            res["by_half"]["{}|{}|{}".format(arm, read, half)] = ci(g["day"], g["gain"])
    res["by_city_temper_all_reads"] = {
        c: ci(g["day"], g["gain"]) for c, g in R[R["arm"] == "temper"].groupby("city")
    }
    H = pd.read_parquet(OUT / "weather_oos_holdout12.parquet")
    res["holdout12_by_city_temper_all_reads"] = {
        c: ci(g["day"], g["gain"]) for c, g in H[H["arm"] == "temper"].groupby("city")
    }
    T = R[R["arm"] == "temper"]  # meta rows already carry the settlement regime
    res["temper_by_regime_2026"] = {
        k: ci(g["day"], g["gain"]) for k, g in T[T["day"] >= "2026-01-01"].groupby("regime")
    }

    # reliability: market bucket probability vs realised frequency, seven cities, 2024-01 on
    df = pd.read_parquet(OUT / "weather_long.parquet")
    df = df[df["city"].isin(list(CITIES)) & (df["day"] >= "2024-01-01")]
    bins = [0, 0.02, 0.05, 0.1, 0.2, 0.35, 0.5, 0.65, 0.8, 1.0]
    df["bin"] = pd.cut(df["p_mkt"], bins, include_lowest=True)
    rel = []
    for (rd, b), g in df.groupby(["read", "bin"], observed=True):
        # date-block CI of (outcome - price) in this bin
        r = ci(g["day"], (g["y"] - g["p_mkt"]).to_numpy(), n=1000)
        rel.append(
            {"read": rd, "bin": str(b), "n": len(g), "mean_p": float(g["p_mkt"].mean()),
             "freq": float(g["y"].mean()), "y_minus_p": r}
        )  # fmt: skip
    res["reliability"] = rel

    lad = df.groupby(["event", "read"]).agg(
        day=("day", "first"), spread=("lad_spread", "first"), onesided=("lad_onesided", "first"),
        sb=("bid", "sum"), sa=("ask", "sum"), S=("S", "first"),
    )  # fmt: skip
    d2 = pd.read_parquet(OUT / "weather_long.parquet")
    d2 = d2[d2["city"].isin(list(CITIES))]
    d2["half"] = d2["day"].dt.year.astype(str) + "H" + (1 + (d2["day"].dt.month > 6)).astype(str)
    d2["absdev"] = (d2["last_px"] - d2["mid"]).abs()
    res["book_quality_by_half"] = (
        d2.groupby("half")
        .agg(median_bucket_spread=("spread", "median"), one_sided_share=("two_sided", lambda s: 1 - s.mean()),
             median_abs_lastprint_minus_mid=("absdev", "median"), mean_overround=("S", "mean"))
        .round(4)
        .to_dict(orient="index")
    )  # fmt: skip
    # executable incoherence (before fees): buy every bucket at the ask for < $1, or sell all at bid for > $1
    lad["arb_buy"] = 1 - lad["sa"]
    lad["arb_sell"] = lad["sb"] - 1
    res["incoherence"] = {
        "ladders": int(len(lad)),
        "sum_asks_below_1": int((lad["arb_buy"] > 0).sum()),
        "sum_bids_above_1": int((lad["arb_sell"] > 0).sum()),
        "max_buy_edge_cents": float(100 * lad["arb_buy"].max()),
        "max_sell_edge_cents": float(100 * lad["arb_sell"].max()),
        "note": "partition ladders: the implied CDF from normalised mids is monotone by construction",
    }
    (OUT / "weather_breakdown.json").write_text(json.dumps(res, indent=1, default=str))
    for k, v in res["by_half"].items():
        print("{:32s} {:+.4f} [{:+.4f}, {:+.4f}] n={}".format(k, v["mean"], v["lo"], v["hi"], v["n"]))
    for k, v in res["by_city_temper_all_reads"].items():
        print("7c", k, "{:+.4f} [{:+.4f}, {:+.4f}]".format(v["mean"], v["lo"], v["hi"]))
    for k, v in res["holdout12_by_city_temper_all_reads"].items():
        print("12c", k, "{:+.4f} [{:+.4f}, {:+.4f}]".format(v["mean"], v["lo"], v["hi"]))
    print(res["temper_by_regime_2026"])
    for r in rel:
        y = r["y_minus_p"]
        print(r["read"], r["bin"], r["n"], round(r["mean_p"], 4), round(r["freq"], 4),
              "{:+.4f} [{:+.4f}, {:+.4f}]".format(y["mean"], y["lo"], y["hi"]))  # fmt: skip
    print(json.dumps(res["book_quality_by_half"], indent=0))
    print(res["incoherence"])


if __name__ == "__main__":
    main()
