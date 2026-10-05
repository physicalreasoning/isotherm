#!/usr/bin/env python3
"""Build the point-in-time market panel for daily-high ladders.

One row per (city, day, bucket market, read time), holding only what was
observable at the read time: the last hourly candle that CLOSED at or before
it. Labels come from Kalshi's own settlement (`result`, `expiration_value`),
never from a weather archive, because the settlement source changed in 2026.

Read times are local wall-clock, so they mean the same thing to a trader in
every city and season:

    d1_16   16:00 the day before (after the 12Z MOS run is public)
    d0_08   08:00 on the day
    d0_12   12:00 on the day (intraday observations start to bind)
    d0_14   14:00 on the day (most daily highs are close to set)

    uv run scripts/build_weather_panel.py --cities NY CHI
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
from isotherm.weather import ALL_CITIES, CITIES  # noqa: E402

READ_TIMES = {"d1_16": (-1, 16), "d0_08": (0, 8), "d0_12": (0, 12), "d0_14": (0, 14)}
OUT = pathlib.Path("data/panel")


def event_day(ev_ticker: str) -> pd.Timestamp:
    """KXHIGHNY-26AUG03 / HIGHCHI-2-24FEB28 -> 2026-08-03 / 2024-02-28."""
    tag = ev_ticker.split("-")[-1]
    return pd.to_datetime(tag, format="%y%b%d")


def quote_at(cs, t):
    best = None
    for c in cs:
        if c["end_period_ts"] <= t:
            best = c
        else:
            break
    if best is None:
        return None, None, 0.0
    b, a = kalshi.candle_quote(best)
    vol = sum(kalshi.candle_volume(c) for c in cs if c["end_period_ts"] <= t)
    return b, a, vol


def build_event(city, ev):
    day = event_day(ev["event_ticker"])
    rows = [r for r in kalshi.event_markets(ev["event_ticker"]) if kalshi.result_yes(r) is not None]
    if not rows:
        return []
    reads = {}
    for name, (dd, hh) in READ_TIMES.items():
        local = (day + pd.Timedelta(days=dd)).replace(hour=hh).tz_localize(city.tz)
        reads[name] = int(local.tz_convert("UTC").timestamp())
    out = []
    for r in rows:
        # A failed fetch must not masquerade as an empty book: flag it, and a
        # rerun (cached for everything that succeeded) fills only the gaps.
        try:
            cs = sorted(kalshi.candles(r, interval=60), key=lambda c: c["end_period_ts"])
            ok = True
        except Exception as e:
            print("   candles {}: {}".format(r["ticker"], str(e)[:60]), flush=True)
            cs, ok = [], False
        base = {
            "city": city.key,
            "day": day,
            "event": ev["event_ticker"],
            "ticker": r["ticker"],
            "strike_type": r.get("strike_type"),
            "floor": kalshi.to_float(r.get("floor_strike")),
            "cap": kalshi.to_float(r.get("cap_strike")),
            "y": kalshi.result_yes(r),
            "settle": kalshi.to_float(r.get("expiration_value")),
            "open_ts": kalshi.ts(r["open_time"]),
            "close_ts": kalshi.ts(r["close_time"]),
            "market_volume": kalshi.volume(r),
            "candles_ok": ok,
            "rules": (r.get("rules_primary") or "")[:300],
        }
        for name, t in reads.items():
            b, a, v = quote_at(cs, t) if t >= base["open_ts"] else (None, None, 0.0)
            out.append(dict(base, read=name, read_ts=t, bid=b, ask=a, cum_volume=v))
    return out


def build_city(key, workers, limit):
    city = ALL_CITIES[key]
    t0 = time.time()
    evs = kalshi.settled_events(city.series)
    evs = [e for e in evs if e["event_ticker"].split("-")[-1][:2].isdigit()]
    if limit:
        evs = evs[:limit]
    print("== {} {}: {} settled events".format(key, city.series, len(evs)), flush=True)
    rows, done = [], 0
    with cf.ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(build_event, city, e): e for e in evs}
        for f in cf.as_completed(futs):
            try:
                rows.extend(f.result())
            except Exception as e:
                print("   skip {}: {}".format(futs[f]["event_ticker"], str(e)[:80]), flush=True)
            done += 1
            if done % 200 == 0:
                print("   {}/{} events, {:.0f}s".format(done, len(evs), time.time() - t0), flush=True)
    df = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / "{}.parquet".format(key)
    df.to_parquet(p, index=False)
    print(
        "   wrote {} ({} rows, {} events) in {:.0f}s".format(
            p, len(df), df["event"].nunique() if len(df) else 0, time.time() - t0
        ),
        flush=True,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cities", nargs="+", default=list(CITIES))
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0, help="events per city, 0 = all")
    a = ap.parse_args()
    for k in a.cities:
        build_city(k, a.workers, a.limit)


if __name__ == "__main__":
    main()
