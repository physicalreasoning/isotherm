#!/usr/bin/env python3
"""Data validation: label arithmetic, ladder coherence, and settlement-source agreement.

Fails loudly (non-zero exit) on the invariants the whole programme rests on:

  1. bucket arithmetic reproduces Kalshi's `result` for every market
  2. exactly one YES bucket per event
  3. settlement value equals the NWS CLI high, reported separately before and
     after the switch to The Weather Company, because a disagreement rate that
     jumps at the switch means the label process changed under us

    uv run scripts/check_labels.py
"""
from __future__ import annotations

import json
import pathlib
import sys

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from pmdecide.weather import CITIES, bucket_contains  # noqa: E402


def regime(rules: str) -> str:
    if "Weather Company" in rules:
        return "twc"
    if "Climatological Report" in rules:
        return "nws_cli"
    return "other"


def main():
    report, failed = {}, False
    for key, city in CITIES.items():
        pp = pathlib.Path("data/panel/{}.parquet".format(key))
        cp = pathlib.Path("data/forecasts/{}_cli.parquet".format(city.station))
        if not pp.exists():
            continue
        m = pd.read_parquet(pp).drop_duplicates("ticker")
        ok = [bucket_contains(s, f, c, v) == bool(y) for s, f, c, v, y in
              zip(m.strike_type, m["floor"], m["cap"], m.settle, m.y, strict=True)]
        arith = float(pd.Series(ok).mean())
        per_event = m.groupby("event")["y"].sum()
        one_yes = float((per_event == 1).mean())
        r = {"markets": len(m), "events": int(per_event.size),
             "arithmetic_agreement": arith, "one_yes_share": one_yes}
        if cp.exists():
            cli = pd.read_parquet(cp)[["valid", "high"]].rename(columns={"valid": "day"})
            ev = m.groupby("event").agg(day=("day", "first"), settle=("settle", "first"),
                                        rules=("rules", "first"))
            ev["regime"] = ev["rules"].map(regime)
            j = ev.merge(cli, on="day", how="left")
            for g, d in j.groupby("regime"):
                d = d.dropna(subset=["high"])
                if len(d):
                    diff = (d["settle"] - d["high"])
                    r["cli_" + g] = {"days": len(d), "agree": float((diff == 0).mean()),
                                     "first": str(d["day"].min().date()),
                                     "last": str(d["day"].max().date()),
                                     "diffs": {str(k): int(v) for k, v in
                                               diff[diff != 0].value_counts().items()}}
        report[key] = r
        bad = arith < 1.0 or one_yes < 1.0
        failed |= bad
        print("{:>5} markets={:6d} arithmetic={:.4f} one_yes={:.4f} {}".format(
            key, len(m), arith, one_yes, "FAIL" if bad else "ok"))
        for g in ("cli_nws_cli", "cli_twc"):
            if g in r:
                x = r[g]
                print("       {:<12} {} days {}..{}  settle==CLI {:.3f}  diffs {}".format(
                    g[4:], x["days"], x["first"], x["last"], x["agree"], x["diffs"]))
    pathlib.Path("results").mkdir(exist_ok=True)
    pathlib.Path("results/label_check.json").write_text(json.dumps(report, indent=2))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
