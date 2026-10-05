#!/usr/bin/env python3
"""Fetch the pre-game prints a resting order could have been filled by, for every MLB market.

Maker orders rest from the read time for at most 4h and are cancelled at first pitch, so
only two windows can ever fill one: [T-24h, T-20h] and [T-3h, T] (T = scheduled first
pitch; the T-15min read sits inside the second). In-game trading is far heavier and
irrelevant to a pre-game order, so it is never downloaded. Settled pages are cached.

    uv run scripts/sports_fetch_trades.py
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import pathlib
import sys
import time

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from isotherm import kalshi  # noqa: E402

D = pathlib.Path("data/sports")
WINDOWS = ((86400, 72000), (10800, 0))  # seconds before first pitch: (from, to)


def market_trades(ticker, T, historical):
    path = "historical/trades" if historical else "markets/trades"
    out = []
    for a, b in WINDOWS:
        for x in kalshi._paginate(
            path, "trades", 200, _cache=True, ticker=ticker, limit=1000, min_ts=T - a, max_ts=T - b
        ):
            out.append(
                {
                    "ticker": ticker,
                    "ts": kalshi.ts(x["created_time"]),
                    "yes_price": float(x["yes_price_dollars"]),
                    "count": float(x["count_fp"]),
                    "taker_yes": x["taker_side"] == "yes",
                }
            )
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    t0 = time.time()
    panel = pd.read_parquet(D / "mlb_panel.parquet")
    mk = panel.drop_duplicates("ticker")[["ticker", "first_pitch_ts"]]
    cut = kalshi.cutoff_ts()
    rows, bad = [], 0
    with cf.ThreadPoolExecutor(a.workers) as ex:
        futs = {
            ex.submit(market_trades, r.ticker, int(r.first_pitch_ts), int(r.first_pitch_ts) < cut): r.ticker
            for r in mk.itertuples()
        }
        for i, f in enumerate(cf.as_completed(futs), 1):
            try:
                rows.extend(f.result())
            except Exception as e:
                bad += 1
                print("   skip {}: {}".format(futs[f], str(e)[:80]), flush=True)
            if i % 1000 == 0:
                print("   {}/{} markets ({:.0f}s)".format(i, len(mk), time.time() - t0), flush=True)
    out = D / "trades"
    out.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows).drop_duplicates()
    df.to_parquet(out / "mlb.parquet", index=False)
    print(
        "wrote {} prints for {} markets, {} failed ({:.0f}s)".format(
            len(df), df["ticker"].nunique() if len(df) else 0, bad, time.time() - t0
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
