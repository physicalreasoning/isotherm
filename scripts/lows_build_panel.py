#!/usr/bin/env python3
"""Point-in-time panel for daily low-temperature ladders.

Same builder as scripts/build_weather_panel.py, with the low series and two read times
the evening before: 16:00 and 22:00 local. The low usually lands near dawn, so both reads
come before any of the climate day has happened.

    uv run scripts/lows_build_panel.py
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import importlib.util
import pathlib
import sys
import time

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from pmdecide import kalshi  # noqa: E402
from pmdecide.lows import LOW_SERIES, PANEL, READS, low_city  # noqa: E402

spec = importlib.util.spec_from_file_location("bwp", ROOT / "scripts" / "build_weather_panel.py")
bwp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bwp)
bwp.READ_TIMES = dict(READS)


def build_city(key, workers):
    city = low_city(key)
    t0 = time.time()
    evs = [e for e in kalshi.settled_events(city.series) if e["event_ticker"].split("-")[-1][:2].isdigit()]
    print("== {} {}: {} settled events".format(key, city.series, len(evs)), flush=True)
    rows = []
    with cf.ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(bwp.build_event, city, e): e for e in evs}
        for f in cf.as_completed(futs):
            try:
                rows.extend(f.result())
            except Exception as e:
                print("   skip {}: {}".format(futs[f]["event_ticker"], str(e)[:80]), flush=True)
    df = pd.DataFrame(rows)
    PANEL.mkdir(parents=True, exist_ok=True)
    df.to_parquet(PANEL / "{}.parquet".format(key), index=False)
    print(
        "   wrote {} rows, {} events, {} failed fetches in {:.0f}s".format(
            len(df), df["event"].nunique() if len(df) else 0, int((~df["candles_ok"]).sum()), time.time() - t0
        ),
        flush=True,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cities", nargs="+", default=list(LOW_SERIES))
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    for k in a.cities:
        build_city(k, a.workers)


if __name__ == "__main__":
    main()
