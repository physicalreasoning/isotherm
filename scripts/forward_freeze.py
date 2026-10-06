#!/usr/bin/env python3
"""Freeze the forward test (FINDINGS §25): the per-read MLP and transformer-L at 16:00 day before.

Both are fit on every settled ladder of the seven scored cities up to the freeze, then pickled
with their feature normalisation into shadow/forward/models.pkl, whose hash goes in FINDINGS.
`--spread` freezes the secondary arm instead: the MLP on NBM-spread inputs (§22), into
shadow/forward/models_spread.pkl.

    uv run scripts/forward_freeze.py && uv run scripts/forward_freeze.py --spread
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import pickle
import sys

import numpy as np
import torch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from isotherm import dataset  # noqa: E402
from isotherm.model import IsothermNet, IsothermTransformer  # noqa: E402
from isotherm.weather import CITIES  # noqa: E402

READ = "d1_16"
OUT = pathlib.Path("shadow/forward")


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--spread", action="store_true")
    ap.add_argument("--flow", action="store_true", help="the order-flow MLP (§31)")
    a = ap.parse_args()
    ls = dataset.load(list(CITIES), nbm_spread=a.spread)
    if a.flow:
        from isotherm.flow import FLOW, DynamicsNet, add_flow

        add_flow(ls)
    ls = ls.take(np.flatnonzero((ls.meta["read"] == READ).to_numpy()))
    ls = ls.complete(["market", "emos_gfs", "emos_nbm", "emos_nbm_obs", "climatology"])
    if a.flow:
        models = {"isotherm-flow": DynamicsNet("isotherm + flow", FLOW)}
    elif a.spread:
        models = {"isotherm-spread": IsothermNet("isotherm · NBM spread")}
    else:
        models = {
            "isotherm": IsothermNet("isotherm"),
            "transformer-L": IsothermTransformer("isotherm · transformer-L", d=128, layers=4, ff=256),
        }
    tag = "_flow" if a.flow else "_spread" if a.spread else ""
    for name, m in models.items():
        m.fit(ls)
        print(name, "fit on", len(ls), "ladders", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    blob = pickle.dumps(models)
    (OUT / "models{}.pkl".format(tag)).write_bytes(blob)
    meta = {
        "read": READ,
        "cities": list(CITIES),
        "fit_through": str(ls.meta["day"].max().date()),
        "ladders": len(ls),
        "torch": torch.__version__,
        "sha256": hashlib.sha256(blob).hexdigest(),
    }
    (OUT / "frozen{}.json".format(tag)).write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps(meta, indent=1))


if __name__ == "__main__":
    main()
