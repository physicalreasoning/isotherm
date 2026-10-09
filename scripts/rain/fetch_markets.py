#!/usr/bin/env python3
"""Kalshi rain markets, point in time: KXRAIN (about 25 cities a day from 2026-07-15) and
KXRAINNYC / RAINNYC (Central Park, 2021-09 to 2026-07-15).

One row per (market, read): the last hourly candle that closed at or before the read, with its
yes bid and ask and the volume to date. Reads are local wall clock in the station's time zone:
16:00 the day before (primary) and 08:00 on the day. KXRAIN markets close early once it rains,
so a market already closed at a read is flagged (`closed_before_read`), never priced.

    uv run scripts/rain/fetch_markets.py      # data/rain/markets.parquet
"""

from __future__ import annotations

import concurrent.futures as cf
import re

import pandas as pd
from common import DATA, READS, corpus, read_time_utc, station_tz

from isotherm import kalshi

SERIES = ["KXRAIN", "KXRAINNYC"]


def event_day(ev: str) -> pd.Timestamp:
    return pd.to_datetime(ev.split("-")[1][:7], format="%y%b%d")


def station_of(m: dict) -> str | None:
    """CLIxxx (or, in five one-off markets, Kxxx) in the rules -> IEM ICAO K+xxx.

    The NYC-only series names Central Park in words.
    """
    r = m.get("rules_primary") or ""
    hit = re.search(r"\bCLI([A-Z]{3})\b", r) or re.search(r"\bat K([A-Z]{3}) in\b", r)
    if hit:
        return "K" + hit.group(1)
    if "Central Park" in r:
        return "KNYC"
    return None


def rule_day(r: str):
    """The day the rules name ("on October 26, 2021", "in Oct 7, 2026"); a few tickers disagree."""
    hit = re.search(r"\b([A-Z][a-z]+\.? \d{1,2}, \d{4})\b", r)
    if not hit:
        return None
    try:
        return pd.to_datetime(hit.group(1).replace(".", ""), format="mixed")
    except ValueError:
        return None


def rule_threshold(r: str):
    hit = re.search(r"(?:strictly )?greater than (\d+(?:\.\d+)?)", r)
    return float(hit.group(1)) if hit else None


def quote_at(cs: list, t: int):
    best, vol = None, 0.0
    for c in cs:
        if c["end_period_ts"] <= t:
            best = c
            vol += kalshi.candle_volume(c)
        else:
            break
    if best is None:
        return None, None, 0.0, None
    b, a = kalshi.candle_quote(best)
    return b, a, vol, best["end_period_ts"]


def build_event(series: str, ev: str, info: dict) -> list:
    out = []
    for m in kalshi.event_markets(ev):
        y = kalshi.result_yes(m)
        st = station_of(m)
        rules = m.get("rules_primary") or ""
        rd = rule_day(rules)
        day = rd if rd is not None else event_day(ev)
        base = {
            "series": series,
            "event": ev,
            "ticker": m["ticker"],
            "city": m["ticker"].split("-")[-1] if series == "KXRAIN" else "NYC",
            "station": st,
            "day": day,
            "ticker_day": event_day(ev),
            "threshold": rule_threshold(rules),
            "y": y,
            "open_ts": kalshi.ts(m["open_time"]),
            "close_ts": kalshi.ts(m["close_time"]),
            "market_volume": kalshi.volume(m),
            "rules": (m.get("rules_primary") or "")[:200],
        }
        if y is None or st is None or st not in info or base["threshold"] != 0:
            out.append(dict(base, read=None))
            continue
        tz = station_tz(st, info)
        try:
            cs = sorted(kalshi.candles(m, interval=60), key=lambda c: c["end_period_ts"])
            ok = True
        except Exception as e:  # a failed fetch must not look like an empty book
            print("   candles {}: {}".format(m["ticker"], str(e)[:60]), flush=True)
            cs, ok = [], False
        for read, (dd, hh) in READS.items():
            t = int(read_time_utc(pd.Series([day]), tz, dd, hh).iloc[0].timestamp())
            b, a, v, cts = quote_at(cs, t) if t > base["open_ts"] else (None, None, 0.0, None)
            out.append(
                dict(
                    base,
                    tz=tz,
                    read=read,
                    read_ts=t,
                    candles_ok=ok,
                    closed_before_read=base["close_ts"] <= t,
                    bid=b,
                    ask=a,
                    cum_volume=v,
                    candle_ts=cts,
                )
            )
    return out


def main():
    info = corpus()
    rows = []
    for s in SERIES:
        evs = [e["event_ticker"] for e in kalshi.settled_events(s)]
        print("{}: {} settled events".format(s, len(evs)), flush=True)
        with cf.ThreadPoolExecutor(4) as ex:
            futs = {ex.submit(build_event, s, e, info): e for e in evs}
            for i, f in enumerate(cf.as_completed(futs), 1):
                try:
                    rows.extend(f.result())
                except Exception as e:
                    print("   skip {}: {}".format(futs[f], str(e)[:80]), flush=True)
                if i % 100 == 0:
                    print("   {}/{}".format(i, len(evs)), flush=True)
    df = pd.DataFrame(rows)
    DATA.mkdir(parents=True, exist_ok=True)
    df.to_parquet(DATA / "markets.parquet", index=False)
    print("wrote {} rows, {} markets".format(len(df), df["ticker"].nunique()), flush=True)


if __name__ == "__main__":
    main()
