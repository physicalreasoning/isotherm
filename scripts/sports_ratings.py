#!/usr/bin/env python3
"""Point-in-time MLB win probabilities: Elo, and Elo + starting pitchers.

  Elo:     K / HFA / season reversion tuned by log loss on 2016-2019 (2012-15 warm-up),
           checked on 2021-2024. Day-batched, so no same-day leakage.
  Elo+SP:  logistic regression of home win on the Elo logit and the starters' regressed
           FIP gap, fit on 2017-2024 only.
Both are frozen before the first Kalshi game (2025-04) and applied unchanged after it.

Writes data/sports/mlb_game_probs.parquet and results/sports_ratings.json.

    uv run scripts/sports_ratings.py
"""

from __future__ import annotations

import json
import pathlib
import sys
from dataclasses import asdict

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from isotherm.sports.elo import (  # noqa: E402
    final_games,
    fit_logistic,
    pitcher_quality,
    predict_logistic,
    run_elo,
    tune_elo,
)

D = pathlib.Path("data/sports")
TUNE, CHECK, FIT = range(2016, 2020), range(2021, 2025), range(2017, 2025)
KALSHI_FROM = 2025


def logloss(p, y):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean())


def main():
    sched = pd.read_parquet(D / "mlb_schedule.parquet")
    logs = pd.read_parquet(D / "mlb_pitcher_logs.parquet")
    games = final_games(sched)
    prm, ll_tune = tune_elo(games, TUNE)
    e = run_elo(games, prm)
    y = e["home_won"].to_numpy()

    q_home = pd.DataFrame({"pitcher": e["home_sp"], "season": e["season"], "day": e["day"]})
    q_away = pd.DataFrame({"pitcher": e["away_sp"], "season": e["season"], "day": e["day"]})
    e["fip_home"] = pitcher_quality(logs, q_home)
    e["fip_away"] = pitcher_quality(logs, q_away)
    e["fip_gap"] = e["fip_away"] - e["fip_home"]  # > 0: home starter is better
    X = e[["elo_logit", "fip_gap"]].to_numpy()
    fit = e["season"].isin(list(FIT)).to_numpy()
    w = fit_logistic(X[fit], y[fit])
    e["p_elo_sp"] = predict_logistic(w, X)

    report = {"elo_params": asdict(prm), "elo_tune_logloss": ll_tune, "elo_sp_weights": w.tolist()}
    for name, rng in (("check_2021_2024", CHECK), ("kalshi_2025_on", range(KALSHI_FROM, 2100))):
        s = e["season"].isin(list(rng)).to_numpy()
        report[name] = {
            "games": int(s.sum()),
            "home_rate": float(y[s].mean()),
            "logloss_coin": logloss(np.full(s.sum(), y[s].mean()), y[s]),
            "logloss_elo": logloss(e.loc[s, "p_elo"].to_numpy(), y[s]),
            "logloss_elo_sp": logloss(e.loc[s, "p_elo_sp"].to_numpy(), y[s]),
        }
    print(json.dumps(report, indent=1))
    cols = [
        "game_pk",
        "season",
        "day",
        "start",
        "home_id",
        "away_id",
        "home_won",
        "p_elo",
        "p_elo_sp",
        "elo_logit",
        "fip_home",
        "fip_away",
        "home_sp",
        "away_sp",
    ]
    e[cols].to_parquet(D / "mlb_game_probs.parquet", index=False)
    pathlib.Path("results").mkdir(exist_ok=True)
    pathlib.Path("results/sports_ratings.json").write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
