#!/usr/bin/env python3
"""Prediction-market benchmark, step 1 (docs/research/benchmark_plan.md): fetch settled events.

For each series, up to N settled events spread evenly over the series' life. For every market of
every event: strike structure, result, settlement value, and quote snapshots at fixed leads before
close (24 h, 6 h, 1 h) and at the open: bid, ask, volume to date, open interest. Events closing
after Kalshi's historical cutoff take one request (event candlesticks); older ones one request per
market. Resumable: one parquet per series, events already fetched are skipped.

    uv run scripts/bench/fetch.py                 # every series
    uv run scripts/bench/fetch.py KXINX KXWTI     # some
"""

from __future__ import annotations

import json
import pathlib
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))
from isotherm import kalshi  # noqa: E402

OUT = pathlib.Path("data/bench/raw")
EVENTS = pathlib.Path("data/bench/events")
LEADS = {"open": None, "24h": 24 * 3600, "6h": 6 * 3600, "1h": 3600}
SERIES = {
    # family, series: max events
    "weather": {"KXHIGHNY": 400, "KXHIGHCHI": 400, "KXLOWTNYC": 400, "KXRAIN": 400},
    "financial": {"KXINX": 400, "KXNASDAQ100": 400, "KXEURUSD": 400, "KXUSDJPY": 400},
    "commodities": {"KXWTI": 400},
    "crypto": {"KXBTC": 400},
    "economics": {"KXCPI": 400, "KXJOBLESSCLAIMS": 400},  # KXFED: 6 current-format events, dropped
    "gas": {"KXAAAGASD": 400},
}


def sample(events, n, series):
    """Up to n current-format events (ticker starts with the series), spread evenly over time.

    Legacy events (e.g. INX-22APR28, INXW-...) carry no strike fields and mix weekly with daily.
    """
    ev = sorted(
        (e for e in events if e["event_ticker"].startswith(series + "-")), key=lambda e: e["event_ticker"]
    )
    if len(ev) <= n:
        return ev
    idx = np.unique(np.linspace(0, len(ev) - 1, n).round().astype(int))
    return [ev[i] for i in idx]


def snaps(cs, open_ts, close_ts):
    """Quote snapshots from one market's hourly candles."""
    cs = sorted(cs or [], key=lambda c: c.get("end_period_ts", 0))
    out = {}
    for lead, sec in LEADS.items():
        t = open_ts + 3600 if sec is None else close_ts - sec
        before = [c for c in cs if c.get("end_period_ts", 0) <= t]
        if sec is not None and t < open_ts or not before:
            out[lead] = (None, None, 0.0, None)
            continue
        bid, ask = kalshi.candle_quote(before[-1])
        oi = kalshi.to_float(before[-1].get("open_interest_fp") or before[-1].get("open_interest"))
        out[lead] = (bid, ask, sum(kalshi.candle_volume(c) for c in before), oi)
    return out


def event_rows(series, family, e, cutoff):
    ms = kalshi.event_markets(e["event_ticker"])
    if not ms:
        return []
    open_ts = min(kalshi.ts(m["open_time"]) for m in ms)
    close_ts = max(kalshi.ts(m["close_time"]) for m in ms)
    candles = {}
    if close_ts >= cutoff:
        r = kalshi.get(
            "series/{}/events/{}/candlesticks".format(series, e["event_ticker"]),
            _cache=True,
            start_ts=open_ts,
            end_ts=close_ts,
            period_interval=60,
        )
        candles = dict(zip(r.get("market_tickers", []), r.get("market_candlesticks", []), strict=False))
    rows = []
    for m in ms:
        cs = candles.get(m["ticker"]) if candles else kalshi.candles(m, 60)
        s = snaps(cs, kalshi.ts(m["open_time"]), kalshi.ts(m["close_time"]))
        base = {
            "family": family,
            "series": series,
            "event": e["event_ticker"],
            "title": e.get("title"),
            "ticker": m["ticker"],
            "strike_type": m.get("strike_type"),
            "floor": kalshi.to_float(m.get("floor_strike")),
            "cap": kalshi.to_float(m.get("cap_strike")),
            "result": kalshi.result_yes(m),
            "settle_value": m.get("expiration_value"),
            "open_ts": kalshi.ts(m["open_time"]),
            "close_ts": kalshi.ts(m["close_time"]),
            "volume": kalshi.volume(m),
            "subtitle": m.get("yes_sub_title") or m.get("subtitle"),
            "rules": (m.get("rules_primary") or "")[:500],
        }
        for lead, (bid, ask, vol, oi) in s.items():
            base.update({"bid_" + lead: bid, "ask_" + lead: ask, "vol_" + lead: vol, "oi_" + lead: oi})
        rows.append(base)
    return rows


def fetch_series(family, series, n, cutoff):
    f = OUT / "{}.parquet".format(series)
    have = pd.read_parquet(f) if f.exists() else pd.DataFrame()
    done = set(have["event"]) if len(have) else set()
    evs = sample(kalshi.settled_events(series, max_pages=500), n, series)
    EVENTS.mkdir(parents=True, exist_ok=True)
    (EVENTS / "{}.json".format(series)).write_text(json.dumps([e["event_ticker"] for e in evs]))
    rows, fails, t0 = [], 0, time.time()
    for i, e in enumerate(evs, 1):
        if e["event_ticker"] in done:
            continue
        try:
            rows += event_rows(series, family, e, cutoff)
        except Exception as ex:  # one bad event must not stop a night's fetch
            fails += 1
            print("  {} failed: {}".format(e["event_ticker"], str(ex)[:80]), flush=True)
        if i % 50 == 0 or i == len(evs):
            part = pd.concat([have, pd.DataFrame(rows)], ignore_index=True) if rows else have
            part.to_parquet(f, index=False)
            print(
                "{} {}/{} events, {:.0f} min".format(series, i, len(evs), (time.time() - t0) / 60), flush=True
            )
    return len(evs), fails


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    want = set(sys.argv[1:])
    cutoff = kalshi.cutoff_ts()
    log = {}
    for family, ss in SERIES.items():
        for series, n in ss.items():
            if want and series not in want:
                continue
            log[series] = fetch_series(family, series, n, cutoff)
    print(json.dumps(log), flush=True)


if __name__ == "__main__":
    main()
