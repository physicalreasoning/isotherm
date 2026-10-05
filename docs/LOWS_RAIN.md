# Daily lows and rain (issue #5)

**Decision.** Daily low-temperature ladders: modelled, and the most promising result in the repo
so far, on a short history. Rain: surveyed, not modelled yet.

## Survey (`scripts/lows_survey.py`, `results/lows_survey.json`)

Same method as `scripts/survey_markets.py`: 40 random settled events per series, quotes at mid-life.

| Series | Settled events | Since | Median volume / event | Markets / event | Median spread |
|---|---:|---|---:|---:|---:|
| KXLOWTNYC | 295 | 2025-12-14 | 29,648 | 6 | 12¢ |
| KXLOWTCHI | 296 | 2025-12-14 | 28,370 | 6 | 8¢ |
| KXLOWTMIA | 296 | 2025-12-14 | 20,566 | 6 | 14.5¢ |
| KXLOWTAUS | 296 | 2025-12-14 | 21,924 | 6 | 12¢ |
| KXLOWTLAX | 295 | 2025-12-14 | 19,344 | 6 | 12¢ |
| KXLOWTDEN | 296 | 2025-12-14 | 21,248 | 6 | 11¢ |
| KXLOWTPHIL | 296 | 2025-12-14 | 13,722 | 6 | 13¢ |
| KXHIGHNY (control) | 1,882 | 2022-12-23 | 74,180 | 6 | 9¢ |
| KXRAINNYC | 869 | | 1,986 | 1 | 9¢ |
| KXRAIN | 77 | 2026-07-16 | 557,423 | 20 | 2¢ |
| KXRAINNYCM | 32 | | 71,475 | 5 | 7.5¢ |
| KXRAINCHIM | 13 | | 94,468 | 7 | 5¢ |
| KXRAINWKND | 7 | | 72,314 | 23 | 17.5¢ |

Lows settle on the same seven stations as the highs (CLINYC, CLIMDW, CLIMIA, CLIAUS, CLILAX, CLIDEN,
CLIPHL), first on the NWS Climatological Report and later on The Weather Company. Same quadratic fee
schedule (multiplier 1). Each series has about 300 events: a third of the highs' volume per event,
wider spreads, and only since December 2025.

## Rain verdict

Not modelled. A free forecast exists (MOS and NBM probability of precipitation), so rain is
modelable in principle, but no series has both liquidity and history: the daily NYC binary trades
about 2,000 contracts a day; the multi-city KXRAIN ladder is liquid (2¢ spreads) but has 77 events
since July 2026; the monthly and weekend series have 7 to 32 events. Revisit KXRAIN once it has
about a year of history.

## Lows: data and labels (`scripts/lows_build_panel.py`, `scripts/lows_check_labels.py`)

Point-in-time panel at 16:00 and 22:00 local the evening before, from hourly candles: 2,068 events,
24,812 rows, 0 failed fetches. Labels from Kalshi `result`.

- Bucket arithmetic reproduces `result` on 100% of ladder markets; every ladder settles exactly one
  bucket; one Miami event is not a ladder and is excluded.
- Settlement = NWS CLI low on every matched day except two (Austin and Philadelphia, each 3°F),
  under both settlement regimes.
- Forecasts: GFS MOS and NBM overnight minimum (7pm to 8am LST, reported at 12Z of the morning it
  ends), public only after the usual lags. The settled value is the calendar-day minimum, which a
  late cold front can set near midnight; EMOS absorbs the average gap.

**Calendar, fixed before scoring.** The series start on 2025-12-14, so the weather calendar has no
usable fold. Lows use monthly walk-forward folds from 2026-02-01 (at least 45 training days, 2-day
embargo) and their own lockbox from 2026-09-01, left sealed. The "last 12 months" slice of the
amended gate is the whole scored period.

## Gate 0 (`scripts/lows_benchmark.py`, `results/lows_benchmark.md`)

About 1,480 ladders per read, 2026-02-01 to 2026-08-31.

| Read | market + GFS MOS | market + NBM | tempered market alone |
|---|---|---|---|
| 16:00 | +0.0085 [−0.0022, +0.0193] | −0.0039 [−0.0141, +0.0064] | +0.0077 [+0.0015, +0.0137] |
| 22:00 | +0.0088 [−0.0003, +0.0178] | −0.0033 [−0.0127, +0.0057] | |

- **As registered: not passed.** No pooled CI excludes zero.
- **Amended: passes only on the per-city clause** (Austin and Los Angeles at both reads). That is
  28 per-city tests, where one false pass is expected by chance.
- The tempered market alone captures most of the pool's gain. The market's own calibration is off
  (debiased ECE 0.018), and fixing it is worth more than the forecasts. NBM, as for highs, adds
  nothing; GFS adds about 0.001 nats on top of tempering.

## Taker backtest (`scripts/lows_backtest.py`, `results/lows_backtest.md`)

Run because the amended gate passes as computed. Existing engine and protocol unchanged: 28 configs,
nested monthly selection, Kalshi fees, 5% participation cap.

| Read | Nested PnL | Sharpe [95% CI] | NW t | Deflated Sharpe | PBO | Noise, same turnover |
|---|---:|---|---:|---:|---:|---:|
| **16:00** | **+$13,384** | **6.12 [3.08, 9.30]** | 4.24 | **0.980** | **0.06** | +$615 |
| 22:00 | +$5,450 | 3.49 [0.68, 6.16] | 2.45 | 0.675 | 0.31 | +$623 |

The 16:00 strategy is the first result in this repo to clear both overfitting bars (DSR ≥ 0.95,
PBO ≤ 0.2). Over 212 days it made $13,384 on a $10k paper bankroll, realised 5.1¢ per contract
against 3.7¢ expected, five of seven cities positive (Chicago and Miami slightly negative),
and the main config keeps +$7,293 at 2¢ of slippage. Engine checks pass: the oracle never loses,
the in-spread market never trades.

**Why this is not yet a strategy.**
- Seven months of a market that launched in December 2025, one cycle of seasons. The highs showed
  exactly this pattern in 2023 and decayed to zero by 2025.
- Noise with matched turnover is slightly profitable here (+$615), and so is trading the normalised
  mid (+$819): part of the edge is a young, miscalibrated market rather than forecast information,
  which matches Gate 0.
- Capacity is small: about 20,000 contracts per event; 1% participation leaves $3,262.
- The lows lockbox (2026-09-01 onward) is unscored. Scoring it once, with this configuration frozen
  and the criteria written down first, is the next step, followed by live shadow scoring.
