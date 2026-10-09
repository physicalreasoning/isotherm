#!/usr/bin/env python3
"""Freeze the rain model for a forward test (recommended pre-registration, not yet adopted).

Fits, on every labelled station-day through 2026-10-07 (capped sample, same as each walk-forward
fold), the logistic PoP model for each read and each label (trace = dry for KXRAIN, trace = wet
for the NYC-only series), and the logistic stack of logit(mid) and logit(model) on every scored
two-sided KXRAIN row. Writes data/rain/frozen_rain.pkl and its sha256 to results/rain/frozen.json.

    uv run scripts/rain/freeze.py
"""

from __future__ import annotations

import hashlib
import json
import pickle

import numpy as np
import pandas as pd
from common import DATA, RESULTS
from evaluate import LAST_LABEL_DAY, MAX_TRAIN, design, fit, logit
from sklearn.linear_model import LogisticRegression


def main():
    feat = pd.read_parquet(DATA / "features.parquet")
    feat = feat[feat[["nbm_any06", "gfs_any06"]].notna().any(axis=1)]
    feat = feat[feat["wet"].notna() & (feat["day"] <= LAST_LABEL_DAY)].copy()
    feat["wett"] = ((feat["wet"] > 0) | feat["trace"]).astype(int)
    rng = np.random.default_rng(0)
    models = {}
    for read, fr in feat.groupby("read"):
        if len(fr) > MAX_TRAIN:
            fr = fr.iloc[np.sort(rng.choice(len(fr), MAX_TRAIN, replace=False))]
        X = design(fr)
        models[(read, "trace_dry")] = fit("logit", X, fr["wet"].to_numpy(int))
        models[(read, "trace_wet")] = fit("logit", X, fr["wett"].to_numpy(int))
    sc = pd.read_parquet(DATA / "scored.parquet")
    stacks = {}
    for read, g in sc[sc["series"] == "KXRAIN"].groupby("read"):
        X = np.column_stack([logit(g["mid"]), logit(g["p_model"])])
        lr = LogisticRegression(C=10.0).fit(X, g["y"].to_numpy(int))
        stacks[read] = lr
    blob = pickle.dumps({"models": models, "stacks": stacks, "fit_through": str(LAST_LABEL_DAY.date())})
    f = DATA / "frozen_rain.pkl"
    f.write_bytes(blob)
    sha = hashlib.sha256(blob).hexdigest()
    out = {
        "file": "data/rain/frozen_rain.pkl",
        "sha256": sha,
        "fit_through": str(LAST_LABEL_DAY.date()),
        "train_rows_per_read": int(min(MAX_TRAIN, feat.groupby("read").size().min())),
        "stack_coefs": {
            r: {
                "intercept": float(m.intercept_[0]),
                "mid": float(m.coef_[0][0]),
                "model": float(m.coef_[0][1]),
            }
            for r, m in stacks.items()
        },
        "stack_rows": {r: int((sc["series"].eq("KXRAIN") & sc["read"].eq(r)).sum()) for r in stacks},
    }
    (RESULTS / "frozen.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
