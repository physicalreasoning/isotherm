#!/usr/bin/env python3
"""Exploration (FINDINGS §36): do the twelve newer cities help once each has its own identity?

One split, every read: train on every ladder before July 2026 (the seven scored cities from 2022,
the twelve newer ones from their first listing in January or February 2026), test on
2026-07-01 to 2026-10-04. Each model is trained twice, on the seven cities alone and on all
nineteen with a city input for each, and scored on the seven and on the twelve separately.
These rows were all looked at before (§23 and the sealed tests), so this is exploration only.

    uv run scripts/explore_cities.py
"""

from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from isotherm import dataset, metrics  # noqa: E402
from isotherm.cities import Net19, Transformer19  # noqa: E402
from isotherm.model import IsothermNet, IsothermTransformer  # noqa: E402
from isotherm.splits import EMBARGO  # noqa: E402
from isotherm.weather import CITIES, NEW_CITIES  # noqa: E402

TEST_FROM, TEST_TO = pd.Timestamp("2026-07-01"), pd.Timestamp("2026-10-04")
SOURCES = ["market", "emos_gfs", "emos_nbm", "emos_nbm_obs", "climatology"]
CTL = "isotherm · 19 cities · market-sampled labels (control)"


def models():
    return {
        "mlp-7": (lambda: IsothermNet("isotherm"), False),
        "mlp-19": (lambda: Net19(), True),
        "tf-7": (lambda: IsothermTransformer("isotherm · transformer-L", d=128, layers=4, ff=256), False),
        "tf-19": (lambda: Transformer19(), True),
        "control-19": (lambda: Net19(CTL, market_labels=True, seeds=3), True),
    }


def split(ls):
    d = ls.meta["day"]
    tr = ls.take(np.flatnonzero((d < TEST_FROM - EMBARGO).to_numpy()))
    te = ls.take(np.flatnonzero(((d >= TEST_FROM) & (d <= TEST_TO)).to_numpy()))
    return tr, te


def paired(days, a, b):
    d = a - b
    return {"diff": float(d.mean()), "ci": metrics.date_bootstrap_mean(days, d, 2000), "n": len(d)}


def main():
    seen = dataset.load(list(CITIES)).complete(SOURCES)
    new = dataset.LadderSet.concat([dataset.build_city(k) for k in NEW_CITIES]).complete(SOURCES)
    s_tr, s_te = split(seen)
    n_tr, n_te = split(new)
    print(
        "train {} + {} ladders, test {} (seven) and {} (twelve)".format(
            len(s_tr), len(n_tr), len(s_te), len(n_te)
        ),
        flush=True,
    )
    res = {"from": str(TEST_FROM.date()), "to": str(TEST_TO.date()), "reads": {}}
    for read in sorted(seen.meta["read"].unique()):

        def pick(ls, r=read):
            return ls.take(np.flatnonzero((ls.meta["read"] == r).to_numpy()))

        tr7, tr19 = pick(s_tr), dataset.LadderSet.concat([pick(s_tr), pick(n_tr)])
        tests = {"seven": pick(s_te), "twelve": pick(n_te)}
        L = {g: {"market": metrics.log_score(t.probs["market"], t.y)} for g, t in tests.items()}
        for key, (make, all19) in models().items():
            m = make().fit(tr19 if all19 else tr7)
            for g, t in tests.items():
                L[g][key] = metrics.log_score(m.predict(t), t.y)
            print(read, key, "done", flush=True)
        r = {"train_new_ladders": len(pick(n_tr))}
        for g, t in tests.items():
            days, lg = t.meta["day"].to_numpy(), L[g]
            r[g] = {
                "ladders": len(t),
                "vs_market": {k: float((lg["market"] - v).mean()) for k, v in lg.items() if k != "market"},
                "mlp19_minus_mlp7": paired(days, lg["mlp-7"], lg["mlp-19"]),
                "tf19_minus_tf7": paired(days, lg["tf-7"], lg["tf-19"]),
                "tf19_minus_mlp19": paired(days, lg["mlp-19"], lg["tf-19"]),
            }
            print(
                "{} {:6s} mlp19-mlp7 {:+.4f} [{:+.4f}, {:+.4f}] tf19-tf7 {:+.4f} ctl {:+.4f}".format(
                    read,
                    g,
                    r[g]["mlp19_minus_mlp7"]["diff"],
                    *r[g]["mlp19_minus_mlp7"]["ci"],
                    r[g]["tf19_minus_tf7"]["diff"],
                    r[g]["vs_market"]["control-19"],
                ),
                flush=True,
            )
        res["reads"][read] = r
    pathlib.Path("results/explore_cities.json").write_text(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
