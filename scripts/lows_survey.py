#!/usr/bin/env python3
"""Survey daily low-temperature and rain series with the method of scripts/survey_markets.py.

uv run scripts/lows_survey.py --events 40
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("survey", ROOT / "scripts" / "survey_markets.py")
survey = importlib.util.module_from_spec(spec)
spec.loader.exec_module(survey)

CANDIDATES = [
    ("KXLOWTNYC", "lows", "NYC daily low"),
    ("KXLOWTCHI", "lows", "Chicago daily low"),
    ("KXLOWTMIA", "lows", "Miami daily low"),
    ("KXLOWTAUS", "lows", "Austin daily low"),
    ("KXLOWTLAX", "lows", "LA daily low"),
    ("KXLOWTDEN", "lows", "Denver daily low"),
    ("KXLOWTPHIL", "lows", "Philadelphia daily low"),
    ("KXHIGHNY", "highs", "control: NYC daily high"),
    ("KXRAINNYC", "rain", "NYC rain, daily"),
    ("KXRAIN", "rain", "where will it rain, daily"),
    ("KXRAINNYCM", "rain", "NYC monthly rain total"),
    ("KXRAINCHIM", "rain", "Chicago monthly rain"),
    ("KXRAINWKND", "rain", "weekend rain"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", type=int, default=40)
    ap.add_argument("--out", default="results/lows_survey.json")
    a = ap.parse_args()
    out = []
    for series, cat, note in CANDIDATES:
        print("==", series, flush=True)
        try:
            s = survey.run_series(series, a.events, 40, 0)
        except Exception as e:
            print("   FAILED", e, flush=True)
            continue
        s.update(category=cat, note=note)
        out.append(s)
        x = s.get("lead0.5", {})
        print(
            "   events={} since={} vol/ev={} markets/ev={} two-sided={} spread={} brier={} slope={}".format(
                s["listed_settled_events"],
                s["first_event"],
                survey.fmt(s["median_event_volume"], 0),
                survey.fmt(s["median_markets_per_event"], 0),
                survey.fmt(x.get("two_sided_share"), 2),
                survey.fmt(x.get("median_spread")),
                survey.fmt(x.get("brier")),
                survey.fmt(x.get("slope"), 2),
            ),
            flush=True,
        )
    p = ROOT / a.out
    p.parent.mkdir(exist_ok=True)
    p.write_text(
        json.dumps(
            {"generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "results": out},
            indent=2,
            default=str,
        )
    )
    print("wrote", p)


if __name__ == "__main__":
    main()
