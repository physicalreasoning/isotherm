#!/usr/bin/env python3
"""Fetch MLB history from the free Stats API: schedules/results and starters' game logs.

Schedules from 2012 give warm Elo ratings well before Kalshi listed games (2025-04).
Game logs are fetched for every pitcher who was a listed probable starter, for each
season he started plus the season before (the prior that point-in-time FIP uses).

    uv run scripts/sports_fetch_mlb.py
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import pathlib
import sys
import time

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from pmdecide.sports import mlbapi  # noqa: E402

OUT = pathlib.Path("data/sports")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--first", type=int, default=2012)
    ap.add_argument("--last", type=int, default=pd.Timestamp.now().year)
    ap.add_argument("--pitchers-from", type=int, default=2015)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    sched = pd.concat([mlbapi.schedule(s) for s in range(a.first, a.last + 1)], ignore_index=True)
    sched.to_parquet(OUT / "mlb_schedule.parquet", index=False)
    print("schedule: {} game records, {} final, seasons {}-{} ({:.0f}s)".format(
        len(sched), int((sched["coded"] == "F").sum()), a.first, a.last, time.time() - t0),
        flush=True)

    teams = pd.concat([mlbapi.teams(s) for s in range(a.first, a.last + 1)], ignore_index=True)
    teams.to_parquet(OUT / "mlb_teams.parquet", index=False)

    s = sched[sched["season"] >= a.pitchers_from]
    sp = pd.concat([s[["away_sp", "season"]].rename(columns={"away_sp": "pid"}),
                    s[["home_sp", "season"]].rename(columns={"home_sp": "pid"})]).dropna()
    sp["pid"] = sp["pid"].astype(int)
    jobs = set()
    for pid, season in sp.drop_duplicates().itertuples(index=False):
        jobs.add((pid, season))
        jobs.add((pid, season - 1))
    print("pitcher-season logs to fetch: {}".format(len(jobs)), flush=True)
    logs = []
    with cf.ThreadPoolExecutor(8) as ex:
        futs = {ex.submit(mlbapi.pitcher_log, pid, season): (pid, season) for pid, season in jobs}
        for i, f in enumerate(cf.as_completed(futs), 1):
            try:
                df = f.result()
                if len(df):
                    logs.append(df)
            except Exception as e:
                print("   skip {}: {}".format(futs[f], str(e)[:60]), flush=True)
            if i % 1000 == 0:
                print("   {}/{} ({:.0f}s)".format(i, len(jobs), time.time() - t0), flush=True)
    logs = pd.concat(logs, ignore_index=True)
    logs.to_parquet(OUT / "mlb_pitcher_logs.parquet", index=False)
    print("pitcher logs: {} appearances, {} pitchers ({:.0f}s)".format(
        len(logs), logs["pitcher"].nunique(), time.time() - t0), flush=True)


if __name__ == "__main__":
    main()
