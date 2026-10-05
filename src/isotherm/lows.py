"""Daily low-temperature ladders: series map, overnight-min forecasts, causal EMOS.

The settled value is the NWS climate-day minimum (midnight to midnight local standard
time) at the same seven stations as the highs; Kalshi switched the settlement source to
The Weather Company the same way. Labels always come from Kalshi's `result`.

Forecasts. GFS MOS (and NBM) report the overnight minimum, 7pm to 8am LST, at forecast
hour 12Z of the morning it ends: for local day D that is the row with ftime = D 12Z.
The climate-day minimum can instead fall late on D itself when cold air arrives in the
evening; the overnight min does not see that, and EMOS absorbs the average gap as bias.

Everything here is a fixed causal function of the past, as in `dataset.py`: a forecast
run counts only once public (GFS +5h, NBM +2h) and EMOS and climatology refit monthly on
CLI lows strictly before the month, with a 2-day embargo.
"""

from __future__ import annotations

import dataclasses
import pathlib

import numpy as np
import pandas as pd

from . import dataset
from .emos import fit_climatology, fit_emos, interval_probs
from .evaluation import OOS
from .splits import EMBARGO
from .weather import AVAILABILITY_LAG, CITIES

LOW_SERIES = {
    "NY": "KXLOWTNYC",
    "CHI": "KXLOWTCHI",
    "MIA": "KXLOWTMIA",
    "AUS": "KXLOWTAUS",
    "LAX": "KXLOWTLAX",
    "DEN": "KXLOWTDEN",
    "PHIL": "KXLOWTPHIL",
}
READS = {"d1_16": (-1, 16), "d1_22": (-1, 22)}
FORECASTS = {"emos_gfs": ("GFS", "n_x", "2015-01-01"), "emos_nbm": ("NBS", "txn", "2021-01-01")}
# The series start on 2025-12-14, so the weather calendar (quarterly folds from 2023-07,
# lockbox 2026-07-01) leaves no pre-lockbox fold. Lows use monthly folds and their own
# lockbox, fixed here before any score was computed (docs/LOWS_RAIN.md).
FOLD_START = "2026-02-01"
FOLD_FREQ = "MS"
MIN_TRAIN_DAYS = 45
LOCKBOX_START = pd.Timestamp("2026-09-01")
FORECAST_ROOT = dataset.DATA / "forecasts"  # shared with the highs: same stations, same files
PANEL = pathlib.Path("data/lows_panel")


def low_city(key: str):
    return dataclasses.replace(CITIES[key], series=LOW_SERIES[key])


def overnight_min_table(mos: pd.DataFrame, value_col: str, lag: pd.Timedelta) -> pd.DataFrame:
    """MOS rows carrying the overnight minimum that ends on the morning of local day `target`."""
    m = mos[mos[value_col].notna() & (mos["ftime"].dt.hour == 12)].copy()
    m["target"] = m["ftime"].dt.tz_localize(None).dt.normalize()
    m["public"] = m["runtime"] + lag
    m = m.rename(columns={value_col: "fcst"})
    return m[["target", "runtime", "public", "fcst"]].sort_values("public")


def _forecast_at(table, targets: pd.Series, reads: pd.Series) -> np.ndarray:
    q = pd.DataFrame({"target": targets.to_numpy(), "read_time": reads.to_numpy()}).reset_index()
    q["target"] = q["target"].astype(table["target"].dtype)
    q = q.sort_values("read_time")
    out = pd.merge_asof(q, table, left_on="read_time", right_on="public", by="target", direction="backward")
    return out.set_index("index").sort_index()["fcst"].to_numpy()


def attach_lows(ls: dataset.LadderSet, key: str) -> None:
    """Causal EMOS (GFS, NBM) and climatology bucket probabilities on CLI lows."""
    city = CITIES[key]
    cli = pd.read_parquet(FORECAST_ROOT / "{}_cli.parquet".format(city.station))
    cli = cli.rename(columns={"valid": "target"}).dropna(subset=["low"])
    cli["doy"] = cli["target"].dt.dayofyear
    months = ls.meta["day"].dt.to_period("M")
    doy = ls.meta["day"].dt.dayofyear.to_numpy()
    n, k = ls.mask.shape

    def fits(hist, fitter, ms):
        out = {}
        for m in ms:
            h = hist[hist["target"] < m.start_time - EMBARGO]
            if len(h) >= 365:
                out[m] = fitter(h)
        return out

    clim = fits(cli, lambda h: fit_climatology(h["low"], h["doy"]), months.unique())
    p = np.full((n, k), np.nan)
    for m, f in clim.items():
        s = (months == m).to_numpy()
        mu, sg = f.params(None, doy[s])
        p[s] = interval_probs(mu, sg, ls.lo[s], ls.hi[s])
    ls.probs["climatology"] = dataset._finish(p, ls.mask)

    for name, (model, col, start) in FORECASTS.items():
        f = FORECAST_ROOT / "{}_{}.parquet".format(city.station, model)
        if not f.exists():
            continue
        table = overnight_min_table(pd.read_parquet(f), col, AVAILABILITY_LAG[model])
        p = np.full((n, k), np.nan)
        fc_all = np.full(n, np.nan)
        for read, (dd, hh) in READS.items():
            rs = (ls.meta["read"] == read).to_numpy()
            if not rs.any():
                continue
            hist = cli[cli["target"] >= start].copy()
            hist["fcst"] = _forecast_at(
                table, hist["target"], dataset.local_read_utc(hist["target"], city.tz, dd, hh)
            )
            hist = hist.dropna(subset=["fcst"])
            days = ls.meta.loc[rs, "day"]
            fc_all[rs] = _forecast_at(table, days, dataset.local_read_utc(days, city.tz, dd, hh))
            ef = fits(hist, lambda h: fit_emos(h["fcst"], h["low"], h["doy"]), months[rs].unique())
            idx = np.flatnonzero(rs)
            for m, fit in ef.items():
                s = idx[(months[rs] == m).to_numpy()]
                ok = s[np.isfinite(fc_all[s])]
                if len(ok):
                    mu, sg = fit.params(fc_all[ok], doy[ok])
                    p[ok] = interval_probs(mu, sg, ls.lo[ok], ls.hi[ok])
        ls.probs[name] = dataset._finish(p, ls.mask)
        ls.meta["fcst_" + model.lower()] = fc_all


def load(keys=None) -> dataset.LadderSet:
    parts = []
    for key in keys or LOW_SERIES:
        f = PANEL / "{}.parquet".format(key)
        if not f.exists():
            continue
        ls = dataset._ladders(pd.read_parquet(f), low_city(key))
        if len(ls):
            attach_lows(ls, key)
            parts.append(ls)
    return dataset.LadderSet.concat(parts)


def walk_forward(days: pd.Series):
    from .splits import walk_forward as wf

    return wf(
        days, start=FOLD_START, freq=FOLD_FREQ, min_train_days=MIN_TRAIN_DAYS, lockbox_start=LOCKBOX_START
    )


def oos_predictions(ls: dataset.LadderSet, suite) -> dict:
    """evaluation.oos_predictions on the lows calendar (monthly folds, own lockbox)."""
    out = {}
    for read in sorted(ls.meta["read"].unique()):
        sub = ls.take(np.flatnonzero(ls.meta["read"].to_numpy() == read))
        preds = {m.name: np.full(sub.mask.shape, np.nan) for m in suite}
        fold_of = np.full(len(sub), -1)
        folds = []
        for i, f in enumerate(walk_forward(sub.meta["day"])):
            tr, te = sub.take(f.train), sub.take(f.test)
            folds.append({"fold": f.name, "train": len(f.train), "test": len(f.test)})
            fold_of[f.test] = i
            for m in suite:
                preds[m.name][f.test] = m.fit(tr).predict(te)
        ok = fold_of >= 0
        for p in preds.values():
            ok &= np.isfinite(p).all(1)
        idx = np.flatnonzero(ok)
        out[read] = OOS(read, sub.take(idx), {k: v[idx] for k, v in preds.items()}, fold_of[idx], folds)
    return out
