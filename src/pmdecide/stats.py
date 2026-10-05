"""Strategy statistics that survive scrutiny: Sharpe with honest CIs, DSR, PBO.

  sharpe            per-period mean / sd of daily PnL (zero-PnL days included)
  stationary boot   Politis & Romano (1994): resamples blocks of random length,
                    so day-to-day dependence (weather regimes) is preserved
  newey_west_t      t-stat of mean daily PnL with HAC variance
  deflated_sharpe   Bailey & López de Prado (2014): probability the true Sharpe
                    exceeds the best you would expect from N unskilled trials,
                    adjusted for skew and fat tails
  pbo_cscv          Bailey, Borwein, López de Prado & Zhu (2017): probability that
                    the configuration that looks best in-sample ranks below the
                    median out-of-sample, over all symmetric splits of the history
"""
from __future__ import annotations

from itertools import combinations
from typing import Dict

import numpy as np
from scipy.stats import kurtosis, norm, skew

EULER = 0.5772156649


def sharpe(x) -> float:
    x = np.asarray(x, float)
    s = x.std(ddof=1)
    return float(x.mean() / s) if s > 0 else 0.0


def annualise(sr_daily: float, periods: int = 365) -> float:
    return sr_daily * np.sqrt(periods)


def stationary_bootstrap(x, stat=sharpe, n: int = 2000, mean_block: float = 5.0, seed: int = 0):
    x = np.asarray(x, float)
    t = len(x)
    rng = np.random.default_rng(seed)
    p = 1.0 / mean_block
    out = np.empty(n)
    for b in range(n):
        idx = np.empty(t, int)
        idx[0] = rng.integers(t)
        jumps = rng.random(t) < p
        starts = rng.integers(0, t, t)
        for i in range(1, t):
            idx[i] = starts[i] if jumps[i] else (idx[i - 1] + 1) % t
        out[b] = stat(x[idx])
    return [float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))]


def newey_west_t(x, lags: int = 5) -> float:
    x = np.asarray(x, float)
    t = len(x)
    c = x - x.mean()
    v = c @ c / t
    for lag in range(1, lags + 1):
        v += 2 * (1 - lag / (lags + 1)) * (c[lag:] @ c[:-lag]) / t
    return float(x.mean() / np.sqrt(max(v, 1e-18) / t))


def expected_max_sharpe(n_trials: int, var_sr: float) -> float:
    """E[max SR] of n_trials unskilled strategies whose SRs have variance var_sr."""
    if n_trials <= 1:
        return 0.0
    return float(np.sqrt(var_sr) * ((1 - EULER) * norm.ppf(1 - 1 / n_trials)
                                    + EULER * norm.ppf(1 - 1 / (n_trials * np.e))))


def deflated_sharpe(x, n_trials: int, var_sr_trials: float) -> Dict[str, float]:
    """DSR for daily PnL x, given how many configurations were tried and their SR spread."""
    x = np.asarray(x, float)
    sr = sharpe(x)
    t = len(x)
    g3, g4 = float(skew(x)), float(kurtosis(x, fisher=False))
    sr0 = expected_max_sharpe(n_trials, var_sr_trials)
    den = np.sqrt(max(1 - g3 * sr + (g4 - 1) / 4 * sr ** 2, 1e-12))
    z = (sr - sr0) * np.sqrt(t - 1) / den
    return {"sr_daily": sr, "sr0_daily": sr0, "dsr": float(norm.cdf(z)), "skew": g3,
            "kurtosis": g4, "n_trials": int(n_trials), "t": int(t)}


def pbo_cscv(M: np.ndarray, s: int = 12) -> Dict[str, float]:
    """M: (T days, N configs) daily PnL. Returns PBO and the median OOS rank of the IS winner."""
    t, n = M.shape
    s = min(s, (t // 20) * 2) if t < 20 * s else s
    s -= s % 2
    blocks = np.array_split(np.arange(t), s)
    lam, degr = [], []
    for is_b in combinations(range(s), s // 2):
        is_idx = np.concatenate([blocks[i] for i in is_b])
        oos_idx = np.concatenate([blocks[i] for i in range(s) if i not in is_b])
        sr_is = np.array([sharpe(M[is_idx, j]) for j in range(n)])
        sr_oos = np.array([sharpe(M[oos_idx, j]) for j in range(n)])
        best = int(np.argmax(sr_is))
        rank = (sr_oos < sr_oos[best]).sum() + 0.5 * ((sr_oos == sr_oos[best]).sum() - 1) + 1
        w = rank / (n + 1)
        lam.append(np.log(w / (1 - w)))
        degr.append(sr_oos[best] - np.median(sr_oos))
    lam = np.array(lam)
    return {"pbo": float((lam <= 0).mean()), "splits": len(lam), "blocks": s,
            "median_logit": float(np.median(lam)),
            "oos_sr_best_minus_median": float(np.median(degr))}
