#!/usr/bin/env python3
"""Kalshi-wide sample of settled non-weather binary markets, priced at fixed horizons before close.

Exploratory (results/alpha/REPORT.md). Public, unauthenticated endpoints only; the throttled,
cached client in isotherm.kalshi; a hard cap on new (uncached) network requests.

Per series: list settled events (newest first, up to --event-pages pages of 200), sample
--events events spread evenly over that list, fetch the event's markets, pick at most two markets
per event (one if the event is a two-way mutually exclusive pair, whose second market is the
complement), fetch candles (1-minute if the market lived <= 6 h, else hourly over at most the
last 8 days) and record the quote at each horizon before close.

    KALSHI_MIN_INTERVAL=0.25 uv run scripts/alpha/fetch_binary_sample.py
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import random
import sys

import pandas as pd

os.environ.pop("KALSHI_API_KEY_ID", None)  # never sign: public data only
os.environ.pop("KALSHI_PRIVATE_KEY_PATH", None)
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))
from isotherm import kalshi  # noqa: E402

OUT = pathlib.Path("results/alpha/binary_sample.parquet")
LOG = pathlib.Path("results/alpha/binary_sample_fetch.json")

SERIES = {
    "Sports": ["KXNBAGAME", "KXNFLGAME", "KXNHLGAME", "KXEPLGAME", "KXUFCFIGHT", "KXATPMATCH"],
    "Economics": ["KXCPIYOY", "KXPAYROLLS", "KXFEDDECISION", "KXGDP", "KXAAAGASD", "KXTSAW"],
    "Financials": ["KXINX", "KXNASDAQ100", "KXEURUSD"],
    "Crypto": ["KXBTCD", "KXETHD"],
    "Commodities": ["KXWTI"],
    "Mentions": ["KXTRUMPMENTION", "KXTRUMPSAY"],
    "Entertainment": ["KXRT", "KXNETFLIXRANKMOVIE", "KXSPOTIFYD"],
    "Climate": ["KXRAINNYC"],
}
HORIZONS_H = [5 / 60, 1, 6, 24, 72]

_calls = [0]
_orig_fetch = kalshi._fetch


def _counted(url):
    _calls[0] += 1
    if _calls[0] > CAP[0]:
        raise RuntimeError("request cap reached")
    return _orig_fetch(url)


kalshi._fetch = _counted
CAP = [2900]


def f(x):
    return kalshi.to_float(x)


def candle_rows(cs):
    out = []
    for c in sorted(cs, key=lambda x: x["end_period_ts"]):
        b, a = kalshi.candle_quote(c)
        p = c.get("price") or {}
        last = f(p.get("close_dollars", p.get("close")))
        out.append((c["end_period_ts"], b, a, last, kalshi.candle_volume(c)))
    return out


def at(rows, t, open_ts):
    """State at time t from candles that ended at or before t."""
    prior = [r for r in rows if r[0] <= t]
    if not prior:
        return None
    end, b, a, _, _ = prior[-1]
    traded = [r for r in prior if r[4] > 0]
    last_trade = traded[-1] if traded else None
    vol24 = sum(r[4] for r in prior if r[0] > t - 86400)
    return {
        "bid": b,
        "ask": a,
        "last": last_trade[3] if last_trade else None,
        "stale_h": (t - last_trade[0]) / 3600 if last_trade else (t - open_ts) / 3600,
        "vol24": vol24,
        "vol_cum": sum(r[4] for r in prior),
        "candle_age_h": (t - end) / 3600,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", type=int, default=36)
    ap.add_argument("--event-pages", type=int, default=10)
    ap.add_argument("--cap", type=int, default=2900)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    CAP[0] = a.cap
    rng = random.Random(a.seed)
    obs, log = [], {"series": {}, "drops": {}}

    def drop(k, n=1):
        log["drops"][k] = log["drops"].get(k, 0) + n

    for cat, series in SERIES.items():
        for s in series:
            try:
                evs = list(
                    kalshi._paginate(
                        "events", "events", a.event_pages, series_ticker=s, status="settled", limit=200
                    )
                )
            except RuntimeError:
                break
            except Exception as e:
                log["series"][s] = {"error": str(e)[:100]}
                continue
            if not evs:
                log["series"][s] = {"events_listed": 0}
                continue
            step = max(1, len(evs) // a.events)
            pick = evs[::step][: a.events]
            n_obs0 = len(obs)
            for ev in pick:
                try:
                    rows = kalshi.event_markets(ev["event_ticker"])
                except RuntimeError:
                    break
                except Exception:
                    drop("event_listing_error")
                    continue
                rows = [r for r in rows if r.get("market_type", "binary") == "binary"]
                settled = [r for r in rows if kalshi.result_yes(r) is not None]
                if len(settled) < len(rows):
                    drop("markets_not_yes_no (voided/scalar/odd)", len(rows) - len(settled))
                if not settled:
                    drop("event_no_settled_markets")
                    continue
                closes = {r["close_time"][:19] for r in settled}
                early = any(r.get("can_close_early") for r in settled)
                if early and (len(closes) > 1 or len(settled) == 1):
                    # close time may depend on the outcome (e.g. a mention market closes on the
                    # mention): horizons before close would leak the result. Drop the event.
                    drop("event_outcome_dependent_close", 1)
                    continue
                if len(closes) > 1:
                    drop("event_mixed_close_times_kept_note")
                live = [r for r in settled if kalshi.volume(r) > 0]
                drop("markets_zero_volume", len(settled) - len(live))
                if not live:
                    continue
                k = 1 if (ev.get("mutually_exclusive") and len(settled) == 2) else 2
                chosen = rng.sample(live, min(k, len(live)))
                for r in chosen:
                    o, c = kalshi.ts(r["open_time"]), kalshi.ts(r["close_time"])
                    life = c - o
                    if life <= 0:
                        drop("market_bad_times")
                        continue
                    interval = 1 if life <= 6 * 3600 else 60
                    start = o if interval == 1 else max(o, c - 8 * 86400)
                    try:
                        cs = kalshi.candles(r, interval=interval, start_ts=start, end_ts=c)
                    except RuntimeError:
                        break
                    except Exception:
                        drop("candle_error")
                        continue
                    cr = candle_rows(cs)
                    if not cr:
                        drop("market_no_candles")
                        continue
                    for h in HORIZONS_H:
                        t = c - int(h * 3600)
                        if t <= o or (interval == 60 and h < 1):
                            continue  # market not open yet, or 5-min horizon on hourly candles
                        st = at(cr, t, o)
                        if st is None:
                            continue
                        obs.append(
                            {
                                "category": cat,
                                "series": s,
                                "event": ev["event_ticker"],
                                "ticker": r["ticker"],
                                "mutually_exclusive": bool(ev.get("mutually_exclusive")),
                                "n_markets_event": len(settled),
                                "open_ts": o,
                                "close_ts": c,
                                "life_h": life / 3600,
                                "h": h,
                                "t": t,
                                "y": kalshi.result_yes(r),
                                "market_volume": kalshi.volume(r),
                                "interval": interval,
                                **st,
                            }
                        )
            log["series"][s] = {
                "category": cat,
                "events_listed": len(evs),
                "events_sampled": len(pick),
                "obs": len(obs) - n_obs0,
                "first_listed": evs[-1]["event_ticker"],
                "last_listed": evs[0]["event_ticker"],
            }
            print(s, log["series"][s], "requests", _calls[0], flush=True)
            if _calls[0] >= CAP[0]:
                break
    log["new_requests"] = _calls[0]
    df = pd.DataFrame(obs)
    df.to_parquet(OUT, index=False)
    LOG.write_text(json.dumps(log, indent=1))
    print("obs", len(df), "requests", _calls[0])


if __name__ == "__main__":
    main()
