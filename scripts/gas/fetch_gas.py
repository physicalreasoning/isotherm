#!/usr/bin/env python3
"""Gas prices (FINDINGS §42): Kalshi's daily AAA national-average ladders and RBOB futures.

Each KXAAAGASD event asks whether AAA's national average for regular gas on day D is above each of
about 17 strikes. It opens the morning before and closes at midnight ET; it settles on the value
AAA publishes on the morning of D, which Kalshi records exactly (`expiration_value`). The read is
16:00 ET on D-1: AAA's D-1 value and that day's RBOB settle (14:30 ET) are both public by then.

    uv run scripts/gas/fetch_gas.py        # data/gas/ladders.parquet, data/gas/rbob.parquet
"""

from __future__ import annotations

import json
import pathlib
import sys
import urllib.request

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))
from isotherm import kalshi  # noqa: E402

OUT = pathlib.Path("data/gas")
SERIES = "KXAAAGASD"
READ_ET = 16  # hour, US Eastern, the day before the target day


def target_day(event_ticker: str) -> pd.Timestamp:
    return pd.to_datetime(event_ticker.split("-")[1][:7], format="%y%b%d")


def read_ts(day: pd.Timestamp) -> int:
    t = (day - pd.Timedelta(days=1)).replace(hour=READ_ET).tz_localize("America/New_York")
    return int(t.tz_convert("UTC").timestamp())


def quote_at(m: dict, t: int):
    """Last hourly candle that closed at or before t: (bid, ask, volume to date)."""
    cs = [c for c in kalshi.candles(m, 60) if c.get("end_period_ts", 0) <= t]
    if not cs:
        return None, None, 0.0
    bid, ask = kalshi.candle_quote(cs[-1])
    return bid, ask, sum(kalshi.candle_volume(c) for c in cs)


def ladders():
    rows = []
    evs = kalshi.settled_events(SERIES)
    for i, e in enumerate(evs, 1):
        day = target_day(e["event_ticker"])
        t = read_ts(day)
        for m in kalshi.event_markets(e["event_ticker"]):
            if m.get("strike_type") != "greater" or m.get("floor_strike") is None:
                continue
            bid, ask, vol = quote_at(m, t) if kalshi.ts(m["open_time"]) < t else (None, None, 0.0)
            rows.append(
                {
                    "event": e["event_ticker"],
                    "day": day,
                    "strike": float(m["floor_strike"]),
                    "bid": bid,
                    "ask": ask,
                    "volume_to_read": vol,
                    "volume": kalshi.volume(m),
                    "yes": kalshi.result_yes(m),
                    "aaa": kalshi.to_float(m.get("expiration_value")),
                    "open_ts": kalshi.ts(m["open_time"]),
                    "read_ts": t,
                }
            )
        if i % 25 == 0:
            print("{}/{} events".format(i, len(evs)), flush=True)
    return pd.DataFrame(rows)


def rbob():
    url = "https://query1.finance.yahoo.com/v8/finance/chart/RB=F?range=10y&interval=1d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    d = json.loads(urllib.request.urlopen(req, timeout=30).read())["chart"]["result"][0]
    ts = pd.to_datetime(d["timestamp"], unit="s", utc=True).tz_convert("America/New_York").normalize()
    return (
        pd.DataFrame({"date": ts.tz_localize(None), "rbob": d["indicators"]["quote"][0]["close"]})
        .dropna()
        .drop_duplicates("date", keep="last")
    )


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    r = rbob()
    r.to_parquet(OUT / "rbob.parquet", index=False)
    print("rbob", len(r), "days", r["date"].min().date(), "to", r["date"].max().date(), flush=True)
    lad = ladders()
    lad.to_parquet(OUT / "ladders.parquet", index=False)
    print("ladders", lad["event"].nunique(), "events,", len(lad), "markets", flush=True)


if __name__ == "__main__":
    main()
