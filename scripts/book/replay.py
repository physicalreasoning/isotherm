#!/usr/bin/env python3
"""Rebuild order books from the recorder's raw messages (scripts/book/record.py).

Each market's book is its latest `orderbook_snapshot` plus every `orderbook_delta` after it, as
resting size by price on each side (YES bids and NO bids; a NO bid at p is a YES offer at 1 - p).

    uv run scripts/book/replay.py --check 20   # rebuild now, compare 20 markets with Kalshi's REST book

`--check` is the recorder's correctness test: a book rebuilt from the stream must equal the one
Kalshi serves, up to messages in flight between the last recorded line and the REST call.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import random
import sys
import zlib
from collections import defaultdict
from decimal import Decimal

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))
from isotherm import kalshi  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2] / "data" / "book" / "raw"


def read_lines(path, chunk=1 << 14):
    """Every line recoverable from a gzip file, even one with an unfinished stream inside.

    Files from before the crash-safe recorder may hold a stream cut off by a killed process with
    a new stream appended after it, which `gzip` refuses past the cut. Here each stream is
    decompressed chunk by chunk; at a cut we keep what came out and resume at the next gzip
    header.
    """
    data = pathlib.Path(path).read_bytes()
    pos = 0
    while pos < len(data):
        d, out, end = zlib.decompressobj(31), [], None
        i = pos
        try:
            while i < len(data) and not d.eof:
                out.append(d.decompress(data[i : i + chunk]))
                i += chunk
            end = len(data) - len(d.unused_data) if d.eof else len(data)
        except zlib.error:
            nxt = data.find(b"\x1f\x8b\x08", max(i - chunk, pos + 1))
            end = nxt if nxt > 0 else len(data)
        text = b"".join(out).decode("utf-8", errors="replace")
        yield from text.splitlines()
        pos = end


def messages(files):
    for f in files:
        for line in read_lines(f):
            try:
                yield json.loads(line)
            except json.JSONDecodeError:  # a line cut off at a crash
                continue


def file_order(f: pathlib.Path):
    """(date, hour, run start): files from before per-run naming (HH.jsonl.gz) count as run 0."""
    hour, _, run = f.name.split(".")[0].partition("-")
    return f.parent.name, int(hour), int(run or 0)


def levels(pairs) -> dict:
    return {Decimal(p): Decimal(q) for p, q in pairs or []}


def rebuild(files) -> tuple[dict, dict]:
    """{ticker: {"yes": {price: size}, "no": {...}}} and {ticker: last message time (ms)}."""
    books, last = {}, {}
    for rec in messages(files):
        m = rec["m"]
        t, msg = m.get("type"), m.get("msg") or {}
        tk = msg.get("market_ticker")
        if t == "orderbook_snapshot":
            books[tk] = {s: levels(msg.get(f"{s}_dollars_fp")) for s in ("yes", "no")}
            last[tk] = rec["recv_ms"]
        elif t == "orderbook_delta" and tk in books:
            side = books[tk][msg["side"]]
            p = Decimal(msg["price_dollars"])
            side[p] = side.get(p, Decimal(0)) + Decimal(msg["delta_fp"])
            if side[p] <= 0:
                del side[p]
            last[tk] = rec["recv_ms"]
    return books, last


def rest_book(ticker) -> dict:
    ob = kalshi.get(f"markets/{ticker}/orderbook").get("orderbook_fp", {})
    return {s: levels(ob.get(f"{s}_dollars")) for s in ("yes", "no")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", type=int, default=20, help="markets to compare with the REST book")
    a = ap.parse_args()
    files = sorted(ROOT.glob("*/*.jsonl.gz"), key=file_order)
    books, _ = rebuild(files)
    print(len(files), "files,", len(books), "markets rebuilt")
    stats = defaultdict(int)
    for tk in random.Random(0).sample(sorted(books), min(a.check, len(books))):
        live = rest_book(tk)
        same = live == books[tk]
        top = all(max(live[s], default=None) == max(books[tk][s], default=None) for s in ("yes", "no"))
        stats["identical"] += same
        stats["same_best_bids"] += top
        if not same:
            diff = sum(
                abs(live[s].get(p, 0) - books[tk][s].get(p, 0))
                for s in ("yes", "no")
                for p in set(live[s]) | set(books[tk][s])
            )
            note = "best bids match" if top else "best bids differ"
            print(f"  {tk} differs by {diff} contracts ({note})")
    print(dict(stats), "of", min(a.check, len(books)))


if __name__ == "__main__":
    main()
