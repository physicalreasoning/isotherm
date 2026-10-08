#!/usr/bin/env python3
"""Candidate frozen parameters for the proposed pre-registration (REPORT.md): one sharpening
exponent per read, p_i proportional to p_mkt_i ** a, fit on every seven-city ladder through
2026-10-04. Written to results/alpha/prereg_params.json; nothing here is scored."""

from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd
from common import CITIES, OUT, READS
from scipy.optimize import minimize
from weather_signals import nll, prep, tensor


def main():
    df = prep(pd.read_parquet(OUT / "weather_long.parquet"))
    df = df[df["city"].isin(list(CITIES)) & (df["day"] <= "2026-10-04")]
    out = {"fit_rows_through": "2026-10-04", "cities": list(CITIES), "exponent": {}}
    for read in READS:
        F, M, Y, _ = tensor(df[df["read"] == read], [], [])
        prior = np.array([1.0])
        r = minimize(nll, prior.copy(), args=(F, M, Y, prior), jac=True, method="L-BFGS-B")
        out["exponent"][read] = round(float(r.x[0]), 4)
        out.setdefault("n_ladders", {})[read] = int(len(Y))
    out["sha256_of_this_dict"] = hashlib.sha256(json.dumps(out, sort_keys=True).encode()).hexdigest()
    (OUT / "prereg_params.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
