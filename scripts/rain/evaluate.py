#!/usr/bin/env python3
"""Will it rain today: a calibrated PoP model against Kalshi's rain markets (FINDINGS §43 draft).

Model: logistic regression on point-in-time NBM and GFS MOS PoP features (max, mean, union of
6-hour PoP over the CLI day, 12-hour PoP, amounts, coverage, season), one per read, trained on
station-days of CLI precip > 0 (trace = dry). Walk-forward: quarterly refits from 2021Q4, a 2-day
embargo, training rows strictly before the test quarter. A gradient-boosted alternative is scored
on non-market stations only, to choose between them without looking at the market.

Comparisons, all out of sample, per market (binary log score and Brier, gain = market - model):
    (a) market mid, two-sided books only
    (b) the market at the price in [bid, ask] closest to the model (clip(model, bid, ask))
    (c) a logistic stack of logit(mid) and logit(model), fit on market rows of earlier dates only
95% CIs resample dates (isotherm.metrics.date_bootstrap_mean).

    uv run scripts/rain/evaluate.py            # results/rain/rain_eval.json
    uv run scripts/rain/evaluate.py --cached   # reuse the walk-forward predictions
"""

from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd
from common import DATA, RESULTS
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from isotherm import metrics
from isotherm.backtest import kalshi_fee

LAST_LABEL_DAY = pd.Timestamp("2026-10-07")  # later CLI rows are same-day partial reports
EMBARGO = pd.Timedelta(days=2)
FIRST_FOLD = pd.Timestamp("2021-10-01")
MAX_TRAIN = 300_000
EPS = 0.005
RAW = [
    f"{m}_{c}"
    for m in ("nbm", "gfs")
    for c in ("max06", "mean06", "any06", "max12", "n06", "q06", "q12", "lead")
]


def logit(p):
    p = np.clip(np.asarray(p, float), 0.01, 0.99)
    return np.log(p / (1 - p))


def design(df: pd.DataFrame) -> np.ndarray:
    cols = []
    for m, o in (("nbm", "gfs"), ("gfs", "nbm")):
        miss = df[m + "_any06"].isna().to_numpy()
        for c in ("any06", "max06", "mean06", "max12"):
            v = df[m + "_" + c].fillna(df[o + "_" + c]).fillna(0.1)
            cols.append(logit(v))
        q6, q12 = df[m + "_q06"].fillna(0).to_numpy(float), df[m + "_q12"].fillna(0).to_numpy(float)
        cols += [np.log1p(q6), np.log1p(q12)] if m == "nbm" else [q6, q12]
        cols += [df[m + "_n06"].fillna(0).to_numpy(float), miss.astype(float)]
    t = 2 * np.pi * df["day"].dt.dayofyear.to_numpy() / 365.25
    cols += [np.sin(t), np.cos(t), np.sin(2 * t), np.cos(2 * t)]
    return np.column_stack(cols)


def fit(kind: str, X, y):
    if kind == "logit":
        m = make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=1000))
    else:
        m = HistGradientBoostingClassifier(
            max_iter=300, learning_rate=0.05, max_leaf_nodes=31, random_state=0
        )
    return m.fit(X, y)


def walk_forward(feat: pd.DataFrame) -> pd.DataFrame:
    """OOS predictions for every station-day-read from FIRST_FOLD, both model kinds."""
    feat = feat[feat[["nbm_any06", "gfs_any06"]].notna().any(axis=1)].copy()
    feat["wett"] = np.where(feat["wet"].notna(), ((feat["wet"] > 0) | feat["trace"]).astype(float), np.nan)
    lab = feat["wet"].notna() & (feat["day"] <= LAST_LABEL_DAY)
    rng = np.random.default_rng(0)
    out = []
    qs = pd.date_range(FIRST_FOLD, feat["day"].max() + pd.Timedelta(days=1), freq="QS")
    for read in ("d1_16", "d0_08"):
        fr = feat[feat["read"] == read]
        lr = lab[fr.index]
        for q0 in qs:
            q1 = q0 + pd.offsets.QuarterBegin(1, startingMonth=1)
            tr = fr[lr & (fr["day"] < q0 - EMBARGO)]
            te = fr[(fr["day"] >= q0) & (fr["day"] < q1)]
            if te.empty:
                continue
            if len(tr) > MAX_TRAIN:
                tr = tr.iloc[np.sort(rng.choice(len(tr), MAX_TRAIN, replace=False))]
            Xt, yt, Xe = design(tr), tr["wet"].to_numpy(int), design(te)
            o = te[["station", "day", "read", "wet", "wett", "precip", "trace"]].copy()
            for kind in ("logit", "gbm"):
                o["p_" + kind] = fit(kind, Xt, yt).predict_proba(Xe)[:, 1]
            # NYC-only series settles a trace as YES (label check): same model, that target
            o["p_logit_t"] = fit("logit", Xt, tr["wett"].to_numpy(int)).predict_proba(Xe)[:, 1]
            o["p_nbm_raw"] = te["nbm_any06"].to_numpy()
            o["n_train"] = len(tr)
            out.append(o)
            print("  {} {} train {} test {}".format(read, q0.date(), len(tr), len(te)), flush=True)
    return pd.concat(out, ignore_index=True)


# ------------------------------------------------------------------ scoring


def ll(p, y):
    p = np.clip(p, EPS, 1 - EPS)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def bs(p, y):
    return (p - y) ** 2


def gain(d: pd.DataFrame, base: str, alt: str, score=ll) -> dict:
    """Mean of score(base) - score(alt): positive means `alt` is better. 95% date-block CI."""
    v = score(d[base].to_numpy(), d["y"].to_numpy()) - score(d[alt].to_numpy(), d["y"].to_numpy())
    if len(v) < 5:
        return {"n": int(len(v))}
    ci = metrics.date_bootstrap_mean(d["day"].to_numpy(), v)
    return {"n": int(len(v)), "days": int(d["day"].nunique()), "mean": float(v.mean()), "ci": ci}


def stack(m: pd.DataFrame) -> pd.Series:
    """Logistic stack of logit(mid) and logit(model), per series and read, fit on earlier dates."""
    out = pd.Series(np.nan, index=m.index)
    for _key, g in m.groupby(["series", "read"]):
        g = g.sort_values("day")
        X = np.column_stack([logit(g["mid"]), logit(g["p_model"])])
        y = g["y"].to_numpy()
        for d in g["day"].unique():
            tr = (g["day"] < d - EMBARGO).to_numpy()
            if tr.sum() < 100 or len(set(y[tr])) < 2:
                continue
            te = (g["day"] == d).to_numpy()
            lr = LogisticRegression(C=10.0).fit(X[tr], y[tr])
            out[g.index[te]] = lr.predict_proba(X[te])[:, 1]
    return out


def pnl(d: pd.DataFrame) -> dict:
    """Exploratory: 100 contracts at the touch when the model clears the price by more than the fee."""
    p, b, a, y = (d[c].to_numpy() for c in ("p_model", "bid", "ask", "y"))
    fy, fn = kalshi_fee(a, 100) / 100, kalshi_fee(1 - b, 100) / 100
    buy_y, buy_n = p - a > fy, (b - p > fn) & ~(p - a > fy)
    r = np.where(buy_y, y - a - fy, np.where(buy_n, (1 - y) - (1 - b) - fn, 0.0))
    t = buy_y | buy_n
    out = {"n_rows": int(len(d)), "trades": int(t.sum()), "yes": int(buy_y.sum()), "no": int(buy_n.sum())}
    if t.sum() >= 5:
        out["pnl_per_contract_total"] = float(r[t].sum())
        out["mean_per_trade"] = float(r[t].mean())
        out["ci_per_trade"] = metrics.date_bootstrap_mean(d["day"].to_numpy()[t], r[t])
    return out


def calib(p, y) -> dict:
    return {"ece": metrics.ece_debiased(p, y, bins=10), "bins": metrics.reliability(p, y, bins=10)}


def main():
    feat = pd.read_parquet(DATA / "features.parquet")
    mk = pd.read_parquet(DATA / "markets.parquet")
    res: dict = {}

    # ---- market filters
    counts = {}
    m = mk[mk["read"].notna()].copy()
    for (s, r), g in m.groupby(["series", "read"]):
        has_b = g["bid"].fillna(0) > 0
        has_a = g["ask"].fillna(1) < 1
        counts["{}/{}".format(s, r)] = {
            "markets": int(len(g)),
            "closed_before_read": int(g["closed_before_read"].sum()),
            "candle_fetch_failed": int((~g["candles_ok"].astype(bool)).sum()),
            "no_quote_yet": int((~g["closed_before_read"] & g["candle_ts"].isna()).sum()),
            "empty_book": int((~g["closed_before_read"] & g["candle_ts"].notna() & ~has_b & ~has_a).sum()),
            "one_sided": int((~g["closed_before_read"] & (has_b ^ has_a)).sum()),
            "two_sided": int((~g["closed_before_read"] & has_b & has_a).sum()),
        }
    unpriced = mk[mk["read"].isna()]
    res["market_counts"] = counts
    res["markets_unscored"] = {
        "no_result_or_station": int(len(unpriced)),
        "tickers": unpriced["ticker"].tolist()[:20],
    }

    # ---- label check: Kalshi result vs CLI precip > 0
    lab = mk[mk["threshold"] == 0].drop_duplicates("ticker").dropna(subset=["station", "y"])
    lab = lab.merge(
        feat.drop_duplicates(["station", "day"])[["station", "day", "precip", "trace", "wet"]].assign(
            wett=lambda f: np.where(f["wet"].notna(), ((f["wet"] > 0) | f["trace"]).astype(float), np.nan)
        ),
        on=["station", "day"],
        how="left",
    )
    lc = {}
    for s, g in lab.groupby("series"):
        k = g[g["wet"].notna()]
        tr = k[k["trace"]]
        bad = k[k["wet"] != k["y"]]
        lc[s] = {
            "markets": int(len(g)),
            "cli_missing": int(g["wet"].isna().sum()),
            "agree_trace_dry": int((k["wet"] == k["y"]).sum()),
            "agree_rate_trace_dry": float((k["wet"] == k["y"]).mean()),
            "agree_rate_trace_wet": float((k["wett"] == k["y"]).mean()),
            "trace_days": int(len(tr)),
            "trace_settled_no": int((tr["y"] == 0).sum()),
            "non_trace_disagreements": int(((k["wet"] != k["y"]) & ~k["trace"].astype(bool)).sum()),
            "disagreements": bad[["ticker", "precip", "trace", "y"]].astype(str).values.tolist()[:40],
        }
    res["label_check"] = lc

    # ---- walk-forward model
    f_oos = DATA / "oos_preds.parquet"
    if "--cached" in sys.argv and f_oos.exists():
        wf = pd.read_parquet(f_oos)
    else:
        wf = walk_forward(feat)
        wf.to_parquet(f_oos, index=False)
    mst = set(mk["station"].dropna())
    sel = wf[wf["wet"].notna() & ~wf["station"].isin(mst) & (wf["day"] <= LAST_LABEL_DAY)]
    choose = {}
    for read, g in sel.groupby("read"):
        y = g["wet"].to_numpy()
        choose[read] = {
            k: float(ll(g[k].to_numpy(), y).mean()) for k in ("p_logit", "p_gbm", "p_nbm_raw")
        } | {"n": int(len(g)), "stations": int(g["station"].nunique())}
    res["model_selection_non_market_stations"] = choose
    gbm_gain = np.mean([choose[r]["p_logit"] - choose[r]["p_gbm"] for r in choose])
    kind = "p_gbm" if gbm_gain > 0.005 else "p_logit"  # GBM only if clearly better (> 0.005 nats)
    res["model_used"] = kind

    # ---- join to markets (two-sided books)
    tw = m[~m["closed_before_read"] & (m["bid"].fillna(0) > 0) & (m["ask"].fillna(1) < 1)].copy()
    tw = tw.merge(
        wf[["station", "day", "read", kind, "p_logit_t", "p_nbm_raw", "trace"]],
        on=["station", "day", "read"],
        how="left",
    )
    # The label each series settles on (label check): KXRAIN trace = NO, KXRAINNYC trace = YES
    tw["p_model"] = np.where(tw["series"] == "KXRAINNYC", tw["p_logit_t"], tw[kind])
    res["label_by_series"] = {"KXRAIN": "precip > 0, trace = no", "KXRAINNYC": "precip > 0 or trace"}
    res["two_sided_without_model"] = int(tw["p_model"].isna().sum())
    tw = tw.dropna(subset=["p_model"]).reset_index(drop=True)
    tw["y"] = tw["y"].astype(float)
    tw["mid"] = (tw["bid"] + tw["ask"]) / 2
    tw["spread"] = tw["ask"] - tw["bid"]
    tw["p_clip"] = np.clip(tw["p_model"], tw["bid"], tw["ask"])
    tw["p_stack"] = stack(tw)
    tw.to_parquet(DATA / "scored.parquet", index=False)

    def block(d: pd.DataFrame) -> dict:
        o = {
            "n": int(len(d)),
            "days": int(d["day"].nunique()),
            "rain_rate": float(d["y"].mean()),
            "median_spread": float(d["spread"].median()),
            "mean_mid": float(d["mid"].mean()),
            "mean_model": float(d["p_model"].mean()),
            "trace_days": int(d["trace"].fillna(False).astype(bool).sum()),
            "trace_mean_mid": float(d.loc[d["trace"].fillna(False).astype(bool), "mid"].mean()),
            "trace_mean_model": float(d.loc[d["trace"].fillna(False).astype(bool), "p_model"].mean()),
            "log_market": float(ll(d["mid"], d["y"]).mean()),
            "log_model": float(ll(d["p_model"], d["y"]).mean()),
            "a_model_vs_mid_log": gain(d, "mid", "p_model"),
            "a_model_vs_mid_brier": gain(d, "mid", "p_model", bs),
            "b_model_vs_clip_log": gain(d, "p_clip", "p_model"),
            "b_model_vs_clip_brier": gain(d, "p_clip", "p_model", bs),
            "nbm_raw_vs_mid_log": gain(d.dropna(subset=["p_nbm_raw"]), "mid", "p_nbm_raw"),
        }
        tight = d[d["spread"] <= 0.05]
        o["a_tight_spread_le5c_log"] = gain(tight, "mid", "p_model")
        s = d.dropna(subset=["p_stack"])
        o["c_stack_vs_mid_log"] = gain(s, "mid", "p_stack")
        o["c_stack_vs_mid_brier"] = gain(s, "mid", "p_stack", bs)
        return o

    tables, cal, cities, years, money = {}, {}, {}, {}, {}
    for (s, r), d in tw.groupby(["series", "read"]):
        key = "{}/{}".format(s, r)
        tables[key] = block(d)
        cal[key] = {"market": calib(d["mid"].to_numpy(), d["y"].to_numpy())} | {
            "model": calib(d["p_model"].to_numpy(), d["y"].to_numpy())
        }
        money[key] = pnl(d)
        if s == "KXRAIN":
            years[key] = {
                str(mo): {"n": int(len(g)), "model_vs_mid_log": gain(g, "mid", "p_model")}
                for mo, g in d.groupby(d["day"].dt.to_period("M"))
            }
            cities[key] = {
                c: {"n": int(len(g)), "model_vs_mid_log": gain(g, "mid", "p_model")}
                for c, g in d.groupby("city")
                if len(g) >= 30
            }
        else:
            years[key] = {
                str(yr): {"n": int(len(g)), "model_vs_mid_log": gain(g, "mid", "p_model")}
                for yr, g in d.groupby(d["day"].dt.year)
            }
    res["tables"] = tables
    res["calibration"] = cal
    res["by_city"] = cities
    res["by_period"] = years  # NYC series by year, KXRAIN by month
    res["pnl_exploratory"] = money
    stk = {}
    for r, g in tw.dropna(subset=["p_stack"]).groupby("read"):
        X = np.column_stack([logit(g["mid"]), logit(g["p_model"])])
        lr = LogisticRegression(C=10.0).fit(X, g["y"])
        stk[r] = {"coef_mid": float(lr.coef_[0][0]), "coef_model": float(lr.coef_[0][1]), "n": int(len(g))}
    res["stack_weights_all_rows_descriptive"] = stk
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "rain_eval.json").write_text(json.dumps(res, indent=1, default=str))
    print(
        json.dumps(
            {k: res[k] for k in ("market_counts", "label_check", "model_selection_non_market_stations")},
            indent=1,
        )
    )
    for k, v in tables.items():
        print(k, json.dumps(v))


if __name__ == "__main__":
    main()
