"""Invariants the whole programme rests on: label arithmetic and point-in-time forecasts."""
import numpy as np
import pandas as pd
import pytest

from pmdecide.weather import (
    MOS_AVAILABILITY_LAG,
    bucket_contains,
    bucket_interval,
    gaussian_bucket_probs,
    mos_daytime_max,
)


@pytest.mark.parametrize("st,floor,cap,inside,outside", [
    ("less", None, 80, [79, -10], [80, 81]),
    ("greater", 87, None, [88, 120], [87, 86]),
    ("between", 80, 81, [80, 81], [79, 82]),
])
def test_bucket_membership_matches_kalshi_semantics(st, floor, cap, inside, outside):
    # KXHIGHNY-26AUG03: T80 = "<80", B80.5 = "80-81", T87 = ">87"
    assert all(bucket_contains(st, floor, cap, v) for v in inside)
    assert not any(bucket_contains(st, floor, cap, v) for v in outside)


def test_a_full_ladder_partitions_the_integers():
    ladder = [("less", None, 80), ("between", 80, 81), ("between", 82, 83),
              ("between", 84, 85), ("between", 86, 87), ("greater", 87, None)]
    for v in range(40, 120):
        assert sum(bucket_contains(s, f, c, v) for s, f, c in ladder) == 1, v


def test_gaussian_bucket_probs_sum_to_one_over_a_partition():
    ladder = [("less", None, 80), ("between", 80, 81), ("between", 82, 83),
              ("greater", 83, None)]
    p = gaussian_bucket_probs(81.3, 2.5, [bucket_interval(*b) for b in ladder])
    assert np.isclose(p.sum(), 1.0)
    assert p.argmax() == 1


def _mos(runs):
    rows = []
    for rt, val in runs:
        rows.append({"runtime": pd.Timestamp(rt, tz="UTC"),
                     "ftime": pd.Timestamp("2026-08-04 00:00", tz="UTC"), "n_x": val})
    return pd.DataFrame(rows)


def test_mos_uses_only_runs_public_at_read_time():
    day = pd.Timestamp("2026-08-03")
    mos = _mos([("2026-08-02 12:00", 84.0), ("2026-08-03 00:00", 82.0),
                ("2026-08-03 12:00", 80.0)])
    # 08:00 EDT = 12:00Z. The 12Z run is not public yet; 00Z became public at 05Z.
    t = pd.Timestamp("2026-08-03 12:00", tz="UTC")
    got = mos_daytime_max(mos, day, t)
    assert got["fcst"] == 82.0
    # One second before 00Z + lag, only the previous day's 12Z run is public.
    t2 = pd.Timestamp("2026-08-03 00:00", tz="UTC") + MOS_AVAILABILITY_LAG - pd.Timedelta(seconds=1)
    assert mos_daytime_max(mos, day, t2)["fcst"] == 84.0


def test_mos_returns_none_when_nothing_is_public():
    day = pd.Timestamp("2026-08-03")
    mos = _mos([("2026-08-03 12:00", 80.0)])
    assert mos_daytime_max(mos, day, pd.Timestamp("2026-08-03 13:00", tz="UTC")) is None


def test_vectorised_forecast_join_matches_reference():
    from pmdecide.emos import daytime_max_table, forecast_at
    rng = np.random.default_rng(0)
    runs = pd.date_range("2026-07-01", "2026-07-20", freq="6h", tz="UTC")
    rows = []
    for rt in runs:
        for k in range(1, 4):
            ft = (rt + pd.Timedelta(days=k)).normalize()
            rows.append({"runtime": rt, "ftime": ft, "n_x": float(rng.integers(60, 95))})
    mos = pd.DataFrame(rows).drop_duplicates(["runtime", "ftime"])
    days = pd.Series(pd.date_range("2026-07-05", "2026-07-18", freq="D"))
    reads = days.dt.tz_localize("UTC") + pd.Timedelta(hours=13, minutes=30)
    got = forecast_at(daytime_max_table(mos), pd.DataFrame({"target": days, "read_time": reads}))
    for i, (d, t) in enumerate(zip(days, reads, strict=True)):
        ref = mos_daytime_max(mos, d, t)
        assert got["fcst"].iloc[i] == ref["fcst"]
        assert got["runtime"].iloc[i] == ref["runtime"]
