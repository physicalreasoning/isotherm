#!/usr/bin/env python3
"""Fetch Kalshi non-weather daily numeric ladders and price every bucket at fixed leads before close.

Exploratory (FINDINGS §39 follow-up: does market sharpening hold outside weather?). Public,
unauthenticated endpoints only, through the throttled, cached client in isotherm.kalshi, with a
hard cap on new (uncached) network requests.

Per series: list settled events, keep the newest --events, fetch each event's markets, keep only
ladders that partition the line, then fetch hourly candles over the last 25 hours before close
(one batch request for events settled after the historical cutoff, one request per market before
it). Events are processed round robin across series, newest first, so a budget stop cuts events
per series evenly rather than whole series.

    uv run scripts/alpha_xcat/fetch_ladders.py
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import pathlib
import sys
import threading

import numpy as np
import pandas as pd

os.environ.pop("KALSHI_API_KEY_ID", None)  # never sign: public data only
os.environ.pop("KALSHI_PRIVATE_KEY_PATH", None)
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from isotherm import kalshi  # noqa: E402

OUT = ROOT / "results" / "alpha_xcat"
SERIES = ["KXINX", "KXNASDAQ100", "KXEURUSD", "KXUSDJPY"]
LEADS_H = [1, 6, 24]
WINDOW_H = 25

_lock = threading.Lock()
_calls = [0]
CAP = [24000]
_orig_fetch = kalshi._fetch


def _counted(url):
    with _lock:
        _calls[0] += 1
        if _calls[0] > CAP[0]:
            raise RuntimeError("request cap reached")
    return _orig_fetch(url)


kalshi._fetch = _counted


def interval(m):
    """Half-open [lo, hi) of the settlement value for one market; None if unparseable."""
    st = m.get("strike_type")
    fl, cp = kalshi.to_float(m.get("floor_strike")), kalshi.to_float(m.get("cap_strike"))
    if st == "less" and cp is not None:
        return -np.inf, cp
    if st == "greater" and fl is not None:
        return fl, np.inf
    if st == "between" and fl is not None and cp is not None:
        return fl, cp
    return None


def partition(ivs):
    """(ok, reason). Sorted intervals must start at -inf, end at +inf and abut within a tick.

    Kalshi writes a range bucket as [floor, next_floor - tick], e.g. 7400 to 7424.9999, so
    neighbours abut when the gap is small relative to the bucket width.
    """
    if any(iv is None for iv in ivs):
        return False, "unparseable strike"
    iv = sorted(ivs)
    if len(iv) < 4:
        return False, "fewer than 4 buckets"
    if iv[0][0] != -np.inf or iv[-1][1] != np.inf:
        return False, "no open tail at one end"
    widths = [b - a for a, b in iv[1:-1]]
    if not widths:
        return False, "fewer than 4 buckets"
    tol = 0.02 * float(np.median(widths))
    for a, b in zip(iv[:-1], iv[1:], strict=True):
        gap = b[0] - a[1]
        if gap < -tol or gap > tol:
            return False, "gap or overlap between buckets"
    return True, ""


def quote_at(cs, t):
    """(bid, ask, cumulative volume) at the close of the last hourly candle ending at or before t."""
    best, vol = None, 0.0
    for c in cs:
        if c["end_period_ts"] <= t:
            best = c
            vol += kalshi.candle_volume(c)
        else:
            break
    if best is None:
        return None, None, 0.0
    b, a = kalshi.candle_quote(best)
    return b, a, vol


def fetch_candles(ms, close_ts):
    """{ticker: sorted candles} over [close - 25 h, close]."""
    start = close_ts - WINDOW_H * 3600
    if close_ts >= kalshi.cutoff_ts():
        tk = ",".join(m["ticker"] for m in ms)
        d = kalshi.get(
            "markets/candlesticks",
            _cache=True,
            market_tickers=tk,
            start_ts=start,
            end_ts=close_ts,
            period_interval=60,
        )
        got = {x["market_ticker"]: x.get("candlesticks") or [] for x in d.get("markets", [])}
        if set(got) != {m["ticker"] for m in ms}:
            raise RuntimeError("batch candles incomplete")
    else:
        got = {m["ticker"]: kalshi.candles(m, 60, start, close_ts) for m in ms}
    return {k: sorted(v, key=lambda c: c["end_period_ts"]) for k, v in got.items()}


def event_markets(ev):
    """Market rows; events settled before the historical cutoff go straight to the cached endpoint.

    kalshi.event_markets first asks the live endpoint (never cached) and only then the historical
    one, which would spend an uncached request per old event on every rerun.
    """
    strike = ev.get("strike_date")
    if strike and kalshi.ts(strike) < kalshi.cutoff_ts() - 2 * 86400:
        d = kalshi.get("historical/markets", _cache=True, event_ticker=ev["event_ticker"], limit=1000)
        rows = d.get("markets", [])
        if rows:
            return rows
    return kalshi.event_markets(ev["event_ticker"])


def build_event(series, ev, drops):
    def add(k):
        with _lock:
            d = drops.setdefault(series, {})
            d[k] = d.get(k, 0) + 1

    ms = event_markets(ev)
    ms = [m for m in ms if m.get("status") not in ("initialized",)]
    if not ms:
        add("event has no markets")
        return []
    if any(kalshi.result_yes(m) is None for m in ms):
        add("event has a market without a yes/no result")
        return []
    ivs = [interval(m) for m in ms]
    ok, why = partition(ivs)
    if not ok:
        add("not a partition ladder: " + why)
        return []
    ys = [kalshi.result_yes(m) for m in ms]
    if sum(ys) != 1:
        add("not exactly one YES")
        return []
    close_ts = max(kalshi.ts(m["close_time"]) for m in ms)
    open_ts = min(kalshi.ts(m["open_time"]) for m in ms)
    try:
        cs = fetch_candles(ms, close_ts)
    except RuntimeError as e:
        if "cap" in str(e):
            raise
        add("candle fetch failed")
        return []
    except Exception:
        add("candle fetch failed")
        return []
    add("partition ladder fetched")
    rows = []
    for m, iv, y in zip(ms, ivs, ys, strict=True):
        for lead in LEADS_H:
            t = close_ts - lead * 3600
            b, a, v = quote_at(cs[m["ticker"]], t) if t >= open_ts else (None, None, 0.0)
            rows.append(
                {
                    "series": series,
                    "event": ev["event_ticker"],
                    "close_ts": close_ts,
                    "open_ts": open_ts,
                    "date": pd.Timestamp(close_ts, unit="s").strftime("%Y-%m-%d"),
                    "ticker": m["ticker"],
                    "lo": iv[0],
                    "hi": iv[1],
                    "y": y,
                    "settle": kalshi.to_float(m.get("expiration_value")),
                    "lead_h": lead,
                    "open_at_read": bool(t >= open_ts),
                    "bid": b,
                    "ask": a,
                    "cum_volume": v,
                    "market_volume": kalshi.volume(m),
                }
            )
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", type=int, default=300)
    ap.add_argument("--cap", type=int, default=24000)
    ap.add_argument("--workers", type=int, default=2)
    args = ap.parse_args()
    CAP[0] = args.cap
    drops, lists = {}, {}
    for s in SERIES:
        evs = kalshi.settled_events(s, max_pages=5)
        evs = sorted(evs, key=lambda e: e.get("strike_date") or "", reverse=True)
        drops[s] = {"settled events listed (newest 1000 max)": len(evs)}
        lists[s] = evs[: args.events]
        drops[s]["newest kept for fetch"] = len(lists[s])
    order = []
    for i in range(args.events):
        for s in SERIES:
            if i < len(lists[s]):
                order.append((s, lists[s][i]))
    rows, done, stopped = [], 0, False
    with cf.ThreadPoolExecutor(args.workers) as ex:
        futs = {ex.submit(build_event, s, e, drops): (s, e) for s, e in order}
        for f in cf.as_completed(futs):
            try:
                rows += f.result()
            except Exception as e:
                key = "not fetched: request cap reached" if "cap" in str(e) else "event fetch error"
                stopped = stopped or "cap" in str(e)
                s = futs[f][0]
                with _lock:
                    drops[s][key] = drops[s].get(key, 0) + 1
            done += 1
            if done % 100 == 0:
                print("{}/{} events, {} new requests".format(done, len(order), _calls[0]), flush=True)
    df = pd.DataFrame(rows)
    df.to_parquet(OUT / "ladders_raw.parquet", index=False)
    log = {"new_requests": _calls[0], "cap": args.cap, "stopped_by_cap": stopped, "filters": drops}
    (OUT / "fetch_log.json").write_text(json.dumps(log, indent=1))
    print(json.dumps(log, indent=1))


if __name__ == "__main__":
    main()
