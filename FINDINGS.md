# Findings

Each finding states what was measured, on what data, and what it does and does not license.
Corrections are added beside the original, never in place of it.

## 1 · Market selection: weather highs (2026-10-04)

17 series, 6 categories, 40 sampled events each. Weather highs are the only category with a free
exogenous forecast, a synthetic-data source 100× the market's history, reproducible settlement and
room in the spread. Detail: `docs/01-market-selection.md`, `results/survey.json`.

## 2 · Labels are clean, after two repairs (2026-10-04)

NY, 9,644 markets, 1,873 events (`scripts/check_labels.py`, `results/label_check.json`):

- 14.5% of markets (all of 2021-22, a few weeks of early 2025) carry no strike fields; bounds are
  parsed from the rules text. Bucket arithmetic then reproduces Kalshi's `result` on **100%** of
  markets, API-sourced and parsed alike.
- 258 events (all 2021-22) are single or overlapping thresholds, not ladders. They are excluded
  from bucket-level scoring by an explicit partition check. Before that check, a single-market
  event that settled YES would have scored as a certain, correct prediction.
- Kalshi settlement = NWS CLI high on **1,545 of 1,546** days. The source switched to The Weather
  Company on **2026-08-14**; on the 51 days since, it has matched CLI on all 51.

## 3 · Gate 0 on NY: passes as written, and the edge has decayed to zero (2026-10-04)

`scripts/benchmark.py --cities NY`, walk-forward by quarter 2023-07 to 2026-06, 1,085-1,092
ladders per read time, identical rows for all eight predictors. Full tables: `results/benchmark.md`.

**As pre-registered:** the market + forecast log pool beats the market at every read time, CIs
excluding zero for 5 of 6 (read, forecast) pairs. At 08:00 on the day, pooling all sources gains
**+0.062 nats per ladder [+0.041, +0.082]**. The tempered market gains +0.002 [−0.001, +0.005], so the
gain is new information from the forecasts, not a recalibration of the market.

**By half-year, the same comparison (best pool vs market, 08:00 read):**

| Period | Δ log score | 95% CI |
|---|---:|---|
| 2023 H2 | **+0.224** | [+0.177, +0.270] |
| 2024 H1 | +0.124 | [+0.068, +0.179] |
| 2024 H2 | +0.105 | [+0.053, +0.155] |
| 2025 H1 | −0.035 | [−0.091, +0.016] |
| 2025 H2 | +0.001 | [−0.055, +0.042] |
| 2026 H1 | **−0.047** | [−0.081, −0.013] |

The day-before (16:00) read shows the same shape: +0.127 in 2023 H2, −0.042 in 2025 H1.

**Reading.** Through 2024 the NYC market underpriced the NWS's own forecasts. From 2025 it does not:
pooling public forecasts adds nothing, and the weights learned on earlier years now *hurt*
(2026 H1 CI excludes zero on the wrong side). The pooled PASS is carried entirely by 2023-24.

**Gate amendment (beside, not over, PLAN §3).** The gate as written pools all walk-forward rows, so
it cannot see decay. Added criterion: the gain must also be positive, CI excluding zero, on the
**most recent 12 months** before the lockbox. On NY this amended gate **fails** at every read time.

**What this does not say.** One city, the most liquid weather market on the exchange. Public point
forecasts in a two-parameter pool are the weakest form of the information; the six other cities
(wider spreads, less volume), intraday observations, NBM's spread, and a nonlinear model are all
untested. Those are next, and this result moves the prior against them.

## 4 · Labels on all seven cities (2026-10-04)

7,722 scored ladders across NY, CHI, MIA, AUS, LAX, DEN and PHIL: bucket arithmetic agrees with
Kalshi's `result` on 100% of ladder markets, every ladder settles exactly one bucket, zero failed
fetches. Two Kalshi records contradict themselves (`HIGHCHI-22APR02-T45`: settlement 47, ">45"
resolved NO; `HIGHCHI-21OCT01-T84`: settlement 84, ">84" resolved YES), likely post-settlement NWS
revisions. `result` is what paid, so it is the label; both are 2021-22 non-ladders and unscored.
One post-switch Miami day settled 5°F away from the NWS CLI value: the Weather Company regime is
not identical to CLI, and stays a monitored slice.

## 5 · Gate 0 on seven cities: the market priced in NBM, not GFS MOS (2026-10-04)

`scripts/benchmark.py`, 6,063-6,095 ladders per read time, walk-forward 2023-07 to 2026-06.

The decay seen on NY holds everywhere. Best pool vs market at 08:00, by half-year: +0.182, +0.113,
+0.089, then −0.012, −0.004, −0.021 from 2025 H1 on.

**On the last 12 months the two forecasts split:**

| Read | market + NBM | market + GFS MOS |
|---|---|---|
| 08:00 | −0.021 [−0.033, −0.010] | **+0.012 [+0.004, +0.020]** |
| 12:00 | −0.000 [−0.007, +0.007] | **+0.009 [+0.005, +0.014]** |
| 16:00 day before | −0.004 [−0.016, +0.007] | **+0.020 [+0.012, +0.026]** |

Reading: the market now fully prices the National Blend of Models, the guidance behind the public
weather.gov point forecast, and still underweights GFS MOS. The crowd anchors on the forecast it
can see. The amended gate passes on the pooled GFS result alone, at all three read times, so the
verdict does not rest on the lenient "any city" clause (42 per-city tests, where one false pass is
expected). The surviving gain is about a tenth of the 2023 edge.

## 6 · Taker backtest: an edge of about one tick, not robust (2026-10-04)

`scripts/backtest.py --execution taker`, 28 configurations (4 models × 7 sizings), nested
walk-forward selection, fixed $10k bankroll. Full tables: `results/backtest_taker.md`.

| Read | Nested PnL | Sharpe [95% CI] | Deflated Sharpe | PBO |
|---|---:|---|---:|---:|
| 08:00 | −$10,049 | −1.01 | 0.000 | 0.26 |
| 12:00 | +$11,071 | 0.47 | 0.005 | 0.20 |
| 16:00 day before | **+$37,459** | **1.67 [0.60, 2.67]** | 0.619 | 0.27 |

The day-before result is real in several ways: positive in every half-year (most of it in 2025-26,
matching §5), positive in all seven cities, Newey-West t = 2.84, every engine check passes, and
matched-turnover noise loses $24,416 over the same days. Attribution: +$95,867 alpha vs mid, −$37,326
spread, −$21,083 fees.

It is not believable as a strategy. **One tick of slippage turns +$21,914 into −$31,243**; 20%
participation or 10× size turn it deeply negative; realised edge is +1.7¢ per contract against +8.4¢
predicted (winner's curse); and it misses both overfitting bars (DSR 0.62 < 0.95, PBO 0.27 > 0.2).
The information is there; crossing the spread to act on it costs about all of it. The next test is
the one that stops paying the spread: maker execution with trade-through fills.

## 7 · Maker backtest: information is real, adverse selection is larger (2026-10-04)

`scripts/backtest.py --execution maker`, 17.0M prints over 40,553 markets (trade sums cover
99.3-99.8% of reported volume, 0 failed fetches), 32 configurations, nested selection. Quotes join or
improve the touch; fills only on later prints strictly through our price. Full tables:
`results/backtest_maker.md`.

| Read | Model as maker | Uninformed market maker | Matched noise | Sharpe [95% CI] |
|---|---:|---:|---:|---|
| 08:00 | −$12,477 | −$42,779 | −$29,195 | −1.02 [−2.25, +0.21] |
| 12:00 | −$34,665 | −$101,869 | −$34,834 | −2.31 [−3.71, −1.10] |
| 16:00 day before | −$8,071 | −$25,116 | −$12,141 | −0.91 [−2.20, +0.40] |

Attribution at 08:00: **+$57,946 of spread captured, −$70,423 alpha vs mid.** Resting orders are
filled when the price moves through them, i.e. when someone better informed is trading. The model's
information cuts that loss by roughly two thirds relative to quoting with no information, which is
the same information §5 measures; it does not cut it to zero. The conclusion holds at both fill
bounds (trade-through and 50% at-touch), with a 1.75¢ maker fee, without price improvement, and
gets far worse with longer-lived quotes (to the close: −$243,506), as stale quotes are picked off.

**Where this leaves the programme.** Public NWS guidance in a 2-4 parameter pool carries real,
measurable information (§5), worth about one tick per contract at the day-before read (§6). Taking
liquidity pays the spread away; providing it pays it away to adverse selection. Neither execution
style turns these probabilities into a robust, deflated-Sharpe-significant strategy. A better model
(G2: intraday observations, time-varying weights, a nonlinear learner) has to buy more than a tick
of edge to change that, and the backtest now exists to say whether it does.
