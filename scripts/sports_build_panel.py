#!/usr/bin/env python3
"""Build the point-in-time MLB game-winner panel from Kalshi, linked to MLB games.

  1. every settled KXMLBGAME event and its two markets (labels = Kalshi `result`)
  2. link each event to its MLB game (scheduled first pitch from the MLB schedule)
  3. 1-minute candles over [first pitch - 24h, first pitch] for both markets, read at
     T-24h, T-3h and T-15min; capacity = contracts traded between the read and first pitch

Writes data/sports/mlb_markets.parquet (raw rows), data/sports/mlb_links.parquet and
data/sports/mlb_panel.parquet (one row per market per read time).

    uv run scripts/sports_build_panel.py
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import pathlib
import sys
import time

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from pmdecide import kalshi  # noqa: E402
from pmdecide.sports.kalshi_mlb import READS, link, period_of, quote_at, volume_between  # noqa: E402

OUT = pathlib.Path("data/sports")
SERIES = "KXMLBGAME"


def fetch_markets(workers):
    evs = kalshi.settled_events(SERIES, max_pages=100)
    print("settled events: {}".format(len(evs)), flush=True)
    rows = []

    def one(e):
        return [dict(r, event=e["event_ticker"]) for r in kalshi.event_markets(e["event_ticker"])]

    with cf.ThreadPoolExecutor(workers) as ex:
        for i, got in enumerate(ex.map(one, evs), 1):
            rows.extend(got)
            if i % 1000 == 0:
                print("   markets for {}/{} events".format(i, len(evs)), flush=True)
    keep = [
        "event",
        "ticker",
        "result",
        "yes_sub_title",
        "open_time",
        "close_time",
        "volume_fp",
        "rules_primary",
        "expected_expiration_time",
        "status",
    ]
    df = pd.DataFrame(rows)
    df = df[[c for c in keep if c in df.columns]]
    df["code"] = df["ticker"].str.split("-").str[-1]
    df["volume"] = pd.to_numeric(df["volume_fp"], errors="coerce").fillna(0.0)
    return df


def event_rows(ev, m, lk):
    """Panel rows for one linked event."""
    T = int(lk["first_pitch"].timestamp())
    out = []
    for r in m.itertuples(index=False):
        o = kalshi.ts(r.open_time)
        start = max(o, T - int(READS["t_24h"].total_seconds()) - 600)
        mk = {"ticker": r.ticker, "open_time": r.open_time, "close_time": r.close_time, "result": r.result}
        ok = True
        try:
            cs = kalshi.candles(mk, interval=1, start_ts=start, end_ts=T) if start < T else []
            cs = sorted(cs, key=lambda c: c["end_period_ts"])
        except Exception as e:
            print("   candles {}: {}".format(r.ticker, str(e)[:60]), flush=True)
            cs, ok = [], False
        for name, dt in READS.items():
            t = T - int(dt.total_seconds())
            b, a = quote_at(cs, t) if t >= o else (None, None)
            out.append(
                {
                    "event": ev,
                    "ticker": r.ticker,
                    "code": r.code,
                    "side": "home" if r.code == lk["home"] else "away",
                    "y": 1 if r.result == "yes" else 0,
                    "result": r.result,
                    "day": lk["day"],
                    "period": period_of(lk["day"]),
                    "game_pk": lk["game_pk"],
                    "first_pitch_ts": T,
                    "read": name,
                    "read_ts": t,
                    "open_ts": o,
                    "bid": b,
                    "ask": a,
                    "vol_after": volume_between(cs, t, T),
                    "market_volume": r.volume,
                    "candles_ok": ok,
                }
            )
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--refetch-markets", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    mp = OUT / "mlb_markets.parquet"
    if mp.exists() and not a.refetch_markets:
        markets = pd.read_parquet(mp)
    else:
        markets = fetch_markets(a.workers)
        markets.to_parquet(mp, index=False)
    res = markets.groupby("event")["result"].agg(lambda s: tuple(sorted(s)))
    print(
        "events {} | result patterns {}".format(markets["event"].nunique(), res.value_counts().to_dict()),
        flush=True,
    )

    sched = pd.read_parquet(OUT / "mlb_schedule.parquet")
    teams = pd.read_parquet(OUT / "mlb_teams.parquet")
    ev = (
        markets.groupby("event")
        .agg(codes=("code", lambda s: tuple(sorted(s))), rules=("rules_primary", "first"))
        .reset_index()
    )
    links = link(ev, sched, teams)
    links["results"] = links["event"].map(res)
    links.to_parquet(OUT / "mlb_links.parquet", index=False)
    print("link status: {}".format(links["link"].value_counts().to_dict()), flush=True)

    good = links[(links["link"] == "ok") & (links["results"] == ("no", "yes"))]
    print("events usable (linked, one YES, one NO): {}".format(len(good)), flush=True)
    by_ev = {e: g for e, g in markets.groupby("event")}
    rows = []
    with cf.ThreadPoolExecutor(a.workers) as ex:
        futs = {
            ex.submit(event_rows, r["event"], by_ev[r["event"]], r): r["event"]
            for r in good.to_dict("records")
        }
        for i, f in enumerate(cf.as_completed(futs), 1):
            try:
                rows.extend(f.result())
            except Exception as e:
                print("   skip {}: {}".format(futs[f], str(e)[:80]), flush=True)
            if i % 500 == 0:
                print("   {}/{} events ({:.0f}s)".format(i, len(good), time.time() - t0), flush=True)
    panel = pd.DataFrame(rows)
    panel.to_parquet(OUT / "mlb_panel.parquet", index=False)
    print(
        "wrote panel: {} rows, {} events ({:.0f}s)".format(
            len(panel), panel["event"].nunique(), time.time() - t0
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
