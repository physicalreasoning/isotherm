#!/usr/bin/env python3
"""Markdown results table from results/bench/baselines.json (FINDINGS §47).

uv run scripts/bench/table.py [path]
"""

from __future__ import annotations

import json
import pathlib
import sys

COLS = [
    ("bid_minus_mid", "bid−mid"),
    ("sharp_minus_mid", "sharp−mid"),
    ("outside_minus_bid", "outside−bid"),
    ("pool_bid_minus_bid", "pool−bid"),
    ("outside_minus_clip", "outside−clip"),
]


def cell(v):
    if v is None:
        return ""
    lo, hi = v["ci"]
    s = "{:+.3f} [{:+.3f}, {:+.3f}]".format(v["diff"], lo, hi).replace("-", "−")
    return "**{}**".format(s) if lo > 0 or hi < 0 else s


def main():
    path = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "results/bench/baselines.json")
    res = json.loads(path.read_text())["results"]
    print("| Series | Lead | Ladders | Mid log loss | " + " | ".join(n for _, n in COLS) + " |")
    print("|---" * (4 + len(COLS)) + "|")
    for series, leads in res.items():
        for lead in ("24h", "6h", "1h"):
            r = leads.get(lead)
            if not r or r["problems"] < 20:
                continue
            row = [series, lead, str(r["problems"]), "{:.2f}".format(r["mid_logloss"])]
            print("| " + " | ".join(row + [cell(r.get(k)) for k, _ in COLS]) + " |")


if __name__ == "__main__":
    main()
