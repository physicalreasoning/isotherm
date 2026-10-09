#!/usr/bin/env python3
"""Prediction-market benchmark, step 2: baselines and protocol (docs/research/benchmark_plan.md).

Every event becomes one forecasting problem at each lead before close (24 h, 6 h, 1 h):
  partition ladders   mutually exclusive ranges, exactly one settles YES   -> one bucket index
  threshold ladders   "above x" strikes only (gas, jobless claims, CPI)    -> buckets between strikes
  binaries            independent yes/no markets (KXRAIN, one per city)    -> one yes/no each
Market probabilities come from the book at the lead; a problem needs at least two two-sided quotes.

Baselines, each scored by log score of the realised outcome against the mid market:
  bid      every bucket priced at its bid (floored at 0.5c), renormalised (§41)
  sharp    the mid market raised to one exponent per series and lead, fit on earlier months
  outside  financial, commodity and crypto series only: lognormal from the hourly price at the read
           and trailing 20-day volatility, no drift (free Yahoo data, point in time)
  pool     log pool of mid and outside, weights fit on earlier months
Walk-forward by month (fits on earlier months only, 3 months of warm-up). 95% date-block CIs.

    uv run scripts/bench/evaluate.py
"""

from __future__ import annotations

import json
import pathlib
import sys
import urllib.request

import numpy as np
import pandas as pd
from scipy.optimize import minimize, minimize_scalar
from scipy.stats import norm

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))
from isotherm import metrics  # noqa: E402

RAW = pathlib.Path("data/bench/raw")
OUTSIDE = pathlib.Path("data/bench/outside")
RESULTS = pathlib.Path("results/bench")
LEADS = ("24h", "6h", "1h")
EPS = 1e-4
BID_FLOOR = 0.005
WARMUP = 3
SYMBOL = {
    "KXINX": "^GSPC",
    "KXNASDAQ100": "^NDX",
    "KXEURUSD": "EURUSD=X",
    "KXUSDJPY": "JPY=X",
    "KXWTI": "CL=F",
    "KXBTC": "BTC-USD",
}


# ----------------------------------------------------------------------------- problems


def interval(st, fl, cp):
    """Continuous [lo, hi) for any numeric strike (weather uses it for ordering only)."""
    if st == "less":
        return -np.inf, cp
    if st == "greater":
        return fl, np.inf
    if st == "between":
        return fl, cp
    return None


def problems(series, df):
    """One row per (event, lead): kind, intervals, mid, bid, ask, realised outcome."""
    out = []
    for ev, g in df.groupby("event"):
        g = g[g["result"].notna()]
        if g.empty:
            continue
        sts = set(g["strike_type"].dropna())
        kind = "binary" if series == "KXRAIN" else ("threshold" if sts <= {"greater"} else "partition")
        iv = [interval(s, f, c) for s, f, c in zip(g["strike_type"], g["floor"], g["cap"], strict=True)]
        if any(x is None for x in iv):
            continue
        g = g.assign(lo=[a for a, _ in iv], hi=[b for _, b in iv]).sort_values(["lo", "hi"])
        if kind == "partition" and g["result"].sum() != 1:
            continue
        day = (
            pd.to_datetime(g["close_ts"].max(), unit="s", utc=True).tz_convert("America/New_York").normalize()
        )
        for lead in LEADS:
            bid = g["bid_" + lead].to_numpy(float)
            ask = g["ask_" + lead].to_numpy(float)
            two = np.isfinite(bid) & np.isfinite(ask) & (bid > 0) & (ask < 1) & (ask > bid)
            if two.sum() < (1 if kind == "binary" else 2):
                continue
            bid = np.nan_to_num(bid, nan=0.0)
            ask = np.nan_to_num(ask, nan=1.0)
            out.append(
                {
                    "series": series,
                    "event": ev,
                    "lead": lead,
                    "day": day.tz_localize(None),
                    "read_ts": int(g["close_ts"].max()) - {"24h": 86400, "6h": 21600, "1h": 3600}[lead],
                    "kind": kind,
                    "lo": g["lo"].to_numpy(float),
                    "hi": g["hi"].to_numpy(float),
                    "bid": bid,
                    "ask": ask,
                    "two": two,
                    "y": g["result"].to_numpy(int),
                }
            )
    return out


def to_buckets(p_above):
    q = np.minimum.accumulate(np.clip(p_above, EPS, 1 - EPS))
    p = np.concatenate([[1 - q[0]], q[:-1] - q[1:], [q[-1]]])
    p = np.clip(p, EPS, None)
    return p / p.sum()


def market(pr, use="mid"):
    """Distribution (partition, threshold) or per-market probabilities (binary) from the book."""
    px = (pr["bid"] + pr["ask"]) / 2 if use == "mid" else np.maximum(pr["bid"], BID_FLOOR)
    if pr["kind"] == "binary":
        return np.clip(px, EPS, 1 - EPS)
    if pr["kind"] == "threshold":
        return to_buckets(px)
    p = np.clip(px, EPS, None)
    return p / p.sum()


def outcome(pr):
    """Index of the realised bucket (partition, threshold), or the 0/1 vector (binary)."""
    if pr["kind"] == "partition":
        return int(np.argmax(pr["y"]))
    if pr["kind"] == "threshold":
        return int(pr["y"].sum())  # number of "above x" strikes that settled YES
    return pr["y"]


def logscore(p, pr):
    """Negative log likelihood: a number per problem (binary: mean over its markets)."""
    y = outcome(pr)
    if pr["kind"] == "binary":
        return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))
    return float(-np.log(max(p[y], EPS)))


# ----------------------------------------------------------------------------- baselines


def sharpen(p, a, pr):
    if pr["kind"] == "binary":
        z = a * np.log(p / (1 - p))
        return np.clip(1 / (1 + np.exp(-z)), EPS, 1 - EPS)
    q = np.power(p, a)
    return q / q.sum()


def fit_exponent(train):
    f = lambda a: np.mean([logscore(sharpen(market(pr), a, pr), pr) for pr in train])  # noqa: E731
    return minimize_scalar(f, bounds=(0.5, 3.0), method="bounded").x


def outside_prices(symbol):
    f = OUTSIDE / "{}.parquet".format(symbol.replace("^", "").replace("=", "_"))
    if f.exists():
        return pd.read_parquet(f)
    url = "https://query1.finance.yahoo.com/v8/finance/chart/{}?range=2y&interval=1h".format(symbol)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    d = json.loads(urllib.request.urlopen(req, timeout=30).read())["chart"]["result"][0]
    px = pd.DataFrame({"ts": d["timestamp"], "close": d["indicators"]["quote"][0]["close"]}).dropna()
    OUTSIDE.mkdir(parents=True, exist_ok=True)
    px.to_parquet(f, index=False)
    return px


def outside_dist(pr, px):
    """Lognormal at the read: last hourly close, trailing 20-day daily volatility, no drift."""
    hist = px[px["ts"] + 3600 <= pr["read_ts"]]  # bar must have closed by the read
    if len(hist) < 200:
        return None
    s = float(hist["close"].iloc[-1])
    daily = hist.assign(d=pd.to_datetime(hist["ts"], unit="s").dt.date).groupby("d")["close"].last()
    r = np.diff(np.log(daily.to_numpy()[-21:]))
    if len(r) < 10 or s <= 0:
        return None
    sig = r.std() * np.sqrt({"24h": 1.0, "6h": 0.25, "1h": 1 / 24}[pr["lead"]])
    sig = max(sig, 1e-4)
    z = lambda x: norm.cdf((np.log(np.clip(x, 1e-12, None)) - np.log(s)) / sig)  # noqa: E731
    if pr["kind"] == "threshold":
        return to_buckets(1 - z(pr["lo"]))
    lo = np.where(np.isfinite(pr["lo"]), z(pr["lo"]), 0.0)
    hi = np.where(np.isfinite(pr["hi"]), z(pr["hi"]), 1.0)
    p = np.clip(hi - lo, EPS, None)
    return p / p.sum()


def pool(pm, po, w):
    z = w[0] * np.log(pm) + w[1] * np.log(po)
    p = np.exp(z - z.max())
    return p / p.sum()


def fit_pool(train):
    f = lambda w: np.mean([logscore(pool(market(pr), pr["out"], w), pr) for pr in train])  # noqa: E731
    return minimize(f, np.array([1.0, 0.0]), method="Nelder-Mead").x


# ----------------------------------------------------------------------------- protocol


def evaluate(series, probs):
    res = {}
    for lead in LEADS:
        P = sorted([p for p in probs if p["lead"] == lead], key=lambda p: p["day"])
        if len(P) < 30:
            continue
        months = sorted({p["day"].to_period("M") for p in P})
        rows = []
        for mo in months[WARMUP:]:
            train = [p for p in P if p["day"].to_period("M") < mo]
            test = [p for p in P if p["day"].to_period("M") == mo]
            if len(train) < 30 or not test:
                continue
            a = fit_exponent(train)
            tr_out = [p for p in train if p.get("out") is not None]
            w = fit_pool(tr_out) if len(tr_out) >= 30 else None
            for pr in test:
                pm = market(pr)
                r = {
                    "day": pr["day"],
                    "mid": logscore(pm, pr),
                    "bid": logscore(market(pr, "bid"), pr),
                    "sharp": logscore(sharpen(pm, a, pr), pr),
                    "exponent": a,
                }
                if pr.get("out") is not None:
                    r["outside"] = logscore(pr["out"], pr)
                    if w is not None:
                        r["pool"] = logscore(pool(pm, pr["out"], w), pr)
                rows.append(r)
        if not rows:
            continue
        R = pd.DataFrame(rows)
        days = R["day"].to_numpy()
        out = {
            "problems": int(len(R)),
            "months": int(R["day"].dt.to_period("M").nunique()),
            "mid_logloss": float(R["mid"].mean()),
        }
        for k in ("bid", "sharp", "outside", "pool"):
            if k in R and R[k].notna().sum() >= 20:
                sel = R[k].notna().to_numpy()
                d = (R["mid"] - R[k]).to_numpy()[sel]
                out[k + "_minus_mid"] = {
                    "diff": float(d.mean()),
                    "ci": metrics.date_bootstrap_mean(days[sel], d, 2000),
                    "n": int(sel.sum()),
                }
        out["last_exponent"] = float(R["exponent"].iloc[-1])
        res[lead] = out
    return res


def main():
    RESULTS.mkdir(parents=True, exist_ok=True)
    allres, counts = {}, {}
    for f in sorted(RAW.glob("*.parquet")):
        series = f.stem
        df = pd.read_parquet(f)
        probs = problems(series, df)
        counts[series] = {"events": int(df["event"].nunique()), "problems": len(probs)}
        if series in SYMBOL:
            px = outside_prices(SYMBOL[series])
            for pr in probs:
                pr["out"] = outside_dist(pr, px)
        allres[series] = evaluate(series, probs)
        for lead, r in allres[series].items():
            line = "{:16s} {:3s} n={:4d} mid {:.3f}".format(series, lead, r["problems"], r["mid_logloss"])
            for k in ("bid", "sharp", "outside", "pool"):
                if k + "_minus_mid" in r:
                    v = r[k + "_minus_mid"]
                    line += "  {} {:+.3f} [{:+.3f},{:+.3f}]".format(k, v["diff"], *v["ci"])
            print(line, flush=True)
    (RESULTS / "baselines.json").write_text(
        json.dumps({"counts": counts, "results": allres}, indent=1, default=str)
    )


if __name__ == "__main__":
    main()
