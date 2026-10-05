"""Daily lows: overnight-min forecast join, the lows calendar, series map."""

import numpy as np
import pandas as pd

from pmdecide import lows
from pmdecide.splits import EMBARGO
from pmdecide.weather import AVAILABILITY_LAG


def test_overnight_min_is_the_12z_row_of_the_morning_it_ends():
    mos = pd.DataFrame(
        {
            "runtime": pd.to_datetime(["2026-01-09 12:00"] * 3, utc=True),
            "ftime": pd.to_datetime(["2026-01-10 00:00", "2026-01-10 12:00", "2026-01-11 00:00"], utc=True),
            "n_x": [41.0, 28.0, 44.0],
        }
    )
    t = lows.overnight_min_table(mos, "n_x", AVAILABILITY_LAG["GFS"])
    assert len(t) == 1
    assert t["target"].iloc[0] == pd.Timestamp("2026-01-10") and t["fcst"].iloc[0] == 28.0
    assert t["public"].iloc[0] == pd.Timestamp("2026-01-09 17:00", tz="UTC")


def test_forecast_join_only_uses_public_runs():
    table = pd.DataFrame(
        {
            "target": pd.to_datetime(["2026-01-10", "2026-01-10"]),
            "runtime": pd.to_datetime(["2026-01-09 00:00", "2026-01-09 12:00"], utc=True),
            "public": pd.to_datetime(["2026-01-09 05:00", "2026-01-09 17:00"], utc=True),
            "fcst": [30.0, 28.0],
        }
    )
    targets = pd.Series(pd.to_datetime(["2026-01-10", "2026-01-10"]))
    reads = pd.Series(pd.to_datetime(["2026-01-09 16:59", "2026-01-09 17:00"], utc=True))
    assert list(lows._forecast_at(table, targets, reads)) == [30.0, 28.0]


def test_lows_calendar_trains_on_the_past_and_stops_before_its_lockbox():
    days = pd.Series(pd.date_range("2025-12-14", "2026-10-03", freq="D"))
    folds = list(lows.walk_forward(days))
    assert folds and folds[0].name.startswith("2026-02-01")
    for f in folds:
        assert days.iloc[f.train].max() <= days.iloc[f.test].min() - EMBARGO
        assert days.iloc[f.test].max() < lows.LOCKBOX_START
        assert days.iloc[f.train].nunique() >= lows.MIN_TRAIN_DAYS


def test_low_series_cover_the_same_stations_as_highs():
    assert lows.low_city("NY").series == "KXLOWTNYC" and lows.low_city("NY").station == "KNYC"
    assert set(lows.LOW_SERIES) == {"NY", "CHI", "MIA", "AUS", "LAX", "DEN", "PHIL"}
    assert np.all([s.startswith("KXLOWT") for s in lows.LOW_SERIES.values()])
