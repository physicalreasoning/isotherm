#!/usr/bin/env python3
"""Paper market making on recorded books: liquidity rewards against the cost of being filled.

Policy, per market and side: rest S contracts at the best bid (YES bids and NO bids), rejoining
at the back of the queue whenever the best bid moves; after a fill, replenish while the net
position stays within LIMIT contracts. Positions are held to settlement.

Fills come from the recorded flow. A trade that hits our side at our price (a taker selling YES
into YES bids shows as taker_side "no" at that YES price, and the mirror for NO bids) first
consumes the queue ahead of us, then our order. A size decrease at our price that no trade
explains is a cancellation and shrinks the queue ahead pro rata. Not modelled: our order changing
anyone's behaviour, and a trade reported after its book change (it is then read as a cancel,
which only delays our fills).

Rewards: Kalshi's Liquidity Incentive Program (help.kalshi.com), scored every STEP seconds as in
lip_estimate.py, with our actual resting size. Fees: Kalshi's maker fee, 0.0175 x C x P x (1-P).

    uv run scripts/book/maker_sim.py --series KXRAIN --sizes 50 200
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from collections import defaultdict
from decimal import Decimal

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from lip_estimate import REWARD_UNIT, STEP, programs, side_score  # noqa: E402
from replay import ROOT, file_order, levels, read_lines  # noqa: E402

from isotherm import kalshi  # noqa: E402

MAKER_FEE = 0.0175
LIMIT_MULT = 2  # net position cap, in multiples of S


class Quote:
    __slots__ = ("price", "left", "ahead")

    def __init__(self):
        self.price, self.left, self.ahead = None, 0.0, 0.0


def best(side: dict):
    return max(side) if side else None


def run(series: str, S: float, progs: dict, files) -> dict:
    books: dict = {}
    quotes = defaultdict(lambda: {"yes": Quote(), "no": Quote()})
    pos = defaultdict(float)  # net YES contracts per market (NO fills count negative)
    fills = []
    pending = defaultdict(float)  # (ticker, side, price) -> traded size not yet seen as a delta
    acc = defaultdict(lambda: {"total": 0.0, "ours": 0.0, "snaps": 0, "eligible": 0})
    next_snap = 0
    pre = f'"market_ticker": "{series}-'

    def place(tk, side):
        q, book = quotes[tk][side], books[tk][side]
        b = best(book)
        net = pos[tk] if side == "yes" else -pos[tk]
        cap = LIMIT_MULT * S - max(net, 0.0)
        q.price, q.left = b, (min(S, max(cap, 0.0)) if b is not None else 0.0)
        q.ahead = float(book.get(b, 0)) if b is not None else 0.0

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
            tk, typ = msg.get("market_ticker"), m.get("type")
            if typ == "orderbook_snapshot":
                books[tk] = {s: levels(msg.get(f"{s}_dollars_fp")) for s in ("yes", "no")}
                for s in ("yes", "no"):
                    place(tk, s)  # a fresh snapshot: rejoin at the back
            elif typ == "trade" and tk in books:
                yes_px = Decimal(msg["yes_price_dollars"])
                side = "yes" if msg["taker_side"] == "no" else "no"  # the resting side that was hit
                px = yes_px if side == "yes" else Decimal(1) - yes_px
                v = float(msg["count_fp"])
                pending[(tk, side, px)] += v
                q = quotes[tk][side]
                if q.price == px and q.left > 0:
                    use = min(v, q.ahead)
                    q.ahead -= use
                    got = min(v - use, q.left)
                    if got > 0:
                        q.left -= got
                        pos[tk] += got if side == "yes" else -got
                        fills.append({"ticker": tk, "side": side, "price": float(px), "qty": got, "t": t_ms})
                        if q.left <= 0:
                            place(tk, side)
            elif typ == "orderbook_delta" and tk in books:
                side, px, dv = msg["side"], Decimal(msg["price_dollars"]), Decimal(msg["delta_fp"])
                book = books[tk][side]
                before = float(book.get(px, 0))
                book[px] = book.get(px, Decimal(0)) + dv
                if book[px] <= 0:
                    del book[px]
                q = quotes[tk][side]
                if dv < 0 and q.price == px:
                    executed = min(pending[(tk, side, px)], float(-dv))
                    pending[(tk, side, px)] -= executed
                    cancelled = float(-dv) - executed
                    others = max(before - executed, 1e-9)
                    q.ahead = max(0.0, q.ahead - cancelled * q.ahead / others)
                if best(book) != q.price:
                    place(tk, side)
            else:
                continue
            sec = t_ms // 1000
            if sec < next_snap:
                continue
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
                        ours = quotes[tk2]["yes"].left + quotes[tk2]["no"].left
                        r["total"] += sy + sn
                        r["ours"] += ours
    return {"fills": fills, "acc": acc}


def settle(tickers) -> dict:
    out = {}
    for tk in tickers:
        try:
            m = kalshi.get(f"markets/{tk}").get("market", {})
        except Exception:  # noqa: BLE001
            continue
        y = kalshi.result_yes(m)
        if y is not None:
            out[tk] = int(y)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--series", default="KXRAIN")
    ap.add_argument("--sizes", type=float, nargs="+", default=[50, 200])
    a = ap.parse_args()
    progs = programs(a.series)
    files = sorted(ROOT.glob("*/*.jsonl.gz"), key=file_order)
    res = {"series": a.series, "by_size": {}}
    for S in a.sizes:
        r = run(a.series, S, progs, files)
        f = pd.DataFrame(r["fills"])
        y = settle(sorted(set(f["ticker"]))) if len(f) else {}
        if len(f):
            f["y"] = f["ticker"].map(y)
            f = f.dropna(subset=["y"])
            win = f["y"].where(f["side"] == "yes", 1 - f["y"])  # did the contract we bought pay
            f["pnl"] = f["qty"] * (win - f["price"])
            f["fee"] = MAKER_FEE * f["qty"] * f["price"] * (1 - f["price"])
        byid = {p["id"]: p for ps in progs.values() for p in ps}
        reward = 0.0
        for pid, s in r["acc"].items():
            if s["eligible"]:
                share = s["ours"] / (s["ours"] + s["total"])
                reward += share * byid[pid]["period_reward"] * REWARD_UNIT * s["eligible"] / s["snaps"]
        out = {
            "fills": int(len(f)),
            "contracts_filled": float(f["qty"].sum()) if len(f) else 0.0,
            "markets_filled": int(f["ticker"].nunique()) if len(f) else 0,
            "fill_pnl_usd": float(f["pnl"].sum()) if len(f) else 0.0,
            "maker_fees_usd": float(f["fee"].sum()) if len(f) else 0.0,
            "mean_edge_per_contract": float(f["pnl"].sum() / f["qty"].sum()) if len(f) else None,
            "rewards_usd": reward,
            "programs": len(r["acc"]),
        }
        out["net_usd"] = out["fill_pnl_usd"] - out["maker_fees_usd"] + out["rewards_usd"]
        res["by_size"][f"{S:g}"] = out
        print(S, json.dumps(out), flush=True)
    p = pathlib.Path("results/book/maker_sim.json")
    p.write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
