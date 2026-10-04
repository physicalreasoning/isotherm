"""Panel -> padded ladder arrays with every causal forecast attached.

One row = one (city, day, read time) ladder. Buckets are sorted by temperature
and padded to the widest ladder; `mask` marks real buckets. `probs[name]` holds
each source's bucket distribution on identical rows, so every model in the
benchmark is scored on exactly the same questions.

Causality. Each forecast source is a *fixed function of the past*:
  - market   the last hourly candle closed at or before the read time
  - emos_*   latest MOS run public at the read time, through an EMOS refit each
             month on CLI highs strictly before that month (2-day embargo)
  - clim     harmonic climatology, refit monthly the same way
Learned models (log pools, the neural model) then train only on earlier rows,
through `splits.walk_forward`.
"""
from __future__ import annotations

import hashlib
import pathlib
import pickle
from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np
import pandas as pd

from .emos import daytime_max_table, fit_climatology, fit_emos, forecast_at, interval_probs
from .weather import AVAILABILITY_LAG, CITIES, City, bucket_interval

READS = {"d1_16": (-1, 16), "d0_08": (0, 8), "d0_12": (0, 12)}
FORECASTS = {"emos_gfs": ("GFS", "n_x", "2015-01-01"), "emos_nbm": ("NBS", "txn", "2021-01-01")}
EMBARGO = pd.Timedelta(days=2)
MIN_FIT_DAYS = 365
EPS = 1e-3            # probability floor; a tenth of Kalshi's 1¢ tick
DATA = pathlib.Path("data")
VERSION = 3           # bump when anything below changes what a row contains


@dataclass
class LadderSet:
    meta: pd.DataFrame
    lo: np.ndarray
    hi: np.ndarray
    mask: np.ndarray
    y: np.ndarray
    probs: Dict[str, np.ndarray] = field(default_factory=dict)

    def __len__(self):
        return len(self.meta)

    def take(self, idx) -> "LadderSet":
        idx = np.asarray(idx)
        return LadderSet(self.meta.iloc[idx].reset_index(drop=True), self.lo[idx], self.hi[idx],
                         self.mask[idx], self.y[idx], {k: v[idx] for k, v in self.probs.items()})

    def complete(self, names) -> "LadderSet":
        """Rows where every named source has a forecast: the identical-rows rule."""
        ok = np.ones(len(self), bool)
        for n in names:
            ok &= np.isfinite(self.probs[n]).all(1)     # missing rows are all-NaN by construction
        return self.take(np.flatnonzero(ok))

    @staticmethod
    def concat(parts: List["LadderSet"]) -> "LadderSet":
        parts = [p for p in parts if len(p)]
        k = max(p.mask.shape[1] for p in parts)

        def padk(a, fill):
            return np.pad(a, ((0, 0), (0, k - a.shape[1])), constant_values=fill)
        names = set.intersection(*(set(p.probs) for p in parts))
        return LadderSet(pd.concat([p.meta for p in parts], ignore_index=True),
                         np.concatenate([padk(p.lo, np.nan) for p in parts]),
                         np.concatenate([padk(p.hi, np.nan) for p in parts]),
                         np.concatenate([padk(p.mask, False) for p in parts]),
                         np.concatenate([p.y for p in parts]),
                         {n: np.concatenate([padk(p.probs[n], 0.0) for p in parts]) for n in names})


def regime(rules: str) -> str:
    if "Weather Company" in rules:
        return "twc"
    if "Climatological Report" in rules:
        return "nws_cli"
    return "other"


def local_read_utc(days: pd.Series, tz: str, dd: int, hh: int) -> pd.Series:
    t = (days + pd.Timedelta(days=dd) + pd.Timedelta(hours=hh)).dt.tz_localize(
        tz, nonexistent="shift_forward", ambiguous=False)
    return t.dt.tz_convert("UTC")


def _normalise(p, mask):
    p = np.where(mask, np.clip(p, EPS, None), 0.0)
    return p / p.sum(1, keepdims=True)


def _ladders(panel: pd.DataFrame, city: City) -> LadderSet:
    if "candles_ok" in panel:
        bad = panel.loc[~panel["candles_ok"], "event"].unique()
        panel = panel[~panel["event"].isin(bad)]
    metas, los, his, mids, ys = [], [], [], [], []
    for (ev, read), g in panel.groupby(["event", "read"], sort=False):
        iv = [bucket_interval(s, f, c) for s, f, c in
              zip(g.strike_type, g["floor"], g["cap"], strict=True)]
        order = np.argsort([a for a, _ in iv])
        g = g.iloc[order]
        iv = [iv[i] for i in order]
        y = g["y"].to_numpy()
        if y.sum() != 1:
            continue
        b, a = g["bid"].to_numpy(float), g["ask"].to_numpy(float)
        if np.all(np.isnan(b) & np.isnan(a)):
            continue                                   # market not open at this read
        b = np.nan_to_num(b, nan=0.0)
        a = np.where(np.isnan(a) | (a <= 0), 1.0, a)
        mid = (a + b) / 2
        metas.append({"event": ev, "city": city.key, "day": g["day"].iloc[0], "read": read,
                      "n_buckets": len(g), "settle": float(g["settle"].iloc[0]),
                      "spread": float(np.median(a - b)), "overround": float(mid.sum()),
                      "cum_volume": float(g["cum_volume"].sum()),
                      "regime": regime(str(g["rules"].iloc[0]))})
        los.append([x for x, _ in iv])
        his.append([x for _, x in iv])
        mids.append(mid)
        ys.append(int(np.argmax(y)))
    if not metas:
        return LadderSet(pd.DataFrame(), np.zeros((0, 1)), np.zeros((0, 1)),
                         np.zeros((0, 1), bool), np.zeros(0, int))
    k = max(len(x) for x in los)

    def pad(rows, fill):
        return np.array([list(r) + [fill] * (k - len(r)) for r in rows], dtype=float)
    lo, hi, mid = pad(los, np.nan), pad(his, np.nan), pad(mids, 0.0)
    mask = np.array([[True] * len(r) + [False] * (k - len(r)) for r in los])
    meta = pd.DataFrame(metas)
    meta["day"] = pd.to_datetime(meta["day"])
    return LadderSet(meta, lo, hi, mask, np.array(ys), {"market": _normalise(mid, mask)})


def _monthly_fits(hist: pd.DataFrame, months, fitter):
    fits = {}
    for m in months:
        cut = m.start_time - EMBARGO
        h = hist[hist["target"] < cut]
        if len(h) >= MIN_FIT_DAYS:
            fits[m] = fitter(h)
    return fits


def _attach_gaussians(ls: LadderSet, city: City) -> None:
    cli = pd.read_parquet(DATA / "forecasts" / "{}_cli.parquet".format(city.station))
    cli = cli.rename(columns={"valid": "target"}).dropna(subset=["high"])
    cli["doy"] = cli["target"].dt.dayofyear
    months = ls.meta["day"].dt.to_period("M")
    doy = ls.meta["day"].dt.dayofyear.to_numpy()
    n, k = ls.mask.shape

    clim = _monthly_fits(cli, months.unique(), lambda h: fit_climatology(h["high"], h["doy"]))
    p = np.full((n, k), np.nan)
    for m, f in clim.items():
        s = (months == m).to_numpy()
        mu, sg = f.params(None, doy[s])
        p[s] = interval_probs(mu, sg, ls.lo[s], ls.hi[s])
    ls.probs["climatology"] = _finish(p, ls.mask)

    for name, (model, col, start) in FORECASTS.items():
        fp = DATA / "forecasts" / "{}_{}.parquet".format(city.station, model)
        if not fp.exists():
            continue
        table = daytime_max_table(pd.read_parquet(fp), col, AVAILABILITY_LAG[model])
        p = np.full((n, k), np.nan)
        fc_all = np.full(n, np.nan)
        lead_all = np.full(n, np.nan)
        for read, (dd, hh) in READS.items():
            rs = (ls.meta["read"] == read).to_numpy()
            if not rs.any():
                continue
            hist = cli[cli["target"] >= start].copy()
            hist["read_time"] = local_read_utc(hist["target"], city.tz, dd, hh)
            hist = hist.join(forecast_at(table, hist[["target", "read_time"]])).dropna(
                subset=["fcst"])
            fits = _monthly_fits(hist, months[rs].unique(),
                                 lambda h: fit_emos(h["fcst"], h["high"], h["doy"]))
            days = ls.meta.loc[rs, "day"]
            fc = forecast_at(table, pd.DataFrame({"target": days.to_numpy(), "read_time":
                                                  local_read_utc(days, city.tz, dd, hh).to_numpy()}))
            fc_all[rs] = fc["fcst"].to_numpy()
            lead_all[rs] = fc["lead_h"].to_numpy()
            idx = np.flatnonzero(rs)
            for m, f in fits.items():
                s = idx[(months[rs] == m).to_numpy()]
                ok = s[np.isfinite(fc_all[s])]
                if len(ok):
                    mu, sg = f.params(fc_all[ok], doy[ok])
                    p[ok] = interval_probs(mu, sg, ls.lo[ok], ls.hi[ok])
        ls.probs[name] = _finish(p, ls.mask)
        ls.meta["fcst_" + model.lower()] = fc_all
        ls.meta["lead_h_" + model.lower()] = lead_all


def _finish(p, mask):
    """Floor and renormalise rows that have a forecast; leave missing rows NaN."""
    p = np.where(mask, p, 0.0)
    ok = np.isfinite(p).all(1)
    out = np.full_like(p, np.nan)
    out[ok] = _normalise(p[ok], mask[ok])
    return out


def build_city(key: str, cache: bool = True) -> LadderSet:
    city = CITIES[key]
    pp = DATA / "panel" / "{}.parquet".format(key)
    if not pp.exists():
        raise FileNotFoundError(pp)
    inputs = [pp] + sorted((DATA / "forecasts").glob(city.station + "_*.parquet"))
    h = hashlib.sha256(repr((VERSION, [(str(f), f.stat().st_mtime_ns) for f in inputs])).encode())
    cp = DATA / "features" / "{}_{}.pkl".format(key, h.hexdigest()[:12])
    if cache and cp.exists():
        return pickle.loads(cp.read_bytes())
    ls = _ladders(pd.read_parquet(pp), city)
    if len(ls):
        _attach_gaussians(ls, city)
    cp.parent.mkdir(parents=True, exist_ok=True)
    for old in cp.parent.glob("{}_*.pkl".format(key)):
        old.unlink()
    cp.write_bytes(pickle.dumps(ls))
    return ls


def load(cities=None) -> LadderSet:
    cities = cities or [k for k in CITIES if (DATA / "panel" / "{}.parquet".format(k)).exists()]
    return LadderSet.concat([build_city(k) for k in cities])
