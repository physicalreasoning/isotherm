"""Daily-high temperature markets: city config, bucket arithmetic, point-in-time forecasts.

Kalshi settles to an integer degree F. A ladder is a set of mutually exclusive
buckets that partition the integers:

    strike_type  ticker   bounds             outcome set
    less         T80      cap=80             high <= 79
    between      B80.5    floor=80, cap=81   80 <= high <= 81
    greater      T87      floor=87           high >= 88

so a continuous predictive distribution F over the high maps to bucket
probabilities with a half-degree continuity correction (`bucket_interval`).
Answering every question from one distribution makes the answers coherent by
construction: bucket probabilities sum to one and threshold probabilities are
monotone in the strike, which a model with independent per-question heads does
not guarantee.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class City:
    key: str
    series: str
    station: str          # ICAO id for MOS and the IEM CLI archive
    tz: str


CITIES: Dict[str, City] = {c.key: c for c in [
    City("NY", "KXHIGHNY", "KNYC", "America/New_York"),
    City("CHI", "KXHIGHCHI", "KMDW", "America/Chicago"),
    City("MIA", "KXHIGHMIA", "KMIA", "America/New_York"),
    City("AUS", "KXHIGHAUS", "KAUS", "America/Chicago"),
    City("LAX", "KXHIGHLAX", "KLAX", "America/Los_Angeles"),
    City("DEN", "KXHIGHDEN", "KDEN", "America/Denver"),
    City("PHIL", "KXHIGHPHIL", "KPHL", "America/New_York"),
]}

# When a run is public, by model. GFS MOS hits the wire roughly 4h after its
# nominal runtime; NBM text bulletins run hourly and post about 1h after. One
# hour of margin on each: using a run before it was public is the classic
# forecast leak, and an over-long lag biases every test against the forecast.
AVAILABILITY_LAG = {"GFS": pd.Timedelta(hours=5), "NBS": pd.Timedelta(hours=2)}
MOS_AVAILABILITY_LAG = AVAILABILITY_LAG["GFS"]


def bucket_interval(strike_type: str, floor: Optional[float],
                    cap: Optional[float]) -> Tuple[float, float]:
    """Continuous interval [lo, hi) of the latent high that settles in this bucket."""
    if strike_type == "less":
        return -np.inf, float(cap) - 0.5
    if strike_type == "greater":
        return float(floor) + 0.5, np.inf
    if strike_type == "between":
        return float(floor) - 0.5, float(cap) + 0.5
    raise ValueError("unknown strike_type {!r}".format(strike_type))


_RULE_PATTERNS = [
    # (regex on rules_primary, strike_type, which groups are floor / cap)
    (re.compile(r"is between (\d+)\s*(?:-|and)\s*(\d+)"), "between"),
    (re.compile(r"is (?:strictly )?(?:greater than|above) (\d+)"), "greater"),
    (re.compile(r"is (?:strictly )?(?:less than|below) (\d+)"), "less"),
]


def normalise_strikes(df: pd.DataFrame) -> pd.DataFrame:
    """Fill strike_type / floor / cap from the rules text where Kalshi left them empty.

    Every 2021-22 market and a few weeks of early 2025 carry no strike fields;
    the bounds exist only in `rules_primary` ("is between 42-43°", "is greater
    than 44°", "is less than 38°"). Dropping them would bias the sample toward
    recent, more liquid markets. Parsed rows are verified downstream by the
    same label-arithmetic check as every other row (scripts/check_labels.py).
    Rows that match no pattern keep a NaN strike_type and are dropped there.
    """
    df = df.copy()
    miss = df["strike_type"].isna()
    for i in np.flatnonzero(miss.to_numpy()):
        rules = str(df["rules"].iat[i])
        for rx, st in _RULE_PATTERNS:
            m = rx.search(rules)
            if not m:
                continue
            df.iat[i, df.columns.get_loc("strike_type")] = st
            if st == "between":
                df.iat[i, df.columns.get_loc("floor")] = float(m.group(1))
                df.iat[i, df.columns.get_loc("cap")] = float(m.group(2))
            elif st == "greater":
                df.iat[i, df.columns.get_loc("floor")] = float(m.group(1))
            else:
                df.iat[i, df.columns.get_loc("cap")] = float(m.group(1))
            break
    df["strike_source"] = np.where(miss, "rules_text", "api")
    return df


def is_partition(intervals) -> bool:
    """True if sorted intervals tile the whole line: (-inf, a), [a, b), ..., [z, inf).

    Early (2021-22) events listed single thresholds or overlapping thresholds
    rather than ladders. Normalising those into a "distribution" would be
    meaningless, so they are excluded from every bucket-level score.
    """
    iv = sorted(intervals)
    if len(iv) < 2 or iv[0][0] != -np.inf or iv[-1][1] != np.inf:
        return False
    return all(a[1] == b[0] for a, b in zip(iv[:-1], iv[1:], strict=True))


def bucket_contains(strike_type: str, floor, cap, value: float) -> bool:
    lo, hi = bucket_interval(strike_type, floor, cap)
    return lo <= value < hi


def gaussian_bucket_probs(mu: float, sigma: float, intervals) -> np.ndarray:
    from scipy.stats import norm
    lo = np.array([a for a, _ in intervals], dtype=float)
    hi = np.array([b for _, b in intervals], dtype=float)
    return norm.cdf((hi - mu) / sigma) - norm.cdf((lo - mu) / sigma)


def mos_daytime_max(mos: pd.DataFrame, day: pd.Timestamp, known_at: pd.Timestamp,
                    max_lead_runs: int = 1) -> Optional[dict]:
    """The latest GFS MOS daytime-max forecast for local `day` that was public by `known_at`.

    MOS reports the 7am-7pm LST max at forecast hour 00Z of the following UTC
    day, which for every US station is the evening of local `day`. Returns the
    forecast value plus its run time and lead, or None if no public run covers it.
    """
    target = pd.Timestamp(day.date()) + pd.Timedelta(days=1)
    target = target.tz_localize("UTC")
    m = mos[(mos["ftime"] == target) & mos["n_x"].notna()]
    m = m[m["runtime"] + MOS_AVAILABILITY_LAG <= known_at]
    if m.empty:
        return None
    r = m.sort_values("runtime").iloc[-1]
    return {"fcst": float(r["n_x"]), "runtime": r["runtime"],
            "lead_h": (target - r["runtime"]).total_seconds() / 3600}
