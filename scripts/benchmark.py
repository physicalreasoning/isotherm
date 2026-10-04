#!/usr/bin/env python3
"""The benchmark: every predictor, identical rows, walk-forward, date-clustered inference.

For each read time, every predictor in the suite is fit on rows before each
quarterly fold and scored on the fold. Predictions are concatenated across
folds and scored once, so the leaderboard covers every out-of-sample row.

Reported per predictor:
  log score (primary, nats), RPS, Brier, debiased ECE on the Noul view,
  Δ log score vs market with a date-block bootstrap CI, Diebold-Mariano vs market.

It also renders the Gate 0 verdict (docs/PLAN.md §3): does pooling the market
with a free forecast beat the market, CI excluding zero?

    uv run scripts/benchmark.py                 # pre-lockbox walk-forward
    uv run scripts/benchmark.py --lockbox       # ONCE, at the end, frozen config
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from pmdecide import dataset, metrics  # noqa: E402
from pmdecide.baselines import default_suite  # noqa: E402
from pmdecide.splits import walk_forward  # noqa: E402

GATE0 = {"pool · market+NBM": "NBM", "pool · market+GFS": "GFS MOS"}


def score_block(name, p, ls, ref=None, boot=1000):
    ls_ = metrics.log_score(p, ls.y)
    pr, out = metrics.binary_pairs(p, ls.y, ls.mask)
    days = ls.meta["day"].to_numpy()
    r = {"model": name, "n": int(len(ls)), "dates": int(pd.Series(days).nunique()),
         "log_score": float(ls_.mean()), "log_score_ci": metrics.date_bootstrap_mean(days, ls_, boot),
         "rps": float(metrics.rps(p, ls.y, ls.mask).mean()),
         "brier": float(metrics.brier(p, ls.y).mean()),
         "ece_debiased": metrics.ece_debiased(pr, out),
         "top1_acc": float((p.argmax(1) == ls.y).mean())}
    if ref is not None:
        d = ref - ls_
        r["gain_vs_market"] = float(d.mean())
        r["gain_vs_market_ci"] = metrics.date_bootstrap_mean(days, d, boot)
        r["dm_vs_market"] = metrics.diebold_mariano(days, ls_, ref)
    return r, ls_


def run(ls, suite, lockbox, boot):
    out, per_city, reliab = {}, {}, {}
    for read in sorted(ls.meta["read"].unique()):
        sub = ls.take(np.flatnonzero(ls.meta["read"].to_numpy() == read))
        preds = {m.name: np.full(sub.mask.shape, np.nan) for m in suite}
        folds = []
        for f in walk_forward(sub.meta["day"], lockbox=lockbox):
            tr, te = sub.take(f.train), sub.take(f.test)
            folds.append({"fold": f.name, "train": len(f.train), "test": len(f.test)})
            for m in suite:
                preds[m.name][f.test] = m.fit(tr).predict(te)
        scored = np.isfinite(preds["market"]).all(1)
        for m in suite:
            scored &= np.isfinite(preds[m.name]).all(1)
        ev = sub.take(np.flatnonzero(scored))
        P = {k: v[scored] for k, v in preds.items()}
        ref = metrics.log_score(P["market"], ev.y)
        rows, losses = [], {}
        for m in suite:
            r, losses[m.name] = score_block(m.name, P[m.name], ev,
                                            None if m.name == "market" else ref, boot)
            rows.append(r)
        out[read] = {"folds": folds, "rows": len(ev),
                     "from": str(ev.meta["day"].min().date()), "to": str(ev.meta["day"].max().date()),
                     "leaderboard": sorted(rows, key=lambda r: r["log_score"])}
        best = min(rows, key=lambda r: r["log_score"])["model"]
        pc = {}
        for c in sorted(ev.meta["city"].unique()):
            s = (ev.meta["city"] == c).to_numpy()
            d = (ref - losses[best])[s]
            pc[c] = {"n": int(s.sum()), "gain": float(d.mean()),
                     "ci": metrics.date_bootstrap_mean(ev.meta["day"].to_numpy()[s], d, boot)}
        for g in ("regime",):
            for v in sorted(ev.meta[g].unique()):
                s = (ev.meta[g] == v).to_numpy()
                d = (ref - losses[best])[s]
                pc["{}={}".format(g, v)] = {"n": int(s.sum()), "gain": float(d.mean()), "ci":
                                            metrics.date_bootstrap_mean(ev.meta["day"].to_numpy()[s],
                                                                        d, boot)}
        per_city[read] = {"model": best, "slices": pc}
        reliab[read] = {k: metrics.reliability(*metrics.binary_pairs(P[k], ev.y, ev.mask))
                        for k in ("market", best)}
    return out, per_city, reliab


def gate0(results):
    verdict = {}
    for read, r in results.items():
        for row in r["leaderboard"]:
            if row["model"] in GATE0:
                lo, hi = row["gain_vs_market_ci"]
                verdict.setdefault(read, {})[GATE0[row["model"]]] = {
                    "gain": row["gain_vs_market"], "ci": [lo, hi], "pass": lo > 0,
                    "dm_p": row["dm_vs_market"]["p"]}
    passed = any(v["pass"] for r in verdict.values() for v in r.values())
    return {"by_read": verdict, "pass": passed}


def markdown(res):
    L = ["# Benchmark", "",
         "Walk-forward by quarter, 2-day embargo, identical rows for every model, lockbox "
         "{}.".format("**scored**" if res["config"]["lockbox"] else "excluded"),
         "Log score in nats per ladder (lower is better). Δ = market − model: positive means the "
         "model beats the market. CIs resample whole dates.", ""]
    g = res["gate0"]
    L += ["## Gate 0: {}".format("**PASS**" if g["pass"] else "**not passed**"), ""]
    L += ["| Read | Forecast | Δ log score vs market | 95% CI | DM p |", "|---|---|---:|---|---:|"]
    for read, v in g["by_read"].items():
        for fc, x in v.items():
            L.append("| {} | {} | {:+.4f} | [{:+.4f}, {:+.4f}] | {:.3g} |".format(
                read, fc, x["gain"], *x["ci"], x["dm_p"]))
    for read, r in res["results"].items():
        L += ["", "## {}  ·  {} ladders, {} to {}".format(read, r["rows"], r["from"], r["to"]), "",
              "| Model | Log score | 95% CI | RPS | Brier | ECE (debiased) | Top-1 | Δ vs market | Δ CI |",
              "|---|---:|---|---:|---:|---:|---:|---:|---|"]
        for x in r["leaderboard"]:
            d = x.get("gain_vs_market")
            fmt = "| {} | {:.4f} | [{:.4f}, {:.4f}] | {:.4f} | {:.4f} | {:.4f} | {:.3f} | {} | {} |"
            L.append(fmt.format(
                x["model"], x["log_score"], *x["log_score_ci"], x["rps"], x["brier"],
                x["ece_debiased"], x["top1_acc"], "" if d is None else "{:+.4f}".format(d),
                "" if d is None else "[{:+.4f}, {:+.4f}]".format(*x["gain_vs_market_ci"])))
        s = res["slices"][read]
        L += ["", "Best model ({}) vs market, by slice:".format(s["model"]), "",
              "| Slice | n | Δ | 95% CI |", "|---|---:|---:|---|"]
        for k, v in s["slices"].items():
            L.append("| {} | {} | {:+.4f} | [{:+.4f}, {:+.4f}] |".format(k, v["n"], v["gain"], *v["ci"]))
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cities", nargs="*")
    ap.add_argument("--lockbox", action="store_true")
    ap.add_argument("--boot", type=int, default=1000)
    ap.add_argument("--out", default="results/benchmark")
    a = ap.parse_args()
    t0 = time.time()
    ls = dataset.load(a.cities)
    print("loaded {} ladders, cities {}".format(len(ls), sorted(ls.meta["city"].unique())), flush=True)
    results, slices, reliab = run(ls, default_suite(), a.lockbox, a.boot)
    try:
        sha = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                      stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        sha = None
    res = {"config": vars(a), "git": sha, "cities": sorted(ls.meta["city"].unique()),
           "results": results, "slices": slices, "reliability": reliab,
           "seconds": round(time.time() - t0, 1)}
    res["gate0"] = gate0(results)
    p = pathlib.Path(a.out + ("_lockbox" if a.lockbox else ""))
    p.parent.mkdir(exist_ok=True)
    p.with_suffix(".json").write_text(json.dumps(res, indent=2, default=str))
    p.with_suffix(".md").write_text(markdown(res))
    print(markdown(res))
    print("wrote {}.json / .md in {:.0f}s".format(p, time.time() - t0))


if __name__ == "__main__":
    main()
