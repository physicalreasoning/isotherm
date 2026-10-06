#!/usr/bin/env python3
"""Exploration (FINDINGS §30, §33): does momentum, order flow or LAMP add to isotherm?

uv run scripts/explore_dynamics.py
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
from isotherm.flow import FLOW, MOMENTUM, DynamicsNet, add_flow, add_momentum  # noqa: E402
from isotherm.lamp import LAMP, add_lamp  # noqa: E402
from isotherm.splits import LOCKBOX_START  # noqa: E402
from isotherm.weather import CITIES  # noqa: E402

RECENT_FROM = LOCKBOX_START - pd.Timedelta(days=365)
ARMS = {
    "isotherm + momentum": MOMENTUM,
    "isotherm + flow": FLOW,
    "isotherm + momentum + flow": MOMENTUM + FLOW,
}
LAMP_ARMS = {"isotherm + LAMP": LAMP, "isotherm + LAMP + flow": LAMP + FLOW}


def key(rows):
    return (rows.meta["event"] + "|" + rows.meta["read"]).to_numpy()


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--lamp", action="store_true", help="score the LAMP arms (§33) instead")
    args = ap.parse_args()
    arms = LAMP_ARMS if args.lamp else ARMS
    ls = dataset.load(list(CITIES))
    base = oos_predictions(ls, transformer_large_suite())
    add_momentum(ls)
    add_flow(ls)
    if args.lamp:
        add_lamp(ls)
    alt = oos_predictions(ls, [Source("market")] + [DynamicsNet(n, x) for n, x in arms.items()])
    res = {}
    for read, o in base.items():
        a = alt[read]
        idx = pd.Series(np.arange(len(a.rows)), index=key(a.rows))
        k = key(o.rows)
        hit = pd.Index(k).isin(idx.index)
        j = idx[k[hit]].to_numpy()
        y, days = o.rows.y[hit], o.rows.meta["day"].to_numpy()[hit]
        recent = days >= np.datetime64(RECENT_FROM)
        l0 = metrics.log_score(o.preds["isotherm"][hit], y)
        r = {}
        for n in arms:
            d = (l0 - metrics.log_score(a.preds[n][j], y))[recent]
            r[n] = {"vs_mlp": float(d.mean()), "ci": metrics.date_bootstrap_mean(days[recent], d, 2000)}
            print(
                "{} {:28s} vs mlp {:+.4f} [{:+.4f}, {:+.4f}]".format(read, n, r[n]["vs_mlp"], *r[n]["ci"]),
                flush=True,
            )
        res[read] = r
    out = "results/explore_lamp_model.json" if args.lamp else "results/explore_dynamics.json"
    pathlib.Path(out).write_text(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
