#!/usr/bin/env python3
"""Station-day table: CLI wet/dry label and point-in-time NBM / GFS MOS PoP features at both reads.

Every corpus station with forecasts (FINDINGS §32). Stations whose 2026 data was fetched
(scripts/rain/fetch_wx.py) run to October 2026; the rest stop at 2025-12-31.
Days: every CLI day from 2021-03-01, plus every market day.

    uv run scripts/rain/build_features.py        # data/rain/features.parquet
"""

from __future__ import annotations

import concurrent.futures as cf

import pandas as pd
from common import DATA, ROOT, YEARS, cli_precip, corpus, station_features, station_tz

START = "2021-03-01"


def one(st: str, market_days: list) -> pd.DataFrame:
    info = corpus()
    tz = station_tz(st, info)
    full = (DATA / "mos" / "{}_NBS.parquet".format(st)).exists() and (
        DATA / "mos" / "{}_GFS.parquet".format(st)
    ).exists()
    c = cli_precip(st, years=YEARS if full else range(2021, 2026))
    if c.empty:
        return pd.DataFrame()
    c = c[c["day"] >= START]
    days = pd.Series(sorted(set(c["day"]) | set(pd.to_datetime(market_days))))
    f = station_features(st, tz, days, cache_only=not full)
    f = f.rename(columns={"target": "day"}).merge(c, on="day", how="left")
    f.insert(0, "station", st)
    return f


def main():
    mk = pd.read_parquet(DATA / "markets.parquet")
    mdays = mk.dropna(subset=["station"]).groupby("station")["day"].apply(lambda s: sorted(set(s))).to_dict()
    # Every corpus station with both forecast files (FINDINGS §32); those without a 2026 fetch
    # contribute 2021-2025 from the iem cache.
    sts = sorted(s for s in corpus() if (ROOT / "data" / "forecasts" / "{}_NBS.parquet".format(s)).exists())
    print("{} stations".format(len(sts)), flush=True)
    parts = []
    with cf.ProcessPoolExecutor(8) as ex:
        futs = {ex.submit(one, s, mdays.get(s, [])): s for s in sts}
        for i, f in enumerate(cf.as_completed(futs), 1):
            try:
                parts.append(f.result())
            except Exception as e:
                print("   {}: {}".format(futs[f], str(e)[:100]), flush=True)
            if i % 50 == 0:
                print("   {}/{}".format(i, len(sts)), flush=True)
    df = pd.concat(parts, ignore_index=True)
    df.to_parquet(DATA / "features.parquet", index=False)
    print("wrote {} rows, {} stations".format(len(df), df["station"].nunique()), flush=True)


if __name__ == "__main__":
    main()
