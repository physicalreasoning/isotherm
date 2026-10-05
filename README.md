# pm-decide

**An open, typed, calibrated decision model for prediction markets.**
Built and evaluated on Kalshi daily high-temperature ladders.

Inspired by TypeSafe AI's Jev: you give it a *state* and a set of *typed questions*, and it returns
typed answers with calibrated probabilities instead of text. Unlike Jev, the weights, data pipeline,
evaluation and every negative result are public. Every answer is read off one predictive
distribution, so answers to different question types cannot contradict each other.

| Question type | Here |
|---|---|
| **Choice** | which ladder bucket settles YES, with a probability per bucket |
| **Noul** | P(high ≥ k), P(high in a set) |
| **Score** | expected high, quantiles, interval |

## Status

Pre-registered plan in [docs/PLAN.md](docs/PLAN.md); domain choice and the survey behind it in
[docs/01-market-selection.md](docs/01-market-selection.md); evaluation protocol in
[docs/EVALS.md](docs/EVALS.md); latest leaderboard in [results/benchmark.md](results/benchmark.md),
backtests in [results/backtest_g2.md](results/backtest_g2.md); every headline number in one place in
[results/SUMMARY.md](results/SUMMARY.md).

| Stage | Question | Result |
|---|---|---|
| Survey | which market is worth modelling | weather highs: 7 cities, ~8,200 city-days ([selection](docs/01-market-selection.md)) |
| Labels | are the settlements reproducible | 7,722 ladders, 100% bucket-arithmetic agreement, settlement = NWS CLI on all but 1 of 1,553 NY days |
| G0 | does a free forecast add information | yes, but decaying: +0.18 nats in 2023 H2, about 0 by 2025 for simple pools. The market now prices NBM, not GFS MOS ([§5](FINDINGS.md)) |
| G1 backtest | can simple pools make money | no robust strategy: about one tick of edge as a taker, adverse selection as a maker ([§6-7](FINDINGS.md)) |
| G2 | does a learned model help | LadderNet +0.033 to +0.071 nats vs market, best calibrated, positive every half-year ([§8](FINDINGS.md)) |
| G2 backtest | does it survive costs | day-before taker: +$22k, Sharpe 2.05, survives +2¢ slippage; DSR 0.85, PBO 0.26 ([§8](FINDINGS.md)) |
| Lockbox | one sealed out-of-sample test | pass, marginally: +$1,851 on 95 unseen days, NW t 1.77; monthly PnL halving ([§9-10](FINDINGS.md)) |
| Sports | same pipeline on MLB | no edge: within ±0.001 nats of the market ([SPORTS](docs/SPORTS.md)) |
| G5 | does it hold live | running: paper trades at 16:00 local daily, ledger on [`shadow-ledger`](../../tree/shadow-ledger) |
| G3 | synthetic pretraining | not started |

## Reproduce

```bash
uv sync
uv run scripts/survey_markets.py --events 40   # market selection, ~5 min cold, seconds cached
uv run scripts/fetch_forecasts.py              # GFS MOS, NBM, NWS CLI from IEM (slow, polite)
uv run scripts/build_weather_panel.py          # point-in-time Kalshi ladders, ~50k calls, hours
uv run scripts/check_labels.py                 # label validation, fails loudly
uv run scripts/benchmark.py                    # G0 verdict + baseline leaderboard
uv run scripts/fetch_trades.py                 # every print, for the maker fill model
uv run scripts/backtest.py                     # taker + maker, nested selection, DSR, PBO
uv run scripts/lockbox.py                      # the one-shot held-out test (already run once)
uv run scripts/report.py                       # every headline metric -> results/SUMMARY.md
uv run scripts/shadow.py score settle report   # live shadow scoring (what CI runs hourly)
uv run pytest
```

Everything uses unauthenticated public endpoints: Kalshi's market-data API (including
`/historical/*`) and the Iowa Environmental Mesonet. No keys, no accounts. An optional Kalshi API
key only raises the rate limit (see `src/pmdecide/kalshi.py`, `scripts/kalshi_auth_check.py`). Settled responses are
cached immutably under `data_cache/`, so reruns are free.

## Layout

```
src/pmdecide/
  kalshi.py, iem.py   public-API clients with immutable response caches
  weather.py          cities, bucket arithmetic, point-in-time forecast selection
  emos.py             EMOS and climatology baselines (interval likelihood)
  dataset.py          panel -> padded ladders with every causal forecast attached
  splits.py           walk-forward folds, embargo, lockbox
  metrics.py          log score, RPS, Brier, debiased ECE, date-block bootstrap, Diebold-Mariano
  baselines.py        Source, TemperedMarket, LogPool (incl. rolling windows): the bar to clear
  model.py            LadderNet: one distribution per ladder, learned log-pool + MLP, log score
  evaluation.py       the one walk-forward out-of-sample path both benchmark and backtest use
  backtest.py         taker + maker execution, Kalshi fees, ladder Kelly, trade ledger
  stats.py            stationary bootstrap, Newey-West, Deflated Sharpe, PBO (CSCV)
  shadow.py           live scoring of the frozen strategy, settlement, running report
  sports/             the same pipeline on MLB game winners
  api.py              typed Choice / Noul / Score interface over one distribution
scripts/              survey, data builds, label checks, benchmark; each writes results/
tests/                label arithmetic, no-leak invariants, scoring rules, API coherence
docs/                 plan, market selection, evaluation protocol
```

Apache-2.0.
