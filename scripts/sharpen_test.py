#!/usr/bin/env python3
"""Score the sealed sharpening test (FINDINGS §40, corrected in §41) on ladders settled after the freeze.

The market's own bucket probabilities raised to a frozen exponent per read and renormalised
(shadow/forward/sharpen.json, hash checked), against the raw market, on every ladder of the 19
cities from 2026-10-10 to 2027-04-05. Refresh the panels first (as for forward_test.py).

    uv run scripts/sharpen_test.py
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
from isotherm.weather import ALL_CITIES, CITIES  # noqa: E402

FROZEN = pathlib.Path("shadow/forward/sharpen.json")


def frozen():
    f = json.loads(FROZEN.read_text())
    body = {k: v for k, v in f.items() if k != "sha256"}
    assert hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest() == f["sha256"], (
        "frozen changed"
    )
    return f


BID_FLOOR = 0.005  # §41: the bid-priced market floors bids at half a cent, then renormalises


def bid_market(bid, mask):
    q = np.where(mask, np.clip(bid, BID_FLOOR, 1), 0.0)
    return q / q.sum(1, keepdims=True)


def sharpen(p, mask, a):
    q = np.where(mask, np.power(np.clip(p, 1e-6, 1), a), 0.0)
    return q / q.sum(1, keepdims=True)


def main():
    f = frozen()
    start, final = (pd.Timestamp(x) for x in f["window"])
    ls = dataset.load([k for k in ALL_CITIES if (dataset.DATA / "panel" / "{}.parquet".format(k)).exists()])
    d = ls.meta["day"]
    ls = ls.take(np.flatnonzero(((d >= start) & (d <= final)).to_numpy())).complete(["market"])
    if not len(ls):
        print("no settled ladders from", start.date())
        return
    res = {
        "through": str(ls.meta["day"].max().date()),
        "complete": bool(ls.meta["day"].max() >= final),
        "reads": {},
    }
    for read, a in f["exponent"].items():
        s = ls.take(np.flatnonzero((ls.meta["read"] == read).to_numpy()))
        if not len(s):
            continue
        days = s.meta["day"].to_numpy()
        diff = metrics.log_score(s.probs["market"], s.y) - metrics.log_score(
            sharpen(s.probs["market"], s.mask, a), s.y
        )
        # §41 primary: against the market priced at its bids (dead quotes carry no mass).
        db = metrics.log_score(bid_market(s.quotes["bid"], s.mask), s.y) - metrics.log_score(
            sharpen(s.probs["market"], s.mask, a), s.y
        )
        r = {
            "ladders": len(s),
            "vs_bid": {"diff": float(db.mean()), "ci": metrics.date_bootstrap_mean(days, db, 2000)},
            "diff": float(diff.mean()),
            "ci": metrics.date_bootstrap_mean(days, diff, 2000),
        }
        seven = s.meta["city"].isin(list(CITIES)).to_numpy()
        r["seven_cities"] = float(diff[seven].mean()) if seven.any() else None
        r["twelve_cities"] = float(diff[~seven].mean()) if (~seven).any() else None
        res["reads"][read] = r
    # Descriptive: the sharpened market against the frozen MLP of §25, 16:00 day before, seven cities.
    blob = pathlib.Path("shadow/forward/models.pkl").read_bytes()
    meta = json.loads(pathlib.Path("shadow/forward/frozen.json").read_text())
    assert hashlib.sha256(blob).hexdigest() == meta["sha256"], "frozen models changed"
    s = ls.take(
        np.flatnonzero(((ls.meta["read"] == "d1_16") & ls.meta["city"].isin(list(CITIES))).to_numpy())
    )
    s = s.complete(["emos_gfs", "emos_nbm", "emos_nbm_obs", "climatology"])
    if len(s):
        mlp = pickle.loads(blob)["isotherm"]
        lq = metrics.log_score(sharpen(s.probs["market"], s.mask, f["exponent"]["d1_16"]), s.y)
        d2 = lq - metrics.log_score(mlp.predict(s), s.y)
        res["mlp_minus_sharpened_d1_16"] = {
            "diff": float(d2.mean()),
            "ci": metrics.date_bootstrap_mean(s.meta["day"].to_numpy(), d2, 2000),
        }
    if res["complete"]:
        rr = res["reads"]
        res["verdict"] = "PASS" if rr.get("d1_16", {}).get("vs_bid", {}).get("ci", [0])[0] > 0 else "FAIL"
        res["reads_passing"] = int(sum(r["vs_bid"]["ci"][0] > 0 for r in rr.values()))
        res["verdict_original_s40"] = "PASS" if rr.get("d1_16", {}).get("ci", [0])[0] > 0 else "FAIL"
    pathlib.Path("results/sharpen_test.json").write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
