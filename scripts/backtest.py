#!/usr/bin/env python3
"""Backtest: can the model's probabilities be turned into money after fees, spread and capacity?

Protocol (docs/EVALS.md §Backtest)
  1. Out-of-sample probabilities come from the same walk-forward as the benchmark.
  2. A grid of strategy configurations (model x sizing) is simulated over the full
     out-of-sample period, one daily PnL series each.
  3. HEADLINE = nested selection: for each quarter, the configuration with the best
     Sharpe on *earlier quarters only* is traded. The first quarters, with no
     history, use the pre-registered default. This is the number you could have
     earned; the full-period best configuration is reported only as a ceiling.
  4. Overfitting control: Deflated Sharpe over all configurations tried, and PBO
     by CSCV over the configuration grid.
  5. Engine checks: oracle (must never lose), market-as-model (must find nothing),
     noise with matched turnover (must lose about the costs it pays).
  6. Robustness: slippage, fee multiplier, participation and size sweeps;
     attribution of PnL into alpha vs mid, spread paid, and fees; edge realisation.

    uv run scripts/backtest.py
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from pmdecide import dataset, stats  # noqa: E402
from pmdecide.backtest import (  # noqa: E402
    Config,
    MakerConfig,
    daily_pnl,
    interior_market,
    load_trades,
    run,
    run_maker,
)
from pmdecide.baselines import default_suite  # noqa: E402
from pmdecide.evaluation import oos_predictions  # noqa: E402

MODELS = ["pool · all", "pool · market+NBM", "EMOS · NBM", "market (tempered)"]
DEFAULT = Config("pool · all", "kelly", fraction=0.25)       # pre-registered, folds w/o history


def grid():
    out = []
    for m in MODELS:
        out += [Config(m, "kelly", fraction=f) for f in (0.10, 0.25, 0.50)]
        out += [Config(m, "threshold", theta=t) for t in (0.01, 0.02, 0.04, 0.08)]
    return out


def summarise(daily: pd.Series, ledger: pd.DataFrame, boot: int) -> dict:
    x = daily.to_numpy()
    r = {"days": len(x), "pnl": float(x.sum()), "mean_daily": float(x.mean()),
         "sharpe_ann": stats.annualise(stats.sharpe(x)),
         "sharpe_ann_ci": [stats.annualise(v) for v in stats.stationary_bootstrap(x, n=boot)],
         "nw_t": stats.newey_west_t(x), "max_drawdown": float((np.maximum.accumulate(
             np.cumsum(x)) - np.cumsum(x)).max()),
         "trades": int(len(ledger)), "active_days": int((x != 0).sum())}
    if len(ledger):
        c = ledger["contracts"]
        r.update({"contracts": float(c.sum()), "outlay": float(ledger["outlay"].sum()),
                  "hit_rate": float((ledger["pnl"] > 0).mean()),
                  "return_on_outlay": float(ledger["pnl"].sum() / ledger["outlay"].sum()),
                  "ev_per_contract": float((ledger["ev_per_contract"] * c).sum() / c.sum()),
                  "realised_per_contract": float(ledger["pnl"].sum() / c.sum()),
                  "attribution": {
                      "alpha_vs_mid": float((c * (ledger["payoff"] / c - ledger["mid"])).sum()),
                      "spread_paid": float(-(c * (ledger["price"] - ledger["mid"])).sum()),
                      "fees": float(-ledger["fee"].sum())}})
    return r


def edge_realisation(ledger: pd.DataFrame, bins: int = 5) -> dict:
    """Ex-ante EV per contract vs realised PnL per contract, by quantile of EV."""
    if len(ledger) < bins * 10:
        return {}
    q = pd.qcut(ledger["ev_per_contract"], bins, duplicates="drop")
    g = ledger.groupby(q, observed=True).apply(lambda d: pd.Series({
        "ev": (d.ev_per_contract * d.contracts).sum() / d.contracts.sum(),
        "realised": d.pnl.sum() / d.contracts.sum(), "trades": len(d)}), include_groups=False)
    w = ledger["contracts"]
    slope = np.polyfit(ledger["ev_per_contract"], ledger["pnl"] / w, 1, w=np.sqrt(w))[0]
    return {"by_bin": g.reset_index(drop=True).to_dict("records"), "slope": float(slope)}


def nested(o, configs, daily, ledgers, default_name):
    """Trade, each fold, the config with the best Sharpe on strictly earlier folds."""
    days = next(iter(daily.values())).index
    fold_by_day = pd.Series(o.fold, index=o.rows.meta["day"]).groupby(level=0).first()
    fold_by_day = fold_by_day.reindex(days)
    sel_daily = pd.Series(0.0, index=days)
    sel_ledgers, picks = [], []
    M = pd.DataFrame({c.name: daily[c.name] for c in configs})
    for f in sorted(fold_by_day.dropna().unique()):
        in_f = (fold_by_day == f).to_numpy()
        hist = (fold_by_day < f).to_numpy()
        if (fold_by_day[hist].nunique() if hist.any() else 0) < 2:
            choice = default_name
        else:
            sr = M[hist].apply(lambda col: stats.sharpe(col.to_numpy()))
            choice = sr.idxmax()
        sel_daily[in_f] = M.loc[in_f, choice].to_numpy()
        led = ledgers[choice]
        if len(led):
            sel_ledgers.append(led[led["day"].isin(days[in_f])])
        picks.append({"fold": o.folds[int(f)]["fold"], "config": choice})
    ledger = pd.concat(sel_ledgers) if sel_ledgers else pd.DataFrame()
    return sel_daily, ledger, picks


def placebos(o, cfg, target_trades, seed=0):
    rows = o.rows
    k = rows.mask.shape[1]
    oracle = np.eye(k)[rows.y] * rows.mask
    # A coherent distribution inside every spread must never trade: the no-free-lunch check.
    # Ladders where none exists (Σbid > 1 or Σask < 1) are true arbitrage, counted apart.
    inner = interior_market(rows.quotes["bid"], rows.quotes["ask"], rows.mask)
    coherent = np.isfinite(inner).all(1)
    out = {"oracle (must never lose)": run(rows, oracle, Config("oracle", "threshold", theta=0.0)),
           "in-spread market (must not trade)": run(rows.take(np.flatnonzero(coherent)),
                                                   inner[coherent],
                                                   Config("mid", "threshold", theta=0.0)),
           # Normalising away the overround moves some probabilities outside their spread;
           # this is what "trading the overround" earns, a baseline rather than a check.
           "normalised mid": run(rows, rows.probs["market"],
                                 Config("market", "threshold", theta=0.0))}
    rng = np.random.default_rng(seed)
    best, best_gap = None, None
    for sigma in (0.05, 0.1, 0.2, 0.3, 0.5, 0.8):
        z = rows.probs["market"] * np.exp(rng.normal(0, sigma, rows.mask.shape))
        z = np.where(rows.mask, z, 0)
        z /= z.sum(1, keepdims=True)
        led = run(rows, z, Config("noise", cfg.sizing, fraction=cfg.fraction, theta=cfg.theta))
        gap = abs(len(led) - target_trades)
        if best_gap is None or gap < best_gap:
            best, best_gap = (sigma, led), gap
    out["noise_matched_turnover"] = best[1]
    res = {}
    for k_, led in out.items():
        res[k_] = {"trades": int(len(led)),
                   "pnl": float(led["pnl"].sum()) if len(led) else 0.0,
                   "losing_trades": int((led["pnl"] < 0).sum()) if len(led) else 0}
    res["noise_matched_turnover"]["sigma"] = best[0]
    res["arbitrage_ladders"] = {"trades": int((~coherent).sum()), "pnl": 0.0, "losing_trades": 0}
    return res


def robustness(o, cfg, cache):
    rows, p = o.rows, o.preds[cfg.model]
    days = rows.meta["day"]
    out = []
    for label, kw in [("base", {}), ("slip +1¢", {"slip": 1}), ("slip +2¢", {"slip": 2}),
                      ("fees ×1.5", {"fee_rate": 0.105}), ("participation 1%", {"participation": 0.01}),
                      ("participation 20%", {"participation": 0.20}),
                      ("size ×10", {"bankroll": cfg.bankroll * 10, "stake": cfg.stake * 10})]:
        c = Config(**{**cfg.__dict__, **kw})
        led = run(rows, p, c, cache if not ({"slip", "fee_rate"} & set(kw)) else None)
        d = daily_pnl(led, days).to_numpy()
        out.append({"scenario": label, "pnl": float(d.sum()),
                    "sharpe_ann": stats.annualise(stats.sharpe(d)), "trades": int(len(led))})
    return out


class Taker:
    label = "taker"
    default = DEFAULT

    def __init__(self, o):
        self.o, self.caches = o, {m: {} for m in MODELS}

    def configs(self):
        return grid()

    def simulate(self, cfg, probs=None, rows=None):
        rows = rows if rows is not None else self.o.rows
        probs = probs if probs is not None else self.o.preds[cfg.model]
        cache = self.caches.get(cfg.model) if (cfg.sizing == "kelly" and rows is self.o.rows) else None
        return run(rows, probs, cfg, cache)

    def placebos(self, cfg, target):
        return placebos(self.o, cfg, target)

    def robustness(self, cfg):
        return robustness(self.o, cfg, self.caches[cfg.model])


class Maker:
    label = "maker"
    default = MakerConfig("pool · all", theta=0.02, horizon_h=4.0)

    def __init__(self, o, trades):
        self.o, self.trades = o, trades

    def configs(self):
        return [MakerConfig(m, theta=t, horizon_h=h) for m in MODELS
                for t in (0.0, 0.01, 0.02, 0.04) for h in (1.0, 4.0)]

    def simulate(self, cfg, probs=None, rows=None):
        rows = rows if rows is not None else self.o.rows
        probs = probs if probs is not None else self.o.preds[cfg.model]
        return run_maker(rows, probs, cfg, self.trades)

    def placebos(self, cfg, target, seed=0):
        rows = self.o.rows
        k = rows.mask.shape[1]
        inner = interior_market(rows.quotes["bid"], rows.quotes["ask"], rows.mask)
        coherent = np.isfinite(inner).all(1)
        base = dict(cfg.__dict__)
        out = {"oracle (must never lose)": self.simulate(
                   MakerConfig(**{**base, "theta": 0.0}), np.eye(k)[rows.y] * rows.mask),
               # quoting around the in-spread price with no information: spread capture minus
               # adverse selection. The model has to beat this, not zero.
               "uninformed market maker": self.simulate(
                   MakerConfig(**{**base, "theta": 0.0}), inner[coherent],
                   rows.take(np.flatnonzero(coherent)))}
        rng = np.random.default_rng(seed)
        best, gap_best = None, None
        for sigma in (0.05, 0.1, 0.2, 0.3, 0.5, 0.8):
            z = rows.probs["market"] * np.exp(rng.normal(0, sigma, rows.mask.shape))
            z = np.where(rows.mask, z, 0)
            z /= z.sum(1, keepdims=True)
            led = self.simulate(cfg, z)
            gap = abs(len(led) - target)
            if gap_best is None or gap < gap_best:
                best, gap_best = (sigma, led), gap
        out["noise_matched_turnover"] = best[1]
        res = {k_: {"trades": int(len(v)), "pnl": float(v["pnl"].sum()) if len(v) else 0.0,
                    "losing_trades": int((v["pnl"] < 0).sum()) if len(v) else 0}
               for k_, v in out.items()}
        res["noise_matched_turnover"]["sigma"] = best[0]
        return res

    def robustness(self, cfg):
        days = self.o.rows.meta["day"]
        out = []
        for label, kw in [("base: trade-through fills", {}),
                          ("touch fills, 50% queue share", {"fill": "touch"}),
                          ("maker fee 0.0175", {"maker_fee_rate": 0.0175}),
                          ("no price improvement", {"improve": False}),
                          ("horizon 1h", {"horizon_h": 1.0}), ("horizon to close", {"horizon_h": 48.0}),
                          ("size ×10", {"stake": cfg.stake * 10})]:
            led = self.simulate(MakerConfig(**{**cfg.__dict__, **kw}))
            d = daily_pnl(led, days).to_numpy()
            out.append({"scenario": label, "pnl": float(d.sum()),
                        "sharpe_ann": stats.annualise(stats.sharpe(d)), "trades": int(len(led)),
                        "fill_ratio": float(led["fill_ratio"].mean()) if len(led) else 0.0})
        return out


def run_read(ex, boot):
    o = ex.o
    configs = ex.configs()
    days = o.rows.meta["day"]
    ledgers, daily = {}, {}
    for c in configs:
        led = ex.simulate(c)
        ledgers[c.name], daily[c.name] = led, daily_pnl(led, days)
    sel_daily, sel_ledger, picks = nested(o, configs, daily, ledgers, ex.default.name)
    M = np.column_stack([daily[c.name].to_numpy() for c in configs])
    srs = np.array([stats.sharpe(M[:, j]) for j in range(M.shape[1])])
    res = {"execution": ex.label, "configs": len(configs), "picks": picks,
           "selected": summarise(sel_daily, sel_ledger, boot),
           "deflated_sharpe": stats.deflated_sharpe(sel_daily.to_numpy(), len(configs),
                                                    float(np.var(srs, ddof=1))),
           "pbo": stats.pbo_cscv(M),
           "edge_realisation": edge_realisation(sel_ledger),
           "all_configs": sorted([{"config": c.name, "pnl": float(daily[c.name].sum()),
                                   "sharpe_ann": stats.annualise(stats.sharpe(daily[c.name])),
                                   "trades": int(len(ledgers[c.name]))} for c in configs],
                                 key=lambda r: -r["sharpe_ann"])}
    if len(sel_ledger):
        for g in ("period", "city"):
            res["by_" + g] = {k: {"pnl": float(v["pnl"].sum()), "trades": int(len(v)),
                                  "per_contract": float(v["pnl"].sum() / v["contracts"].sum())}
                              for k, v in sel_ledger.groupby(g)}
    top = pd.Series([p["config"] for p in picks]).mode().iloc[0]
    cfg = next(c for c in configs if c.name == top)
    res["robustness_config"] = top
    res["robustness"] = ex.robustness(cfg)
    res["placebos"] = ex.placebos(cfg, res["selected"]["trades"])
    return res


def markdown(res):
    L = ["# Backtest", "",
         "**Taker:** fills at the read-time quote, Kalshi quadratic fees, size capped at a share of "
         "post-read volume. **Maker:** rest at or inside the touch, filled only by later prints "
         "strictly through our price (no queue model needed). Both held to settlement; fixed "
         "$10,000 bankroll; daily PnL, Sharpe annualised by √365. **Headline = nested "
         "selection**: each quarter trades the config with the best Sharpe on earlier quarters "
         "only. See docs/EVALS.md for what each number can and cannot tell you.", ""]
    for read, r in res["results"].items():
        s, dsr, pbo = r["selected"], r["deflated_sharpe"], r["pbo"]
        L += ["## {}".format(read), "",
              "| | |", "|---|---|",
              "| PnL (nested, out-of-sample) | **${:,.0f}** over {} days, {} trades |".format(
                  s["pnl"], s["days"], s["trades"]),
              "| Sharpe (ann.) | **{:.2f}** [{:.2f}, {:.2f}] stationary bootstrap |".format(
                  s["sharpe_ann"], *s["sharpe_ann_ci"]),
              "| Newey-West t | {:.2f} |".format(s["nw_t"]),
              "| Deflated Sharpe | **{:.3f}** ({} configs tried; ≥0.95 to believe) |".format(
                  dsr["dsr"], dsr["n_trials"]),
              "| PBO (CSCV) | **{:.2f}** ({} splits; ≤0.2 to believe) |".format(
                  pbo["pbo"], pbo["splits"]),
              "| Max drawdown | ${:,.0f} |".format(s["max_drawdown"])]
        if "attribution" in s:
            a = s["attribution"]
            L += ["| Hit rate | {:.1%} |".format(s["hit_rate"]),
                  "| Return on outlay | {:+.2%} |".format(s["return_on_outlay"]),
                  "| EV vs realised per contract | {:+.4f} vs {:+.4f} |".format(
                      s["ev_per_contract"], s["realised_per_contract"]),
                  "| Attribution | alpha vs mid ${:,.0f} · spread ${:,.0f} · fees ${:,.0f} |".format(
                      a["alpha_vs_mid"], a["spread_paid"], a["fees"])]
        if r.get("by_period"):
            L += ["", "By period:", "", "| Period | PnL | Trades | per contract |",
                  "|---|---:|---:|---:|"]
            for k, v in r["by_period"].items():
                L.append("| {} | ${:,.0f} | {} | {:+.4f} |".format(k, v["pnl"], v["trades"],
                                                                   v["per_contract"]))
        if r.get("by_city"):
            L += ["", "By city:", "", "| City | PnL | Trades | per contract |", "|---|---:|---:|---:|"]
            for k, v in r["by_city"].items():
                L.append("| {} | ${:,.0f} | {} | {:+.4f} |".format(k, v["pnl"], v["trades"],
                                                                   v["per_contract"]))
        L += ["", "Engine checks:", "", "| Check | Trades | PnL | Losing trades |",
              "|---|---:|---:|---:|"]
        for k, v in r["placebos"].items():
            L.append("| {} | {} | ${:,.0f} | {} |".format(k, v["trades"], v["pnl"], v["losing_trades"]))
        L += ["", "Robustness ({}):".format(r["robustness_config"]), "",
              "| Scenario | PnL | Sharpe | Trades |", "|---|---:|---:|---:|"]
        for v in r["robustness"]:
            L.append("| {} | ${:,.0f} | {:.2f} | {} |".format(v["scenario"], v["pnl"],
                                                             v["sharpe_ann"], v["trades"]))
        L += ["", "Top configs over the full period (in-sample ceiling, not a result):", "",
              "| Config | PnL | Sharpe | Trades |", "|---|---:|---:|---:|"]
        for v in r["all_configs"][:6]:
            L.append("| {} | ${:,.0f} | {:.2f} | {} |".format(v["config"], v["pnl"],
                                                             v["sharpe_ann"], v["trades"]))
        L.append("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cities", nargs="*")
    ap.add_argument("--reads", nargs="*")
    ap.add_argument("--boot", type=int, default=1000)
    ap.add_argument("--execution", nargs="+", default=["taker", "maker"], choices=["taker", "maker"])
    ap.add_argument("--out", default="results/backtest")
    a = ap.parse_args()
    t0 = time.time()
    ls = dataset.load(a.cities)
    oos = oos_predictions(ls, default_suite())
    trades = load_trades(sorted(ls.meta["city"].unique())) if "maker" in a.execution else {}
    results = {}
    for read, o in oos.items():
        if a.reads and read not in a.reads:
            continue
        for exe in a.execution:
            if exe == "maker" and not trades:
                print("   maker: no trades in data/trades, run scripts/fetch_trades.py", flush=True)
                continue
            ex = Taker(o) if exe == "taker" else Maker(o, trades)
            key = "{} · {}".format(read, exe)
            print("== {}: {} ladders".format(key, len(o.rows)), flush=True)
            results[key] = run_read(ex, a.boot)
            s = results[key]["selected"]
            print("   nested PnL ${:,.0f}  Sharpe {:.2f}  DSR {:.3f}  PBO {:.2f}  ({:.0f}s)".format(
                s["pnl"], s["sharpe_ann"], results[key]["deflated_sharpe"]["dsr"],
                results[key]["pbo"]["pbo"], time.time() - t0), flush=True)
    try:
        sha = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                      stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        sha = None
    res = {"config": vars(a), "git": sha, "cities": sorted(ls.meta["city"].unique()),
           "results": results, "seconds": round(time.time() - t0, 1)}
    p = pathlib.Path(a.out)
    p.parent.mkdir(exist_ok=True)
    p.with_suffix(".json").write_text(json.dumps(res, indent=2, default=str))
    p.with_suffix(".md").write_text(markdown(res))
    print(markdown(res))


if __name__ == "__main__":
    main()
