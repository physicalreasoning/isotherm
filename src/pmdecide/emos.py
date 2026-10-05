"""Gaussian forecast baselines fit by interval likelihood: EMOS and climatology.

    high ~ N(Xμ·β, exp(Xσ·γ))

  EMOS         Xμ = [1, fcst]                          (Gneiting et al. 2005)
  climatology  Xμ = [1, cos t, sin t, cos 2t, sin 2t]   no forecast at all
  both         Xσ = [1, cos t, sin t]                   seasonal spread

Highs are integers, so the likelihood of an observation is the mass of
[h-0.5, h+0.5), not a density. Seasonal spread matters: a 3°F miss is routine
in a Chicago spring and rare in a Miami summer. Both are deliberately tiny, so
they are hard-to-beat references rather than models in their own right.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import norm

from .weather import MOS_AVAILABILITY_LAG


def _season(doy, harmonics: int):
    t = 2 * np.pi * np.asarray(doy, float) / 365.25
    cols = [np.ones_like(t)]
    for k in range(1, harmonics + 1):
        cols += [np.cos(k * t), np.sin(k * t)]
    return np.stack(cols, 1)


@dataclass
class GaussianModel:
    kind: str  # "emos" | "climatology"
    beta: np.ndarray
    gamma: np.ndarray

    def design(self, fcst, doy):
        if self.kind == "emos":
            xm = np.stack([np.ones(len(np.atleast_1d(doy))), np.atleast_1d(fcst)], 1)
        else:
            xm = _season(np.atleast_1d(doy), 2)
        return xm, _season(np.atleast_1d(doy), 1)

    def params(self, fcst, doy):
        xm, xs = self.design(fcst, doy)
        return xm @ self.beta, np.exp(xs @ self.gamma)


def _fit(kind, xm, xs, high) -> GaussianModel:
    def nll(p):
        b, g = p[: xm.shape[1]], p[xm.shape[1] :]
        mu, s = xm @ b, np.exp(np.clip(xs @ g, -5, 5))  # sigma in [0.007, 148]°F
        pr = norm.cdf((high + 0.5 - mu) / s) - norm.cdf((high - 0.5 - mu) / s)
        return -np.log(np.clip(pr, 1e-12, None)).sum()

    b0 = np.zeros(xm.shape[1])
    if kind == "emos":
        b0[1] = 1.0
    else:
        b0[0] = float(np.mean(high))
    g0 = np.zeros(xs.shape[1])
    g0[0] = np.log(max(np.std(high) if kind != "emos" else 3.0, 1.0))
    r = minimize(nll, np.concatenate([b0, g0]), method="L-BFGS-B")
    return GaussianModel(kind, r.x[: xm.shape[1]], r.x[xm.shape[1] :])


def fit_emos(fcst, high, doy) -> GaussianModel:
    fcst, high, doy = (np.asarray(x, float) for x in (fcst, high, doy))
    ok = np.isfinite(fcst) & np.isfinite(high)
    m = GaussianModel("emos", None, None)
    xm, xs = m.design(fcst[ok], doy[ok])
    return _fit("emos", xm, xs, high[ok])


def fit_climatology(high, doy) -> GaussianModel:
    high, doy = np.asarray(high, float), np.asarray(doy, float)
    ok = np.isfinite(high)
    return _fit("climatology", _season(doy[ok], 2), _season(doy[ok], 1), high[ok])


def interval_probs(mu, sigma, lo, hi):
    """(n,) Gaussians integrated over (n, K) intervals; NaN bounds stay NaN."""
    mu, sigma = np.asarray(mu)[:, None], np.asarray(sigma)[:, None]
    return norm.cdf((hi - mu) / sigma) - norm.cdf((lo - mu) / sigma)


def daytime_max_table(
    mos: pd.DataFrame, value_col: str = "n_x", lag: pd.Timedelta = MOS_AVAILABILITY_LAG
) -> pd.DataFrame:
    """MOS rows that carry the daytime max for local day `target`, with public time."""
    m = mos[mos[value_col].notna() & (mos["ftime"].dt.hour == 0)].copy()
    m["target"] = (m["ftime"] - pd.Timedelta(days=1)).dt.tz_localize(None).dt.normalize()
    m["public"] = m["runtime"] + lag
    m = m.rename(columns={value_col: "fcst"})
    return m[["target", "runtime", "public", "fcst"]].sort_values("public")


def forecast_at(table: pd.DataFrame, queries: pd.DataFrame) -> pd.DataFrame:
    """For each (target day, read time) query, the latest forecast public at read time.

    queries: columns `target` (naive date) and `read_time` (UTC). Vectorised
    point-in-time join; equivalent to weather.mos_daytime_max per row (tested).
    """
    q = queries.sort_values("read_time").reset_index()
    q["target"] = q["target"].astype(table["target"].dtype)
    out = pd.merge_asof(q, table, left_on="read_time", right_on="public", by="target", direction="backward")
    lead = out["target"].dt.tz_localize("UTC") + pd.Timedelta(days=1) - out["runtime"]
    out["lead_h"] = lead.dt.total_seconds() / 3600
    return out.set_index("index").sort_index()[["fcst", "runtime", "lead_h"]]
