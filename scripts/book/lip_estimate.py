#!/usr/bin/env python3
"""What would Kalshi's Liquidity Incentive Program have paid a resting quote? (exploratory)

Kalshi snapshots each rewarded market's book once a second. On each side an order scores its
size times the discount factor raised to the number of ticks it sits below the side's reference
price (walking down from the best bid, the first level where cumulative size reaches a fifth of
the target size); orders at or above the reference score full size. A snapshot counts only when
both sides hold at least the target size. A participant's reward is its share of all snapshot
scores in the period times the period reward (help.kalshi.com, Liquidity Incentive Program).

From our recorded books (scripts/book/record.py) this replays every rewarded market of a series,
takes a snapshot every STEP seconds of recorded time, and asks: had we also rested S contracts at
the best bid on each side (YES and NO), what share of the period's score would we have had? It
ignores that our order would change the book and others' behaviour, and says nothing about the
cost of being filled (adverse selection), which is the other half of the question.

    uv run scripts/book/lip_estimate.py --series KXRAIN --sizes 100 500 1000
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from collections import defaultdict
from decimal import Decimal

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from replay import ROOT, file_order, levels, read_lines  # noqa: E402

from isotherm import kalshi  # noqa: E402

STEP = 10  # seconds between snapshots; an unbiased sample of Kalshi's once-a-second snapshots
REWARD_UNIT = 1e-4  # period_reward is "in centi-cents" (docs.kalshi.com, Get Incentives)


def programs(series: str) -> dict:
    out, cur = {}, None
    while True:
        r = kalshi.get("incentive_programs", limit=1000, **({"cursor": cur} if cur else {}))
        for p in r.get("incentive_programs", []):
            if p["market_ticker"].startswith(series + "-") and p["incentive_type"] == "liquidity":
                out.setdefault(p["market_ticker"], []).append(p)
        cur = r.get("next_cursor")
        if not cur:
            return out


def side_score(book_side: dict, target: float, disc: float) -> tuple[float, float, float]:
    """(total score, total size, best price) of one side; prices in dollars, ticks of 1 cent."""
    if not book_side:
        return 0.0, 0.0, 0.0
    px = sorted(book_side, reverse=True)
    size = np.array([float(book_side[p]) for p in px])
    cum = np.cumsum(size)
    ref_i = int(np.searchsorted(cum, target / 5))
    ref = float(px[min(ref_i, len(px) - 1)])
    ticks = np.maximum(0, np.round((ref - np.array([float(p) for p in px])) * 100))
    return float((size * disc**ticks).sum()), float(cum[-1]), float(px[0])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--series", default="KXRAIN")
    ap.add_argument("--sizes", type=float, nargs="+", default=[100, 500, 1000])
    a = ap.parse_args()
    progs = programs(a.series)
    files = sorted(ROOT.glob("*/*.jsonl.gz"), key=file_order)
    books: dict = {}
    next_snap = 0
    acc = defaultdict(
        lambda: {"snaps": 0, "eligible": 0, "total": 0.0, **{f"ours_{s:g}": 0.0 for s in a.sizes}}
    )
    pre = f'"market_ticker": "{a.series}-'
    for f in files:
        for line in read_lines(f):
            if pre not in line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            m, t_ms = rec["m"], rec["recv_ms"]
            msg = m.get("msg") or {}
            tk = msg.get("market_ticker")
            if m.get("type") == "orderbook_snapshot":
                books[tk] = {s: levels(msg.get(f"{s}_dollars_fp")) for s in ("yes", "no")}
            elif m.get("type") == "orderbook_delta" and tk in books:
                side = books[tk][msg["side"]]
                p = Decimal(msg["price_dollars"])
                side[p] = side.get(p, Decimal(0)) + Decimal(msg["delta_fp"])
                if side[p] <= 0:
                    del side[p]
            else:
                continue
            sec = t_ms // 1000
            if sec < next_snap:
                continue
            # A shared clock: every rewarded market is sampled at each step, busy or quiet.
            next_snap = sec - sec % STEP + STEP
            ts = pd.Timestamp(sec, unit="s", tz="UTC").isoformat()
            for tk2, book in books.items():
                for p in progs.get(tk2, []):
                    if not (p["start_date"] <= ts < p["end_date"]):
                        continue
                    tgt, disc = float(p["target_size_fp"]), p["discount_factor_bps"] / 1e4
                    sy, ny, _ = side_score(book["yes"], tgt, disc)
                    sn, nn, _ = side_score(book["no"], tgt, disc)
                    r = acc[p["id"]]
                    r["snaps"] += 1
                    if ny >= tgt and nn >= tgt:
                        r["eligible"] += 1
                        r["total"] += sy + sn
                        for sz in a.sizes:
                            r[f"ours_{sz:g}"] += 2 * sz  # S at the best bid on each side scores in full
    rows = []
    byid = {p["id"]: p for ps in progs.values() for p in ps}
    for pid, r in acc.items():
        p = byid[pid]
        dur = (pd.Timestamp(p["end_date"]) - pd.Timestamp(p["start_date"])).total_seconds()
        reward = p["period_reward"] * REWARD_UNIT
        row = {
            "ticker": p["market_ticker"],
            "reward_usd": reward,
            "coverage": r["snaps"] * STEP / dur,  # share of the period we recorded
            "eligible_share": r["eligible"] / max(r["snaps"], 1),
        }
        for s in a.sizes:
            ours = r[f"ours_{s:g}"]
            share = ours / (ours + r["total"]) if ours + r["total"] > 0 else 0.0
            row[f"share_{s:g}"] = share
            row[f"usd_{s:g}"] = share * reward * row["eligible_share"]  # pro rata over recorded time
        rows.append(row)
    df = pd.DataFrame(rows)
    out = pathlib.Path("results/book/lip_estimate.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    summ = {
        "series": a.series,
        "programs": int(len(df)),
        "median_coverage": float(df["coverage"].median()) if len(df) else 0,
        "median_eligible_share": float(df["eligible_share"].median()) if len(df) else 0,
        **{f"median_share_{s:g}": float(df[f"share_{s:g}"].median()) for s in a.sizes},
        **{f"mean_usd_per_program_{s:g}": float(df[f"usd_{s:g}"].mean()) for s in a.sizes},
        "reward_unit_assumed_usd": REWARD_UNIT,
    }
    out.write_text(json.dumps({"summary": summ, "programs": rows}, indent=1))
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
