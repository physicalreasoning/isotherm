#!/usr/bin/env python3
"""Sealed forward test of the AIFS pool (FINDINGS §51), as §50 pre-registered on a pass.

    uv run scripts/aifs_forward.py --freeze   # once: fit both pools, write shadow/forward/aifs.json
    uv run scripts/aifs_forward.py            # after the window settles: score, results/aifs_forward.json

Frozen now: the log-pool weights of pool(market, EMOS-GFS, EMOS-AIFS) and of the live strategy's
form, pool(market, EMOS-GFS), both fit on every d1_16 ladder of the seven cities from 2025-06-01
through the freeze, and the sha256 of this file and of scripts/aifs_test.py (which defines the
EMOS-AIFS source: Open-Meteo day-2 values, monthly EMOS refit, 2-day embargo). The source keeps
refitting monthly as defined; the pool weights do not move.

Window: target days 2026-11-01 to 2027-04-05. Primary: pool3 minus pool2, log score per ladder,
PASS if the 95% date-block CI lower bound is above zero. Secondary: pool3 minus the bid-priced market.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import sys

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import aifs_test as A  # noqa: E402

from isotherm import dataset, metrics  # noqa: E402
from isotherm.baselines import LogPool, _logs, pool  # noqa: E402
from isotherm.dataset import _finish  # noqa: E402
from isotherm.weather import CITIES  # noqa: E402

FROZEN = ROOT / "shadow" / "forward" / "aifs.json"
WINDOW = ("2026-11-01", "2027-04-05")
CODE = ["scripts/aifs_test.py", "scripts/aifs_forward.py"]
NAMES = {"pool2": ["market", "emos_gfs"], "pool3": ["market", "emos_gfs", "emos_aifs"]}


def sha(p) -> str:
    return hashlib.sha256((ROOT / p).read_bytes()).hexdigest()


def ladders(refetch: bool = False):
    """d1_16 ladders of the seven cities with EMOS-AIFS attached, as aifs_test builds them."""
    if refetch:  # scoring: the cached archive stops at its fetch date
        for c in CITIES.values():
            (A.DATA / "forecasts" / f"{c.station}_AIFS.parquet").unlink(missing_ok=True)
    ls = dataset.load(list(CITIES))
    ls = ls.take(np.flatnonzero((ls.meta["read"] == A.READ).to_numpy()))
    ls.probs["emos_aifs"] = np.full(ls.mask.shape, np.nan)
    for key, city in CITIES.items():
        A.attach_emos(ls, key, A.aifs_day2(city.station, city.tz), "emos_aifs")
    ls.probs["emos_aifs"] = _finish(ls.probs["emos_aifs"], ls.mask)
    ok = np.isfinite(ls.probs["emos_aifs"]).all(1) & np.isfinite(ls.probs["emos_gfs"]).all(1)
    ok &= np.isfinite(ls.probs["market"]).all(1) & (ls.meta["day"] >= pd.Timestamp(A.TRAIN_FROM)).to_numpy()
    return ls.take(np.flatnonzero(ok))


def freeze():
    if FROZEN.exists():
        raise SystemExit(f"{FROZEN} exists: frozen once")
    ls = ladders()
    w = {k: LogPool(v).fit(ls).weights[A.READ].tolist() for k, v in NAMES.items()}
    rec = {
        "frozen_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "fit_rows": int(len(ls)),
        "fit_through": str(ls.meta["day"].max().date()),
        "window": list(WINDOW),
        "read": A.READ,
        "weights": w,
        "code_sha256": {p: sha(p) for p in CODE},
    }
    FROZEN.write_text(json.dumps(rec, indent=1))
    print(json.dumps(rec, indent=1))


def score():
    fz = json.loads(FROZEN.read_text())
    changed = [p for p, h in fz["code_sha256"].items() if sha(p) != h]
    if changed:
        raise SystemExit(f"changed since the freeze: {changed}")
    ls = ladders(refetch=True)
    d = ls.meta["day"]
    t = np.flatnonzero(((d >= WINDOW[0]) & (d <= WINDOW[1])).to_numpy())
    sub = ls.take(t)
    p = {k: pool(np.array(fz["weights"][k]), _logs(sub, v), sub.mask) for k, v in NAMES.items()}
    loss = {k: metrics.log_score(np.where(sub.mask, v, 0.0), sub.y) for k, v in p.items()}
    loss["bid"] = metrics.log_score(A.bid_market(sub), sub.y)
    days = sub.meta["day"].to_numpy()
    res = {
        "window": list(WINDOW),
        "ladders": len(t),
        "through": str(sub.meta["day"].max().date()) if len(t) else None,
        "complete": bool(len(t) and sub.meta["day"].max() >= pd.Timestamp(WINDOW[1])),
        "primary_pool3_minus_pool2": A.diff(days, loss["pool2"], loss["pool3"]),
        "secondary_pool3_minus_bid_market": A.diff(days, loss["bid"], loss["pool3"]),
    }
    if res["complete"]:
        res["verdict"] = "PASS" if res["primary_pool3_minus_pool2"]["ci"][0] > 0 else "FAIL"
    out = ROOT / "results" / "aifs_forward.json"
    out.write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze", action="store_true")
    freeze() if ap.parse_args().freeze else score()
