# Model card

Two models live in this repo. The **served model** is small and frozen, and is the one the lockbox
tested, the shadow record tracks and the API serves. **isotherm** is the research model: better
probabilities, not yet frozen or live.

## Served model: `pool · market+GFS` (frozen)

| | |
|---|---|
| Version | `shadow/frozen.json`, hash `b200c51ce4ee` |
| Fit on | every Kalshi daily-high ladder before 2026-06-29 (7,008 ladders at the 16:00 read) |
| Form | log pool: p ∝ p_market^1.073 · p_EMOS-GFS^0.294, renormalised over the ladder |
| EMOS | per city, high ~ N(a + b · GFS MOS max, σ(day of year)), fit by interval likelihood on NWS CLI highs 2015 to 2026-06-29 |
| Read time | 16:00 local the day before |
| Serving | `uv run uvicorn isotherm.serve:app` (`/health`, `/ladder/{city}`, `/decide`) |

### Intended use

Research on how prediction markets price public information, and as the frozen subject of the
live shadow record. The output is a calibrated probability for each bucket of a Kalshi daily-high
ladder, and typed answers (Choice, Noul, Score) derived from one distribution.

### Not intended for

Trading real money. The edge is about one to two cents per contract, it has been shrinking month
by month, and it has not yet been confirmed live (see below). Not a weather forecast: it consumes
NWS forecasts, it does not improve them.

### Inputs (all public at the read time)

Live Kalshi ladder quotes (bid and ask per bucket) and the latest GFS MOS daytime max already on
the wire (run time + 5 h). No observations are used at this read.

### Outputs

Bucket probabilities. The API spreads them over integer highs using the EMOS Gaussian as the
within-bucket shape, so any threshold, range or quantile question is answered from the same
distribution and stays consistent with the bucket prices.

### Evaluation

| Test | Result |
|---|---|
| Walk-forward log score vs market, last 12 months, 16:00 read | +0.020 nats [+0.012, +0.026] |
| Nested walk-forward backtest, taker (2023-07 to 2026-06) | +$22,122, Sharpe 2.05 [0.81, 3.27], deflated Sharpe 0.85, PBO 0.26 |
| Lockbox, scored once (2026-07-01 to 2026-10-03) | **pass**: +$1,851, Newey-West t 1.77, hit rate 80%; log score +0.014 [+0.001, +0.027] |
| Lockbox by month | July +$1,029, August +$517, September +$246 |

Engine checks held in every run: the oracle never loses, a coherent in-spread market never trades,
and noise with matched turnover loses. Full record: `FINDINGS.md` §8-10.

## Research model: isotherm

| | |
|---|---|
| Code | `src/isotherm/model.py` |
| Form | per bucket: learned log pool of market, EMOS-GFS, EMOS-NBM, EMOS-NBM conditioned on today's observed max, climatology; plus an MLP correction over bucket and context features; softmax over the ladder |
| Training | log score, sample weights halving every 365 days, initialised to equal the market, early stopping on the latest 15% of dates, 5-seed ensemble |
| Result | +0.033 to +0.071 nats vs the market across read times; best calibrated model (debiased ECE 0.004 to 0.007); positive in every half-year |
| Control | the same network trained on labels sampled from the market scores within ±0.002 of the market |

## Data

Kalshi public market data (ladders, hourly candles, trades) and Iowa Environmental Mesonet
archives of NWS products (GFS MOS, NBM, daily climate reports, METAR). Labels are Kalshi's own
`result`. Raw data is not redistributed; scripts rebuild it from the public APIs.

## Known risks

- **Decay.** The 2023 edge went to zero within about 18 months, and lockbox PnL halved each month.
- **Settlement source.** Kalshi moved from the NWS climate report to The Weather Company on
  2026-08-14. Agreement with NWS has been near perfect since, with one 5°F exception in Miami.
- **Capacity.** Spreads of 1 to 10 cents and thin books cap the size this could ever trade.
- **Live vs backtest prices.** Backtests read hourly candle closes; live scoring reads the book.

## Monitoring

The shadow job scores every city daily at 16:00 local and settles the next morning. Its report
carries a rolling 30-day log score gain with a date-block CI, PnL by month and settlement source,
and a status: `INSUFFICIENT_DATA`, `OK`, or `STOP` once the last two 30-day windows both sit fully
below zero. Ledger: the `shadow-ledger` branch.
