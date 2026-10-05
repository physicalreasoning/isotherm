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
- **Market-label control** (added with G2): the same network trained on labels sampled from the
  market's own distribution. Its best possible fit is the market, so it can only beat the market
  if the pipeline leaks the outcome. (An untrained copy is not a useful control here: the network
  is initialised to equal the market.)

## Slices

City, read time, settlement regime (`nws_cli` / `twc`), and from G2 on: season, forecast surprise,
volume tercile. A pooled gain driven by one city is reported as that.

## Backtest (`scripts/backtest.py`)

Proper scores say whether the probabilities are better. The backtest asks whether they are
better **by more than it costs to act on them**.

### Execution

| | Taker | Maker |
|---|---|---|
| Price | the ask (YES) or 1 − bid (NO) at the read time; `slip` ticks worse in sweeps | join the touch, or improve it by 1¢ when the spread is ≥ 2¢ |
| Fill | immediate, capped at `participation` × contracts traded in the bucket after the read | only by later prints from the opposite taker side **strictly through** our price, within `horizon` |
| Fees | Kalshi quadratic taker fee, rounded up to the cent per order | none for these series (`fee_type: quadratic`); 0.0175 in sweeps |
| Why this is conservative | no queue priority, no price improvement, no maker rebates | a print through our level fills any order resting there, so no queue model is needed; and those are exactly the fills that arrive when the price moves against us, so adverse selection is modelled for free |

Positions are held to settlement. Post-read volume is used only as a capacity cap, never as a
signal.

### Sizing

*Threshold:* every instrument with EV per contract above θ after fees, at a fixed stake.
*Ladder Kelly:* the buckets are mutually exclusive and exhaustive, so a ladder is one bet. Holdings
in every YES and NO contract are chosen jointly to maximise E[log wealth] under the model (a concave
program), then scaled by a Kelly fraction to absorb the model's own estimation error.

### Selection, and how we avoid fooling ourselves

- **Headline = nested walk-forward.** Each quarter trades the configuration with the best Sharpe on
  *earlier quarters only*; the first quarters use a pre-registered default. This is the number that
  could actually have been earned. The full-period best configuration is shown only as a ceiling.
- **Deflated Sharpe** (Bailey & López de Prado 2014) for the number of configurations tried and the
  dispersion of their Sharpes, with skew and kurtosis. Believe it at ≥ 0.95.
- **PBO via CSCV** (Bailey et al. 2017): over every symmetric split of the history, how often does
  the in-sample winner land below the median out of sample? Believe the selection at ≤ 0.2.
- Sharpe CIs by **stationary bootstrap** (weather persists for days), mean daily PnL by
  **Newey-West t**.

### Engine checks (each must hold before any PnL is read)

| Check | Must |
|---|---|
| Oracle (true outcome as the model) | never lose a trade |
| Coherent in-spread market distribution as the model (taker) | make zero trades |
| Uninformed market maker quoting around that distribution (maker) | is the bar a maker strategy must beat, not zero |
| Noise around the market with matched turnover | lose roughly what it pays in costs |

### Diagnostics

- **Attribution:** PnL = alpha vs mid + spread paid + fees. Tells you whether information is
  missing or merely too expensive to act on.
- **Edge realisation:** ex-ante EV per contract against realised PnL per contract, by quantile.
  Realised far below predicted is the winner's curse: trading where the model disagrees most with
  the market also selects the model's errors.
- **Robustness:** slippage, fee multiplier, participation, size, fill rule, order horizon.
- **By period and city:** a pooled profit carried by one half-year or one city is reported as that.

## What this cannot tell you

- **What a live order would actually get.** Hourly candles carry no depth, and trade-through fills
  ignore queue position at our own level. The maker model is a lower bound on fills; the touch
  variant an upper bound. Only G5's shadow trading measures the truth.
- **Whether it holds live.** Backfilled candles are not a live feed; G5 is four weeks of shadow
  scoring to measure that.
- **Anything about other venues or other contracts.** Seven cities, one exchange, one contract
  family.
