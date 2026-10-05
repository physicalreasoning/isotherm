# Backtest: daily lows

**Taker:** fills at the read-time quote, Kalshi quadratic fees, size capped at a share of post-read volume. **Maker:** rest at or inside the touch, filled only by later prints strictly through our price (no queue model needed). Both held to settlement; fixed $10,000 bankroll; daily PnL, Sharpe annualised by √365. **Headline = nested selection**: each quarter trades the config with the best Sharpe on earlier quarters only. See docs/EVALS.md for what each number can and cannot tell you.

## d1_16 · taker

| | |
|---|---|
| PnL (nested, out-of-sample) | **$13,384** over 212 days, 2528 trades |
| Sharpe (ann.) | **6.12** [3.08, 9.30] stationary bootstrap |
| Newey-West t | 4.24 |
| Deflated Sharpe | **0.980** (28 configs tried; ≥0.95 to believe) |
| PBO (CSCV) | **0.06** (924 splits; ≤0.2 to believe) |
| Max drawdown | $1,074 |
| Hit rate | 68.5% |
| Return on outlay | +9.11% |
| EV vs realised per contract | +0.0371 vs +0.0509 |
| Attribution | alpha vs mid $18,899 · spread $-2,655 · fees $-2,860 |

By period:

| Period | PnL | Trades | per contract |
|---|---:|---:|---:|
| 2026H1 | $8,625 | 2005 | +0.0432 |
| 2026H2 | $4,759 | 523 | +0.0752 |

By city:

| City | PnL | Trades | per contract |
|---|---:|---:|---:|
| AUS | $3,624 | 279 | +0.1256 |
| CHI | $-521 | 328 | -0.0125 |
| DEN | $3,695 | 358 | +0.1067 |
| LAX | $1,908 | 444 | +0.0478 |
| MIA | $-476 | 443 | -0.0115 |
| NY | $3,459 | 363 | +0.0712 |
| PHIL | $1,695 | 313 | +0.0606 |

Engine checks:

| Check | Trades | PnL | Losing trades |
|---|---:|---:|---:|
| oracle (must never lose) | 8177 | $375,335 | 0 |
| in-spread market (must not trade) | 0 | $0 | 0 |
| normalised mid | 318 | $819 | 171 |
| noise_matched_turnover | 2003 | $615 | 1032 |
| arbitrage_ladders | 190 | $0 | 0 |

Robustness (pool · market+GFS · θ 0.01):

| Scenario | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| base | $19,806 | 6.81 | 2226 |
| slip +1¢ | $10,753 | 4.02 | 1223 |
| slip +2¢ | $7,293 | 3.24 | 737 |
| fees ×1.5 | $13,458 | 4.81 | 1785 |
| participation 1% | $3,262 | 2.41 | 2215 |
| participation 20% | $16,323 | 4.44 | 2227 |
| size ×10 | $10,626 | 1.42 | 2226 |

Top configs over the full period (in-sample ceiling, not a result):

| Config | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| pool · market+GFS · θ 0.01 | $19,806 | 6.81 | 2226 |
| pool · all · θ 0.01 | $17,554 | 6.32 | 2159 |
| pool · market+GFS · θ 0.02 | $13,408 | 4.81 | 1211 |
| pool · all · θ 0.02 | $11,088 | 4.70 | 1160 |
| pool · market+GFS · θ 0.04 | $8,281 | 3.83 | 475 |
| market (tempered) · kelly 0.10 | $758 | 3.71 | 2344 |

## d1_22 · taker

| | |
|---|---|
| PnL (nested, out-of-sample) | **$5,450** over 212 days, 1346 trades |
| Sharpe (ann.) | **3.49** [0.68, 6.16] stationary bootstrap |
| Newey-West t | 2.45 |
| Deflated Sharpe | **0.675** (28 configs tried; ≥0.95 to believe) |
| PBO (CSCV) | **0.31** (924 splits; ≤0.2 to believe) |
| Max drawdown | $941 |
| Hit rate | 68.9% |
| Return on outlay | +7.46% |
| EV vs realised per contract | +0.0421 vs +0.0437 |
| Attribution | alpha vs mid $8,506 · spread $-1,614 · fees $-1,442 |

By period:

| Period | PnL | Trades | per contract |
|---|---:|---:|---:|
| 2026H1 | $3,729 | 1136 | +0.0395 |
| 2026H2 | $1,721 | 210 | +0.0566 |

By city:

| City | PnL | Trades | per contract |
|---|---:|---:|---:|
| AUS | $1,864 | 162 | +0.1387 |
| CHI | $376 | 170 | +0.0212 |
| DEN | $2,084 | 186 | +0.1308 |
| LAX | $1,030 | 275 | +0.0457 |
| MIA | $-624 | 228 | -0.0297 |
| NY | $644 | 197 | +0.0259 |
| PHIL | $76 | 128 | +0.0082 |

Engine checks:

| Check | Trades | PnL | Losing trades |
|---|---:|---:|---:|
| oracle (must never lose) | 7622 | $340,528 | 0 |
| in-spread market (must not trade) | 0 | $0 | 0 |
| normalised mid | 304 | $21 | 154 |
| noise_matched_turnover | 1141 | $623 | 602 |
| arbitrage_ladders | 105 | $0 | 0 |

Robustness (pool · market+GFS · θ 0.02):

| Scenario | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| base | $9,395 | 4.50 | 782 |
| slip +1¢ | $4,558 | 2.78 | 487 |
| slip +2¢ | $2,584 | 1.82 | 305 |
| fees ×1.5 | $5,541 | 3.16 | 596 |
| participation 1% | $2,197 | 2.41 | 781 |
| participation 20% | $6,620 | 2.75 | 782 |
| size ×10 | $11,173 | 1.98 | 782 |

Top configs over the full period (in-sample ceiling, not a result):

| Config | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| pool · market+GFS · θ 0.02 | $9,395 | 4.50 | 782 |
| market (tempered) · θ 0.02 | $3,472 | 3.70 | 310 |
| pool · market+GFS · θ 0.01 | $8,857 | 3.58 | 1570 |
| pool · market+GFS · kelly 0.10 | $1,236 | 3.11 | 2827 |
| pool · all · θ 0.04 | $4,546 | 3.00 | 323 |
| market (tempered) · kelly 0.10 | $519 | 2.88 | 2232 |
