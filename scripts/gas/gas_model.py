#!/usr/bin/env python3
"""Gas prices (FINDINGS §42), exploration: does wholesale RBOB tell us tomorrow's AAA average better
than Kalshi's crowd does?

Forecast for day D, made at 16:00 ET on D-1 from public data only:
    AAA_D = AAA_{D-1} + delta,  delta ~ Normal(x'b, s)
    x = RBOB changes over 1, 3, 5, 10 and 20 trading days to D-1, the last two AAA changes, and the
        retail-minus-wholesale spread against its trailing 60-day mean
b by ridge regression and s from residuals, refit every day on all earlier days (walk-forward,
first forecast after 60 days of history). Ladders: strikes s_1 < ... < s_k ("above s" markets)
become buckets (-inf, s_1], (s_1, s_2], ..., (s_k, inf). The market's bucket probabilities come
from its mid prices made monotone. Scored by log score of the bucket AAA landed in, against the
market and against a log pool of market and model fitted on earlier days.

    uv run scripts/gas/gas_model.py
"""

from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import norm

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))
from isotherm import metrics  # noqa: E402

DATA = pathlib.Path("data/gas")
OUT = pathlib.Path("results/gas")
MIN_HISTORY = 60
RIDGE = 1.0
EPS = 1e-4


def aaa_series(lad):
    a = lad.groupby("day")["aaa"].first().dropna().sort_index()
    return a[~a.index.duplicated()]


def features(aaa, rb):
    """One row per target day D with x known at 16:00 ET on D-1, and the realised change."""
    rb = rb.set_index("date")["rbob"].sort_index()
    rows = []
    for d in aaa.index:
        prev = d - pd.Timedelta(days=1)
        if prev not in aaa.index:
            continue  # AAA for D-1 must be known
        r = rb[rb.index <= prev]
        if len(r) < 25:
            continue
        hist = aaa[aaa.index <= prev]
        x = {"rb{}".format(k): r.iloc[-1] - r.iloc[-1 - k] for k in (1, 3, 5, 10, 20)}
        dif = hist.diff()
        x["da1"] = dif.iloc[-1] if len(dif) > 1 and np.isfinite(dif.iloc[-1]) else 0.0
        x["da2"] = dif.iloc[-2] if len(dif) > 2 and np.isfinite(dif.iloc[-2]) else 0.0
        spread = hist - rb.reindex(hist.index, method="ffill")
        x["spread_dev"] = spread.iloc[-1] - spread.iloc[-60:].mean()
        rows.append({"day": d, "aaa_prev": hist.iloc[-1], "delta": aaa[d] - hist.iloc[-1], **x})
    return pd.DataFrame(rows).set_index("day")


def fit(X, y):
    mu, sd = X.mean(0), X.std(0) + 1e-9
    Z = np.column_stack([np.ones(len(X)), (X - mu) / sd])
    pen = RIDGE * np.eye(Z.shape[1])
    pen[0, 0] = 0
    b = np.linalg.solve(Z.T @ Z + pen, Z.T @ y)
    s = np.sqrt(np.mean((y - Z @ b) ** 2) * len(y) / max(len(y) - Z.shape[1], 1))
    return mu, sd, b, max(s, 0.002)


def predict(model, x):
    mu, sd, b, s = model
    return b[0] + ((x - mu) / sd) @ b[1:], s


def buckets(strikes, p_above):
    """Monotone P(above s_j) to bucket probabilities over (-inf, s_1], ..., (s_k, inf)."""
    q = np.minimum.accumulate(np.clip(p_above, EPS, 1 - EPS))
    p = np.concatenate([[1 - q[0]], q[:-1] - q[1:], [q[-1]]])
    p = np.clip(p, EPS, None)
    return p / p.sum()


def pool_logp(w, pm, pf, y):
    z = w[0] * np.log(pm) + w[1] * np.log(pf)
    z = z - z.max()
    return (z - np.log(np.exp(z).sum()))[y]


def pool_fit(PM, PF, Y):
    """Log-pool weights for (market, model) maximising the mean log score of the realised bucket."""
    return minimize(
        lambda w: -np.mean([pool_logp(w, pm, pf, y) for pm, pf, y in zip(PM, PF, Y, strict=True)]),
        np.array([1.0, 0.0]),
        method="Nelder-Mead",
    ).x


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    lad = pd.read_parquet(DATA / "ladders.parquet")
    rb = pd.read_parquet(DATA / "rbob.parquet")
    aaa = aaa_series(lad)
    F = features(aaa, rb)
    cols = [c for c in F.columns if c not in ("aaa_prev", "delta")]
    rows, drops = [], {"no features": 0, "too little history": 0, "no two-sided quote": 0}
    for d, g in lad.groupby("day"):
        if d not in F.index:
            drops["no features"] += 1
            continue
        past = F[F.index < d]
        if len(past) < MIN_HISTORY:
            drops["too little history"] += 1
            continue
        g = g.sort_values("strike")
        ok = g["bid"].notna() & g["ask"].notna() & (g["ask"] > g["bid"])
        if ok.sum() < 3:
            drops["no two-sided quote"] += 1
            continue
        model = fit(past[cols].to_numpy(float), past["delta"].to_numpy(float))
        m, s = predict(model, F.loc[d, cols].to_numpy(float))
        strikes = g["strike"].to_numpy(float)
        mid = np.where(ok, (g["bid"].fillna(0) + g["ask"].fillna(1)) / 2, np.nan)
        mid = pd.Series(mid).interpolate(limit_direction="both").to_numpy()
        p_mkt = buckets(strikes, mid)
        p_mod = buckets(strikes, 1 - norm.cdf((strikes - F.loc[d, "aaa_prev"] - m) / s))
        y = int(np.searchsorted(strikes, aaa[d], side="left"))  # AAA above s_j strictly for j < y
        rows.append(
            {"day": d, "y": y, "p_mkt": p_mkt, "p_mod": p_mod, "mu": m, "s": s, "delta": F.loc[d, "delta"]}
        )
    R = pd.DataFrame(rows).sort_values("day").reset_index(drop=True)
    lm = np.array([np.log(p[y]) for p, y in zip(R["p_mkt"], R["y"], strict=True)])
    lf = np.array([np.log(p[y]) for p, y in zip(R["p_mod"], R["y"], strict=True)])
    # Pool weights fit on earlier days only, refit daily from day 30 of the evaluation.
    PM, PF, Y = list(R["p_mkt"]), list(R["p_mod"]), R["y"].to_numpy()
    lp, W = np.full(len(R), np.nan), []
    for i in range(30, len(R)):
        w = pool_fit(PM[:i], PF[:i], Y[:i])
        W.append(w)
        lp[i] = pool_logp(w, PM[i], PF[i], Y[i])
    days = R["day"].to_numpy()
    sel = np.isfinite(lp)
    res = {
        "days_scored": int(len(R)),
        "first": str(R["day"].min().date()),
        "last": str(R["day"].max().date()),
        "drops": drops,
        "model_minus_market": {
            "diff": float((lf - lm).mean()),
            "ci": metrics.date_bootstrap_mean(days, lf - lm, 2000),
        },
        "pool_minus_market": {
            "diff": float((lp - lm)[sel].mean()),
            "ci": metrics.date_bootstrap_mean(days[sel], (lp - lm)[sel], 2000),
            "days": int(sel.sum()),
            "last_weights": [float(x) for x in W[-1]] if W else None,
        },
        "log_loss": {"market": float(-lm.mean()), "model": float(-lf.mean())},
        "delta_sd": float(R["delta"].std()),
        "model_sd_mean": float(R["s"].mean()),
        "mae_model_cents": float(100 * np.abs(R["delta"] - R["mu"]).mean()),
        "mae_no_change_cents": float(100 * np.abs(R["delta"]).mean()),
    }
    (OUT / "gas_model.json").write_text(json.dumps(res, indent=2, default=str))
    print(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
