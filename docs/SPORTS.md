# Sports · MLB game winners

**Question:** does the pipeline that found a decaying edge in weather ladders find anything in the
runner-up domain from `docs/01-market-selection.md`?
**Market:** Kalshi `KXMLBGAME`, one market per team per game, two per event, mutually exclusive.
**Answer:** no. Free baseball data adds nothing the market does not already price, and no execution
style turns it into a strategy that survives deflation and overfitting checks.

## Data

| | |
|---|---|
| Settled events | 4,658, from 2025-04-16 (Kalshi's first MLB game market) to 2026-10-04 |
| Excluded | 11 resolved 50/50 (`scalar`); 67 no matching MLB game; 41 unknown team or date; 34 doubleheaders the ticker cannot disambiguate; 24 start-time mismatches; 8 not played as scheduled |
| Linked and usable | **4,484 games (96.3%)**, each tied to an MLB Stats API `gamePk` and its scheduled first pitch |
| Panel | 26,904 rows (game × team × read), 0 failed candle fetches |
| Labels | Kalshi `result`; agrees with the official MLB result on **100%** of rows |
| Quotes | 1-minute candles, read at T−24h, T−3h, T−15min before scheduled first pitch. T−24h is quoted for only 48% of games: 2025 markets opened the morning of the game |
| Liquidity | median volume 1.23M contracts per game; median spread **1¢** at every read |
| Trades (maker fills) | 5.21M prints over 8,967 markets, restricted to the only windows a pre-game order can rest in, [T−24h, T−20h] and [T−3h, T] |
| Fees | taker quadratic 0.07; **maker 0.0175** (`quadratic_with_maker_fees`, unlike the weather series) |

## Exogenous model: free and point-in-time

All from the MLB Stats API (no key), frozen before the first Kalshi game and applied unchanged after:

- **Elo**, day-batched (a doubleheader's first game cannot inform the second), K = 5, home advantage
  24, 25% reversion between seasons, tuned on 2016-2019 after a 2012-2015 warm-up.
- **Starting pitchers:** regressed FIP from appearances strictly before the game day plus half of
  last season, shrunk toward the league mean with 40 pseudo-innings; unknown starters get the mean.
- **Elo + starters:** logistic regression on the Elo logit and the starters' FIP gap, fit 2017-2024.

| Log loss (home win) | Coin | Elo | Elo + starters |
|---|---:|---:|---:|
| 2021-2024 check seasons (9,879 games) | 0.6915 | 0.6778 | 0.6759 |
| Kalshi period, frozen model (4,920 games) | 0.6905 | 0.6818 | 0.6802 |

## Gate 0: fails at every read time

`scripts/sports_benchmark.py`. Monthly walk-forward from 2025-07, lockbox from 2026-09-01 (the last
weeks of the 2026 season and the postseason, untouched), identical rows, date-block CIs.

| Read | Ladders | Market | Elo + starters | Best pool | Δ best pool vs market [95% CI] |
|---|---:|---:|---:|---:|---|
| T−24h | 1,505 | **0.6818** | 0.6830 | 0.6823 | −0.0005 [−0.0025, +0.0016] |
| T−3h | 3,167 | 0.6821 | 0.6838 | 0.6821 | +0.0001 [−0.0015, +0.0014] |
| T−15min | 3,167 | 0.6819 | 0.6838 | 0.6818 | +0.0001 [−0.0011, +0.0012] |

Every market + model pool lands within ±0.001 nats of the market; every CI straddles zero; every
Diebold-Mariano p > 0.3. The last-12-months slice says the same. The tempered market gains nothing
either, so the market is not even miscalibrated in a way two parameters can fix. The free model
alone is 0.001 to 0.003 nats *worse* than the market. **Gate 0, as registered and amended: FAIL.**

## Backtests

`scripts/sports_backtest.py`: the weather engine and protocol unchanged (nested selection, Deflated
Sharpe, PBO by CSCV, engine checks, attribution, robustness), with ~15 concurrent games per day and
orders cancelled at first pitch. Full tables: `results/sports_backtest.md`.

| Read | Taker nested PnL | Sharpe | DSR | PBO | Maker nested PnL | Sharpe | DSR | PBO |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| T−24h | −$987 | −0.73 | 0.02 | 0.41 | +$362 | 0.34 | 0.13 | 0.43 |
| T−3h | −$1,626 | −0.48 | 0.03 | 0.49 | +$3,826 | 1.22 [−0.99, 3.48] | 0.14 | 0.35 |
| T−15min | +$384 | 0.15 | 0.13 | 0.44 | −$1,290 | −0.61 | 0.02 | 0.34 |

Nothing clears either bar (DSR ≥ 0.95, PBO ≤ 0.2). PBO of 0.34-0.49 means choosing among the
configurations is close to a coin flip. The one positive-looking cell, T−3h maker, is positive in
2025 H2 and 2026 H1 and negative in 2026 H2, its Sharpe CI includes zero, and it moves within a few
thousand dollars of the information-free market maker (−$2,303) and matched-turnover noise (+$1).

**Engine checks pass everywhere:** oracle never loses (2,372-6,334 trades per cell), the in-spread
coherent market never trades as a taker, normalised-mid and noise baselines behave as expected.

## Verdict

MLB game winners on Kalshi are what the market survey predicted: the deepest, tightest market in the
sample (1¢ spreads, a million contracts a game) and the most efficient. A warm Elo model with
point-in-time starting pitchers, the standard free public model, is fully priced. Unlike weather,
there was no historical window in which the free information was underpriced; the market started
efficient. Beating it would need information that is not free (lineups at lock, bullpen usage,
weather at the park, sharp-book odds), and a backtest on these numbers says the bar is high.

## Caveats

- **History is short:** 1.5 seasons, Kalshi's whole MLB history. CIs are correspondingly wide.
- **Probable pitchers:** the archived `probablePitcher` is the listed starter; a late scratch can
  make it differ from what was public pre-game. This can only flatter the model, and it still loses.
- **Maker fills** are trade-through only (a lower bound on fills, an upper bound on adverse
  selection), as in weather; the touch variant is reported in the robustness tables.
- **Lockbox** (2026-09-01 on) has not been scored.

## Reproduce

```bash
uv run scripts/sports_fetch_mlb.py        # MLB schedules 2012+, starters' game logs (free API)
uv run scripts/sports_build_panel.py      # Kalshi events, links, 1-minute candle panel
uv run scripts/sports_ratings.py          # Elo + starters, frozen pre-2025
uv run scripts/sports_benchmark.py        # Gate 0
uv run scripts/sports_fetch_trades.py     # pre-game prints for the maker fill model
uv run scripts/sports_backtest.py         # taker + maker, nested, DSR, PBO
```
