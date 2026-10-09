#!/usr/bin/env python3
"""Two controls from financial representation learning (FINDINGS §45).

1. Random encoder: transformer-L with a frozen random encoder against the trained one and the MLP.
2. Regime vs seed: five single-seed MLPs; the share of variance in monthly gain over the market
   that comes from the month (regime) rather than the seed.

    uv run scripts/controls.py
"""

from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from isotherm import dataset, metrics  # noqa: E402
from isotherm.baselines import Source, transformer_large_suite  # noqa: E402
from isotherm.controls import RandomEncoderTransformer, SeedNet  # noqa: E402
from isotherm.evaluation import oos_predictions  # noqa: E402
from isotherm.splits import LOCKBOX_START  # noqa: E402
from isotherm.weather import CITIES  # noqa: E402

CACHE = "data/oos_controls"
RECENT_FROM = np.datetime64(LOCKBOX_START - pd.Timedelta(days=365))
SEEDS = range(5)


def aligned(base, other, name):
    """Predictions of `name` from `other`, aligned to `base` rows (NaN where missing)."""
    key = (base.rows.meta["event"] + "|" + base.rows.meta["read"]).to_numpy()
    k2 = other.rows.meta["event"] + "|" + other.rows.meta["read"]
    idx = pd.Series(np.arange(len(other.rows)), index=k2.to_numpy())
    p = np.full(base.preds["market"].shape, np.nan)
    hit = pd.Index(key).isin(idx.index)
    p[hit] = other.preds[name][idx[key[hit]].to_numpy()]
    return p


def paired(days, a, b, sel):
    d = (a - b)[sel]
    return {
        "diff": float(d.mean()),
        "ci": metrics.date_bootstrap_mean(days[sel], d, 2000),
        "n": int(sel.sum()),
    }


def main():
    ls = dataset.load(list(CITIES))
    base = oos_predictions(ls, transformer_large_suite())
    rnd = RandomEncoderTransformer()
    ro = oos_predictions(ls, [Source("market"), rnd], cache_dir=CACHE)
    print("random encoder done", flush=True)
    seeds = {s: oos_predictions(ls, [Source("market"), SeedNet(s)], cache_dir=CACHE) for s in SEEDS}
    print("seeds done", flush=True)
    res = {"random_encoder": {}, "regime": {}}
    for read, o in base.items():
        y, days = o.rows.y, o.rows.meta["day"].to_numpy()
        recent = days >= RECENT_FROM
        L = {
            k: metrics.log_score(o.preds[v], y)
            for k, v in (("market", "market"), ("mlp", "isotherm"), ("tf", "isotherm · transformer-L"))
        }
        pr = aligned(o, ro[read], rnd.name)
        ok = np.isfinite(pr).all(1)
        L["rnd"] = np.where(ok, metrics.log_score(np.nan_to_num(pr, nan=1.0), y), np.nan)
        sel = recent & ok
        res["random_encoder"][read] = {
            "random_vs_market": paired(days, L["market"], L["rnd"], sel),
            "trained_minus_random": paired(days, L["rnd"], L["tf"], sel),
            "mlp_minus_random": paired(days, L["rnd"], L["mlp"], sel),
        }
        # Regime vs seed: monthly mean gain over the market, per seed, over every out-of-sample month.
        cells = []
        for s in SEEDS:
            ps = aligned(o, seeds[s][read], "isotherm · seed {}".format(s))
            g = L["market"] - metrics.log_score(np.nan_to_num(ps, nan=1.0), y)
            m = np.isfinite(ps).all(1)
            month = pd.Series(days[m]).dt.to_period("M").astype(str).to_numpy()
            for mo, v in pd.Series(g[m]).groupby(month).mean().items():
                cells.append({"seed": s, "month": mo, "gain": v})
        c = pd.DataFrame(cells)
        tab = c.pivot(index="month", columns="seed", values="gain").dropna()
        grand = tab.to_numpy().mean()
        ss_month = tab.shape[1] * ((tab.mean(axis=1) - grand) ** 2).sum()
        ss_seed = tab.shape[0] * ((tab.mean(axis=0) - grand) ** 2).sum()
        ss_tot = ((tab.to_numpy() - grand) ** 2).sum()
        res["regime"][read] = {
            "months": int(tab.shape[0]),
            "share_month": float(ss_month / ss_tot),
            "share_seed": float(ss_seed / ss_tot),
            "share_residual": float((ss_tot - ss_month - ss_seed) / ss_tot),
            "monthly_gain_range": [float(tab.mean(axis=1).min()), float(tab.mean(axis=1).max())],
            "months_positive": int((tab.mean(axis=1) > 0).sum()),
        }
        print(
            read,
            json.dumps(res["random_encoder"][read]["trained_minus_random"]),
            json.dumps(res["regime"][read]),
            flush=True,
        )
    pathlib.Path("results/controls.json").write_text(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
