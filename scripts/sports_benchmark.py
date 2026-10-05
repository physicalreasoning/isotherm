#!/usr/bin/env python3
"""MLB benchmark and Gate 0: does free baseball data add information the market lacks?

Same protocol as the weather benchmark (docs/EVALS.md): identical rows, walk-forward,
date-block CIs, Diebold-Mariano, tempered-market control. MLB calendar:
monthly folds from 2025-07, at least 45 training dates, lockbox from 2026-09-01
(the last weeks of the 2026 regular season and the postseason), scored only with
--lockbox. "Recent" = the 12 months before the lockbox.

    uv run scripts/sports_benchmark.py
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from pmdecide import metrics  # noqa: E402
from pmdecide.baselines import LogPool, Source, TemperedMarket  # noqa: E402
from pmdecide.sports.dataset import build  # noqa: E402
from pmdecide.sports.oos import oos_predictions  # noqa: E402

SPLITS = {"start": "2025-07-01", "freq": "MS", "min_train_days": 45,
          "lockbox_start": pd.Timestamp("2026-09-01")}
RECENT_FROM = SPLITS["lockbox_start"] - pd.Timedelta(days=365)
GATE0 = {"pool · market+Elo": "Elo", "pool · market+Elo+SP": "Elo + starters"}


def suite():
    return [Source("elo", "Elo"), Source("elo_sp", "Elo + starters"), Source("market"),
            TemperedMarket(),
            LogPool(["market", "elo"], "pool · market+Elo"),
            LogPool(["market", "elo_sp"], "pool · market+Elo+SP"),
            LogPool(["market", "elo", "elo_sp"], "pool · all")]


def gain_block(days, d, boot):
    return {"n": int(len(d)), "gain": float(d.mean()) if len(d) else float("nan"),
            "ci": metrics.date_bootstrap_mean(days, d, boot) if len(d) > 1 else [np.nan, np.nan]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lockbox", action="store_true")
    ap.add_argument("--boot", type=int, default=1000)
    ap.add_argument("--out", default="results/sports_benchmark")
    a = ap.parse_args()
    ls = build()
    print("ladders {} | games {} | Kalshi result = MLB result on {:.4f} of rows".format(
        len(ls), ls.meta["game_pk"].nunique(), ls.meta["label_agrees_mlb"].mean()), flush=True)
    res = {"config": vars(a), "splits": {k: str(v) for k, v in SPLITS.items()},
           "label_agreement": float(ls.meta["label_agrees_mlb"].mean()), "reads": {}}
    gate, amended = {}, {}
    for read, o in oos_predictions(ls, suite(), a.lockbox, **SPLITS).items():
        ev, P = o.rows, o.preds
        days = ev.meta["day"].to_numpy()
        ref = metrics.log_score(P["market"], ev.y)
        board = []
        for name, p in P.items():
            lsc = metrics.log_score(p, ev.y)
            pr, out = metrics.binary_pairs(p, ev.y, ev.mask)
            row = {"model": name, "log_score": float(lsc.mean()),
                   "log_score_ci": metrics.date_bootstrap_mean(days, lsc, a.boot),
                   "brier": float(metrics.brier(p, ev.y).mean()),
                   "ece_debiased": metrics.ece_debiased(pr, out)}
            if name != "market":
                d = ref - lsc
                row["gain_vs_market"] = float(d.mean())
                row["gain_ci"] = metrics.date_bootstrap_mean(days, d, a.boot)
                row["dm_p"] = metrics.diebold_mariano(days, lsc, ref)["p"]
                recent = ev.meta["day"].to_numpy() >= np.datetime64(RECENT_FROM)
                row["recent"] = gain_block(days[recent], d[recent], a.boot)
                row["by_period"] = {k: gain_block(days[(ev.meta["period"] == k).to_numpy()],
                                                  d[(ev.meta["period"] == k).to_numpy()], a.boot)
                                    for k in sorted(ev.meta["period"].unique())}
            board.append(row)
        board.sort(key=lambda r: r["log_score"])
        res["reads"][read] = {"rows": len(ev), "games": int(ev.meta["game_pk"].nunique()),
                              "from": str(ev.meta["day"].min().date()),
                              "to": str(ev.meta["day"].max().date()), "folds": o.folds,
                              "median_spread": float(ev.meta["spread"].median()),
                              "leaderboard": board}
        for r in board:
            if r["model"] in GATE0:
                gate.setdefault(read, {})[GATE0[r["model"]]] = {
                    "gain": r["gain_vs_market"], "ci": r["gain_ci"], "pass": r["gain_ci"][0] > 0,
                    "dm_p": r["dm_p"]}
                amended.setdefault(read, {})[GATE0[r["model"]]] = dict(
                    r["recent"], **{"pass": r["recent"]["ci"][0] > 0})
        print("\n[{}] {} ladders {}..{}  median spread {:.3f}".format(
            read, len(ev), res["reads"][read]["from"], res["reads"][read]["to"],
            res["reads"][read]["median_spread"]))
        for r in board:
            g = r.get("gain_vs_market")
            print("  {:<24} {:.4f}  {}".format(r["model"], r["log_score"], "" if g is None else
                  "Δ {:+.4f} [{:+.4f}, {:+.4f}]  recent {:+.4f} [{:+.4f}, {:+.4f}]".format(
                      g, *r["gain_ci"], r["recent"]["gain"], *r["recent"]["ci"])))
    res["gate0"] = {"by_read": gate, "pass": any(v["pass"] for r in gate.values() for v in r.values()),
                    "amended_by_read": amended, "recent_from": str(RECENT_FROM.date()),
                    "amended_pass": any(v["pass"] for r in amended.values() for v in r.values())}
    print("\nGate 0 as registered: {}   amended (last 12 months): {}".format(
        "PASS" if res["gate0"]["pass"] else "not passed",
        "PASS" if res["gate0"]["amended_pass"] else "FAIL"))
    p = pathlib.Path(a.out + ("_lockbox" if a.lockbox else "") + ".json")
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps(res, indent=2, default=str))
    print("wrote", p)


if __name__ == "__main__":
    main()
