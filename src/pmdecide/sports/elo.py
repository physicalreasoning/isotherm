"""Point-in-time team strength (Elo) and starting-pitcher quality for MLB.

Elo
  p_home = 1 / (1 + 10^(-(R_home + HFA - R_away) / 400)); after each game
  R += K (outcome - p). Ratings regress a fraction `revert` toward 1500 between
  seasons. Updates are batched by game *day*: every game on day D is priced with
  ratings as of the start of D, so a doubleheader's first game can never inform
  the second. K, HFA and `revert` are tuned on seasons before the market existed.

Starting pitchers
  A FIP-style run value per nine innings, (13 HR + 3 (BB + HBP) - 2 K) / IP + c,
  from appearances strictly before the game day, with last season counted at half
  weight and shrunk toward the league mean with `prior_ip` pseudo-innings. Missing
  or unannounced starters get the league mean.

Combined model
  logit P(home) = a + b * elo_logit + c * (fip_away - fip_home), fit once on
  pre-market seasons and applied unchanged to the Kalshi period.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Tuple

import numpy as np
import pandas as pd

LN10_400 = np.log(10) / 400
FIP_CONST = 3.10


@dataclass
class EloParams:
    k: float = 4.0
    hfa: float = 24.0
    revert: float = 0.33


def final_games(sched: pd.DataFrame) -> pd.DataFrame:
    """Completed games only, one row per game, in start order."""
    g = sched[(sched["coded"] == "F") & sched["home_win"].notna()].copy()
    g = g.sort_values("start").drop_duplicates("game_pk", keep="last")
    g["home_won"] = g["home_win"].astype(bool).astype(int)
    g["day"] = g["official_date"]
    return g.reset_index(drop=True)


def run_elo(games: pd.DataFrame, prm: EloParams) -> pd.DataFrame:
    """Pre-game ratings and p_home for every completed game, batched by day."""
    r: Dict[int, float] = {}
    season = None
    pre_h, pre_a, p = np.empty(len(games)), np.empty(len(games)), np.empty(len(games))
    for _day, idx in games.groupby("day", sort=True).groups.items():
        idx = np.asarray(idx)
        s = int(games.loc[idx[0], "season"])
        if season is not None and s != season:
            for t in r:
                r[t] = 1500 + (1 - prm.revert) * (r[t] - 1500)
        season = s
        snap = dict(r)
        for i in idx:
            h, a = games.at[i, "home_id"], games.at[i, "away_id"]
            rh, ra = snap.get(h, 1500.0), snap.get(a, 1500.0)
            pre_h[i], pre_a[i] = rh, ra
            p[i] = 1 / (1 + 10 ** (-(rh + prm.hfa - ra) / 400))
        for i in idx:
            h, a = games.at[i, "home_id"], games.at[i, "away_id"]
            d = prm.k * (games.at[i, "home_won"] - p[i])
            r[h] = r.get(h, 1500.0) + d
            r[a] = r.get(a, 1500.0) - d
    out = games.copy()
    out["elo_home"], out["elo_away"], out["p_elo"] = pre_h, pre_a, p
    out["elo_logit"] = LN10_400 * (pre_h + prm.hfa - pre_a)
    return out


def ratings_before(games: pd.DataFrame, prm: EloParams, day: pd.Timestamp) -> Dict[int, float]:
    """Ratings at the start of `day` (for games not in `games`, e.g. today's slate)."""
    g = games[games["day"] < day]
    r: Dict[int, float] = {}
    season = None
    for _d, idx in g.groupby("day", sort=True).groups.items():
        idx = np.asarray(idx)
        s = int(g.loc[idx[0], "season"])
        if season is not None and s != season:
            for t in r:
                r[t] = 1500 + (1 - prm.revert) * (r[t] - 1500)
        season = s
        snap = dict(r)
        for i in idx:
            h, a = g.at[i, "home_id"], g.at[i, "away_id"]
            rh, ra = snap.get(h, 1500.0), snap.get(a, 1500.0)
            ph = 1 / (1 + 10 ** (-(rh + prm.hfa - ra) / 400))
            dlt = prm.k * (g.at[i, "home_won"] - ph)
            r[h] = r.get(h, 1500.0) + dlt
            r[a] = r.get(a, 1500.0) - dlt
    if season is not None and int(day.year) != season:
        for t in r:
            r[t] = 1500 + (1 - prm.revert) * (r[t] - 1500)
    return r


def tune_elo(games: pd.DataFrame, fit_seasons: Iterable[int], grid=None) -> Tuple[EloParams, float]:
    """Grid-search K, HFA, revert by log loss on `fit_seasons` (warm-up seasons run first)."""
    grid = grid or [EloParams(k, h, rv) for k in (3, 4, 5, 6, 8) for h in (16, 24, 32)
                    for rv in (0.25, 0.33, 0.5)]
    fit = games["season"].isin(list(fit_seasons)).to_numpy()
    best, best_ll = None, np.inf
    for prm in grid:
        e = run_elo(games, prm)
        p = np.clip(e.loc[fit, "p_elo"].to_numpy(), 1e-6, 1 - 1e-6)
        y = e.loc[fit, "home_won"].to_numpy()
        ll = float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean())
        if ll < best_ll:
            best, best_ll = prm, ll
    return best, best_ll


# --------------------------------------------------------------------------- pitchers

def _fip(hr, bb, hbp, k, outs):
    ip = outs / 3.0
    return np.where(ip > 0, (13 * hr + 3 * (bb + hbp) - 2 * k) / np.maximum(ip, 1e-9) + FIP_CONST,
                    np.nan)


def pitcher_quality(logs: pd.DataFrame, queries: pd.DataFrame, league_fip: float = 4.2,
                    prior_ip: float = 40.0, last_season_weight: float = 0.5) -> np.ndarray:
    """Regressed FIP for each (pitcher, season, day) query, from appearances before `day`.

    logs: pitcher game logs (pitcher, season, date, outs, k, bb, hbp, hr).
    queries: columns pitcher, season, day. Returns NaN-free array (league mean when unknown).
    """
    out = np.full(len(queries), league_fip)
    if logs.empty:
        return out
    tot_cols = ["outs", "k", "bb", "hbp", "hr"]
    logs = logs.sort_values("date")
    cum = {}
    for key, g in logs.groupby(["pitcher", "season"]):
        dates = g["date"].to_numpy("datetime64[ns]")
        c = np.vstack([np.zeros(5), np.cumsum(g[tot_cols].to_numpy(float), 0)])
        cum[key] = (dates, c)
    for i, (pid, s, day) in enumerate(zip(queries["pitcher"], queries["season"], queries["day"],
                                          strict=True)):
        if pd.isna(pid):
            continue
        pid, s = int(pid), int(s)
        acc = np.zeros(5)
        hit = cum.get((pid, s))
        if hit is not None:
            # strictly before the game day: appearances on `day` itself are excluded
            n = np.searchsorted(hit[0], np.datetime64(pd.Timestamp(day), "ns"), side="left")
            acc += hit[1][n]
        prev = cum.get((pid, s - 1))
        prev = prev[1][-1] if prev is not None else None
        if prev is not None:
            acc += last_season_weight * prev
        outs, k, bb, hbp, hr = acc
        ip = outs / 3.0
        if ip <= 0:
            continue
        fip = float(_fip(hr, bb, hbp, k, outs))
        out[i] = (fip * ip + league_fip * prior_ip) / (ip + prior_ip)
    return out


def fit_logistic(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    from sklearn.linear_model import LogisticRegression
    m = LogisticRegression(C=1e4, max_iter=2000).fit(X, y)
    return np.concatenate([m.intercept_, m.coef_[0]])


def predict_logistic(w: np.ndarray, X: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-(w[0] + X @ w[1:])))
