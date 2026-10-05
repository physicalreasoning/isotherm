#!/usr/bin/env python3
"""Fetch hourly + special METAR temperatures for each settlement station (IEM ASOS archive).

At the noon read the day's maximum so far is a hard lower bound on the settled high,
and nothing upstream of this uses it.

    uv run scripts/fetch_obs.py --start 2023
"""

from __future__ import annotations

import argparse
import pathlib
import sys

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from isotherm import iem  # noqa: E402
from isotherm.weather import ALL_CITIES, CITIES  # noqa: E402

OUT = pathlib.Path("data/obs")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cities", nargs="+", default=list(CITIES))
    ap.add_argument("--start", type=int, default=2023)
    ap.add_argument("--end", type=int, default=pd.Timestamp.now().year)
    ap.add_argument("--five-min", action="store_true", help="1-minute archive at 5-minute sampling")
    a = ap.parse_args()
    if a.five_min:
        iem.MIN_INTERVAL = 5.0  # shared with other IEM users; be slow
        for k in a.cities:
            c = ALL_CITIES[k]
            qs = pd.date_range("{}-01-01".format(a.start), "{}-01-01".format(a.end + 1), freq="QS")
            parts = [
                iem.asos1min(c.asos, str(x.date()), str(y.date()))
                for x, y in zip(qs[:-1], qs[1:], strict=True)
            ]
            df = pd.concat([p for p in parts if len(p)], ignore_index=True)
            df.to_parquet(OUT / "{}_5min.parquet".format(c.station), index=False)
            print("{} {} 5-min: {} obs".format(k, c.asos, len(df)), flush=True)
        return
    OUT.mkdir(parents=True, exist_ok=True)
    for k in a.cities:
        c = ALL_CITIES[k]
        df = pd.concat([iem.asos(c.asos, y) for y in range(a.start, a.end + 1)], ignore_index=True)
        df.to_parquet(OUT / "{}.parquet".format(c.station), index=False)
        print(
            "{} {}: {} obs {}..{}".format(k, c.asos, len(df), df["valid"].min(), df["valid"].max()),
            flush=True,
        )


if __name__ == "__main__":
    main()
