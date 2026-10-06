#!/usr/bin/env python3
"""Exploration (FINDINGS §28): equal-weight ensembles of cached walk-forward predictions.

No weights are fit, so nothing is selected; any winner still has to pass the forward test.

    uv run scripts/explore_ensemble.py
"""

from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from isotherm import dataset, metrics  # noqa: E402
from isotherm.baselines import Source, transformer_large_suite  # noqa: E402
from isotherm.evaluation import oos_predictions  # noqa: E402
from isotherm.model import IsothermNet  # noqa: E402
from isotherm.splits import LOCKBOX_START  # noqa: E402
from isotherm.weather import CITIES  # noqa: E402

RECENT_FROM = LOCKBOX_START - pd.Timedelta(days=365)
SPREAD = "isotherm · NBM spread"


def key(rows):
    return (rows.meta["event"] + "|" + rows.meta["read"]).to_numpy()


def geo(ps, mask):
    lp = np.mean([np.log(np.clip(p, 1e-6, 1)) for p in ps], 0)
    q = np.where(mask, np.exp(lp), 0.0)
    return q / q.sum(1, keepdims=True)


def main():
    cities = list(CITIES)
    old, new = dataset.load(cities), dataset.load(cities, nbm_spread=True)
    base = oos_predictions(old, transformer_large_suite())
    ctl = "isotherm · NBM spread · market-sampled labels (control)"
    alt = oos_predictions(
        new, [Source("market"), IsothermNet(SPREAD), IsothermNet(ctl, market_labels=True, seeds=3)]
    )
    res = {}
    for read, o in base.items():
        a = alt[read]
        idx = pd.Series(np.arange(len(a.rows)), index=key(a.rows))
        k = key(o.rows)
        hit = pd.Index(k).isin(idx.index)
        j = idx[k[hit]].to_numpy()
        y, days, mask = o.rows.y[hit], o.rows.meta["day"].to_numpy()[hit], o.rows.mask[hit]
        P = {
            "market": o.preds["market"][hit],
            "mlp": o.preds["isotherm"][hit],
            "tf": o.preds["isotherm · transformer-L"][hit],
            "spread": a.preds[SPREAD][j],
        }
        P["mean(mlp,tf)"] = (P["mlp"] + P["tf"]) / 2
        P["geo(mlp,tf)"] = geo([P["mlp"], P["tf"]], mask)
        P["mean(mlp,tf,spread)"] = (P["mlp"] + P["tf"] + P["spread"]) / 3
        P["geo(mlp,tf,spread)"] = geo([P["mlp"], P["tf"], P["spread"]], mask)
        P["mean(tf,spread)"] = (P["tf"] + P["spread"]) / 2
        recent = days >= np.datetime64(RECENT_FROM)
        L = {n: metrics.log_score(p, y) for n, p in P.items()}
        r = {}
        for n in P:
            if n in ("market", "mlp"):
                continue
            d = (L["mlp"] - L[n])[recent]
            r[n] = {"vs_mlp": float(d.mean()), "ci": metrics.date_bootstrap_mean(days[recent], d, 2000)}
        r["mlp_vs_market"] = float((L["market"] - L["mlp"])[recent].mean())
        res[read] = r
        print(read, "mlp vs market {:+.4f}".format(r["mlp_vs_market"]))
        for n, v in r.items():
            if isinstance(v, dict):
                print("   {:22s} vs mlp {:+.4f} [{:+.4f}, {:+.4f}]".format(n, v["vs_mlp"], *v["ci"]))
    pathlib.Path("results/explore_ensemble.json").write_text(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
