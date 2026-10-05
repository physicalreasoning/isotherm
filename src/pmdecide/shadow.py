"""Live shadow scoring (G5) of the frozen lockbox strategy. No orders are ever placed.

  score    within [16:00, 18:00) local the day before, read each city's live ladder and the
           latest GFS MOS run already public, apply the frozen model, log every bucket's
           probabilities and the paper trades the strategy would take at the live quote
  settle   once a ladder has settled, record each market's result and final volume;
           capacity (participation x volume after the read) is applied here, exactly as in
           the backtest, because it cannot be known at the read
  report   cumulative and monthly PnL, by city, live log score against the market

The ledger lives in CSVs under `shadow/` and is committed by CI on its own branch, so
every prediction carries a commit timestamp from before the outcome existed.
"""

from __future__ import annotations

import json
import pathlib
import time
from typing import Dict, List

import numpy as np
import pandas as pd

from . import iem, kalshi, metrics
from .backtest import _instruments, kalshi_fee, kelly_ladder
from .dataset import regime
from .emos import GaussianModel, daytime_max_table, forecast_at, interval_probs
from .weather import AVAILABILITY_LAG, CITIES, bucket_interval, is_partition

EPS = 1e-3


def load_frozen(path="shadow/frozen.json") -> dict:
    return json.loads(pathlib.Path(path).read_text())


def event_ticker(series: str, day: pd.Timestamp) -> str:
    return "{}-{}".format(series, day.strftime("%y%b%d").upper())


def due(city, now_utc: pd.Timestamp, window=(16, 18)):
    """(target day, read due?) for this city at `now_utc`: due in [16:00, 18:00) local."""
    local = now_utc.tz_convert(city.tz)
    return (local.normalize() + pd.Timedelta(days=1)).tz_localize(None), window[0] <= local.hour < window[1]


def _ladder(rows):
    rows = [r for r in rows if r.get("strike_type")]
    iv = [
        bucket_interval(
            r["strike_type"], kalshi.to_float(r.get("floor_strike")), kalshi.to_float(r.get("cap_strike"))
        )
        for r in rows
    ]
    order = np.argsort([a for a, _ in iv])
    return [rows[i] for i in order], [iv[i] for i in order]


def score_city(key: str, now_utc: pd.Timestamp, frozen: dict, force: bool = False) -> Dict:
    city = CITIES[key]
    day, is_due = due(city, now_utc, frozen["strategy"]["window_local_hours"])
    ev = event_ticker(city.series, day)
    base = {
        "scored_at": now_utc.isoformat(),
        "city": key,
        "event": ev,
        "day": str(day.date()),
        "model_hash": frozen["hash"],
    }
    if not (is_due or force):
        return {**base, "status": "not_due"}
    rows, iv = _ladder(kalshi.get("markets", event_ticker=ev, limit=100).get("markets", []))
    if not rows or not is_partition(iv):
        return {**base, "status": "no_ladder"}
    mos = iem.mos(
        city.station,
        "GFS",
        str((day - pd.Timedelta(days=3)).date()),
        str((day + pd.Timedelta(days=1)).date()),
    )
    tab = daytime_max_table(mos, "n_x", AVAILABILITY_LAG["GFS"]) if len(mos) else None
    fc = (
        forecast_at(tab, pd.DataFrame({"target": [day], "read_time": [now_utc]}))
        if tab is not None and len(tab)
        else None
    )
    if fc is None or not np.isfinite(fc["fcst"].iloc[0]):
        return {**base, "status": "no_forecast"}
    f = frozen["emos_gfs"][key]
    em = GaussianModel("emos", np.array(f["beta"]), np.array(f["gamma"]))
    mu, sg = em.params(np.array([fc["fcst"].iloc[0]]), np.array([day.dayofyear]))
    lo = np.array([[a for a, _ in iv]])
    hi = np.array([[b for _, b in iv]])
    pf = np.clip(interval_probs(mu, sg, lo, hi)[0], EPS, None)
    pf /= pf.sum()
    bid = np.array([kalshi.to_float(r.get("yes_bid_dollars")) or 0.0 for r in rows])
    ask = np.array([kalshi.to_float(r.get("yes_ask_dollars")) or 1.0 for r in rows])
    ask = np.where(ask <= 0, 1.0, ask)
    pm = np.clip((bid + ask) / 2, EPS, None)
    pm /= pm.sum()
    w = frozen["pool_weights"]
    z = w["market"] * np.log(pm) + w["emos_gfs"] * np.log(pf)
    p = np.exp(z - z.max())
    p /= p.sum()
    s = frozen["strategy"]
    mask = np.ones(len(rows), bool)
    price, cost, payoff, evs, ok = _instruments(p, bid, ask, mask, 0, 0.07)
    x = kelly_ladder(p, cost, payoff, ok & (evs > 0))
    n = np.floor(s["fraction"] * x * s["bankroll"] / s["slots"])
    k = len(rows)
    preds, trades = [], []
    for j, r in enumerate(rows):
        preds.append(
            {
                **base,
                "ticker": r["ticker"],
                "bucket": j,
                "lo": iv[j][0],
                "hi": iv[j][1],
                "bid": bid[j],
                "ask": ask[j],
                "p_market": pm[j],
                "p_emos": pf[j],
                "p_model": p[j],
                "gfs_fcst": float(fc["fcst"].iloc[0]),
                "gfs_runtime": str(fc["runtime"].iloc[0]),
                "volume_at_read": kalshi.volume(r),
            }
        )
    for i in np.flatnonzero(n > 0):
        b = i % k
        trades.append(
            {
                **base,
                "ticker": rows[b]["ticker"],
                "bucket": int(b),
                "side": "yes" if i < k else "no",
                "price": float(price[i]),
                "contracts_intended": float(n[i]),
                "ev_per_contract": float(evs[i]),
                "p_model": float(payoff[i] @ p),
                "volume_at_read": kalshi.volume(rows[b]),
            }
        )
    return {**base, "status": "scored", "predictions": preds, "trades": trades}


def _append(path: pathlib.Path, rows: List[dict], key: List[str]):
    if not rows:
        return 0
    new = pd.DataFrame(rows)
    if path.exists():
        old = pd.read_csv(path)
        new = new[~new.set_index(key).index.isin(old.set_index(key).index)]
        out = pd.concat([old, new], ignore_index=True)
    else:
        out = new
    out.to_csv(path, index=False)
    return len(new)


def score_all(root: pathlib.Path, now_utc=None, force=False, cities=None) -> List[dict]:
    frozen = load_frozen(root / "frozen.json")
    now_utc = now_utc or pd.Timestamp.now(tz="UTC")
    pred_p, trade_p, log_p = root / "predictions.csv", root / "trades.csv", root / "runs.csv"
    done = set(pd.read_csv(pred_p)["event"]) if pred_p.exists() else set()
    log = []
    for key in cities or CITIES:
        day, _ = due(CITIES[key], now_utc)
        if event_ticker(CITIES[key].series, day) in done and not force:
            continue
        try:
            r = score_city(key, now_utc, frozen, force)
        except Exception as e:  # one city failing must not stop the others
            r = {"scored_at": now_utc.isoformat(), "city": key, "status": "error: " + str(e)[:120]}
        if r["status"] == "scored":
            _append(pred_p, r.pop("predictions"), ["event", "ticker"])
            _append(trade_p, r.pop("trades"), ["event", "ticker", "side"])
        if r["status"] != "not_due":
            log.append({k: v for k, v in r.items() if k not in ("predictions", "trades")})
    _append(log_p, log, ["scored_at", "city"])
    return log


def settle(root: pathlib.Path) -> int:
    pred_p, out_p = root / "predictions.csv", root / "outcomes.csv"
    if not pred_p.exists():
        return 0
    preds = pd.read_csv(pred_p)
    have = set(pd.read_csv(out_p)["ticker"]) if out_p.exists() else set()
    todo = preds.loc[~preds["ticker"].isin(have), "event"].unique()
    rows = []
    for ev in todo:
        ms = kalshi.get("markets", event_ticker=ev, limit=100).get("markets", [])
        if not ms or not all(m.get("result") in ("yes", "no") for m in ms):
            continue
        for m in ms:
            rows.append(
                {
                    "event": ev,
                    "ticker": m["ticker"],
                    "y": kalshi.result_yes(m),
                    "final_volume": kalshi.volume(m),
                    "regime": regime(m.get("rules_primary") or ""),
                    "settled_seen_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
            )
    return _append(out_p, rows, ["ticker"])


WINDOW_DAYS = 30
MIN_DAYS = 20


def decay_status(days: np.ndarray, gain: np.ndarray, window: int = WINDOW_DAYS) -> dict:
    """Rolling log-score gain vs the market, and the stop rule from issue #3.

    Windows are consecutive and non-overlapping, counted back from the latest settled
    day. STOP when the latest two windows each have a date-block 95% CI entirely below
    zero; INSUFFICIENT_DATA until the latest window holds MIN_DAYS settled days.
    """
    d = pd.to_datetime(pd.Series(days)).dt.normalize()
    end = d.max()
    windows = []
    for i in range(6):
        hi = end - pd.Timedelta(days=window * i)
        lo = hi - pd.Timedelta(days=window)
        s = ((d > lo) & (d <= hi)).to_numpy()
        n_days = int(d[s].nunique())
        if n_days == 0:
            break
        w = {
            "from": str((lo + pd.Timedelta(days=1)).date()),
            "to": str(hi.date()),
            "days": n_days,
            "gain": float(gain[s].mean()),
        }
        if n_days >= 5:
            w["ci"] = metrics.date_bootstrap_mean(d[s].to_numpy(), gain[s], 1000)
        windows.append(w)
    if not windows or windows[0]["days"] < MIN_DAYS:
        status = "INSUFFICIENT_DATA"
    elif (
        len(windows) >= 2
        and all(w.get("ci", [0, 0])[1] < 0 for w in windows[:2])
        and windows[1]["days"] >= MIN_DAYS
    ):
        status = "STOP"
    else:
        status = "OK"
    return {"status": status, "window_days": window, "windows": windows}


def report(root: pathlib.Path, participation: float = 0.05) -> dict:
    pred_p, trade_p, out_p = root / "predictions.csv", root / "trades.csv", root / "outcomes.csv"
    if not (pred_p.exists() and out_p.exists()):
        return {"settled_ladders": 0}
    preds = pd.read_csv(pred_p).merge(pd.read_csv(out_p), on=["event", "ticker"])
    res = {"settled_ladders": int(preds["event"].nunique())}
    if res["settled_ladders"]:
        g = preds.groupby("event")
        ll_m = -np.log(g.apply(lambda d: d.loc[d.y == 1, "p_market"].sum(), include_groups=False).clip(1e-12))
        ll_s = -np.log(g.apply(lambda d: d.loc[d.y == 1, "p_model"].sum(), include_groups=False).clip(1e-12))
        days = g["day"].first()
        gain = (ll_m - ll_s).to_numpy()
        res["log_score_gain_vs_market"] = float(gain.mean())
        if len(gain) >= 5:
            res["gain_ci"] = metrics.date_bootstrap_mean(days.to_numpy(), gain, 1000)
        res["decay"] = decay_status(days.to_numpy(), gain)
    if trade_p.exists():
        t = pd.read_csv(trade_p).merge(pd.read_csv(out_p), on=["event", "ticker"])
        if len(t):
            cap = np.floor(participation * np.clip(t["final_volume"] - t["volume_at_read"], 0, None))
            t["contracts"] = np.minimum(t["contracts_intended"], cap)
            win = np.where(t["side"] == "yes", t["y"], 1 - t["y"])
            fee = kalshi_fee(t["price"].to_numpy(), t["contracts"].to_numpy())
            t["pnl"] = t["contracts"] * (win - t["price"]) - fee
            t = t[t["contracts"] > 0]
            res.update(
                {
                    "trades": int(len(t)),
                    "pnl": float(t["pnl"].sum()),
                    "hit_rate": float((t["pnl"] > 0).mean()) if len(t) else None,
                    "by_month": {k: float(v) for k, v in t.groupby(t["day"].str[:7])["pnl"].sum().items()},
                    "by_city": {k: float(v) for k, v in t.groupby("city")["pnl"].sum().items()},
                    "by_regime": (
                        {k: float(v) for k, v in t.groupby("regime")["pnl"].sum().items()}
                        if "regime" in t
                        else {}
                    ),
                }
            )
    return res
