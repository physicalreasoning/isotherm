"""Kalshi MLB game-winner events (KXMLBGAME), linked to MLB Stats API games.

Each event has two mutually exclusive markets, one per team, the team code being
the market-ticker suffix (Kalshi uses MLB's own abbreviations: ATH, AZ, CWS, ...).
The event ticker carries the originally scheduled date (and, from mid-2025, the
scheduled ET start as HHMM):

    KXMLBGAME-25APR16ATLTOR           date only
    KXMLBGAME-26OCT041600SDMIL        date + 16:00 ET

Linking rule: same official date, same two teams. A doubleheader is resolved by
the HHMM in the ticker (or the "at 1:35 PM EDT" in the rules text); if neither
disambiguates, the event is dropped and counted. Events whose game was postponed,
suspended or not played as scheduled are dropped too: their pre-game read times
would refer to a start that did not happen.
"""
from __future__ import annotations

import re
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

ET = "America/New_York"
_TICK = re.compile(r"^KXMLBGAME-(\d{2})([A-Z]{3})(\d{2})(\d{4})?")
_RULE_TIME = re.compile(r"at (\d{1,2}):(\d{2}) ?([AP]M) ?(E[DS]T)")

# Read times relative to the scheduled first pitch. Orders and quotes are cancelled
# at first pitch: the strategy only trades the pre-game market.
READS = {"t_24h": pd.Timedelta(hours=24), "t_3h": pd.Timedelta(hours=3),
         "t_15m": pd.Timedelta(minutes=15)}


def parse_event(event_ticker: str) -> Tuple[Optional[pd.Timestamp], Optional[str]]:
    m = _TICK.match(event_ticker)
    if not m:
        return None, None
    yy, mon, dd, hhmm = m.groups()
    day = pd.to_datetime("{}{}{}".format(yy, mon, dd), format="%y%b%d")
    return day, hhmm


def rules_time(rules: str) -> Optional[str]:
    m = _RULE_TIME.search(rules or "")
    if not m:
        return None
    h, mi, ap, _ = m.groups()
    h = int(h) % 12 + (12 if ap == "PM" else 0)
    return "{:02d}{}".format(h, mi)


def abbr_map(teams: pd.DataFrame) -> Dict[Tuple[int, str], int]:
    """(season, abbreviation) -> team_id."""
    return {(int(s), a): int(t) for s, a, t in zip(teams["season"], teams["abbr"], teams["team_id"],
                                                   strict=True)}


def link(events: pd.DataFrame, sched: pd.DataFrame, teams: pd.DataFrame) -> pd.DataFrame:
    """events: one row per Kalshi event with columns event, codes (tuple of 2), rules.

    Returns events with game_pk, first_pitch (UTC), home/away codes, and `link` status.
    """
    amap = abbr_map(teams)
    sched = sched.copy()
    sched["start_et"] = sched["start"].dt.tz_convert(ET)
    by_day = {d: g for d, g in sched.groupby("official_date")}
    out = []
    for r in events.itertuples(index=False):
        day, hhmm = parse_event(r.event)
        rec = {"event": r.event, "day": day, "game_pk": None, "first_pitch": pd.NaT,
               "home": None, "away": None, "link": "unparsed"}
        if day is None or len(r.codes) != 2:
            out.append(rec)
            continue
        ids = {amap.get((day.year, c)) for c in r.codes}
        g = by_day.get(day)
        if None in ids or g is None:
            rec["link"] = "no_team_or_day"
            out.append(rec)
            continue
        c = g[(g["home_id"].isin(ids)) & (g["away_id"].isin(ids))]
        c = c.drop_duplicates("game_pk")
        want = hhmm or rules_time(r.rules)
        if len(c) > 1 and want:
            c = c[c["start_et"].dt.strftime("%H%M") == want]
        if len(c) != 1:
            rec["link"] = "ambiguous" if len(c) > 1 else "no_game"
            out.append(rec)
            continue
        x = c.iloc[0]
        inv = {v: k for (s, k), v in amap.items() if s == day.year}
        rec.update(game_pk=int(x["game_pk"]), first_pitch=x["start"], home=inv.get(int(x["home_id"])),
                   away=inv.get(int(x["away_id"])), state=x["state"], coded=x["coded"],
                   home_won=x["home_win"])
        if x["coded"] != "F":
            rec["link"] = "not_played_as_scheduled"
        elif want and x["start_et"].strftime("%H%M") != want:
            rec["link"] = "start_mismatch"
        else:
            rec["link"] = "ok"
        out.append(rec)
    return pd.DataFrame(out)


def quote_at(cs, t):
    """(bid, ask) from the last candle that closed at or before t."""
    from .. import kalshi
    best = None
    for c in cs:
        if c["end_period_ts"] <= t:
            best = c
        else:
            break
    if best is None:
        return None, None
    return kalshi.candle_quote(best)


def volume_between(cs, t0, t1) -> float:
    from .. import kalshi
    return float(sum(kalshi.candle_volume(c) for c in cs if t0 < c["end_period_ts"] <= t1))


def period_of(day: pd.Timestamp) -> str:
    return "{}H{}".format(day.year, 1 + (day.month > 6))


def nan_to_none(x):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else x
