"""LadderNet: the typed decision model. One distribution per ladder, learned from outcomes.

    score_j = Σ_s w_s · log p_s,j  +  MLP([x_j ; c])          p = softmax_j(score)

  log p_s,j   every causal forecast source for bucket j (market, EMOS-GFS, EMOS-NBM,
              EMOS-NBM conditioned on today's observed max, climatology)
  x_j         bucket features: position against each forecast (z-scores), whether
              today's observed max already rules the bucket out, quoted spread, tails
  c           context: city, season, lead time, forecast disagreement and spread,
              observations so far, ladder overround and traded volume before the read

The pool weights start at "market only" and the MLP's output layer starts at zero,
so an untrained LadderNet *is* the market: training can only move it away from the
crowd where outcomes justify it. Loss is the log score (the proper scoring rule that
Jev's RLCD amounts to for a discriminative head), with sample weights that halve
every `half_life_days`, so the model tracks a market whose biases decay. Early
stopping holds out the most recent 15% of training dates. Probabilities from
`seeds` independently initialised nets are averaged.

Implements the Predictor protocol, so the benchmark and backtest treat it exactly
like the baselines.
"""

from __future__ import annotations

import numpy as np
import torch
from torch import nn

from .dataset import LadderSet
from .weather import CITIES

SOURCES = ["market", "emos_gfs", "emos_nbm", "emos_nbm_obs", "climatology"]
CITY_KEYS = list(CITIES)


def _centre(lo, hi):
    lo_f = np.where(np.isfinite(lo), lo, hi - 2.0)
    hi_f = np.where(np.isfinite(hi), hi, lo + 2.0)
    return (lo_f + hi_f) / 2


def features(ls: LadderSet):
    """(x: n×K×F bucket features, c: n×C context, logp: n×K×S source log-probs)."""
    m = ls.meta
    n, k = ls.mask.shape
    logp = np.stack([np.log(np.clip(np.nan_to_num(ls.probs[s], nan=0.0), 1e-4, 1)) for s in SOURCES], -1)
    cen = _centre(ls.lo, ls.hi)

    def col(name, fill=0.0):
        return np.nan_to_num(m[name].to_numpy(float), nan=fill) if name in m else np.full(n, fill)

    mu_n, sg_n = col("mu_nbs", np.nan), col("sigma_nbs", 3.0)
    mu_g, sg_g = col("mu_gfs", np.nan), col("sigma_gfs", 3.0)
    mu_n = np.where(np.isfinite(mu_n), mu_n, np.nanmean(cen, 1))
    mu_g = np.where(np.isfinite(mu_g), mu_g, mu_n)
    obs = col("obs_best", np.nan) if "obs_best" in m else col("obs_max", np.nan)
    rest = m["nbm_rest_max"].to_numpy(float) if "nbm_rest_max" in m else np.full(n, np.nan)
    has_rest = np.isfinite(rest)
    rest0 = np.where(has_rest, rest, 0.0)
    has_obs = np.isfinite(obs)
    obs0 = np.where(has_obs, obs, 0.0)
    bid, ask = ls.quotes["bid"], ls.quotes["ask"]
    x = np.stack(
        [
            (cen - mu_n[:, None]) / np.maximum(sg_n, 0.5)[:, None],
            (cen - mu_g[:, None]) / np.maximum(sg_g, 0.5)[:, None],
            np.where(has_obs[:, None], (ls.hi <= np.round(obs0)[:, None] - 1.5), 0.0),
            np.where(has_obs[:, None], np.clip((cen - obs0[:, None]) / 5, -3, 3), 0.0),
            ask - bid,
            (bid + ask) / 2,
            (~np.isfinite(ls.lo)).astype(float),
            (~np.isfinite(ls.hi)).astype(float),
            np.where(has_rest[:, None], np.clip((cen - rest0[:, None]) / 5, -3, 3), 0.0),
        ],
        -1,
    )
    x = np.where(ls.mask[..., None], x, 0.0)
    doy = m["day"].dt.dayofyear.to_numpy() / 365.25 * 2 * np.pi
    city = np.stack([(m["city"] == c).to_numpy(float) for c in CITY_KEYS], -1)
    c = np.column_stack(
        [
            city,
            np.sin(doy),
            np.cos(doy),
            np.clip((mu_n - mu_g) / 5, -3, 3),
            sg_n / 5,
            sg_g / 5,
            col("lead_h_gfs", 24.0) / 48,
            col("overround", 1.0) - 1,
            has_obs.astype(float),
            col("obs_n") / 24,
            np.where(has_obs, np.clip((col("obs_last") - obs0) / 5, -3, 3), 0.0),
            np.log1p(col("cum_volume")) / 10,
            has_rest.astype(float),
            np.where(has_rest & has_obs, np.clip((rest0 - obs0) / 5, -3, 3), 0.0),
        ]
    )
    return x.astype(np.float32), c.astype(np.float32), logp.astype(np.float32)


class _Net(nn.Module):
    def __init__(self, f, cdim, s, hidden=64, dropout=0.1):
        super().__init__()
        self.pool = nn.Parameter(torch.tensor([1.0] + [0.0] * (s - 1)))
        self.mlp = nn.Sequential(
            nn.Linear(f + cdim + s, hidden),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden, hidden),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden, 1),
        )
        nn.init.zeros_(self.mlp[-1].weight)
        nn.init.zeros_(self.mlp[-1].bias)

    def forward(self, x, c, logp, mask):
        k = x.shape[1]
        h = torch.cat([x, c[:, None, :].expand(-1, k, -1), logp], -1)
        score = (logp * self.pool).sum(-1) + self.mlp(h).squeeze(-1)
        return torch.log_softmax(score.masked_fill(~mask, -1e9), -1)


class LadderNet:
    def __init__(
        self,
        name="LadderNet",
        half_life_days=365.0,
        seeds=5,
        hidden=64,
        epochs=300,
        lr=3e-3,
        weight_decay=1e-3,
        patience=15,
        market_labels=False,
    ):
        self.name = name
        self.half_life, self.seeds, self.hidden = half_life_days, seeds, hidden
        self.epochs, self.lr, self.wd, self.patience = epochs, lr, weight_decay, patience
        # Control: train on labels drawn from the market's own distribution. The best
        # possible fit to those is the market itself, so this model must score like the
        # market on real outcomes; a gain here would mean the pipeline leaks the outcome.
        self.market_labels = market_labels
        self.nets, self.stats = [], None

    def _prep(self, ls):
        x, c, logp = features(ls)
        if self.stats is None:
            msk = ls.mask
            xm = x[msk].mean(0)
            xs = x[msk].std(0) + 1e-6
            self.stats = (xm, xs, c.mean(0), c.std(0) + 1e-6)
        xm, xs, cm, cs = self.stats
        x = np.where(ls.mask[..., None], (x - xm) / xs, 0.0).astype(np.float32)
        c = ((c - cm) / cs).astype(np.float32)
        return (torch.from_numpy(x), torch.from_numpy(c), torch.from_numpy(logp), torch.from_numpy(ls.mask))

    def fit(self, train: LadderSet):
        self.stats, self.nets = None, []
        if len(train) < 200:
            return self
        days = train.meta["day"].to_numpy("datetime64[D]").astype(float)
        age = days.max() - days
        w = np.power(0.5, age / self.half_life).astype(np.float32)
        cut = np.quantile(days, 0.85)
        tr, va = days < cut, days >= cut
        x, c, lp, mk = self._prep(train)
        y = torch.from_numpy(train.y.astype(np.int64))
        wt = torch.from_numpy(w)
        for seed in range(self.seeds):
            torch.manual_seed(seed)
            yy = y.clone()
            if self.market_labels:
                rng = np.random.default_rng(1000 + seed)
                pm = np.where(train.mask, train.probs["market"], 0.0)
                cum = np.cumsum(pm / pm.sum(1, keepdims=True), 1)
                yy = torch.from_numpy(
                    (cum < rng.random((len(cum), 1))).sum(1).clip(0, train.mask.sum(1) - 1).astype(np.int64)
                )
            net = _Net(x.shape[-1], c.shape[-1], lp.shape[-1], self.hidden)
            opt = torch.optim.AdamW(net.parameters(), lr=self.lr, weight_decay=self.wd)
            best, best_state, bad = np.inf, None, 0
            itr, iva = torch.from_numpy(np.flatnonzero(tr)), torch.from_numpy(np.flatnonzero(va))
            for _ in range(self.epochs):
                net.train()
                opt.zero_grad()
                out = net(x[itr], c[itr], lp[itr], mk[itr])
                nll = -out.gather(1, yy[itr, None]).squeeze(1)
                loss = (nll * wt[itr]).sum() / wt[itr].sum()
                loss.backward()
                opt.step()
                net.eval()
                with torch.no_grad():
                    o = net(x[iva], c[iva], lp[iva], mk[iva])
                    v = float((-o.gather(1, yy[iva, None]).squeeze(1) * wt[iva]).sum() / wt[iva].sum())
                if v < best - 1e-5:
                    best, bad = v, 0
                    best_state = {k_: t.clone() for k_, t in net.state_dict().items()}
                else:
                    bad += 1
                    if bad >= self.patience:
                        break
            net.load_state_dict(best_state)
            net.eval()
            self.nets.append(net)
        return self

    def predict(self, test: LadderSet) -> np.ndarray:
        if not self.nets:
            return test.probs["market"].copy()
        x, c, lp, mk = self._prep(test)
        with torch.no_grad():
            p = torch.stack([net(x, c, lp, mk).exp() for net in self.nets]).mean(0).numpy()
        return np.where(test.mask, p, 0.0)
