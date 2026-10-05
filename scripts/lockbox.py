#!/usr/bin/env python3
"""Score the lockbox ONCE, with the strategy frozen in FINDINGS §9.

Every model is refit on all ladders before 2026-06-29 (2-day embargo) and predicts
2026-07-01 onward. The frozen configuration trades; the criteria were pushed before
this script ever ran (commit b455496).

    uv run scripts/lockbox.py
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from isotherm import dataset, metrics, stats  # noqa: E402
from isotherm.backtest import Config, daily_pnl, interior_market, run  # noqa: E402
from isotherm.baselines import g2_suite  # noqa: E402
from isotherm.evaluation import oos_predictions  # noqa: E402

spec = importlib.util.spec_from_file_location("bt", ROOT / "scripts" / "backtest.py")
bt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bt)

READ = "d1_16"
FROZEN = Config("pool · market+GFS", "kelly", fraction=0.25)


def main():
    ls = dataset.load()
    o = oos_predictions(ls, g2_suite(), lockbox=True)[READ]
    rows = o.rows
    print(
        "lockbox {}: {} ladders, {} to {}".format(
            READ, len(rows), rows.meta["day"].min().date(), rows.meta["day"].max().date()
        ),
        flush=True,
    )
    days = rows.meta["day"]
    led = run(rows, o.preds[FROZEN.model], FROZEN)
    d = daily_pnl(led, days)
    x = d.to_numpy()
    t = stats.newey_west_t(x)
    verdict = (
        "PASS" if x.sum() > 0 and t > 1.645 else "CONSISTENT BUT UNDERPOWERED" if x.sum() > 0 else "FAIL"
    )
    res = {
        "frozen": FROZEN.name,
        "read": READ,
        "ladders": len(rows),
        "from": str(days.min().date()),
        "to": str(days.max().date()),
        "verdict": verdict,
        "summary": bt.summarise(d, led, 2000),
    }
    slip = run(rows, o.preds[FROZEN.model], Config(**{**FROZEN.__dict__, "slip": 1}))
    res["slip_1c_pnl"] = float(slip["pnl"].sum()) if len(slip) else 0.0
    if len(led):
        res["by_city"] = {
            k: {"pnl": float(v["pnl"].sum()), "trades": int(len(v))} for k, v in led.groupby("city")
        }
        led = led.assign(
            month=led["day"].dt.to_period("M").astype(str),
            regime=led["event"].map(dict(zip(rows.meta["event"], rows.meta["regime"], strict=False))),
        )
        res["by_month"] = {k: float(v["pnl"].sum()) for k, v in led.groupby("month")}
        res["by_regime"] = {k: float(v["pnl"].sum()) for k, v in led.groupby("regime")}

    # engine checks and noise on the same rows
    k = rows.mask.shape[1]
    inner = interior_market(rows.quotes["bid"], rows.quotes["ask"], rows.mask)
    ok = np.isfinite(inner).all(1)
    oracle = run(rows, np.eye(k)[rows.y] * rows.mask, Config("o", "threshold", theta=0.0))
    insp = run(rows.take(np.flatnonzero(ok)), inner[ok], Config("m", "threshold", theta=0.0))
    res["engine_checks"] = {
        "oracle_losing_trades": int((oracle["pnl"] < 0).sum()),
        "in_spread_trades": int(len(insp)),
    }
    ex = bt.Taker(o)
    res["noise_matched_turnover"] = ex.placebos(FROZEN, len(led))["noise_matched_turnover"]

    # secondary: scoring on the lockbox, every model vs market
    ref = metrics.log_score(o.preds["market"], rows.y)
    dd = days.to_numpy()
    res["scores"] = {}
    for name, p in o.preds.items():
        ls_ = metrics.log_score(p, rows.y)
        res["scores"][name] = {
            "log_score": float(ls_.mean()),
            "gain_vs_market": float((ref - ls_).mean()),
            "ci": metrics.date_bootstrap_mean(dd, ref - ls_, 2000),
        }
    try:
        res["git"] = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).decode().strip()
    except Exception:
        res["git"] = None
    out = ROOT / "results" / "lockbox.json"
    out.write_text(json.dumps(res, indent=2, default=str))
    s = res["summary"]
    print("\nVERDICT: {}".format(verdict))
    print(
        "PnL ${:,.0f} over {} days, {} trades | Sharpe {:.2f} [{:.2f}, {:.2f}] | NW t {:.2f}".format(
            s["pnl"], s["days"], s["trades"], s["sharpe_ann"], *s["sharpe_ann_ci"], t
        )
    )
    for key in ("hit_rate", "return_on_outlay", "ev_per_contract", "realised_per_contract"):
        if key in s:
            print("  {}: {:.4f}".format(key, s[key]))
    print("  +1¢ slip PnL: ${:,.0f}".format(res["slip_1c_pnl"]))
    print("  by city:", {k_: round(v["pnl"]) for k_, v in res.get("by_city", {}).items()})
    print("  by month:", {k_: round(v) for k_, v in res.get("by_month", {}).items()})
    print("  by regime:", {k_: round(v) for k_, v in res.get("by_regime", {}).items()})
    print("  engine checks:", res["engine_checks"], "| noise:", res["noise_matched_turnover"])
    for name in ("isotherm", "pool · market+GFS", "isotherm · market-sampled labels (control)"):
        v = res["scores"][name]
        print(
            "  score {:46s} Δ vs market {:+.4f} [{:+.4f}, {:+.4f}]".format(
                name, v["gain_vs_market"], *v["ci"]
            )
        )
    print("wrote", out)


if __name__ == "__main__":
    main()
