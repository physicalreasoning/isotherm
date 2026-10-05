"""Backtest accounting and statistics. A wrong ledger makes every PnL number meaningless."""

import numpy as np
import pandas as pd

from pmdecide import stats
from pmdecide.backtest import Config, kalshi_fee, kelly_ladder, run
from pmdecide.dataset import LadderSet


def test_kalshi_fee_matches_the_published_formula():
    assert kalshi_fee(0.50, 100) == 1.75  # 0.07 * 100 * 0.25
    assert kalshi_fee(0.01, 1) == 0.01  # 0.0693¢ rounds UP to 1¢
    assert kalshi_fee(0.30, 10) == 0.15  # 0.147 -> 0.15
    assert kalshi_fee(0.30, 0) == 0.0


def _ladder(p_true, bid, ask, y, n=1, vol=1e9):
    k = len(bid)
    meta = pd.DataFrame(
        {
            "day": pd.date_range("2025-01-01", periods=n),
            "city": "X",
            "event": ["E{}".format(i) for i in range(n)],
            "read": "d0_08",
            "period": "2025H1",
        }
    )
    mid = (np.array(bid) + np.array(ask)) / 2
    tile = lambda a: np.tile(np.asarray(a, float), (n, 1))  # noqa: E731
    return LadderSet(
        meta,
        tile(np.arange(k)),
        tile(np.arange(k) + 1),
        np.ones((n, k), bool),
        np.full(n, y),
        {"market": tile(mid / mid.sum()), "model": tile(p_true)},
        {"bid": tile(bid), "ask": tile(ask), "vol_after": tile([vol] * k)},
    )


def test_oracle_never_loses_and_pays_exactly_payoff_minus_cost_minus_fee():
    ls = _ladder([0, 1, 0], bid=[0.20, 0.40, 0.20], ask=[0.25, 0.45, 0.25], y=1)
    oracle = np.eye(3)[[1]]
    led = run(ls, oracle, Config("oracle", sizing="threshold", theta=0.0, stake=100))
    assert len(led) and (led["pnl"] > 0).all()
    r = led[led.side == "yes"].iloc[0]
    assert np.isclose(r.pnl, r.contracts * (1 - r.price) - r.fee)


def test_trading_the_market_mid_finds_no_edge():
    ls = _ladder([0.2, 0.5, 0.3], bid=[0.18, 0.48, 0.28], ask=[0.22, 0.52, 0.32], y=0, n=5)
    led = run(ls, ls.probs["market"], Config("market", sizing="threshold", theta=0.0))
    assert led.empty


def test_kelly_recovers_the_closed_form_binary_bet():
    # One instrument: YES at 0.50, no fee, true p = 0.6 -> Kelly wealth fraction 0.2,
    # i.e. 0.4 contracts per dollar of bankroll.
    p = np.array([0.6, 0.4])
    cost = np.array([0.5, 1.0, 1.0, 1.0])
    payoff = np.array([[1, 0], [0, 1], [0, 1], [1, 0]], float)
    x = kelly_ladder(p, cost, payoff, np.array([True, False, False, False]))
    assert abs(x[0] - 0.4) < 1e-3


def test_capacity_cap_binds():
    ls = _ladder([0, 1, 0], bid=[0.2, 0.4, 0.2], ask=[0.25, 0.45, 0.25], y=1, vol=100)
    led = run(
        ls, np.eye(3)[[1]], Config("oracle", sizing="threshold", theta=0.0, stake=1e6, participation=0.05)
    )
    assert led["contracts"].max() <= 5


def test_pbo_is_high_for_noise_and_low_for_a_real_edge():
    rng = np.random.default_rng(0)
    noise = rng.normal(0, 1, (600, 12))
    assert 0.3 < stats.pbo_cscv(noise, s=8)["pbo"] < 0.8
    edge = noise.copy()
    edge[:, 3] += 0.3
    assert stats.pbo_cscv(edge, s=8)["pbo"] < 0.1


def test_deflated_sharpe_penalises_many_trials():
    rng = np.random.default_rng(1)
    x = rng.normal(0.05, 1, 500)  # weak edge
    few = stats.deflated_sharpe(x, n_trials=1, var_sr_trials=0.0025)["dsr"]
    many = stats.deflated_sharpe(x, n_trials=200, var_sr_trials=0.0025)["dsr"]
    assert many < few


def test_stationary_bootstrap_covers_the_sharpe():
    x = np.random.default_rng(2).normal(0.1, 1, 800)
    lo, hi = stats.stationary_bootstrap(x, n=300)
    assert lo < stats.sharpe(x) < hi


def test_in_spread_market_never_trades_even_with_overround():
    # mids sum to 1.06. Raw mids are not a distribution (a NO contract would count 1.06 - p),
    # and normalised mids leave the spread; the in-spread coherent distribution must not trade.
    from pmdecide.backtest import interior_market

    ls = _ladder([0.3, 0.5, 0.26], bid=[0.29, 0.40, 0.25], ask=[0.31, 0.51, 0.37], y=1, n=3)
    inner = interior_market(ls.quotes["bid"], ls.quotes["ask"], ls.mask)
    assert np.allclose(inner.sum(1), 1)
    assert ((inner >= ls.quotes["bid"]) & (inner <= ls.quotes["ask"])).all()
    assert run(ls, inner, Config("mid", sizing="threshold", theta=0.0)).empty


def test_arbitrage_ladder_has_no_interior_distribution():
    from pmdecide.backtest import interior_market

    ls = _ladder([0.3, 0.5, 0.2], bid=[0.40, 0.40, 0.30], ask=[0.42, 0.45, 0.33], y=1)
    assert np.isnan(interior_market(ls.quotes["bid"], ls.quotes["ask"], ls.mask)).all()


# ------------------------------------------------------------------------- maker


def _with_meta(ls, read_ts=1000, close_ts=100000):
    ls.meta["read_ts"] = read_ts
    ls.meta["close_ts"] = close_ts
    ls.meta["tickers"] = [tuple("T{}".format(j) for j in range(ls.mask.shape[1]))] * len(ls)
    return ls


def _tr(ts, px, cnt, taker_yes):
    return (np.array(ts), np.array(px, float), np.array(cnt, float), np.array(taker_yes))


def test_maker_fills_only_on_trade_throughs_from_the_right_side():
    from pmdecide.backtest import MakerConfig, run_maker

    ls = _with_meta(_ladder([0.1, 0.8, 0.1], bid=[0.05, 0.50, 0.05], ask=[0.10, 0.60, 0.10], y=1))
    cfg = MakerConfig("m", theta=0.0, stake=100)  # bid on bucket 1 improves to 0.51
    trades = {
        "T1": _tr(
            [900, 1500, 1600, 1700], [0.40, 0.51, 0.55, 0.50], [999, 7, 50, 30], [False, False, False, False]
        )
    }
    led = run_maker(ls, ls.probs["model"], cfg, trades)
    yes = led[(led.bucket == 1) & (led.side == "yes")]
    # before the read: ignored; at our price: not a trade-through; above our bid: not a fill;
    # 0.50 < 0.51 from a NO taker: 30 contracts through
    assert yes.contracts.iloc[0] == 30
    assert np.isclose(yes.pnl.iloc[0], 30 * (1 - 0.51))


def test_maker_touch_fills_add_a_share_of_at_price_volume():
    from pmdecide.backtest import MakerConfig, run_maker

    ls = _with_meta(_ladder([0.1, 0.8, 0.1], bid=[0.05, 0.50, 0.05], ask=[0.10, 0.60, 0.10], y=1))
    trades = {"T1": _tr([1500], [0.51], [40], [False])}
    led = run_maker(ls, ls.probs["model"], MakerConfig("m", theta=0.0, fill="touch"), trades)
    assert led[(led.bucket == 1) & (led.side == "yes")].contracts.iloc[0] == 20


def test_maker_oracle_never_loses():
    from pmdecide.backtest import MakerConfig, run_maker

    ls = _with_meta(_ladder([0, 1, 0], bid=[0.20, 0.40, 0.20], ask=[0.30, 0.50, 0.30], y=1))
    rng = np.random.default_rng(0)
    trades = {
        "T{}".format(j): _tr(
            np.sort(rng.integers(1001, 9000, 50)),
            rng.uniform(0.01, 0.99, 50),
            rng.integers(1, 100, 50),
            rng.random(50) < 0.5,
        )
        for j in range(3)
    }
    led = run_maker(ls, np.eye(3)[[1]], MakerConfig("o", theta=0.0, stake=1e4), trades)
    assert len(led) and (led.pnl > 0).all()


def test_next_gfs_release_and_cancel_on_new_run():
    from pmdecide.backtest import MakerConfig, next_gfs_public, run_maker

    t = 1785715200  # 2026-08-03 00:00Z
    assert next_gfs_public(t) == t + 5 * 3600
    assert next_gfs_public(t + 5 * 3600) == t + 11 * 3600
    assert next_gfs_public(t + 23 * 3600 + 1) == t + 86400 + 5 * 3600
    # an order resting from 00:00Z is cancelled at 05:00Z, so a print through it at 06:00Z does not fill
    ls = _with_meta(
        _ladder([0.1, 0.8, 0.1], bid=[0.05, 0.50, 0.05], ask=[0.10, 0.60, 0.10], y=1),
        read_ts=t,
        close_ts=t + 86400,
    )
    trades = {"T1": _tr([t + 6 * 3600], [0.40], [30], [False])}
    keep = run_maker(ls, ls.probs["model"], MakerConfig("m", theta=0.0, horizon_h=48), trades)
    gone = run_maker(
        ls, ls.probs["model"], MakerConfig("m", theta=0.0, horizon_h=48, cancel_on="gfs"), trades
    )
    assert len(keep) == 1 and gone.empty
