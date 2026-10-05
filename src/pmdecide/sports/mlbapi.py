"""MLB Stats API (statsapi.mlb.com): schedules, results, probable pitchers, pitcher game logs.

Free and keyless. Responses for completed seasons are cached immutably (same
scheme as the Kalshi client); the current season is refetched, since games are
still being added to it.

Point-in-time caveat: the archived `probablePitcher` of a completed game is the
pitcher listed for it, which for nearly every game is the announced probable
starter. A late scratch can make it differ from what was public pre-game; the
effect is small and is stated as a limitation in docs/SPORTS.md.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import threading
import time
import urllib.error
import urllib.request
from typing import Dict, List

import pandas as pd

from ..kalshi import CACHE as _KCACHE

BASE = "https://statsapi.mlb.com/api/v1"
CACHE = _KCACHE.parent / "mlb"
MIN_INTERVAL = 0.05
GAME_TYPES = "R,F,D,L,W"        # regular season + every postseason round; no spring training

_lock = threading.Lock()
_last = [0.0]


def _fetch(url: str, retries: int = 6) -> Dict:
    delay = 2.0
    for attempt in range(retries):
        with _lock:
            dt = time.time() - _last[0]
            if dt < MIN_INTERVAL:
                time.sleep(MIN_INTERVAL - dt)
            _last[0] = time.time()
        try:
            with urllib.request.urlopen(url, timeout=90) as r:
                return json.loads(r.read())
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if isinstance(e, urllib.error.HTTPError) and e.code == 404:
                raise
            if attempt < retries - 1:
                time.sleep(delay)
                delay *= 2
                continue
            raise
    raise RuntimeError("unreachable")


def get(path: str, cache: bool) -> Dict:
    url = BASE + path
    if not cache:
        return _fetch(url)
    h = hashlib.sha256(url.encode()).hexdigest()
    f = CACHE / h[:2] / (h[:24] + ".json.gz")
    if f.exists():
        return json.loads(gzip.decompress(f.read_bytes()))
    out = _fetch(url)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp{}".format(threading.get_ident()))
    tmp.write_bytes(gzip.compress(json.dumps(out).encode()))
    tmp.replace(f)
    return out


def _closed(season: int) -> bool:
    return season < pd.Timestamp.now().year


def schedule(season: int) -> pd.DataFrame:
    """Every regular and postseason game of a season, one row per game record."""
    d = get("/schedule?sportId=1&season={}&gameType={}&hydrate=probablePitcher".format(
        season, GAME_TYPES), cache=_closed(season))
    rows: List[Dict] = []
    for day in d.get("dates", []):
        for g in day.get("games", []):
            a, h = g["teams"]["away"], g["teams"]["home"]
            rows.append({
                "game_pk": g["gamePk"], "season": season, "game_type": g.get("gameType"),
                "start": pd.Timestamp(g["gameDate"]), "official_date": g.get("officialDate"),
                "state": g["status"].get("detailedState"),
                "coded": g["status"].get("codedGameState"),
                "double_header": g.get("doubleHeader"), "game_number": g.get("gameNumber"),
                "away_id": a["team"]["id"], "home_id": h["team"]["id"],
                "away_score": a.get("score"), "home_score": h.get("score"),
                "away_win": a.get("isWinner"), "home_win": h.get("isWinner"),
                "away_sp": (a.get("probablePitcher") or {}).get("id"),
                "home_sp": (h.get("probablePitcher") or {}).get("id"),
                "rescheduled_from": g.get("rescheduledFrom"),
            })
    df = pd.DataFrame(rows)
    if len(df):
        df["start"] = pd.to_datetime(df["start"], utc=True)
        df["official_date"] = pd.to_datetime(df["official_date"])
    return df


def teams(season: int) -> pd.DataFrame:
    t = get("/teams?sportId=1&season={}".format(season), cache=_closed(season))["teams"]
    return pd.DataFrame([{"team_id": x["id"], "abbr": x["abbreviation"], "name": x["teamName"],
                          "season": season} for x in t])


def pitcher_log(person_id: int, season: int) -> pd.DataFrame:
    """Per-appearance pitching lines for one pitcher-season."""
    try:
        d = get("/people/{}/stats?stats=gameLog&group=pitching&season={}".format(person_id, season),
                cache=_closed(season))
    except urllib.error.HTTPError:
        return pd.DataFrame()
    rows = []
    for st in d.get("stats", []):
        for s in st.get("splits", []):
            x = s.get("stat", {})
            ip = str(x.get("inningsPitched", "0.0"))
            whole, _, frac = ip.partition(".")
            outs = int(whole or 0) * 3 + int(frac or 0)
            rows.append({"pitcher": person_id, "season": season, "date": s.get("date"),
                         "game_pk": (s.get("game") or {}).get("gamePk"), "outs": outs,
                         "er": x.get("earnedRuns", 0), "k": x.get("strikeOuts", 0),
                         "bb": x.get("baseOnBalls", 0), "hbp": x.get("hitByPitch", 0),
                         "hr": x.get("homeRuns", 0), "bf": x.get("battersFaced", 0),
                         "gs": x.get("gamesStarted", 0)})
    df = pd.DataFrame(rows)
    if len(df):
        df["date"] = pd.to_datetime(df["date"])
    return df
