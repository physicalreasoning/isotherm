#!/usr/bin/env python3
"""Freeze the lockbox strategy (FINDINGS §9) into shadow/frozen.json for live shadow scoring.

Everything is fit on data strictly before the lockbox (2026-06-29, 2-day embargo), exactly
as the lockbox run fit it, so the live record tests the same model the lockbox did:
  - per city, EMOS on GFS MOS as known at 16:00 local the day before
  - one log pool of market + EMOS-GFS for the day-before read, pooled across cities

    uv run scripts/shadow_freeze.py
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from isotherm import dataset  # noqa: E402
from isotherm.baselines import LogPool  # noqa: E402
from isotherm.emos import daytime_max_table, fit_emos, forecast_at  # noqa: E402
from isotherm.splits import EMBARGO, LOCKBOX_START  # noqa: E402
from isotherm.weather import AVAILABILITY_LAG, CITIES  # noqa: E402

READ = "d1_16"
CUT = LOCKBOX_START - EMBARGO


def main():
    out = {
        "read": READ,
        "fit_before": str(CUT.date()),
        "strategy": {
            "model": "pool · market+GFS",
            "sizing": "kelly",
            "fraction": 0.25,
            "bankroll": 10_000.0,
            "slots": 7,
            "participation": 0.05,
            "read_local": "16:00 day before",
            "window_local_hours": [16, 18],
        },
        "emos_gfs": {},
    }
    for k, c in CITIES.items():
        cli = pd.read_parquet("data/forecasts/{}_cli.parquet".format(c.station))
        cli = cli.rename(columns={"valid": "target"}).dropna(subset=["high"])
        cli = cli[(cli["target"] >= "2015-01-01") & (cli["target"] < CUT)]
        cli["doy"] = cli["target"].dt.dayofyear
        cli["read_time"] = dataset.local_read_utc(cli["target"], c.tz, *dataset.READS[READ])
        tab = daytime_max_table(
            pd.read_parquet("data/forecasts/{}_GFS.parquet".format(c.station)), "n_x", AVAILABILITY_LAG["GFS"]
        )
        h = cli.join(forecast_at(tab, cli[["target", "read_time"]])).dropna(subset=["fcst"])
        f = fit_emos(h["fcst"], h["high"], h["doy"])
        out["emos_gfs"][k] = {"beta": f.beta.tolist(), "gamma": f.gamma.tolist(), "n": len(h)}
    ls = dataset.load()
    sub = ls.take(np.flatnonzero(((ls.meta["read"] == READ) & (ls.meta["day"] < CUT)).to_numpy()))
    pool = LogPool(["market", "emos_gfs"]).fit(sub)
    out["pool_weights"] = {
        "market": float(pool.weights[READ][0]),
        "emos_gfs": float(pool.weights[READ][1]),
        "n_ladders": len(sub),
    }
    body = json.dumps(out, indent=2, sort_keys=True)
    out["hash"] = hashlib.sha256(body.encode()).hexdigest()[:12]
    p = pathlib.Path("shadow/frozen.json")
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"pool_weights": out["pool_weights"], "hash": out["hash"]}, indent=1))


if __name__ == "__main__":
    main()
