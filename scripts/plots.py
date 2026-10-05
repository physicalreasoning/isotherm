#!/usr/bin/env python3
"""Render the figure set in results/plots/ from the raw results. Computes nothing new.

uv run scripts/plots.py
"""

from __future__ import annotations

import json
import pathlib

import matplotlib
import matplotlib.dates

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

R = pathlib.Path("results")
OUT = R / "plots"

INK, MUTED, FAINT, SURFACE = "#1f1f1d", "#6b6a64", "#e6e5e0", "#fcfcfb"
MODEL, BASE = "#2a78d6", "#9a9890"  # model = slot 1 blue; baselines recede to grey
CATS = {
    "weather": "#2a78d6",
    "sports": "#eb6834",
    "commodities": "#1baf7a",
    "economics": "#eda100",
    "financials": "#e87ba4",
    "crypto": "#008300",
}
READS = ["d1_16", "d0_08", "d0_12", "d0_14"]
READ_LABEL = {"d1_16": "4pm day before", "d0_08": "8am", "d0_12": "noon", "d0_14": "2pm"}

plt.rcParams.update(
    {
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "axes.edgecolor": FAINT,
        "axes.labelcolor": MUTED,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "axes.grid": True,
        "grid.color": FAINT,
        "grid.linewidth": 0.8,
        "axes.axisbelow": True,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "font.size": 9.5,
        "axes.titlesize": 10.5,
        "axes.titleweight": "bold",
        "axes.titlecolor": INK,
        "axes.titlelocation": "left",
        "legend.frameon": False,
        "lines.linewidth": 2,
        "figure.dpi": 150,
    }
)


def load(name):
    p = R / name
    # Raw results predate the rename and call the model LadderNet; show it as isotherm.
    return json.loads(p.read_text().replace("LadderNet", "isotherm")) if p.exists() else None


def save(fig, name, note):
    fig.text(0.01, -0.06, note, color=MUTED, fontsize=7.5, ha="left", va="top")
    fig.savefig(OUT / name, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    print("wrote", OUT / name)


def zero(ax):
    ax.axhline(0, color=INK, lw=0.9, alpha=0.6, zorder=1)


# points that land on top of each other get one shared label
LABEL_AS = {"HIGHNY": "HIGHNY, HIGHCHI", "BTCD": "BTCD", "GOLD15M": "GOLD15M, ATPMATCH"}
SKIP_LABEL = {"HIGHCHI", "ATPMATCH"}
OFFSET = {"GOLD15M": (-10, -12), "BTCD": (6, 6), "INX": (6, 2)}


def survey():
    s = load("survey.json")
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    for r in s["results"]:
        sp = (r.get("lead0.5") or {}).get("median_spread")
        if sp is None:
            continue
        c = CATS.get(r["category"], BASE)
        ax.scatter(
            r["listed_settled_events"],
            sp * 100,
            s=18 + 14 * np.log10(max(r["median_event_volume"], 10)),
            color=c,
            edgecolor=SURFACE,
            linewidth=1.5,
            zorder=3,
        )
        name = r["series"].replace("KX", "")
        if name in SKIP_LABEL:
            continue
        ax.annotate(
            LABEL_AS.get(name, name),
            (r["listed_settled_events"], sp * 100),
            xytext=OFFSET.get(name, (5, 3)),
            textcoords="offset points",
            fontsize=7,
            color=INK,
        )
    ax.set_xscale("log")
    ax.set_xlabel("settled events (log)")
    ax.set_ylabel("median spread at mid-life (¢)")
    ax.set_title(
        "Market survey: 17 Kalshi series. Weather has history, room in the spread and a free forecast"
    )
    for k, c in CATS.items():
        ax.scatter([], [], color=c, label=k, s=30)
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=8)
    save(
        fig, "01_market_survey.png", "Source: results/survey.json · point size ∝ log median volume per event"
    )


def edge_decay():
    g1, g2 = load("benchmark.json"), load("benchmark_g2.json")
    fig, axes = plt.subplots(1, 4, figsize=(11, 3.2), sharey=True)
    for ax, read in zip(axes, READS, strict=True):
        net = {
            k.split("=")[1]: v["gain"]
            for k, v in g2["slices"][read]["slices"].items()
            if k.startswith("period=")
        }
        xs = list(net)
        ax.plot(xs, [net[x] for x in xs], color=MODEL, marker="o", ms=5, label="isotherm", zorder=3)
        if read in g1["slices"]:
            pool = {
                k.split("=")[1]: v["gain"]
                for k, v in g1["slices"][read]["slices"].items()
                if k.startswith("period=")
            }
            ax.plot(
                xs, [pool.get(x, np.nan) for x in xs], color=BASE, ls="--", lw=1.6, label="best simple pool"
            )
        zero(ax)
        ax.set_title(READ_LABEL[read])
        ax.tick_params(axis="x", rotation=45)
    axes[0].set_ylabel("log score gain vs market (nats)")
    axes[0].legend(loc="upper right", fontsize=8)
    fig.suptitle(
        "The edge decayed: gain over the market by half-year", x=0.01, ha="left", fontweight="bold", y=1.03
    )
    save(
        fig,
        "02_edge_decay.png",
        "Source: results/benchmark.json, results/benchmark_g2.json · walk-forward, out of sample",
    )


def forecast_split():
    b = load("benchmark_g2.json")
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    w = 0.36
    for i, read in enumerate(READS):
        rec = b["results"][read]["recent"]
        for j, (name, lab, col) in enumerate(
            [("pool · market+NBM", "market + NBM", BASE), ("pool · market+GFS", "market + GFS MOS", MODEL)]
        ):
            v = rec[name]
            x = i + (j - 0.5) * w
            ax.bar(x, v["gain"], w * 0.92, color=col, label=lab if i == 0 else None, zorder=3)
            ax.errorbar(
                x,
                v["gain"],
                yerr=[[v["gain"] - v["ci"][0]], [v["ci"][1] - v["gain"]]],
                color=INK,
                capsize=3,
                lw=1,
                zorder=4,
            )
    zero(ax)
    ax.set_xticks(range(len(READS)), [READ_LABEL[r] for r in READS])
    ax.set_ylabel("Δ log score vs market (nats)")
    ax.set_title("Last 12 months: the market priced NBM, not GFS MOS")
    ax.legend(loc="lower right", fontsize=8)
    save(
        fig, "03_forecast_split.png", "Source: results/benchmark_g2.json · whiskers: 95% date-block bootstrap"
    )


def leaderboard():
    b = load("benchmark_g2.json")
    models = [
        "isotherm",
        "pool · market+GFS+obs · 365d",
        "pool · all",
        "pool · market+GFS",
        "pool · market+NBM",
        "market (tempered)",
        "EMOS · NBM",
        "isotherm · market-sampled labels (control)",
    ]
    fig, axes = plt.subplots(1, 4, figsize=(11, 3.6), sharey=True)
    for ax, read in zip(axes, READS, strict=True):
        lb = {r["model"]: r for r in b["results"][read]["leaderboard"]}
        for i, m in enumerate(models):
            r = lb[m]
            g, (lo, hi) = r["gain_vs_market"], r["gain_vs_market_ci"]
            c = MODEL if m == "isotherm" else (INK if "control" in m else BASE)
            ax.plot([lo, hi], [i, i], color=c, lw=1.4)
            ax.plot(g, i, "o", color=c, ms=5, mec=SURFACE, mew=1)
        ax.axvline(0, color=INK, lw=0.9, alpha=0.6)
        ax.set_xlim(-0.30, 0.10)
        ax.set_title(READ_LABEL[read])
        ax.set_xlabel("Δ log score vs market")
    axes[0].set_yticks(
        range(len(models)),
        [m.replace("isotherm · market-sampled labels (control)", "control (market labels)") for m in models],
    )
    axes[0].invert_yaxis()
    fig.suptitle(
        "Leaderboard: every model scored against the market on identical rows",
        x=0.01,
        ha="left",
        fontweight="bold",
        y=1.04,
    )
    save(
        fig,
        "04_leaderboard.png",
        "Source: results/benchmark_g2.json · 95% date-block CIs · EMOS alone can sit off-scale left",
    )


def calibration():
    b = load("benchmark_g2.json")
    fig, axes = plt.subplots(1, 4, figsize=(11, 3.2), sharey=True)
    for ax, read in zip(axes, READS, strict=True):
        rel = b["reliability"][read]
        ax.plot([0, 1], [0, 1], color=FAINT, lw=1.2, zorder=1)
        for k, c, lab in (("market", BASE, "market"), ("isotherm", MODEL, "isotherm")):
            r = rel[k]
            ax.plot(r["mean_prob"], r["freq"], marker="o", ms=4, color=c, label=lab, zorder=3)
        ax.set_title(READ_LABEL[read])
        ax.set_xlabel("predicted probability")
        ax.set_aspect("equal")
    axes[0].set_ylabel("observed frequency")
    axes[0].legend(loc="upper left", fontsize=8)
    fig.suptitle(
        "Calibration: every bucket as a yes/no question", x=0.01, ha="left", fontweight="bold", y=1.03
    )
    save(fig, "05_calibration.png", "Source: results/benchmark_g2.json · out-of-sample, pooled across cities")


def city_heatmap():
    b = load("benchmark_g2.json")
    cities = sorted(b["results"]["d1_16"]["recent"]["isotherm"]["by_city"])
    M = np.array(
        [[b["results"][r]["recent"]["isotherm"]["by_city"][c]["gain"] for r in READS] for c in cities]
    )
    lim = np.nanmax(np.abs(M))
    from matplotlib.colors import LinearSegmentedColormap

    cmap = LinearSegmentedColormap.from_list("div", ["#e34948", "#f0efec", "#2a78d6"])
    fig, ax = plt.subplots(figsize=(6.2, 3.8))
    ax.imshow(M, cmap=cmap, vmin=-lim, vmax=lim, aspect="auto")
    ax.grid(False)
    for i in range(len(cities)):
        for j in range(len(READS)):
            ci = b["results"][READS[j]]["recent"]["isotherm"]["by_city"][cities[i]]["ci"]
            star = " *" if ci[0] > 0 else ""
            ax.text(j, i, "{:+.3f}{}".format(M[i, j], star), ha="center", va="center", fontsize=8, color=INK)
    ax.set_xticks(range(len(READS)), [READ_LABEL[r] for r in READS])
    ax.set_yticks(range(len(cities)), cities)
    ax.set_title("isotherm vs market, last 12 months, by city")
    save(
        fig,
        "06_city_heatmap.png",
        "Source: results/benchmark_g2.json · * = 95% CI excludes zero · blue better than market, red worse",
    )


def equity():
    bt = load("backtest_g2.json")["results"]["d1_16 · taker"]["selected"]
    lb = load("lockbox.json")["summary"]
    lows_bt = load("lows_backtest.json")["results"]["d1_16 · taker"]["selected"]
    lows_lb = load("lows_lockbox.json")["summary"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.4))
    for ax, a, b, title in (
        (axes[0], bt, lb, "Highs, 4pm day before"),
        (axes[1], lows_bt, lows_lb, "Daily lows, 4pm day before"),
    ):
        s1 = pd.Series({pd.Timestamp(d): v for d, v in a["daily"]}).cumsum()
        s2 = pd.Series({pd.Timestamp(d): v for d, v in b["daily"]}).cumsum() + s1.iloc[-1]
        ax.plot(s1.index, s1.values, color=MODEL, lw=1.6, label="walk-forward backtest")
        ax.plot(s2.index, s2.values, color=INK, lw=2.4, label="sealed test, scored once")
        ax.axvspan(s2.index[0], s2.index[-1], color=FAINT, alpha=0.6, lw=0)
        ax.set_title(title)
        loc = matplotlib.dates.AutoDateLocator(minticks=3, maxticks=8)
        ax.xaxis.set_major_locator(loc)
        ax.xaxis.set_major_formatter(matplotlib.dates.ConciseDateFormatter(loc))
        ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: "${:,.0f}".format(v)))
        ax.annotate(
            "sealed: {:+,.0f}".format(b["pnl"]),
            (s2.index[-1], s2.iloc[-1]),
            xytext=(-6, 8),
            textcoords="offset points",
            ha="right",
            fontsize=8,
            color=INK,
        )
    axes[0].legend(loc="upper left", fontsize=8)
    fig.suptitle(
        "Paper PnL, $10k bankroll, taker fills, Kalshi fees", x=0.01, ha="left", fontweight="bold", y=1.03
    )
    save(
        fig,
        "07_equity.png",
        "Source: results/backtest_g2.json, lockbox.json, lows_backtest.json, lows_lockbox.json",
    )


def overfitting_map():
    pts = []
    for name, label, col in (
        ("backtest_taker.json", "highs G1", BASE),
        ("backtest_maker.json", "highs G1", BASE),
        ("backtest_g2.json", "highs G2", MODEL),
        ("lows_backtest.json", "daily lows", "#eb6834"),
        ("sports_backtest.json", "MLB", "#1baf7a"),
    ):
        d = load(name)
        if not d:
            continue
        for k, r in d["results"].items():
            pts.append((r["pbo"]["pbo"], r["deflated_sharpe"]["dsr"], label, col, k, r["selected"]["pnl"]))
    fig, ax = plt.subplots(figsize=(7.2, 4.4))
    ax.axvspan(0, 0.2, ymin=0.95 / 1.05, ymax=1, color="#2a78d6", alpha=0.08, lw=0)
    ax.axvline(0.2, color=MUTED, lw=0.8, ls=":")
    ax.axhline(0.95, color=MUTED, lw=0.8, ls=":")
    seen = set()
    for pbo, dsr, lab, col, k, _pnl in pts:
        ax.scatter(
            pbo,
            dsr,
            color=col,
            s=34,
            edgecolor=SURFACE,
            lw=1.2,
            zorder=3,
            label=lab if lab not in seen else None,
        )
        seen.add(lab)
        if dsr > 0.5:
            ax.annotate(
                "{} · {}".format(lab.split()[0] if lab != "daily lows" else "lows", k.replace(" · ", " ")),
                (pbo, dsr),
                xytext=(5, -3),
                textcoords="offset points",
                fontsize=7,
                color=INK,
            )
    ax.text(0.01, 1.0, "believable", color=MODEL, fontsize=8, va="bottom")
    ax.set_xlim(-0.02, 0.7)
    ax.set_ylim(-0.03, 1.05)
    ax.set_xlabel("probability of backtest overfitting (CSCV), lower is better")
    ax.set_ylabel("deflated Sharpe ratio")
    ax.set_title("Overfitting map: every strategy cell we ran")
    ax.legend(loc="upper right", fontsize=8)
    save(
        fig,
        "08_overfitting_map.png",
        "Bars: DSR ≥ 0.95 and PBO ≤ 0.20 · only the lows 4pm cell cleared both, and its sealed test made $36",
    )


def attribution():
    bt = load("backtest_g2.json")["results"]
    cells = [k for k in bt if "attribution" in bt[k]["selected"]]
    fig, ax = plt.subplots(figsize=(8.2, 4.2))
    parts = [
        ("alpha_vs_mid", "alpha vs mid", MODEL),
        ("spread_paid", "spread (taker pays, maker earns)", "#e34948"),
        ("fees", "fees", "#eb6834"),
    ]
    y = np.arange(len(cells))
    for j, (key, lab, col) in enumerate(parts):
        vals = [bt[c]["selected"]["attribution"][key] for c in cells]
        ax.barh(y + (j - 1) * 0.26, vals, 0.24, color=col, label=lab, zorder=3)
    ax.scatter(
        [bt[c]["selected"]["pnl"] for c in cells], y, marker="D", color=INK, s=22, zorder=4, label="net PnL"
    )
    ax.axvline(0, color=INK, lw=0.9, alpha=0.6)
    ax.set_yticks(
        y,
        [
            c.replace("d1_16", "4pm d-1")
            .replace("d0_08", "8am")
            .replace("d0_12", "noon")
            .replace("d0_14", "2pm")
            for c in cells
        ],
    )
    ax.invert_yaxis()
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: "${:,.0f}k".format(v / 1000)))
    ax.set_title("Where the money goes: information vs costs, by strategy cell")
    ax.legend(loc="lower right", fontsize=8, ncol=2)
    save(
        fig,
        "09_attribution.png",
        "Source: results/backtest_g2.json · maker cells pay no spread; adverse selection shows up in alpha",
    )


def g3_curve():
    g = load("g3_learning_curve.json")
    if not g:
        return
    fr = list(g["curve"])
    x = [float(f.rstrip("%")) for f in fr]
    fig, ax = plt.subplots(figsize=(6.2, 3.6))
    for key, lab, col in (
        ("none", "no pretraining", BASE),
        ("pretrained", "pretrained on 92k synthetic ladders", MODEL),
    ):
        m = np.array([g["curve"][f][key]["gain"] for f in fr])
        lo = np.array([g["curve"][f][key]["ci"][0] for f in fr])
        hi = np.array([g["curve"][f][key]["ci"][1] for f in fr])
        ax.fill_between(x, lo, hi, color=col, alpha=0.15, lw=0)
        ax.plot(x, m, marker="o", color=col, label=lab)
    ax.set_xscale("log")
    ax.set_xticks(x, fr)
    ax.set_xlabel("share of real training data")
    ax.set_ylabel("Δ log score vs market")
    ax.set_title("G3: pretraining helps only when real data is scarce")
    ax.legend(loc="lower right", fontsize=8)
    save(
        fig,
        "10_g3_learning_curve.png",
        "Source: results/g3_learning_curve.json · 4pm day-before read · bands: 95% CIs",
    )


def robustness():
    bt = load("backtest_g2.json")["results"]["d1_16 · taker"]
    rows = bt["robustness"]
    fig, ax = plt.subplots(figsize=(6.6, 3.4))
    labels = [r["scenario"] for r in rows]
    vals = [r["pnl"] for r in rows]
    ax.barh(range(len(rows)), vals, color=[MODEL if v > 0 else "#e34948" for v in vals], zorder=3)
    for i, v in enumerate(vals):
        ax.text(
            v, i, " ${:,.0f}".format(v), va="center", ha="left" if v >= 0 else "right", fontsize=8, color=INK
        )
    ax.set_yticks(range(len(rows)), labels)
    ax.invert_yaxis()
    ax.axvline(0, color=INK, lw=0.9, alpha=0.6)
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: "${:,.0f}k".format(v / 1000)))
    ax.set_title("Stress test, 4pm day-before taker ({})".format(bt["robustness_config"]))
    save(fig, "11_robustness.png", "Source: results/backtest_g2.json")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for f in (
        survey,
        edge_decay,
        forecast_split,
        leaderboard,
        calibration,
        city_heatmap,
        equity,
        overfitting_map,
        attribution,
        g3_curve,
        robustness,
    ):
        f()


if __name__ == "__main__":
    main()
