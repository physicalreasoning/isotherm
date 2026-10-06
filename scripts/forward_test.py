#!/usr/bin/env python3
"""Score the sealed forward test (FINDINGS §25) on ladders that settled after the freeze.

Refresh the panels first so the newest days exist, then score:

    uv run scripts/build_weather_panel.py && uv run scripts/forward_test.py
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import pickle
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from isotherm import dataset, metrics  # noqa: E402
from isotherm.weather import CITIES  # noqa: E402

DIR = pathlib.Path("shadow/forward")
START = pd.Timestamp("2026-10-07")  # first target day whose ladder opened after the freeze
FINAL = pd.Timestamp("2027-04-05")  # last day of the primary window


def frozen(tag):
    meta = json.loads((DIR / "frozen{}.json".format(tag)).read_text())
    blob = (DIR / "models{}.pkl".format(tag)).read_bytes()
    assert hashlib.sha256(blob).hexdigest() == meta["sha256"], "frozen models changed"
    return meta, pickle.loads(blob)


def window(ls, read):
    d = ls.meta["day"]
    ls = ls.take(np.flatnonzero(((ls.meta["read"] == read) & (d >= START) & (d <= FINAL)).to_numpy()))
    return ls.complete(["market", "emos_gfs", "emos_nbm", "emos_nbm_obs", "climatology"])


def main():
    meta, models = frozen("")
    _, spread = frozen("_spread")
    ls = window(dataset.load(list(CITIES)), meta["read"])
    if not len(ls):
        print("no settled ladders after", START.date())
        return
    lss = window(dataset.load(list(CITIES), nbm_spread=True), meta["read"])
    assert (ls.meta["event"].to_numpy() == lss.meta["event"].to_numpy()).all()
    days = ls.meta["day"].to_numpy()
    lm = metrics.log_score(ls.probs["market"], ls.y)
    L = {k: metrics.log_score(m.predict(ls), ls.y) for k, m in models.items()}
    L.update({k: metrics.log_score(m.predict(lss), lss.y) for k, m in spread.items()})
    diff = L["isotherm"] - L["transformer-L"]
    d2 = L["isotherm"] - L["isotherm-spread"]
    res = {
        "through": str(ls.meta["day"].max().date()),
        "ladders": len(ls),
        "days": int(pd.Series(days).nunique()),
        "complete": bool(ls.meta["day"].max() >= FINAL),
        "transformer_minus_isotherm": {
            "diff": float(diff.mean()),
            "ci": metrics.date_bootstrap_mean(days, diff, 2000),
        },
        "spread_minus_isotherm": {
            "diff": float(d2.mean()),
            "ci": metrics.date_bootstrap_mean(days, d2, 2000),
        },
        "vs_market": {
            k: {"gain": float((lm - v).mean()), "ci": metrics.date_bootstrap_mean(days, lm - v, 2000)}
            for k, v in L.items()
        },
    }
    if res["complete"]:
        res["verdict"] = "PASS" if res["transformer_minus_isotherm"]["ci"][0] > 0 else "FAIL"
        res["secondary_verdict"] = "PASS" if res["spread_minus_isotherm"]["ci"][0] > 0 else "FAIL"
    pathlib.Path("results/forward_test.json").write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
