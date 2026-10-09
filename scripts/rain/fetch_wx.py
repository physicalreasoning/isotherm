#!/usr/bin/env python3
"""NWS CLI precipitation and MOS PoP (NBM, GFS) for the market stations, then the corpus.

2021-2025 responses are already cached by `iem` from the station corpus download (FINDINGS §32);
2026 is fetched once (MOS up to 2026-10-06 lands in the iem cache, CLI 2026 under data/rain/cli).
Market stations also get the live window to 2026-10-09. One IEM request every 3 s.

    uv run scripts/rain/fetch_wx.py                # market stations only
    uv run scripts/rain/fetch_wx.py --corpus       # then every corpus station
"""

from __future__ import annotations

import argparse
import time

from common import DATA, cli_precip, corpus, iem, mos_precip

MARKET_STATIONS = (
    "KABQ KATL KAUS KBOS KORD KCLL KCMH KDFW KDCA KDEN KEWR KHOU KIAH KIND KLAX KLEX KLAS KMIA KMSP "
    "KMKE KMSY KNYC KOKC KPHL KPHX KPIT KPVD KSAT KSEA KSFO KSGF KTTN"
).split()
LIVE_END = "2026-10-09"


def one(st: str, live: bool) -> str:
    c = cli_precip(st)
    if c.empty:
        return "no CLI"
    g = mos_precip(st, "GFS", LIVE_END if live else None)
    n = mos_precip(st, "NBS", LIVE_END if live else None)
    return "cli {} days, GFS {} rows, NBS {} rows".format(c["wet"].notna().sum(), len(g), len(n))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", action="store_true")
    a = ap.parse_args()
    iem.MIN_INTERVAL = 3.0
    todo = [(s, True) for s in MARKET_STATIONS]
    if a.corpus:
        todo += [(s, False) for s in corpus() if s not in MARKET_STATIONS]
    t0 = time.time()
    status = {}
    for i, (st, live) in enumerate(todo, 1):
        try:
            status[st] = one(st, live)
        except Exception as e:
            status[st] = "error: " + str(e)[:80]
        print(
            "{}/{} {} {} ({:.0f} min)".format(i, len(todo), st, status[st], (time.time() - t0) / 60),
            flush=True,
        )
    (DATA / "wx_status.txt").write_text("\n".join("{} {}".format(k, v) for k, v in status.items()))


if __name__ == "__main__":
    main()
