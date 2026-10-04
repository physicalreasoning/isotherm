# Evaluation protocol

What every number in this repo means, and what it cannot tell you.

## The question being scored

One row is one ladder: a (city, day, read time) triple. The model returns a probability for each
bucket; exactly one bucket settles YES. Read times are local wall-clock (`d1_16` = 16:00 the day
before, `d0_08` = 08:00, `d0_12` = noon), so a row means the same thing in every city and season.

## Identical rows

Every predictor is scored on exactly the same rows. A row enters the benchmark only if **every**
predictor has a forecast for it (`LadderSet.complete`, and the `scored` mask in `benchmark.py`).
Dropping rows per model is how leaderboards get quietly rigged; here a model that cannot answer a
row removes that row for everyone, and the row count is printed beside every result.

## Causality

| Input | Known at the read time because |
|---|---|
| market quotes | last hourly candle whose `end_period_ts` ≤ read time |
| GFS MOS | run public at `runtime + 5h` |
| NBM | run public at `runtime + 2h` |
| EMOS / climatology parameters | refit each month on CLI highs before the month, 2-day embargo |
| learned weights (pools, neural model) | walk-forward: fit only on rows before the fold, 2-day embargo |

`tests/test_weather.py` and `tests/test_eval.py` lock the point-in-time joins and the fold
boundaries down.

## Splits

- **Walk-forward**, quarterly folds from 2023-07-01, 2-day embargo, minimum 120 training dates.
  Predictions from all folds are concatenated and scored once.
- **Lockbox:** 2026-07-01 onward. Excluded from every fold and every selection decision. Scored
  once with `--lockbox`, with the configuration frozen in `PLAN.md`. It straddles the settlement
  switch from NWS CLI to The Weather Company, deliberately.

## Metrics

| Metric | Why |
|---|---|
| **Log score** (primary) | strictly proper; it is what training optimises; it punishes confident misses hardest, which is what loses money |
| RPS | buckets are ordered; a near miss should cost less than a far one |
| Brier | bounded, familiar, less sensitive to single tail events |
| **Debiased ECE** (Noul view) | calibration of every bucket as a yes/no question. Plain binned ECE is biased upward at these sample sizes (the market survey showed its point estimate below its own bootstrap CI), so the per-bin sampling variance is subtracted |
| Top-1 accuracy | intuition only; not proper, never used to choose anything |

## Inference

The **date** is the unit of independence: cities share weather systems, and the three read times of
a city-day share one outcome. All CIs are date-block bootstraps (1,000 resamples). Model-vs-market
comparisons also report Diebold-Mariano on per-date mean loss differences with a lag-1 Newey-West
variance.

## Controls every result is read against

- **Market**, normalised mid. The crowd. The primary comparison for every model.
- **Tempered market** (`p_mkt^w`). If a pool beats the market but not the tempered market, the gain
  came from fixing the market's own calibration, not from new information.
- **EMOS (GFS, NBM)** and **climatology**. Is there signal, and how much is the NWS's?
- **Log pools**. Two or three parameters. The real bar for anything with more parameters.
- **Untrained network** of the final architecture (added with G2). The `causal-jepa` lesson: a
  model that does not separate from its own initialisation has learned nothing.

## Slices

City, read time, settlement regime (`nws_cli` / `twc`), and from G2 on: season, forecast surprise,
volume tercile. A pooled gain driven by one city is reported as that.

## What this cannot tell you

- **Whether the edge is tradeable.** Log score against the mid ignores the spread you would pay and
  the depth you could fill. That is G4's backtest, with fees and a conservative fill model.
- **Whether it holds live.** Backfilled candles are not a live feed; G5 is four weeks of shadow
  scoring to measure that.
- **Anything about other venues or other contracts.** Seven cities, one exchange, one contract
  family.
