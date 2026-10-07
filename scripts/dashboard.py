#!/usr/bin/env python3
"""Build the interactive results dashboard (results/dashboard.html) from results/*.json.

Every number comes from the raw result files; the page computes nothing new. The live
shadow record is read from the `shadow-ledger` branch when it is available.

    uv run scripts/dashboard.py
"""

from __future__ import annotations

import json
import pathlib
import subprocess

R = pathlib.Path("results")
READS = ["d1_16", "d0_08", "d0_12", "d0_14"]


def load(name):
    p = R / name
    # Raw results predate the rename and call the model LadderNet; show it as isotherm.
    return json.loads(p.read_text().replace("LadderNet", "isotherm")) if p.exists() else None


def periods(slices):
    return {k.split("=")[1]: round(v["gain"], 4) for k, v in slices.items() if k.startswith("period=")}


def cell(r, daily=True):
    s = r["selected"]
    out = {
        "pnl": round(s["pnl"]),
        "sharpe": round(s["sharpe_ann"], 2),
        "sharpe_ci": [round(x, 2) for x in s["sharpe_ann_ci"]],
        "nw_t": round(s["nw_t"], 2),
        "dsr": round(r["deflated_sharpe"]["dsr"], 3),
        "pbo": round(r["pbo"]["pbo"], 2),
        "trades": s["trades"],
        "max_dd": round(s["max_drawdown"]),
        "hit": round(s.get("hit_rate") or 0, 3),
        "noise": round(r["placebos"]["noise_matched_turnover"]["pnl"]),
        "attribution": {k: round(v) for k, v in (s.get("attribution") or {}).items()},
        "touch": round(s["touch_bound_pnl"]) if "touch_bound_pnl" in s else None,
        "robustness": [{"s": x["scenario"], "pnl": round(x["pnl"])} for x in r.get("robustness", [])],
        "robust_cfg": r.get("robustness_config"),
    }
    if daily and "daily" in s:
        acc, pts = 0.0, []
        for d, v in s["daily"]:
            acc += v
            pts.append([d, round(acc, 1)])
        out["equity"] = pts
    return out


def shadow():
    try:
        m = subprocess.check_output(
            ["git", "show", "origin/shadow-ledger:metrics.json"], stderr=subprocess.DEVNULL
        )
        return json.loads(m)
    except Exception:
        return {"settled_ladders": 0}


def build():
    b2, b1 = load("benchmark_g2.json"), load("benchmark.json")
    d = {
        "reads": READS,
        "labels": {"d1_16": "4pm day before", "d0_08": "8am", "d0_12": "noon", "d0_14": "2pm"},
    }
    d["leaderboard"], d["decay"], d["recent"], d["reliability"], d["cities"] = {}, {}, {}, {}, {}
    for read in READS:
        x = b2["results"][read]
        d["leaderboard"][read] = [
            {
                "model": r["model"],
                "gain": r.get("gain_vs_market"),
                "ci": r.get("gain_vs_market_ci"),
                "ls": round(r["log_score"], 4),
                "ece": round(r["ece_debiased"], 4),
                "rps": round(r["rps"], 4),
            }
            for r in x["leaderboard"]
        ]
        d["decay"][read] = {
            "isotherm": periods(b2["slices"][read]["slices"]),
            "pool": periods(b1["slices"][read]["slices"]) if read in b1["slices"] else {},
        }
        d["recent"][read] = {
            k: {"gain": round(v["gain"], 4), "ci": [round(c, 4) for c in v["ci"]]}
            for k, v in x["recent"].items()
        }
        d["reliability"][read] = b2["reliability"][read]
        d["cities"][read] = {
            c: {"gain": round(v["gain"], 4), "ci": [round(z, 4) for z in v["ci"]]}
            for c, v in x["recent"]["isotherm"]["by_city"].items()
        }
    bt = load("backtest_g2.json")["results"]
    d["cells"] = {k: cell(r) for k, r in bt.items()}
    over = []
    for name, group in (
        ("backtest_taker.json", "highs G1"),
        ("backtest_maker.json", "highs G1"),
        ("backtest_g2.json", "highs G2"),
        ("lows_backtest.json", "daily lows"),
        ("sports_backtest.json", "MLB"),
    ):
        x = load(name)
        if x:
            for k, r in x["results"].items():
                over.append(
                    {
                        "group": group,
                        "cell": k,
                        "dsr": round(r["deflated_sharpe"]["dsr"], 3),
                        "pbo": round(r["pbo"]["pbo"], 2),
                        "pnl": round(r["selected"]["pnl"]),
                    }
                )
    d["overfitting"] = over
    hl, ll = load("lockbox.json"), load("lows_lockbox.json")
    lows_bt = load("lows_backtest.json")["results"]["d1_16 · taker"]
    d["sealed"] = {
        "highs": {
            "bt": cell(bt["d1_16 · taker"]),
            "lb": {
                **cell(
                    {
                        "selected": hl["summary"],
                        "deflated_sharpe": {"dsr": 0},
                        "pbo": {"pbo": 0},
                        "placebos": {"noise_matched_turnover": hl["noise_matched_turnover"]},
                    }
                ),
                "by_month": hl["by_month"],
                "verdict": hl["verdict"],
                "score": hl["scores"]["pool · market+GFS"],
            },
        },
        "lows": {
            "bt": cell(lows_bt),
            "lb": {
                **cell(
                    {
                        "selected": ll["summary"],
                        "deflated_sharpe": {"dsr": 0},
                        "pbo": {"pbo": 0},
                        "placebos": ll["checks"],
                    }
                ),
                "by_month": ll.get("by_month"),
                "verdict": ll["verdict"],
                "score": {"gain_vs_market": ll["log_score_gain_vs_market"], "ci": ll["log_score_ci"]},
            },
        },
    }
    s = load("survey.json")
    d["survey"] = [
        {
            "series": r["series"].replace("KX", ""),
            "cat": r["category"],
            "events": r["listed_settled_events"],
            "spread": round(100 * ((r.get("lead0.5") or {}).get("median_spread") or 0), 1),
            "volume": r["median_event_volume"],
        }
        for r in s["results"]
    ]
    g3 = load("g3_learning_curve.json")
    d["g3"] = (
        {
            f: {
                k: {"gain": round(v["gain"], 4), "ci": [round(c, 4) for c in v["ci"]]}
                for k, v in arms.items()
            }
            for f, arms in g3["curve"].items()
        }
        if g3
        else {}
    )
    sb = load("sports_benchmark.json")
    d["mlb"] = (
        {
            r: {k: {"gain": round(v["gain"], 4), "ci": [round(c, 4) for c in v["ci"]]} for k, v in x.items()}
            for r, x in sb["gate0"]["by_read"].items()
        }
        if sb
        else {}
    )
    lb = load("lows_benchmark.json")
    d["lows_gate"] = (
        {
            r: {k: {"gain": round(v["gain"], 4), "ci": [round(c, 4) for c in v["ci"]]} for k, v in x.items()}
            for r, x in lb["gate0"]["by_read"].items()
        }
        if lb
        else {}
    )
    tg = load("transformer_gate.json")
    d["transformer"] = (
        {
            r: {
                "diff": round(v["transformer_minus_isotherm_recent"], 4),
                "ci": [round(c, 4) for c in v["ci"]],
                "control": round(v["control_vs_market_all"], 4),
            }
            for r, v in tg["results"].items()
        }
        if tg
        else {}
    )
    d["research"] = research()
    d["shadow"] = shadow()
    return d


def research():
    """FINDINGS §18-35: every variant against the MLP, the learning curve, unseen cities, regime."""

    def ci(x):
        return [round(c, 4) for c in x]

    arms = []

    def arm(name, kind, sec, per_read):
        if per_read:
            arms.append({"name": name, "kind": kind, "sec": sec, "reads": per_read})

    tl = load("transformer_large_gate.json")
    if tl:
        arm(
            "Transformer, 8x larger",
            "gate",
            "§19",
            {
                r: {"d": round(v["transformer_minus_isotherm_recent"], 4), "ci": ci(v["ci"])}
                for r, v in tl["results"].items()
            },
        )
    ds = load("data_scaling.json")
    if ds:
        arm(
            "Transformer, pooled reads",
            "gate",
            "§21",
            {
                r: {"d": round(v["pooled_tf_minus_mlp"]["diff"], 4), "ci": ci(v["pooled_tf_minus_mlp"]["ci"])}
                for r, v in ds["per_read"].items()
            },
        )
    ns = load("nbm_spread.json")
    if ns:
        arm(
            "NBM's own spread",
            "gate",
            "§26",
            {r: {"d": round(v["diff"], 4), "ci": ci(v["ci"])} for r, v in ns["adoption"].items()},
        )
    en = load("explore_ensemble.json")
    if en:
        arm(
            "Ensemble of three",
            "explore",
            "§28",
            {
                r: {
                    "d": round(v["mean(mlp,tf,spread)"]["vs_mlp"], 4),
                    "ci": ci(v["mean(mlp,tf,spread)"]["ci"]),
                }
                for r, v in en.items()
            },
        )
    dy = load("explore_dynamics.json")
    if dy:
        for key, name in (("isotherm + flow", "Order flow"), ("isotherm + momentum", "Price momentum")):
            arm(
                name,
                "explore",
                "§30",
                {r: {"d": round(v[key]["vs_mlp"], 4), "ci": ci(v[key]["ci"])} for r, v in dy.items()},
            )
    lm = load("explore_lamp_model.json")
    if lm:
        arm(
            "LAMP",
            "explore",
            "§33",
            {
                r: {"d": round(v["isotherm + LAMP"]["vs_mlp"], 4), "ci": ci(v["isotherm + LAMP"]["ci"])}
                for r, v in lm.items()
                if r != "d1_16"
            },
        )
    wx = load("wx_gate.json")
    if wx:
        v = wx["adoption"]["vs_mlp"]
        arm(
            "Weather model, 576 stations",
            "gate",
            "§35",
            {"d1_16": {"d": round(v["diff"], 4), "ci": ci(v["ci"])}},
        )
    out = {"arms": arms}
    if wx:
        f = wx["forecast"]["vs_emos_spread"]
        out["wx"] = {
            "forecast": {"d": round(f["diff"], 4), "ci": ci(f["ci"])},
            "mlp_vs_market": round(wx["adoption"]["mlp_vs_market"], 4),
            "wx_vs_market": round(wx["adoption"]["wx_mlp_vs_market"], 4),
        }
    te = load("typed_eval.json")
    if te:

        def gap(v):
            return round(100 * (v["score_80_coverage"] - v["score_80_predicted_mass"]), 1)

        out["typed"] = {
            r: {
                "ece": [
                    round(x["models"]["market"]["noul_ece"], 3),
                    round(x["models"]["isotherm"]["noul_ece"], 3),
                ],
                "cover": [gap(x["models"]["market"]), gap(x["models"]["isotherm"])],
                "crps": {
                    "d": round(x["models"]["isotherm"]["vs_market_mean"]["score_crps"], 4),
                    "ci": ci(x["models"]["isotherm"]["vs_market"]["score_crps"]),
                },
                "violations": x["coherence_violations"],
            }
            for r, x in te["reads"].items()
        }
    ec = load("explore_cities.json")
    if ec:
        cols = {
            "mlp_seven": ("seven", "mlp19_minus_mlp7"),
            "tf_seven": ("seven", "tf19_minus_tf7"),
            "tf_twelve": ("twelve", "tf19_minus_tf7"),
            "tf_vs_mlp": ("seven", "tf19_minus_mlp19"),
        }
        out["cities"] = {
            r: {c: {"d": round(v[g][k]["diff"], 4), "ci": ci(v[g][k]["ci"])} for c, (g, k) in cols.items()}
            for r, v in ec["reads"].items()
        }
    if ds:
        out["curve"] = {
            f: {"mlp": round(v["mlp_vs_market"], 4), "tf": round(v["tf_vs_market"], 4)}
            for f, v in ds["learning_curve"].items()
        }
    un = load("unseen_cities.json")
    if un:
        out["unseen"] = {
            "reads": {
                r: {"g": round(v["isotherm"]["gain"], 4), "ci": ci(v["isotherm"]["ci"])}
                for r, v in un["reads"].items()
            },
            "pnl": round(un["strategy"]["pnl"]),
            "t": round(un["strategy"]["nw_t"], 2),
            "ladders": sum(v["ladders"] for v in un["reads"].values()),
        }
    ra = load("regime_audit.json")
    if ra:
        out["regime"] = {
            m: {
                "mkt": round(v["ls_market"], 3),
                "nbm": round(v["ls_emos_nbm"], 3),
                "w_gfs": v["w_market+GFS"][1],
                "n": v["ladders"],
            }
            for m, v in ra.items()
            if v["ladders"] >= 100
        }
    fz = []
    for tag, names in (
        ("", ["MLP (reference)", "Transformer, 8x larger"]),
        ("_spread", ["NBM's own spread"]),
        ("_flow", ["Order flow"]),
        ("_wx", ["Weather model, from 2026-10-09"]),
    ):
        f = pathlib.Path("shadow/forward/frozen{}.json".format(tag))
        if f.exists():
            m = json.loads(f.read_text())
            fz += [{"name": n, "sha": m["sha256"][:12], "fit_through": m["fit_through"]} for n in names]
    if fz:
        fz.append({"name": "Ensemble of three", "sha": "members above", "fit_through": fz[0]["fit_through"]})
    ft = load("forward_test.json")
    out["forward"] = {"arms": fz, "window": ["2026-10-07", "2027-04-05"], "result": ft}
    return out


HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="description"
  content="Out-of-sample results for isotherm, a calibrated decision model on Kalshi temperature markets.">
<meta property="og:title" content="Isotherm results">
<meta property="og:description"
  content="Probabilities, backtests, sealed tests, ablations and the live shadow record.">
<style>html,body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style>
"""


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--standalone", help="also write a complete HTML document here (for GitHub Pages)")
    ap.add_argument("--nav", action="store_true", help="add the physicalreasoning.ai site header")
    a = ap.parse_args()
    data = build()
    tpl = (pathlib.Path(__file__).parent / "dashboard_template.html").read_text()
    out = tpl.replace("__DATA__", json.dumps(data, separators=(",", ":")))
    (R / "dashboard.html").write_text(out.replace("__NAV__", ""))
    print("wrote results/dashboard.html ({:.0f} KB)".format(len(out) / 1024))
    if a.standalone:
        # The template opens with <title> and <style>, which belong in <head>; the rest is body.
        nav = (
            '<nav class="site"><a class="wordmark" href="/">[Pr]</a>'
            '<a class="back" href="/blog/">&larr; Blog</a></nav>'
        )
        out = out.replace("__NAV__", nav if a.nav else "")
        cut = out.index('<div class="wrap">')
        doc = HEAD + out[:cut] + "</head>\n<body>\n" + out[cut:] + "\n</body>\n</html>\n"
        p = pathlib.Path(a.standalone)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(doc)
        print("wrote {} ({:.0f} KB)".format(p, len(doc) / 1024))


if __name__ == "__main__":
    main()
