"""GFS LAMP as a same-day input (FINDINGS §33).

LAMP updates the GFS MOS guidance with the latest observations every hour; IEM archives a few
cycles a day. At each same-day read, the latest run public by then (cycle + 1 h) gives an hourly
temperature path; its max over the rest of the climate day (local standard time), floored by
the high already observed, estimates the final high. Two bucket features follow, attached to
`ls.quotes` like those in `flow.py`: the bucket centre's distance from that estimate, and
whether the observed high already exceeds the bucket.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .dataset import DATA, LadderSet
from .weather import ALL_CITIES

LAG = pd.Timedelta(hours=1)
LAMP = ["x_lamp_dist", "x_lamp_has"]


def rest_max(ls: LadderSet) -> np.ndarray:
    m = ls.meta.reset_index(drop=True)
    out = np.full(len(m), np.nan)
    for key in m["city"].unique():
        c = ALL_CITIES[key]
        f = DATA / "forecasts" / "{}_LAV.parquet".format(c.station)
        if not f.exists():
            continue
        lav = pd.read_parquet(f).dropna(subset=["tmp"])
        by_run = {rt: (g["ftime"].to_numpy(), g["tmp"].to_numpy(float)) for rt, g in lav.groupby("runtime")}
        runs = np.array(sorted(by_run))
        idx = np.flatnonzero(((m["city"] == key) & m["read"].str.startswith("d0")).to_numpy())
        start = m.loc[idx, "day"].dt.tz_localize("UTC") - pd.Timedelta(hours=c.std_offset_h)
        end = (start + pd.Timedelta(hours=24)).to_numpy()
        read = pd.to_datetime(m.loc[idx, "read_ts"], unit="s", utc=True).to_numpy()
        pub = runs + LAG
        for i, rt, e in zip(idx, read, end, strict=True):
            j = np.searchsorted(pub, rt, "right") - 1
            if j < 0:
                continue
            ft, tmp = by_run[runs[j]]
            sel = (ft > rt) & (ft <= e)
            if sel.any():
                out[i] = tmp[sel].max()
    return out


def add_lamp(ls: LadderSet) -> None:
    n, k = ls.mask.shape
    rm = rest_max(ls)
    obs = ls.meta["obs_best"].to_numpy(float) if "obs_best" in ls.meta else np.full(n, np.nan)
    est = np.fmax(rm, obs)  # NaN only when both are missing
    has = np.isfinite(rm)
    lo = np.where(np.isfinite(ls.lo), ls.lo, ls.hi - 2.0)
    hi = np.where(np.isfinite(ls.hi), ls.hi, ls.lo + 2.0)
    cen = (lo + hi) / 2
    dist = np.where(has[:, None], np.clip((cen - np.nan_to_num(est)[:, None]) / 5, -3, 3), 0.0)
    ls.quotes["x_lamp_dist"] = np.where(ls.mask, dist, 0.0)
    ls.quotes["x_lamp_has"] = np.where(ls.mask, np.repeat(has[:, None].astype(float), k, 1), 0.0)
