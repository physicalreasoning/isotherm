#!/usr/bin/env python3
"""Phase 0: which prediction-market domain is worth building a decision model for?

Measures, for a shortlist spanning every category with real volume, the things
that decide whether a calibrated decision model has anything to learn:

  sample size   settled events, history depth, events per day
  liquidity     event volume, quoted spread and two-sided share at mid-life
  headroom      how well the market mid already predicts the outcome
                (Brier, ECE, logistic calibration slope, all bootstrapped by event)

A market whose mid is perfectly calibrated with tight spreads leaves a model
nothing to add from price alone; the case for a domain then rests entirely on
an exogenous information source, which is assessed qualitatively in
docs/01-market-selection.md. Everything measured here is reproducible from the
unauthenticated Kalshi API; settled responses are cached so a rerun is free.

    uv run scripts/survey_markets.py --events 30
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import math
import pathlib
import random
import sys
import time

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from isotherm import kalshi  # noqa: E402

CANDIDATES = [
    # series,          category,      note
    ("KXHIGHNY", "weather", "NYC daily high, bucket ladder"),
    ("KXHIGHCHI", "weather", "Chicago daily high"),
    ("KXHIGHLAX", "weather", "LA daily high"),
    ("KXHIGHMIA", "weather", "Miami daily high"),
    ("KXRAINNYC", "weather", "NYC rain, monthly/daily"),
    ("KXWTI", "commodities", "WTI daily range"),
    ("KXGOLDD", "commodities", "Gold daily"),
    ("KXGOLD15M", "commodities", "Gold 15-minute up/down"),
    ("KXMLBGAME", "sports", "MLB game winner"),
    ("KXNBAGAME", "sports", "NBA game winner"),
    ("KXATPMATCH", "sports", "ATP match winner"),
    ("KXFEDDECISION", "economics", "FOMC decision"),
    ("KXCPIYOY", "economics", "CPI YoY"),
    ("KXAAAGASD", "economics", "AAA gas daily up/down"),
    ("KXINX", "financials", "S&P 500 daily range"),
    ("KXINXU", "financials", "S&P 500 hourly above/below"),
    ("KXBTCD", "crypto", "BTC hourly above/below (pm-jepa control)"),
]

LEADS = (0.5, 0.9)  # fraction of market life elapsed at which we read the quote
MAX_MARKETS_PER_EVENT = 6  # most-traded markets of a ladder; keeps 188-strike ladders cheap
CONTESTED = (0.05, 0.95)  # a mid outside this range carries no calibration information


def quote_at(cs, t):
    """(bid, ask) from the last candle that closed at or before t."""
    best = None
    for c in cs:
        if c["end_period_ts"] <= t:
            best = c
        else:
            break
    if best is None:
        return None, None
    return kalshi.candle_quote(best)


def survey_event(ev):
    rows = kalshi.event_markets(ev["event_ticker"])
    rows = [r for r in rows if kalshi.result_yes(r) is not None]
    if not rows:
        return None
    out = {
        "event": ev["event_ticker"],
        "n_markets": len(rows),
        "volume": sum(kalshi.volume(r) for r in rows),
        "obs": [],
    }
    rows.sort(key=kalshi.volume, reverse=True)
    for r in rows[:MAX_MARKETS_PER_EVENT]:
        o, c = kalshi.ts(r["open_time"]), kalshi.ts(r["close_time"])
        life = c - o
        if life <= 0:
            continue
        interval = 1 if life <= 6 * 3600 else 60
        try:
            cs = kalshi.candles(r, interval=interval)
        except Exception as e:  # opaque 400s on a few windows; skip, count, move on
            out.setdefault("errors", []).append(str(e)[:60])
            continue
        cs.sort(key=lambda x: x["end_period_ts"])
        for lead in LEADS:
            b, a = quote_at(cs, o + lead * life)
            out["obs"].append(
                {"lead": lead, "bid": b, "ask": a, "y": kalshi.result_yes(r), "life_h": life / 3600}
            )
    return out


def logit(p):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def calib_slope(mid, y):
    """Slope b in P(y)=sigmoid(a + b*logit(mid)). b<1: market overconfident; b>1: underconfident."""
    from sklearn.linear_model import LogisticRegression

    if len(set(y)) < 2:
        return float("nan")
    m = LogisticRegression(C=1e6, max_iter=1000).fit(logit(mid)[:, None], y)
    return float(m.coef_[0, 0])


def ece(p, y, bins=10):
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, edges) - 1, 0, bins - 1)
    tot = 0.0
    for k in range(bins):
        s = idx == k
        if s.any():
            tot += s.mean() * abs(p[s].mean() - y[s].mean())
    return float(tot)


def summarise(series, events, n_listed, first, last, boot=300, seed=0):
    rng = np.random.default_rng(seed)
    ev = [e for e in events if e]
    res = {
        "series": series,
        "listed_settled_events": n_listed,
        "first_event": first,
        "last_event": last,
        "sampled_events": len(ev),
        "median_event_volume": float(np.median([e["volume"] for e in ev])) if ev else None,
        "median_markets_per_event": float(np.median([e["n_markets"] for e in ev])) if ev else None,
        "median_life_h": float(np.median([o["life_h"] for e in ev for o in e["obs"]])) if ev else None,
    }
    for lead in LEADS:
        per_event = []
        n_all = n_two = 0
        spreads = []
        for e in ev:
            rows = []
            for o in e["obs"]:
                if o["lead"] != lead:
                    continue
                n_all += 1
                b, a = o["bid"], o["ask"]
                if b is None or a is None or b <= 0 or a >= 1 or a < b:
                    continue
                n_two += 1
                mid = (a + b) / 2
                if CONTESTED[0] <= mid <= CONTESTED[1]:
                    spreads.append(a - b)
                    rows.append((mid, o["y"]))
            if rows:
                per_event.append(np.array(rows))
        key = "lead{}".format(lead)
        res[key] = {
            "two_sided_share": n_two / n_all if n_all else None,
            "contested_obs": int(sum(len(r) for r in per_event)),
            "median_spread": float(np.median(spreads)) if spreads else None,
        }
        if len(per_event) < 5:
            continue
        allr = np.concatenate(per_event)
        p, y = allr[:, 0], allr[:, 1]
        stats = {
            "brier": float(np.mean((p - y) ** 2)),
            "brier_climo": float(np.mean((y.mean() - y) ** 2)),
            "ece": ece(p, y),
            "slope": calib_slope(p, y),
        }
        bs = {k: [] for k in stats}
        for _ in range(boot):
            pick = rng.integers(0, len(per_event), len(per_event))
            r = np.concatenate([per_event[i] for i in pick])
            pp, yy = r[:, 0], r[:, 1]
            bs["brier"].append(np.mean((pp - yy) ** 2))
            bs["brier_climo"].append(np.mean((yy.mean() - yy) ** 2))
            bs["ece"].append(ece(pp, yy))
            bs["slope"].append(calib_slope(pp, yy))
        for k, v in stats.items():
            v_ = np.array([x for x in bs[k] if not math.isnan(x)])
            res[key][k] = v
            res[key][k + "_ci"] = (
                [float(np.percentile(v_, 2.5)), float(np.percentile(v_, 97.5))] if len(v_) else None
            )
        res[key]["brier_skill"] = (
            1 - stats["brier"] / stats["brier_climo"] if stats["brier_climo"] > 0 else None
        )
    return res


def run_series(series, n_events, max_pages, seed):
    t0 = time.time()
    evs = kalshi.settled_events(series, max_pages=max_pages)
    dates = sorted(e["strike_date"][:10] for e in evs if e.get("strike_date"))
    rng = random.Random(seed)
    # Sample from the most recent 1000 listed events: recent market structure is
    # what we would trade, and older events of renamed series use other tickers.
    pool = evs[:1000]
    sample = rng.sample(pool, min(n_events, len(pool)))
    with cf.ThreadPoolExecutor(6) as ex:
        out = list(ex.map(lambda e: _safe(survey_event, e), sample))
    s = summarise(series, out, len(evs), dates[0] if dates else None, dates[-1] if dates else None, seed=seed)
    s["seconds"] = round(time.time() - t0, 1)
    s["listing_truncated"] = len(evs) >= max_pages * 200
    return s


def _safe(f, x):
    try:
        return f(x)
    except Exception as e:
        print("   skip {}: {}".format(x.get("event_ticker"), str(e)[:80]), flush=True)
        return None


def fmt(x, nd=3):
    return (
        "-"
        if x is None or (isinstance(x, float) and math.isnan(x))
        else ("{:.%df}" % nd).format(x)
        if isinstance(x, float)
        else str(x)
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", type=int, default=30)
    ap.add_argument("--max-pages", type=int, default=40)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--out", default="results/survey.json")
    a = ap.parse_args()

    results = []
    for series, cat, note in CANDIDATES:
        if a.only and series not in a.only:
            continue
        print("== {} ({})".format(series, cat), flush=True)
        try:
            s = run_series(series, a.events, a.max_pages, a.seed)
        except Exception as e:
            print("   FAILED {}".format(e), flush=True)
            continue
        s.update(category=cat, note=note)
        results.append(s)
        l5 = s.get("lead0.5", {})
        print(
            "   events={} since={} vol/ev={} two-sided={} spread={} brier={} ece={} slope={} ({}s)".format(
                s["listed_settled_events"],
                s["first_event"],
                fmt(s["median_event_volume"], 0),
                fmt(l5.get("two_sided_share"), 2),
                fmt(l5.get("median_spread")),
                fmt(l5.get("brier")),
                fmt(l5.get("ece")),
                fmt(l5.get("slope"), 2),
                s["seconds"],
            ),
            flush=True,
        )

    p = pathlib.Path(a.out)
    p.parent.mkdir(exist_ok=True)
    p.write_text(
        json.dumps(
            {
                "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "config": vars(a),
                "results": results,
            },
            indent=2,
        )
    )
    print("wrote", p)


if __name__ == "__main__":
    main()
