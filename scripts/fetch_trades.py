#!/usr/bin/env python3
"""Fetch every print for every market in the evaluation window, for the maker fill model.

Trades carry `taker_side`, so for each print we know which resting side was hit:
taker "yes" lifted a YES offer (= a resting NO bid); taker "no" hit a YES bid.
Settled markets' trades never change, so every page is cached immutably.

    uv run scripts/fetch_trades.py --since 2023-07-01
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import pathlib
import sys
import time

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from pmdecide import kalshi  # noqa: E402
from pmdecide.weather import CITIES  # noqa: E402

OUT = pathlib.Path("data/trades")


def market_trades(row):
    m = {
        "ticker": row["ticker"],
        "close_time": pd.Timestamp(row["close_ts"], unit="s", tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"),
        "result": "yes" if row["y"] == 1 else "no",
    }
    t = kalshi.trades(m)
    return [
        {
            "ticker": x["ticker"],
            "ts": kalshi.ts(x["created_time"]),
            "yes_price": float(x["yes_price_dollars"]),
            "count": float(x["count_fp"]),
            "taker_yes": x["taker_side"] == "yes",
        }
        for x in t
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cities", nargs="+", default=list(CITIES))
    ap.add_argument("--since", default="2023-07-01")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    for key in a.cities:
        pp = pathlib.Path("data/panel/{}.parquet".format(key))
        if not pp.exists():
            continue
        t0 = time.time()
        p = pd.read_parquet(pp)
        mk = p[p["day"] >= a.since].drop_duplicates("ticker")[["ticker", "close_ts", "y"]]
        rows, bad = [], 0
        with cf.ThreadPoolExecutor(a.workers) as ex:
            futs = [ex.submit(market_trades, r) for r in mk.to_dict("records")]
            for i, f in enumerate(cf.as_completed(futs), 1):
                try:
                    rows.extend(f.result())
                except Exception as e:
                    bad += 1
                    print("   skip: {}".format(str(e)[:80]), flush=True)
                if i % 2000 == 0:
                    print(
                        "   {} {}/{} markets, {:.0f}s".format(key, i, len(mk), time.time() - t0), flush=True
                    )
        df = pd.DataFrame(rows)
        df.to_parquet(OUT / "{}.parquet".format(key), index=False)
        vol = p.drop_duplicates("ticker").set_index("ticker")["market_volume"]
        got = df.groupby("ticker")["count"].sum() if len(df) else pd.Series(dtype=float)
        complete = float(
            (got.reindex(mk["ticker"]).fillna(0) >= 0.999 * vol.reindex(mk["ticker"]).fillna(0)).mean()
        )
        print(
            "== {}: {} markets, {} trades, {} failed, volume-complete {:.3f}, {:.0f}s".format(
                key, len(mk), len(df), bad, complete, time.time() - t0
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
