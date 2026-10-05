"""Shadow scoring: the read window, tickers, and settlement arithmetic (no network)."""
import numpy as np
import pandas as pd

from pmdecide import shadow
from pmdecide.weather import CITIES


def test_read_window_is_local_16_to_18_in_every_timezone_and_season():
    for key, utc_hour in [("NY", 20), ("CHI", 21), ("DEN", 22), ("LAX", 23)]:   # summer: DST
        day, due = shadow.due(CITIES[key], pd.Timestamp("2026-07-14 {}:05".format(utc_hour), tz="UTC"))
        assert due and day == pd.Timestamp("2026-07-15")
    # winter: standard time shifts every city an hour later in UTC
    _, due = shadow.due(CITIES["NY"], pd.Timestamp("2026-01-14 20:05", tz="UTC"))
    assert not due                                       # 15:05 EST
    day, due = shadow.due(CITIES["NY"], pd.Timestamp("2026-01-14 21:05", tz="UTC"))
    assert due and day == pd.Timestamp("2026-01-15")


def test_event_ticker_matches_kalshi():
    assert shadow.event_ticker("KXHIGHNY", pd.Timestamp("2026-10-05")) == "KXHIGHNY-26OCT05"


def test_report_applies_capacity_fees_and_no_side_payoffs(tmp_path):
    base = {"scored_at": "t", "city": "NY", "event": "E", "day": "2026-10-05", "model_hash": "h"}
    preds = [dict(base, ticker="A", bucket=0, p_market=0.6, p_model=0.5),
             dict(base, ticker="B", bucket=1, p_market=0.4, p_model=0.5)]
    trades = [dict(base, ticker="B", bucket=1, side="yes", price=0.40, contracts_intended=100,
                   volume_at_read=1000, ev_per_contract=0.1, p_model=0.5),
              dict(base, ticker="A", bucket=0, side="no", price=0.38, contracts_intended=10,
                   volume_at_read=0, ev_per_contract=0.1, p_model=0.5)]
    outcomes = [{"event": "E", "ticker": "A", "y": 0, "final_volume": 5000},
                {"event": "E", "ticker": "B", "y": 1, "final_volume": 1600}]
    for name, rows in (("predictions", preds), ("trades", trades), ("outcomes", outcomes)):
        pd.DataFrame(rows).to_csv(tmp_path / "{}.csv".format(name), index=False)
    r = shadow.report(tmp_path)
    # B: cap = 5% of (1600-1000) = 30 contracts, win 1-0.40, fee ceil(0.07*30*.4*.6)=0.51
    # A (NO, bucket lost): 10 contracts, win 1-0.38, fee ceil(0.07*10*.38*.62)=0.17
    expected = 30 * 0.60 - 0.51 + 10 * 0.62 - 0.17
    assert np.isclose(r["pnl"], expected)
    assert r["trades"] == 2 and r["hit_rate"] == 1.0
    # log score: market put 0.4 on the winner, model 0.5
    assert np.isclose(r["log_score_gain_vs_market"], np.log(0.5) - np.log(0.4))
