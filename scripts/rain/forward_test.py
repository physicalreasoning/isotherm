#!/usr/bin/env python3
"""Score the sealed rain forward test (FINDINGS §44) on KXRAIN days that settled after the freeze.

Frozen: shadow/forward/models_rain.pkl (hash in shadow/forward/frozen_rain.json, checked on load),
the logistic PoP model and the market+model stack fit through 2026-10-07. Nothing is refit.
Refresh the markets first, then score:

    uv run scripts/rain/fetch_markets.py
    uv run scripts/rain/forward_test.py
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import pathlib
import pickle
import sys

import numpy as np
import pandas as pd
from common import DATA, RESULTS, mos_precip, station_features, station_tz
from evaluate import design, gain, logit

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))

ROOT = pathlib.Path(__file__).resolve().parents[2]
FROZEN = ROOT / "shadow" / "forward"
START, FINAL = pd.Timestamp("2026-10-11"), pd.Timestamp("2027-04-05")
READ = "d1_16"


def frozen():
    meta = json.loads((FROZEN / "frozen_rain.json").read_text())
    blob = (FROZEN / "models_rain.pkl").read_bytes()
    assert hashlib.sha256(blob).hexdigest() == meta["sha256"], "frozen rain model changed"
    return pickle.loads(blob)


def main():
    fz = frozen()
    mk = pd.read_parquet(DATA / "markets.parquet")
    m = mk[(mk["series"] == "KXRAIN") & (mk["read"] == READ) & (mk["threshold"] == 0)]
    m = m[(m["day"] >= START) & (m["day"] <= FINAL) & m["y"].notna() & m["station"].notna()]
    m = m[~m["closed_before_read"].astype(bool) & (m["bid"].fillna(0) > 0) & (m["ask"].fillna(1) < 1)].copy()
    if m.empty:
        print("no settled two-sided KXRAIN markets from", START.date())
        return
    today = str(dt.date.today() + dt.timedelta(days=1))
    parts = []
    for st, g in m.groupby("station"):
        for model in ("NBS", "GFS"):
            mos_precip(st, model, live_end=today)  # refresh runs through the window
        f = station_features(st, station_tz(st), g["day"].drop_duplicates())
        parts.append(f[f["read"] == READ].rename(columns={"target": "day"}).assign(station=st))
    feat = pd.concat(parts, ignore_index=True)
    d = m.merge(feat, on=["station", "day"], how="left")
    d = d[d[["nbm_any06", "gfs_any06"]].notna().any(axis=1)].copy()
    d["p_model"] = fz["models"][(READ, "trace_dry")].predict_proba(design(d))[:, 1]
    d["mid"] = (d["bid"] + d["ask"]) / 2
    X = np.column_stack([logit(d["mid"]), logit(d["p_model"])])
    d["p_stack"] = fz["stacks"][READ].predict_proba(X)[:, 1]
    d["p_clip"] = np.clip(d["p_model"], d["bid"], d["ask"])
    res = {
        "through": str(d["day"].max().date()),
        "complete": bool(d["day"].max() >= FINAL),
        "markets": int(len(d)),
        "days": int(d["day"].nunique()),
        "primary_stack_minus_mid": gain(d, "mid", "p_stack"),
        "secondary_model_minus_clipped": gain(d, "p_clip", "p_model"),
        "model_minus_mid": gain(d, "mid", "p_model"),
        "by_month": {str(k): gain(g, "mid", "p_stack") for k, g in d.groupby(d["day"].dt.to_period("M"))},
    }
    if res["complete"]:
        p, s = res["primary_stack_minus_mid"], res["secondary_model_minus_clipped"]
        res["verdict"] = "PASS" if p.get("ci", [0])[0] > 0 else "FAIL"
        res["secondary_verdict"] = "PASS" if s.get("ci", [0])[0] > 0 else "FAIL"
    (RESULTS / "forward_test.json").write_text(json.dumps(res, indent=2, default=str))
    print(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
