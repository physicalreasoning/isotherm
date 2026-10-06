#!/usr/bin/env python3
"""Unseen cities: score models frozen on the seven cities on twelve they never saw (FINDINGS §23).

Run once; the criteria were pushed before this script ever ran.

    uv run scripts/unseen_cities.py
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess
import sys

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from isotherm import dataset, metrics, stats  # noqa: E402
from isotherm.backtest import Config, daily_pnl, run  # noqa: E402
from isotherm.baselines import LogPool, Source  # noqa: E402
from isotherm.model import IsothermNet, IsothermTransformer  # noqa: E402
from isotherm.splits import EMBARGO, LOCKBOX_START  # noqa: E402
from isotherm.weather import CITIES, NEW_CITIES  # noqa: E402

spec = importlib.util.spec_from_file_location("bt", ROOT / "scripts" / "backtest.py")
bt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bt)

TEST_FROM, TEST_TO = pd.Timestamp("2026-07-01"), pd.Timestamp("2026-10-04")
FROZEN = Config("pool · market+GFS", "kelly", fraction=0.25)
SOURCES = ["market", "emos_gfs", "emos_nbm", "emos_nbm_obs", "climatology"]


def suite():
    return [
        Source("market"),
        LogPool(["market", "emos_gfs"], "pool · market+GFS"),
        IsothermNet("isotherm"),
        IsothermTransformer("isotherm · transformer-L", d=128, layers=4, ff=256),
    ]


def main():
    seen = dataset.load(list(CITIES))
    seen = seen.take(np.flatnonzero((seen.meta["day"] < LOCKBOX_START - EMBARGO).to_numpy()))
    new = dataset.LadderSet.concat([dataset.build_city(k) for k in NEW_CITIES])
    d = new.meta["day"]
    new = new.take(np.flatnonzero(((d >= TEST_FROM) & (d <= TEST_TO)).to_numpy())).complete(SOURCES)
    print(
        "train {} ladders (seven cities), test {} ladders (twelve new)".format(len(seen), len(new)),
        flush=True,
    )

    res = {"from": str(TEST_FROM.date()), "to": str(TEST_TO.date()), "reads": {}}
    rows_16, preds_16 = None, None
    for read in sorted(new.meta["read"].unique()):
        tr = seen.take(np.flatnonzero((seen.meta["read"] == read).to_numpy()))
        te = new.take(np.flatnonzero((new.meta["read"] == read).to_numpy()))
        P = {m.name: m.fit(tr).predict(te) for m in suite()}
        days = te.meta["day"].to_numpy()
        ref = metrics.log_score(P["market"], te.y)
        r = {"ladders": len(te)}
        for name, p in P.items():
            if name == "market":
                continue
            g = ref - metrics.log_score(p, te.y)
            r[name] = {"gain": float(g.mean()), "ci": metrics.date_bootstrap_mean(days, g, 2000)}
        tf = metrics.log_score(P["isotherm"], te.y) - metrics.log_score(P["isotherm · transformer-L"], te.y)
        r["transformer_minus_isotherm"] = {
            "diff": float(tf.mean()),
            "ci": metrics.date_bootstrap_mean(days, tf, 2000),
        }
        g = ref - metrics.log_score(P["isotherm"], te.y)
        r["by_city"] = {
            c: float(g[(te.meta["city"] == c).to_numpy()].mean()) for c in sorted(te.meta["city"].unique())
        }
        r["pass"] = r["isotherm"]["ci"][0] > 0
        res["reads"][read] = r
        print(
            read,
            "isotherm vs market {:+.4f} [{:+.4f}, {:+.4f}]".format(
                r["isotherm"]["gain"], *r["isotherm"]["ci"]
            ),
            flush=True,
        )
        if read == "d1_16":
            rows_16, preds_16 = te, P

    passing = sum(v["pass"] for v in res["reads"].values())
    res["primary"] = {"reads_passing": int(passing), "verdict": "PASS" if passing >= 3 else "FAIL"}

    led = run(rows_16, preds_16[FROZEN.model], FROZEN)
    x = daily_pnl(led, rows_16.meta["day"]).to_numpy()
    t = stats.newey_west_t(x)
    verdict = (
        "PASS" if x.sum() > 0 and t > 1.645 else "CONSISTENT BUT UNDERPOWERED" if x.sum() > 0 else "FAIL"
    )
    res["strategy"] = {
        "frozen": FROZEN.name,
        "verdict": verdict,
        "pnl": float(x.sum()),
        "nw_t": float(t),
        "days": int(len(x)),
        "trades": int(len(led)),
        "by_city": {k: float(v["pnl"].sum()) for k, v in led.groupby("city")} if len(led) else {},
        "by_month": {
            k: float(v["pnl"].sum()) for k, v in led.groupby(led["day"].dt.to_period("M").astype(str))
        }
        if len(led)
        else {},
    }
    try:
        res["git"] = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).decode().strip()
    except Exception:
        res["git"] = None
    (ROOT / "results" / "unseen_cities.json").write_text(json.dumps(res, indent=2, default=str))
    print(json.dumps({"primary": res["primary"], "strategy": res["strategy"]}, indent=1, default=str))


if __name__ == "__main__":
    main()
