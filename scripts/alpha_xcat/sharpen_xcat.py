#!/usr/bin/env python3
"""Does market sharpening (p ∝ p_market^a, FINDINGS §39) hold on Kalshi's non-weather ladders?

Reads results/alpha_xcat/ladders_raw.parquet (fetch_ladders.py). For each series and lead, every
ladder's bucket mids are normalised into the market distribution; the label is the bucket that
settled yes. Arms, all scored as log-score gain over the raw market on the later half of each
series' dates (95% date-block bootstrap CI):

  own       one exponent per series and lead, fit on that series' earlier half
  weather   a = 1.18 from the weather ladders, unchanged (no parameter fit on this data)
  pooled    one exponent per lead, fit on the earlier halves of all four series together

Plus a reliability table per series (market price bins against settle frequency, all ladders).
"""

from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from isotherm.metrics import date_bootstrap_mean  # noqa: E402

OUT = ROOT / "results" / "alpha_xcat"
EPS = 1e-3  # same probability floor as §39 and isotherm.dataset
A_WEATHER = 1.18
BINS = [0, 0.02, 0.05, 0.1, 0.2, 0.35, 0.5, 0.65, 0.8, 0.9, 1.0001]


def clean(raw: pd.DataFrame):
    """One row per (event, lead, bucket) with p_mkt; every dropped ladder counted."""
    drops, out = {}, []

    def add(s, lead, k):
        d = drops.setdefault("{} {}h".format(s, lead), {})
        d[k] = d.get(k, 0) + 1

    for (s, ev, lead), g in raw.groupby(["series", "event", "lead_h"], sort=False):
        add(s, lead, "ladders (start)")
        if not g["open_at_read"].all():
            add(s, lead, "dropped: ladder not open at read")
            continue
        b, a = g["bid"].to_numpy(float), g["ask"].to_numpy(float)
        if np.all(np.isnan(b) & np.isnan(a)):
            add(s, lead, "dropped: book empty (no quote on any bucket)")
            continue
        if np.any(np.isnan(a) | (a <= 0)):
            add(s, lead, "dropped: a bucket with no ask (one-sided book)")
            continue
        b = np.nan_to_num(b, nan=0.0)
        mid = (a + b) / 2
        S = mid.sum()
        bad = bool(S < 0.8 or S > 1.5)
        if bad:
            add(s, lead, "flagged, kept: sum of mids outside [0.8, 1.5]")
        p = np.clip(mid / S, EPS, None)
        p = p / p.sum()
        # zero-parameter repair: a bucket quoted only as "no bid, ask 1c" is dust, not half a cent
        dust = (b == 0) & (a <= 0.01)
        q = np.where(dust, 0.0, mid)
        q = np.clip(q / q.sum(), EPS, None) if q.sum() > 0 else np.full(len(q), 1 / len(q))
        q = q / q.sum()
        # second repair: price each bucket at its bid (what someone will actually pay), floored
        r = np.clip(b / b.sum(), EPS, None) if b.sum() > 0 else np.full(len(b), 1 / len(b))
        r = r / r.sum()
        add(s, lead, "ladders kept")
        out.append(
            pd.DataFrame(
                {
                    "series": s,
                    "event": ev,
                    "lead_h": lead,
                    "date": g["date"].to_numpy(),
                    "n_buckets": len(g),
                    "p_mkt": p,
                    "p_dedust": q,
                    "p_bid": r,
                    "dust": dust,
                    "y": g["y"].to_numpy(),
                    "spread": a - b,
                    "bid_zero": b == 0,
                    "S": S,
                    "bad_sum": bad,
                }
            )
        )
    return pd.concat(out, ignore_index=True), drops


def tensor(df, col="p_mkt"):
    """Padded (ladders, K) arrays of log p_mkt, mask, label index; plus per-ladder meta."""
    df = df.sort_values(["series", "event", "lead_h"]).copy()
    codes = df.groupby(["series", "event", "lead_h"], sort=False).ngroup().to_numpy()
    df["_k"] = df.groupby(codes).cumcount().to_numpy()
    n, K = codes.max() + 1, int(df["_k"].max()) + 1
    LP = np.full((n, K), -np.inf)
    LP[codes, df["_k"].to_numpy()] = np.log(df[col].to_numpy())
    Y = np.zeros(n, int)
    yy = df["y"].to_numpy() == 1
    Y[codes[yy]] = df["_k"].to_numpy()[yy]
    meta = df.groupby(codes)[["series", "event", "lead_h", "date"]].first().reset_index(drop=True)
    return LP, Y, meta


def logscore(LP, Y, a):
    s = a * LP
    mx = s.max(1, keepdims=True)
    lz = mx[:, 0] + np.log(np.exp(s - mx).sum(1))
    return s[np.arange(len(Y)), Y] - lz


def fit_a(LP, Y):
    r = minimize_scalar(lambda a: -logscore(LP, Y, a).mean(), bounds=(0.2, 4.0), method="bounded")
    return float(r.x)


def ci(dates, vals, n=2000, seed=0):
    vals = np.asarray(vals, float)
    lo, hi = date_bootstrap_mean(np.asarray(dates), vals, n=n, seed=seed)
    return {"mean": float(vals.mean()), "lo": lo, "hi": hi, "n": len(vals), "n_dates": len(set(dates))}


def reliability(df):
    rows = []
    idx = np.digitize(df["p_mkt"], BINS) - 1
    for i in range(len(BINS) - 1):
        m = idx == i
        if not m.any():
            continue
        mp, fq = float(df["p_mkt"][m].mean()), float(df["y"][m].mean())
        rows.append(
            {
                "bin": "{:.2f}-{:.2f}".format(BINS[i], min(BINS[i + 1], 1)),
                "n": int(m.sum()),
                "mean_price": mp,
                "settle_freq": fq,
                "freq_over_price": fq / mp,
            }
        )
    return rows


def evaluate(df, col):
    """Out-of-sample gains of the three sharpening arms over the market distribution in `col`."""
    LP, Y, meta = tensor(df, col)
    series = sorted(meta["series"].unique())
    res = {}
    for lead in sorted(meta["lead_h"].unique()):
        L = meta["lead_h"] == lead
        train, test = np.zeros(len(meta), bool), np.zeros(len(meta), bool)
        for s in series:
            m = L & (meta["series"] == s)
            if m.sum() < 40:
                continue
            ud = np.sort(meta.loc[m, "date"].unique())
            cut = ud[len(ud) // 2]
            train |= m & (meta["date"] < cut)
            test |= m & (meta["date"] >= cut)
        if not test.any():
            continue
        a_pool = fit_a(LP[train], Y[train])
        out = {"a_pooled": a_pool, "per_series": {}}
        for s in series + ["pooled"]:
            sm = np.ones(len(meta), bool) if s == "pooled" else (meta["series"] == s).to_numpy()
            tr, te = train & sm, test & sm
            if not te.any():
                continue
            base = logscore(LP[te], Y[te], 1.0)
            d = meta.loc[te, "date"].to_numpy()
            r = {
                "n_train": int(tr.sum()),
                "n_test": int(te.sum()),
                "train_dates": [str(meta.loc[tr, "date"].min()), str(meta.loc[tr, "date"].max())],
                "test_dates": [str(meta.loc[te, "date"].min()), str(meta.loc[te, "date"].max())],
                "a_fit_full_sample": fit_a(LP[sm & L.to_numpy()], Y[sm & L.to_numpy()]),
                "a_fit_test_half": fit_a(LP[te], Y[te]),
                "market_logloss_test": float(-base.mean()),
                "gain_weather": ci(d, logscore(LP[te], Y[te], A_WEATHER) - base),
                "gain_pooled": ci(d, logscore(LP[te], Y[te], a_pool) - base),
            }
            if s == "pooled":
                # each series' own exponent applied to its own test rows
                own = np.zeros(len(meta))
                for s2 in series:
                    m2 = (meta["series"] == s2).to_numpy()
                    if (train & m2).any() and (test & m2).any():
                        a2 = out["per_series"][s2]["a_own"]
                        own[test & m2] = logscore(LP[test & m2], Y[test & m2], a2)
                r["gain_own"] = ci(d, own[te] - base)
            else:
                r["a_own"] = fit_a(LP[tr], Y[tr])
                r["gain_own"] = ci(d, logscore(LP[te], Y[te], r["a_own"]) - base)
            out["per_series"][s] = r
        res["{}h".format(int(lead))] = out
    return res


def main():
    raw = pd.read_parquet(OUT / "ladders_raw.parquet")
    df, drops = clean(raw)
    series = sorted(df["series"].unique())
    good = df[~df["bad_sum"]]
    res = {
        "filters": drops,
        "results": evaluate(df, "p_mkt"),
        "results_dedust": evaluate(df, "p_dedust"),
        "results_sum_ok_only": evaluate(good, "p_mkt"),
        "results_bid": evaluate(df, "p_bid"),
        "reliability": {},
        "reliability_dedust": {},
        "describe": {},
    }
    # zero-parameter dedust repair against the raw mids, same test halves are not needed: all ladders
    for lead in sorted(df["lead_h"].unique()):
        for s in series:
            sub = df[(df["series"] == s) & (df["lead_h"] == lead)]
            if len(sub):
                key = "{} {}h".format(s, int(lead))
                res["reliability"][key] = reliability(sub)
                res["reliability_dedust"][key] = reliability(sub.assign(p_mkt=sub["p_dedust"]))
                g = sub.groupby("event")
                w = sub[sub["y"] == 1]
                res["describe"][key] = {
                    "ladders": int(g.ngroups),
                    "buckets_median": float(g.size().median()),
                    "share_buckets_bid_zero": float(sub["bid_zero"].mean()),
                    "share_buckets_dust": float(sub["dust"].mean()),
                    "dust_mass_median": float(g.apply(lambda x: x.loc[x["dust"], "p_mkt"].sum()).median()),
                    "winner_was_dust": int(w["dust"].sum()),
                    "median_spread_where_bid_positive": float(sub.loc[~sub["bid_zero"], "spread"].median()),
                    "sum_mids_median": float(g["S"].first().median()),
                    "bad_sum_ladders": int(g["bad_sum"].first().sum()),
                    "dedust_minus_mid_logscore": ci(
                        w["date"].to_numpy(), np.log(w["p_dedust"].to_numpy()) - np.log(w["p_mkt"].to_numpy())
                    ),
                    "bid_minus_mid_logscore": ci(
                        w["date"].to_numpy(), np.log(w["p_bid"].to_numpy()) - np.log(w["p_mkt"].to_numpy())
                    ),
                    "dates": [str(sub["date"].min()), str(sub["date"].max())],
                }
    (OUT / "sharpen_xcat.json").write_text(json.dumps(res, indent=1))
    df.to_parquet(OUT / "ladders_clean.parquet", index=False)

    def f(r):
        return "{:+.4f} [{:+.4f}, {:+.4f}]".format(r["mean"], r["lo"], r["hi"])

    for var in ("results", "results_dedust", "results_sum_ok_only", "results_bid"):
        for lead, out in res[var].items():
            print("== {} lead {}  pooled a = {:.3f}".format(var, lead, out["a_pooled"]))
            for s, r in out["per_series"].items():
                print(
                    "{:12s} {:4d}/{:4d} a={} own {} w1.18 {} pool {} (a full {:.2f}, test {:.2f})".format(
                        s,
                        r["n_train"],
                        r["n_test"],
                        "{:.3f}".format(r["a_own"]) if "a_own" in r else "  -  ",
                        f(r["gain_own"]),
                        f(r["gain_weather"]),
                        f(r["gain_pooled"]),
                        r["a_fit_full_sample"],
                        r["a_fit_test_half"],
                    )
                )
    for rel in ("reliability", "reliability_dedust"):
        for k, v in res[rel].items():
            if not k.endswith(" 24h"):
                print(rel, k, [(r["bin"], r["n"], round(r["freq_over_price"], 2)) for r in v])
    for k, v in res["describe"].items():
        print(k, {a: b for a, b in v.items() if a != "dates"})


if __name__ == "__main__":
    main()
