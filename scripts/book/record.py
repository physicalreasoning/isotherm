#!/usr/bin/env python3
"""Order-book recorder (Track B): every open weather and commodity ladder, live from Kalshi's websocket.

Kalshi's history keeps hourly candles and trades but no depth, so a fill or adverse-selection
model needs books we record ourselves. This keeps one authenticated connection, subscribes to
`orderbook_delta` (a full snapshot per market, then every change) and `trade` for every open
market of the series below, and adds markets as new events list (checked every 10 minutes).

Raw messages, unchanged, plus our receive time, go to
data/book/raw/YYYY-MM-DD/HH-<run start>.jsonl.gz (UTC hour; one file per hour per run, flushed
every minute, so a crash loses at most a minute and never corrupts earlier data). Anything that breaks
the record is logged to data/book/gaps.jsonl: disconnects (with how long we were down) and
sequence jumps. After either, every market is resubscribed, which sends fresh snapshots.

    uv run scripts/book/record.py            # runs until killed
    uv run scripts/book/record.py --once 60  # record 60 s, then exit (smoke test)

Needs KALSHI_API_KEY_ID and KALSHI_PRIVATE_KEY_PATH (the websocket requires a signed handshake).
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import gzip
import json
import pathlib
import shutil
import signal
import sys
import time
import zlib

import websockets

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))
from isotherm import kalshi  # noqa: E402
from isotherm.lows import LOW_SERIES  # noqa: E402
from isotherm.weather import CITIES, NEW_CITIES  # noqa: E402

URL = "wss://api.elections.kalshi.com/trade-api/ws/v2"
ROOT = pathlib.Path(__file__).resolve().parents[2] / "data" / "book"
SERIES = (
    [c.series for c in CITIES.values()]
    + [c.series for c in NEW_CITIES.values()]
    + list(LOW_SERIES.values())
    + ["KXRAIN"]
    + ["KXWTI", "KXGOLDD", "KXSILVERD", "KXCOPPERD", "KXBRENTD", "KXNATGASD"]
)
REFRESH_S = 600
MIN_FREE = 25 * 2**30  # stop before the disk fills
FLUSH_S = 60
CHANNELS = ["orderbook_delta", "trade"]


def open_tickers() -> set[str]:
    out = set()
    for s in SERIES:
        try:
            r = kalshi.get("events", status="open", series_ticker=s, with_nested_markets="true", limit=200)
        except Exception as ex:  # one series failing must not stop the recorder
            log_gap({"kind": "list_failed", "series": s, "error": str(ex)[:200]})
            continue
        for e in r.get("events", []):
            out.update(
                m["ticker"] for m in e.get("markets", []) if m.get("status") in (None, "active", "open")
            )
    return out


def log_gap(rec: dict) -> None:
    rec = {"ts": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"), **rec}
    ROOT.mkdir(parents=True, exist_ok=True)
    with open(ROOT / "gaps.jsonl", "a") as f:
        f.write(json.dumps(rec) + "\n")
    print("gap", json.dumps(rec), flush=True)


class Sink:
    """Writes lines to this run's file for the current UTC hour; rolls over on the hour.

    Each run writes its own files (HH-<run start>.jsonl.gz) and never appends to an older one:
    a killed process leaves an unfinished gzip stream, and anything appended after it would be
    unreadable. The stream is sync-flushed every FLUSH_S seconds, so a crash loses at most that.
    """

    def __init__(self):
        self.key, self.f, self.n, self.run = None, None, 0, int(time.time())
        self.flushed = time.time()

    def write(self, line: str) -> None:
        now = dt.datetime.now(dt.UTC)
        key = now.strftime("%Y-%m-%d/%H")
        if key != self.key:
            self.close()
            p = ROOT / "raw" / f"{key}-{self.run}.jsonl.gz"
            p.parent.mkdir(parents=True, exist_ok=True)
            self.f, self.key = gzip.open(p, "wt"), key
        self.f.write(line + "\n")
        self.n += 1
        if time.time() - self.flushed > FLUSH_S:
            self.f.flush()
            self.f.buffer.flush(zlib.Z_SYNC_FLUSH)
            self.flushed = time.time()
        if self.n % 20000 == 0 and shutil.disk_usage(ROOT).free < MIN_FREE:
            log_gap({"kind": "disk_low", "free_gb": shutil.disk_usage(ROOT).free // 2**30})
            raise SystemExit(f"stopping: under {MIN_FREE // 2**30} GB free")

    def close(self) -> None:
        if self.f:
            self.f.close()
            self.f = None


async def send(ws, cmd_id: int, cmd: str, params: dict) -> None:
    await ws.send(json.dumps({"id": cmd_id, "cmd": cmd, "params": params}))


async def session(sink: Sink, deadline: float | None) -> None:
    headers = kalshi.auth_headers("GET", URL)
    async with websockets.connect(URL, additional_headers=headers, open_timeout=20, max_size=2**24) as ws:
        tickers = await asyncio.to_thread(open_tickers)
        await send(ws, 1, "subscribe", {"channels": CHANNELS, "market_tickers": sorted(tickers)})
        print("subscribed", len(tickers), "markets", flush=True)
        sids, last_seq, next_refresh, cmd_id = [], {}, time.time() + REFRESH_S, 2
        while deadline is None or time.time() < deadline:
            if time.time() >= next_refresh and sids:
                new = await asyncio.to_thread(open_tickers) - tickers
                if new:
                    params = {"sids": sids, "market_tickers": sorted(new), "action": "add_markets"}
                    await send(ws, cmd_id, "update_subscription", params)
                    cmd_id += 1
                    tickers |= new
                    print("added", len(new), "markets, now", len(tickers), flush=True)
                next_refresh = time.time() + REFRESH_S
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=60)
            except TimeoutError:
                continue
            m = json.loads(raw)
            if m.get("type") == "subscribed":
                sids.append(m["msg"]["sid"])
            elif m.get("type") == "error":
                log_gap({"kind": "server_error", "msg": m.get("msg")})
            sid, seq = m.get("sid"), m.get("seq")
            if seq is not None:
                if sid in last_seq and seq != last_seq[sid] + 1:
                    log_gap({"kind": "seq_jump", "sid": sid, "expected": last_seq[sid] + 1, "got": seq})
                    sink.write(json.dumps({"recv_ms": int(time.time() * 1000), "m": m}))
                    return  # reconnect: fresh snapshots for every market
                last_seq[sid] = seq
            sink.write(json.dumps({"recv_ms": int(time.time() * 1000), "m": m}))


async def main(once: float | None) -> None:
    sink = Sink()
    # launchd stops us with SIGTERM: cancel, so the finally below closes the open file.
    asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, asyncio.current_task().cancel)
    deadline = time.time() + once if once else None
    backoff, down_since = 1, None
    try:
        while deadline is None or time.time() < deadline:
            try:
                if down_since is not None:
                    log_gap({"kind": "reconnected", "down_s": round(time.time() - down_since, 1)})
                    down_since = None
                await session(sink, deadline)
                backoff = 1
            except Exception as ex:
                if down_since is None:
                    down_since = time.time()
                    log_gap({"kind": "disconnect", "error": repr(ex)[:200]})
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)
                continue
            if down_since is None and (deadline is None or time.time() < deadline):
                down_since = time.time()  # deliberate reconnect after a sequence jump
    finally:
        sink.close()
        print("wrote", sink.n, "messages", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", type=float, help="record this many seconds, then exit")
    asyncio.run(main(ap.parse_args().once))
