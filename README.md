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
[docs/EVALS.md](docs/EVALS.md); latest leaderboard in [results/benchmark.md](results/benchmark.md).

| Gate | | Status |
|---|---|---|
| Survey | which market is worth modelling | **done:** weather highs, 7 cities, ~8,200 city-days |
| G0 | does a free forecast add information the market lacks | running |
| G1-G5 | baselines, model, synthetic pretraining, backtest, live shadow | not started |

## Reproduce

```bash
uv sync
uv run scripts/survey_markets.py --events 40   # market selection, ~5 min cold, seconds cached
uv run scripts/fetch_forecasts.py              # GFS MOS, NBM, NWS CLI from IEM (slow, polite)
uv run scripts/build_weather_panel.py          # point-in-time Kalshi ladders, ~50k calls, hours
uv run scripts/benchmark.py                    # G0 verdict + baseline leaderboard
uv run pytest
```

Everything uses unauthenticated public endpoints: Kalshi's market-data API (including
`/historical/*`) and the Iowa Environmental Mesonet. No keys, no accounts. Settled responses are
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
  baselines.py        Source, TemperedMarket, LogPool: the bar the model must clear
  api.py              typed Choice / Noul / Score interface over one distribution
scripts/              survey, data builds, label checks, benchmark; each writes results/
tests/                label arithmetic, no-leak invariants, scoring rules, API coherence
docs/                 plan, market selection, evaluation protocol
```

Apache-2.0.
