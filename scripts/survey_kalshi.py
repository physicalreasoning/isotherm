#!/usr/bin/env python3
"""Survey of Kalshi's settled history: what data exists beyond the weather ladders?

Two public listings, paged by cursor and saved as they go (resumable):
  events   every settled event: category, series, whether its markets are mutually exclusive
  markets  every settled market: event, strike type, open and close time, volume, result
Then per category and series: events, markets, ladders vs yes/no, date span, volume.

    uv run scripts/survey_kalshi.py            # fetch (slow, polite) and summarise
    uv run scripts/survey_kalshi.py --summary  # summarise what is already fetched
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from isotherm import kalshi  # noqa: E402

OUT = pathlib.Path("data/kalshi_survey")
EVENT_COLS = ["event_ticker", "series_ticker", "category", "title", "mutually_exclusive"]
MARKET_COLS = [
    "ticker", "event_ticker", "strike_type", "floor_strike", "cap_strike", "open_time", "close_time",
    "volume", "volume_fp", "result", "market_type",
]  # fmt: skip


def crawl(kind: str, cols: list, limit: int):
    """Page through /{kind}?status=settled, one parquet part per page; resume from the saved cursor."""
    d = OUT / kind
    d.mkdir(parents=True, exist_ok=True)
    state = d / "cursor.json"
    st = json.loads(state.read_text()) if state.exists() else {"cursor": None, "page": 0, "done": False}
    while not st["done"]:
        r = kalshi.get(kind, status="settled", limit=limit, cursor=st["cursor"])
        rows = r.get(kind, [])
        if rows:
            df = pd.DataFrame([{c: x.get(c) for c in cols} for x in rows])
            df.to_parquet(d / "part{:06d}.parquet".format(st["page"]), index=False)
        st = {
            "cursor": r.get("cursor") or None,
            "page": st["page"] + 1,
            "done": not r.get("cursor") or not rows,
        }
        state.write_text(json.dumps(st))
        if st["page"] % 50 == 0:
            print(kind, "page", st["page"], flush=True)
    print(kind, "done,", st["page"], "pages", flush=True)


def load(kind):
    parts = sorted((OUT / kind).glob("part*.parquet"))
    return pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True) if parts else pd.DataFrame()


def summarise_events():
    """Category and series counts from the events listing alone (the market listing is days long)."""
    ev = load("events").drop_duplicates("event_ticker")
    cat = ev.groupby("category").agg(events=("event_ticker", "size"), series=("series_ticker", "nunique"))
    cat = cat.sort_values("events", ascending=False)
    top = (
        ev.groupby(["category", "series_ticker"]).size().rename("events").reset_index()
        .sort_values("events", ascending=False).groupby("category").head(8)
    )  # fmt: skip
    res = {
        "events": len(ev),
        "by_category": cat.reset_index().to_dict(orient="records"),
        "top_series": top.to_dict(orient="records"),
    }
    pathlib.Path("results/kalshi_survey.json").write_text(json.dumps(res, indent=1))
    print(cat.to_string())


def summarise():
    ev, mk = load("events").drop_duplicates("event_ticker"), load("markets").drop_duplicates("ticker")
    mk["vol"] = pd.to_numeric(mk["volume_fp"].fillna(mk["volume"]), errors="coerce").fillna(0)
    mk["close"] = pd.to_datetime(mk["close_time"], errors="coerce", utc=True)
    per_ev = mk.groupby("event_ticker").agg(
        n=("ticker", "size"),
        ladder=(
            "strike_type",
            lambda s: s.isin(["between", "greater", "less", "greater_or_equal", "less_or_equal"]).sum() >= 3,
        ),  # noqa: E501
        vol=("vol", "sum"),
        first=("close", "min"),
        last=("close", "max"),
    )
    j = per_ev.join(ev.set_index("event_ticker")[["series_ticker", "category"]], how="left")
    j["category"] = j["category"].fillna("(unknown)")
    j["kind"] = j["ladder"].map({True: "ladder", False: "yes/no or other"})
    cat = j.groupby(["category", "kind"]).agg(
        events=("n", "size"), markets=("n", "sum"), volume=("vol", "sum"),
        first=("first", "min"), last=("last", "max"), series=("series_ticker", "nunique"),
    ).reset_index().sort_values("events", ascending=False)  # fmt: skip
    ser = j[j["ladder"]].groupby(["category", "series_ticker"]).agg(
        events=("n", "size"), markets=("n", "sum"), volume=("vol", "sum"),
        first=("first", "min"), last=("last", "max"),
    ).reset_index().sort_values("events", ascending=False)  # fmt: skip
    res = {
        "events": len(j),
        "markets": int(j["n"].sum()),
        "by_category": json.loads(cat.to_json(orient="records", date_format="iso")),
        "top_ladder_series": json.loads(ser.head(60).to_json(orient="records", date_format="iso")),
    }
    pathlib.Path("results/kalshi_survey.json").write_text(json.dumps(res, indent=1))
    pd.set_option("display.width", 200)
    print(cat.to_string(index=False))
    print("\nTop ladder series:\n", ser.head(30).to_string(index=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--events-only", action="store_true", help="crawl and summarise events only")
    a = ap.parse_args()
    if a.events_only:
        crawl("events", EVENT_COLS, 200)
        return summarise_events()
    if not a.summary:
        crawl("events", EVENT_COLS, 200)
        crawl("markets", MARKET_COLS, 1000)
    summarise()


if __name__ == "__main__":
    main()
