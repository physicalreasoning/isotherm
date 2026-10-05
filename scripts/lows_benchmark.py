#!/usr/bin/env python3
"""Gate 0 and baseline leaderboard for daily-low ladders.

Same scoring as scripts/benchmark.py (identical rows, log score vs market, date-block
CIs, Diebold-Mariano), on the lows calendar: monthly walk-forward folds from 2026-02,
lockbox from 2026-09-01 left sealed. The series only start on 2025-12-14, so the
"last 12 months" slice of the amended gate is the whole scored period.

    uv run scripts/lows_benchmark.py
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import time

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from isotherm import lows, metrics  # noqa: E402
from isotherm.baselines import LogPool, Source, TemperedMarket  # noqa: E402

spec = importlib.util.spec_from_file_location("bench", ROOT / "scripts" / "benchmark.py")
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)

RECENT_FROM = lows.LOCKBOX_START - pd.Timedelta(days=365)


def suite():
    return [
        Source("climatology"),
        Source("emos_gfs", "EMOS · GFS MOS"),
        Source("emos_nbm", "EMOS · NBM"),
        Source("market"),
        TemperedMarket(),
        LogPool(["market", "emos_gfs"], "pool · market+GFS"),
        LogPool(["market", "emos_nbm"], "pool · market+NBM"),
        LogPool(["market", "emos_nbm", "emos_gfs", "climatology"], "pool · all"),
        LogPool(["market", "emos_gfs", "emos_nbm"], "pool · market+GFS+NBM · 365d", window_days=365),
    ]


def run(ls, boot):
    out, slices, reliab = {}, {}, {}
    st = suite()
    for read, o in lows.oos_predictions(ls, st).items():
        ev, P = o.rows, o.preds
        ref = metrics.log_score(P["market"], ev.y)
        rows, losses = [], {}
        for m in st:
            r, losses[m.name] = bench.score_block(
                m.name, P[m.name], ev, None if m.name == "market" else ref, boot
            )
            rows.append(r)
        out[read] = {
            "folds": o.folds,
            "rows": len(ev),
            "from": str(ev.meta["day"].min().date()),
            "to": str(ev.meta["day"].max().date()),
            "leaderboard": sorted(rows, key=lambda r: r["log_score"]),
        }
        best = min(rows, key=lambda r: r["log_score"])["model"]
        days = ev.meta["day"].to_numpy()
        pc = {}
        for col in ("city", "regime", "period"):
            for v in sorted(ev.meta[col].unique()):
                s = (ev.meta[col] == v).to_numpy()
                d = (ref - losses[best])[s]
                label = v if col == "city" else "{}={}".format(col, v)
                pc[label] = {
                    "n": int(s.sum()),
                    "gain": float(d.mean()),
                    "ci": metrics.date_bootstrap_mean(days[s], d, boot),
                }
        slices[read] = {"model": best, "slices": pc}
        recent = (ev.meta["day"] >= RECENT_FROM).to_numpy()
        rec = {}
        for name in list(bench.GATE0) + [best]:
            d = ref - losses[name]
            row = {
                "n": int(recent.sum()),
                "gain": float(d[recent].mean()),
                "ci": metrics.date_bootstrap_mean(days[recent], d[recent], boot),
                "by_city": {},
            }
            for c in sorted(ev.meta["city"].unique()):
                s = recent & (ev.meta["city"] == c).to_numpy()
                row["by_city"][c] = {
                    "n": int(s.sum()),
                    "gain": float(d[s].mean()),
                    "ci": metrics.date_bootstrap_mean(days[s], d[s], boot),
                }
            rec[name] = row
        out[read]["recent"] = rec
        reliab[read] = {
            k: metrics.reliability(*metrics.binary_pairs(P[k], ev.y, ev.mask)) for k in ("market", best)
        }
    return out, slices, reliab


def main():
    t0 = time.time()
    ls = lows.load()
    print("loaded {} low ladders, cities {}".format(len(ls), sorted(ls.meta["city"].unique())), flush=True)
    results, slices, reliab = run(ls, 1000)
    res = {
        "config": {"lockbox": False, "folds": "monthly from {}".format(lows.FOLD_START)},
        "cities": sorted(ls.meta["city"].unique()),
        "results": results,
        "slices": slices,
        "reliability": reliab,
        "seconds": round(time.time() - t0, 1),
    }
    res["gate0"] = bench.gate0(results)
    res["gate0"]["recent_from"] = str(RECENT_FROM.date())
    md = bench.markdown(res).replace(
        "Walk-forward by quarter, 2-day embargo",
        "Daily lows. Walk-forward by month from {}, 2-day embargo, lockbox from {} sealed".format(
            lows.FOLD_START, lows.LOCKBOX_START.date()
        ),
    )
    p = ROOT / "results" / "lows_benchmark"
    p.with_suffix(".json").write_text(json.dumps(res, indent=2, default=str))
    p.with_suffix(".md").write_text(md)
    print(md)
    n = np.mean([r["rows"] for r in results.values()])
    print("wrote results/lows_benchmark.json/.md, {:.0f} ladders per read".format(n))


if __name__ == "__main__":
    main()
