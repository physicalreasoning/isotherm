"""A weather model across stations (FINDINGS §34): one network, about 600 NWS climate sites.

For each station-day it predicts the CLI high as a distribution over integers, from the NBM
and GFS MOS forecasts public at 16:00 local the day before (the same point-in-time join EMOS
uses), NBM's spread, season and a learned station embedding:

    p(high = round(NBM) + k),  k in [-20, 20]      softmax over 41 offsets

Kalshi buckets settle on integers, so a bucket's probability is the sum over the integers it
covers. Station time zones come from the city tables where known; elsewhere from longitude,
which only shifts which forecast run counts as public for training stations by up to an hour.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import torch
from torch import nn

from .dataset import DATA, LadderSet, _finish, local_read_utc
from .emos import daytime_max_table, forecast_at
from .weather import ALL_CITIES, AVAILABILITY_LAG

K = 20
READ = (-1, 16)
FEATS = ["nbm", "gfs", "diff", "log_xnd", "lead_nbm", "lead_gfs", "sin", "cos"]


def station_tz() -> dict:
    tz = {c.station: c.tz for c in ALL_CITIES.values()}
    try:
        from .pretrain import STATIONS

        tz = {**STATIONS, **tz}
    except ImportError:
        pass
    f = DATA / "corpus_stations.json"
    info = json.loads(f.read_text()) if f.exists() else {}
    for st, v in info.items():
        if st in tz:
            continue
        lon, state = v["lon"], v.get("state")
        if state == "AZ":
            tz[st] = "America/Phoenix"
        elif lon > -86.5:
            tz[st] = "America/New_York"
        elif lon > -101.5:
            tz[st] = "America/Chicago"
        elif lon > -114.5:
            tz[st] = "America/Denver"
        else:
            tz[st] = "America/Los_Angeles"
    return tz


def station_frame(st: str, tz: str, targets=None) -> pd.DataFrame:
    """One row per target day: forecasts public at 16:00 local the day before, and the CLI high.

    With `targets`, rows are exactly those days (for prediction): no label is needed and no row
    is dropped on its outcome.
    """
    fd = DATA / "forecasts"
    files = [fd / "{}_{}.parquet".format(st, m) for m in ("cli", "GFS", "NBS")]
    if not all(f.exists() for f in files):
        return pd.DataFrame()
    if targets is not None:
        cli = pd.DataFrame(
            {"target": pd.to_datetime(pd.Series(targets)).reset_index(drop=True), "high": np.nan}
        )
    else:
        cli = pd.read_parquet(files[0]).rename(columns={"valid": "target"}).dropna(subset=["high"])
        cli = cli[cli["target"] >= "2021-03-01"][["target", "high"]].reset_index(drop=True)
    if cli.empty:
        return pd.DataFrame()
    q = pd.DataFrame({"target": cli["target"], "read_time": local_read_utc(cli["target"], tz, *READ)})
    gfs = forecast_at(daytime_max_table(pd.read_parquet(files[1]), "n_x", AVAILABILITY_LAG["GFS"]), q)
    nbs = forecast_at(
        daytime_max_table(pd.read_parquet(files[2]), "txn", AVAILABILITY_LAG["NBS"], extra=("xnd",)), q
    )
    out = pd.DataFrame(
        {
            "station": st,
            "target": cli["target"],
            "high": cli["high"].astype(float),
            "nbm": nbs["fcst"].to_numpy(float),
            "xnd": nbs["xnd"].to_numpy(float),
            "lead_nbm": nbs["lead_h"].to_numpy(float),
            "gfs": gfs["fcst"].to_numpy(float),
            "lead_gfs": gfs["lead_h"].to_numpy(float),
        }
    )
    out = out.dropna(subset=["nbm", "gfs"])
    if targets is not None:
        return out.reset_index(drop=True)
    # CLI typos (a 448°F high exists): keep plausible highs near the forecast. Training rows only;
    # Kalshi ladders are labelled by Kalshi's own result.
    ok = out["high"].between(-60, 135) & ((out["high"] - out["nbm"]).abs() <= 30)
    return out[ok].reset_index(drop=True)


def corpus(stations=None) -> pd.DataFrame:
    tz = station_tz()
    sts = stations or sorted(p.name.split("_")[0] for p in (DATA / "forecasts").glob("*_NBS.parquet"))
    parts = [station_frame(st, tz[st]) for st in sts if st in tz]
    return pd.concat([p for p in parts if len(p)], ignore_index=True)


def _design(df: pd.DataFrame, fill_xnd: float):
    doy = df["target"].dt.dayofyear.to_numpy() / 365.25 * 2 * np.pi
    xnd = df["xnd"].fillna(fill_xnd).clip(lower=0.5)
    x = np.column_stack(
        [
            df["nbm"],
            df["gfs"],
            df["nbm"] - df["gfs"],
            np.log(xnd),
            df["lead_nbm"].fillna(24) / 24,
            df["lead_gfs"].fillna(24) / 24,
            np.sin(doy),
            np.cos(doy),
        ]
    ).astype(np.float32)
    return x, np.round(df["nbm"].to_numpy()).astype(int)


class _Net(nn.Module):
    def __init__(self, f, n_st, emb=8, hidden=128, dropout=0.1):
        super().__init__()
        self.emb = nn.Embedding(n_st + 1, emb)
        self.mlp = nn.Sequential(
            nn.Linear(f + emb, hidden),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden, hidden),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden, hidden),
            nn.GELU(),
            nn.Linear(hidden, 2 * K + 1),
        )

    def forward(self, x, s):
        return torch.log_softmax(self.mlp(torch.cat([x, self.emb(s)], -1)), -1)


class WxNet:
    def __init__(self, seeds=3, epochs=15, lr=2e-3, batch=8192, patience=3):
        self.seeds, self.epochs, self.lr, self.batch, self.patience = seeds, epochs, lr, batch, patience

    def fit(self, df: pd.DataFrame):
        self.stations = {s: i + 1 for i, s in enumerate(sorted(df["station"].unique()))}
        self.fill = float(df["xnd"].median())
        x, c = _design(df, self.fill)
        self.mu, self.sd = x.mean(0), x.std(0) + 1e-6
        x = (x - self.mu) / self.sd
        y = np.clip(df["high"].to_numpy() - c, -K, K).astype(np.int64) + K
        s = df["station"].map(self.stations).to_numpy()
        cut = df["target"].quantile(0.9)
        tr, va = np.flatnonzero(df["target"] < cut), np.flatnonzero(df["target"] >= cut)
        X, Y, S = torch.from_numpy(np.ascontiguousarray(x)), torch.from_numpy(y), torch.from_numpy(s.copy())
        self.nets = []
        for seed in range(self.seeds):
            torch.manual_seed(seed)
            rng = np.random.default_rng(seed)
            net = _Net(x.shape[1], len(self.stations))
            opt = torch.optim.AdamW(net.parameters(), lr=self.lr, weight_decay=1e-4)
            best, state, bad = np.inf, None, 0
            for _ in range(self.epochs):
                net.train()
                for b in np.array_split(rng.permutation(tr), max(1, len(tr) // self.batch)):
                    opt.zero_grad()
                    loss = -net(X[b], S[b]).gather(1, Y[b, None]).mean()
                    loss.backward()
                    opt.step()
                net.eval()
                with torch.no_grad():
                    v = float(-net(X[va], S[va]).gather(1, Y[va, None]).mean())
                if v < best - 1e-4:
                    best, state, bad = v, {k: t.clone() for k, t in net.state_dict().items()}, 0
                else:
                    bad += 1
                    if bad >= self.patience:
                        break
            net.load_state_dict(state)
            net.eval()
            self.nets.append(net)
        self.val_nll = best
        return self

    def predict(self, df: pd.DataFrame):
        """(centre, p): p[i, k] = P(high = centre[i] + k - K)."""
        x, c = _design(df, self.fill)
        x = torch.from_numpy(np.ascontiguousarray((x - self.mu) / self.sd, dtype=np.float32))
        s = torch.from_numpy(df["station"].map(self.stations).fillna(0).astype(np.int64).to_numpy().copy())
        with torch.no_grad():
            p = torch.stack([n(x, s).exp() for n in self.nets]).mean(0).numpy()
        return c, p


def ladder_rows(ls: LadderSet) -> pd.DataFrame:
    """Prediction rows (no labels) for every ladder day of the cities in `ls`."""
    tz = station_tz()
    parts = []
    for k in ls.meta["city"].unique():
        st = ALL_CITIES[k].station
        days = ls.meta.loc[ls.meta["city"] == k, "day"].unique()
        parts.append(station_frame(st, tz[st], targets=days))
    return pd.concat(parts, ignore_index=True)


def expanding_preds(df: pd.DataFrame, rows: pd.DataFrame, start, end, embargo) -> pd.DataFrame:
    """Predict each quarter of `rows` from start to end with a model fit on every corpus row before it."""
    qs = pd.date_range(start, end, freq="QS")
    out = []
    for a, b in zip(qs[:-1], qs[1:], strict=True):
        te = rows[(rows["target"] >= a) & (rows["target"] < b)]
        if te.empty:
            continue
        c, p = WxNet().fit(df[df["target"] < a - embargo]).predict(te)
        out.append(te.assign(centre=c, p=list(p)))
    return pd.concat(out, ignore_index=True)


def bucket_probs(centre: np.ndarray, p: np.ndarray, lo: np.ndarray, hi: np.ndarray, mask: np.ndarray):
    """Sum integer probabilities over each bucket's settlement interval (lo, hi)."""
    v = centre[:, None] + np.arange(-K, K + 1)[None, :]  # (n, 2K+1)
    lo_ = np.where(np.isfinite(lo), lo, -np.inf)[:, :, None]
    hi_ = np.where(np.isfinite(hi), hi, np.inf)[:, :, None]
    inside = (v[:, None, :] > lo_) & (v[:, None, :] < hi_)  # (n, buckets, 2K+1)
    out = (inside * p[:, None, :]).sum(-1)
    return _finish(np.where(mask, out, np.nan), mask)


def as_inputs(ls: LadderSet, name: str = "wx_net") -> LadderSet:
    """Rows with a weather-model forecast, which stands in for EMOS-NBM in the MLP's inputs (§34)."""
    alt = ls.take(np.flatnonzero(np.isfinite(ls.probs[name]).all(1)))
    alt.probs["emos_nbm"] = alt.probs[name].copy()
    alt.probs["emos_nbm_obs"] = alt.probs[name].copy()  # no observations the day before
    alt.meta["mu_nbs"], alt.meta["sigma_nbs"] = alt.meta["mu_" + name], alt.meta["sigma_" + name]
    return alt


def attach(ls: LadderSet, preds: pd.DataFrame, name: str = "wx_net") -> None:
    """Map station-day predictions (columns station, target, centre, p) onto ladder rows."""
    st = ls.meta["city"].map({k: c.station for k, c in ALL_CITIES.items()})
    key = st + "|" + ls.meta["day"].dt.strftime("%Y-%m-%d")
    pk = preds["station"] + "|" + preds["target"].dt.strftime("%Y-%m-%d")
    idx = pd.Series(np.arange(len(preds)), index=pk.to_numpy())
    hit = key.isin(idx.index).to_numpy()
    n, kk = ls.mask.shape
    out = np.full((n, kk), np.nan)
    mu, sd = np.full(n, np.nan), np.full(n, np.nan)
    if hit.any():
        j = idx[key[hit]].to_numpy()
        P, c = np.stack(preds["p"].to_numpy())[j], preds["centre"].to_numpy()[j]
        out[hit] = bucket_probs(c, P, ls.lo[hit], ls.hi[hit], ls.mask[hit])
        mu[hit], sd[hit] = moments(c, P)
    ls.probs[name] = out
    ls.meta["mu_" + name], ls.meta["sigma_" + name] = mu, sd


def moments(centre: np.ndarray, p: np.ndarray):
    """Mean and standard deviation of the integer distribution, for the MLP's Gaussian-based inputs."""
    v = centre[:, None] + np.arange(-K, K + 1)[None, :]
    mu = (p * v).sum(1)
    return mu, np.sqrt(np.maximum((p * (v - mu[:, None]) ** 2).sum(1), 0.25))
