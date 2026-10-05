"""Kalshi public market-data client.

Adapted from our earlier internal project pm-jepa. Every endpoint used here
serves market rows, candlesticks, trades and settlement without a key. We only
ever issue GETs for market data; nothing here can place an order.

Optional API key, only to lift the anonymous rate limit:

    export KALSHI_API_KEY_ID=...                       # the Key ID shown on kalshi.com
    export KALSHI_PRIVATE_KEY_PATH=~/.kalshi/key.pem   # chmod 600, never in the repo
    export KALSHI_MIN_INTERVAL=0.06                    # optional, seconds between calls

Requests are then signed (RSA-PSS over timestamp + method + path, Kalshi's
scheme). The cache is keyed on URL alone, so signed and anonymous runs share it.

What changed since pm-jepa (verified against the live API on 2026-10-04):

  - The rolling purge pm-jepa raced is gone. Markets settled before
    `GET /historical/cutoff` (2026-08-05 at time of writing) moved to
    `/historical/markets`, `/historical/markets/{t}/candlesticks` and
    `/historical/trades`, back to the first event of each series (2021 for
    KXHIGHNY). History is now a query, not a snapshot job.
  - Historical candles use un-suffixed field names (`close`, `open_interest`)
    where live candles use `close_dollars`, `open_interest_fp`. `candle_quote`
    reads both.
  - Trades carry `taker_side`, so trade direction is observed, not inferred.
"""

from __future__ import annotations

import calendar
import gzip
import hashlib
import http.client
import json
import os
import pathlib
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from base64 import b64encode
from typing import Dict, Iterator, List, Optional, Tuple

BASE = "https://api.elections.kalshi.com/trade-api/v2"
MIN_INTERVAL = float(os.environ.get("KALSHI_MIN_INTERVAL", 0.12))  # anonymous: stay polite
KEY_ID = os.environ.get("KALSHI_API_KEY_ID")
KEY_PATH = os.environ.get("KALSHI_PRIVATE_KEY_PATH")
MAX_RETRIES = 6

CACHE = pathlib.Path(
    os.environ.get("PMDECIDE_CACHE", pathlib.Path(__file__).resolve().parents[2] / "data_cache" / "http")
)

_lock = threading.Lock()
_last_call = [0.0]
_cutoff_ts: List[Optional[int]] = [None]
_key: list = []


def _private_key():
    if not _key:
        from cryptography.hazmat.primitives import serialization

        data = pathlib.Path(KEY_PATH).expanduser().read_bytes()
        _key.append(serialization.load_pem_private_key(data, password=None))
    return _key[0]


def sign(private_key, method: str, url: str, ts_ms: str) -> str:
    """Kalshi request signature over timestamp + METHOD + path (no query string).

    RSA keys sign with PSS(SHA256, salt = digest length); Ed25519 keys, which
    Kalshi issues as of 2026-10, sign the same message directly.
    """
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ed25519, padding

    msg = (ts_ms + method + urllib.parse.urlparse(url).path).encode()
    if isinstance(private_key, ed25519.Ed25519PrivateKey):
        sig = private_key.sign(msg)
    else:
        sig = private_key.sign(
            msg,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
            hashes.SHA256(),
        )
    return b64encode(sig).decode()


def auth_headers(method: str, url: str) -> Dict[str, str]:
    if not (KEY_ID and KEY_PATH):
        return {}
    ts_ms = str(int(time.time() * 1000))
    return {
        "KALSHI-ACCESS-KEY": KEY_ID,
        "KALSHI-ACCESS-TIMESTAMP": ts_ms,
        "KALSHI-ACCESS-SIGNATURE": sign(_private_key(), method, url, ts_ms),
    }


def _throttle() -> None:
    with _lock:
        dt = time.time() - _last_call[0]
        if dt < MIN_INTERVAL:
            time.sleep(MIN_INTERVAL - dt)
        _last_call[0] = time.time()


def get(path: str, _cache: bool = False, **params) -> Dict:
    """GET with throttling and bounded exponential backoff on 429/5xx.

    `_cache=True` only for responses that cannot change: anything about a market
    that has already settled. Keyed on the full URL, gzipped, written atomically.
    """
    q = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}, safe=",")
    url = "{}/{}{}".format(BASE, path.lstrip("/"), ("?" + q) if q else "")
    if _cache:
        f = (
            CACHE
            / hashlib.sha256(url.encode()).hexdigest()[:2]
            / (hashlib.sha256(url.encode()).hexdigest()[:24] + ".json.gz")
        )
        if f.exists():
            try:
                return json.loads(gzip.decompress(f.read_bytes()), strict=False)
            except (OSError, ValueError):
                f.unlink(missing_ok=True)
        out = _fetch(url)
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp{}".format(threading.get_ident()))
        tmp.write_bytes(gzip.compress(json.dumps(out).encode()))
        tmp.replace(f)
        return out
    return _fetch(url)


def _fetch(url: str) -> Dict:
    delay = 1.0
    for attempt in range(MAX_RETRIES):
        _throttle()
        try:
            req = urllib.request.Request(url, headers=auth_headers("GET", url))
            with urllib.request.urlopen(req, timeout=45) as r:
                # strict=False: Kalshi rule text contains raw control characters
                return json.loads(r.read().decode(), strict=False)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES - 1:
                time.sleep(delay)
                delay *= 2
                continue
            raise
        except (urllib.error.URLError, TimeoutError, http.client.IncompleteRead, ConnectionError):
            if attempt < MAX_RETRIES - 1:
                time.sleep(delay)
                delay *= 2
                continue
            raise
    raise RuntimeError("unreachable")


def ts(iso: str) -> int:
    """ISO8601 (UTC) -> unix seconds."""
    return calendar.timegm(time.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S"))


def to_float(x) -> Optional[float]:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def cutoff_ts() -> int:
    """Markets settled before this live under /historical/*."""
    if _cutoff_ts[0] is None:
        _cutoff_ts[0] = ts(get("historical/cutoff")["market_settled_ts"])
    return _cutoff_ts[0]


def is_historical(market: Dict) -> bool:
    return ts(market["close_time"]) < cutoff_ts()


# ---------------------------------------------------------------- listing


def _paginate(path: str, key: str, max_pages: int, _cache: bool = False, **params) -> Iterator[Dict]:
    cursor = None
    for _ in range(max_pages):
        d = get(path, _cache=_cache, cursor=cursor, **params)
        rows = d.get(key, []) or []
        yield from rows
        cursor = d.get("cursor")
        if not cursor or not rows:
            return


def settled_events(series: str, max_pages: int = 200) -> List[Dict]:
    """All settled events of a series, live and historical. /events is not purged."""
    return list(_paginate("events", "events", max_pages, series_ticker=series, status="settled", limit=200))


def event_markets(event_ticker: str) -> List[Dict]:
    """Market rows of one event, from the live endpoint or the historical one."""
    rows = get("markets", event_ticker=event_ticker, limit=1000).get("markets", [])
    if rows and all(r.get("result") in ("yes", "no") for r in rows):
        return rows
    hist = get("historical/markets", _cache=True, event_ticker=event_ticker, limit=1000).get("markets", [])
    return hist or rows


def series_markets(series: str, historical: bool, max_pages: int = 500) -> Iterator[Dict]:
    path = "historical/markets" if historical else "markets"
    params = {"series_ticker": series, "limit": 1000}
    if not historical:
        params["status"] = "settled"
    return _paginate(path, "markets", max_pages, **params)


# ---------------------------------------------------------------- prices


def candles(
    market: Dict, interval: int = 60, start_ts: Optional[int] = None, end_ts: Optional[int] = None
) -> List[Dict]:
    """OHLC of yes_bid / yes_ask plus volume and OI. interval in minutes (1, 60, 1440)."""
    s = start_ts if start_ts is not None else ts(market["open_time"])
    e = end_ts if end_ts is not None else ts(market["close_time"])
    t = market["ticker"]
    if is_historical(market):
        path = "historical/markets/{}/candlesticks".format(t)
    else:
        series = market.get("series_ticker") or t.split("-")[0]
        path = "series/{}/markets/{}/candlesticks".format(series, t)
    settled = market.get("result") in ("yes", "no")
    return (
        get(path, _cache=settled, start_ts=s, end_ts=e, period_interval=interval).get("candlesticks", [])
        or []
    )


def _ohlc(c: Dict, side: str, field: str = "close") -> Optional[float]:
    d = c.get(side) or {}
    v = d.get(field + "_dollars", d.get(field))
    return to_float(v)


def candle_quote(c: Dict) -> Tuple[Optional[float], Optional[float]]:
    """(bid, ask) in dollars at the close of a candle, either schema."""
    return _ohlc(c, "yes_bid"), _ohlc(c, "yes_ask")


def candle_volume(c: Dict) -> float:
    return to_float(c.get("volume_fp", c.get("volume"))) or 0.0


def trades(market: Dict, max_pages: int = 50) -> List[Dict]:
    """Every print in a market, with `taker_side`. Cached once the market has settled."""
    path = "historical/trades" if is_historical(market) else "markets/trades"
    settled = market.get("result") in ("yes", "no")
    return list(_paginate(path, "trades", max_pages, _cache=settled, ticker=market["ticker"], limit=1000))


# ---------------------------------------------------------------- rows


def volume(row: Dict) -> float:
    return to_float(row.get("volume_fp", row.get("volume"))) or 0.0


def result_yes(row: Dict) -> Optional[int]:
    r = row.get("result")
    return 1 if r == "yes" else 0 if r == "no" else None
