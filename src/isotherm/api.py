"""The Jev-style typed interface: questions in, typed calibrated answers out.

Every answer is read off one `IntegerDistribution` over the outcome, so answers
to different questions about the same state are coherent by construction:
Choice probabilities sum to one, Noul probabilities are monotone in the
threshold, and the Score mean agrees with both. Questions are validated
against the type system before anything is computed; a malformed question is a
schema error, never a guess.

    dist = IntegerDistribution.gaussian(mu=81.2, sigma=2.4)
    answer(dist, [
        Choice(options=[Bucket(hi=79), Bucket(lo=80, hi=81), Bucket(lo=82)]),
        Noul(set=Bucket(lo=85)),
        Score(stat="quantiles", q=[0.1, 0.5, 0.9]),
    ])
"""

from __future__ import annotations

from typing import List, Literal, Optional, Union

import numpy as np
from pydantic import BaseModel, Field, model_validator
from scipy.stats import norm


class Bucket(BaseModel):
    """An inclusive integer range; open-ended when a bound is omitted."""

    lo: Optional[int] = None
    hi: Optional[int] = None
    label: Optional[str] = None

    @model_validator(mode="after")
    def _ordered(self):
        if self.lo is None and self.hi is None:
            raise ValueError("a bucket needs at least one bound")
        if self.lo is not None and self.hi is not None and self.lo > self.hi:
            raise ValueError("lo > hi")
        return self

    def contains(self, v: np.ndarray) -> np.ndarray:
        ok = np.ones_like(v, bool)
        if self.lo is not None:
            ok &= v >= self.lo
        if self.hi is not None:
            ok &= v <= self.hi
        return ok


class Choice(BaseModel):
    kind: Literal["choice"] = "choice"
    options: List[Bucket] = Field(min_length=2, max_length=255)

    @model_validator(mode="after")
    def _disjoint(self):
        grid = np.arange(-200, 300)
        hits = sum(b.contains(grid).astype(int) for b in self.options)
        if hits.max() > 1:
            raise ValueError("choice options overlap")
        return self


class Noul(BaseModel):
    kind: Literal["noul"] = "noul"
    set: Bucket


class Score(BaseModel):
    kind: Literal["score"] = "score"
    stat: Literal["mean", "quantiles", "interval"] = "mean"
    q: List[float] = Field(default_factory=lambda: [0.5])
    coverage: float = 0.8


Question = Union[Choice, Noul, Score]


class Answer(BaseModel):
    kind: str
    value: Union[int, float, bool, List[float], None]
    probabilities: Optional[List[float]] = None
    confidence: Optional[float] = None
    uncovered_mass: Optional[float] = None


class IntegerDistribution:
    """P(outcome = v) for integers v in [lo, lo + len(p))."""

    def __init__(self, lo: int, p: np.ndarray):
        p = np.clip(np.asarray(p, float), 0, None)
        self.lo, self.p = int(lo), p / p.sum()
        self.v = np.arange(self.lo, self.lo + len(self.p))

    @classmethod
    def gaussian(cls, mu: float, sigma: float, width: int = 40):
        lo = int(np.floor(mu)) - width
        v = np.arange(lo, lo + 2 * width + 2)
        return cls(lo, norm.cdf((v + 0.5 - mu) / sigma) - norm.cdf((v - 0.5 - mu) / sigma))

    def mass(self, b: Bucket) -> float:
        return float(self.p[b.contains(self.v)].sum())

    def mean(self) -> float:
        return float(self.p @ self.v)

    def quantile(self, q: float) -> int:
        return int(self.v[np.searchsorted(np.cumsum(self.p), q)])


def answer(dist: IntegerDistribution, questions: List[Question]) -> List[Answer]:
    out = []
    for q in questions:
        if isinstance(q, Choice):
            pr = np.array([dist.mass(b) for b in q.options])
            i = int(pr.argmax())
            out.append(
                Answer(
                    kind="choice",
                    value=i,
                    probabilities=pr.tolist(),
                    confidence=float(pr[i]),
                    uncovered_mass=max(0.0, float(1 - pr.sum())),  # no float noise below zero
                )
            )
        elif isinstance(q, Noul):
            p = dist.mass(q.set)
            out.append(Answer(kind="noul", value=p >= 0.5, probabilities=[p], confidence=max(p, 1 - p)))
        elif isinstance(q, Score):
            if q.stat == "mean":
                val = dist.mean()
            elif q.stat == "quantiles":
                val = [float(dist.quantile(x)) for x in q.q]
            else:
                a = (1 - q.coverage) / 2
                val = [float(dist.quantile(a)), float(dist.quantile(1 - a))]
            out.append(Answer(kind="score", value=val))
        else:
            raise TypeError("unsupported question type {!r}".format(type(q).__name__))
    return out
