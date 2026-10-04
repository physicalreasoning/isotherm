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
