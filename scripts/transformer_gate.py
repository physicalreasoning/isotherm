#!/usr/bin/env python3
"""Score the pre-registered transformer gate (FINDINGS §16) from the cached walk-forward predictions.

uv run scripts/benchmark.py --suite transformer   # computes and caches the predictions
uv run scripts/transformer_gate.py
"""

from __future__ import annotations

import json
import pathlib
import sys

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from isotherm import dataset, metrics  # noqa: E402
from isotherm.baselines import transformer_suite  # noqa: E402
from isotherm.evaluation import oos_predictions  # noqa: E402
from isotherm.splits import LOCKBOX_START  # noqa: E402

RECENT_FROM = LOCKBOX_START - pd.Timedelta(days=365)
TF, NET = "isotherm · transformer", "isotherm"
CTL = "isotherm · transformer · market-sampled labels (control)"


def main():
    oos = oos_predictions(dataset.load(), transformer_suite())
    res, passing = {}, 0
    for read, o in oos.items():
        y, days = o.rows.y, o.rows.meta["day"]
        recent = (days >= RECENT_FROM).to_numpy()
        ls = {k: metrics.log_score(p, y) for k, p in o.preds.items()}
        diff = ls[NET] - ls[TF]  # positive: transformer better
        ctl = ls["market"] - ls[CTL]
        r = {
            "rows_recent": int(recent.sum()),
            "transformer_minus_isotherm_recent": float(diff[recent].mean()),
            "ci": metrics.date_bootstrap_mean(days.to_numpy()[recent], diff[recent], 2000),
            "transformer_minus_isotherm_all": float(diff.mean()),
            "ci_all": metrics.date_bootstrap_mean(days.to_numpy(), diff, 2000),
            "transformer_vs_market_recent": float((ls["market"] - ls[TF])[recent].mean()),
            "isotherm_vs_market_recent": float((ls["market"] - ls[NET])[recent].mean()),
            "control_vs_market_all": float(ctl.mean()),
        }
        r["pass"] = r["ci"][0] > 0
        passing += r["pass"]
        res[read] = r
        print(
            "{:6s} recent Δ {:+.4f} [{:+.4f}, {:+.4f}]  all {:+.4f}  control {:+.4f}  {}".format(
                read,
                r["transformer_minus_isotherm_recent"],
                *r["ci"],
                r["transformer_minus_isotherm_all"],
                r["control_vs_market_all"],
                "PASS" if r["pass"] else "-",
            )
        )
    controls_ok = all(abs(r["control_vs_market_all"]) <= 0.005 for r in res.values())
    verdict = "PASS" if passing >= 3 and controls_ok else "FAIL"
    out = {
        "gate": "FINDINGS §16",
        "reads_passing": passing,
        "controls_ok": controls_ok,
        "verdict": verdict,
        "results": res,
    }
    pathlib.Path("results/transformer_gate.json").write_text(json.dumps(out, indent=2))
    print("\nreads passing {}/4, controls within ±0.005: {} -> {}".format(passing, controls_ok, verdict))


if __name__ == "__main__":
    main()
