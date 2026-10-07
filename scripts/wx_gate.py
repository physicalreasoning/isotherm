#!/usr/bin/env python3
"""Score the multi-station weather model's gates (FINDINGS §34), 16:00 day before.

Weather-model predictions for every ladder day come from expanding quarterly refits: each
quarter is predicted by a model fit on every station-day before it (two-day embargo).

    uv run scripts/wx_gate.py --dry     # coverage only, no scores
    uv run scripts/wx_gate.py
"""

from __future__ import annotations

import argparse
import json
import pathlib
import pickle
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from isotherm import dataset, metrics, wxnet  # noqa: E402
from isotherm.baselines import Source, transformer_large_suite  # noqa: E402
from isotherm.evaluation import oos_predictions  # noqa: E402
from isotherm.model import IsothermNet  # noqa: E402
from isotherm.splits import EMBARGO, LOCKBOX_START  # noqa: E402
from isotherm.weather import CITIES  # noqa: E402

READ = "d1_16"
RECENT_FROM = LOCKBOX_START - pd.Timedelta(days=365)
SPREAD, WX = "isotherm · NBM spread", "isotherm · weather model"
CACHE = pathlib.Path("data/wx_preds.pkl")


def d16(ls):
    return ls.take(np.flatnonzero((ls.meta["read"] == READ).to_numpy()))


def key(rows):
    return (rows.meta["event"] + "|" + rows.meta["read"]).to_numpy()


def paired(days, a, b, sel):
    d = (a - b)[sel]
    return {
        "diff": float(d.mean()),
        "ci": metrics.date_bootstrap_mean(days[sel], d, 2000),
        "n": int(sel.sum()),
    }


def weather_preds(ls):
    if CACHE.exists():
        return pickle.loads(CACHE.read_bytes())
    df = wxnet.corpus()
    tz = wxnet.station_tz()
    rows = []
    for k, c in CITIES.items():
        days = ls.meta.loc[ls.meta["city"] == k, "day"].unique()
        rows.append(wxnet.station_frame(c.station, tz[c.station], targets=days))
    rows = pd.concat(rows, ignore_index=True)
    print(
        "corpus {} station-days, {} stations; {} ladder days".format(
            len(df), df["station"].nunique(), len(rows)
        )
    )
    qs = pd.date_range("2021-10-01", LOCKBOX_START, freq="QS")
    out = []
    for a, b in zip(qs[:-1], qs[1:], strict=True):
        te = rows[(rows["target"] >= a) & (rows["target"] < b)]
        if te.empty:
            continue
        t0 = time.time()
        m = wxnet.WxNet().fit(df[df["target"] < a - EMBARGO])
        c, p = m.predict(te)
        out.append(te.assign(centre=c, p=list(p)))
        print("  {} {} days, fit {:.0f}s".format(a.date(), len(te), time.time() - t0), flush=True)
    preds = pd.concat(out, ignore_index=True)
    CACHE.write_bytes(pickle.dumps(preds))
    return preds


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    cities = list(CITIES)
    ls, lss = d16(dataset.load(cities)), d16(dataset.load(cities, nbm_spread=True))
    assert (key(ls) == key(lss)).all()
    if a.dry:
        df = wxnet.corpus()
        print("corpus", len(df), "station-days,", df["station"].nunique(), "stations; ladders", len(ls))
        return
    wxnet.attach(ls, weather_preds(ls))
    days = ls.meta["day"].to_numpy()
    res = {}

    # Gate 1: forecast level, every ladder 2023-07 to 2026-06.
    ok = np.isfinite(ls.probs["wx_net"]).all(1) & np.isfinite(lss.probs["emos_nbm"]).all(1)
    ok &= (days >= np.datetime64("2023-07-01")) & (days < np.datetime64(LOCKBOX_START))
    L = {
        "wx": metrics.log_score(np.nan_to_num(ls.probs["wx_net"], nan=1.0), ls.y),
        "emos_spread": metrics.log_score(np.nan_to_num(lss.probs["emos_nbm"], nan=1.0), ls.y),
        "emos": metrics.log_score(np.nan_to_num(ls.probs["emos_nbm"], nan=1.0), ls.y),
    }
    res["forecast"] = {
        "vs_emos_spread": paired(days, L["emos_spread"], L["wx"], ok),
        "vs_emos": paired(days, L["emos"], L["wx"], ok),
    }
    res["forecast"]["pass"] = res["forecast"]["vs_emos_spread"]["ci"][0] > 0

    # Gate 2: the MLP with the weather model in place of EMOS-NBM.
    have = np.flatnonzero(np.isfinite(ls.probs["wx_net"]).all(1))
    alt = ls.take(have)
    alt.probs["emos_nbm"] = alt.probs["wx_net"].copy()
    alt.probs["emos_nbm_obs"] = alt.probs["wx_net"].copy()  # no observations the day before
    alt.meta["mu_nbs"], alt.meta["sigma_nbs"] = alt.meta["mu_wx_net"], alt.meta["sigma_wx_net"]
    new = oos_predictions(alt, [Source("market"), IsothermNet(WX)])[READ]
    base = oos_predictions(dataset.load(cities), transformer_large_suite())[READ]
    spr = oos_predictions(
        dataset.load(cities, nbm_spread=True),
        [
            Source("market"),
            IsothermNet(SPREAD),
            IsothermNet(SPREAD + " · market-sampled labels (control)", market_labels=True, seeds=3),
        ],
    )[READ]
    idx = pd.Series(np.arange(len(new.rows)), index=key(new.rows))
    sidx = pd.Series(np.arange(len(spr.rows)), index=key(spr.rows))
    k = key(base.rows)
    hit = pd.Index(k).isin(idx.index) & pd.Index(k).isin(sidx.index)
    j, js = idx[k[hit]].to_numpy(), sidx[k[hit]].to_numpy()
    y, dd = base.rows.y[hit], base.rows.meta["day"].to_numpy()[hit]
    recent = dd >= np.datetime64(RECENT_FROM)
    lm = metrics.log_score(base.preds["market"][hit], y)
    l0 = metrics.log_score(base.preds["isotherm"][hit], y)
    lw = metrics.log_score(new.preds[WX][j], y)
    ls_ = metrics.log_score(spr.preds[SPREAD][js], y)
    res["adoption"] = {
        "vs_mlp": paired(dd, l0, lw, recent),
        "vs_spread_mlp": paired(dd, ls_, lw, recent),
        "wx_mlp_vs_market": float((lm - lw)[recent].mean()),
        "mlp_vs_market": float((lm - l0)[recent].mean()),
    }
    res["adoption"]["pass"] = res["adoption"]["vs_mlp"]["ci"][0] > 0
    pathlib.Path("results/wx_gate.json").write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
