# 01 · Market selection

**Decision:** Kalshi daily high-temperature ladders, seven cities (NY, CHI, MIA, AUS, LAX, DEN, PHIL).
**Runner-up:** MLB / NBA / ATP game winners.
**Status:** decided on the survey below, conditional on Gate 0 (`docs/PLAN.md`), which can still reverse it.

## How this was chosen

A Jev-style model returns calibrated probabilities to typed questions. It can only be worth building
where something it sees is *not already in the price*. So the selection criteria are, in order:

1. **Independent resolved events.** The effective sample size. Monthly macro prints are out on this alone.
2. **A free exogenous information source** the model can read and the market might under-use.
3. **A synthetic-data source** to pretrain on, as Jev does, that is far larger than market history.
4. **Objective settlement** that we can reproduce, so labels are not a modelling problem.
5. **Enough liquidity to trade**, but not so much that the price is the forecast.

The trap that sank `causal-jepa` is criterion 2: on a market whose underlying is itself a liquid
price (crypto, index, commodity futures), the mid already is the martingale forecast, and there is
nothing for a model to add from public data.

## What was measured

`scripts/survey_markets.py`, 40 random settled events per series from the most recent 1,000, quotes
read from hourly (or 1-minute, for short-lived markets) candles at 50% and 90% of market life.
Raw output with CIs: `results/survey.json`. Calibration slope is `b` in
`P(yes) = sigmoid(a + b·logit(mid))`; `b > 1` means the market is underconfident, `b < 1` overconfident.

| Series | Category | Settled events | Since | Median volume / event | Two-sided @ mid-life | Median spread | Slope @ 0.5 life [95% CI] |
|---|---|---:|---|---:|---:|---:|---|
| KXHIGHNY | weather | 1,881 | 2021-08 | 62,711 | 65% | 9¢ | 0.72 [0.25, 1.29] |
| KXHIGHCHI | weather | 1,869 | 2022-12 | 39,104 | 70% | 9¢ | **1.84 [1.30, 2.71]** |
| KXHIGHLAX | weather | 637 | 2025-04 | 148,875 | 82% | 3¢ | 0.78 [0.32, 1.32] |
| KXHIGHMIA | weather | 1,241 | 2023-08 | 37,332 | 66% | 10¢ | 1.00 [0.55, 1.69] |
| KXRAINNYC | weather | 869 | | 1,986 | 53% | 9¢ | 1.63 [0.84, 250] |
| KXWTI | commodities | 849 | 2022-12 | 999 | 33% | 4¢ | 0.39 [-0.53, 1.04] |
| KXGOLDD | commodities | 107 | 2026-05 | 138,892 | 100% | 3¢ | 0.14 [-0.08, 0.40] |
| KXGOLD15M | commodities | 4,449 | 2026-07 | 312,370 | 100% | 1¢ | 0.92 [0.32, 1.64] |
| KXMLBGAME | sports | 4,657 | | 3,166,296 | 100% | 2¢ | 1.81 [-0.57, 4.44] |
| KXNBAGAME | sports | 1,449 | | 5,409,934 | 100% | 2¢ | 0.90 [0.31, 1.78] |
| KXATPMATCH | sports | 4,781 | | 2,005,681 | 100% | 1¢ | 1.38 [0.51, 4.69] |
| KXFEDDECISION | economics | **28** | 2023-05 | 2,648,582 | 52% | 2¢ | 2.10 [1.17, 45.7] |
| KXCPIYOY | economics | **46** | | 167,612 | 74% | 4¢ | 1.04 [0.61, 1.73] |
| KXAAAGASD | economics | 217 | 2023-09 | 137,775 | 81% | 4¢ | 1.26 [0.95, 1.89] |
| KXINX | financials | 1,129 | 2022-12 | 89,205 | 50% | 11¢ | 0.05 [-0.52, 0.62] |
| KXINXU | financials | 3,285 | 2023-06 | 99,595 | 90% | 5¢ | 0.67 [0.39, 1.31] |
| KXBTCD | crypto | 8,000+ | 2025-09 | 1,610,096 | 97% | 1¢ | 1.05 [0.78, 1.54] |

**What the survey can and cannot say.** Forty events is enough to rank liquidity and sample size,
and not enough to rank market efficiency: most slope intervals contain 1, and ECE at n≈100 is
biased upward (its point estimate sits below its own bootstrap interval). The survey is therefore
used for criteria 1, 4 and 5. Criterion 2 is settled by Gate 0, which asks the sharper question
directly: does a free forecast add information the market price lacks?

## Scoring

| | Weather highs | Sports games | Commodities / index / crypto | Macro prints |
|---|---|---|---|---|
| Independent events | ~8,200 city-days, 7 cities | ~11k games, 3 leagues | many, but one underlying each | 28-217 |
| Free exogenous info | **NWS MOS + NBM forecasts, intraday ASOS obs** | box scores free; the strong signal (book odds) is paid | the underlying price, which *is* the forecast | consensus surveys |
| Synthetic data | **12+ yrs × hundreds of stations of forecast/outcome pairs** | game simulators, weak | GBM / jump simulators (`causal-jepa` tried) | none |
| Settlement | NWS CLI, reproduced exactly; now The Weather Company | official result | exchange index | BLS / Fed |
| Spread at mid-life | 3-10¢ (room for a model) | 1-2¢ (efficient) | 1-11¢ | 2-4¢ |
| Typed-question fit | **ladder = Choice, strike = Noul, high = Score** | Noul only | ladder | ladder |

Weather is the only column with a strong answer on every row, and its ladder structure is a
one-to-one match for Jev's three primitives. Sports is the runner-up: deepest volume, but the
spreads say it is the most efficient category on the exchange, and the information that would beat
it is not free.

## Verified facts this rests on (2026-10-04)

- `GET /historical/*` serves every market settled before 2026-08-05, back to each series' first
  event. The rolling purge our earlier pm-jepa project had to race is gone.
- Bucket arithmetic in `isotherm.weather.bucket_interval` reproduces Kalshi's `result` on every
  market checked (48/48 in the smoke panel; the full panel re-checks every row).
- NWS CLI for KNYC 2026-08-03 = 80°F = Kalshi `expiration_value` for `KXHIGHNY-26AUG03`.
- **Settlement-source change:** contracts through at least 2026-08-03 settle on the NWS Daily
  Climatological Report; by 2026-10-03 they settle on The Weather Company (same CLINYC station).
  Labels therefore always come from Kalshi's settlement, and the switch is an evaluation slice.
- GFS MOS archive available from at least 2012, NBM (with spread fields) from 2021, CLI from 2015,
  all free from Iowa Environmental Mesonet.

## Not chosen, and why it is not "ML weather forecasting"

An earlier framing, ML weather forecasting on ERA5 / WeatherBench 2, was rejected for the world-model
project. This is a different problem: we do not forecast the atmosphere. We take the NWS's own
operational forecasts as inputs and model **the market's decision problem**: how much to trust the
forecast against the crowd, at a given time, for a given city and season. If it turns out that the
only value is in better weather forecasting, Gate 0 will say so and we stop.
