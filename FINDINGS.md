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
