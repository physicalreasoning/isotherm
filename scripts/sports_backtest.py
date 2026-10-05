#!/usr/bin/env python3
"""MLB taker and maker backtests, through the same engine and protocol as weather.

Reuses scripts/backtest.py unchanged (nested selection, DSR, PBO, engine checks,
attribution, robustness) and overrides only what is MLB-specific:
  - models: the sports suite (market, tempered market, Elo, Elo+SP, pools)
  - bankroll slots: ~15 games run concurrently on a full MLB day
  - maker fee: KXMLBGAME is `quadratic_with_maker_fees`, so resting orders pay 0.0175
  - calendar: monthly walk-forward, lockbox from 2026-09-01 (scripts/sports_benchmark.py)
Orders are pre-game only: `close_ts` is the scheduled first pitch, so a resting maker
order is cancelled when the game starts.

    uv run scripts/sports_backtest.py
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import backtest as bt  # noqa: E402
import sports_benchmark as sb  # noqa: E402

from pmdecide.backtest import Config, MakerConfig  # noqa: E402
from pmdecide.sports.dataset import build  # noqa: E402
from pmdecide.sports.oos import oos_predictions  # noqa: E402

MODELS = ["pool · all", "pool · market+Elo+SP", "Elo + starters", "market (tempered)"]
SLOTS = 15
MAKER_FEE = 0.0175


def grid():
    out = []
    for m in MODELS:
        out += [Config(m, "kelly", fraction=f, slots=SLOTS) for f in (0.10, 0.25, 0.50)]
        out += [Config(m, "threshold", theta=t, slots=SLOTS) for t in (0.01, 0.02, 0.04, 0.08)]
    return out


class Maker(bt.Maker):
    default = MakerConfig("pool · all", theta=0.02, horizon_h=4.0, maker_fee_rate=MAKER_FEE)

    def configs(self):
        return [MakerConfig(m, theta=t, horizon_h=h, maker_fee_rate=MAKER_FEE) for m in MODELS
                for t in (0.0, 0.01, 0.02, 0.04) for h in (1.0, 4.0)]


def load_trades(root="data/sports/trades"):
    import pandas as pd
    out = {}
    f = pathlib.Path(root) / "mlb.parquet"
    if not f.exists():
        return out
    df = pd.read_parquet(f).sort_values(["ticker", "ts"])
    for t, g in df.groupby("ticker", sort=False):
        out[t] = (g["ts"].to_numpy(), g["yes_price"].to_numpy(), g["count"].to_numpy(),
                  g["taker_yes"].to_numpy())
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--execution", nargs="+", default=["taker", "maker"])
    ap.add_argument("--boot", type=int, default=1000)
    ap.add_argument("--out", default="results/sports_backtest")
    a = ap.parse_args()
    bt.grid = grid
    bt.MODELS = MODELS
    bt.Taker.default = Config("pool · all", "kelly", fraction=0.25, slots=SLOTS)
    t0 = time.time()
    ls = build()
    oos = oos_predictions(ls, sb.suite(), **sb.SPLITS)
    trades = load_trades() if "maker" in a.execution else {}
    results = {}
    for read, o in oos.items():
        for exe in a.execution:
            if exe == "maker" and not trades:
                print("maker: no trades, run scripts/sports_fetch_trades.py", flush=True)
                continue
            ex = bt.Taker(o) if exe == "taker" else Maker(o, trades)
            key = "{} · {}".format(read, exe)
            print("== {}: {} ladders".format(key, len(o.rows)), flush=True)
            results[key] = bt.run_read(ex, a.boot)
            s = results[key]["selected"]
            print("   nested PnL ${:,.0f}  Sharpe {:.2f}  DSR {:.3f}  PBO {:.2f}  ({:.0f}s)".format(
                s["pnl"], s["sharpe_ann"], results[key]["deflated_sharpe"]["dsr"],
                results[key]["pbo"]["pbo"], time.time() - t0), flush=True)
    res = {"config": vars(a), "results": results, "seconds": round(time.time() - t0, 1)}
    p = pathlib.Path(a.out)
    p.parent.mkdir(exist_ok=True)
    p.with_suffix(".json").write_text(json.dumps(res, indent=2, default=str))
    md = bt.markdown(res).replace("split across 7 concurrent ladders",
                                  "split across {} concurrent games".format(SLOTS))
    md = md.replace("# Backtest", "# MLB backtest", 1)
    p.with_suffix(".md").write_text(md)
    print(md)


if __name__ == "__main__":
    main()
