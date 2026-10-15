#!/usr/bin/env python3
"""FINDINGS §50, pre-registered: does ECMWF's learned model (AIFS) add to the live pool?

    uv run scripts/aifs_test.py            # fetch (cached), build the source, score, results/aifs_test.json

Source `emos_aifs`: AIFS 2 m temperature from Open-Meteo's Previous Runs API, the value of each
hour from the run started 48 h before it (`temperature_2m_previous_day2`, every such run public
before 16:00 local on D-1), maximum over the station's local day (at least 20 hours), then EMOS
with the same form, monthly refit and 2-day embargo as `emos_gfs`, from at least 90 days of fit.

Primary: pool(market, EMOS-GFS, EMOS-AIFS) minus the live strategy's pool(market, EMOS-GFS), d1_16,
target days 2025-10-01 to 2026-06-30, quarterly walk-forward on rows from 2025-06-01, log score per
ladder; PASS if the 95% date-block CI lower bound is above zero. Secondaries (a) to (d) as registered.
"""

from __future__ import annotations

import json
import pathlib
import sys
import time
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from isotherm import dataset, metrics  # noqa: E402
from isotherm.baselines import LogPool  # noqa: E402
from isotherm.dataset import DATA, EMBARGO, _finish  # noqa: E402
from isotherm.emos import fit_emos, interval_probs  # noqa: E402
from isotherm.model import IsothermNet, features  # noqa: E402
from isotherm.splits import walk_forward  # noqa: E402
from isotherm.weather import CITIES  # noqa: E402

READ = "d1_16"
TEST_START, TEST_END, TRAIN_FROM = "2025-10-01", "2026-06-30", "2025-06-01"
ARCHIVE_FROM = "2025-01-01"
MIN_FIT_DAYS = 90
OUT = pathlib.Path("results/aifs_test.json")
COORDS = {  # IEM station metadata (data/corpus_stations.json)
    "KNYC": (40.779, -73.9693),
    "KMDW": (41.786, -87.7524),
    "KMIA": (25.7881, -80.3169),
    "KAUS": (30.1945, -97.6699),
    "KLAX": (33.9382, -118.3865),
    "KDEN": (39.8328, -104.6575),
    "KPHL": (39.8683, -75.2311),
}


def _get(url: str, params: dict) -> dict:
    q = url + "?" + urllib.parse.urlencode(params)
    for i in range(6):
        try:
            with urllib.request.urlopen(q, timeout=90) as r:
                return json.loads(r.read())
        except Exception:  # noqa: BLE001 (retry any network error)
            if i == 5:
                raise
            time.sleep(5 * 2**i)
    raise RuntimeError("unreachable")


def _daily_max(times, values) -> pd.Series:
    s = pd.Series(values, index=pd.to_datetime(times), dtype=float)
    g = s.groupby(s.index.normalize())
    return g.max().where(g.count() >= 20)


def aifs_day2(station: str, tz: str) -> pd.Series:
    """Daily local max of AIFS day-2 values, by target day (cached per station)."""
    f = DATA / "forecasts" / f"{station}_AIFS.parquet"
    if f.exists():
        d = pd.read_parquet(f)
        return d.set_index("target")["fcst"]
    lat, lon = COORDS[station]
    end = str((pd.Timestamp.now() - pd.Timedelta(days=3)).date())
    parts = []
    for a, b in ((ARCHIVE_FROM, "2025-12-31"), ("2026-01-01", end)):
        h = _get(
            "https://previous-runs-api.open-meteo.com/v1/forecast",
            {
                "latitude": lat,
                "longitude": lon,
                "start_date": a,
                "end_date": b,
                "hourly": "temperature_2m_previous_day2",
                "models": "ecmwf_aifs025_single",
                "temperature_unit": "fahrenheit",
                "timezone": tz,
            },
        )["hourly"]
        parts.append(_daily_max(h["time"], h["temperature_2m_previous_day2"]))
    s = pd.concat(parts).dropna()
    s.index.name = "target"
    s.rename("fcst").reset_index().to_parquet(f, index=False)
    return s.rename("fcst")


def aifs_exact_12z(station: str, tz: str, days) -> pd.Series:
    """Secondary (d): daily local max from the exact 12z run of D-1, for the given target days."""
    lat, lon = COORDS[station]
    out = {}
    for day in days:
        run = (pd.Timestamp(day) - pd.Timedelta(days=1)).strftime("%Y-%m-%dT12:00")
        try:
            h = _get(
                "https://single-runs-api.open-meteo.com/v1/forecast",
                {
                    "latitude": lat,
                    "longitude": lon,
                    "hourly": "temperature_2m",
                    "models": "ecmwf_aifs025_single",
                    "run": run,
                    "forecast_days": 3,
                    "temperature_unit": "fahrenheit",
                    "timezone": tz,
                },
            )["hourly"]
        except Exception:  # noqa: BLE001 (a missing run is a missing day)
            continue
        v = _daily_max(h["time"], h["temperature_2m"]).get(pd.Timestamp(day))
        if v is not None and np.isfinite(v):
            out[pd.Timestamp(day)] = float(v)
    return pd.Series(out, dtype=float)


def attach_emos(ls, city_key, fc: pd.Series, name: str) -> None:
    """EMOS on a daily forecast series, monthly refit on CLI highs before each month (2-day embargo)."""
    city = CITIES[city_key]
    cli = pd.read_parquet(DATA / "forecasts" / f"{city.station}_cli.parquet")
    cli = cli.rename(columns={"valid": "target"}).dropna(subset=["high"])
    cli["doy"] = cli["target"].dt.dayofyear
    hist = cli.join(fc.rename("fcst"), on="target").dropna(subset=["fcst"])
    day = ls.meta["day"].reset_index(drop=True)
    f_all = fc.reindex(pd.DatetimeIndex(day)).to_numpy(float)
    mine = (ls.meta["city"] == city_key).to_numpy()
    months = day.dt.to_period("M")
    for m in months[mine].unique():
        h = hist[hist["target"] < m.start_time - EMBARGO]
        if len(h) < MIN_FIT_DAYS:
            continue
        model = fit_emos(h["fcst"], h["high"], h["doy"])
        ok = np.flatnonzero(mine & (months == m).to_numpy() & np.isfinite(f_all))
        if len(ok):
            mu, sg = model.params(f_all[ok], day.iloc[ok].dt.dayofyear.to_numpy())
            ls.probs[name][ok] = interval_probs(mu, sg, ls.lo[ok], ls.hi[ok])


def bid_market(ls):
    q = np.where(ls.mask, np.clip(np.nan_to_num(ls.quotes["bid"], nan=0.0), 0.005, 1), 0.0)
    return q / q.sum(1, keepdims=True)


class Net6(IsothermNet):
    """IsothermNet with `emos_aifs` as a sixth source (secondary c)."""

    def _prep(self, ls):
        x, c, logp = features(ls)
        extra = np.log(np.clip(np.nan_to_num(ls.probs["emos_aifs"], nan=0.0), 1e-4, 1))[..., None]
        logp = np.concatenate([logp, extra.astype(np.float32)], -1)
        if self.stats is None:
            xm, xs = x[ls.mask].mean(0), x[ls.mask].std(0) + 1e-6
            self.stats = (xm, xs, c.mean(0), c.std(0) + 1e-6)
        xm, xs, cm, cs = self.stats
        import torch

        x = np.where(ls.mask[..., None], (x - xm) / xs, 0.0).astype(np.float32)
        c = ((c - cm) / cs).astype(np.float32)
        return (torch.from_numpy(x), torch.from_numpy(c), torch.from_numpy(logp), torch.from_numpy(ls.mask))


def diff(days, base_loss, new_loss) -> dict:
    g = np.asarray(base_loss) - np.asarray(new_loss)  # positive: the new model is better
    return {"gain": float(g.mean()), "ci": metrics.date_bootstrap_mean(days, g, 2000), "n": int(len(g))}


def walk(ls, model_factory, days):
    """Out-of-sample predictions on the test window from quarterly walk-forward refits."""
    out = np.full(ls.mask.shape, np.nan)
    # min_train_days=1: every registered test quarter is scored (training starts 2025-06-01).
    for fold in walk_forward(days, start=TEST_START, freq="QS", min_train_days=1):
        tr = fold.train[(days.iloc[fold.train] >= pd.Timestamp(TRAIN_FROM)).to_numpy()]
        te = fold.test[(days.iloc[fold.test] <= pd.Timestamp(TEST_END)).to_numpy()]
        if len(te) == 0 or len(tr) < 30:
            continue
        m = model_factory().fit(ls.take(tr))
        out[te] = m.predict(ls.take(te))
    return out


def main():
    ls = dataset.load(list(CITIES))
    ls = ls.take(np.flatnonzero((ls.meta["read"] == READ).to_numpy()))
    ls.probs["emos_aifs"] = np.full(ls.mask.shape, np.nan)
    for key, city in CITIES.items():
        fc = aifs_day2(city.station, city.tz)
        print(key, "AIFS days", len(fc), fc.index.min().date(), "to", fc.index.max().date(), flush=True)
        attach_emos(ls, key, fc, "emos_aifs")
    ls.probs["emos_aifs"] = _finish(ls.probs["emos_aifs"], ls.mask)

    have = np.isfinite(ls.probs["emos_aifs"]).all(1) & np.isfinite(ls.probs["emos_gfs"]).all(1)
    have &= np.isfinite(ls.probs["market"]).all(1)
    have &= (ls.meta["day"] >= pd.Timestamp(TRAIN_FROM)).to_numpy()
    ls = ls.take(np.flatnonzero(have))
    days = ls.meta["day"].reset_index(drop=True)

    p2 = walk(ls, lambda: LogPool(["market", "emos_gfs"], "pool · market+GFS"), days)
    p3 = walk(ls, lambda: LogPool(["market", "emos_gfs", "emos_aifs"], "pool · market+GFS+AIFS"), days)
    ok = np.isfinite(p2).all(1) & np.isfinite(p3).all(1)
    t = np.flatnonzero(ok)
    y, d = ls.y[t], days.iloc[t].to_numpy()
    loss = lambda p: metrics.log_score(np.where(ls.mask[t], p[t], 0.0), y)  # noqa: E731
    l2, l3 = loss(p2), loss(p3)
    res = {
        "window": [TEST_START, TEST_END],
        "ladders": int(len(t)),
        "days": int(len(np.unique(d))),
        "primary_pool3_minus_pool2": diff(d, l2, l3),
    }
    res["verdict"] = "PASS" if res["primary_pool3_minus_pool2"]["ci"][0] > 0 else "FAIL"

    src = {
        s: loss(np.nan_to_num(ls.probs[s], nan=0.0)) for s in ("emos_aifs", "emos_gfs", "emos_nbm", "market")
    }
    res["secondary_a_emos_aifs_minus_emos_gfs"] = diff(d, src["emos_gfs"], src["emos_aifs"])
    res["secondary_a_emos_aifs_minus_emos_nbm"] = diff(d, src["emos_nbm"], src["emos_aifs"])
    lb = loss(bid_market(ls))
    res["secondary_b_pool3_minus_bid_market"] = diff(d, lb, l3)
    res["context_pool2_minus_bid_market"] = diff(d, lb, l2)

    m5 = walk(ls, lambda: IsothermNet("isotherm · 5 sources"), days)
    m6 = walk(ls, lambda: Net6("isotherm · 6 sources"), days)
    okm = ok & np.isfinite(m5).all(1) & np.isfinite(m6).all(1)
    tm = np.flatnonzero(okm)
    lm5 = metrics.log_score(np.where(ls.mask[tm], m5[tm], 0.0), ls.y[tm])
    lm6 = metrics.log_score(np.where(ls.mask[tm], m6[tm], 0.0), ls.y[tm])
    res["secondary_c_mlp6_minus_mlp5"] = diff(days.iloc[tm].to_numpy(), lm5, lm6)

    # (d) live timing on May to June 2026: exact 12z D-1 run minus the day-2 version.
    may = np.flatnonzero(((days >= "2026-05-01") & (days <= "2026-06-30")).to_numpy())
    if len(may):
        sub = ls.take(may)
        sub.probs["emos_aifs_12z"] = np.full(sub.mask.shape, np.nan)
        for key, city in CITIES.items():
            want = sub.meta.loc[sub.meta["city"] == key, "day"].drop_duplicates()
            exact = aifs_exact_12z(city.station, city.tz, want)
            day2 = aifs_day2(city.station, city.tz)
            # EMOS fit on the day-2 history; the exact run is only the input at prediction time.
            fc = day2.copy()
            fc.loc[exact.index] = exact.to_numpy()
            attach_emos(sub, key, fc, "emos_aifs_12z")
        sub.probs["emos_aifs_12z"] = _finish(sub.probs["emos_aifs_12z"], sub.mask)
        okd = np.isfinite(sub.probs["emos_aifs_12z"]).all(1)
        td = np.flatnonzero(okd)
        a = metrics.log_score(np.where(sub.mask[td], sub.probs["emos_aifs"][td], 0.0), sub.y[td])
        b = metrics.log_score(np.where(sub.mask[td], sub.probs["emos_aifs_12z"][td], 0.0), sub.y[td])
        res["secondary_d_exact_12z_minus_day2"] = diff(sub.meta["day"].iloc[td].to_numpy(), a, b)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
