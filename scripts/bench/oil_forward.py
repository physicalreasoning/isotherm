#!/usr/bin/env python3
"""Sealed forward test for oil (FINDINGS §48): does a lognormal on the WTI front-month future beat
Kalshi's KXWTI ladders a day before close, even at the market's most favourable in-quote prices?

Found by looking (§47, 104 ladders, +0.17 [+0.02, +0.35]), so it is tested once on events that
have not happened. Frozen: the outside model (code, hashed), its lead, the log-pool weights, the
window and the decision rule, in shadow/forward/oil.json. Nothing is refit.

    uv run scripts/bench/oil_forward.py --freeze   # once, before the window opens
    uv run scripts/bench/oil_forward.py            # score (refetches events and prices)
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))
import evaluate as ev  # noqa: E402
import fetch  # noqa: E402

from isotherm import kalshi, metrics  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
SPEC = ROOT / "shadow" / "forward" / "oil.json"
CODE = pathlib.Path(ev.__file__)
SERIES, SYMBOL = "KXWTI", "CL=F"
START, FINAL = "2026-10-12", "2027-04-05"
EXTEND, MIN_LADDERS = "2027-10-05", 80
OUT = ROOT / "results" / "bench" / "oil_forward.json"


def code_sha():
    return hashlib.sha256(CODE.read_bytes()).hexdigest()


def prices(refresh):
    f = ev.OUTSIDE / "{}.parquet".format(SYMBOL.replace("^", "").replace("=", "_"))
    if refresh:
        f.unlink(missing_ok=True)
    return ev.outside_prices(SYMBOL)


def with_outside(probs, px):
    for pr in probs:
        pr["out"] = ev.outside_dist(pr, px)
    return [p for p in probs if p["out"] is not None]


def freeze():
    assert not SPEC.exists(), "already frozen"
    df = pd.read_parquet(ev.RAW / "{}.parquet".format(SERIES))
    probs = with_outside(ev.problems(SERIES, df), prices(refresh=False))
    weights = {}
    for lead in ("24h", "6h"):
        P = [p for p in probs if p["lead"] == lead]
        weights[lead] = [float(x) for x in ev.fit_pool(P, "bid")]
    spec = {
        "frozen": pd.Timestamp.now(tz="UTC").isoformat(),
        "series": SERIES,
        "outside": SYMBOL,
        "code": str(CODE.relative_to(ROOT)),
        "code_sha256": code_sha(),
        "window": {"from_close": START, "to_close": FINAL},
        "extension": "if fewer than {} ladders at 24h by {}, continue to {} ladders or {}".format(
            MIN_LADDERS, FINAL, MIN_LADDERS, EXTEND
        ),
        "primary": (
            "24h: outside minus in-quote market, log loss; PASS if the 95% date-block CI lower bound > 0"
        ),
        "secondary": [
            "6h: the same comparison",
            "24h: log pool (frozen weights) of bid-priced market and outside, minus bid-priced market",
        ],
        "pool_bid_weights": weights,
        "history": {"ladders_24h": sum(p["lead"] == "24h" for p in probs)},
    }
    SPEC.write_text(json.dumps(spec, indent=2))
    print(json.dumps(spec, indent=1))


def window_events(lo, hi):
    lo_ts, hi_ts = (int(pd.Timestamp(x, tz="America/New_York").timestamp()) for x in (lo, hi))
    evs = [
        e for e in kalshi.settled_events(SERIES, max_pages=50) if e["event_ticker"].startswith(SERIES + "-")
    ]
    cutoff = kalshi.cutoff_ts()
    rows = []
    for e in evs:
        ms = kalshi.event_markets(e["event_ticker"])
        if not ms or not lo_ts <= max(kalshi.ts(m["close_time"]) for m in ms) < hi_ts + 86400:
            continue
        rows += fetch.event_rows(SERIES, "commodities", e, cutoff)
    return pd.DataFrame(rows)


def gain(rows, a, b):
    d = np.array([r[a] - r[b] for r in rows])
    days = np.array([r["day"] for r in rows])
    return {"diff": float(d.mean()), "ci": metrics.date_bootstrap_mean(days, d, 2000), "n": int(len(d))}


def score():
    spec = json.loads(SPEC.read_text())
    assert code_sha() == spec["code_sha256"], "frozen outside model changed"
    end = spec["window"]["to_close"]
    df = window_events(spec["window"]["from_close"], EXTEND)
    probs = with_outside(ev.problems(SERIES, df), prices(refresh=True)) if len(df) else []
    rows = {lead: [] for lead in ("24h", "6h")}
    for pr in probs:
        if pr["lead"] not in rows:
            continue
        w = spec["pool_bid_weights"][pr["lead"]]
        mb = ev.market(pr, "bid")
        rows[pr["lead"]].append(
            {
                "day": pr["day"],
                "outside": ev.logscore(pr["out"], pr),
                "clip": ev.logscore(ev.in_quote(pr), pr),
                "bid": ev.logscore(mb, pr),
                "pool": ev.logscore(ev.pool(mb, pr["out"], np.array(w)), pr),
            }
        )
    # The scored set: the window, extended only if it holds too few ladders at 24h.
    n_end = sum(r["day"] <= pd.Timestamp(end) for r in rows["24h"])
    stop = pd.Timestamp(end) if n_end >= MIN_LADDERS else None
    if stop is None:
        days = sorted(r["day"] for r in rows["24h"])
        stop = days[MIN_LADDERS - 1] if len(days) >= MIN_LADDERS else pd.Timestamp(EXTEND)
    for lead in rows:
        rows[lead] = [r for r in rows[lead] if r["day"] <= stop]
    r24 = rows["24h"]
    res = {
        "through": str(max((r["day"] for r in r24), default=None)),
        "scored_to": str(stop.date()),
        "complete": bool(pd.Timestamp.now() > stop + pd.Timedelta(days=1)),
        "primary_24h_outside_minus_inquote": gain(r24, "clip", "outside") if len(r24) > 1 else None,
        "secondary_6h_outside_minus_inquote": gain(rows["6h"], "clip", "outside")
        if len(rows["6h"]) > 1
        else None,
        "secondary_24h_pool_minus_bid": gain(r24, "bid", "pool") if len(r24) > 1 else None,
    }
    p = res["primary_24h_outside_minus_inquote"]
    if res["complete"] and p:
        res["verdict"] = "PASS" if p["ci"][0] > 0 else "FAIL"
    OUT.write_text(json.dumps(res, indent=2, default=str))
    print(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    freeze() if "--freeze" in sys.argv else score()
