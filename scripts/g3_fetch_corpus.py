#!/usr/bin/env python3
"""Fetch the G3 physics corpus: CLI highs, GFS MOS and NBM for every pretraining station.

Slow on purpose: IEM is shared with other jobs, so one request every 5 seconds.

    uv run scripts/g3_fetch_corpus.py
"""

from __future__ import annotations

import json
import pathlib
import sys

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from pmdecide import iem  # noqa: E402
from pmdecide.pretrain import STATIONS  # noqa: E402

iem.MIN_INTERVAL = 5.0
OUT = pathlib.Path("data/forecasts")
KEEP = {"GFS": ["runtime", "ftime", "n_x", "tmp"], "NBS": ["runtime", "ftime", "txn", "xnd", "tmp", "tsd"]}
YEARS = range(2021, 2027)


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
    cover = {}
    for st in STATIONS:
        files = {m: OUT / "{}_{}.parquet".format(st, m) for m in ("cli", "GFS", "NBS")}
        if all(f.exists() for f in files.values()):
            cover[st] = "cached"
            continue
        cli = pd.concat([iem.cli(st, y) for y in YEARS], ignore_index=True)
        if cli.empty or cli["high"].notna().sum() < 700:
            cover[st] = "no CLI"
            print("{}: no CLI, skipped".format(st), flush=True)
            continue
        gfs, nbs = model_frames(st, "GFS"), model_frames(st, "NBS")
        if gfs.empty or nbs.empty:
            cover[st] = "no MOS"
            print("{}: missing MOS, skipped".format(st), flush=True)
            continue
        cli.to_parquet(files["cli"], index=False)
        gfs.to_parquet(files["GFS"], index=False)
        nbs.to_parquet(files["NBS"], index=False)
        cover[st] = {"cli_days": int(cli["high"].notna().sum()), "gfs_rows": len(gfs), "nbs_rows": len(nbs)}
        print("{}: {}".format(st, cover[st]), flush=True)
    pathlib.Path("data/g3_coverage.json").write_text(json.dumps(cover, indent=1))


if __name__ == "__main__":
    main()
