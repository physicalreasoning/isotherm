#!/usr/bin/env python3
"""Market-structure recalibration of Kalshi weather ladders, walk-forward, market-only.

Every arm is a conditional logit over the buckets of one ladder:
    score_i = log p_mkt_i * (a0 + a . z_ladder) + b . x_bucket ;  p = softmax(score)
fit per read time on ladders strictly before each test quarter (2-day embargo) and scored on the
quarter. No forecast, observation or model output enters. The market itself is a0 = 1, rest 0.

Arms (nested where it matters):
  temper        a0 only: one global confidence correction
  temper_state  + ladder state z: overround, median spread, log volume, one-sided share,
                bad_sum flag, entropy of the market distribution
  flb           temper_state + bucket shape x: tail-bucket dummy, (log p)^2, one-sided bucket,
                bucket spread
  flow          temper + per-bucket order flow: flow_3, flow_12, bigflow, last-print minus mid,
                log hours since last print (rows with trades only: 7 cities from 2023-07)
  flow_state    temper_state + the flow features
Zero-parameter normalisations (power, additive) are scored on the same rows for comparison.

Splits: dev = test quarters 2024Q1..2025Q4; holdout = 2026Q1..2026-10-04 on the seven scored
cities, plus the twelve newer cities (2026) scored with parameters fit on the seven only.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from common import CITIES, EPS, OUT, READS, ci, fmt
from scipy.optimize import minimize

STATE = ["z_over", "z_spread", "z_vol", "z_onesided", "z_badsum", "z_entropy"]
FLB = ["x_tail", "x_lp2", "x_onesided", "x_spread"]
FLOW = ["x_flow3", "x_flow12", "x_bigflow", "x_lastdev", "x_stale"]
ARMS = {
    "temper": ([], []),
    "temper_state": (STATE, []),
    "flb": (STATE, FLB),
    "flow": ([], FLOW),
    "flow_state": (STATE, FLOW),
    "flow_dir": ([], ["x_flow3", "x_flow12", "x_bigflow"]),
    "flow_stale": ([], ["x_lastdev", "x_stale"]),
}
EMBARGO = pd.Timedelta(days=2)
L2 = 1e-3


def prep(df):
    df = df.copy()
    lp = np.log(df["p_mkt"].to_numpy())
    df["lp"] = lp
    df["z_over"] = df["S"] - 1
    df["z_spread"] = df["lad_spread"]
    df["z_vol"] = df["lad_vol"]
    df["z_onesided"] = df["lad_onesided"]
    df["z_badsum"] = df["bad_sum"].astype(float)
    df["z_entropy"] = df["lad_entropy"]
    df["x_tail"] = df["tail"].astype(float)
    df["x_lp2"] = lp**2 / 10
    df["x_onesided"] = (~df["two_sided"]).astype(float)
    df["x_spread"] = df["spread"]
    df["x_flow3"] = df["flow_3"].fillna(0) * (df["lvol_3"].fillna(0) > 0)
    df["x_flow12"] = df["flow_12"].fillna(0)
    df["x_bigflow"] = df["bigflow"].fillna(0)
    df["x_lastdev"] = (df["last_px"] - df["mid"]).fillna(0)
    df["x_stale"] = np.log1p(df["stale_h"].fillna(24 * 7).clip(upper=24 * 7))
    df["has_flow"] = df["has_trades"].notna()
    return df


def tensor(df, cols_z, cols_x, K=8):
    """Padded arrays: F[n, K, d] with features [lp, lp*z..., x...], mask, y index, ladder meta."""
    g = df.sort_values(["event", "read", "k"])
    keys = g[["event", "read"]].drop_duplicates()
    lad = pd.MultiIndex.from_frame(g[["event", "read"]])
    codes = pd.factorize(lad)[0]
    n = codes.max() + 1
    k = g["k"].to_numpy()
    d = 1 + len(cols_z) + len(cols_x)
    F = np.zeros((n, K, d))
    M = np.zeros((n, K), bool)
    lp = g["lp"].to_numpy()
    F[codes, k, 0] = lp
    for j, c in enumerate(cols_z):
        F[codes, k, 1 + j] = lp * g[c].to_numpy()
    for j, c in enumerate(cols_x):
        F[codes, k, 1 + len(cols_z) + j] = g[c].to_numpy()
    M[codes, k] = True
    Y = np.zeros(n, int)
    yy = g["y"].to_numpy() == 1
    Y[codes[yy]] = k[yy]
    first = g.groupby(codes).first()
    return F, M, Y, first.reset_index(drop=True)


def nll(theta, F, M, Y, prior):
    s = F @ theta
    s = np.where(M, s, -np.inf)
    mx = s.max(1, keepdims=True)
    e = np.exp(s - mx)
    z = e.sum(1, keepdims=True)
    p = e / z
    ly = s[np.arange(len(Y)), Y] - mx[:, 0] - np.log(z[:, 0])
    f_y = F[np.arange(len(Y)), Y]
    ef = (p[..., None] * F).sum(1)
    n = len(Y)
    loss = -ly.mean() + L2 * ((theta - prior) ** 2).sum()
    grad = -(f_y - ef).mean(0) + 2 * L2 * (theta - prior)
    return loss, grad


def predict(theta, F, M):
    s = np.where(M, F @ theta, -np.inf)
    s = s - s.max(1, keepdims=True)
    p = np.exp(s)
    p = p / p.sum(1, keepdims=True)
    p = np.where(M, np.clip(p, EPS, None), 0)
    return p / p.sum(1, keepdims=True)


def standardise(tr, te, cols):
    for c in cols:
        m, s = tr[c].mean(), tr[c].std()
        s = s if s > 1e-6 else 1.0
        tr[c] = (tr[c] - m) / s
        te[c] = (te[c] - m) / s
    return tr, te


def fit_eval(train, test, cz, cx):
    train, test = train.copy(), test.copy()
    train, test = standardise(train, test, cz + [c for c in cx if c not in ("x_tail", "x_onesided")])
    F, M, Y, _ = tensor(train, cz, cx)
    prior = np.zeros(F.shape[2])
    prior[0] = 1.0
    r = minimize(nll, prior.copy(), args=(F, M, Y, prior), jac=True, method="L-BFGS-B")
    Ft, Mt, Yt, meta = tensor(test, cz, cx)
    p = predict(r.x, Ft, Mt)
    pm = predict(prior, Ft, Mt)
    ls = np.log(p[np.arange(len(Yt)), Yt])
    lm = np.log(pm[np.arange(len(Yt)), Yt])
    # Brier over buckets (multi-category), lower is better; report market minus model (gain)
    oh = np.zeros_like(p)
    oh[np.arange(len(Yt)), Yt] = 1
    bm = (((pm - oh) ** 2) * Mt).sum(1)
    bs = (((p - oh) ** 2) * Mt).sum(1)
    meta = meta.assign(gain=ls - lm, brier_gain=bm - bs, ll_mkt=lm)
    return meta, r.x


def zero_param(df):
    """Alternative de-overrounding of the same mids: power and additive, vs multiplicative."""
    out = []
    for (ev, rd), g in df.groupby(["event", "read"], sort=False):
        m = np.clip(g["mid"].to_numpy(), 1e-4, None)
        y = g["y"].to_numpy() == 1
        pm = g["p_mkt"].to_numpy()
        lo, hi = 0.2, 5.0
        for _ in range(50):
            k = (lo + hi) / 2
            if (m**k).sum() > 1:
                lo = k
            else:
                hi = k
        pw = np.clip(m**k, EPS, None)
        pw /= pw.sum()
        ad = np.clip(m - (m.sum() - 1) / len(m), EPS, None)
        ad /= ad.sum()
        out.append((ev, rd, np.log(pw[y][0]) - np.log(pm[y][0]), np.log(ad[y][0]) - np.log(pm[y][0])))
    return pd.DataFrame(out, columns=["event", "read", "power", "additive"])


def quarters(start, end):
    q = pd.period_range(start, end, freq="Q")
    return [(p.start_time, min(p.end_time, pd.Timestamp(end))) for p in q]


def main():
    df = prep(pd.read_parquet(OUT / "weather_long.parquet"))
    seven = df[df["city"].isin(list(CITIES))]
    twelve = df[~df["city"].isin(list(CITIES))]
    results = {"dev": {}, "holdout7": {}, "holdout12": {}, "params": {}}
    rows = {"dev": [], "holdout7": [], "holdout12": []}
    folds = quarters("2024-01-01", "2026-10-04")
    for read in READS:
        s7 = seven[seven["read"] == read]
        for arm, (cz, cx) in ARMS.items():
            for qs, qe in folds:
                tr = s7[s7["day"] < qs - EMBARGO]
                te = s7[(s7["day"] >= qs) & (s7["day"] <= qe)]
                if "flow" in arm:
                    tr = tr[tr["has_flow"] & (tr["day"] >= "2023-07-01")]
                    te = te[te["has_flow"]]
                if te.empty or tr.empty:
                    continue
                meta, th = fit_eval(tr, te, cz, cx)
                split = "dev" if qs < pd.Timestamp("2026-01-01") else "holdout7"
                rows[split].append(meta.assign(arm=arm, read=read))
                results["params"]["{}|{}|{}".format(read, arm, qs.date())] = [float(x) for x in th]
                if qs == pd.Timestamp("2026-01-01") and "flow" not in arm:
                    # parameters frozen at 2026-01-01, fit on the seven cities only -> twelve new cities
                    t12 = twelve[twelve["read"] == read]
                    m12, _ = fit_eval(tr, t12, cz, cx)
                    rows["holdout12"].append(m12.assign(arm=arm, read=read))
            print(read, arm, flush=True)
    # zero-parameter normalisations on all seven-city rows from 2024 (nothing is fit)
    zp = zero_param(seven[seven["day"] >= "2024-01-01"]).merge(
        seven.groupby(["event", "read"]).first()[["day"]].reset_index(), on=["event", "read"]
    )
    for split, R in rows.items():
        if not R:
            continue
        R = pd.concat(R, ignore_index=True)
        R.to_parquet(OUT / "weather_oos_{}.parquet".format(split), index=False)
        for (arm, read), g in R.groupby(["arm", "read"]):
            results[split]["{}|{}".format(arm, read)] = {
                "logscore_gain": ci(g["day"], g["gain"]),
                "brier_gain": ci(g["day"], g["brier_gain"]),
            }
        # identical-rows comparison: flow arms vs temper/temper_state on the same ladders
        if split != "holdout12":
            for read in READS:
                g = R[R["read"] == read].pivot_table(index=["event", "day"], columns="arm", values="gain")
                g = g.dropna()
                for a_, b_ in [
                    ("flow", "temper"),
                    ("flow_dir", "temper"),
                    ("flow_stale", "temper"),
                    ("flow_state", "temper_state"),
                    ("flb", "temper_state"),
                    ("temper_state", "temper"),
                ]:
                    if a_ in g and b_ in g:
                        d = g[a_] - g[b_]
                        results[split]["{}-minus-{}|{}".format(a_, b_, read)] = {
                            "logscore_gain": ci(d.index.get_level_values("day"), d.to_numpy())
                        }
    for split, lo, hi in [("dev", "2024-01-01", "2025-12-31"), ("holdout7", "2026-01-01", "2026-10-04")]:
        z = zp[(zp["day"] >= lo) & (zp["day"] <= hi)]
        for read in READS:
            g = z[z["read"] == read]
            for c in ["power", "additive"]:
                results[split]["{}|{}".format(c, read)] = {"logscore_gain": ci(g["day"], g[c])}
    (OUT / "weather_signals.json").write_text(json.dumps(results, indent=1))
    for split in ["dev", "holdout7", "holdout12"]:
        print("\n==", split)
        for k, v in sorted(results[split].items()):
            print("{:40s} {}  n={}".format(k, fmt(v["logscore_gain"]), v["logscore_gain"]["n"]))


if __name__ == "__main__":
    main()
