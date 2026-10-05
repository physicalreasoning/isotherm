# Findings

Each finding states what was measured, on what data, and what it does and does not license.
The learned model is called isotherm here; raw result files from before the rename label it
`LadderNet`, its working name.
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

## 8 · G2: isotherm, observations, time-varying weights (2026-10-04)

**Model.** `isotherm.model.isotherm`: per-bucket score = learned log-pool of every causal source
(market, EMOS-GFS, EMOS-NBM, EMOS-NBM conditioned on today's observed max, climatology) plus an
MLP correction over bucket and context features; softmax over the ladder; trained on the log score
with sample weights halving every 365 days; initialised to equal the market; 5-seed ensemble.
New inputs: hourly METAR maximum so far in the NWS climate day (midnight-midnight local *standard*
time), which bounds the settled high from below (CLI ≥ round(hourly max) − 1 on every day with a
settlement value); rolling 365-day pools.

**Bug caught before it reached a result.** pandas 3 stores datetimes in microseconds, so
`astype("int64") // 10**9` produced timestamps 1000× too small and the observation window spanned
all of history (100% observation coverage at the day-before read, which must be 0%). Fixed with a
resolution-independent conversion and regression tests.

**Benchmark** (`results/benchmark_g2.md`), Δ log score vs market:

| Read | isotherm, all periods | best simple pool | isotherm, last 12 months | Control |
|---|---|---|---|---|
| 08:00 | **+0.071** [+0.062, +0.081] | +0.054 | +0.011 [+0.002, +0.018] | −0.002 |
| 12:00 | **+0.033** [+0.027, +0.039] | +0.018 | +0.009 [+0.003, +0.014] | +0.001 |
| 16:00 day before | **+0.045** [+0.036, +0.054] | +0.039 | +0.015 [+0.007, +0.022] | −0.001 |

isotherm is the best model at every read and the best calibrated (debiased ECE 0.004-0.007 vs the
market's 0.013-0.020), and unlike every pool it is positive in **every** half-year, though the
2026 H1 gain is thin (+0.006 to +0.013). The control, the same network trained on labels sampled
from the market's own distribution, scores within ±0.002 of the market, so the gain is learned from
outcomes, not leaked by the pipeline. (A first control that shuffled labels across ladders was
flawed: it learned a prior over bucket index and scored −0.28 to −0.64; replaced.)

**Backtest** (`results/backtest_g2.md`), nested selection over 28 configs per execution style:

| Read · execution | Nested PnL | Sharpe [95% CI] | DSR | PBO |
|---|---:|---|---:|---:|
| 08:00 · taker | +$11,884 | 1.21 | 0.330 | 0.61 |
| 08:00 · maker | +$1,629 | 0.13 | 0.002 | 0.29 |
| 12:00 · taker | +$592 | 0.37 | 0.139 | 0.47 |
| 12:00 · maker | −$24,577 | −2.10 | 0.000 | 0.00 |
| **16:00 day before · taker** | **+$22,122** | **2.05 [0.81, 3.27]** | **0.849** | 0.26 |
| 16:00 day before · maker | −$2,419 | −0.32 | 0.000 | 0.31 |

The day-before taker strategy is the first result that survives costs: Newey-West t 3.17; most of
its profit in 2025 H2 and 2026 H1 ($18,018 of $22,122), so it is not the decayed 2023 edge; positive
in six of seven cities, losing only in NY, the most liquid; realised edge 2.6¢ of 4.8¢ predicted.
The configuration nested selection settles on is the market+GFS pool trading only at ≥ 4¢ of EV,
and it survives +1¢ slippage (+$6,513), +2¢ (+$4,516), 1.5× fees, 20% participation and 10× size
(+$61,210, Sharpe 1.71). The G1 version of this strategy died at +1¢.

**Verdict.** Close to the bar, not over it: DSR 0.85 < 0.95 and PBO 0.26 > 0.2. The one remaining
honest test is the lockbox (2026-07-01 onward, about 640 ladders per read), scored once with the
configuration frozen as above. It has not been run.

## 9 · Lockbox: pre-registration (written and pushed before any lockbox number was computed)

**Strategy, frozen.** Read 16:00 local the day before; taker execution; configuration
`pool · market+GFS · kelly 0.25`, chosen by the same rule nested selection uses every quarter
(best Sharpe on all history before the test period); it is also the config nested selection
picked for the last pre-lockbox quarter. Log pool of market + EMOS-GFS with per-read weights fit
on every ladder before 2026-06-29 (2-day embargo); joint ladder Kelly at 0.25; $10,000 bankroll
over 7 slots; 5% participation cap; Kalshi quadratic fees; held to settlement.

**Data.** Every settled ladder from 2026-07-01 to 2026-10-03, all seven cities. Never used for any
fit, selection or design decision. The period contains the settlement switch to The Weather
Company (2026-08-14) and the one Miami day that settled 5°F from the NWS value.

**Criteria.**
- *Pass:* mean daily PnL > 0 with Newey-West t > 1.645 (one-sided 5%).
- *Consistent but underpowered:* PnL > 0, t ≤ 1.645.
- *Fail:* PnL ≤ 0.

Secondary, reported regardless: PnL at +1¢ slippage; isotherm Δ log score vs market at this read,
CI by date; engine checks (oracle never loses, in-spread market never trades) and matched-turnover
noise. About 95 days and ~640 ladders: the interval will be wide, and a pass on this sample is
evidence, not proof.

## 10 · Lockbox result: passes as registered, marginally, and shrinking month by month (2026-10-04)

`scripts/lockbox.py`, run once against the criteria in §9 (commit b455496). Raw: `results/lockbox.json`.

| | |
|---|---|
| Verdict | **PASS** by the registered rule: Newey-West t **1.77** > 1.645 |
| PnL | **+$1,851** over 95 days, 664 ladders, 1,925 trades, hit rate 80.4% |
| Sharpe | 3.87, stationary-bootstrap 95% CI **[−0.19, 8.95]** (two-sided interval includes zero) |
| +1¢ slippage | +$462 |
| EV vs realised per contract | +2.2¢ vs +1.3¢ |
| Engine checks | oracle 0 losing trades; in-spread market 0 trades; matched-turnover noise −$2,703 |
| Scoring, Δ log score vs market | market+GFS pool **+0.014 [+0.001, +0.027]**; isotherm +0.013 [−0.004, +0.027]; control −0.001 |

By city: six of seven positive (NY +$666, MIA +$374, CHI +$339, PHIL +$219, LAX +$210, AUS +$67),
DEN −$22. **By month: July +$1,029, August +$517, September +$246** (October, 3 days: +$60). By
settlement regime: +$1,580 under NWS CLI, +$272 under The Weather Company (similar number of days).

**Reading.** The strategy found and frozen on 2023-2026 data made money on three months it had never
seen, beat noise with the same turnover by $4,554, survived a tick of slippage, and the pool's
probabilities beat the market's on held-out outcomes with a CI excluding zero. That is the pass.
It is a narrow one on 95 days, and the monthly PnL halves each month and falls after the switch to
The Weather Company. Three months cannot tell renewed decay, the regime change and noise apart.
The honest next step is G5: shadow-score it live on new days, with the decay as the thing to watch,
before any capital is involved.

## 11 · Sports (MLB game winners): no edge (2026-10-04)

Full record: `docs/SPORTS.md`; raw: `results/sports_benchmark.json`, `results/sports_backtest.{md,json}`.
4,484 games linked to the MLB Stats API (96.3% of 4,658 settled; drops counted by reason), Kalshi
result = official result on 100% of rows, 5.21M pre-game prints. Elo (tuned on 2016-19) plus
point-in-time starting-pitcher quality, frozen before Kalshi's first MLB game.

Gate 0 fails as registered and as amended: the best blend is within ±0.001 nats of the market at
24h, 3h and 15min before first pitch, every CI spanning zero; Elo + starters alone is 0.001-0.003
worse than the market. No taker or maker cell passes (DSR ≤ 0.14, PBO 0.34-0.49); the best, the
3h maker at +$3,826, has a Sharpe CI including zero and was negative in 2026 H2. With 1¢ spreads and
about 1.2M contracts per game, MLB on Kalshi prices everything free public data can see. The
survey's prediction (§1: "the most efficient category on the exchange") holds.

## 12 · Same-day reads with finer data, and a better maker policy (2026-10-05)

New inputs: a 14:00 read; the day's max so far from the IEM ASOS 1-minute archive at 5-minute
sampling (10-minute reporting lag; the settled high is at or above round(5-minute max) − 1 on
99.8-99.9% of days); and NBM's forecast max over the rest of the climate day from the latest run
public at the read. Day-before reads see none of these (verified: zero rows with same-day inputs).
Caveat: IEM receives the 1-minute archive with a delay, so a live system needs a real-time
5-minute feed to use this.

isotherm, Δ log score vs market (`results/benchmark_g2.md`):

| Read | all periods | last 12 months | ECE | control |
|---|---|---|---|---|
| 16:00 day before | +0.044 [+0.035, +0.053] | +0.014 [+0.006, +0.022] | 0.003 | −0.000 |
| 08:00 | +0.070 [+0.061, +0.080] | +0.009 [+0.001, +0.017] | 0.004 | −0.001 |
| 12:00 | +0.035 [+0.029, +0.041] | +0.010 [+0.004, +0.015] | 0.005 | +0.000 |
| **14:00** | **+0.053 [+0.045, +0.061]** | **+0.017 [+0.010, +0.025]** | 0.005 | +0.001 |

The 14:00 read carries the largest recent gain of any read, and isotherm is positive in every
half-year at every read.

Maker execution now also tries pulling quotes when the next GFS MOS run goes public, and every
maker headline reports the same picks under at-touch fills as an upper bound
(`results/backtest_g2.md`). Queue position itself is not estimable without order-book depth
history, which Kalshi does not publish.

| Read · execution | Nested PnL | Sharpe | DSR | PBO | maker at-touch bound |
|---|---:|---:|---:|---:|---:|
| 16:00 day before · taker | +$22,311 | 2.06 | 0.865 | 0.24 | |
| 16:00 day before · maker | +$2,985 | 0.42 | 0.000 | 0.40 | +$4,820 |
| 08:00 · taker | +$16,071 | 1.51 | 0.540 | 0.45 | |
| 08:00 · maker | +$10,108 | 0.82 | 0.023 | 0.21 | +$15,843 |
| 12:00 · taker | +$727 | 0.37 | 0.211 | 0.48 | |
| 14:00 · taker | +$2,316 | 1.14 | 0.421 | 0.12 | |
| 12:00 and 14:00 · maker | −$23,991, −$30,573 | | | | −$21,312, −$26,753 |

**Reading.** Finer same-day information sharpens the probabilities most at 14:00, but trading
barely moves: late-day books are thin (322 taker trades in three years at 14:00) and resting
orders in the afternoon are still picked off. The day-before taker strategy remains the only
candidate, essentially unchanged. The cancel-on-new-run policy was selected in one quarter of one
read; it is not the fix for adverse selection here.

## 13 · Daily lows: lockbox pre-registration (written and pushed before any lockbox number)

Context: `docs/LOWS_RAIN.md`. Lows gate 0 fails as registered and passes only per city (Austin,
Los Angeles); the 16:00 taker backtest clears both overfitting bars (DSR 0.980, PBO 0.06) on 212
days of a market launched 2025-12-14, and matched-turnover noise is slightly profitable too.

**Strategy, frozen.** Read 16:00 local the day before; taker; `pool · market+GFS · θ 0.01`
(log pool of market and EMOS on the GFS MOS overnight min, threshold sizing at 1¢ EV, $100 per
instrument). It is both the full-period best and the nested pick for each of the last three
months. Pool weights and EMOS fit on every lows ladder before 2026-08-30 (2-day embargo).

**Data.** Every settled lows ladder from 2026-09-01 on, all seven cities, never used for any fit
or choice. About five weeks: underpowered by construction.

**Criteria.** Pass: mean daily PnL > 0 with Newey-West t > 1.645. Consistent but underpowered:
PnL > 0, t ≤ 1.645. Fail: PnL ≤ 0. Reported regardless: log score vs market, matched-turnover
noise, engine checks.

## 14 · Daily lows lockbox: probabilities hold, the money does not (2026-10-05)

`scripts/lows_lockbox.py`, run once against §13 (commit c0d3456). The rebuilt panel first
reproduced the pre-lockbox backtest exactly (+$13,384, DSR 0.980, PBO 0.06). Raw:
`results/lows_lockbox.json`.

| | |
|---|---|
| Verdict | consistent but underpowered: **+$36** over 34 days, 131 trades, Newey-West t 0.06 |
| Sharpe | 0.19, 95% CI [−5.57, 7.25] |
| Log score vs market | **+0.019 [+0.001, +0.035]** |
| Matched-turnover noise / normalised mid | −$454 / −$366 (both were slightly profitable in-sample) |
| Engine checks | oracle never loses; in-spread market never trades |

**Reading.** The model's probabilities still beat the market on held-out lows, but the trading
edge is gone: about $1 a day against $63 a day in the backtest. The placebos flipping from
profit to loss say the in-sample PnL came largely from a newly launched market's miscalibration,
and that has been corrected. It is the highs story (§3, §10) in five weeks. Lows are not added
to live trading.

## 15 · G3: synthetic pretraining helps only when real data is scarce (2026-10-05)

Full record: `docs/G3.md`; raw: `results/g3_learning_curve.{json,md}`. 92,452 synthetic
day-before ladders from 55 ASOS stations that Kalshi does not list (none of the seven settlement
stations, enforced by a test), with a market simulator fit to the real panel. The simulator
matches the real market's log score gap to EMOS-NBM (−0.110 vs −0.109), its overround (1.065 vs
1.050) and spread (4.0¢ vs 4.5¢).

| Real training data | Pretrained minus none, Δ log score |
|---|---|
| 10% | **+0.017** [+0.013, +0.022] |
| 25% | +0.002 [−0.002, +0.005] |
| 50% | −0.006 [−0.011, −0.002] |
| 100% | −0.005 [−0.009, −0.001] |

The gate (PLAN §6) fails on both clauses: pretrained on 50% of real data is 0.009 worse than no
pretraining on 100%, and at 100% pretraining slightly hurts. Pretraining is not added to
isotherm. It is worth keeping for new contracts with little history, where it doubles the gain at
10% data. Caveat: the pretrained control is +0.005, not zero, so up to that much of any pretrained
gain may come from the synthetic stage rather than real outcomes; it can only flatter the
pretrained arms, so it does not change the verdict.

## 16 · Transformer over ladder buckets: pre-registration (written and pushed before any result)

**Question.** Does attention across a ladder's buckets beat the per-bucket MLP in isotherm?

**Model, fixed now.** Identical inputs, features, training loop, recency weighting, early
stopping and five seeds as isotherm; only the network changes. Each bucket is a token
(its features and source log-probabilities, projected to d = 64), plus one context token
(city, season, lead, forecast spread and disagreement). Two pre-norm transformer encoder layers,
4 heads, feed-forward 128, dropout 0.1, padding masked. The output per bucket is the same
learned log pool as isotherm plus a zero-initialised linear head, so the untrained model equals
the market. Learning rate 1e-3, otherwise isotherm's settings. No tuning after this commit.

**Gate.** Paired on identical walk-forward rows, transformer minus isotherm, log score gain on the
last 12 months before the lockbox (2025-07-01 to 2026-06-30), 95% date-block bootstrap.
- *Pass:* the difference is above zero with the CI excluding zero at 3 or more of the 4 read
  times, and the transformer's market-label control stays within ±0.005 of the market.
- *Otherwise* the MLP stays and this is recorded as a negative result.
The lockbox is not used.

## 17 · Bucket transformer: fails its gate (2026-10-05)

`scripts/transformer_gate.py` against §16 (pre-registered in commit fd6d027). Raw:
`results/transformer_gate.json`, `results/benchmark_transformer.md`.

Transformer minus isotherm, log score gain on the last 12 months before the lockbox, paired on
identical rows, 95% date-block CI:

| Read | Difference | CI |
|---|---|---|
| 08:00 | +0.0016 | [−0.0012, +0.0044] |
| 12:00 | +0.0004 | [−0.0022, +0.0031] |
| 14:00 | −0.0003 | [−0.0026, +0.0020] |
| 16:00 day before | **+0.0040** | **[+0.0010, +0.0069]** |

One read of four clears zero against the three required, so **the gate fails and the per-bucket
MLP stays**. The transformer's market-label control sits within −0.0004 to +0.0008 of the market,
so the comparison is clean. Attention across a ladder's buckets lands within a few thousandths of
the MLP: with about 6,000 ladders per read time and the edge limited by information rather than
capacity, the extra machinery has little to work with.

The one clear difference falls at the read the trading strategy uses. Acting on it now would be
selection after seeing the result; it can only become a new pre-registered test of its own.

## 18 · A larger transformer: pre-registration (2026-10-05)

§17 leaves open whether the transformer was too small. This scales it up about eightfold (width
128, four layers, feed-forward 256; roughly 0.5M parameters against 0.07M) and keeps everything
else fixed: same features, rows, walk-forward folds, five seeds, learning rate and early stopping.
Suite `transformer-large`, scored by `scripts/transformer_gate.py --large`.

**Gate.** Identical to §16: transformer-L minus isotherm, paired, last 12 months before the
lockbox, 95% date-block bootstrap. Pass needs the CI above zero at 3 or more of the 4 read times,
with transformer-L's market-label control within ±0.005 of the market. The lockbox is not used.

This is the second architecture tried on the same out-of-sample rows, so a pass would count as
weaker evidence than §16's would have, and would need confirming on data after 2026-10-05 before
the MLP is replaced.

## 19 · Larger transformer: fails its gate, but scale helps (2026-10-05)

`scripts/transformer_gate.py --large` against §18 (pre-registered in commit 83b3a3e). Raw:
`results/transformer_large_gate.json`, `results/benchmark_transformer_large.md`.

Transformer-L minus isotherm, log score gain on the last 12 months before the lockbox, paired on
identical rows, 95% date-block CI, with §17's small transformer for comparison:

| Read | Transformer-L | CI | Small (§17) |
|---|---|---|---|
| 08:00 | **+0.0064** | **[+0.0001, +0.0129]** | +0.0016 |
| 12:00 | +0.0012 | [−0.0019, +0.0044] | +0.0004 |
| 14:00 | +0.0009 | [−0.0021, +0.0039] | −0.0003 |
| 16:00 day before | **+0.0099** | **[+0.0063, +0.0136]** | +0.0040 |

Two reads of four clear zero against the three required, so **the gate fails and the MLP stays**.
Controls sit within −0.0004 to +0.0017 of the market, so the comparison is clean.

Scale moved every read in the same direction: the larger network beats the small one at all four.
At 16:00 the day before it lifts the gain over the market from +0.014 (MLP) to +0.024 nats per
ladder. Read against §18's caveat this is a second look at the same rows, and the 08:00 pass is at
the edge of its interval. It is a reason to run a forward test on ladders after 2026-10-05, not to
switch models now. Issue #24 tracks it.

## 20 · More data for the same models: pre-registration (2026-10-05)

§19 left open whether the transformer is limited by data. Four cheap ways to get more of it,
all on the highs walk-forward rows of the seven scored cities, lockbox untouched
(`scripts/data_scaling.py`, `src/isotherm/pooled.py`):

1. **Pooled read times.** One network trained on all four reads at once, with the read as a
   one-hot input: about four times the ladders per fold. Arms: pooled MLP, pooled transformer-L,
   and its market-label control.
2. **Learning curve.** The pooled MLP and transformer-L retrained on a random 25% and 50% of
   training dates (all reads of each kept date).
3. **Daily lows as extra training rows**, flagged as lows, before the lows lockbox. Lows start
   on 2025-12-14, so they can only change the last fold (2026-04-01 to 2026-06-30).
4. **New cities as extra training rows.** Kalshi lists twelve more US cities from January and
   February 2026 (ATL BOS DAL DC LV MIN NOLA OKC PHX SATX SEA SFO). Same last-fold limit. Only
   their rows before 2026-06-30 are used; this arm runs only if their panels pass the label
   check.

**Gates.** Paired on identical rows, log score, 95% date-block bootstrap, last 12 months before
the lockbox unless stated.
- *Adoption:* pooled transformer-L minus the per-read MLP must clear zero at 3 or more of 4 reads,
  with its control within ±0.005 of the market (the §16 rule). Otherwise the MLP stays.
- *Data-limited:* the transformer-L minus MLP gap, pooled over reads, grows from 50% to 100% of
  training dates with a CI above zero. A flat or shrinking gap means size or information, not
  data, is the limit.
- *Lows, new cities:* each, minus pooled transformer-L, on the rows of the last fold only (the
  only rows they can change), pooled over reads. Helps if the CI is above zero.

Pooled-vs-per-read differences for each model are reported without a gate.
