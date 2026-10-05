#!/usr/bin/env python3
"""Taker backtest for daily-low ladders, with the engine and protocol of scripts/backtest.py.

Out-of-sample probabilities come from the lows calendar (monthly walk-forward, lockbox
from 2026-09-01 sealed). Nested selection, Deflated Sharpe, PBO, engine checks and
robustness are the backtest script's own functions, unchanged.

    uv run scripts/lows_backtest.py
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from pmdecide import lows  # noqa: E402

spec = importlib.util.spec_from_file_location("bt", ROOT / "scripts" / "backtest.py")
bt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bt)
spec = importlib.util.spec_from_file_location("lb", ROOT / "scripts" / "lows_benchmark.py")
lb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lb)

MODELS = ["pool · market+GFS", "pool · all", "EMOS · GFS MOS", "market (tempered)"]


def main():
    t0 = time.time()
    bt.MODELS[:] = MODELS
    oos = lows.oos_predictions(lows.load(), lb.suite())
    results = {}
    for read, o in oos.items():
        key = "{} · taker".format(read)
        print("== {}: {} ladders".format(key, len(o.rows)), flush=True)
        results[key] = bt.run_read(bt.Taker(o), 1000)
        s = results[key]["selected"]
        print(
            "   nested PnL ${:,.0f}  Sharpe {:.2f}  DSR {:.3f}  PBO {:.2f}".format(
                s["pnl"], s["sharpe_ann"], results[key]["deflated_sharpe"]["dsr"], results[key]["pbo"]["pbo"]
            ),
            flush=True,
        )
    res = {"config": {"models": MODELS, "calendar": "lows monthly"}, "results": results}
    res["seconds"] = round(time.time() - t0, 1)
    p = ROOT / "results" / "lows_backtest"
    p.with_suffix(".json").write_text(json.dumps(res, indent=2, default=str))
    p.with_suffix(".md").write_text(bt.markdown(res).replace("# Backtest", "# Backtest: daily lows", 1))
    print(bt.markdown(res))


if __name__ == "__main__":
    main()
