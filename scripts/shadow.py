#!/usr/bin/env python3
"""Shadow-score the frozen strategy live. Run hourly by .github/workflows/shadow.yml.

uv run scripts/shadow.py score settle report       # what CI runs
uv run scripts/shadow.py score --force --root /tmp/x  # test outside the 16:00 window
"""

from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from isotherm import shadow  # noqa: E402


def write_report(root: pathlib.Path, r: dict):
    (root / "metrics.json").write_text(json.dumps(r, indent=2, sort_keys=True) + "\n")
    L = [
        "# Shadow record",
        "",
        "Frozen strategy from FINDINGS §9, scored live at 16:00 local the day before. "
        "Paper trades only. Lockbox reference: +$1,851 over 95 days.",
        "",
        "| | |",
        "|---|---|",
        "| Settled ladders | {} |".format(r.get("settled_ladders", 0)),
    ]
    dec = r.get("decay")
    if dec:
        L.insert(
            4,
            "**Status: {}** (stop rule: last two {}-day windows both below zero, CI included)".format(
                dec["status"], dec["window_days"]
            ),
        )
        L.insert(5, "")
    if "log_score_gain_vs_market" in r:
        ci = r.get("gain_ci")
        L.append(
            "| Log score gain vs market | {:+.4f}{} |".format(
                r["log_score_gain_vs_market"], " [{:+.4f}, {:+.4f}]".format(*ci) if ci else ""
            )
        )
    if "pnl" in r:
        L += [
            "| Paper PnL | ${:,.0f} over {} trades |".format(r["pnl"], r["trades"]),
            "| Hit rate | {:.1%} |".format(r["hit_rate"] or 0),
        ]
        L += ["", "| Month | PnL |", "|---|---:|"]
        L += ["| {} | ${:,.0f} |".format(k, v) for k, v in r["by_month"].items()]
        if r.get("by_regime"):
            L += ["", "| Settlement source | PnL |", "|---|---:|"]
            L += ["| {} | ${:,.0f} |".format(k, v) for k, v in r["by_regime"].items()]
    if dec and dec["windows"]:
        L += ["", "| Window | Settled days | Log score gain vs market [95% CI] |", "|---|---:|---|"]
        for w in dec["windows"]:
            ci = " [{:+.4f}, {:+.4f}]".format(*w["ci"]) if "ci" in w else ""
            L.append("| {} to {} | {} | {:+.4f}{} |".format(w["from"], w["to"], w["days"], w["gain"], ci))
    (root / "REPORT.md").write_text("\n".join(L) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("steps", nargs="+", choices=["score", "settle", "report"])
    ap.add_argument("--root", default="shadow")
    ap.add_argument("--force", action="store_true", help="score now, ignoring the 16:00 window")
    a = ap.parse_args()
    root = pathlib.Path(a.root)
    root.mkdir(parents=True, exist_ok=True)
    if not (root / "frozen.json").exists():
        shutil.copy("shadow/frozen.json", root / "frozen.json")
    for step in a.steps:
        if step == "score":
            for r in shadow.score_all(root, force=a.force):
                print("score", r.get("city"), r.get("event"), r["status"])
        elif step == "settle":
            print("settle: {} market outcomes recorded".format(shadow.settle(root)))
        else:
            r = shadow.report(root)
            write_report(root, r)
            print("report:", json.dumps(r))


if __name__ == "__main__":
    main()
