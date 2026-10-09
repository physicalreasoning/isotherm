# A prediction-market forecasting benchmark: plan (2026-10-09)

Merchant et al. (2026, arXiv 2610.09048) built Market-1T and a fixed evaluation protocol for
equities. Nothing comparable exists for prediction markets. isotherm already has most of the
pieces: point-in-time ladder builders, label audits against official sources, walk-forward
splits, proper scoring against the market's own price, and the §41 lesson about mid prices.

## What it measures

One question for every model: **does it add information to the market's own price, at a fixed
time before close, out of sample?** Scored with proper scoring rules (log score; RPS for ordered
ladders; Brier for yes/no), against the market at the same timestamp, by date-block bootstrap, and
broken down by month (the month explains 97-99% of variance, §45).

## Scope, v1

About 12 series chosen for volume, history and label clarity, sampled across time:

| Family | Series | Type | Outside data (point in time) |
|---|---|---|---|
| Weather | daily highs (7 cities), lows, KXRAIN | ladder, yes/no | NBM and GFS MOS (have) |
| Financial | KXINX, KXNASDAQ100, KXEURUSD, KXUSDJPY (daily) | ladder | index / FX level, realised vol (free daily) |
| Commodities | KXWTI, KXGOLD (daily if listed) | ladder | futures level (free daily) |
| Economics | KXCPI, KXJOBLESSCLAIMS, KXFED | ladder | none in v1 |
| Gas | KXAAAGASD | threshold ladder | RBOB (have) |

Up to 400 settled events per series, stratified over the series' life. Snapshots at four leads
before close (24 h, 6 h, 1 h, and the open) with bid, ask, mid, volume and open interest per
bucket; settlement value and result; rules text and resolution source.

**Cost.** Events after Kalshi's historical cutoff (2026-08-10) take one request each (event
candlesticks); older ones about 15 (per-market historical candles). About 70,000 requests: an
overnight fetch at the polite rate already in `kalshi.py`. Free data only.

## Baselines

The market (mid); the market priced at its bids (§41); the market sharpened by one fitted
exponent; a base rate per series; an outside-data-only calibrated model where outside data exist;
a log pool of market and outside model (isotherm's design); and, following Merchant et al., a
random-feature model with a fitted head as the representation floor.

## Protocol

Quarterly walk-forward, two-day embargo, every fit on earlier dates only. Label audit per series
(Kalshi's settlement value against the official source where one is public). A frozen test
period at the end, scored once. Results reported per series, per family, and pooled, with
month-against-seed variance.

## Release

Code, event lists, labels and a script that rebuilds every snapshot from Kalshi's public API.
Raw Kalshi price snapshots are released only if Kalshi's terms allow redistribution (to be
confirmed first). Outside data are free public sources (NOAA/IEM, Yahoo daily, EIA).

## Order of work

1. Fetcher for the 12 series (event candlesticks after the cutoff, per-market before), with label audit. One night.
2. Baselines and protocol on weather and financial families, where results already exist to check against (§33-43). Two to three days.
3. The remaining families, a results table, and a short write-up. About a week.
4. Release decision after the terms check.
