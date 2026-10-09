"""HTTP service for the frozen model: typed questions in, calibrated typed answers out.

    uv run uvicorn isotherm.serve:app --port 8000      # REST only
    uv run uvicorn isotherm.app:app --port 8000        # REST and MCP (/mcp), as deployed

    GET  /health                  model hash and what it was fit on
    GET  /ladder/{city}?day=      live ladder: market, forecast and model probability per bucket
    POST /decide                  {"city": "NY", "day": "2026-10-06", "questions": [...]}

The model is the frozen strategy from FINDINGS §9 (shadow/frozen.json), the one the lockbox
tested and the shadow record tracks. Questions use the typed API in `isotherm.api`.

Bucket probabilities are turned into a distribution over integer highs by spreading each
bucket's mass over its integers in proportion to the forecast Gaussian, and the tails out to
±6 sigma. Every typed answer is read off that one distribution, so a Choice over the listed
buckets reproduces the model's bucket probabilities exactly, and any other question (a
threshold, a range, a quantile) stays coherent with them.

Every /decide answer is appended to a JSON-lines log with the integer distribution it was read
from (`ISOTHERM_ANSWER_LOG`, default data/served/answers.jsonl; empty to disable), so served
answers can be scored against outcomes later the way FINDINGS §38 scores the backtest.
"""

from __future__ import annotations

import json
import os
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

ROOT = pathlib.Path(__file__).resolve().parents[2]
FROZEN_PATH = pathlib.Path(os.environ.get("ISOTHERM_FROZEN", ROOT / "shadow" / "frozen.json"))


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
    disagreement: float = Field(
        description="KL divergence of the model's ladder from the market's, nats. The best single "
        "indicator that an answer carries information beyond the price (FINDINGS §46); near 0, "
        "the model is repeating the market."
    )


app = FastAPI(
    title="isotherm",
    version="0.1.0",
    description=(
        "Calibrated, typed answers for Kalshi's daily high-temperature markets in seven US cities. "
        "Every answer for a city-day is read off one distribution, so answers never contradict each "
        "other. The same tools are available to agents over MCP (streamable HTTP) at `/mcp`. "
        "Reference: https://github.com/physicalreasoning/isotherm/blob/main/docs/API.md"
    ),
)


def _frozen() -> dict:
    return shadow.load_frozen(FROZEN_PATH)


class NotServable(Exception):
    """No ladder, quotes or forecast for that city-day yet."""


def _predict(city: str, day: Optional[str]):
    if city not in CITIES:
        raise KeyError("unknown city {!r}; one of {}".format(city, sorted(CITIES)))
    now = pd.Timestamp.now(tz="UTC")
    if day is None:
        d, _ = shadow.due(CITIES[city], now)
    else:
        d = pd.Timestamp(day)
    out = shadow.predict_city(city, d, now, _frozen())
    if isinstance(out, str):
        raise NotServable("cannot score {} {}: {}".format(city, d.date(), out))
    return d, out


def health_payload() -> dict:
    f = _frozen()
    return {
        "status": "ok",
        "model_hash": f["hash"],
        "fit_before": f["fit_before"],
        "model": f["strategy"]["model"],
        "cities": sorted(CITIES),
    }


def disagreement(out: dict) -> float:
    """KL(model || market) over the ladder's buckets, nats."""
    p, q = np.clip(out["p_model"], 1e-9, 1), np.clip(out["p_market"], 1e-9, 1)
    return round(float(np.sum(p * (np.log(p) - np.log(q)))), 5)


def ladder_payload(city: str, day: Optional[str] = None) -> dict:
    d, out = _predict(city, day)
    buckets = []
    for j, (r, (a, b)) in enumerate(zip(out["rows"], out["iv"], strict=True)):
        buckets.append(
            {
                "ticker": r["ticker"],
                "lo": float(a) if np.isfinite(a) else None,  # JSON has no infinity
                "hi": float(b) if np.isfinite(b) else None,
                "bid": float(out["bid"][j]),
                "ask": float(out["ask"][j]),
                "p_market": float(out["p_market"][j]),
                "p_forecast": float(out["p_emos"][j]),
                "p_model": float(out["p_model"][j]),
            }
        )
    return {
        "city": city,
        "day": str(d.date()),
        "event": out["event"],
        "gfs_fcst": out["gfs_fcst"],
        "gfs_runtime": out["gfs_runtime"],
        "disagreement": disagreement(out),
        "buckets": buckets,
    }


def _log(record: dict) -> None:
    path = os.environ.get("ISOTHERM_ANSWER_LOG", str(ROOT / "data" / "served" / "answers.jsonl"))
    if not path:
        return
    try:
        p = pathlib.Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a") as f:
            f.write(json.dumps(record) + "\n")
    except OSError:
        pass  # logging must never break an answer


def decide_payload(city: str, questions: List[Choice | Noul | Score], day: Optional[str] = None, via="http"):
    d, out = _predict(city, day)
    dist = integer_distribution(out["p_model"], out["iv"], out["mu"], out["sigma"])
    model_hash = _frozen()["hash"]
    answers = answer(dist, questions)
    _log(
        {
            "served_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "via": via,
            "city": city,
            "day": str(d.date()),
            "event": out["event"],
            "model_hash": model_hash,
            "questions": [q.model_dump() for q in questions],
            "answers": [a.model_dump() for a in answers],
            "dist": {"lo": dist.lo, "p": [round(float(x), 6) for x in dist.p]},
            "disagreement": disagreement(out),
        }
    )
    return DecideResponse(
        city=city,
        day=str(d.date()),
        event=out["event"],
        model_hash=model_hash,
        answers=answers,
        disagreement=disagreement(out),
    )


def _http(fn, *a):
    try:
        return fn(*a)
    except KeyError as e:
        raise HTTPException(404, str(e.args[0])) from None
    except NotServable as e:
        raise HTTPException(409, str(e)) from None


@app.get("/health")
def health():
    return health_payload()


@app.get("/ladder/{city}")
def ladder(city: str, day: Optional[str] = None):
    return _http(ladder_payload, city, day)


@app.post("/decide", response_model=DecideResponse)
def decide(req: DecideRequest):
    return _http(decide_payload, req.city, req.questions, req.day)
