#!/usr/bin/env python3
"""Fetch archived NWS forecasts (GFS MOS, NBM) and climate reports for each settlement station.

GFS MOS from 2015 gives eight years before the first Kalshi weather market to
fit forecast-to-outcome calibration with no possibility of leakage. NBM is the
stronger forecast but only archived with its spread (`txn`, `xnd`) from 2021.

    uv run scripts/fetch_forecasts.py
"""

from __future__ import annotations

import argparse
import pathlib
import sys

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from pmdecide import iem  # noqa: E402
from pmdecide.weather import CITIES  # noqa: E402

OUT = pathlib.Path("data/forecasts")
KEEP = {"GFS": ["runtime", "ftime", "n_x", "tmp"], "NBS": ["runtime", "ftime", "txn", "xnd", "tmp", "tsd"]}


def fetch_model(station, model, start_year, end_year):
    parts = []
    for y in range(start_year, end_year + 1):
        df = iem.mos(station, model, "{}-01-01".format(y), "{}-01-01".format(y + 1))
        if df.empty:
            continue
        cols = [c for c in KEEP[model] if c in df.columns]
        parts.append(df[cols])
        print("   {} {} {}: {} rows".format(station, model, y, len(df)), flush=True)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cities", nargs="+", default=list(CITIES))
    ap.add_argument("--start", type=int, default=2015)
    ap.add_argument("--end", type=int, default=pd.Timestamp.now().year)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    for k in a.cities:
        st = CITIES[k].station
        print("== {} {}".format(k, st), flush=True)
        cli = pd.concat([iem.cli(st, y) for y in range(a.start, a.end + 1)], ignore_index=True)
        cli.to_parquet(OUT / "{}_cli.parquet".format(st), index=False)
        print("   CLI: {} days".format(len(cli)), flush=True)
        for model, y0 in (("GFS", a.start), ("NBS", max(a.start, 2021))):
            df = fetch_model(st, model, y0, a.end)
            df.to_parquet(OUT / "{}_{}.parquet".format(st, model), index=False)


if __name__ == "__main__":
    main()
