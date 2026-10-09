#!/usr/bin/env python3
"""Exploration (FINDINGS §46): can we predict, before the read, when isotherm beats the market?

The month explains 97 to 99% of the variance in isotherm's gain (§45), so the useful question is
not whether there is an edge but whether there is one today. Target: each ladder's out-of-sample
gain of the MLP over the market (log score). Features, all known at the read:
  disagreement   KL(isotherm || market) and the largest bucket difference on this ladder
  forecasts      |NBM - GFS| in forecast sigmas, NBM sigma, GFS lead time
  book           spread, overround, log volume so far
  season         day-of-year sin, cos
  recent         mean gain and market log loss over the 30 days settled by D-2, same read
A ridge regression, refit monthly on all earlier months (12 months of warm-up), predicts each
ladder's gain. Evaluated on 2024-07 to 2026-06: rank correlation of predicted and realised gain,
and a gated model that uses isotherm where the prediction is positive and the market elsewhere.

    uv run scripts/edge_model.py
"""

from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from isotherm import dataset, metrics  # noqa: E402
from isotherm.backtest import Config, run  # noqa: E402
from isotherm.baselines import transformer_large_suite  # noqa: E402
from isotherm.evaluation import oos_predictions  # noqa: E402
from isotherm.weather import CITIES  # noqa: E402

WARMUP_MONTHS = 12
RIDGE = 10.0
FEATS = [
    "kl", "maxdiff", "fdis", "sig_nbs", "lead_gfs", "spread", "overround", "logvol",
    "sin", "cos", "trail_gain", "trail_mkt",
]  # fmt: skip


def rows_for(o):
    m = o.rows.meta.reset_index(drop=True)
    pm, pi, y = o.preds["market"], o.preds["isotherm"], o.rows.y
    lm, li = metrics.log_score(pm, y), metrics.log_score(pi, y)
    mask = o.rows.mask
    kl = np.where(mask, pi * (np.log(np.clip(pi, 1e-9, 1)) - np.log(np.clip(pm, 1e-9, 1))), 0).sum(1)
    doy = m["day"].dt.dayofyear.to_numpy() / 365.25 * 2 * np.pi
    sg = np.maximum(m["sigma_nbs"].fillna(m["sigma_gfs"]).to_numpy(float), 0.5)
    df = pd.DataFrame(
        {
            "day": m["day"],
            "city": m["city"],
            "event": m["event"],
            "gain": lm - li,
            "mkt_ll": lm,
            "kl": kl,
            "maxdiff": np.abs(np.where(mask, pi - pm, 0)).max(1),
            "fdis": (m["mu_nbs"] - m["mu_gfs"]).abs().to_numpy(float) / sg,
            "sig_nbs": sg,
            "lead_gfs": m["lead_h_gfs"].fillna(24).to_numpy(float),
            "spread": m["spread"].fillna(m["spread"].median()).to_numpy(float),
            "overround": m["overround"].fillna(1).to_numpy(float),
            "logvol": np.log1p(m["cum_volume"].fillna(0).to_numpy(float)),
            "sin": np.sin(doy),
            "cos": np.cos(doy),
            "p_iso": list(pi),
            "p_mkt": list(pm),
            "y": y,
        }
    )
    # Recent performance, from days settled by D-2 only (the read for D happens on D-1 or D).
    daily = df.groupby("day")[["gain", "mkt_ll"]].mean().sort_index()
    roll = daily.rolling("30D", min_periods=5).mean()
    roll.index = roll.index + pd.Timedelta(days=2)
    trail = roll.reindex(pd.DatetimeIndex(df["day"]), method="ffill")
    df["trail_gain"] = trail["gain"].to_numpy()
    df["trail_mkt"] = trail["mkt_ll"].to_numpy()
    return df.dropna(subset=["trail_gain", "trail_mkt"]).reset_index(drop=True)


def ridge(X, y):
    mu, sd = X.mean(0), X.std(0) + 1e-9
    Z = np.column_stack([np.ones(len(X)), (X - mu) / sd])
    pen = RIDGE * np.eye(Z.shape[1])
    pen[0, 0] = 0
    b = np.linalg.solve(Z.T @ Z + pen, Z.T @ y)
    return lambda Xn: b[0] + ((Xn - mu) / sd) @ b[1:], b


def main():
    ls = dataset.load(list(CITIES))
    base = oos_predictions(ls, transformer_large_suite())
    res = {}
    for read, o in base.items():
        df = rows_for(o)
        month = df["day"].dt.to_period("M")
        months = sorted(month.unique())
        pred = np.full(len(df), np.nan)
        coefs = None
        for mo in months[WARMUP_MONTHS:]:
            tr, te = (month < mo).to_numpy(), (month == mo).to_numpy()
            f, coefs = ridge(df.loc[tr, FEATS].to_numpy(float), df.loc[tr, "gain"].to_numpy(float))
            pred[te] = f(df.loc[te, FEATS].to_numpy(float))
        ev = df[np.isfinite(pred)].copy()
        ev["pred"] = pred[np.isfinite(pred)]
        days = ev["day"].to_numpy()
        li = ev["mkt_ll"] - ev["gain"]  # isotherm log score
        gated = np.where(ev["pred"] > 0, li, ev["mkt_ll"])
        rho = spearmanr(ev["pred"], ev["gain"]).statistic
        q = pd.qcut(ev["pred"], 5, labels=False)
        res[read] = {
            "ladders": int(len(ev)),
            "from": str(ev["day"].min().date()),
            "spearman": float(rho),
            "gain_by_predicted_quintile": [float(ev["gain"][q == k].mean()) for k in range(5)],
            "share_gated_to_market": float((ev["pred"] <= 0).mean()),
            "isotherm_vs_market": {
                "diff": float(ev["gain"].mean()),
                "ci": metrics.date_bootstrap_mean(days, ev["gain"].to_numpy(), 2000),
            },
            "gated_vs_isotherm": {
                "diff": float((li - gated).mean()),
                "ci": metrics.date_bootstrap_mean(days, (li - gated).to_numpy(), 2000),
            },
            "gated_vs_market": {
                "diff": float((ev["mkt_ll"] - gated).mean()),
                "ci": metrics.date_bootstrap_mean(days, (ev["mkt_ll"] - gated).to_numpy(), 2000),
            },
            "last_coefficients": dict(
                zip(["intercept"] + FEATS, [round(float(c), 5) for c in coefs], strict=True)
            ),
        }
        # Paper P&L (taker, quarter Kelly, the §6 engine) of trading isotherm, split by predicted edge.
        sel = o.rows.meta["event"].isin(ev["event"]).to_numpy()
        sub = o.rows.take(np.flatnonzero(sel))
        qmap = dict(zip(ev["event"], q, strict=True))
        pnl = {}
        for slip in (0, 1):
            led = run(sub, o.preds["isotherm"][sel], Config("isotherm", slip=slip))
            led["q"] = led["event"].map(qmap)
            by = led.groupby("q")["pnl"].sum().reindex(range(5), fill_value=0.0)
            pnl["slip{}".format(slip)] = {
                "total": float(led["pnl"].sum()),
                "by_predicted_quintile": [round(float(x), 0) for x in by],
                "top_two_quintiles": float(by.iloc[3:].sum()),
                "bottom_three_quintiles": float(by.iloc[:3].sum()),
            }
        res[read]["paper_pnl"] = pnl
        r = res[read]
        print(
            read,
            "pnl by quintile",
            pnl["slip0"]["by_predicted_quintile"],
            "slip1",
            pnl["slip1"]["by_predicted_quintile"],
            flush=True,
        )
        print(
            "{} n={} rho {:+.3f} quintiles {} gated-iso {:+.4f} [{:+.4f}, {:+.4f}] to-market {:.0%}".format(
                read,
                r["ladders"],
                r["spearman"],
                [round(x, 3) for x in r["gain_by_predicted_quintile"]],
                r["gated_vs_isotherm"]["diff"],
                *r["gated_vs_isotherm"]["ci"],
                r["share_gated_to_market"],
            ),
            flush=True,
        )
    pathlib.Path("results/edge_model.json").write_text(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
