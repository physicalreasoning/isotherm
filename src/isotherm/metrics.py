"""Proper scoring rules, calibration, and date-clustered inference.

Conventions: `p` is (n, K) bucket probabilities with zeros outside `mask`; `y`
is the index of the YES bucket; buckets are ordered by temperature. Lower is
better for every score here.

The unit of independence is the *date*, not the row: cities share weather
systems and the three read times of one city-day share an outcome. Every
interval in this module resamples dates.
"""

from __future__ import annotations

from typing import Dict, Sequence

import numpy as np

FLOOR = 1e-12


def log_score(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Negative log probability of the realised bucket (nats). Strictly proper."""
    return -np.log(np.clip(p[np.arange(len(y)), y], FLOOR, None))


def brier(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Multiclass Brier score."""
    oh = np.zeros_like(p)
    oh[np.arange(len(y)), y] = 1.0
    return ((p - oh) ** 2).sum(1)


def rps(p: np.ndarray, y: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Ranked probability score: Brier on the CDF, so near-misses cost less than far misses."""
    cp = np.cumsum(np.where(mask, p, 0.0), 1)
    oh = np.zeros_like(p)
    oh[np.arange(len(y)), y] = 1.0
    co = np.cumsum(oh, 1)
    k = mask.sum(1)
    return (((cp - co) ** 2) * mask).sum(1) / np.maximum(k - 1, 1)


def binary_pairs(p: np.ndarray, y: np.ndarray, mask: np.ndarray):
    """Flatten ladders into (prob, outcome) pairs, one per bucket: the Noul view."""
    oh = np.zeros_like(p)
    oh[np.arange(len(y)), y] = 1.0
    return p[mask], oh[mask]


def ece_debiased(prob: np.ndarray, out: np.ndarray, bins: int = 15) -> float:
    """Debiased squared-ECE, reported as its square root (Kumar et al. 2019).

    Plain binned ECE is biased upward at small n (the market survey showed its
    point estimate sitting below its own bootstrap interval). Subtracting each
    bin's sampling variance removes the leading-order bias.
    """
    edges = np.quantile(prob, np.linspace(0, 1, bins + 1))
    edges[0], edges[-1] = -np.inf, np.inf
    idx = np.clip(np.searchsorted(edges, prob, side="right") - 1, 0, bins - 1)
    tot = 0.0
    n = len(prob)
    for b in range(bins):
        s = idx == b
        nb = s.sum()
        if nb < 2:
            continue
        ybar, pbar = out[s].mean(), prob[s].mean()
        var = ybar * (1 - ybar) / (nb - 1)
        tot += (nb / n) * ((ybar - pbar) ** 2 - var)
    return float(np.sqrt(max(tot, 0.0)))


def reliability(prob: np.ndarray, out: np.ndarray, bins: int = 10) -> Dict[str, list]:
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(prob, edges) - 1, 0, bins - 1)
    r = {"bin_mid": [], "mean_prob": [], "freq": [], "n": []}
    for b in range(bins):
        s = idx == b
        if s.any():
            r["bin_mid"].append(float((edges[b] + edges[b + 1]) / 2))
            r["mean_prob"].append(float(prob[s].mean()))
            r["freq"].append(float(out[s].mean()))
            r["n"].append(int(s.sum()))
    return r


def date_bootstrap_mean(dates: Sequence, vals: np.ndarray, n: int = 1000, seed: int = 0):
    """95% CI of the row-mean of `vals`, resampling whole dates."""
    ud, inv = np.unique(np.asarray(dates), return_inverse=True)
    sums = np.bincount(inv, weights=vals, minlength=len(ud))
    cnt = np.bincount(inv, minlength=len(ud))
    rng = np.random.default_rng(seed)
    picks = rng.integers(0, len(ud), (n, len(ud)))
    stats = sums[picks].sum(1) / cnt[picks].sum(1)
    return [float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5))]


def diebold_mariano(dates: Sequence, loss_a: np.ndarray, loss_b: np.ndarray) -> Dict[str, float]:
    """DM test on per-date mean loss differences (a - b). Negative stat: a is better.

    Aggregating to dates first makes the test robust to within-date correlation;
    the variance uses a Newey-West correction at lag 1 for day-to-day persistence.
    """
    from scipy.stats import norm

    d = np.asarray(loss_a) - np.asarray(loss_b)
    ud, inv = np.unique(np.asarray(dates), return_inverse=True)
    dd = np.bincount(inv, weights=d) / np.bincount(inv)
    n = len(dd)
    if n < 10:
        return {"stat": float("nan"), "p": float("nan"), "n_dates": n}
    m = dd.mean()
    c = dd - m
    g0 = (c @ c) / n
    g1 = (c[1:] @ c[:-1]) / n
    var = (g0 + 2 * 0.5 * g1) / n
    stat = m / np.sqrt(max(var, 1e-18))
    return {"stat": float(stat), "p": float(2 * (1 - norm.cdf(abs(stat)))), "n_dates": n}
