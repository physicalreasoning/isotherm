#!/usr/bin/env python3
"""NBM's own spread (XND) in EMOS: score the two gates of FINDINGS §22.

uv run scripts/nbm_spread.py
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
V5 = pd.Timestamp("2026-04-21")
NEW, CTL = "isotherm · NBM spread", "isotherm · NBM spread · market-sampled labels (control)"


def paired(days, a, b, sel):
    d = (a - b)[sel]
    return {
        "diff": float(d.mean()),
        "ci": metrics.date_bootstrap_mean(days[sel], d, 2000),
        "n": int(sel.sum()),
    }


def keyed(rows):
    return (rows.meta["event"] + "|" + rows.meta["read"]).to_numpy()


def main():
    cities = list(CITIES)
    old, new = dataset.load(cities), dataset.load(cities, nbm_spread=True)
    assert (keyed(old) == keyed(new)).all()
    res = {"weather": {}, "adoption": {}}

    # Gate 1: the EMOS forecasts themselves, every ladder in the walk-forward window.
    day = old.meta["day"]
    win = ((day >= "2023-07-01") & (day < LOCKBOX_START)).to_numpy()
    for read in sorted(old.meta["read"].unique()):
        r = {}
        for src in ("emos_nbm", "emos_nbm_obs"):
            a, b = old.probs[src], new.probs[src]
            sel = win & (old.meta["read"] == read).to_numpy() & np.isfinite(a).all(1) & np.isfinite(b).all(1)
            la, lb = (
                metrics.log_score(np.nan_to_num(a, nan=1.0), old.y),
                metrics.log_score(np.nan_to_num(b, nan=1.0), old.y),
            )
            d = day.to_numpy()
            r[src] = paired(d, la, lb, sel)
            r[src + "_post_v5"] = paired(d, la, lb, sel & (day >= V5).to_numpy())
        r["pass"] = r["emos_nbm"]["ci"][0] > 0
        res["weather"][read] = r
    res["weather_reads_passing"] = int(sum(v["pass"] for v in res["weather"].values()))

    # Gate 2: the per-read MLP retrained on the spread inputs, against the cached MLP.
    base = oos_predictions(old, transformer_large_suite())
    suite = [Source("market"), IsothermNet(NEW), IsothermNet(CTL, market_labels=True, seeds=3)]
    alt = oos_predictions(new, suite)
    for read, o in base.items():
        n = alt[read]
        idx = pd.Series(np.arange(len(n.rows)), index=keyed(n.rows))
        k = keyed(o.rows)
        hit = pd.Index(k).isin(idx.index)
        j = idx[k[hit]].to_numpy()
        y, days = o.rows.y[hit], o.rows.meta["day"].to_numpy()[hit]
        recent = days >= np.datetime64(RECENT_FROM)
        lm = metrics.log_score(o.preds["market"][hit], y)
        l0 = metrics.log_score(o.preds["isotherm"][hit], y)
        l1 = metrics.log_score(n.preds[NEW][j], y)
        lc = metrics.log_score(n.preds[CTL][j], y)
        r = paired(days, l0, l1, recent)
        r["control_vs_market_all"] = float((lm - lc).mean())
        r["new_vs_market_recent"] = float((lm - l1)[recent].mean())
        r["old_vs_market_recent"] = float((lm - l0)[recent].mean())
        r["pass"] = r["ci"][0] > 0
        res["adoption"][read] = r
    a = res["adoption"]
    passing = sum(v["pass"] for v in a.values())
    controls = all(abs(v["control_vs_market_all"]) <= 0.005 for v in a.values())
    res["verdict"] = {
        "weather": "PASS" if res["weather_reads_passing"] >= 3 else "FAIL",
        "adoption": "PASS" if passing >= 3 and controls else "FAIL",
        "adoption_reads_passing": int(passing),
        "controls_ok": controls,
    }
    pathlib.Path("results/nbm_spread.json").write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
