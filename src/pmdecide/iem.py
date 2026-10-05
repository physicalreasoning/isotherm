"""Iowa Environmental Mesonet: archived NWS forecasts and climate reports, free.

Two products matter:

  MOS   Model Output Statistics: the NWS's own statistically post-processed
        station forecasts. GFS MOS (MAV) carries `n_x`, the daytime max /
        nighttime min, for every run back well before Kalshi existed, which is
        what makes leak-free calibration possible: fit on years the market
        never traded, evaluate on years it did.
  CLI   the NWS Daily Climatological Report, Kalshi's settlement source for
        daily-high markets until it switched to The Weather Company between
        2026-08-03 and 2026-10-03 (see docs/02-data.md).

IEM returns HTTP 429 with a plain-text body when hit faster than roughly one
request every couple of seconds, so this client is much slower than the Kalshi
one, and caches every response that covers a closed time window.
"""

from __future__ import annotations

import gzip
import hashlib
import http.client
import io
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import pandas as pd

from .kalshi import CACHE as _KCACHE

BASE = "https://mesonet.agron.iastate.edu"
MIN_INTERVAL = 2.5
CACHE = _KCACHE.parent / "iem"

_lock = threading.Lock()
_last = [0.0]


def _fetch(url: str, retries: int = 8) -> bytes:
    delay = 15.0
    for attempt in range(retries):
        with _lock:
            dt = time.time() - _last[0]
            if dt < MIN_INTERVAL:
                time.sleep(MIN_INTERVAL - dt)
            _last[0] = time.time()
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(delay)
                delay = min(delay * 2, 300)
                continue
            raise
        except (urllib.error.URLError, TimeoutError, http.client.IncompleteRead, ConnectionError):
            if attempt < retries - 1:
                time.sleep(delay)
                continue
            raise
    raise RuntimeError("unreachable")


def _cached(url: str, cache: bool) -> bytes:
    if not cache:
        return _fetch(url)
    h = hashlib.sha256(url.encode()).hexdigest()
    f = CACHE / h[:2] / (h[:24] + ".gz")
    if f.exists():
        return gzip.decompress(f.read_bytes())
    body = _fetch(url)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp{}".format(threading.get_ident()))
    tmp.write_bytes(gzip.compress(body))
    tmp.replace(f)
    return body


def mos(station: str, model: str, start: str, end: str) -> pd.DataFrame:
    """All MOS runs for a station in [start, end), as a DataFrame (UTC times).

    model: GFS (MAV, back to 2000s), NBS (NBM short-range), NBE (NBM extended).
    """
    q = urllib.parse.urlencode(
        {
            "station": station,
            "model": model,
            "sts": start + "T00:00Z",
            "ets": end + "T00:00Z",
            "format": "csv",
        }
    )
    closed = pd.Timestamp(end, tz="UTC") < pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=2)
    body = _cached("{}/cgi-bin/request/mos.py?{}".format(BASE, q), cache=closed)
    if not body.strip():
        return pd.DataFrame()
    df = pd.read_csv(io.BytesIO(body), low_memory=False)
    for c in ("runtime", "ftime"):
        df[c] = pd.to_datetime(df[c], utc=True)
    return df


def cli(station: str, year: int) -> pd.DataFrame:
    """NWS Daily Climatological Report highs/lows for one station-year.

    `station` is the ICAO id IEM files the CLI under (KNYC for Central Park,
    KMDW for Chicago Midway, ...). Values are integer degrees F.
    """
    url = "{}/json/cli.py?station={}&year={}".format(BASE, station, year)
    closed = year < pd.Timestamp.now(tz="UTC").year
    body = _cached(url, cache=closed)
    rows = json.loads(body, strict=False).get("results", [])
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["valid"] = pd.to_datetime(df["valid"])
    for c in ("high", "low"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df[["station", "valid", "high", "low", "product"]]


def asos(station3: str, year: int) -> pd.DataFrame:
    """Hourly + special METAR temperatures for one station-year, UTC.

    `station3` is the 3-letter id IEM's ASOS archive uses (NYC for Central Park).
    Routine hourly obs land at :51; specials whenever weather changes. tmpf is
    derived from the tenths-of-°C remark when present, so it is not pre-rounded.
    """
    q = urllib.parse.urlencode(
        [
            ("station", station3),
            ("data", "tmpf"),
            ("year1", year),
            ("month1", 1),
            ("day1", 1),
            ("year2", year + 1),
            ("month2", 1),
            ("day2", 1),
            ("tz", "Etc/UTC"),
            ("format", "onlycomma"),
            ("latlon", "no"),
            ("missing", "M"),
            ("trace", "T"),
            ("direct", "no"),
            ("report_type", 3),
            ("report_type", 4),
        ]
    )
    closed = year < pd.Timestamp.now(tz="UTC").year
    body = _cached("{}/cgi-bin/request/asos.py?{}".format(BASE, q), cache=closed)
    df = pd.read_csv(io.BytesIO(body), na_values=["M"])
    if df.empty:
        return df
    df["valid"] = pd.to_datetime(df["valid"], utc=True)
    df["tmpf"] = pd.to_numeric(df["tmpf"], errors="coerce")
    return df.dropna(subset=["tmpf"])[["station", "valid", "tmpf"]]
