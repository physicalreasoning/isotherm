#!/usr/bin/env python3
"""Score the daily-lows lockbox ONCE, with the strategy frozen in FINDINGS §13 (commit c0d3456).

uv run scripts/lows_lockbox.py
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess
import sys
from types import SimpleNamespace

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from pmdecide import lows, metrics, stats  # noqa: E402
from pmdecide.backtest import Config, daily_pnl, run  # noqa: E402
from pmdecide.baselines import LogPool  # noqa: E402
from pmdecide.splits import EMBARGO  # noqa: E402

spec = importlib.util.spec_from_file_location("bt", ROOT / "scripts" / "backtest.py")
bt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bt)

READ = "d1_16"
FROZEN = Config("pool · market+GFS", "threshold", theta=0.01)


def main():
    ls = lows.load()
    ls = ls.take(np.flatnonzero((ls.meta["read"] == READ).to_numpy()))
    ls = ls.complete(["market", "emos_gfs"])
    day = ls.meta["day"]
    train = ls.take(np.flatnonzero((day < lows.LOCKBOX_START - EMBARGO).to_numpy()))
    test = ls.take(np.flatnonzero((day >= lows.LOCKBOX_START).to_numpy()))
    pool = LogPool(["market", "emos_gfs"], FROZEN.model).fit(train)
    p = pool.predict(test)
    print(
        "lows lockbox: {} ladders, {} to {}; pool weights {}".format(
            len(test),
            test.meta["day"].min().date(),
            test.meta["day"].max().date(),
            np.round(pool.weights[READ], 3).tolist(),
        )
    )
    led = run(test, p, FROZEN)
    d = daily_pnl(led, test.meta["day"])
    x = d.to_numpy()
    t = stats.newey_west_t(x)
    verdict = (
        "PASS" if x.sum() > 0 and t > 1.645 else "CONSISTENT BUT UNDERPOWERED" if x.sum() > 0 else "FAIL"
    )
    res = {
        "frozen": FROZEN.name,
        "read": READ,
        "ladders": len(test),
        "verdict": verdict,
        "from": str(test.meta["day"].min().date()),
        "to": str(test.meta["day"].max().date()),
        "pool_weights": pool.weights[READ].tolist(),
        "summary": bt.summarise(d, led, 2000),
    }
    if len(led):
        res["by_city"] = {k: float(v["pnl"].sum()) for k, v in led.groupby("city")}
        res["by_month"] = {
            k: float(v["pnl"].sum()) for k, v in led.groupby(led["day"].dt.to_period("M").astype(str))
        }
    res["checks"] = bt.placebos(SimpleNamespace(rows=test), FROZEN, len(led))
    ref = metrics.log_score(test.probs["market"], test.y)
    gain = ref - metrics.log_score(p, test.y)
    res["log_score_gain_vs_market"] = float(gain.mean())
    res["log_score_ci"] = metrics.date_bootstrap_mean(test.meta["day"].to_numpy(), gain, 2000)
    try:
        res["git"] = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).decode().strip()
    except Exception:
        res["git"] = None
    (ROOT / "results" / "lows_lockbox.json").write_text(json.dumps(res, indent=2, default=str))
    s = res["summary"]
    print("\nVERDICT: {}".format(verdict))
    print(
        "PnL ${:,.0f} over {} days, {} trades | Sharpe {:.2f} [{:.2f}, {:.2f}] | NW t {:.2f}".format(
            s["pnl"], s["days"], s["trades"], s["sharpe_ann"], *s["sharpe_ann_ci"], t
        )
    )
    print(
        "  hit rate {:.1%}".format(s.get("hit_rate") or 0),
        "| by city",
        {k: round(v) for k, v in res.get("by_city", {}).items()},
    )
    print("  by month", {k: round(v) for k, v in res.get("by_month", {}).items()})
    print(
        "  log score vs market {:+.4f} [{:+.4f}, {:+.4f}]".format(
            res["log_score_gain_vs_market"], *res["log_score_ci"]
        )
    )
    print("  checks", {k: (v["trades"], round(v["pnl"])) for k, v in res["checks"].items()})


if __name__ == "__main__":
    main()
