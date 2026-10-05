# MLB backtest

**Taker:** fills at the read-time quote, Kalshi quadratic fees, size capped at a share of post-read volume. **Maker:** rest at or inside the touch, filled only by later prints strictly through our price (no queue model needed). Both held to settlement; fixed $10,000 bankroll; daily PnL, Sharpe annualised by √365. **Headline = nested selection**: each quarter trades the config with the best Sharpe on earlier quarters only. See docs/EVALS.md for what each number can and cannot tell you.

## t_15m · taker

| | |
|---|---|
| PnL (nested, out-of-sample) | **$384** over 263 days, 759 trades |
| Sharpe (ann.) | **0.15** [-2.08, 2.11] stationary bootstrap |
| Newey-West t | 0.12 |
| Deflated Sharpe | **0.125** (28 configs tried; ≥0.95 to believe) |
| PBO (CSCV) | **0.44** (924 splits; ≤0.2 to believe) |
| Max drawdown | $2,879 |
| Hit rate | 41.8% |
| Return on outlay | +0.96% |
| EV vs realised per contract | +0.0557 vs +0.0041 |
| Attribution | alpha vs mid $2,385 · spread $-472 · fees $-1,529 |

By period:

| Period | PnL | Trades | per contract |
|---|---:|---:|---:|
| 2025H2 | $569 | 438 | +0.0291 |
| 2026H1 | $-79 | 234 | -0.0015 |
| 2026H2 | $-107 | 87 | -0.0055 |

By city:

| City | PnL | Trades | per contract |
|---|---:|---:|---:|
| MLB | $384 | 759 | +0.0041 |

Engine checks:

| Check | Trades | PnL | Losing trades |
|---|---:|---:|---:|
| oracle (must never lose) | 6283 | $496,186 | 0 |
| in-spread market (must not trade) | 0 | $0 | 0 |
| normalised mid | 0 | $0 | 0 |
| noise_matched_turnover | 452 | $444 | 214 |
| arbitrage_ladders | 11 | $0 | 0 |

Robustness (Elo + starters · θ 0.04):

| Scenario | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| base | $3,563 | 1.19 | 665 |
| slip +1¢ | $13 | 0.01 | 377 |
| slip +2¢ | $-2,486 | -1.54 | 179 |
| fees ×1.5 | $306 | 0.13 | 414 |
| participation 1% | $1,424 | 0.58 | 655 |
| participation 20% | $3,656 | 1.11 | 668 |
| size ×10 | $3,503 | 0.16 | 665 |

Top configs over the full period (in-sample ceiling, not a result):

| Config | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| Elo + starters · θ 0.04 | $3,563 | 1.19 | 665 |
| pool · market+Elo+SP · θ 0.02 | $1,091 | 1.07 | 37 |
| market (tempered) · θ 0.02 | $330 | 0.36 | 34 |
| pool · all · θ 0.08 | $0 | 0.00 | 0 |
| pool · market+Elo+SP · θ 0.04 | $0 | 0.00 | 0 |
| pool · market+Elo+SP · θ 0.08 | $0 | 0.00 | 0 |

## t_15m · maker

| | |
|---|---|
| PnL (nested, out-of-sample) | **$-1,290** over 263 days, 432 trades |
| Sharpe (ann.) | **-0.61** [-2.94, 1.78] stationary bootstrap |
| Newey-West t | -0.56 |
| Deflated Sharpe | **0.024** (32 configs tried; ≥0.95 to believe) |
| PBO (CSCV) | **0.34** (924 splits; ≤0.2 to believe) |
| Max drawdown | $2,354 |
| Hit rate | 42.6% |
| Return on outlay | -3.51% |
| EV vs realised per contract | +0.0370 vs -0.0150 |
| Attribution | alpha vs mid $-1,298 · spread $367 · fees $-359 |

By period:

| Period | PnL | Trades | per contract |
|---|---:|---:|---:|
| 2025H2 | $-1,260 | 253 | -0.0248 |
| 2026H1 | $759 | 151 | +0.0274 |
| 2026H2 | $-788 | 28 | -0.1082 |

By city:

| City | PnL | Trades | per contract |
|---|---:|---:|---:|
| MLB | $-1,290 | 432 | -0.0150 |

Engine checks:

| Check | Trades | PnL | Losing trades |
|---|---:|---:|---:|
| oracle (must never lose) | 864 | $75,095 | 0 |
| uninformed market maker | 1119 | $-2,230 | 578 |
| noise_matched_turnover | 474 | $1,894 | 231 |

Robustness (Elo + starters · maker θ 0.02 · 1h):

| Scenario | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| base: trade-through fills | $2,560 | 1.08 | 547 |
| touch fills, 50% queue share | $8,152 | 1.21 | 3382 |
| maker fee 0.0175 | $2,560 | 1.08 | 547 |
| no price improvement | $1,056 | 0.47 | 461 |
| horizon 1h | $2,560 | 1.08 | 547 |
| horizon to close | $2,560 | 1.08 | 547 |
| size ×10 | $1,043 | 0.06 | 547 |

Top configs over the full period (in-sample ceiling, not a result):

| Config | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| pool · market+Elo+SP · maker θ 0.02 · 1h | $2,556 | 1.66 | 148 |
| pool · market+Elo+SP · maker θ 0.02 · 4h | $2,556 | 1.66 | 148 |
| market (tempered) · maker θ 0.02 · 1h | $1,729 | 1.22 | 116 |
| market (tempered) · maker θ 0.02 · 4h | $1,729 | 1.22 | 116 |
| Elo + starters · maker θ 0.02 · 1h | $2,560 | 1.08 | 547 |
| Elo + starters · maker θ 0.02 · 4h | $2,560 | 1.08 | 547 |

## t_24h · taker

| | |
|---|---|
| PnL (nested, out-of-sample) | **$-987** over 119 days, 621 trades |
| Sharpe (ann.) | **-0.73** [-5.29, 2.66] stationary bootstrap |
| Newey-West t | -0.38 |
| Deflated Sharpe | **0.024** (28 configs tried; ≥0.95 to believe) |
| PBO (CSCV) | **0.41** (252 splits; ≤0.2 to believe) |
| Max drawdown | $2,570 |
| Hit rate | 45.2% |
| Return on outlay | -3.58% |
| EV vs realised per contract | +0.0380 vs -0.0175 |
| Attribution | alpha vs mid $273 · spread $-306 · fees $-954 |

By period:

| Period | PnL | Trades | per contract |
|---|---:|---:|---:|
| 2026H1 | $-83 | 357 | -0.0270 |
| 2026H2 | $-905 | 264 | -0.0169 |

By city:

| City | PnL | Trades | per contract |
|---|---:|---:|---:|
| MLB | $-987 | 621 | -0.0175 |

Engine checks:

| Check | Trades | PnL | Losing trades |
|---|---:|---:|---:|
| oracle (must never lose) | 2837 | $258,043 | 0 |
| in-spread market (must not trade) | 0 | $0 | 0 |
| normalised mid | 93 | $-1,028 | 57 |
| noise_matched_turnover | 672 | $-1,445 | 343 |
| arbitrage_ladders | 38 | $0 | 0 |

Robustness (Elo + starters · θ 0.02):

| Scenario | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| base | $508 | 0.26 | 615 |
| slip +1¢ | $2,009 | 1.43 | 372 |
| slip +2¢ | $355 | 0.33 | 203 |
| fees ×1.5 | $2,425 | 1.61 | 406 |
| participation 1% | $508 | 0.26 | 615 |
| participation 20% | $508 | 0.26 | 615 |
| size ×10 | $5,136 | 0.26 | 615 |

Top configs over the full period (in-sample ceiling, not a result):

| Config | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| market (tempered) · θ 0.08 | $269 | 1.50 | 6 |
| Elo + starters · θ 0.04 | $1,125 | 1.00 | 204 |
| pool · all · θ 0.04 | $383 | 0.80 | 43 |
| Elo + starters · kelly 0.10 | $15 | 0.30 | 987 |
| Elo + starters · θ 0.02 | $508 | 0.26 | 615 |
| Elo + starters · θ 0.08 | $84 | 0.26 | 13 |

## t_24h · maker

| | |
|---|---|
| PnL (nested, out-of-sample) | **$362** over 119 days, 282 trades |
| Sharpe (ann.) | **0.34** [-3.36, 3.92] stationary bootstrap |
| Newey-West t | 0.18 |
| Deflated Sharpe | **0.125** (32 configs tried; ≥0.95 to believe) |
| PBO (CSCV) | **0.43** (252 splits; ≤0.2 to believe) |
| Max drawdown | $1,245 |
| Hit rate | 46.1% |
| Return on outlay | +1.89% |
| EV vs realised per contract | +0.0441 vs +0.0080 |
| Attribution | alpha vs mid $361 · spread $190 · fees $-190 |

By period:

| Period | PnL | Trades | per contract |
|---|---:|---:|---:|
| 2026H1 | $-850 | 195 | -0.0276 |
| 2026H2 | $1,212 | 87 | +0.0840 |

By city:

| City | PnL | Trades | per contract |
|---|---:|---:|---:|
| MLB | $362 | 282 | +0.0080 |

Engine checks:

| Check | Trades | PnL | Losing trades |
|---|---:|---:|---:|
| oracle (must never lose) | 883 | $63,052 | 0 |
| uninformed market maker | 870 | $-5,785 | 470 |
| noise_matched_turnover | 257 | $-2,850 | 141 |

Robustness (Elo + starters · maker θ 0.04 · 4h):

| Scenario | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| base: trade-through fills | $917 | 1.04 | 207 |
| touch fills, 50% queue share | $2,325 | 1.55 | 609 |
| maker fee 0.0175 | $917 | 1.04 | 207 |
| no price improvement | $291 | 0.38 | 168 |
| horizon 1h | $-526 | -1.28 | 102 |
| horizon to close | $467 | 0.35 | 319 |
| size ×10 | $-76 | -0.01 | 207 |

Top configs over the full period (in-sample ceiling, not a result):

| Config | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| Elo + starters · maker θ 0.04 · 4h | $917 | 1.04 | 207 |
| pool · market+Elo+SP · maker θ 0.00 · 1h | $-325 | -0.39 | 385 |
| Elo + starters · maker θ 0.02 · 4h | $-1,011 | -0.77 | 478 |
| Elo + starters · maker θ 0.02 · 1h | $-622 | -0.88 | 222 |
| Elo + starters · maker θ 0.04 · 1h | $-526 | -1.28 | 102 |
| market (tempered) · maker θ 0.01 · 1h | $-863 | -1.36 | 239 |

## t_3h · taker

| | |
|---|---|
| PnL (nested, out-of-sample) | **$-1,626** over 263 days, 1137 trades |
| Sharpe (ann.) | **-0.48** [-2.83, 1.80] stationary bootstrap |
| Newey-West t | -0.38 |
| Deflated Sharpe | **0.027** (28 configs tried; ≥0.95 to believe) |
| PBO (CSCV) | **0.49** (924 splits; ≤0.2 to believe) |
| Max drawdown | $4,806 |
| Hit rate | 44.0% |
| Return on outlay | -2.25% |
| EV vs realised per contract | +0.0411 vs -0.0103 |
| Attribution | alpha vs mid $1,840 · spread $-808 · fees $-2,658 |

By period:

| Period | PnL | Trades | per contract |
|---|---:|---:|---:|
| 2025H2 | $-1,769 | 526 | -0.0681 |
| 2026H1 | $143 | 611 | +0.0011 |

By city:

| City | PnL | Trades | per contract |
|---|---:|---:|---:|
| MLB | $-1,626 | 1137 | -0.0103 |

Engine checks:

| Check | Trades | PnL | Losing trades |
|---|---:|---:|---:|
| oracle (must never lose) | 6334 | $569,444 | 0 |
| in-spread market (must not trade) | 0 | $0 | 0 |
| normalised mid | 1 | $-100 | 1 |
| noise_matched_turnover | 1352 | $-6,124 | 676 |
| arbitrage_ladders | 10 | $0 | 0 |

Robustness (Elo + starters · θ 0.02):

| Scenario | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| base | $4,224 | 0.83 | 1651 |
| slip +1¢ | $790 | 0.20 | 1043 |
| slip +2¢ | $533 | 0.19 | 593 |
| fees ×1.5 | $959 | 0.24 | 1112 |
| participation 1% | $2,546 | 0.56 | 1651 |
| participation 20% | $4,416 | 0.85 | 1651 |
| size ×10 | $12,611 | 0.29 | 1651 |

Top configs over the full period (in-sample ceiling, not a result):

| Config | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| pool · market+Elo+SP · θ 0.04 | $217 | 1.18 | 1 |
| Elo + starters · θ 0.04 | $2,971 | 1.00 | 594 |
| Elo + starters · θ 0.02 | $4,224 | 0.83 | 1651 |
| pool · all · θ 0.01 | $775 | 0.21 | 781 |
| pool · all · kelly 0.10 | $9 | 0.19 | 980 |
| pool · all · kelly 0.25 | $18 | 0.14 | 1367 |

## t_3h · maker

| | |
|---|---|
| PnL (nested, out-of-sample) | **$3,826** over 263 days, 743 trades |
| Sharpe (ann.) | **1.22** [-0.99, 3.48] stationary bootstrap |
| Newey-West t | 0.95 |
| Deflated Sharpe | **0.141** (32 configs tried; ≥0.95 to believe) |
| PBO (CSCV) | **0.35** (924 splits; ≤0.2 to believe) |
| Max drawdown | $3,622 |
| Hit rate | 44.4% |
| Return on outlay | +5.66% |
| EV vs realised per contract | +0.0492 vs +0.0234 |
| Attribution | alpha vs mid $3,771 · spread $734 · fees $-679 |

By period:

| Period | PnL | Trades | per contract |
|---|---:|---:|---:|
| 2025H2 | $4,952 | 408 | +0.0549 |
| 2026H1 | $752 | 198 | +0.0174 |
| 2026H2 | $-1,878 | 137 | -0.0628 |

By city:

| City | PnL | Trades | per contract |
|---|---:|---:|---:|
| MLB | $3,826 | 743 | +0.0234 |

Engine checks:

| Check | Trades | PnL | Losing trades |
|---|---:|---:|---:|
| oracle (must never lose) | 2372 | $222,708 | 0 |
| uninformed market maker | 3453 | $-2,303 | 1740 |
| noise_matched_turnover | 575 | $1 | 291 |

Robustness (Elo + starters · maker θ 0.04 · 4h):

| Scenario | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| base: trade-through fills | $5,293 | 1.76 | 645 |
| touch fills, 50% queue share | $11,142 | 2.18 | 1740 |
| maker fee 0.0175 | $5,293 | 1.76 | 645 |
| no price improvement | $3,728 | 1.32 | 608 |
| horizon 1h | $1,640 | 1.05 | 264 |
| horizon to close | $5,293 | 1.76 | 645 |
| size ×10 | $36,720 | 1.42 | 645 |

Top configs over the full period (in-sample ceiling, not a result):

| Config | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| pool · market+Elo+SP · maker θ 0.02 · 4h | $7,250 | 2.06 | 655 |
| Elo + starters · maker θ 0.04 · 4h | $5,293 | 1.76 | 645 |
| pool · all · maker θ 0.01 · 4h | $7,916 | 1.68 | 1521 |
| market (tempered) · maker θ 0.02 · 4h | $5,249 | 1.58 | 555 |
| pool · market+Elo+SP · maker θ 0.00 · 4h | $7,517 | 1.32 | 2330 |
| market (tempered) · maker θ 0.00 · 4h | $7,446 | 1.30 | 2289 |
