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
from pmdecide import iem  # noqa: E402
from pmdecide.weather import CITIES  # noqa: E402

OUT = pathlib.Path("data/obs")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cities", nargs="+", default=list(CITIES))
    ap.add_argument("--start", type=int, default=2023)
    ap.add_argument("--end", type=int, default=pd.Timestamp.now().year)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    for k in a.cities:
        c = CITIES[k]
        df = pd.concat([iem.asos(c.asos, y) for y in range(a.start, a.end + 1)], ignore_index=True)
        df.to_parquet(OUT / "{}.parquet".format(c.station), index=False)
        print(
            "{} {}: {} obs {}..{}".format(k, c.asos, len(df), df["valid"].min(), df["valid"].max()),
            flush=True,
        )


if __name__ == "__main__":
    main()
