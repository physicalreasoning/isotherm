# pm-decide · plan

An open, typed, calibrated decision model for prediction markets, in the style of TypeSafe's Jev
("System One"), built and evaluated on Kalshi daily high-temperature ladders.

Every gate below is stated before its experiment runs. When a gate turns out to be mis-specified it
is corrected beside the original, never in place of it, as in `causal-jepa`.

---

## 0 · Problem statement

**Input:** a point-in-time *state* for one city-day at one read time: the market ladder, the NWS
forecasts public at that moment, intraday observations so far, climatology, calendar.

**Output:** answers to *typed questions*, each with calibrated probabilities:

| Jev primitive | Here | Example |
|---|---|---|
| **Choice** | which ladder bucket settles YES | `{"<80", "80-81", ..., ">87"}` -> per-option P |
| **Noul** | any yes/no over the high | P(high ≥ 85), P(high in [80, 83]) |
| **Score** | the high itself | E[high], 10/50/90% quantiles, interval |

**Design commitment:** all answers are read off **one predictive distribution over the integer
high**. Choice, Noul and Score then cannot contradict each other (buckets sum to one, thresholds
are monotone), and the model answers any ladder Kalshi lists, including strike layouts it has
never seen, with no retraining. Jev does not publish whether its heads are coherent; ours are by
construction.

**Primary metric:** out-of-sample log score of the realised bucket, against the market-implied
distribution **at the same timestamp**. Secondary: ranked probability score (buckets are ordered),
CRPS for Score, debiased ECE for Noul, and net-of-fee P&L in a conservative backtest.

**Non-goals:** forecasting the atmosphere (we consume NWS forecasts, see 01-market-selection);
live trading; an LLM reading question text and emitting P(yes).

---

## 1 · Lifecycle at a glance

```
 survey ──► G0 headroom ──► data platform ──► baselines (G1) ──► model v1 (G2)
 (done)     no model,        point-in-time      EMOS, market,      typed heads over
            decides go       panel + features   blend, GBM         one distribution
                                                                     │
   release ◄── G5 paper ◄── G4 backtest ◄── calibration ◄── G3 synthetic pretraining
   cards,      trading 4wk   net of fees,    temperature,     ablated: kept only
   API, repo   live, shadow  lockbox once    conformal         if it earns it
                                   │
                         monitoring + retraining (continuous)
```

| Gate | Question | Pass | Kill / redirect |
|---|---|---|---|
| **G0** | Does a free forecast add information the market lacks? | blend beats market log score, 95% CI excludes 0, at ≥1 read time | CI includes 0 at every read time *and* intraday obs add nothing: stop, write up |
| **G1** | What is the bar? | baselines reproduce, leak tests pass | |
| **G2** | Does the typed model beat the best baseline? | Δ log score vs best baseline > 0, CI excludes 0, walk-forward | ship the best baseline as the model instead; it still serves the API |
| **G3** | Does synthetic pretraining help? | learning curve: same score with ≤50% real data, or better at 100% | drop it, and say so |
| **G4** | Does the edge survive fees and fills? | lockbox net P&L CI excludes 0 under the conservative fill model | publish as a forecasting result only |
| **G5** | Does it hold live? | 4 weeks shadow: realised log score within backtest CI, no calibration drift | investigate skew before anything else |

---

## 2 · Data

### Sources (all free, all verified 2026-10-04)

| Source | What | Since | Use |
|---|---|---|---|
| Kalshi `/events`, `/markets`, `/historical/*` | ladders, settlement, hourly candles, trades with taker side | 2021-08 (NY) | state, labels |
| IEM GFS MOS (MAV) | station max/min forecast per 6h-cycle run | ≤2012 | feature; leak-free calibration years |
| IEM NBM (NBS) | NBM max/min with spread (`txn`, `xnd`) | 2021 | feature |
| IEM CLI | NWS Daily Climatological Report | ≤2015 | old settlement source; synthetic labels |
| IEM ASOS | hourly / 1-min station observations | decades | intraday "high so far" (a hard lower bound on the answer) |

### Point-in-time correctness (where leaks come from)

1. **Market:** only candles whose `end_period_ts` ≤ read time. A candle's close is known at its end,
   not its start.
2. **Forecasts:** a run is usable only at `runtime + 5h` (GFS MOS hits the wire ~4h after nominal
   time). Enforced in `weather.mos_daytime_max`, unit-tested.
3. **Observations:** an hourly ob is usable at its valid time plus a reporting lag (15 min).
4. **Labels:** always Kalshi's `result` / `expiration_value`, never an archive. The settlement source
   moved from NWS CLI to The Weather Company between 2026-08-03 and 2026-10-03; the switch is a slice
   and a monitoring alarm, not a silent relabel.
5. **Calibration fits** (EMOS bias and spread) use only years before the evaluation window; the
   default fits on 2015 to the first market date, which the market never traded.

### Validation (runs on every build, fails loudly)

- bucket arithmetic reproduces Kalshi's `result` for **every** market (currently 48/48 on the smoke
  panel; the full panel re-checks all ~50k)
- exactly one YES bucket per event; ladder mids sum within [0.85, 1.20]
- CLI high = Kalshi settlement on pre-switch days (measures label agreement; expected ~100%)
- failed fetches are flagged (`candles_ok`) and refilled, never mistaken for an empty book

### Storage and lineage

Raw HTTP responses for anything settled are cached immutably (`data_cache/`, keyed on URL). Derived
tables are parquet under `data/`, rebuilt by script, never edited. Each results JSON inlines its full
config plus the git SHA; a data manifest (row counts + content hash per table) is written alongside.

---

## 3 · G0: headroom, before any model (`scripts/benchmark.py`, Gate 0 section)

The cheapest experiment that can kill the programme, run first. This is the lesson of
`causal-jepa`'s `horizon_headroom.py`: three of its four targets were unusable, and it took a minute
to show that without training anything.

For each city-day and read time (`d1_16`, `d0_08`, `d0_12` local):

1. **Market:** bucket mids at the read time, overround removed by normalising.
2. **Forecast (EMOS):** the latest public GFS MOS max, mapped to bucket probabilities by
   `N(a + b·fcst, σ(doy))` fitted by maximum likelihood on CLI highs from **2015 to the city's first
   market date**, so no evaluation day can leak into the fit.
3. **Blend:** logarithmic opinion pool `p ∝ p_mkt^w1 · p_fcst^w2`, weights per read time, refit
   walk-forward each quarter on earlier rows only (§7 splits).

Report log score for all three, Δ(market − blend) with a block bootstrap by **date** (cities share
weather systems; date is the independent unit) and a Diebold-Mariano test. A **tempered market**
(`p_mkt^w`, no forecast) is scored alongside, so a gain from merely fixing the market's own
calibration is not mistaken for new information. Run with GFS MOS and with NBM; the intraday
max-so-far for `d0_12` is added once ASOS is ingested.

---

## 4 · Baselines (G1)

Every model is compared against all of these on identical rows. Each one is a real competitor; the
model has to beat the best, not the weakest.

| Baseline | What it tests |
|---|---|
| Climatology (day-of-year normal + spread) | is there any signal at all |
| Market mid, normalised | the crowd |
| EMOS on GFS MOS, EMOS on NBM | the NWS forecast, honestly calibrated |
| Log-pool of market and EMOS | a two-parameter model; the real bar |
| LightGBM multiclass on residual bins | strong tabular learner on the same features |
| Untrained network, same architecture | the `causal-jepa` control: has training learned anything |

---

## 5 · Model (G2)

### State encoder

| Block | Inputs | Encoder |
|---|---|---|
| market | bucket mids, spreads, ladder-implied mean / sd / skew, 1-3-6h changes, cum volume, taker imbalance from trades | per-bucket tokens + set attention (ladders vary in size and strikes) |
| forecast | latest GFS MOS and NBM max, NBM spread, run-to-run revisions, lead time | MLP |
| obs | max so far today, current temp, hours of daylight left | MLP |
| context | city embedding, day-of-year (sin/cos), normal high, settlement regime | embeddings |

The fused representation goes to a **distributional head**: logits over integer offsets
`high − anchor` in [−25, +25] °F, where `anchor` is the latest forecast. This makes the output
space translation-invariant across cities and seasons, and makes "trust the forecast" the default.
A second variant predicts a **correction to the market distribution** (log-ratio) rather than a
distribution from scratch; in markets with a strong crowd that parameterisation usually wins, and
it is cheap to try both.

### Typed adapters (parameter-free)

`Choice(options)`: sum bin mass inside each option's interval. `Noul(set)`: mass inside the set.
`Score`: mean / quantiles of the distribution. *Confidence* = probability of the chosen option, as
Jev reports it. The adapters are the public API; the distribution is the model.

### Training: the "RLCD" analogue

Jev's RLCD rewards probabilities that match outcomes. With a discriminative head that **is** a
proper scoring rule, and its gradient is exact, so we optimise it directly:

- loss = log score of the realised integer high (+ small CRPS term, which rewards putting mass
  *near* the truth, useful for ordered bins)
- because every typed answer is a deterministic function of the distribution, a calibrated
  distribution gives calibrated answers to every question type at once
- RL would only be needed if outputs were sampled text; they are not, and we say so rather than
  borrowing the name

**Post-hoc:** temperature scaling on the validation fold; split-conformal intervals for Score.
**Seeds:** 5 per configuration, reported as mean and CI, never best-of.
**Search:** Optuna over a small space (width, depth, dropout, lr, CRPS weight), walk-forward CV only.

---

## 6 · Synthetic pretraining (G3): the Jev data recipe, made honest

Jev is trained entirely on synthetic data. Our analogue, at ~100× the real corpus:

1. **Physics corpus:** GFS MOS / NBM forecast vs CLI outcome for 150+ ASOS stations, 2015-2026,
   about 1M station-days. Real forecasts, real outcomes, no market.
2. **Market simulator:** for each synthetic station-day, generate a ladder in Kalshi's layout and
   quote it with a population of simulated traders: each holds the EMOS posterior plus private
   noise and a lag in absorbing new runs; quotes carry overround and spread drawn from the real
   panel's empirical distribution. Simulator parameters are fit to match real-ladder statistics
   (spread, overround, response to forecast revisions), and a check confirms those statistics match
   before any pretraining uses it.
3. **Stage A** pretrain on synthetic; **Stage B** fine-tune on real Kalshi.

The G3 ablation (learning curves at 10/25/50/100% of real data, with and without Stage A) decides
whether this stays. `causal-jepa` found its simulator flattered the objective; this gate exists so
that we find out, not assume.

---

## 7 · Evaluation

- **Splits:** walk-forward by month with a 2-day embargo. **Lockbox:** 2026-07-01 onward, scored
  once, at the end, by the final pre-registered configuration. It straddles the settlement switch,
  which is deliberate.
- **Unit of independence:** the date. All CIs are block bootstraps by date; model comparisons also
  report Diebold-Mariano on per-date score differences.
- **Slices:** city, season, read time, forecast surprise (|fcst − market mean|), market volume
  tercile, settlement regime.
- **Ablations:** −market, −forecast, −obs, −synthetic, −city embedding, untrained encoder.
- **Calibration:** reliability diagrams per head; ECE with the debiased estimator (the survey showed
  plain ECE is biased at these sample sizes).

### Trading backtest (G4)

Fee: Kalshi quadratic, `ceil(0.07 · C · P · (1−P))` per fill (`fee_multiplier = 1` for these series,
read from series metadata, not hardcoded). Decision: buy YES at the ask when
`p_model − ask > fee + margin`, symmetric for NO; size by fractional Kelly with a hard cap. **Fills**
are conservative: only at the quoted ask at the read time, and only up to a fraction of the
*following* hour's traded volume, since candles carry no depth. Report P&L, Sharpe by date, max
drawdown, turnover, edge per contract, and a capacity curve. The margin is tuned on validation,
never on the lockbox.

---

## 8 · Serving and MLOps

- **API:** `pmdecide.api`: pydantic schemas `DecisionRequest(state, questions: [Choice | Noul | Score])`
  -> `DecisionResponse(answers: [{value, probabilities, confidence}])`, served by FastAPI and
  callable as a library. Schema validation rejects questions outside the supported type system,
  like Jev.
- **No train/serve skew:** one feature function builds state for backfill and live; a test asserts
  live features equal backfilled features for the same timestamp once the day has settled.
- **Registry:** each model artifact carries git SHA, data manifest hash, config, and its eval
  report; promotion is champion/challenger on the trailing 60 days with a CI, never by eye.
- **Jobs:** daily ingest (settled events, new forecasts), scoring at each read time, a paper-trade
  ledger. GitHub Actions cron to start; nothing heavier until it hurts (`pm-jepa/PIPELINE.md`).
- **Monitoring:** rolling log score vs market, calibration drift per head, feature PSI, data
  freshness (missing forecast run = alarm), **contract-change detection** (hash of `rules_primary`
  per series; the TWC switch would have fired this), and new strike layouts.
- **Retraining:** monthly, or on a contract-change alarm.

---

## 9 · Engineering

`src/pmdecide/` library, `scripts/` one experiment per file writing `results/<name>.json` with config
inlined, `tests/` with unit tests for bucket math, point-in-time selection and no-leak invariants,
plus a 30-second end-to-end smoke. `ruff` + `pytest` in CI. Apache-2.0, matching `causal-jepa`.
Raw Kalshi data is not redistributed; scripts rebuild it from the public API.

**Compute:** everything through G2 runs on the M2 Max (tabular + small set-transformer, ~1-5M params).
Synthetic pretraining sweeps (G3) are the one place cloud credits help: a few spot GPU instances for
a day or two.

---

## 10 · Risks

| Risk | Mitigation |
|---|---|
| Market already prices MOS/NBM fully | G0 measures it before anything is built; obs at `d0_12` are a second, independent source |
| Settlement switch changes the label process | Kalshi labels only; regime slice; contract-change alarm |
| Edge exists but capacity is tiny (3-10¢ spreads, thin books) | capacity curve in G4; publish as a forecasting result if it does not survive |
| Overfitting 7 cities | synthetic pretraining on 150+ stations; per-city holdout as an extra slice |
| Leakage | point-in-time rules above, unit-tested; embargo; lockbox scored once |
| Forking paths | gates pre-registered here; corrections logged beside, not over, the original |

---

## 11 · Milestones

| Week | Deliverable |
|---|---|
| 1 | survey (done), panel + forecasts, **G0 result** |
| 2 | data validation suite, feature pipeline, baselines, **G1** |
| 3-4 | model v1, typed adapters, walk-forward eval, **G2** |
| 4-5 | synthetic corpus + market simulator, **G3** ablation |
| 6 | calibration, backtest, lockbox, **G4** |
| 6-10 | API, scheduled jobs, monitoring, 4-week shadow, **G5**; model card, findings record, release |
