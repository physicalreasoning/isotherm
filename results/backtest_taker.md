# Backtest

**Taker:** fills at the read-time quote, Kalshi quadratic fees, size capped at a share of post-read volume. **Maker:** rest at or inside the touch, filled only by later prints strictly through our price (no queue model needed). Both held to settlement; fixed $10,000 bankroll; daily PnL, Sharpe annualised by √365. **Headline = nested selection**: each quarter trades the config with the best Sharpe on earlier quarters only. See docs/EVALS.md for what each number can and cannot tell you.

## d0_08 · taker

| | |
|---|---|
| PnL (nested, out-of-sample) | **$-10,049** over 1095 days, 5941 trades |
| Sharpe (ann.) | **-1.01** [-2.36, 0.26] stationary bootstrap |
| Newey-West t | -1.55 |
| Deflated Sharpe | **0.000** (28 configs tried; ≥0.95 to believe) |
| PBO (CSCV) | **0.26** (924 splits; ≤0.2 to believe) |
| Max drawdown | $18,746 |
| Hit rate | 66.5% |
| Return on outlay | -2.29% |
| EV vs realised per contract | +0.0662 vs -0.0095 |
| Attribution | alpha vs mid $13,783 · spread $-14,896 · fees $-8,936 |

By period:

| Period | PnL | Trades | per contract |
|---|---:|---:|---:|
| 2023H2 | $829 | 518 | +0.0667 |
| 2024H1 | $70 | 555 | +0.0033 |
| 2024H2 | $2,169 | 284 | +0.0394 |
| 2025H1 | $2,537 | 876 | +0.0131 |
| 2025H2 | $-5,417 | 1301 | -0.0178 |
| 2026H1 | $-10,237 | 2407 | -0.0218 |

By city:

| City | PnL | Trades | per contract |
|---|---:|---:|---:|
| AUS | $-686 | 1222 | -0.0048 |
| CHI | $501 | 1299 | +0.0020 |
| DEN | $-2,434 | 637 | -0.0211 |
| LAX | $-1,750 | 715 | -0.0131 |
| MIA | $822 | 844 | +0.0070 |
| NY | $-4,089 | 664 | -0.0237 |
| PHIL | $-2,413 | 560 | -0.0191 |

Engine checks:

| Check | Trades | PnL | Losing trades |
|---|---:|---:|---:|
| oracle (must never lose) | 24685 | $1,194,529 | 0 |
| in-spread market (must not trade) | 0 | $0 | 0 |
| normalised mid | 3586 | $-13,001 | 1555 |
| noise_matched_turnover | 4988 | $-14,027 | 2218 |
| arbitrage_ladders | 718 | $0 | 0 |

Robustness (pool · all · θ 0.02):

| Scenario | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| base | $-2,857 | -0.23 | 4969 |
| slip +1¢ | $-8,570 | -0.88 | 3675 |
| slip +2¢ | $-13,500 | -1.81 | 2763 |
| fees ×1.5 | $-3,949 | -0.35 | 4253 |
| participation 1% | $-2,358 | -0.29 | 4865 |
| participation 20% | $-14,289 | -1.05 | 5001 |
| size ×10 | $-24,698 | -0.40 | 4969 |

Top configs over the full period (in-sample ceiling, not a result):

| Config | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| market (tempered) · θ 0.01 | $1,909 | 0.43 | 2721 |
| market (tempered) · kelly 0.50 | $1,615 | 0.42 | 7545 |
| market (tempered) · θ 0.02 | $1,059 | 0.32 | 1638 |
| market (tempered) · kelly 0.25 | $519 | 0.24 | 7515 |
| market (tempered) · kelly 0.10 | $-49 | -0.05 | 7413 |
| market (tempered) · θ 0.08 | $-277 | -0.19 | 559 |

## d0_12 · taker

| | |
|---|---|
| PnL (nested, out-of-sample) | **$11,071** over 1095 days, 7034 trades |
| Sharpe (ann.) | **0.47** [-0.84, 1.56] stationary bootstrap |
| Newey-West t | 0.70 |
| Deflated Sharpe | **0.005** (28 configs tried; ≥0.95 to believe) |
| PBO (CSCV) | **0.20** (924 splits; ≤0.2 to believe) |
| Max drawdown | $16,502 |
| Hit rate | 26.6% |
| Return on outlay | +2.78% |
| EV vs realised per contract | +0.2227 vs +0.0069 |
| Attribution | alpha vs mid $63,302 · spread $-38,663 · fees $-13,568 |

By period:

| Period | PnL | Trades | per contract |
|---|---:|---:|---:|
| 2023H2 | $414 | 348 | +0.0719 |
| 2024H1 | $87 | 221 | +0.0125 |
| 2024H2 | $20,685 | 1408 | +0.0425 |
| 2025H1 | $-3,445 | 3793 | -0.0041 |
| 2025H2 | $-7,074 | 1222 | -0.0275 |
| 2026H1 | $403 | 42 | +0.0605 |

By city:

| City | PnL | Trades | per contract |
|---|---:|---:|---:|
| AUS | $8,988 | 1390 | +0.0304 |
| CHI | $1,439 | 1130 | +0.0053 |
| DEN | $-2,131 | 932 | -0.0104 |
| LAX | $385 | 718 | +0.0025 |
| MIA | $-2,506 | 826 | -0.0115 |
| NY | $3,791 | 1235 | +0.0113 |
| PHIL | $1,105 | 803 | +0.0084 |

Engine checks:

| Check | Trades | PnL | Losing trades |
|---|---:|---:|---:|
| oracle (must never lose) | 18914 | $939,953 | 0 |
| in-spread market (must not trade) | 2 | $740 | 1 |
| normalised mid | 2169 | $3,577 | 1228 |
| noise_matched_turnover | 6341 | $-3,994 | 3005 |
| arbitrage_ladders | 378 | $0 | 0 |

Robustness (EMOS · NBM · kelly 0.50):

| Scenario | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| base | $-24,144 | -0.68 | 16323 |
| slip +1¢ | $-82,327 | -2.38 | 14883 |
| slip +2¢ | $-126,175 | -3.70 | 13662 |
| fees ×1.5 | $-35,653 | -1.03 | 15980 |
| participation 1% | $9,845 | 0.54 | 15484 |
| participation 20% | $-117,935 | -2.43 | 16621 |
| size ×10 | $47,529 | 0.52 | 16336 |

Top configs over the full period (in-sample ceiling, not a result):

| Config | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| market (tempered) · θ 0.04 | $2,043 | 1.31 | 513 |
| market (tempered) · θ 0.08 | $691 | 1.16 | 241 |
| market (tempered) · kelly 0.25 | $1,367 | 0.88 | 4708 |
| market (tempered) · kelly 0.50 | $2,522 | 0.88 | 4736 |
| market (tempered) · kelly 0.10 | $578 | 0.80 | 4625 |
| market (tempered) · θ 0.02 | $1,823 | 0.71 | 897 |

## d1_16 · taker

| | |
|---|---|
| PnL (nested, out-of-sample) | **$37,459** over 1089 days, 10720 trades |
| Sharpe (ann.) | **1.67** [0.60, 2.67] stationary bootstrap |
| Newey-West t | 2.84 |
| Deflated Sharpe | **0.619** (28 configs tried; ≥0.95 to believe) |
| PBO (CSCV) | **0.27** (924 splits; ≤0.2 to believe) |
| Max drawdown | $4,795 |
| Hit rate | 52.7% |
| Return on outlay | +4.84% |
| EV vs realised per contract | +0.0841 vs +0.0173 |
| Attribution | alpha vs mid $95,867 · spread $-37,326 · fees $-21,083 |

By period:

| Period | PnL | Trades | per contract |
|---|---:|---:|---:|
| 2023H2 | $220 | 847 | +0.0093 |
| 2024H1 | $2,333 | 647 | +0.0660 |
| 2024H2 | $3,151 | 479 | +0.0434 |
| 2025H1 | $12,346 | 3862 | +0.0142 |
| 2025H2 | $14,011 | 2511 | +0.0218 |
| 2026H1 | $5,397 | 2374 | +0.0102 |

By city:

| City | PnL | Trades | per contract |
|---|---:|---:|---:|
| AUS | $8,836 | 1537 | +0.0301 |
| CHI | $2,136 | 1753 | +0.0061 |
| DEN | $3,327 | 1241 | +0.0132 |
| LAX | $2,235 | 1399 | +0.0057 |
| MIA | $6,534 | 1821 | +0.0224 |
| NY | $5,494 | 1715 | +0.0158 |
| PHIL | $8,896 | 1254 | +0.0363 |

Engine checks:

| Check | Trades | PnL | Losing trades |
|---|---:|---:|---:|
| oracle (must never lose) | 29204 | $1,569,263 | 0 |
| in-spread market (must not trade) | 0 | $0 | 0 |
| normalised mid | 3446 | $-6,727 | 1238 |
| noise_matched_turnover | 8944 | $-24,416 | 3976 |
| arbitrage_ladders | 548 | $0 | 0 |

Robustness (EMOS · NBM · θ 0.02):

| Scenario | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| base | $21,914 | 0.58 | 17311 |
| slip +1¢ | $-31,243 | -0.95 | 15370 |
| slip +2¢ | $-68,330 | -2.42 | 13598 |
| fees ×1.5 | $3,869 | 0.11 | 16472 |
| participation 1% | $13,309 | 0.65 | 17126 |
| participation 20% | $-85,028 | -1.86 | 17385 |
| size ×10 | $-50,967 | -0.41 | 17311 |

Top configs over the full period (in-sample ceiling, not a result):

| Config | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| pool · all · θ 0.01 | $36,628 | 2.07 | 8453 |
| market (tempered) · kelly 0.50 | $6,035 | 1.69 | 7117 |
| pool · all · θ 0.02 | $21,878 | 1.51 | 5793 |
| pool · all · kelly 0.10 | $4,396 | 1.49 | 10862 |
| pool · all · kelly 0.25 | $10,026 | 1.41 | 10990 |
| market (tempered) · kelly 0.25 | $2,916 | 1.39 | 7083 |
