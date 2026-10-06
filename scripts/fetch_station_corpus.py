#!/usr/bin/env python3
"""Fetch the station corpus for the multi-station weather model (FINDINGS §32).

Every site that issues an NWS Daily Climate Report (CLI) on 2026-10-01, about 600, with
CLI highs and lows, GFS MOS and NBM for 2021 onward: real forecasts and real outcomes, no
market. Slow on purpose (one IEM request every 3 s) and resumable: a station whose three
files exist is skipped, and every closed-window response is cached by `iem`.

    uv run scripts/fetch_station_corpus.py            # roughly 9 hours
"""

from __future__ import annotations

import json
import pathlib
import sys
import time

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from isotherm import iem  # noqa: E402

iem.MIN_INTERVAL = 3.0
OUT = pathlib.Path("data/forecasts")
LIST = pathlib.Path("data/corpus_stations.json")
KEEP = {"GFS": ["runtime", "ftime", "n_x", "tmp"], "NBS": ["runtime", "ftime", "txn", "xnd", "tmp", "tsd"]}
YEARS = range(2021, 2027)


def stations():
    if LIST.exists():
        return json.loads(LIST.read_text())
    body = iem._fetch(iem.BASE + "/geojson/cli.py?dt=2026-10-01")
    feats = json.loads(body)["features"]
    out = sorted(
        {
            f["properties"]["station"]: {
                "name": f["properties"]["name"],
                "state": f["properties"]["state"],
                "lat": f["properties"]["lat"],
                "lon": f["properties"]["lon"],
            }
            for f in feats
            if str(f["properties"].get("station", "")).startswith("K")
        }.items()
    )
    LIST.write_text(json.dumps(dict(out), indent=1))
    return dict(out)


def model_frames(st, model):
    parts = []
    for y in YEARS:
        try:
            df = iem.mos(st, model, "{}-01-01".format(y), "{}-01-01".format(y + 1))
        except Exception as e:
            print("   {} {} {}: {}".format(st, model, y, str(e)[:60]), flush=True)
            continue
        if not df.empty:
            parts.append(df[[c for c in KEEP[model] if c in df.columns]])
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sts = stations()
    print("{} CLI stations".format(len(sts)), flush=True)
    cover, t0 = {}, time.time()
    for i, st in enumerate(sts, 1):
        files = {m: OUT / "{}_{}.parquet".format(st, m) for m in ("cli", "GFS", "NBS")}
        if all(f.exists() for f in files.values()):
            cover[st] = "cached"
            continue
        try:
            cli = pd.concat([iem.cli(st, y) for y in YEARS], ignore_index=True)
        except Exception as e:
            cover[st] = "CLI error: " + str(e)[:40]
            continue
        if cli.empty or cli["high"].notna().sum() < 700:
            cover[st] = "short CLI"
            continue
        gfs = model_frames(st, "GFS")
        if gfs.empty:
            cover[st] = "no GFS MOS"
            continue
        nbs = model_frames(st, "NBS")
        if nbs.empty:
            cover[st] = "no NBM"
            continue
        cli.to_parquet(files["cli"], index=False)
        gfs.to_parquet(files["GFS"], index=False)
        nbs.to_parquet(files["NBS"], index=False)
        cover[st] = "ok"
        print("{}/{} {} ok ({:.0f} min)".format(i, len(sts), st, (time.time() - t0) / 60), flush=True)
    pathlib.Path("data/corpus_coverage.json").write_text(json.dumps(cover, indent=1))
    n = sum(v in ("ok", "cached") for v in cover.values())
    print("done: {} stations usable of {}".format(n, len(sts)), flush=True)


if __name__ == "__main__":
    main()
