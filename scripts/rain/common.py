"""Shared pieces for the rain study: paths, stations, CLI precipitation, MOS precipitation tables.

The event: NWS CLI daily precipitation strictly greater than zero, a trace ("T") counting as no.
That is also the event MOS probability of precipitation (PoP) forecasts: at least 0.01 inch.

The CLI day runs midnight to midnight local STANDARD time. A 6-hour MOS period [ftime-6h, ftime)
is assigned to the CLI day holding its midpoint, i.e. the day it overlaps by more than half;
12-hour periods likewise. Every US offset then gives exactly four 6-hour periods per day.
"""

from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from isotherm import iem  # noqa: E402
from isotherm.weather import AVAILABILITY_LAG  # noqa: E402

DATA = ROOT / "data" / "rain"
RESULTS = ROOT / "results" / "rain"
CORPUS = ROOT / "data" / "corpus_stations.json"
YEARS = range(2021, 2027)
CUT_2026 = "2026-10-06"  # 2026 MOS before this is a closed window, cached by iem
READS = {"d1_16": (-1, 16), "d0_08": (0, 8)}
MOS_COLS = ["runtime", "ftime", "p06", "p12", "q06", "q12"]


def corpus() -> dict:
    return json.loads(CORPUS.read_text())


def station_tz(st: str, info: dict | None = None) -> str:
    """Time zone from state and longitude (exact for every market station, checked by hand)."""
    v = (info or corpus())[st]
    if v.get("state") == "AZ":
        return "America/Phoenix"
    lon = v["lon"]
    if lon > -86.5:
        return "America/New_York"
    if lon > -101.5:
        return "America/Chicago"
    if lon > -114.5:
        return "America/Denver"
    return "America/Los_Angeles"


def std_offset_h(tz: str) -> int:
    return int(pd.Timestamp("2026-01-15", tz=tz).utcoffset().total_seconds() // 3600)


# ------------------------------------------------------------------ CLI precipitation


def _cli_rows(st: str, year: int, refresh: bool = False) -> list:
    url = "{}/json/cli.py?station={}&year={}".format(iem.BASE, st, year)
    if year < 2026:
        return json.loads(iem._cached(url, True), strict=False).get("results", [])
    f = DATA / "cli" / "{}_{}.json".format(st, year)
    if f.exists() and not refresh:
        return json.loads(f.read_text())
    rows = json.loads(iem._fetch(url), strict=False).get("results", [])
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps([{k: r.get(k) for k in ("valid", "precip", "product")} for r in rows]))
    return rows


def parse_precip(v):
    """CLI precip field -> (inches or NaN, is_trace)."""
    if v == "T":
        return 0.0, True
    try:
        x = float(v)
    except (TypeError, ValueError):
        return np.nan, False
    return (x, False) if x >= 0 else (np.nan, False)


def cli_precip(st: str, years=YEARS, refresh: bool = False) -> pd.DataFrame:
    out = []
    for y in years:
        for r in _cli_rows(st, y, refresh and y == 2026):
            p, tr = parse_precip(r.get("precip"))
            out.append({"day": r["valid"], "precip": p, "trace": tr})
    df = pd.DataFrame(out)
    if df.empty:
        return df
    df["day"] = pd.to_datetime(df["day"])
    df = df.drop_duplicates("day", keep="last").sort_values("day").reset_index(drop=True)
    df["wet"] = np.where(df["precip"].notna(), (df["precip"] > 0).astype(float), np.nan)
    return df


# ------------------------------------------------------------------ MOS precipitation


def mos_precip(st: str, model: str, live_end: str | None = None, cache_only: bool = False) -> pd.DataFrame:
    """PoP and amount columns of every run, 2021 onward, saved per station.

    `cache_only`: if 2026 was never fetched for this station, use the cached 2021-2025 years
    alone (no request) and save nothing.
    """
    f = DATA / "mos" / "{}_{}.parquet".format(st, model)
    if f.exists():
        df = pd.read_parquet(f)
        if live_end is None or df["runtime"].max() >= pd.Timestamp(live_end, tz="UTC") - pd.Timedelta(days=2):
            return df
    parts = []
    spans = [("{}-01-01".format(y), "{}-01-01".format(y + 1)) for y in range(2021, 2026)]
    if not cache_only:
        spans.append(("2026-01-01", CUT_2026))
    if live_end:
        spans.append((CUT_2026, live_end))
    for s, e in spans:
        d = iem.mos(st, model, s, e)
        if not d.empty:
            parts.append(d[[c for c in MOS_COLS if c in d.columns]])
    df = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=MOS_COLS)
    for c in ("p06", "p12", "q06", "q12"):
        df[c] = pd.to_numeric(df.get(c), errors="coerce")
    df = df.dropna(subset=["p06", "p12"], how="all").drop_duplicates(["runtime", "ftime"])
    if cache_only:
        return df
    f.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(f, index=False)
    return df


def period_table(mos: pd.DataFrame, off_h: int, lag: pd.Timedelta) -> pd.DataFrame:
    """Per (run, CLI day): PoP aggregates over the periods that day holds, with public time."""
    off = pd.Timedelta(hours=off_h)
    a = mos.dropna(subset=["p06"]).copy()
    a["target"] = (a["ftime"] - pd.Timedelta(hours=3) + off).dt.tz_localize(None).dt.normalize()
    a["p"] = a["p06"].clip(0, 100) / 100
    a["lq"] = np.log1p(-a["p"].clip(upper=0.999))
    g6 = a.groupby(["runtime", "target"]).agg(
        max06=("p", "max"), mean06=("p", "mean"), lq=("lq", "sum"), n06=("p", "size"), q06=("q06", "max")
    )
    g6["any06"] = 1 - np.exp(g6.pop("lq"))
    b = mos.dropna(subset=["p12"]).copy()
    b["target"] = (b["ftime"] - pd.Timedelta(hours=6) + off).dt.tz_localize(None).dt.normalize()
    b["p"] = b["p12"].clip(0, 100) / 100
    g12 = b.groupby(["runtime", "target"]).agg(max12=("p", "max"), q12=("q12", "max"))
    t = g6.join(g12, how="outer").reset_index()
    t["public"] = t["runtime"] + lag
    return t.sort_values("public")


def features_at(table: pd.DataFrame, queries: pd.DataFrame, prefix: str) -> pd.DataFrame:
    """Latest run public at each query's read time that covers its target day (point in time)."""
    q = queries[["target", "read_time"]].reset_index(drop=True).reset_index().sort_values("read_time")
    q["target"] = q["target"].astype(table["target"].dtype)
    out = pd.merge_asof(q, table, left_on="read_time", right_on="public", by="target", direction="backward")
    out["lead"] = (out["read_time"] - out["runtime"]).dt.total_seconds() / 3600
    cols = ["max06", "mean06", "any06", "n06", "q06", "max12", "q12", "lead"]
    out = out.set_index("index").sort_index()[cols]
    return out.add_prefix(prefix + "_")


def read_time_utc(days: pd.Series, tz: str, dd: int, hh: int) -> pd.Series:
    t = (pd.to_datetime(days) + pd.Timedelta(days=dd) + pd.Timedelta(hours=hh)).dt.tz_localize(
        tz, nonexistent="shift_forward", ambiguous=False
    )
    return t.dt.tz_convert("UTC")


def station_features(st: str, tz: str, days: pd.Series, cache_only: bool = False) -> pd.DataFrame:
    """NBM and GFS MOS PoP features for each day at both reads, long format (one row per day x read)."""
    off = std_offset_h(tz)
    tabs = {
        m: period_table(mos_precip(st, m, cache_only=cache_only), off, AVAILABILITY_LAG[m])
        for m in ("NBS", "GFS")
    }
    out = []
    for read, (dd, hh) in READS.items():
        q = pd.DataFrame({"target": pd.to_datetime(days).to_numpy()})
        q["read_time"] = read_time_utc(q["target"], tz, dd, hh)
        f = [features_at(tabs["NBS"], q, "nbm"), features_at(tabs["GFS"], q, "gfs")]
        out.append(pd.concat([q.assign(read=read)] + f, axis=1))
    return pd.concat(out, ignore_index=True)
