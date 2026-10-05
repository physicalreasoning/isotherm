#!/usr/bin/env python3
"""G4: is the transformer data-limited, and do the cheap sources of more data help? (FINDINGS §20)

    uv run scripts/data_scaling.py --arms pooled-tf pooled-mlp ...   # compute and cache arms
    uv run scripts/data_scaling.py --score                           # score every cached arm

Arms are cached in data/oos_g4/. The per-read MLP and transformer-L are read from the
walk-forward cache of `benchmark.py --suite transformer-large`.
"""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import pathlib
import pickle
import sys
import time

import numpy as np
import pandas as pd
import torch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from isotherm import dataset, lows, metrics, model, pooled  # noqa: E402
from isotherm.baselines import transformer_large_suite  # noqa: E402
from isotherm.evaluation import oos_predictions  # noqa: E402
from isotherm.splits import LOCKBOX_START  # noqa: E402
from isotherm.weather import CITIES  # noqa: E402

CACHE = pathlib.Path("data/oos_g4")
RECENT_FROM = LOCKBOX_START - pd.Timedelta(days=365)
LAST_FOLD_FROM = pd.Timestamp("2026-04-01")
HIGHS = list(CITIES)  # pinned: the seven scored cities, whatever other panels exist
MLP, TF = "isotherm", "isotherm · transformer-L"
CTL = "isotherm · transformer-L · pooled · market-sampled labels (control)"


def arms():
    P, T = pooled.PooledNet, pooled.PooledTransformer
    return {
        "pooled-mlp": (lambda: P(), None),
        "pooled-tf": (lambda: T(), None),
        "pooled-tf-control": (lambda: T(CTL, market_labels=True, seeds=3), None),
        "lc-mlp-25": (lambda: P("isotherm · pooled · 25%", frac=0.25), None),
        "lc-mlp-50": (lambda: P("isotherm · pooled · 50%", frac=0.5), None),
        "lc-tf-25": (lambda: T("isotherm · transformer-L · pooled · 25%", frac=0.25), None),
        "lc-tf-50": (lambda: T("isotherm · transformer-L · pooled · 50%", frac=0.5), None),
        "pooled-tf-lows": (lambda: T("isotherm · transformer-L · pooled + lows"), "lows"),
        "pooled-tf-cities": (lambda: T("isotherm · transformer-L · pooled + new cities"), "cities"),
    }


def extra(kind):
    if kind == "lows":
        ls = lows.load()
        ls = ls.take(np.flatnonzero((ls.meta["day"] < lows.LOCKBOX_START).to_numpy()))
        return pooled.as_extra(ls, is_low=True)
    if kind == "cities":
        from isotherm.weather import NEW_CITIES

        keys = [k for k in NEW_CITIES if (dataset.DATA / "panel" / "{}.parquet".format(k)).exists()]
        return pooled.as_extra(dataset.LadderSet.concat([dataset.build_city(k) for k in keys]), is_low=False)
    return None


def cache_path(name, m, ls, kind):
    h = hashlib.sha256()
    h.update(repr((name, kind, sorted(vars(m).items(), key=str))).encode())
    h.update(pd.util.hash_pandas_object(ls.meta[["event", "read", "day"]], index=False).values)
    for mod in (model, pooled):
        h.update(inspect.getsource(mod).encode())
    return CACHE / "{}_{}.pkl".format(name, h.hexdigest()[:12])


def compute(ls, names):
    folds = list(pooled.walk_forward(ls.meta["day"]))
    last = {len(folds) - 1}
    for name in names:
        make, kind = arms()[name]
        m = make()
        f = cache_path(name, m, ls, kind)
        if f.exists():
            print(name, "cached", flush=True)
            continue
        t0 = time.time()
        out = pooled.pooled_oos(ls, m, extra(kind), folds=last if kind else None)
        CACHE.mkdir(parents=True, exist_ok=True)
        f.write_bytes(pickle.dumps(out))
        print("{} done in {:.0f}s".format(name, time.time() - t0), flush=True)


def load_all(ls):
    """{read: (rows meta, y, {model: probs})} on the rows every loaded arm covers."""
    base = oos_predictions(ls, transformer_large_suite())
    got = {}
    for name, (make, kind) in arms().items():
        m = make()
        f = cache_path(name, m, ls, kind)
        if f.exists():
            got[name] = (m.name, pickle.loads(f.read_bytes()))
    out = {}
    for read, o in base.items():
        key = o.rows.meta["event"] + "|" + o.rows.meta["read"]
        P = {"market": o.preds["market"], MLP: o.preds[MLP], TF: o.preds[TF]}
        for mname, oos in got.values():
            r = oos[read]
            idx = pd.Series(np.arange(len(r.rows)), index=r.rows.meta["event"] + "|" + r.rows.meta["read"])
            p = np.full_like(o.preds["market"], np.nan)
            hit = key.isin(idx.index).to_numpy()
            p[hit] = r.preds[mname][idx[key[hit]].to_numpy()]
            P[mname] = p
        out[read] = (o.rows, P)
    return out


def paired(days, a, b, sel):
    """Mean of (log score of b) minus (log score of a) on sel, positive when b is better."""
    d = (a - b)[sel]
    ci = metrics.date_bootstrap_mean(days[sel], d, 2000)
    return {"diff": float(d.mean()), "ci": ci, "n": int(sel.sum())}


def score(ls):
    data = load_all(ls)
    names = {k: v for k, v in [(n, a[0]().name) for n, a in arms().items()]}
    res = {"per_read": {}, "pooled_reads": {}}
    stack = {}
    for read, (rows, P) in data.items():
        y, days = rows.y, rows.meta["day"].to_numpy()
        recent = rows.meta["day"].to_numpy() >= np.datetime64(RECENT_FROM)
        lastf = rows.meta["day"].to_numpy() >= np.datetime64(LAST_FOLD_FROM)
        ok = np.ones(len(y), bool)
        for k in P:
            if "+ lows" not in k and "+ new cities" not in k:
                ok &= np.isfinite(P[k]).all(1)
        L = {k: np.where(ok, metrics.log_score(np.nan_to_num(p, nan=1.0), y), np.nan) for k, p in P.items()}
        r = {}
        comps = {
            "pooled_tf_minus_mlp": (MLP, names["pooled-tf"]),
            "pooled_tf_minus_tf": (TF, names["pooled-tf"]),
            "pooled_mlp_minus_mlp": (MLP, names["pooled-mlp"]),
            "tf_minus_mlp_pooled": (names["pooled-mlp"], names["pooled-tf"]),
        }
        for c, (a, b) in comps.items():
            if a in L and b in L:
                r[c] = paired(days, L[a], L[b], ok & recent)
        if CTL in L:
            r["control_vs_market_all"] = float(np.nanmean((L["market"] - L[CTL])[ok]))
        for k in L:
            if k != "market":
                r.setdefault("vs_market_recent", {})[k] = float(np.nanmean((L["market"] - L[k])[ok & recent]))
        for tag in ("lows", "cities"):
            k = names["pooled-tf-" + tag]
            if k in L:
                sel = ok & lastf & np.isfinite(L[k])
                r["plus_" + tag + "_q2"] = paired(days, L[names["pooled-tf"]], L[k], sel)
        r["pass"] = "pooled_tf_minus_mlp" in r and r["pooled_tf_minus_mlp"]["ci"][0] > 0
        res["per_read"][read] = r
        stack[read] = (days, ok, recent, lastf, L)
    # Learning curve and lows/cities, pooled over reads.
    D = np.concatenate([s[0] for s in stack.values()])
    OK = np.concatenate([s[1] & s[2] for s in stack.values()])

    def cat(k):
        return np.concatenate([s[4][k] if k in s[4] else np.full(len(s[0]), np.nan) for s in stack.values()])

    mk = cat("market")
    curve = {}
    for frac, (m_, t_) in {
        "25%": ("lc-mlp-25", "lc-tf-25"),
        "50%": ("lc-mlp-50", "lc-tf-50"),
        "100%": ("pooled-mlp", "pooled-tf"),
    }.items():
        a, b = cat(names[m_]), cat(names[t_])
        sel = OK & np.isfinite(a) & np.isfinite(b)
        if sel.any():
            curve[frac] = {
                "mlp_vs_market": float((mk - a)[sel].mean()),
                "tf_vs_market": float((mk - b)[sel].mean()),
                "tf_minus_mlp": paired(D, a, b, sel),
            }
    res["learning_curve"] = curve
    if "50%" in curve and "100%" in curve:
        g50 = cat(names["lc-mlp-50"]) - cat(names["lc-tf-50"])
        g100 = cat(names["pooled-mlp"]) - cat(names["pooled-tf"])
        sel = OK & np.isfinite(g50) & np.isfinite(g100)
        d = (g100 - g50)[sel]
        ci = metrics.date_bootstrap_mean(D[sel], d, 2000)
        res["gap_growth_50_to_100"] = {"diff": float(d.mean()), "ci": ci}
    pr = res["per_read"]
    res["adoption"] = {
        "reads_passing": int(sum(r["pass"] for r in pr.values())),
        "controls_ok": all(abs(r.get("control_vs_market_all", 1)) <= 0.005 for r in pr.values()),
    }
    a = res["adoption"]
    a["verdict"] = "PASS" if a["reads_passing"] >= 3 and a["controls_ok"] else "FAIL"
    pathlib.Path("results/data_scaling.json").write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", nargs="*", default=[])
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--threads", type=int, default=0)
    a = ap.parse_args()
    if a.threads:
        torch.set_num_threads(a.threads)
    ls = dataset.load(HIGHS)
    if a.arms:
        compute(ls, a.arms)
    if a.score:
        score(ls)


if __name__ == "__main__":
    main()
