#!/usr/bin/env python3
"""G3 ablation: does synthetic pretraining help LadderNet at the day-before read?

PLAN §6 gate, made operational before any result was seen:
  (a) pretrained on 50% of real dates matches no pretraining on 100%:
      point estimate of the paired difference >= 0 and its 95% CI lower bound > -0.005 nats
  (b) or pretrained on 100% beats no pretraining on 100%: paired CI lower bound > 0
Every arm uses 3 seeds and is scored on identical walk-forward rows, against the market,
with date-block CIs. The control pretrains on labels sampled from the simulated market and
fine-tunes on labels sampled from the real one, so it must score like the market.

    uv run scripts/g3_ablation.py
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from isotherm import metrics  # noqa: E402
from isotherm import pretrain as P  # noqa: E402
from isotherm.baselines import Source  # noqa: E402
from isotherm.evaluation import oos_predictions  # noqa: E402
from isotherm.splits import EMBARGO, LOCKBOX_START  # noqa: E402

FRACS = (0.1, 0.25, 0.5, 1.0)
CONTROL = "control · market labels · pretrained"


def ci(days, v, boot):
    if len(v) == 0:
        return [float("nan"), float("nan")]
    return metrics.date_bootstrap_mean(days, v, boot)


def simulator_check(real, corpus):
    cut = LOCKBOX_START - EMBARGO
    pre = real.take(
        np.flatnonzero(((real.meta["day"] < cut) & np.isfinite(real.probs["emos_nbm"]).all(1)).to_numpy())
    )
    corp = corpus.take(np.flatnonzero((corpus.meta["day"] < cut).to_numpy()))
    sim = P.MarketSim().fit_empirical(pre).calibrate(corp)
    syn = sim.simulate(corp, np.random.default_rng(0))
    return {
        "tau": sim.tau,
        "lam": sim.lam,
        "real": sim.stats(pre),
        "simulated": sim.stats(syn),
        "real_ladders": len(pre),
        "synthetic_ladders": len(syn),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--boot", type=int, default=1000)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--until", default=None, help="truncate real data (smoke tests only)")
    a = ap.parse_args()
    t0 = time.time()
    real = P.load_real()
    if a.until:
        real = real.take(np.flatnonzero((real.meta["day"] < a.until).to_numpy()))
    offsets = P.layout_offsets(real)
    corpus = P.build_corpus(offsets)
    print(
        "real {} ladders; corpus {} ladders from {} stations".format(
            len(real), len(corpus), corpus.meta["city"].nunique()
        ),
        flush=True,
    )
    check = simulator_check(real, corpus)
    print(
        "simulator:",
        json.dumps(
            {
                k: (round(v, 4) if isinstance(v, float) else v)
                for k, v in check.items()
                if k not in ("real", "simulated")
            }
        ),
        flush=True,
    )
    for k in check["real"]:
        print(
            "   {:34s} real {:+.4f}  sim {:+.4f}".format(k, check["real"][k], check["simulated"][k]),
            flush=True,
        )

    pre = {f: P.Pretrained(corpus, f, seeds=a.seeds) for f in FRACS}
    none = {f: P.Subsampled(f, seeds=a.seeds) for f in FRACS}
    control = P.Pretrained(corpus, 1.0, seeds=a.seeds, market_labels=True, name=CONTROL)
    suite = [Source("market")] + list(none.values()) + list(pre.values()) + [control]
    o = oos_predictions(real, suite, cache_dir=None)[P.READ]
    rows, days = o.rows, o.rows.meta["day"].to_numpy()
    recent = (o.rows.meta["day"] >= LOCKBOX_START - np.timedelta64(365, "D")).to_numpy()
    ls = {m.name: metrics.log_score(o.preds[m.name], rows.y) for m in suite}
    ref = ls["market"]

    def gain(name, mask=None):
        m = np.ones(len(ref), bool) if mask is None else mask
        d = (ref - ls[name])[m]
        return {"gain": float(d.mean()), "ci": ci(days[m], d, a.boot)}

    def paired(x, y, mask=None):
        m = np.ones(len(ref), bool) if mask is None else mask
        d = (ls[y] - ls[x])[m]  # positive: x better than y
        return {"diff": float(d.mean()), "ci": ci(days[m], d, a.boot)}

    res = {
        "config": vars(a),
        "simulator_check": check,
        "folds": o.folds,
        "rows": len(rows),
        "curve": {},
        "paired": {},
        "recent": {},
    }
    for f in FRACS:
        res["curve"]["{:.0%}".format(f)] = {"none": gain(none[f].name), "pretrained": gain(pre[f].name)}
        res["paired"]["pretrained_vs_none_{:.0%}".format(f)] = paired(pre[f].name, none[f].name)
    res["control"] = gain(CONTROL)
    res["paired"]["pretrained_50_vs_none_100"] = paired(pre[0.5].name, none[1.0].name)
    res["recent"]["pretrained_vs_none_100"] = paired(pre[1.0].name, none[1.0].name, recent)
    res["recent"]["none_100"] = gain(none[1.0].name, recent)
    res["recent"]["pretrained_100"] = gain(pre[1.0].name, recent)
    p50 = res["paired"]["pretrained_50_vs_none_100"]
    p100 = res["paired"]["pretrained_vs_none_100%"]
    res["gate"] = {
        "a_matches_with_half_the_data": p50["diff"] >= 0 and p50["ci"][0] > -0.005,
        "b_beats_at_full_data": p100["ci"][0] > 0,
    }
    res["gate"]["pass"] = res["gate"]["a_matches_with_half_the_data"] or res["gate"]["b_beats_at_full_data"]
    res["pretrain_log"] = {f: pre[f].log for f in FRACS}
    res["seconds"] = round(time.time() - t0)

    out = pathlib.Path("results")
    out.mkdir(exist_ok=True)
    (out / "g3_learning_curve.json").write_text(json.dumps(res, indent=2, default=str))
    L = [
        "# G3: synthetic pretraining, learning curves",
        "",
        "Day-before read, {} walk-forward ladders, Δ log score vs market (nats, positive is better), "
        "95% date-block CIs, {} seeds per arm.".format(len(rows), a.seeds),
        "",
        "| Real training data | No pretraining | Pretrained | Pretrained minus none |",
        "|---|---|---|---|",
    ]
    for f in FRACS:
        k = "{:.0%}".format(f)
        n_, p_ = res["curve"][k]["none"], res["curve"][k]["pretrained"]
        d = res["paired"]["pretrained_vs_none_" + k]
        cell = "{:+.4f} [{:+.4f}, {:+.4f}]"
        L.append(
            "| {} | {} | {} | {} |".format(
                k,
                cell.format(n_["gain"], *n_["ci"]),
                cell.format(p_["gain"], *p_["ci"]),
                cell.format(d["diff"], *d["ci"]),
            )
        )
    L += [
        "",
        "Pretrained on 50% minus none on 100%: {:+.4f} [{:+.4f}, {:+.4f}]".format(p50["diff"], *p50["ci"]),
        "Control (market labels at both stages): {:+.4f} [{:+.4f}, {:+.4f}]".format(
            res["control"]["gain"], *res["control"]["ci"]
        ),
        "Last 12 months, pretrained minus none at 100%: {:+.4f} [{:+.4f}, {:+.4f}]".format(
            res["recent"]["pretrained_vs_none_100"]["diff"], *res["recent"]["pretrained_vs_none_100"]["ci"]
        ),
        "",
        "Gate: (a) {} · (b) {} · **{}**".format(
            res["gate"]["a_matches_with_half_the_data"],
            res["gate"]["b_beats_at_full_data"],
            "PASS" if res["gate"]["pass"] else "FAIL",
        ),
    ]
    (out / "g3_learning_curve.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
