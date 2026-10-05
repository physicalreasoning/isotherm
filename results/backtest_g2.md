# Backtest

**Taker:** fills at the read-time quote, Kalshi quadratic fees, size capped at a share of post-read volume. **Maker:** rest at or inside the touch, filled only by later prints strictly through our price (no queue model needed). Both held to settlement; fixed $10,000 bankroll; daily PnL, Sharpe annualised by √365. **Headline = nested selection**: each quarter trades the config with the best Sharpe on earlier quarters only. See docs/EVALS.md for what each number can and cannot tell you.

## d0_08 · taker

| | |
|---|---|
| PnL (nested, out-of-sample) | **$11,884** over 1095 days, 6193 trades |
| Sharpe (ann.) | **1.21** [0.12, 2.29] stationary bootstrap |
| Newey-West t | 2.01 |
| Deflated Sharpe | **0.330** (28 configs tried; ≥0.95 to believe) |
| PBO (CSCV) | **0.61** (924 splits; ≤0.2 to believe) |
| Max drawdown | $3,209 |
| Hit rate | 71.6% |
| Return on outlay | +2.73% |
| EV vs realised per contract | +0.0406 vs +0.0142 |
| Attribution | alpha vs mid $33,177 · spread $-12,709 · fees $-8,584 |

By period:

| Period | PnL | Trades | per contract |
|---|---:|---:|---:|
| 2023H2 | $797 | 476 | +0.0715 |
| 2024H1 | $642 | 680 | +0.0262 |
| 2024H2 | $-183 | 447 | -0.0036 |
| 2025H1 | $410 | 924 | +0.0087 |
| 2025H2 | $6,335 | 1756 | +0.0199 |
| 2026H1 | $3,883 | 1910 | +0.0101 |

By city:

| City | PnL | Trades | per contract |
|---|---:|---:|---:|
| AUS | $-170 | 1344 | -0.0013 |
| CHI | $1,914 | 1345 | +0.0103 |
| DEN | $987 | 708 | +0.0107 |
| LAX | $1,946 | 646 | +0.0212 |
| MIA | $3,247 | 954 | +0.0256 |
| NY | $-5 | 669 | -0.0000 |
| PHIL | $3,965 | 527 | +0.0377 |

Engine checks:

| Check | Trades | PnL | Losing trades |
|---|---:|---:|---:|
| oracle (must never lose) | 24685 | $1,194,529 | 0 |
| in-spread market (must not trade) | 0 | $0 | 0 |
| normalised mid | 3586 | $-13,001 | 1555 |
| noise_matched_turnover | 5518 | $-5,629 | 2200 |
| arbitrage_ladders | 718 | $0 | 0 |

Robustness (LadderNet · kelly 0.25):

| Scenario | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| base | $4,899 | 1.30 | 8460 |
| slip +1¢ | $2,619 | 0.86 | 4293 |
| slip +2¢ | $2,145 | 0.84 | 2668 |
| fees ×1.5 | $3,208 | 0.94 | 7243 |
| participation 1% | $-227 | -0.07 | 8187 |
| participation 20% | $7,170 | 1.72 | 8535 |
| size ×10 | $-13,791 | -0.52 | 8520 |

Top configs over the full period (in-sample ceiling, not a result):

| Config | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| pool · market+GFS+obs · 365d · θ 0.01 | $26,351 | 1.94 | 7173 |
| pool · market+GFS · θ 0.04 | $13,943 | 1.94 | 2498 |
| pool · market+GFS · kelly 0.25 | $8,942 | 1.89 | 9034 |
| pool · market+GFS · θ 0.01 | $23,819 | 1.86 | 6536 |
| pool · market+GFS · kelly 0.10 | $3,676 | 1.83 | 8952 |
| pool · market+GFS · kelly 0.50 | $15,740 | 1.76 | 9064 |

## d0_08 · maker

| | |
|---|---|
| PnL (nested, out-of-sample) | **$1,629** over 1095 days, 9844 trades |
| Sharpe (ann.) | **0.13** [-0.99, 1.29] stationary bootstrap |
| Newey-West t | 0.22 |
| Deflated Sharpe | **0.002** (32 configs tried; ≥0.95 to believe) |
| PBO (CSCV) | **0.29** (924 splits; ≤0.2 to believe) |
| Max drawdown | $10,320 |
| Hit rate | 58.6% |
| Return on outlay | +0.28% |
| EV vs realised per contract | +0.0725 vs +0.0012 |
| Attribution | alpha vs mid $-62,998 · spread $64,627 · fees $-0 |

By period:

| Period | PnL | Trades | per contract |
|---|---:|---:|---:|
| 2023H2 | $-689 | 875 | -0.0073 |
| 2024H1 | $-354 | 934 | -0.0043 |
| 2024H2 | $7,283 | 1379 | +0.0327 |
| 2025H1 | $-4,701 | 1873 | -0.0160 |
| 2025H2 | $-459 | 2334 | -0.0015 |
| 2026H1 | $549 | 2449 | +0.0017 |

By city:

| City | PnL | Trades | per contract |
|---|---:|---:|---:|
| AUS | $-3,966 | 1731 | -0.0182 |
| CHI | $776 | 1779 | +0.0035 |
| DEN | $-1,770 | 888 | -0.0160 |
| LAX | $2,162 | 1111 | +0.0140 |
| MIA | $5,275 | 1651 | +0.0271 |
| NY | $172 | 1750 | +0.0006 |
| PHIL | $-1,020 | 934 | -0.0078 |

Engine checks:

| Check | Trades | PnL | Losing trades |
|---|---:|---:|---:|
| oracle (must never lose) | 12808 | $511,839 | 0 |
| uninformed market maker | 17080 | $-42,779 | 7990 |
| noise_matched_turnover | 10221 | $-19,321 | 5185 |

Robustness (LadderNet · maker θ 0.02 · 1h):

| Scenario | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| base: trade-through fills | $6,028 | 0.53 | 9253 |
| touch fills, 50% queue share | $10,425 | 0.88 | 10539 |
| maker fee 0.0175 | $2,130 | 0.20 | 8564 |
| no price improvement | $5,346 | 0.48 | 8421 |
| horizon 1h | $6,028 | 0.53 | 9253 |
| horizon to close | $-59,280 | -2.83 | 17144 |
| size ×10 | $-27,346 | -0.71 | 9253 |

Top configs over the full period (in-sample ceiling, not a result):

| Config | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| pool · market+GFS · maker θ 0.02 · 1h | $16,178 | 1.16 | 10070 |
| pool · market+GFS+obs · 365d · maker θ 0.02 · 1h | $14,317 | 1.04 | 10183 |
| pool · market+GFS · maker θ 0.04 · 1h | $10,093 | 0.91 | 6225 |
| pool · market+GFS+obs · 365d · maker θ 0.04 · 1h | $9,242 | 0.81 | 6172 |
| pool · market+GFS+obs · 365d · maker θ 0.01 · 1h | $10,878 | 0.73 | 13020 |
| pool · market+GFS · maker θ 0.01 · 1h | $9,967 | 0.66 | 13070 |

## d0_12 · taker

| | |
|---|---|
| PnL (nested, out-of-sample) | **$592** over 1095 days, 702 trades |
| Sharpe (ann.) | **0.37** [-0.89, 1.65] stationary bootstrap |
| Newey-West t | 0.62 |
| Deflated Sharpe | **0.139** (28 configs tried; ≥0.95 to believe) |
| PBO (CSCV) | **0.47** (924 splits; ≤0.2 to believe) |
| Max drawdown | $1,292 |
| Hit rate | 59.0% |
| Return on outlay | +2.81% |
| EV vs realised per contract | +0.0523 vs +0.0171 |
| Attribution | alpha vs mid $2,233 · spread $-1,150 · fees $-490 |

By period:

| Period | PnL | Trades | per contract |
|---|---:|---:|---:|
| 2023H2 | $125 | 241 | +0.0366 |
| 2024H1 | $542 | 235 | +0.0759 |
| 2024H2 | $-277 | 117 | -0.0430 |
| 2025H2 | $-201 | 67 | -0.0184 |
| 2026H1 | $403 | 42 | +0.0605 |

By city:

| City | PnL | Trades | per contract |
|---|---:|---:|---:|
| AUS | $86 | 307 | +0.0082 |
| CHI | $1,101 | 122 | +0.1621 |
| DEN | $-276 | 11 | -0.1388 |
| LAX | $343 | 14 | +0.1663 |
| MIA | $-437 | 81 | -0.0925 |
| NY | $-289 | 147 | -0.0540 |
| PHIL | $64 | 20 | +0.0202 |

Engine checks:

| Check | Trades | PnL | Losing trades |
|---|---:|---:|---:|
| oracle (must never lose) | 18914 | $939,953 | 0 |
| in-spread market (must not trade) | 2 | $740 | 1 |
| normalised mid | 2169 | $3,577 | 1228 |
| noise_matched_turnover | 805 | $418 | 400 |
| arbitrage_ladders | 378 | $0 | 0 |

Robustness (market (tempered) · θ 0.04):

| Scenario | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| base | $2,043 | 1.31 | 513 |
| slip +1¢ | $1,485 | 1.21 | 430 |
| slip +2¢ | $1,293 | 1.36 | 344 |
| fees ×1.5 | $1,649 | 1.33 | 445 |
| participation 1% | $1,391 | 1.24 | 409 |
| participation 20% | $2,072 | 0.99 | 555 |
| size ×10 | $8,314 | 0.96 | 513 |

Top configs over the full period (in-sample ceiling, not a result):

| Config | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| market (tempered) · θ 0.04 | $2,043 | 1.31 | 513 |
| market (tempered) · θ 0.08 | $691 | 1.16 | 241 |
| market (tempered) · kelly 0.25 | $1,367 | 0.88 | 4708 |
| market (tempered) · kelly 0.50 | $2,522 | 0.88 | 4736 |
| market (tempered) · kelly 0.10 | $578 | 0.80 | 4625 |
| pool · market+GFS · θ 0.04 | $1,770 | 0.73 | 655 |

## d0_12 · maker

| | |
|---|---|
| PnL (nested, out-of-sample) | **$-24,577** over 1095 days, 8538 trades |
| Sharpe (ann.) | **-2.10** [-3.22, -0.94] stationary bootstrap |
| Newey-West t | -3.44 |
| Deflated Sharpe | **0.000** (32 configs tried; ≥0.95 to believe) |
| PBO (CSCV) | **0.00** (924 splits; ≤0.2 to believe) |
| Max drawdown | $26,238 |
| Hit rate | 52.3% |
| Return on outlay | -5.12% |
| EV vs realised per contract | +0.0687 vs -0.0190 |
| Attribution | alpha vs mid $-104,455 · spread $79,878 · fees $-0 |

By period:

| Period | PnL | Trades | per contract |
|---|---:|---:|---:|
| 2023H2 | $-6,589 | 863 | -0.0745 |
| 2024H1 | $-135 | 588 | -0.0035 |
| 2024H2 | $1,016 | 1277 | +0.0068 |
| 2025H1 | $-15,480 | 3102 | -0.0248 |
| 2025H2 | $-4,659 | 1926 | -0.0164 |
| 2026H1 | $1,270 | 782 | +0.0116 |

By city:

| City | PnL | Trades | per contract |
|---|---:|---:|---:|
| AUS | $-3,075 | 1498 | -0.0149 |
| CHI | $-4,962 | 1484 | -0.0226 |
| DEN | $-538 | 971 | -0.0030 |
| LAX | $-3,385 | 763 | -0.0212 |
| MIA | $-3,606 | 1478 | -0.0179 |
| NY | $-4,808 | 1533 | -0.0216 |
| PHIL | $-4,206 | 811 | -0.0397 |

Engine checks:

| Check | Trades | PnL | Losing trades |
|---|---:|---:|---:|
| oracle (must never lose) | 11764 | $545,805 | 0 |
| uninformed market maker | 19196 | $-101,869 | 9808 |
| noise_matched_turnover | 8453 | $-34,834 | 4658 |

Robustness (pool · market+GFS · maker θ 0.04 · 1h):

| Scenario | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| base: trade-through fills | $-5,786 | -0.55 | 6572 |
| touch fills, 50% queue share | $-3,168 | -0.30 | 6943 |
| maker fee 0.0175 | $-7,202 | -0.72 | 6106 |
| no price improvement | $-16,506 | -1.46 | 6378 |
| horizon 1h | $-5,786 | -0.55 | 6572 |
| horizon to close | $-74,594 | -5.23 | 10098 |
| size ×10 | $-156,030 | -3.42 | 6572 |

Top configs over the full period (in-sample ceiling, not a result):

| Config | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| pool · market+GFS · maker θ 0.04 · 1h | $-5,786 | -0.55 | 6572 |
| LadderNet · maker θ 0.04 · 1h | $-15,034 | -1.35 | 6643 |
| pool · market+GFS+obs · 365d · maker θ 0.04 · 1h | $-15,957 | -1.38 | 6991 |
| pool · market+GFS+obs · 365d · maker θ 0.02 · 1h | $-27,903 | -1.85 | 11124 |
| market (tempered) · maker θ 0.04 · 1h | $-17,210 | -1.92 | 6136 |
| pool · market+GFS · maker θ 0.02 · 1h | $-28,088 | -2.08 | 10757 |

## d1_16 · taker

| | |
|---|---|
| PnL (nested, out-of-sample) | **$22,122** over 1089 days, 6662 trades |
| Sharpe (ann.) | **2.05** [0.81, 3.27] stationary bootstrap |
| Newey-West t | 3.17 |
| Deflated Sharpe | **0.849** (28 configs tried; ≥0.95 to believe) |
| PBO (CSCV) | **0.26** (924 splits; ≤0.2 to believe) |
| Max drawdown | $5,195 |
| Hit rate | 71.0% |
| Return on outlay | +4.60% |
| EV vs realised per contract | +0.0483 vs +0.0259 |
| Attribution | alpha vs mid $43,561 · spread $-12,434 · fees $-9,005 |

By period:

| Period | PnL | Trades | per contract |
|---|---:|---:|---:|
| 2023H2 | $396 | 587 | +0.0267 |
| 2024H1 | $1,413 | 385 | +0.0614 |
| 2024H2 | $1,109 | 281 | +0.0293 |
| 2025H1 | $1,186 | 1444 | +0.0051 |
| 2025H2 | $11,187 | 1444 | +0.0423 |
| 2026H1 | $6,831 | 2521 | +0.0243 |

By city:

| City | PnL | Trades | per contract |
|---|---:|---:|---:|
| AUS | $4,549 | 908 | +0.0444 |
| CHI | $1,985 | 1139 | +0.0139 |
| DEN | $4,533 | 710 | +0.0465 |
| LAX | $4,191 | 768 | +0.0399 |
| MIA | $6,651 | 1455 | +0.0376 |
| NY | $-1,751 | 904 | -0.0151 |
| PHIL | $1,964 | 778 | +0.0175 |

Engine checks:

| Check | Trades | PnL | Losing trades |
|---|---:|---:|---:|
| oracle (must never lose) | 29204 | $1,569,263 | 0 |
| in-spread market (must not trade) | 0 | $0 | 0 |
| normalised mid | 3446 | $-6,727 | 1238 |
| noise_matched_turnover | 5876 | $-15,646 | 2609 |
| arbitrage_ladders | 548 | $0 | 0 |

Robustness (pool · market+GFS · θ 0.04):

| Scenario | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| base | $11,622 | 1.79 | 2188 |
| slip +1¢ | $6,513 | 1.24 | 1633 |
| slip +2¢ | $4,516 | 0.98 | 1255 |
| fees ×1.5 | $8,515 | 1.42 | 1845 |
| participation 1% | $9,206 | 1.88 | 2146 |
| participation 20% | $8,734 | 1.18 | 2206 |
| size ×10 | $61,210 | 1.71 | 2188 |

Top configs over the full period (in-sample ceiling, not a result):

| Config | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| pool · market+GFS · kelly 0.25 | $14,655 | 3.12 | 9644 |
| pool · market+GFS · kelly 0.50 | $27,242 | 3.04 | 9699 |
| pool · market+GFS+obs · 365d · θ 0.01 | $40,723 | 2.80 | 7887 |
| pool · market+GFS · kelly 0.10 | $5,307 | 2.61 | 9517 |
| pool · market+GFS · θ 0.01 | $33,560 | 2.50 | 6609 |
| pool · market+GFS+obs · 365d · kelly 0.25 | $12,896 | 2.37 | 11020 |

## d1_16 · maker

| | |
|---|---|
| PnL (nested, out-of-sample) | **$-2,419** over 1089 days, 4672 trades |
| Sharpe (ann.) | **-0.32** [-1.58, 0.99] stationary bootstrap |
| Newey-West t | -0.53 |
| Deflated Sharpe | **0.000** (32 configs tried; ≥0.95 to believe) |
| PBO (CSCV) | **0.31** (924 splits; ≤0.2 to believe) |
| Max drawdown | $5,111 |
| Hit rate | 59.0% |
| Return on outlay | -1.02% |
| EV vs realised per contract | +0.0737 vs -0.0051 |
| Attribution | alpha vs mid $-16,170 · spread $13,751 · fees $-0 |

By period:

| Period | PnL | Trades | per contract |
|---|---:|---:|---:|
| 2023H2 | $-680 | 694 | -0.0097 |
| 2024H1 | $1,000 | 635 | +0.0200 |
| 2024H2 | $404 | 661 | +0.0066 |
| 2025H1 | $-129 | 965 | -0.0012 |
| 2025H2 | $-2,009 | 901 | -0.0239 |
| 2026H1 | $-1,004 | 816 | -0.0097 |

By city:

| City | PnL | Trades | per contract |
|---|---:|---:|---:|
| AUS | $245 | 842 | +0.0031 |
| CHI | $-2,875 | 943 | -0.0269 |
| DEN | $54 | 336 | +0.0015 |
| LAX | $1,208 | 349 | +0.0297 |
| MIA | $-23 | 1006 | -0.0002 |
| NY | $-2,017 | 825 | -0.0229 |
| PHIL | $989 | 371 | +0.0315 |

Engine checks:

| Check | Trades | PnL | Losing trades |
|---|---:|---:|---:|
| oracle (must never lose) | 16240 | $549,707 | 0 |
| uninformed market maker | 23453 | $-66,702 | 10412 |
| noise_matched_turnover | 5231 | $-15,491 | 2222 |

Robustness (pool · market+GFS+obs · 365d · maker θ 0.04 · 4h):

| Scenario | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| base: trade-through fills | $7,037 | 0.76 | 6168 |
| touch fills, 50% queue share | $10,964 | 1.13 | 6892 |
| maker fee 0.0175 | $7,610 | 0.84 | 5683 |
| no price improvement | $8,274 | 0.86 | 5949 |
| horizon 1h | $2,212 | 0.46 | 3141 |
| horizon to close | $-52,947 | -2.95 | 11441 |
| size ×10 | $-15,326 | -0.53 | 6168 |

Top configs over the full period (in-sample ceiling, not a result):

| Config | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| pool · market+GFS+obs · 365d · maker θ 0.04 · 4h | $7,037 | 0.76 | 6168 |
| LadderNet · maker θ 0.04 · 1h | $2,836 | 0.66 | 2642 |
| pool · market+GFS · maker θ 0.02 · 1h | $3,148 | 0.50 | 5936 |
| LadderNet · maker θ 0.04 · 4h | $3,986 | 0.49 | 5241 |
| pool · market+GFS+obs · 365d · maker θ 0.04 · 1h | $2,212 | 0.46 | 3141 |
| pool · market+GFS+obs · 365d · maker θ 0.02 · 4h | $5,248 | 0.43 | 11477 |
