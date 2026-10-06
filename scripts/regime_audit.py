#!/usr/bin/env python3
"""Regime audit for 2025-2026 (FINDINGS §24): did NBM v5 (2026-04-21) price out the GFS edge?

Descriptive only, no gate. By month at the 16:00 day-before read, seven scored cities:
forecast error of the NBM and GFS MOS point forecasts against the NWS CLI high; log score of
the market and each EMOS source; and the pool's weights refit on the trailing 90 days.

    uv run scripts/regime_audit.py
"""

from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from isotherm import dataset, metrics  # noqa: E402
from isotherm.baselines import fit_pool  # noqa: E402
from isotherm.weather import CITIES  # noqa: E402

READ = "d1_16"
FROM = pd.Timestamp("2025-01-01")
POOLS = {"market+GFS": ["market", "emos_gfs"], "market+NBM+GFS": ["market", "emos_nbm", "emos_gfs"]}


def main():
    ls = dataset.load(list(CITIES))
    ls = ls.take(np.flatnonzero((ls.meta["read"] == READ).to_numpy()))
    ls = ls.complete(["market", "emos_gfs", "emos_nbm"])
    # Forecast error against the NWS CLI high: Kalshi's `settle` field is blank for much of early
    # 2025 (labels come from `result` and are unaffected), and CLI matched settlement on every day.
    cli = pd.concat(
        [
            pd.read_parquet(dataset.DATA / "forecasts" / "{}_cli.parquet".format(c.station))
            .rename(columns={"valid": "day"})[["day", "high"]]
            .assign(city=k)
            for k, c in CITIES.items()
        ]
    )
    ls.meta = ls.meta.merge(cli, on=["city", "day"], how="left")
    m = ls.meta
    month = m["day"].dt.to_period("M")
    out = {}
    for mo in sorted(month[m["day"] >= FROM].unique()):
        s = (month == mo).to_numpy()
        sub = ls.take(np.flatnonzero(s))
        r = {"ladders": int(s.sum())}
        for f in ("nbs", "gfs"):
            e = (sub.meta["fcst_" + f] - sub.meta["high"]).to_numpy(float)
            r["mae_" + f] = float(np.nanmean(np.abs(e)))
            r["bias_" + f] = float(np.nanmean(e))
        for src in ("market", "emos_nbm", "emos_gfs"):
            r["ls_" + src] = float(metrics.log_score(sub.probs[src], sub.y).mean())
        end = mo.end_time.normalize()
        win = ls.take(
            np.flatnonzero(((m["day"] > end - pd.Timedelta(days=90)) & (m["day"] <= end)).to_numpy())
        )
        for k, names in POOLS.items():
            r["w_" + k] = [round(float(x), 3) for x in fit_pool(win, names)]
        out[str(mo)] = r
    pathlib.Path("results/regime_audit.json").write_text(json.dumps(out, indent=2))
    print("month    n  MAE nbm  gfs | bias nbm  gfs | logscore mkt  nbm  gfs | w[mkt,gfs] | w[mkt,nbm,gfs]")
    for mo, r in out.items():
        print(
            "{} {:4d}  {:.2f} {:.2f} | {:+.2f} {:+.2f} | {:.3f} {:.3f} {:.3f} | {} | {}".format(
                mo,
                r["ladders"],
                r["mae_nbs"],
                r["mae_gfs"],
                r["bias_nbs"],
                r["bias_gfs"],
                r["ls_market"],
                r["ls_emos_nbm"],
                r["ls_emos_gfs"],
                r["w_market+GFS"],
                r["w_market+NBM+GFS"],
            )
        )


if __name__ == "__main__":
    main()
