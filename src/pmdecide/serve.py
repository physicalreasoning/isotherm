"""HTTP service for the frozen model: typed questions in, calibrated typed answers out.

    uv run uvicorn pmdecide.serve:app --port 8000

    GET  /health                  model hash and what it was fit on
    GET  /ladder/{city}?day=      live ladder: market, forecast and model probability per bucket
    POST /decide                  {"city": "NY", "day": "2026-10-06", "questions": [...]}

The model is the frozen strategy from FINDINGS §9 (shadow/frozen.json), the one the lockbox
tested and the shadow record tracks. Questions use the typed API in `pmdecide.api`.

Bucket probabilities are turned into a distribution over integer highs by spreading each
bucket's mass over its integers in proportion to the forecast Gaussian, and the tails out to
±6 sigma. Every typed answer is read off that one distribution, so a Choice over the listed
buckets reproduces the model's bucket probabilities exactly, and any other question (a
threshold, a range, a quantile) stays coherent with them.
"""

from __future__ import annotations

import pathlib
from typing import List, Optional

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from scipy.stats import norm

from . import shadow
from .api import Answer, Choice, IntegerDistribution, Noul, Score, answer
from .weather import CITIES

FROZEN_PATH = pathlib.Path(__file__).resolve().parents[2] / "shadow" / "frozen.json"


def integer_distribution(p, intervals, mu: float, sigma: float) -> IntegerDistribution:
    """Spread bucket probabilities over integers using the forecast Gaussian as the within-bucket shape."""
    lo_all = int(np.floor(mu - 6 * sigma))
    hi_all = int(np.ceil(mu + 6 * sigma))
    for a, b in intervals:  # make sure every finite bucket edge is covered
        if np.isfinite(a):
            lo_all = min(lo_all, int(np.floor(a)))
        if np.isfinite(b):
            hi_all = max(hi_all, int(np.ceil(b)))
    v = np.arange(lo_all, hi_all + 1)
    w = norm.cdf((v + 0.5 - mu) / sigma) - norm.cdf((v - 0.5 - mu) / sigma)
    out = np.zeros(len(v))
    for pj, (a, b) in zip(p, intervals, strict=True):
        inside = (v + 0.5 > a) & (v - 0.5 < b)  # integer v settles in [a, b)
        if not inside.any():
            continue
        ww = np.maximum(w[inside], 1e-12)
        out[inside] += pj * ww / ww.sum()
    return IntegerDistribution(lo_all, out)


class DecideRequest(BaseModel):
    city: str
    day: Optional[str] = Field(None, description="target day YYYY-MM-DD; default tomorrow, local")
    questions: List[Choice | Noul | Score]


class DecideResponse(BaseModel):
    city: str
    day: str
    event: str
    model_hash: str
    answers: List[Answer]


app = FastAPI(title="pm-decide", version="0.1.0")


def _frozen() -> dict:
    return shadow.load_frozen(FROZEN_PATH)


def _predict(city: str, day: Optional[str]):
    if city not in CITIES:
        raise HTTPException(404, "unknown city {!r}; one of {}".format(city, sorted(CITIES)))
    now = pd.Timestamp.now(tz="UTC")
    if day is None:
        d, _ = shadow.due(CITIES[city], now)
    else:
        d = pd.Timestamp(day)
    out = shadow.predict_city(city, d, now, _frozen())
    if isinstance(out, str):
        raise HTTPException(409, "cannot score {} {}: {}".format(city, d.date(), out))
    return d, out


@app.get("/health")
def health():
    f = _frozen()
    return {
        "status": "ok",
        "model_hash": f["hash"],
        "fit_before": f["fit_before"],
        "model": f["strategy"]["model"],
        "cities": sorted(CITIES),
    }


@app.get("/ladder/{city}")
def ladder(city: str, day: Optional[str] = None):
    d, out = _predict(city, day)
    buckets = [
        {
            "ticker": r["ticker"],
            "lo": a,
            "hi": b,
            "bid": float(out["bid"][j]),
            "ask": float(out["ask"][j]),
            "p_market": float(out["p_market"][j]),
            "p_forecast": float(out["p_emos"][j]),
            "p_model": float(out["p_model"][j]),
        }
        for j, (r, (a, b)) in enumerate(zip(out["rows"], out["iv"], strict=True))
    ]
    for b in buckets:  # JSON has no infinity
        b["lo"] = None if not np.isfinite(b["lo"]) else b["lo"]
        b["hi"] = None if not np.isfinite(b["hi"]) else b["hi"]
    return {
        "city": city,
        "day": str(d.date()),
        "event": out["event"],
        "gfs_fcst": out["gfs_fcst"],
        "gfs_runtime": out["gfs_runtime"],
        "buckets": buckets,
    }


@app.post("/decide", response_model=DecideResponse)
def decide(req: DecideRequest):
    d, out = _predict(req.city, req.day)
    dist = integer_distribution(out["p_model"], out["iv"], out["mu"], out["sigma"])
    return DecideResponse(
        city=req.city,
        day=str(d.date()),
        event=out["event"],
        model_hash=_frozen()["hash"],
        answers=answer(dist, req.questions),
    )
