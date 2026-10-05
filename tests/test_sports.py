"""MLB pipeline invariants: ticker parsing, game linking, and no same-day leakage."""

import numpy as np
import pandas as pd

from pmdecide.sports.elo import EloParams, pitcher_quality, run_elo
from pmdecide.sports.kalshi_mlb import link, parse_event, rules_time


def test_parse_event_with_and_without_start_time():
    d, t = parse_event("KXMLBGAME-26OCT041600SDMIL")
    assert d == pd.Timestamp("2026-10-04") and t == "1600"
    d, t = parse_event("KXMLBGAME-25APR16ATLTOR")
    assert d == pd.Timestamp("2025-04-16") and t is None


def test_rules_time_parses_et_clock():
    assert rules_time("originally scheduled for Apr 5, 2026 at 1:35 PM EDT") == "1335"
    assert rules_time("scheduled for Apr 16, 2025, then") is None


def _sched(rows):
    df = pd.DataFrame(rows)
    df["start"] = pd.to_datetime(df["start"], utc=True)
    df["official_date"] = pd.to_datetime(df["official_date"])
    return df


TEAMS = pd.DataFrame({"team_id": [1, 2], "abbr": ["NYY", "BOS"], "name": ["Y", "B"], "season": [2026, 2026]})


def test_doubleheader_resolved_by_ticker_time_and_dropped_when_ambiguous():
    base = {
        "official_date": "2026-05-01",
        "away_id": 2,
        "home_id": 1,
        "coded": "F",
        "state": "Final",
        "home_win": True,
    }
    sched = _sched(
        [
            dict(base, game_pk=10, start="2026-05-01T17:05:00Z"),
            dict(base, game_pk=11, start="2026-05-01T23:05:00Z"),
        ]
    )
    ev = pd.DataFrame(
        {
            "event": ["KXMLBGAME-26MAY011905BOSNYY", "KXMLBGAME-26MAY01BOSNYY"],
            "codes": [("BOS", "NYY"), ("BOS", "NYY")],
            "rules": ["", ""],
        }
    )
    out = link(ev, sched, TEAMS)
    assert out.loc[0, "game_pk"] == 11 and out.loc[0, "link"] == "ok"  # 19:05 ET = 23:05Z
    assert out.loc[0, "home"] == "NYY" and out.loc[0, "away"] == "BOS"
    assert out.loc[1, "link"] == "ambiguous"


def test_postponed_game_is_not_linked_as_ok():
    sched = _sched(
        [
            {
                "official_date": "2026-05-01",
                "away_id": 2,
                "home_id": 1,
                "coded": "D",
                "state": "Postponed",
                "home_win": None,
                "game_pk": 12,
                "start": "2026-05-01T23:05:00Z",
            }
        ]
    )
    ev = pd.DataFrame({"event": ["KXMLBGAME-26MAY011905BOSNYY"], "codes": [("BOS", "NYY")], "rules": [""]})
    assert link(ev, sched, TEAMS).loc[0, "link"] == "not_played_as_scheduled"


def test_elo_prices_a_doubleheader_with_start_of_day_ratings():
    g = pd.DataFrame(
        {
            "game_pk": [1, 2, 3],
            "season": 2024,
            "home_id": [1, 1, 1],
            "away_id": [2, 2, 2],
            "home_won": [1, 1, 1],
            "day": pd.to_datetime(["2024-05-01", "2024-05-02", "2024-05-02"]),
        }
    )
    e = run_elo(g, EloParams(k=10, hfa=0, revert=0.0))
    # both games on 05-02 see the same pre-game rating, despite game 2 happening first
    assert e.loc[1, "elo_home"] == e.loc[2, "elo_home"] > 1500
    assert np.isclose(e.loc[0, "p_elo"], 0.5)


def test_pitcher_quality_ignores_the_game_day_itself():
    logs = pd.DataFrame(
        {
            "pitcher": 7,
            "season": 2025,
            "date": pd.to_datetime(["2025-04-01", "2025-04-06"]),
            "outs": [18, 18],
            "k": [9, 0],
            "bb": [0, 5],
            "hbp": [0, 0],
            "hr": [0, 4],
        }
    )
    q = pd.DataFrame(
        {
            "pitcher": [7, 7, np.nan],
            "season": [2025, 2025, 2025],
            "day": pd.to_datetime(["2025-04-06", "2025-04-07", "2025-04-07"]),
        }
    )
    v = pitcher_quality(logs, q)
    assert v[0] < 4.2  # only the dominant 04-01 start counts on 04-06
    assert v[1] > v[0]  # the 04-06 shelling counts from the next day on
    assert v[2] == 4.2  # unknown starter -> league mean


def test_build_makes_coherent_two_bucket_ladders():
    from pmdecide.sports.dataset import build

    rows = []
    for side, code, y, b, a in (("away", "BOS", 0, 0.44, 0.46), ("home", "NYY", 1, 0.54, 0.56)):
        rows.append(
            {
                "event": "E1",
                "ticker": "E1-" + code,
                "code": code,
                "side": side,
                "y": y,
                "day": pd.Timestamp("2026-05-01"),
                "period": "2026H1",
                "game_pk": 11,
                "first_pitch_ts": 2000,
                "read": "t_3h",
                "read_ts": 1000,
                "bid": b,
                "ask": a,
                "vol_after": 50.0,
                "candles_ok": True,
            }
        )
    probs = pd.DataFrame({"game_pk": [11], "p_elo": [0.6], "p_elo_sp": [0.62], "home_won": [1]})
    ls = build(pd.DataFrame(rows), probs)
    assert len(ls) == 1 and ls.y[0] == 1  # bucket 1 = home
    assert ls.meta.loc[0, "label_agrees_mlb"]
    assert ls.meta.loc[0, "close_ts"] == 2000  # orders cancel at first pitch
    for k in ("market", "elo", "elo_sp"):
        assert np.allclose(ls.probs[k].sum(1), 1)
    assert np.isclose(ls.probs["elo_sp"][0, 1], 0.62)
    assert np.allclose(ls.quotes["ask"][0], [0.46, 0.56])
