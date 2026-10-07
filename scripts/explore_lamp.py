#!/usr/bin/env python3
"""Exploration (FINDINGS §33): is LAMP's rest-of-day max a better same-day signal than NBM's?

At each same-day read, the high so far observed and the max of the latest public forecast's
hourly temperatures over the rest of the climate day (local standard time) give an estimate of
the final high. Compare its error against the settled high (NWS CLI) for LAMP and for NBM,
which the model already uses (`nbm_rest_max`). A LAMP run counts as public one hour after
its cycle.

    uv run scripts/explore_lamp.py
"""

from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from isotherm import dataset  # noqa: E402
from isotherm.weather import CITIES  # noqa: E402

LAG = pd.Timedelta(hours=1)
READS = ["d0_08", "d0_12", "d0_14"]


def main():
    out = {}
    rows = []
    for k, c in CITIES.items():
        ls = dataset.build_city(k)
        m = ls.meta[ls.meta["read"].isin(READS)].copy()
        cli = pd.read_parquet(dataset.DATA / "forecasts" / "{}_cli.parquet".format(c.station))
        m = m.merge(cli.rename(columns={"valid": "day"})[["day", "high"]], on="day", how="left")
        lav = pd.read_parquet(dataset.DATA / "forecasts" / "{}_LAV.parquet".format(c.station))
        lav = lav.dropna(subset=["tmp"]).sort_values(["runtime", "ftime"])
        start = m["day"].dt.tz_localize("UTC") - pd.Timedelta(hours=c.std_offset_h)
        end = start + pd.Timedelta(hours=24)
        read = pd.to_datetime(m["read_ts"], unit="s", utc=True)
        by_run = {rt: g for rt, g in lav.groupby("runtime")}
        runs = np.array(sorted(by_run))
        lr = []
        for rt_read, e in zip(read, end, strict=True):
            ok = runs[runs + LAG <= rt_read]
            if not len(ok):
                lr.append(np.nan)
                continue
            g = by_run[ok.max()]
            rest = g["tmp"][(g["ftime"] > rt_read) & (g["ftime"] <= e)]
            lr.append(float(rest.max()) if len(rest) else np.nan)
        m["lamp_rest_max"] = lr
        m["city"] = k
        rows.append(m[["city", "day", "read", "high", "obs_best", "nbm_rest_max", "lamp_rest_max"]])
    df = pd.concat(rows, ignore_index=True)
    df = df[(df["day"] >= "2023-07-01") & (df["day"] < "2026-07-01")].dropna(subset=["high"])
    for read in READS:
        d = df[df["read"] == read].dropna(subset=["nbm_rest_max", "lamp_rest_max"])
        obs = d["obs_best"].fillna(-999)
        est_n = np.maximum(obs, d["nbm_rest_max"])
        est_l = np.maximum(obs, d["lamp_rest_max"])
        est_b = np.maximum(obs, (d["nbm_rest_max"] + d["lamp_rest_max"]) / 2)
        r = {"n": len(d)}
        for name, est in (("nbm", est_n), ("lamp", est_l), ("blend", est_b)):
            e = est - d["high"]
            r[name] = {"mae": float(e.abs().mean()), "bias": float(e.mean())}
        r["corr_of_errors"] = float(np.corrcoef(est_n - d["high"], est_l - d["high"])[0, 1])
        out[read] = r
        print(
            "{} n={:5d} MAE nbm {:.2f} lamp {:.2f} blend {:.2f} | bias {:+.2f} {:+.2f} | r {:.2f}".format(
                read,
                r["n"],
                r["nbm"]["mae"],
                r["lamp"]["mae"],
                r["blend"]["mae"],
                r["nbm"]["bias"],
                r["lamp"]["bias"],
                r["corr_of_errors"],
            )
        )
    pathlib.Path("results/explore_lamp.json").write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
