#!/usr/bin/env python3
"""Typed answers, evaluated (FINDINGS §38): Choice, Noul and Score from the one distribution.

Every result so far scores the bucket probabilities. The public interface (`isotherm.api`) answers
three question types off one integer distribution, built from those probabilities exactly as
`serve.integer_distribution` builds it (the forecast Gaussian spreads each bucket's mass over its
integers). This scores what a user of the API would receive, for the market and each model, on
the out-of-sample rows of the last 12 months before the lockbox:

    Choice  which bucket settles             log loss (the usual metric)
    Noul    P(high >= t), every integer t    Brier score, debiased calibration error
            within 6°F of the NBM forecast
    Score   the high itself                  CRPS, absolute error of the median,
                                             coverage and width of the 80% interval

Coherence (Choice sums to one, Noul monotone in t, mean inside the 1-99% range) is checked on
every distribution. The within-bucket shape is the same for every model, so differences inside a
bucket come only from the bucket probabilities.

    uv run scripts/typed_eval.py
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import pickle
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from isotherm import dataset, metrics, wxnet  # noqa: E402
from isotherm.baselines import Source, transformer_large_suite  # noqa: E402
from isotherm.evaluation import oos_predictions  # noqa: E402
from isotherm.model import IsothermNet  # noqa: E402
from isotherm.serve import integer_distribution  # noqa: E402
from isotherm.splits import LOCKBOX_START  # noqa: E402
from isotherm.weather import CITIES  # noqa: E402

RECENT_FROM = LOCKBOX_START - pd.Timedelta(days=365)
NOUL_RANGE = 6
MODELS = {"market": "market", "isotherm": "isotherm", "transformer-L": "isotherm · transformer-L"}
WX = "isotherm · weather model"


def highs(meta: pd.DataFrame) -> np.ndarray:
    """The settled integer high: Kalshi's settle value, else the NWS CLI high."""
    h = pd.to_numeric(meta["settle"], errors="coerce").to_numpy(float).copy()
    for k, c in CITIES.items():
        cli = pd.read_parquet(dataset.DATA / "forecasts" / "{}_cli.parquet".format(c.station))
        m = cli.set_index("valid")["high"]
        sel = (meta["city"] == k).to_numpy() & ~np.isfinite(h)
        h[sel] = meta.loc[sel, "day"].map(m).to_numpy(float)
    return h


def weather_rows(ls):
    """The §35 weather-model MLP at 16:00 day before, from the gate's caches."""
    d16 = ls.take(np.flatnonzero((ls.meta["read"] == "d1_16").to_numpy()))
    wxnet.attach(d16, pickle.loads(pathlib.Path("data/wx_preds.pkl").read_bytes()))
    alt = wxnet.as_inputs(d16)
    wx_id = hashlib.sha256(np.nan_to_num(alt.probs["wx_net"]).tobytes()).hexdigest()[:12]
    f = pathlib.Path("data/oos_wx") / wx_id
    if not f.exists():
        return None
    return oos_predictions(alt, [Source("market"), IsothermNet(WX)], cache_dir=str(f))["d1_16"]


def typed_scores(rows, preds: dict) -> dict:
    """Per-ladder metrics for each model on `rows`."""
    m = rows.meta
    y = highs(m)
    mu = m["mu_nbs"].fillna(m["mu_gfs"]).to_numpy(float)
    sg = m["sigma_nbs"].fillna(m["sigma_gfs"]).fillna(3.0).to_numpy(float)
    ok = np.isfinite(y) & np.isfinite(mu)
    # The settled high must fall in the settled bucket; anything else is a label we cannot use.
    yi = rows.y
    ok &= (y > rows.lo[np.arange(len(y)), yi]) & (y < rows.hi[np.arange(len(y)), yi])
    out = {
        k: {
            "crps": [],
            "ae": [],
            "cover": [],
            "mass": [],
            "width": [],
            "noul_b": [],
            "noul_p": [],
            "noul_o": [],
        }
        for k in preds
    }
    viol = 0
    idx = np.flatnonzero(ok)
    for i in idx:
        mk = rows.mask[i]
        iv = list(zip(rows.lo[i][mk], rows.hi[i][mk], strict=True))
        ts = np.arange(round(mu[i]) - NOUL_RANGE, round(mu[i]) + NOUL_RANGE + 1)
        for k, p in preds.items():
            d = integer_distribution(p[i][mk], iv, mu[i], sg[i])
            v, pv = d.v, d.p
            grid = np.arange(min(v[0], int(y[i])) - 1, max(v[-1], int(y[i])) + 2)
            F = np.cumsum(np.interp(grid, v, pv, left=0, right=0))
            out[k]["crps"].append(float(((F - (grid >= y[i])) ** 2).sum()))
            q10, q50, q90 = d.quantile(0.1), d.quantile(0.5), d.quantile(0.9)
            out[k]["ae"].append(abs(q50 - y[i]))
            out[k]["cover"].append(float(q10 <= y[i] <= q90))
            # Integer quantiles with inclusive ends hold more than 80% of the mass; compare
            # observed coverage with the mass the model itself puts inside the interval.
            out[k]["mass"].append(float(pv[(v >= q10) & (v <= q90)].sum()))
            out[k]["width"].append(q90 - q10)
            ge = np.array([pv[v >= t].sum() for t in ts])
            out[k]["noul_b"].append(float(((ge - (y[i] >= ts)) ** 2).mean()))
            out[k]["noul_p"].append(ge)
            out[k]["noul_o"].append((y[i] >= ts).astype(float))
            choice = np.array([pv[(v + 0.5 > a) & (v - 0.5 < b)].sum() for a, b in iv])
            viol += int(abs(choice.sum() - 1) > 1e-6)
            viol += int((np.diff(ge) > 1e-12).any())
            mean = float(pv @ v)
            viol += int(not (d.quantile(0.01) <= mean <= d.quantile(0.99)))
    return {"idx": idx, "y": y, "per": out, "violations": viol}


def summarise(rows, preds, s) -> dict:
    days = rows.meta["day"].to_numpy()[s["idx"]]
    yb = rows.y[s["idx"]]
    res = {"ladders": len(s["idx"]), "coherence_violations": s["violations"], "models": {}}
    ref = s["per"]["market"]
    ls_m = metrics.log_score(preds["market"][s["idx"]], yb)
    for k, o in s["per"].items():
        crps = np.array(o["crps"])
        nb = np.array(o["noul_b"])
        ls_k = metrics.log_score(preds[k][s["idx"]], yb)
        r = {
            "choice_log_loss": float(ls_k.mean()),
            "score_crps": float(crps.mean()),
            "score_median_abs_err": float(np.mean(o["ae"])),
            "score_80_coverage": float(np.mean(o["cover"])),
            "score_80_predicted_mass": float(np.mean(o["mass"])),
            "score_80_width": float(np.mean(o["width"])),
            "noul_brier": float(nb.mean()),
            "noul_ece": float(metrics.ece_debiased(np.concatenate(o["noul_p"]), np.concatenate(o["noul_o"]))),
        }
        if k != "market":
            r["vs_market"] = {
                "choice_log_loss": metrics.date_bootstrap_mean(days, ls_m - ls_k, 2000),
                "score_crps": metrics.date_bootstrap_mean(days, np.array(ref["crps"]) - crps, 2000),
                "noul_brier": metrics.date_bootstrap_mean(days, np.array(ref["noul_b"]) - nb, 2000),
            }
            r["vs_market_mean"] = {
                "choice_log_loss": float((ls_m - ls_k).mean()),
                "score_crps": float((np.array(ref["crps"]) - crps).mean()),
                "noul_brier": float((np.array(ref["noul_b"]) - nb).mean()),
            }
        res["models"][k] = r
    return res


def main():
    ls = dataset.load(list(CITIES))
    base = oos_predictions(ls, transformer_large_suite())
    out = {"window": [str(RECENT_FROM.date()), str(LOCKBOX_START.date())], "reads": {}}
    for read, o in base.items():
        sel = np.flatnonzero(o.rows.meta["day"].to_numpy() >= np.datetime64(RECENT_FROM))
        rows = o.rows.take(sel)
        preds = {k: o.preds[v][sel] for k, v in MODELS.items()}
        out["reads"][read] = summarise(rows, preds, typed_scores(rows, preds))
        print(read, json.dumps(out["reads"][read]["models"]["isotherm"].get("vs_market_mean")), flush=True)
    wx = weather_rows(ls)
    if wx is not None:
        sel = np.flatnonzero(wx.rows.meta["day"].to_numpy() >= np.datetime64(RECENT_FROM))
        rows = wx.rows.take(sel)
        preds = {"market": wx.preds["market"][sel], "isotherm · weather model": wx.preds[WX][sel]}
        out["weather_model_d1_16"] = summarise(rows, preds, typed_scores(rows, preds))
    pathlib.Path("results/typed_eval.json").write_text(json.dumps(out, indent=2))
    for read, r in out["reads"].items():
        print("\n" + read, r["ladders"], "ladders, coherence violations:", r["coherence_violations"])
        for k, v in r["models"].items():
            print(
                "  {:16s} log loss {:.4f} CRPS {:.3f} |med err| {:.2f} 80% cover {:.3f} of {:.3f} w {:.1f}"
                "  Noul Brier {:.4f} ECE {:.4f}".format(
                    k,
                    v["choice_log_loss"],
                    v["score_crps"],
                    v["score_median_abs_err"],
                    v["score_80_coverage"],
                    v["score_80_predicted_mass"],
                    v["score_80_width"],
                    v["noul_brier"],
                    v["noul_ece"],
                )
            )


if __name__ == "__main__":
    main()
