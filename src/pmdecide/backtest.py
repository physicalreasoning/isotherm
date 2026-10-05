"""Event-level backtest for ladder markets: fees, fills, sizing, and a trade ledger.

Execution model (taker, conservative)
  At the read time we may buy YES at the bucket's ask, or NO at 1 - bid. Nothing
  better: no queue priority, no price improvement, no maker rebates. Size is capped
  at `participation` x the contracts that traded in that bucket *after* the read
  (a capacity cap, never a signal) and by `max_contracts`. `slip` adds ticks to
  every fill to model latency; the report sweeps it. Positions are held to
  settlement, which is how these contracts are overwhelmingly traded, so there is
  no exit cost to model.

Fees
  Kalshi's quadratic taker fee: ceil(rate * C * P * (1 - P)) to the cent, per
  order, `rate` = 0.07 x the series' `fee_multiplier` (1 for these series).

Sizing
  threshold  buy every instrument whose expected value per contract under the
             model exceeds `theta` after fees; fixed dollar stake per instrument.
  kelly      the ladder's buckets are mutually exclusive and exhaustive, so the
             whole ladder is one bet. Maximise E_p[log W] over YES and NO holdings
             jointly (a concave program; Kelly 1956, horse-race form), then scale
             by `fraction`. Fractional Kelly is the standard hedge against the
             model's own estimation error.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.optimize import minimize

FEE_RATE = 0.07
TICK = 0.01


def kalshi_fee(price, contracts, rate: float = FEE_RATE):
    """Taker fee in dollars for one order of `contracts` at `price`, rounded up to the cent."""
    price, contracts = np.asarray(price, float), np.asarray(contracts, float)
    raw = rate * contracts * price * (1 - price)
    return np.where(contracts > 0, np.ceil(np.round(raw * 100, 9)) / 100, 0.0)


@dataclass
class Config:
    model: str
    sizing: str = "kelly"  # "kelly" | "threshold"
    fraction: float = 0.25  # Kelly fraction
    theta: float = 0.02  # minimum EV per contract, dollars, after fees
    stake: float = 100.0  # threshold sizing: dollars per instrument
    bankroll: float = 10_000.0  # fixed (non-compounding) for clean statistics
    slots: int = 7  # concurrent ladders sharing the bankroll per read
    participation: float = 0.05
    max_contracts: int = 5_000
    slip: int = 0  # extra ticks paid on every fill
    fee_rate: float = FEE_RATE
    extra: dict = field(default_factory=dict)

    @property
    def name(self):
        s = "{} · {}".format(
            self.model,
            "kelly {:.2f}".format(self.fraction) if self.sizing == "kelly" else "θ {:.2f}".format(self.theta),
        )
        return s


def _instruments(p, bid, ask, mask, slip, fee_rate):
    """YES and NO contracts of one ladder: cost per contract (incl. linearised fee), payoff matrix."""
    k = int(mask.sum())
    p, bid, ask = p[:k], bid[:k], ask[:k]
    py = np.clip(ask + slip * TICK, 0, 1)  # YES price
    pn = np.clip(1 - bid + slip * TICK, 0, 1)  # NO price
    ok_y = ask < 1.0  # there is an offer
    ok_n = bid > 0.0  # there is a bid to sell into
    price = np.concatenate([py, pn])
    ok = np.concatenate([ok_y, ok_n]) & (price > 0) & (price < 1)
    cost = price + fee_rate * price * (1 - price)
    eye = np.eye(k)
    payoff = np.concatenate([eye, 1 - eye])  # (2k instruments, k outcomes)
    ev = payoff @ p - cost
    return price, cost, payoff, ev, ok


def interior_market(bid: np.ndarray, ask: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """The coherent distribution inside every spread: p_j = bid_j + λ (ask_j - bid_j), Σ p = 1.

    It exists iff Σ bid ≤ 1 ≤ Σ ask, the ladder's no-arbitrage condition. Under it every
    YES and NO contract has negative expected value after costs, so a correct engine
    must not trade it. Rows violating the condition are true arbitrage and come back NaN.
    """
    b = np.where(mask, bid, 0.0)
    a = np.where(mask, ask, 0.0)
    sb, sa = b.sum(1, keepdims=True), a.sum(1, keepdims=True)
    lam = (1 - sb) / np.where(sa > sb, sa - sb, np.nan)
    p = b + lam * (a - b)
    ok = (sb <= 1) & (sa >= 1)
    return np.where(ok & mask, p, np.where(ok, 0.0, np.nan))


def kelly_ladder(p, cost, payoff, cand):
    """Full-Kelly holdings (contracts per $1 of slot bankroll) over candidate instruments."""
    idx = np.flatnonzero(cand)
    if len(idx) == 0:
        return np.zeros(len(cost))
    c, A = cost[idx], payoff[idx]  # A: (m, k)

    def neg(x):
        w = 1 - x @ c + x @ A
        if np.any(w <= 1e-9):
            return 1e6
        return -(p @ np.log(w))

    def grad(x):
        w = 1 - x @ c + x @ A
        return -((A - c[:, None]) @ (p / w))

    cons = [{"type": "ineq", "fun": lambda x: 1 - x @ c, "jac": lambda x: -c}]
    r = minimize(
        neg,
        np.zeros(len(idx)),
        jac=grad,
        bounds=[(0, None)] * len(idx),
        constraints=cons,
        method="SLSQP",
        options={"maxiter": 200, "ftol": 1e-10},
    )
    x = np.zeros(len(cost))
    if r.success or r.status == 9:
        x[idx] = np.clip(r.x, 0, None)
    return x


def run(rows, probs: np.ndarray, cfg: Config, kelly_cache: dict | None = None) -> pd.DataFrame:
    """Simulate one strategy on a LadderSet; returns the trade ledger.

    `kelly_cache` (one dict per model) memoises full-Kelly solutions so that
    configurations differing only in `fraction` share one solve per ladder.
    """
    bid, ask, vol = rows.quotes["bid"], rows.quotes["ask"], rows.quotes["vol_after"]
    slot = cfg.bankroll / cfg.slots
    out = []
    meta = rows.meta
    mid_all = rows.probs["market"]
    for i in range(len(rows)):
        m = rows.mask[i]
        k = int(m.sum())
        price, cost, payoff, ev, ok = _instruments(probs[i], bid[i], ask[i], m, cfg.slip, cfg.fee_rate)
        if cfg.sizing == "threshold":
            take = ok & (ev > cfg.theta)
            n = np.where(take, np.floor(cfg.stake / np.maximum(cost, 1e-9)), 0)
        else:
            cand = ok & (ev > 0)
            key = (i, cfg.slip, cfg.fee_rate)
            if kelly_cache is not None and key in kelly_cache:
                x = kelly_cache[key]
            else:
                x = kelly_ladder(probs[i][:k], cost, payoff, cand)
                if kelly_cache is not None:
                    kelly_cache[key] = x
            n = np.floor(cfg.fraction * x * slot)
        cap = np.minimum(
            np.floor(cfg.participation * np.concatenate([vol[i][:k], vol[i][:k]])), cfg.max_contracts
        )
        n = np.minimum(n, cap)
        for j in np.flatnonzero(n > 0):
            side = "yes" if j < k else "no"
            b = j % k
            fee = float(kalshi_fee(price[j], n[j], cfg.fee_rate))
            win = float(payoff[j, rows.y[i]])
            mid = 0.5 * (bid[i][b] + ask[i][b])
            mid = mid if side == "yes" else 1 - mid
            out.append(
                {
                    "day": meta["day"].iat[i],
                    "city": meta["city"].iat[i],
                    "event": meta["event"].iat[i],
                    "read": meta["read"].iat[i],
                    "period": meta["period"].iat[i],
                    "bucket": int(b),
                    "side": side,
                    "contracts": float(n[j]),
                    "price": float(price[j]),
                    "mid": float(mid),
                    "fee": fee,
                    "outlay": float(n[j] * price[j] + fee),
                    "payoff": float(n[j] * win),
                    "pnl": float(n[j] * (win - price[j]) - fee),
                    "ev_per_contract": float(ev[j]),
                    "p_model": float(payoff[j, :k] @ probs[i][:k]),
                    "p_market": float(payoff[j, :k] @ mid_all[i][:k]),
                }
            )
    return pd.DataFrame(out)


def daily_pnl(ledger: pd.DataFrame, days) -> pd.Series:
    """PnL per calendar day over every eligible day, zero on days with no trade."""
    idx = pd.DatetimeIndex(sorted(pd.unique(pd.to_datetime(days))))
    if ledger.empty:
        return pd.Series(0.0, index=idx)
    return ledger.groupby("day")["pnl"].sum().reindex(idx, fill_value=0.0)


# ---------------------------------------------------------------------------- maker


@dataclass
class MakerConfig:
    """Passive execution: rest a limit order at the read time, fill only when prints prove it.

    Quotes join the touch, or improve it by one tick when the spread is at least 2¢ (a new
    price level, so we are first in its queue). A resting order is filled only by later
    trades from the opposite taker side:

      fill="through"  prints strictly through our price. Any order at our level would have
                      been filled first, so this is a lower bound on fills that needs no
                      queue model. Headline.
      fill="touch"    also counts prints *at* our price, times `touch_share` of their size.
                      An upper bound, for sensitivity only.

    Fills are adversely selected by construction: the market trades through a bid exactly
    when the price is falling. That cost is the point of modelling them this way.
    """

    model: str
    theta: float = 0.02
    stake: float = 100.0
    horizon_h: float = 4.0
    improve: bool = True
    fill: str = "through"
    touch_share: float = 0.5
    maker_fee_rate: float = 0.0  # weather series: fee_type "quadratic", no maker fee
    max_contracts: int = 5_000

    @property
    def name(self):
        return "{} · maker θ {:.2f} · {:g}h".format(self.model, self.theta, self.horizon_h)


def load_trades(cities, root="data/trades"):
    """{ticker: (ts, yes_price, count, taker_yes)} sorted by time, for the given cities."""
    import pathlib

    out = {}
    for c in cities:
        f = pathlib.Path(root) / "{}.parquet".format(c)
        if not f.exists():
            continue
        df = pd.read_parquet(f).sort_values(["ticker", "ts"])
        for t, g in df.groupby("ticker", sort=False):
            out[t] = (
                g["ts"].to_numpy(),
                g["yes_price"].to_numpy(),
                g["count"].to_numpy(),
                g["taker_yes"].to_numpy(),
            )
    return out


def maker_prices(bid, ask, improve: bool):
    """Our resting YES bid and YES offer for each bucket."""
    wide = (ask - bid) >= 0.02 - 1e-9
    qb = np.where(improve & wide, bid + TICK, bid)
    qa = np.where(improve & wide, ask - TICK, ask)
    return np.clip(qb, TICK, 1 - TICK), np.clip(qa, TICK, 1 - TICK)


def _filled(tr, t0, t1, price, taker_yes_side: bool, cfg: MakerConfig):
    if tr is None:
        return 0.0
    ts, px, cnt, ty = tr
    a, b = np.searchsorted(ts, t0, "right"), np.searchsorted(ts, t1, "right")
    px, cnt, ty = px[a:b], cnt[a:b], ty[a:b]
    side = ty if taker_yes_side else ~ty
    if taker_yes_side:  # our YES offer at `price`, lifted by YES takers
        through, touch = px > price + 1e-9, np.isclose(px, price)
    else:  # our YES bid at `price`, hit by NO takers
        through, touch = px < price - 1e-9, np.isclose(px, price)
    vol = cnt[side & through].sum()
    if cfg.fill == "touch":
        vol += cfg.touch_share * cnt[side & touch].sum()
    return float(vol)


def run_maker(rows, probs: np.ndarray, cfg: MakerConfig, trades: dict) -> pd.DataFrame:
    bid, ask = rows.quotes["bid"], rows.quotes["ask"]
    meta, mid_all = rows.meta, rows.probs["market"]
    out = []
    for i in range(len(rows)):
        k = int(rows.mask[i].sum())
        qb, qa = maker_prices(bid[i][:k], ask[i][:k], cfg.improve)
        p = probs[i][:k]
        t0 = int(meta["read_ts"].iat[i])
        t1 = min(t0 + int(cfg.horizon_h * 3600), int(meta["close_ts"].iat[i]))
        tick = meta["tickers"].iat[i]
        for j in range(k):
            y = 1.0 if rows.y[i] == j else 0.0
            mid = 0.5 * (bid[i][j] + ask[i][j])
            # (side, our price paid per contract, model P(win), payoff if win, taker side that fills us)
            for side, price, pwin, win, taker_yes in (
                ("yes", qb[j], p[j], y, False),
                ("no", 1 - qa[j], 1 - p[j], 1 - y, True),
            ):
                fee_c = cfg.maker_fee_rate * price * (1 - price)
                ev = pwin - price - fee_c
                if ev <= cfg.theta:
                    continue
                want = min(np.floor(cfg.stake / (price + fee_c)), cfg.max_contracts)
                level = qb[j] if side == "yes" else qa[j]
                got = _filled(trades.get(tick[j]), t0, t1, level, taker_yes, cfg)
                n = float(min(want, np.floor(got)))
                if n <= 0:
                    continue
                fee = float(kalshi_fee(price, n, cfg.maker_fee_rate)) if cfg.maker_fee_rate else 0.0
                out.append(
                    {
                        "day": meta["day"].iat[i],
                        "city": meta["city"].iat[i],
                        "event": meta["event"].iat[i],
                        "read": meta["read"].iat[i],
                        "period": meta["period"].iat[i],
                        "bucket": j,
                        "side": side,
                        "contracts": n,
                        "price": float(price),
                        "mid": float(mid if side == "yes" else 1 - mid),
                        "fee": fee,
                        "outlay": float(n * price + fee),
                        "payoff": n * win,
                        "pnl": float(n * (win - price) - fee),
                        "ev_per_contract": float(ev),
                        "p_model": float(pwin),
                        "p_market": float(mid_all[i][j] if side == "yes" else 1 - mid_all[i][j]),
                        "fill_ratio": n / want if want else 0.0,
                    }
                )
    return pd.DataFrame(out)
