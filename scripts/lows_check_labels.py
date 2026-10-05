#!/usr/bin/env python3
"""Label validation for daily-low ladders. Fails (non-zero exit) on broken invariants.

1. bucket arithmetic reproduces Kalshi's `result` on every ladder market
2. exactly one YES bucket per ladder
3. settlement value vs the NWS CLI low, by settlement regime

  uv run scripts/lows_check_labels.py
"""

from __future__ import annotations

import json
import pathlib
import sys

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from pmdecide.dataset import regime  # noqa: E402
from pmdecide.lows import FORECAST_ROOT, LOW_SERIES, PANEL  # noqa: E402
from pmdecide.weather import (  # noqa: E402
    CITIES,
    bucket_contains,
    bucket_interval,
    is_partition,
    normalise_strikes,
)


def main():
    report, failed = {}, False
    for key in LOW_SERIES:
        f = PANEL / "{}.parquet".format(key)
        if not f.exists():
            continue
        m = normalise_strikes(pd.read_parquet(f).drop_duplicates("ticker"))
        unparsed = int(m["strike_type"].isna().sum())
        m = m[m["strike_type"].notna()]
        part = m.groupby("event").apply(
            lambda g: is_partition(
                [
                    bucket_interval(s, a, b)
                    for s, a, b in zip(g.strike_type, g["floor"], g["cap"], strict=True)
                ]
            ),
            include_groups=False,
        )
        ladder = m["event"].isin(part[part].index)
        a = m[m["settle"].notna() & ladder]
        ok = pd.Series(
            [
                bucket_contains(s, lo, hi, v) == bool(y)
                for s, lo, hi, v, y in zip(a.strike_type, a["floor"], a["cap"], a.settle, a.y, strict=True)
            ],
            index=a.index,
        )
        per_event = m[ladder].groupby("event")["y"].sum()
        r = {
            "markets": len(m),
            "ladders": int(part.sum()),
            "non_ladders": int((~part).sum()),
            "unparsed": unparsed,
            "arithmetic_agreement": float(ok.mean()) if len(ok) else None,
            "contradictions": a.loc[~ok, ["ticker", "settle", "y"]].to_dict("records"),
            "one_yes_share": float((per_event == 1).mean()) if len(per_event) else None,
        }
        cli = pd.read_parquet(FORECAST_ROOT / "{}_cli.parquet".format(CITIES[key].station))
        cli = cli[["valid", "low"]].rename(columns={"valid": "day"})
        ev = (
            m[ladder]
            .groupby("event")
            .agg(day=("day", "first"), settle=("settle", "first"), rules=("rules", "first"))
        )
        ev["regime"] = ev["rules"].map(regime)
        j = ev.merge(cli, on="day", how="left").dropna(subset=["low", "settle"])
        for g, d in j.groupby("regime"):
            diff = d["settle"] - d["low"]
            r["cli_" + g] = {
                "days": len(d),
                "agree": float((diff == 0).mean()),
                "diffs": {str(k): int(v) for k, v in diff[diff != 0].value_counts().items()},
            }
        report[key] = r
        bad = (r["arithmetic_agreement"] or 0) < 1.0 or (r["one_yes_share"] or 0) < 1.0
        failed |= bad
        print(
            "{:>5} markets={:5d} ladders={} non-ladders={} arith={} one_yes={} contra={} {}".format(
                key,
                len(m),
                r["ladders"],
                r["non_ladders"],
                r["arithmetic_agreement"],
                r["one_yes_share"],
                len(r["contradictions"]),
                "FAIL" if bad else "ok",
            )
        )
        for g in ("cli_nws_cli", "cli_twc"):
            if g in r:
                print(
                    "       {:<8} {} days, settle == CLI low {:.3f}, diffs {}".format(g[4:], *r[g].values())
                )
    (ROOT / "results" / "lows_label_check.json").write_text(json.dumps(report, indent=2, default=str))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
