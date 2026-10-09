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

## 21 · More data: the transformer keeps learning, the MLP does not; extra rows hurt (2026-10-06)

`scripts/data_scaling.py --score` against §20 (pre-registered in commit a4454df). Raw:
`results/data_scaling.json`. Paired, last 12 months before the lockbox, 95% date-block CI.

**Adoption: fails.** Pooled transformer-L minus the per-read MLP:

| Read | Difference | CI |
|---|---|---|
| 08:00 | +0.0026 | [−0.0043, +0.0094] |
| 12:00 | +0.0011 | [−0.0043, +0.0068] |
| 14:00 | +0.0007 | [−0.0038, +0.0053] |
| 16:00 day before | **+0.0106** | **[+0.0038, +0.0172]** |

One read of four against three required; the MLP stays. Controls sit within ±0.0023 of the market.

**Pooling read times does not help on its own.** Pooled transformer-L ties the per-read
transformer-L at every read (−0.0038 to +0.0007, no CI excludes zero). The pooled MLP is better
at 16:00 (+0.0088) but worse at noon and 14:00 (−0.0035 each, CIs exclude zero): the same-day
reads lean on intraday observations that the day-before rows do not have, and one network has to
share capacity between them.

**Learning curve: the transformer is still learning, the MLP has stopped.** Gain over the market
pooled over reads, by share of training dates:

| Training dates | MLP | Transformer-L | Transformer minus MLP |
|---|---|---|---|
| 25% | +0.0102 | +0.0062 | −0.0039 [−0.0067, −0.0012] |
| 50% | +0.0106 | +0.0114 | +0.0008 [−0.0006, +0.0022] |
| 100% | +0.0128 | +0.0163 | +0.0035 [−0.0007, +0.0081] |

The MLP gains 0.003 nats from a fourfold increase in data; the transformer gains 0.010 and moves
from clearly worse to ahead. The pre-registered test, gap growth from 50% to 100%, is +0.0027
[−0.0012, +0.0067]: in the expected direction but **not significant**, so the data-limited claim
is not confirmed. The shape of the curve is the strongest evidence so far that more ladders, not
more parameters, are what the transformer needs.

**Lows and new cities as extra training rows hurt or do nothing.** On the last fold:
- *+ lows:* −0.0011 to −0.0026 at each read, no CI excludes zero.
- *+ new cities:* −0.0009 to −0.0063, worse at noon and 14:00 with CIs excluding zero.

The twelve new cities passed the label check (settlement equal to the NWS CLI on every day), so
this is not bad labels. They enter with a blank city input and only about 2,900 ladders from one
winter. That reads as distribution shift, not useful data: as extra rows they pull the network
toward climates it is not scored on. Their rows after 2026-06-30, about 4,500 ladders never used
by any test, remain a clean out-of-sample set for a future pre-registered test.

## 22 · NBM's own spread in EMOS: pre-registration (2026-10-06)

EMOS sets each forecast's sigma from the season alone. NBM publishes its own spread for the daily
max (XND, cached since 2021 and unused). The variant lets sigma scale with it:
log σ = γ·[1, cos t, sin t, log XND], refit monthly on strictly earlier days like every EMOS fit
(`dataset.load(nbm_spread=True)`; the default path is unchanged and reproduces the cached
features exactly). `emos_nbm_obs` inherits the new mean and sigma. Script: `scripts/nbm_spread.py`.

**Gates.** Paired on identical rows, log score, 95% date-block bootstrap.
- *Weather level:* EMOS-NBM with spread minus EMOS-NBM, on every ladder from 2023-07-01 to
  2026-06-30. Pass if the CI is above zero at 3 or more of the 4 reads.
- *Adoption:* the per-read isotherm MLP retrained on the spread inputs minus the current MLP, last
  12 months before the lockbox. Pass at 3 or more of 4 reads with its market-label control within
  ±0.005 of the market. Otherwise the inputs stay as they are.

NBM v5 (2026-04-21) changes what XND means; with only ten weeks of v5 before the lockbox, the split
is reported, not gated.

## 23 · Unseen cities: pre-registration (2026-10-06)

The twelve cities Kalshi added in January and February 2026 (§20) have rows after 2026-06-30
that no test has scored: about 4,500 ladders. They test whether isotherm transfers to cities it
has never seen, with no refitting. Script: `scripts/unseen_cities.py`, run once.

**Frozen models**, fit as in the lockbox on the seven scored cities' highs before 2026-06-29
(two-day embargo), per read: the market, pool · market+GFS, the isotherm MLP (five seeds) and
transformer-L (five seeds). New cities enter with a blank city input. Their EMOS and climatology
are fit on each city's own CLI history, monthly and causal, as everywhere else.

**Test rows:** the twelve cities' settled ladders from 2026-07-01 to 2026-10-04, all four reads,
rows where every source has a forecast.

**Gates.**
- *Primary:* isotherm minus the market, log score, CI above zero at 3 or more of the 4 reads:
  isotherm transfers.
- *Secondary:* the frozen strategy (pool · market+GFS, quarter Kelly, 16:00 taker; FINDINGS §9)
  through the lockbox engine, judged by the lockbox rule: PASS if PnL > 0 and Newey-West t > 1.645.
  Reported alongside: pool and transformer-L against the market, and results by city.

## 24 · Regime audit: the market got sharper; NBM v5 did not price out GFS (2026-10-06)

`scripts/regime_audit.py`, descriptive, no gate. Raw: `results/regime_audit.json`. 16:00 day-before
read, seven scored cities, by month from 2025-01. It uses months inside the lockbox, which was
already scored, only to describe them.

| | May to Sep 2025 | May to Sep 2026 |
|---|---|---|
| NBM point forecast MAE | 1.43 to 1.91°F | 1.60 to 1.83°F |
| GFS MOS point forecast MAE | 1.75 to 2.24°F | 2.00 to 2.17°F |
| Market log score | 1.30 to 1.37 | 1.14 to 1.22 |
| EMOS-NBM log score | 1.36 to 1.56 | 1.39 to 1.56 |

1. **NBM v5 (2026-04-21) did not make NBM visibly better at these stations.** Its summer 2026 error
   is no lower than summer 2025's.
2. **The market got about 0.15 nats sharper** in a year, while both public forecasts stood still.
   Most of the decay in §6 and §15 is the crowd improving, not the forecasts.
3. **The market now holds all of NBM.** In a 90-day trailing pool of market, NBM and GFS, NBM's
   weight has sat at or below zero since 2026-01, against +0.16 to +0.26 through most of 2025.
4. **GFS's weight is seasonal.** In the market+GFS pool it falls each winter and recovers each
   summer: 0.27 to 0.38 from Jul to Oct 2025, 0.08 to 0.11 from Dec 2025 to Feb 2026, 0.26 to 0.38
   from Apr to Aug 2026, then 0.19 in Sep and 0.11 in early Oct. The highs lockbox's falling
   monthly PnL (Jul $1,029, Aug $517, Sep $246) tracks this autumn decline, so part of that
   decay may be seasonal, not permanent. Expect a thin GFS edge through winter. Whether it returns
   next summer is a forward question the shadow ledger can answer.

Kalshi's `settle` field is blank for most of 2025-01, so forecast errors here are measured
against the NWS CLI high. Labels come from `result` and are unaffected.

## 25 · Sealed forward test: transformer-L against the MLP (pre-registration, 2026-10-06)

The backtest rows are used up: §17, §19 and §21 all looked at them. The question of whether the
transformer is better now goes to days that had not happened when this was written.

**Frozen** (`scripts/forward_freeze.py`, committed with this section before 20:00 UTC on
2026-10-06, the 16:00 ET read for 2026-10-07): the per-read MLP and transformer-L at 16:00 day
before, five seeds each, fit on all 7,692 settled ladders of the seven scored cities through
2026-10-04. `shadow/forward/models.pkl`, sha256 `c0f109a0bf8a2555…` (full hash in
`shadow/forward/frozen.json`, checked on load). Nothing is refit.

**Test window:** ladders for 2026-10-07 to 2027-04-05 at 16:00 day before, seven cities, built
afterwards by the same point-in-time panel builder from candles that closed before the read
(`scripts/forward_test.py`).

**Primary gate:** transformer-L minus the MLP, log score, 95% date-block CI, on the full window.
PASS if the CI is above zero; then transformer-L replaces the MLP at 16:00. Looks before
2027-04-05 are descriptive only.

**Secondary:** the MLP on NBM-spread inputs (§22) minus the MLP, same window and rule
(`models_spread.pkl`, sha256 `af83b5f31a7b1095…`). Each model against the market is reported.

## 26 · NBM's own spread: a large gain for EMOS, adoption fails 2 of 4 (2026-10-06)

`scripts/nbm_spread.py` against §22 (pre-registered in commit 09207d3). Raw:
`results/nbm_spread.json`.

**Weather level: passes at every read.** EMOS-NBM with spread minus EMOS-NBM, every ladder from
2023-07 to 2026-06:

| Read | EMOS-NBM | EMOS-NBM after v5 | EMOS-NBM-obs |
|---|---|---|---|
| 08:00 | +0.050 [+0.042, +0.058] | +0.038 [+0.012, +0.066] | +0.048 [+0.041, +0.056] |
| 12:00 | +0.050 [+0.042, +0.058] | +0.040 [+0.013, +0.069] | +0.043 [+0.036, +0.050] |
| 14:00 | +0.050 [+0.042, +0.058] | +0.040 [+0.013, +0.069] | +0.035 [+0.028, +0.042] |
| 16:00 day before | +0.043 [+0.035, +0.050] | +0.042 [+0.017, +0.067] | +0.043 [+0.035, +0.050] |

Letting sigma follow NBM's own spread is worth 0.04 to 0.05 nats per ladder to the forecast
itself, the largest single improvement to any input in this project. It holds after NBM v5.

**Adoption: fails.** The MLP retrained on the spread inputs minus the current MLP, last 12 months:

| Read | Difference | CI | MLP vs market, before → after |
|---|---|---|---|
| 08:00 | +0.0034 | [+0.0000, +0.0067] | +0.009 → +0.013 |
| 12:00 | +0.0017 | [−0.0007, +0.0041] | +0.010 → +0.011 |
| 14:00 | +0.0016 | [−0.0006, +0.0040] | +0.017 → +0.019 |
| 16:00 day before | **+0.0133** | **[+0.0074, +0.0185]** | **+0.014 → +0.028** |

Two reads of four clear zero against three required (08:00 by a hair), so the inputs stay as
they are. Controls sit within ±0.001 of the market. Most of the forecast's 0.05 nats was already
recovered by the MLP from the market and the other inputs; what is left is small at the same-day
reads, where observations dominate, and large the day before, where the forecast is all there is.
At 16:00 the spread nearly doubles isotherm's gain over the market. Picking that read now would
be selection after the fact, so it goes into the forward test as the secondary arm (§25).

## 27 · Unseen cities: isotherm does not clearly transfer (2026-10-06)

`scripts/unseen_cities.py` against §23, run once. Raw: `results/unseen_cities.json`. Models
frozen on the seven scored cities, scored on 4,588 ladders from the twelve new cities, 2026-07-01
to 2026-10-04.

| Read | isotherm vs market | pool · market+GFS | transformer-L |
|---|---|---|---|
| 08:00 | +0.0008 [−0.0043, +0.0061] | −0.0140 [−0.0271, −0.0012] | −0.0105 [−0.0216, +0.0014] |
| 12:00 | +0.0033 [−0.0020, +0.0085] | +0.0015 [−0.0068, +0.0095] | +0.0047 [−0.0050, +0.0142] |
| 14:00 | +0.0059 [−0.0012, +0.0132] | +0.0105 [+0.0004, +0.0206] | +0.0064 [−0.0001, +0.0131] |
| 16:00 day before | +0.0034 [−0.0081, +0.0145] | +0.0061 [−0.0063, +0.0182] | −0.0022 [−0.0178, +0.0129] |

**Primary: fails, 0 of 4.** Every point estimate for isotherm is positive, but none clears zero.
On cities it has never seen, isotherm is roughly as good as the market and no better that we can
detect.

**Secondary: the frozen strategy is consistent but underpowered.** +$1,549 over 96 days and 3,149
paper trades, Newey-West t 1.05. By month: Jul +$265, Aug +$2,032, Sep −$1,277, Oct (4 days)
+$529. By city it is split: LV +$1,072, NOLA +$659, BOS +$438, DAL −$884, ATL −$429, OKC −$403.

The transformer transfers worse than the MLP (−0.011 at 08:00, CI excluding zero): the extra
capacity fits the seven training cities more closely. Two readings of the null result: the
twelve markets are newer and may be priced differently, and the model has no city input for them.
Only the first matters for trading, and the data cannot yet tell them apart.

## 28 · Exploration: equal-weight ensembles beat the MLP at every read (2026-10-06)

`scripts/explore_ensemble.py`. Raw: `results/explore_ensemble.json`. **Exploratory**: five
combinations of cached walk-forward predictions, chosen after §19 and §26 were seen, on rows
already used many times. Equal weights, nothing fit. Each minus the MLP, last 12 months:

| Read | mean(MLP, transformer-L, spread MLP) | mean(transformer-L, spread MLP) |
|---|---|---|
| 08:00 | +0.0071 [+0.0047, +0.0096] | +0.0093 [+0.0058, +0.0129] |
| 12:00 | +0.0023 [+0.0010, +0.0036] | +0.0030 [+0.0011, +0.0050] |
| 14:00 | +0.0019 [+0.0006, +0.0033] | +0.0025 [+0.0005, +0.0044] |
| 16:00 day before | +0.0103 [+0.0078, +0.0128] | +0.0141 [+0.0103, +0.0177] |

The first variant in this project to clear zero at all four reads. Averaging members that err
differently narrows the intervals: neither the transformer nor the spread MLP clears zero alone
at noon or 14:00, but their mean does. Geometric means score within 0.0004 of arithmetic ones.
Because this was found by looking, it is not adopted; it goes to the forward test (§29).

## 29 · Forward test: the three-way ensemble (pre-registration, 2026-10-06)

Added to §25 before any test-window outcome exists. Its three members are the models already
frozen and hashed in §25, so nothing new is fit: the ensemble is their arithmetic mean at 16:00
day before. Same window (2026-10-07 to 2027-04-05), same rule: PASS if ensemble minus the MLP has
a 95% date-block CI above zero. The two-way mean of transformer-L and the spread MLP scored
higher in §28, but choosing it would be selection on the result; the three-way mean is the
pre-registered arm.

## 30 · Exploration: order flow helps, momentum does not (2026-10-06)

`scripts/explore_dynamics.py`, `src/isotherm/flow.py`. Raw: `results/explore_dynamics.json`.
**Exploratory.** Extra bucket inputs for the per-read MLP, everything else unchanged:
*momentum*, the change in the market's log-odds since the previous read and since 16:00 the day
before; *flow*, the net taker-YES share and log volume of each bucket's trades in the three hours
before the read (timestamps strictly before it). Each minus the MLP, last 12 months:

| Read | + momentum | + flow | + both |
|---|---|---|---|
| 08:00 | −0.0018 [−0.0044, +0.0009] | **+0.0049 [+0.0016, +0.0083]** | +0.0037 [+0.0006, +0.0069] |
| 12:00 | +0.0002 [−0.0031, +0.0035] | +0.0018 [−0.0020, +0.0055] | +0.0012 [−0.0020, +0.0044] |
| 14:00 | −0.0007 [−0.0020, +0.0006] | +0.0004 [−0.0011, +0.0021] | −0.0005 [−0.0026, +0.0015] |
| 16:00 day before | −0.0006 [−0.0017, +0.0004] | **+0.0057 [+0.0020, +0.0095]** | +0.0049 [+0.0012, +0.0090] |

The market's own price history adds nothing: the current price already holds it. Who has been
crossing the spread does add something, before the day starts, when no observation exists and
the crowd's recent direction is the freshest information. Once the day's observations arrive
(12:00, 14:00) it fades. Found by looking, so not adopted; it joins the forward test (§31).

## 31 · Forward test: the order-flow MLP (pre-registration, 2026-10-06)

Added to §25 before any test-window outcome exists. The per-read MLP with the two flow inputs
(§30), fit like the §25 models on all settled 16:00 day-before ladders through 2026-10-04, five
seeds: `shadow/forward/models_flow.pkl`, sha256 `e84ca72deeef511b…`. Same window (2026-10-07 to
2027-04-05) and rule: PASS if flow MLP minus the MLP has a 95% date-block CI above zero. Scoring
needs trades for the window (`scripts/fetch_trades.py`), filtered to before each read as in
training.

## 32 · Station corpus: 576 stations, 1.16 million station-days (2026-10-07)

`scripts/fetch_station_corpus.py`. Every NWS climate-report site in the lower 48 that IEM lists
(598), with CLI highs and lows, GFS MOS and NBM for 2021 onward: real forecasts and real
outcomes, no market. 576 stations are usable; 20 have no GFS MOS and 2 too short a CLI record
(`data/corpus_coverage.json`). After the 16:00 day-before point-in-time join and the removal of
CLI typos (§34), 1,155,446 station-days remain, about 150 times the ladder days of the seven
scored cities. The download took 11 hours at one IEM request every 3 s. It feeds the
multi-station weather model (§34, §35).

## 33 · Exploration: LAMP is the better forecast and adds nothing to isotherm (2026-10-06)

`scripts/fetch_lamp.py`, `scripts/explore_lamp.py`, `src/isotherm/lamp.py`. Raw:
`results/explore_lamp.json`, `results/explore_lamp_model.json`. **Exploratory.**

At each same-day read, the higher of the high already observed and the latest public LAMP run's
max over the rest of the climate day estimates the final high. Against the NWS CLI high,
2023-07 to 2026-06, seven cities:

| Read | NBM rest-of-day estimate, MAE | LAMP estimate, MAE | error correlation |
|---|---|---|---|
| 08:00 | 2.29°F | 1.82°F | 0.76 |
| 12:00 | 1.84°F | 1.52°F | 0.77 |
| 14:00 | 1.14°F | 0.98°F | 0.79 |

LAMP's estimate is 14 to 21% more accurate than the NBM one the model already uses, and its errors
are only partly shared. As two extra bucket inputs to the per-read MLP it is worth +0.0005 to
+0.0008 nats over the last 12 months, no CI excluding zero; with order flow, +0.0014 to +0.0017,
also inside the noise. The 16:00 day-before read, where LAMP inputs are blank, moves by −0.0006:
that is the size of seed noise alone.

A better public forecast that the market already watches does not help. Traders follow LAMP and
the live observations; by the read, the price holds what LAMP knows. Of everything tried, only
inputs that take work to use have added anything: NBM's spread is public but buried in text
bulletins, and the lean of the order flow has to be computed from the tape.

## 34 · A weather model across stations: pre-registration (2026-10-06)

EMOS fits each city alone on a few years of its own forecasts. The station corpus (§32) has the
same forecasts and outcomes at about 600 sites. One network across all of them can learn how NBM
and GFS MOS err in general, and per station through a learned embedding.

**Model** (`src/isotherm/wxnet.py`), fixed before any Kalshi row is scored. Scope: the 16:00
day-before read. Inputs, as public at that read (same `daytime_max_table` / `forecast_at`
point-in-time join as EMOS): NBM max and its spread XND, GFS MOS max, their difference, lead
times, season, and a station embedding (dimension 8). Output: a softmax over the integer high as
an offset of −20 to +20°F from the rounded NBM forecast, trained on log loss against the CLI high.
Three hidden layers of 128, three seeds averaged. Bucket probabilities are sums over the integers
each bucket settles on. Station time zones come from the city tables where known, otherwise from
longitude (corpus stations are training data only). Hyperparameters may be tuned on non-Kalshi
stations only.

**Walk-forward**: the same quarterly folds and two-day embargo as everywhere; each fold trains on
every station-day before the fold and predicts the seven scored cities' ladders in it.

**Gates**, 16:00 day before, paired, 95% date-block CI:
- *Forecast level:* the weather model minus EMOS-NBM with spread (§26, the best EMOS) on every
  ladder from 2023-07 to 2026-06. Pass if the CI is above zero.
- *Adoption:* the per-read MLP with the weather model in place of EMOS-NBM, minus the current
  MLP, last 12 months before the lockbox. Pass if the CI is above zero; then it joins the forward
  test as a new arm. Reported beside it: the same against the spread MLP.

## 35 · The weather model passes both gates; a fifth forward arm (2026-10-07)

`scripts/wx_gate.py`, results in `results/wx_gate.json`. 576 stations, 1,155,446 station-days,
expanding quarterly refits from 2022-04; nothing in §34 was changed. The model was not tuned
(no hyperparameter was varied after §34 was written).

**Preflight, disclosed.** While the download ran, the same script ran once on the first 338
stations (`--preflight`, `results/wx_gate_preflight.json`) to catch bugs before the long run.
It passed both gates (+0.041 and +0.019). Setting it up exposed one defect: the MLP's out-of-sample cache key
ignored input probabilities, so the partial run would have been reused by the full one; the
gate's MLP is now cached under a hash of the weather predictions. Nothing about the model
changed after the preflight.

| 16:00 day before | Δ log score | 95% CI | n |
|---|---|---|---|
| Forecast: weather model − EMOS-NBM with spread, 2023-07 to 2026-06 | **+0.043** | [+0.034, +0.051] | 6,063 ladders |
| Forecast: weather model − EMOS-NBM | +0.085 | [+0.075, +0.097] | 6,063 |
| Adoption: MLP on the weather model − MLP, last 12 months | **+0.018** | [+0.010, +0.025] | 2,542 |
| Same − the MLP on NBM-spread inputs (§26), reported only | +0.004 | [−0.002, +0.011] | 2,542 |

Both gates pass. Against the market over the same 12 months the MLP gains +0.014 nats and the
MLP on the weather model +0.032.

What this does and does not show:
- **Most of the gain is the spread.** The spread MLP already takes +0.013 of the +0.018; the
  margin over it is not distinguishable from zero. The network adds a modest amount on top of
  what NBM's own spread gives EMOS.
- **Station count saturates early.** 338 stations gave +0.041 at the forecast level, 576 gave
  +0.043. More stations of the same two forecasts add little; a third forecast source would
  likely matter more than more sites.
- **One read.** §34 scoped the gate to 16:00 day before; same-day reads are untested.

**Forward arm** (pre-registration). Frozen by `scripts/forward_freeze.py --wx` into
`shadow/forward/models_wx.pkl`, sha256 `23988591642664f4…` (full hash in
`shadow/forward/frozen_wx.json`, checked on load): the station network fit on every corpus station-day through 2026-10-04, and
the per-read MLP at 16:00 day before fit on 7,692 ladders through 2026-10-04 whose
weather-model inputs come from the expanding refits above. The arm was frozen after the §25
window opened, so it gets its own: ladders for **2026-10-09 to 2027-04-05**, built by the same
point-in-time pipeline; at each, the frozen network predicts from the 16:00 forecasts and the
frozen MLP takes its output in place of EMOS-NBM. **Gate:** the MLP on the weather model minus
the frozen MLP of §25, paired on those ladders, PASS if the 95% date-block CI is above zero over
the whole window (`scripts/forward_test.py`, key `weather_model`). Looks before 2027-04-05 are
descriptive only.

*Process note.* Background jobs thought dead were still running, so the gate ran twice and the
freeze three times concurrently, all on the same code and data. CPU training is not
bit-reproducible: the three freezes hashed `8eb849b6…`, `e7da06c4…` and `23988591…`. The frozen
arm is the last written, whose model file and hash file agree; none was scored on anything. The
recorded gate result was reproduced exactly from its caches afterwards.

## 36 · Exploration: nineteen cities help the transformer, not the MLP; Polymarket is a different label (2026-10-07)

The transformer looks data-limited (§21), and the seven cities add only about 2,550 ladders a
year. Two cheap sources of more were checked.

**The twelve newer cities, each with its own identity** (`src/isotherm/cities.py`,
`scripts/explore_cities.py`, `results/explore_cities.json`). As extra rows with a blank city
input they hurt (§21). Here the context gains a one-hot over the twelve. One split: train on
every ladder before July 2026 (28,133 from the seven cities, 7,254 from the twelve, which list
from January or February 2026), test 2026-07-01 to 2026-10-04 (2,683 ladders from the seven,
4,588 from the twelve). These rows were seen in §23 and the sealed tests, so this is exploration.

| Read | MLP: 19 − 7 cities, on the seven | Transformer: 19 − 7, on the seven | Transformer: 19 − 7, on the twelve | Transformer-19 − MLP-7 on the seven (point) |
|---|---|---|---|---|
| 08:00 | −0.009 [−0.014, −0.004] | −0.014 [−0.027, −0.002] | +0.013 [+0.003, +0.022] | −0.004 |
| 12:00 | −0.002 [−0.006, +0.003] | +0.004 [+0.000, +0.007] | +0.004 [−0.002, +0.011] | +0.012 |
| 14:00 | −0.001 [−0.005, +0.002] | +0.009 [+0.006, +0.013] | +0.004 [−0.000, +0.008] | +0.007 |
| 16:00 day before | −0.002 [−0.008, +0.005] | −0.003 [−0.013, +0.007] | +0.007 [−0.001, +0.014] | +0.003 |

The control (19-city MLP on market-sampled labels) is within ±0.001 of the market everywhere.

- **The MLP gains nothing** from the twelve, as §21's learning curve predicted.
- **The transformer mostly gains**: on the twelve at every read, on the seven at noon and 14:00,
  but it loses at 08:00. On the seven, the 19-city transformer beats the 19-city MLP at three
  of four reads (CI above zero at 08:00, noon and 14:00).
- One split of 96 days; worth a test on a window nobody has seen (§37), not adoption.

**Polymarket** (`docs/research/polymarket_2026-10.md`). 2,999 settled US city-days of "highest
temperature" markets in 11 cities, mostly from December 2025 or March 2026, with minute-level
prices. Not usable as Kalshi ladders: Polymarket settles on the highest *hourly* airport
reading, and even at Kalshi's own station the NWS climate-report high falls in Polymarket's
winning bucket only 59 to 71% of the time (usually 1°F higher); four cities settle at a
different airport. It would need a second target and a multi-task model. Not pursued.

## 37 · Nineteen cities on a fresh window: pre-registration (2026-10-07)

Written before any ladder in the test window exists.

**Design** (`scripts/explore_cities.py --gate`, unchanged from §36 apart from the window):
train on every settled ladder before 2026-12-30 (two-day embargo), seven scored cities plus the
twelve newer ones, each with its city input; test on ladders for **2027-01-01 to 2027-04-05**,
all four reads. Models as in §36: the per-read MLP on the seven cities (today's isotherm), the
19-city MLP, transformer-L on the seven, the 19-city transformer-L, and the 19-city
market-labels control. By then the twelve have about eleven months of history.

**Primary gate:** the 19-city transformer-L minus the 7-city MLP, log score on the seven scored
cities, 95% date-block CI. PASS if the CI is above zero at 3 of 4 reads and the control is within
±0.005 of the market on both city groups. Then the 19-city transformer replaces the MLP, and
the twelve newer cities become scored cities. Reported, not gated: every other pairing in §36,
on both groups. Run once, after the window settles (the script refuses earlier).

## 38 · The typed answers: coherent, better calibrated, no better at locating the high (2026-10-07)

`scripts/typed_eval.py`, `results/typed_eval.json`. Every result before this scores bucket
probabilities. The API (`isotherm.api`, PLAN §0) answers three question types off one integer
distribution, built from those probabilities as `serve.integer_distribution` builds it. This
scores what an API user receives, on the out-of-sample rows of the last 12 months before the
lockbox (about 2,550 ladders per read):
- **Choice:** the bucket, by log loss.
- **Noul:** P(high ≥ t) at every integer t within 6°F of the NBM forecast, by Brier score and
  debiased calibration error.
- **Score:** the high itself, by CRPS, the error of the median and the 80% interval.

The within-bucket shape (the forecast Gaussian) is the same for every model, so they differ only
through their bucket probabilities.

**Coherence holds**: 0 violations on 10,204 ladders × 3 models (Choice sums to one, Noul
monotone, mean inside the 1-99% range), as the design promises.

| Read | Choice: Δ log loss vs market | Noul calibration error, market → isotherm | Score: Δ CRPS vs market | 80% interval: coverage − own mass, market → isotherm | Width, market → isotherm |
|---|---|---|---|---|---|
| 08:00 | +0.009 [+0.001, +0.017] | 0.020 → 0.007 | +0.003 [−0.003, +0.008] | +2.8 → −0.2 pts | 4.4 → 4.1°F |
| 12:00 | +0.010 [+0.004, +0.015] | 0.019 → 0.010 | −0.001 [−0.005, +0.002] | +3.9 → +1.8 pts | 3.6 → 3.4°F |
| 14:00 | +0.017 [+0.010, +0.024] | 0.027 → 0.017 | +0.001 [−0.002, +0.004] | +4.4 → +0.9 pts | 2.8 → 2.5°F |
| 16:00 day before | +0.014 [+0.006, +0.022] | 0.026 → 0.013 | +0.005 [−0.005, +0.014] | +3.8 → +1.4 pts | 5.6 → 5.2°F |

- **isotherm's edge is in shape and calibration, not location.** Across thresholds its yes/no
  probabilities' calibration error is a third to two thirds lower than the market's. The market's 80% intervals
  are too wide (they hold the outcome 2.8 to 4.4 points more often than its own probabilities say);
  isotherm's are about 7% narrower and close to their stated mass.
- **For a point forecast it adds nothing.** CRPS and the error of the median (0.7 to 1.6°F) match
  the market's. For the MLP no CRPS CI clears zero, and only the 16:00 Noul Brier does, barely
  (+0.0006 [+0.00002, +0.0012]). The crowd already knows where the high will land; what it
  misprices is how sure to be.
- **Transformer-L at 16:00 day before** is the exception: CRPS +0.014 [+0.006, +0.024] and Noul
  Brier +0.0012 [+0.0006, +0.0018], both above zero.
- **The weather-model MLP (§35)** at 16:00: Choice +0.032 [+0.021, +0.042], Noul calibration error
  0.015 against the market's 0.027, CRPS +0.005 [−0.008, +0.017]. (Its rows use the weather
  model's moments for the within-bucket shape, so its market row differs slightly from the table.)

This is the first evaluation of the typed interface itself. It supports the Jev design (one
distribution, coherent answers, better calibrated than the market) and narrows the claim: the
answers to "which bucket" and "how likely is above t" beat the market; the answer to "what will
the high be" does not.

## 39 · Exploration: market-only signals, and what Kalshi holds beyond weather (2026-10-08)

**What Kalshi holds** (`scripts/survey_kalshi.py --events-only`, `results/kalshi_survey.json`). The
public listing has 799,186 settled events: sports 378,148, crypto 301,411, climate and weather
35,851, commodities 30,010, financials 27,831, entertainment 11,022, economics 3,895. Beyond the
daily highs, the numeric ladders with thousands of settled events are the S&P 500 (daily 1,132,
hourly 3,307), Nasdaq 100, EUR/USD and USD/JPY (hourly about 4,000 each), WTI, gold and silver
(hourly about 1,400, 15-minute about 4,800 each) and hourly NYC temperature (3,806). That is the
cross-category data a general model would train on. The per-market listing was stopped: at this
size it takes days, and per-series fetches are the better tool.

**Market-only signals** (`scripts/alpha/`, `results/alpha/`; an agent's exploratory search on rows
that other sections have used). Data: 42,806 weather ladders over 19 cities after cleaning (7
events with failed candle fetches, 46 empty books and 2,040 non-partition ladders dropped; 3,061
books whose mids sum outside 0.8 to 1.5 kept and flagged), and 1,165 non-weather binary markets
in 8 categories (111 events whose close time depends on the outcome dropped as leaky, 17,599
zero-volume markets and 435 bad-book rows dropped). Log-score gain over the market at the same
timestamp, 95% date-block CI:

| Signal | 2024-25, walk-forward | 2026, seven cities | 2026, twelve newer cities |
|---|---|---|---|
| Sharpening exponent, 16:00 day before | +0.006 [+0.004, +0.009] | **+0.010 [+0.005, +0.015]** | **+0.009 [+0.005, +0.012]** |
| Sharpening exponent, 08:00 / 12:00 / 14:00 | +0.007 / +0.007 / +0.018, all CIs above 0 | +0.007 / +0.007 / +0.015, all CIs above 0 | not significant |
| Stale quotes, bucket shape | +0.008 to +0.033 | about 0 | |
| Order flow, linear, market only | about 0 | slightly negative | |
| Kalshi-wide binary recalibration | | +0.0004 [−0.0013, +0.0020] | |

- **The one survivor is sharpening**: each bucket's market probability raised to a power (about
  1.17; 1.32 at 14:00) and renormalised. It is positive in every half-year, read and scored city.
  The market is a favourite-longshot crowd: buckets priced 2 to 10% settle 30 to 45% less often
  than priced. This is §38's finding (the crowd misprices how sure to be) recovered from price
  alone. It is not new to isotherm: the frozen pool of §9 already raises the market to 1.073
  (§3: tempering the market gained +0.002 then), and whether the stronger exponent adds to the MLP is untested.
  Recomputed on the project's own market probabilities, 2026 rows: +0.011 [+0.005, +0.016] at
  16:00 day before, matching.
  *Corrected in §41: most of this gain is the mid-price convention, not the crowd.*
- **Stale quotes and bucket shape faded** with 2024's thin books (9¢ median spread then, 1¢
  now): a data repair, not a signal.
- **Order flow alone does nothing**; §30's gain needs the forecasts beside it.
- **Kalshi-wide, the bias points the same way but is too small to see** on 542 test markets.
  Apparent arbitrage in ladders (bids summing above $1 after fees, 154 of 24,111) comes from
  non-simultaneous hourly quotes.

## 40 · Sharpening the market: sealed forward test (pre-registration, 2026-10-08)

Written before any ladder in the window opened (the 2026-10-10 ladders open at 14:00 UTC on
2026-10-09).

**Frozen** (`shadow/forward/sharpen.json`, sha256 `6ae8017d1f98cd98…`, checked on load): one
exponent per read, fit on every seven-city ladder through 2026-10-04: 16:00 day before 1.1822,
08:00 1.1661, 12:00 1.1569, 14:00 1.3212. The forecast is p ∝ p_market^a, renormalised over the
ladder; nothing is refit.

**Window:** every settled ladder of the 19 cities from **2026-10-10 to 2027-04-05**, at all four
reads, from the same point-in-time panel (`scripts/sharpen_test.py`).

**Primary gate:** sharpened minus raw market, log score, 16:00 day before, 95% date-block CI.
PASS if the CI is above zero. Secondary: CI above zero at 3 of 4 reads. Reported, not gated: the
seven and the twelve cities separately, and the frozen §25 MLP minus the sharpened market at 16:00
day before (does isotherm already hold this edge?). Looks before 2027-04-05 are descriptive only.

## 41 · Correction: the sharpening gain is mostly how the market price is built (2026-10-08)

Written before any ladder in the §40 window opened (first opens 14:00 UTC 2026-10-09).

**Cross-category test** (`scripts/alpha_xcat/`, `results/alpha_xcat/sharpen_xcat.json`, an agent's
exploration). The newest 280 settled events of four daily numeric ladders (S&P 500, Nasdaq 100,
EUR/USD, USD/JPY; 1,120 clean partition ladders, August 2025 to October 2026), priced 1 hour
before close. Sharpening the mid-price market wins by +0.08 to +0.15 pooled, ten times weather's
gain, with fitted exponents of 1.5 to 3.5. The reason: 70 to 86% of those buckets have no bid and
an ask of a few cents, and the mid counts that unbid ask as probability. Pricing each bucket at
its bid (floored at 0.5¢, renormalised) beats the mid market by +0.15 to +0.31, more than any
sharpening; sharpening on top of the bid-priced market then loses out of sample (pooled −0.055
[−0.078, −0.032]). Market sharpening does not generalise as a crowd bias across categories.

**The same check on weather**, 2026 rows, seven cities:

| Read | Buckets with no bid | Bid-priced minus mid market | Sharpened minus mid (§39) | Sharpened minus bid-priced |
|---|---|---|---|---|
| 08:00 | 23% | +0.004 [+0.002, +0.007] | +0.007 | +0.002 [−0.002, +0.006] |
| 12:00 | 38% | +0.004 [+0.002, +0.007] | +0.007 | +0.002 [−0.002, +0.006] |
| 14:00 | 53% | +0.003 [+0.000, +0.006] | +0.015 | **+0.012 [+0.006, +0.018]** |
| 16:00 day before | 6% | +0.007 [+0.005, +0.010] | +0.011 | +0.003 [−0.001, +0.007] |

Pricing at the bid takes most of §39's gain with no parameters; beyond it, sharpening still wins
only at 14:00. §39's reading ("the crowd overprices long shots") was too strong: mostly, the mid
price overstates buckets nobody is bidding on.

**isotherm against the stricter baseline.** Every result in this file compares with the mid
market, so the MLP was rechecked against the bid-priced market, last 12 months before the
lockbox: 08:00 +0.009 [+0.001, +0.018], 12:00 +0.005 [−0.002, +0.011], 14:00 +0.014 [+0.007,
+0.020], 16:00 day before +0.013 [+0.004, +0.021] (against the mid: +0.009, +0.010, +0.017,
+0.014). The edge survives at three of four reads; it comes from the forecasts, not the pricing.

**§40 corrected, beside the original.** Primary gate: sharpened market minus the **bid-priced**
market (bids floored at 0.5¢, renormalised), 16:00 day before, 95% date-block CI above zero.
Secondary: 3 of 4 reads on the same comparison. The original §40 comparison (against the mid
market) is still computed and reported (`verdict_original_s40`). Frozen exponents and window
unchanged.

## 42 · Exploration: gas prices, where the crowd already knows (2026-10-08)

Two candidates for a second domain were checked first. Kalshi's hourly temperature ladders
(KXTEMPNYCH and others, settled on The Weather Company's hourly reading) were discontinued on
2026-09-10 and the median NYC event never traded: dropped. Kalshi's daily AAA national gas
average (KXAAAGASD) is live and liquid: 221 settled events (24 in 2023, then daily from late
March 2026), 17 "above $x" strikes 0.5¢ apart, median volume about 140,000 contracts a day, and the
exact AAA value recorded at settlement.

`scripts/gas/`, `results/gas/gas_model.json`. At 16:00 ET the day before (AAA's previous value and
that day's RBOB settle both public), a walk-forward ridge regression forecasts the change in AAA
from RBOB futures moves over 1 to 20 trading days, the last two AAA changes and the
retail-minus-wholesale spread, as a Gaussian; refit daily on earlier days only, first forecast
after 60 days. 153 ladders scored, 2026-05-09 to 2026-10-08:

| | Δ log score vs market | 95% CI |
|---|---|---|
| Model alone | −0.931 | [−1.095, −0.745] |
| Log pool of market and model (weights fit on earlier days) | −0.025 | [−0.081, +0.013] |

The model does carry signal: its forecast misses AAA's change by 1.15¢ on average, against 1.41¢
for "no change". But the market is far sharper, putting nearly all its mass on two or three
0.5¢ buckets, and the pool gives the model a weight of 0.17. By 16:00 the crowd can watch
real-time station-price trackers that are close to the next morning's AAA figure, and that is
neither free nor something daily futures can match.

This sharpens the thesis behind isotherm. Weather works because the useful public information
(NWS model output, calibrated) takes skill to use and the crowd under-uses it. Where the decisive
information is real-time and easy to read, the crowd prices it. Not pursued further.

## 43 · Rain: the model adds information the day before, mostly inside the spread (2026-10-09)

The §42 thesis says isotherm's edge lives where public information takes skill to use. Rain
probability from NWS model output is that kind of signal. `scripts/rain/`, `results/rain/rain_eval.json`
(an agent's build, reviewed here).

**Markets.** KXRAIN, "will it rain in <city> today", daily since 2026-07-15 in about 25 cities,
settling on NWS climate-report precipitation strictly above 0 (80 events, 1,815 markets to
2026-10-07); and the NYC-only series, 2021 to 2026-07-15 (771 usable days; 98 early events with
only amount thresholds dropped; none listed in 2023-24). Read at 16:00 local the day before
(1,663 KXRAIN two-sided books; 127 one-sided, 25 unquoted dropped) and 08:00 on the day (1,265
two-sided; the 545 one-sided books there are dropped, though they select on the outcome: a 99¢
bid with no ask had always already rained).

**Labels.** Non-trace days agree with the climate report 100% in both series. The two series
settle a trace differently: KXRAIN as dry (198 of 198 trace days NO), the NYC series as wet (82
of 82 YES); each model is trained on its own series' rule.

**Model.** Logistic regression on NBM and GFS MOS precipitation probabilities (6- and 12-hour
PoP aggregated over the climate day, amount categories, season), point in time at each read,
trained on 2.33 million station-day-reads across the 576 corpus stations, refit quarterly from
2021Q4 with a two-day embargo. Gradient boosting was chosen against on non-market stations only
(it gained under the 0.005 bar set beforehand).

**Results**, log score gain, 95% date-block CI:

| Series, read | n | Model − mid | Model − market at its most favourable price in [bid, ask] | Stack (fit on earlier days) − mid |
|---|---|---|---|---|
| KXRAIN, 16:00 day before | 1,663 | **+0.032 [+0.014, +0.053]** | +0.010 [−0.002, +0.022] | **+0.015 [+0.002, +0.026]** |
| KXRAIN, 08:00 | 1,265 | −0.018 [−0.037, +0.002] | −0.030 [−0.046, −0.015] | **+0.026 [+0.016, +0.036]** |
| NYC, 16:00 day before | 484 | **+0.049 [+0.018, +0.079]** | +0.018 [−0.006, +0.041] | **+0.052 [+0.021, +0.083]** |
| NYC, 08:00 | 402 | −0.001 [−0.042, +0.039] | −0.035 [−0.068, −0.005] | +0.030 [−0.003, +0.063] |

- **The day before, the model knows something the price does not.** The market overprices rain
  (mean mid 0.273 against 0.243 realised; its 45% bin rains 30% of the time), while the model is
  calibrated (debiased calibration error 0.030 against the market's 0.041). 18 of 22 cities are
  positive.
- **Mostly inside the spread.** Against the market at its most favourable price within the
  quote, the gain is +0.010 with a CI touching zero. A taker paper rule shows +4.4¢ a contract,
  but §6 showed one tick of slippage can erase an edge this size.
- **Decaying, like §3.** KXRAIN at 16:00: July +0.133 (the series' first weeks), August +0.021,
  September +0.015, October +0.008. Without July, +0.016 [+0.003, +0.029]. NYC by year: 2021
  +0.05, 2022 +0.05, 2025 +0.095, 2026 +0.006.
- **On the day the price wins**: by 08:00 it knows whether it rained overnight, the model does
  not, and only the stack helps.

## 44 · Rain: sealed forward test (pre-registration, 2026-10-09)

Committed before the first window market opens (KXRAIN opens about two days ahead; the
2026-10-11 event opens around 09:10 UTC on 2026-10-09).

**Frozen** (`shadow/forward/models_rain.pkl`, sha256 `5befac8ebd9542c5…`, full hash in
`shadow/forward/frozen_rain.json`, checked on load; scikit-learn 1.9.1): the logistic PoP model
fit on every labelled station-day through 2026-10-07, and the 16:00 stack
p = σ(−0.097 + 0.359·logit(mid) + 0.755·logit(model)) fit on the 1,663 KXRAIN rows above.
Nothing is refit.

**Window:** KXRAIN target days **2026-10-11 to 2027-04-05**, read at 16:00 local the day before,
two-sided books only (`scripts/rain/forward_test.py`).

**Primary gate:** frozen stack minus mid, log score, 95% date-block CI above zero.
**Secondary gate:** the model minus the market at its most favourable price within [bid, ask]
(information beyond the spread), CI above zero. Reported, not gated: model minus mid, by month,
by city. Looks before 2027-04-05 are descriptive only.

## 45 · Two controls from financial representation learning (2026-10-09)

Merchant, Guthrie, Mahns, Balestriero and Levy, "Towards Financial World Modeling" (arXiv
2610.09048), compare 18 encoder-training strategies on a trillion one-second US equity
observations. They find a random, untrained encoder with a fitted probe is a strong baseline,
supervised training beats self-supervised, and the test month explains 97 to 99.9% of the variance
in results against the seed. Their two controls, applied to isotherm (`src/isotherm/controls.py`,
`scripts/controls.py`, `results/controls.json`), last 12 months before the lockbox, 95% date-block CI:

**Random encoder.** Transformer-L with its encoder frozen at random initialisation; only the log
pool and the output head are trained (five seeds, as for every isotherm model).

| Read | Random encoder − market | Trained − random encoder | MLP − random encoder |
|---|---|---|---|
| 08:00 | +0.008 [+0.002, +0.015] | +0.007 [−0.000, +0.015] | +0.001 [−0.003, +0.005] |
| 12:00 | +0.007 [+0.003, +0.011] | +0.004 [−0.001, +0.009] | +0.003 [−0.001, +0.006] |
| 14:00 | +0.014 [+0.007, +0.021] | +0.004 [−0.002, +0.009] | +0.003 [−0.001, +0.007] |
| 16:00 day before | +0.016 [+0.009, +0.022] | **+0.008 [+0.004, +0.013]** | −0.002 [−0.006, +0.003] |

Most of isotherm's gain over the market needs no learned representation: random features over the
same inputs, with a trained head and log pool, already beat the market at every read and tie the
MLP. Training the attention adds only at 16:00 the day before, where it is also the read at which
the transformer beat the MLP (§19). This is the paper's finding at a smaller scale: the inputs
and the supervised head carry the edge.

**Regime against seed.** Five single-seed MLPs (one network each, different initialisation),
monthly gain over the market across every out-of-sample month (36), two-way decomposition:

| Read | Month | Seed | Residual | Months positive | Monthly gain range |
|---|---|---|---|---|---|
| 08:00 | 98.2% | 0.10% | 1.7% | 32 of 36 | −0.049 to +0.349 |
| 12:00 | 96.9% | 0.34% | 2.7% | 32 of 36 | −0.013 to +0.146 |
| 14:00 | 99.2% | 0.02% | 0.8% | 32 of 36 | −0.040 to +0.196 |
| 16:00 day before | 99.1% | 0.02% | 0.9% | 32 of 36 | −0.037 to +0.294 |

Seed noise is negligible; when isotherm wins or loses is decided by the month (§24: the market's
sharpness and GFS's seasonal value). Results from a single short window, ours included, should be
read as one draw from a highly variable regime, which is why every gate here uses a year of data
and date-block intervals.
