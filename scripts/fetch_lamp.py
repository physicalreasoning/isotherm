#!/usr/bin/env python3
"""Fetch GFS LAMP (LAV) hourly temperature forecasts for the seven scored stations (FINDINGS §33).

IEM's archive keeps a few cycles a day (00Z, 12Z, 18Z, sometimes 06Z). Slow: one request
every 6 s, so it can run beside the station corpus fetch.

    uv run scripts/fetch_lamp.py
"""

from __future__ import annotations

import pathlib
import sys

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from isotherm import iem  # noqa: E402
from isotherm.weather import CITIES  # noqa: E402

iem.MIN_INTERVAL = 6.0
OUT = pathlib.Path("data/forecasts")


def main():
    for k, c in CITIES.items():
        f = OUT / "{}_LAV.parquet".format(c.station)
        if f.exists():
            continue
        parts = []
        for y in range(2023, 2027):
            df = iem.mos(c.station, "LAV", "{}-01-01".format(y), "{}-01-01".format(y + 1))
            if not df.empty:
                parts.append(df[["runtime", "ftime", "tmp"]])
        df = pd.concat(parts, ignore_index=True)
        df.to_parquet(f, index=False)
        print(k, c.station, len(df), "rows", df["runtime"].min(), df["runtime"].max(), flush=True)


if __name__ == "__main__":
    main()
