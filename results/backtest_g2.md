# Backtest

**Taker:** fills at the read-time quote, Kalshi quadratic fees, size capped at a share of post-read volume. **Maker:** rest at or inside the touch, filled only by later prints strictly through our price (no queue model needed). Both held to settlement; fixed $10,000 bankroll; daily PnL, Sharpe annualised by √365. **Headline = nested selection**: each quarter trades the config with the best Sharpe on earlier quarters only. See docs/EVALS.md for what each number can and cannot tell you.

## d0_08 · taker

| | |
|---|---|
| PnL (nested, out-of-sample) | **$16,071** over 1095 days, 7178 trades |
| Sharpe (ann.) | **1.51** [0.37, 2.63] stationary bootstrap |
| Newey-West t | 2.39 |
| Deflated Sharpe | **0.540** (28 configs tried; ≥0.95 to believe) |
| PBO (CSCV) | **0.45** (924 splits; ≤0.2 to believe) |
| Max drawdown | $3,209 |
| Hit rate | 70.7% |
| Return on outlay | +2.86% |
| EV vs realised per contract | +0.0404 vs +0.0159 |
| Attribution | alpha vs mid $44,358 · spread $-17,850 · fees $-10,437 |

By period:

| Period | PnL | Trades | per contract |
|---|---:|---:|---:|
| 2023H2 | $675 | 485 | +0.0607 |
| 2024H1 | $1,032 | 680 | +0.0391 |
| 2024H2 | $1,889 | 796 | +0.0264 |
| 2025H1 | $3,290 | 1610 | +0.0135 |
| 2025H2 | $4,976 | 1703 | +0.0180 |
| 2026H1 | $4,210 | 1904 | +0.0110 |

By city:

| City | PnL | Trades | per contract |
|---|---:|---:|---:|
| AUS | $1,434 | 1514 | +0.0089 |
| CHI | $4,602 | 1514 | +0.0199 |
| DEN | $-1,542 | 904 | -0.0120 |
| LAX | $2,724 | 741 | +0.0242 |
| MIA | $5,508 | 1126 | +0.0352 |
| NY | $649 | 777 | +0.0058 |
| PHIL | $2,695 | 602 | +0.0246 |

Engine checks:

| Check | Trades | PnL | Losing trades |
|---|---:|---:|---:|
| oracle (must never lose) | 24685 | $1,194,529 | 0 |
| in-spread market (must not trade) | 0 | $0 | 0 |
| normalised mid | 3586 | $-13,001 | 1555 |
| noise_matched_turnover | 6589 | $-22,676 | 2912 |
| arbitrage_ladders | 718 | $0 | 0 |

Robustness (pool · market+GFS+obs · 365d · θ 0.01):

| Scenario | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| base | $29,907 | 2.17 | 7184 |
| slip +1¢ | $11,786 | 1.12 | 4834 |
| slip +2¢ | $3,171 | 0.37 | 3436 |
| fees ×1.5 | $19,077 | 1.57 | 6054 |
| participation 1% | $16,883 | 1.91 | 7043 |
| participation 20% | $23,310 | 1.50 | 7234 |
| size ×10 | $98,356 | 1.50 | 7184 |

Top configs over the full period (in-sample ceiling, not a result):

| Config | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| pool · market+GFS+obs · 365d · θ 0.01 | $29,907 | 2.17 | 7184 |
| pool · market+GFS · θ 0.04 | $13,943 | 1.94 | 2498 |
| pool · market+GFS · kelly 0.25 | $8,942 | 1.89 | 9034 |
| pool · market+GFS · θ 0.01 | $23,819 | 1.86 | 6536 |
| pool · market+GFS+obs · 365d · θ 0.02 | $21,072 | 1.83 | 4785 |
| pool · market+GFS · kelly 0.10 | $3,676 | 1.83 | 8952 |

## d0_08 · maker

| | |
|---|---|
| PnL (nested, out-of-sample) | **$10,108** over 1095 days, 8855 trades |
| Sharpe (ann.) | **0.82** [-0.39, 1.99] stationary bootstrap |
| Newey-West t | 1.36 |
| Deflated Sharpe | **0.023** (48 configs tried; ≥0.95 to believe) |
| PBO (CSCV) | **0.21** (924 splits; ≤0.2 to believe) |
| Max drawdown | $7,193 |
| Same picks, at-touch fills (upper bound) | $15,843 |
| Hit rate | 58.3% |
| Return on outlay | +1.94% |
| EV vs realised per contract | +0.0763 vs +0.0084 |
| Attribution | alpha vs mid $-48,975 · spread $59,082 · fees $-0 |

By period:

| Period | PnL | Trades | per contract |
|---|---:|---:|---:|
| 2023H2 | $-1,242 | 856 | -0.0134 |
| 2024H1 | $1,059 | 841 | +0.0146 |
| 2024H2 | $10,042 | 1396 | +0.0438 |
| 2025H1 | $-662 | 1337 | -0.0030 |
| 2025H2 | $362 | 1976 | +0.0014 |
| 2026H1 | $549 | 2449 | +0.0017 |

By city:

| City | PnL | Trades | per contract |
|---|---:|---:|---:|
| AUS | $-393 | 1559 | -0.0020 |
| CHI | $2,512 | 1611 | +0.0121 |
| DEN | $-1,468 | 768 | -0.0148 |
| LAX | $2,845 | 888 | +0.0222 |
| MIA | $5,610 | 1569 | +0.0303 |
| NY | $1,279 | 1598 | +0.0049 |
| PHIL | $-277 | 862 | -0.0023 |

Engine checks:

| Check | Trades | PnL | Losing trades |
|---|---:|---:|---:|
| oracle (must never lose) | 12808 | $511,839 | 0 |
| uninformed market maker | 17080 | $-42,779 | 7990 |
| noise_matched_turnover | 9081 | $-17,353 | 4760 |

Robustness (LadderNet · maker θ 0.04 · 1h):

| Scenario | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| base: trade-through fills | $5,625 | 0.64 | 5108 |
| touch fills, 50% queue share | $8,704 | 0.95 | 5745 |
| maker fee 0.0175 | $3,594 | 0.42 | 4735 |
| no price improvement | $7,068 | 0.80 | 4673 |
| horizon 1h | $5,625 | 0.64 | 5108 |
| horizon to close | $-42,904 | -2.62 | 10835 |
| size ×10 | $-8,875 | -0.30 | 5108 |

Top configs over the full period (in-sample ceiling, not a result):

| Config | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| pool · market+GFS · maker θ 0.02 · 1h | $16,178 | 1.16 | 10070 |
| pool · market+GFS+obs · 365d · maker θ 0.02 · 1h | $13,436 | 0.97 | 10173 |
| pool · market+GFS · maker θ 0.04 · 1h | $10,093 | 0.91 | 6225 |
| pool · market+GFS+obs · 365d · maker θ 0.04 · 1h | $9,430 | 0.83 | 6159 |
| LadderNet · maker θ 0.04 · 4h | $11,269 | 0.80 | 8335 |
| pool · market+GFS+obs · 365d · maker θ 0.01 · 1h | $11,889 | 0.79 | 13031 |

## d0_12 · taker

| | |
|---|---|
| PnL (nested, out-of-sample) | **$727** over 1095 days, 746 trades |
| Sharpe (ann.) | **0.37** [-0.79, 1.56] stationary bootstrap |
| Newey-West t | 0.63 |
| Deflated Sharpe | **0.211** (28 configs tried; ≥0.95 to believe) |
| PBO (CSCV) | **0.48** (924 splits; ≤0.2 to believe) |
| Max drawdown | $1,339 |
| Hit rate | 61.3% |
| Return on outlay | +2.74% |
| EV vs realised per contract | +0.0552 vs +0.0171 |
| Attribution | alpha vs mid $2,721 · spread $-1,383 · fees $-611 |

By period:

| Period | PnL | Trades | per contract |
|---|---:|---:|---:|
| 2023H2 | $267 | 231 | +0.0845 |
| 2024H1 | $542 | 235 | +0.0759 |
| 2024H2 | $-284 | 171 | -0.0193 |
| 2025H2 | $-201 | 67 | -0.0184 |
| 2026H1 | $403 | 42 | +0.0605 |

By city:

| City | PnL | Trades | per contract |
|---|---:|---:|---:|
| AUS | $470 | 300 | +0.0441 |
| CHI | $867 | 125 | +0.1188 |
| DEN | $-324 | 28 | -0.0719 |
| LAX | $343 | 14 | +0.1663 |
| MIA | $-576 | 103 | -0.0708 |
| NY | $-17 | 155 | -0.0026 |
| PHIL | $-36 | 21 | -0.0105 |

Engine checks:

| Check | Trades | PnL | Losing trades |
|---|---:|---:|---:|
| oracle (must never lose) | 18914 | $939,953 | 0 |
| in-spread market (must not trade) | 2 | $740 | 1 |
| normalised mid | 2169 | $3,577 | 1228 |
| noise_matched_turnover | 786 | $1,936 | 384 |
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
| PnL (nested, out-of-sample) | **$-23,991** over 1095 days, 8233 trades |
| Sharpe (ann.) | **-1.96** [-3.13, -0.76] stationary bootstrap |
| Newey-West t | -3.04 |
| Deflated Sharpe | **0.000** (48 configs tried; ≥0.95 to believe) |
| PBO (CSCV) | **0.00** (924 splits; ≤0.2 to believe) |
| Max drawdown | $25,698 |
| Same picks, at-touch fills (upper bound) | $-21,312 |
| Hit rate | 50.4% |
| Return on outlay | -5.32% |
| EV vs realised per contract | +0.0795 vs -0.0192 |
| Attribution | alpha vs mid $-105,101 · spread $81,110 · fees $-0 |

By period:

| Period | PnL | Trades | per contract |
|---|---:|---:|---:|
| 2023H2 | $-6,532 | 878 | -0.0702 |
| 2024H1 | $-379 | 609 | -0.0093 |
| 2024H2 | $1,937 | 1192 | +0.0130 |
| 2025H1 | $-11,536 | 2324 | -0.0239 |
| 2025H2 | $-8,751 | 2448 | -0.0233 |
| 2026H1 | $1,270 | 782 | +0.0116 |

By city:

| City | PnL | Trades | per contract |
|---|---:|---:|---:|
| AUS | $-5,443 | 1436 | -0.0277 |
| CHI | $-4,278 | 1436 | -0.0204 |
| DEN | $-354 | 907 | -0.0021 |
| LAX | $-2,360 | 757 | -0.0152 |
| MIA | $-1,992 | 1431 | -0.0098 |
| NY | $-5,102 | 1489 | -0.0237 |
| PHIL | $-4,462 | 777 | -0.0439 |

Engine checks:

| Check | Trades | PnL | Losing trades |
|---|---:|---:|---:|
| oracle (must never lose) | 11764 | $545,805 | 0 |
| uninformed market maker | 19196 | $-101,869 | 9808 |
| noise_matched_turnover | 8433 | $-39,587 | 4677 |

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
| pool · market+GFS+obs · 365d · maker θ 0.04 · 1h | $-16,354 | -1.39 | 6953 |
| LadderNet · maker θ 0.04 · 1h | $-17,728 | -1.56 | 6713 |
| pool · market+GFS+obs · 365d · maker θ 0.02 · 1h | $-26,189 | -1.69 | 11106 |
| market (tempered) · maker θ 0.04 · 1h | $-17,210 | -1.92 | 6136 |
| pool · market+GFS · maker θ 0.02 · 1h | $-28,088 | -2.08 | 10757 |

## d0_14 · taker

| | |
|---|---|
| PnL (nested, out-of-sample) | **$2,316** over 1095 days, 322 trades |
| Sharpe (ann.) | **1.14** [0.20, 2.11] stationary bootstrap |
| Newey-West t | 1.99 |
| Deflated Sharpe | **0.421** (28 configs tried; ≥0.95 to believe) |
| PBO (CSCV) | **0.12** (924 splits; ≤0.2 to believe) |
| Max drawdown | $337 |
| Hit rate | 75.2% |
| Return on outlay | +13.14% |
| EV vs realised per contract | +0.1227 vs +0.0870 |
| Attribution | alpha vs mid $3,191 · spread $-503 · fees $-373 |

By period:

| Period | PnL | Trades | per contract |
|---|---:|---:|---:|
| 2023H2 | $79 | 116 | +0.0396 |
| 2024H1 | $-122 | 46 | -0.0980 |
| 2024H2 | $368 | 33 | +0.0856 |
| 2025H1 | $396 | 40 | +0.0729 |
| 2025H2 | $367 | 30 | +0.0864 |
| 2026H1 | $1,227 | 57 | +0.1305 |

By city:

| City | PnL | Trades | per contract |
|---|---:|---:|---:|
| AUS | $123 | 102 | +0.0212 |
| CHI | $98 | 54 | +0.0178 |
| DEN | $-77 | 18 | -0.0283 |
| LAX | $80 | 3 | +0.2120 |
| MIA | $175 | 48 | +0.0496 |
| NY | $401 | 71 | +0.0912 |
| PHIL | $1,515 | 26 | +0.3537 |

Engine checks:

| Check | Trades | PnL | Losing trades |
|---|---:|---:|---:|
| oracle (must never lose) | 13687 | $592,892 | 0 |
| in-spread market (must not trade) | 0 | $0 | 0 |
| normalised mid | 1736 | $8,978 | 1354 |
| noise_matched_turnover | 304 | $-463 | 183 |
| arbitrage_ladders | 193 | $0 | 0 |

Robustness (pool · market+GFS · θ 0.08):

| Scenario | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| base | $2,633 | 1.32 | 208 |
| slip +1¢ | $1,298 | 0.75 | 139 |
| slip +2¢ | $1,414 | 0.96 | 107 |
| fees ×1.5 | $1,495 | 0.82 | 154 |
| participation 1% | $1,077 | 0.92 | 194 |
| participation 20% | $2,764 | 1.31 | 211 |
| size ×10 | $4,054 | 0.45 | 208 |

Top configs over the full period (in-sample ceiling, not a result):

| Config | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| market (tempered) · θ 0.08 | $2,755 | 1.34 | 210 |
| pool · market+GFS · θ 0.08 | $2,633 | 1.32 | 208 |
| LadderNet · kelly 0.10 | $2,514 | 1.10 | 4591 |
| pool · market+GFS · kelly 0.10 | $2,145 | 0.90 | 5130 |
| market (tempered) · kelly 0.10 | $2,126 | 0.89 | 5145 |
| LadderNet · kelly 0.25 | $3,377 | 0.81 | 4619 |

## d0_14 · maker

| | |
|---|---|
| PnL (nested, out-of-sample) | **$-30,573** over 1095 days, 7389 trades |
| Sharpe (ann.) | **-2.68** [-3.88, -1.51] stationary bootstrap |
| Newey-West t | -4.55 |
| Deflated Sharpe | **0.000** (48 configs tried; ≥0.95 to believe) |
| PBO (CSCV) | **0.00** (924 splits; ≤0.2 to believe) |
| Max drawdown | $30,799 |
| Same picks, at-touch fills (upper bound) | $-26,753 |
| Hit rate | 58.3% |
| Return on outlay | -6.53% |
| EV vs realised per contract | +0.1007 vs -0.0300 |
| Attribution | alpha vs mid $-115,517 · spread $84,943 · fees $-0 |

By period:

| Period | PnL | Trades | per contract |
|---|---:|---:|---:|
| 2023H2 | $-4,851 | 564 | -0.0732 |
| 2024H1 | $99 | 421 | +0.0035 |
| 2024H2 | $-428 | 1127 | -0.0034 |
| 2025H1 | $-19,127 | 2136 | -0.0532 |
| 2025H2 | $-3,657 | 1841 | -0.0132 |
| 2026H1 | $-2,609 | 1300 | -0.0161 |

By city:

| City | PnL | Trades | per contract |
|---|---:|---:|---:|
| AUS | $-9,997 | 1638 | -0.0458 |
| CHI | $-3,016 | 1191 | -0.0192 |
| DEN | $-4,928 | 935 | -0.0331 |
| LAX | $-1,598 | 494 | -0.0186 |
| MIA | $-1,423 | 973 | -0.0111 |
| NY | $-3,788 | 1271 | -0.0242 |
| PHIL | $-5,823 | 887 | -0.0464 |

Engine checks:

| Check | Trades | PnL | Losing trades |
|---|---:|---:|---:|
| oracle (must never lose) | 8674 | $423,291 | 0 |
| uninformed market maker | 15584 | $-127,513 | 8420 |
| noise_matched_turnover | 7450 | $-61,837 | 4492 |

Robustness (pool · market+GFS+obs · 365d · maker θ 0.04 · 1h):

| Scenario | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| base: trade-through fills | $-23,802 | -2.09 | 6639 |
| touch fills, 50% queue share | $-19,906 | -1.72 | 6952 |
| maker fee 0.0175 | $-21,991 | -2.01 | 6348 |
| no price improvement | $-29,727 | -2.62 | 6222 |
| horizon 1h | $-23,802 | -2.09 | 6639 |
| horizon to close | $-63,820 | -4.55 | 9141 |
| size ×10 | $-298,887 | -4.76 | 6639 |

Top configs over the full period (in-sample ceiling, not a result):

| Config | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| market (tempered) · maker θ 0.04 · 1h | $-20,712 | -1.92 | 7138 |
| pool · market+GFS · maker θ 0.04 · 1h | $-21,515 | -2.03 | 7109 |
| pool · market+GFS+obs · 365d · maker θ 0.04 · 1h | $-23,802 | -2.09 | 6639 |
| LadderNet · maker θ 0.04 · 1h | $-25,040 | -2.36 | 6220 |
| pool · market+GFS · maker θ 0.02 · 1h | $-31,922 | -2.68 | 9311 |
| market (tempered) · maker θ 0.02 · 1h | $-32,888 | -2.80 | 9293 |

## d1_16 · taker

| | |
|---|---|
| PnL (nested, out-of-sample) | **$22,311** over 1089 days, 6679 trades |
| Sharpe (ann.) | **2.06** [0.82, 3.30] stationary bootstrap |
| Newey-West t | 3.20 |
| Deflated Sharpe | **0.865** (28 configs tried; ≥0.95 to believe) |
| PBO (CSCV) | **0.24** (924 splits; ≤0.2 to believe) |
| Max drawdown | $5,195 |
| Hit rate | 71.0% |
| Return on outlay | +4.63% |
| EV vs realised per contract | +0.0483 vs +0.0262 |
| Attribution | alpha vs mid $43,748 · spread $-12,426 · fees $-9,012 |

By period:

| Period | PnL | Trades | per contract |
|---|---:|---:|---:|
| 2023H2 | $586 | 604 | +0.0378 |
| 2024H1 | $1,413 | 385 | +0.0614 |
| 2024H2 | $1,109 | 281 | +0.0293 |
| 2025H1 | $1,186 | 1444 | +0.0051 |
| 2025H2 | $11,187 | 1444 | +0.0423 |
| 2026H1 | $6,831 | 2521 | +0.0243 |

By city:

| City | PnL | Trades | per contract |
|---|---:|---:|---:|
| AUS | $4,589 | 910 | +0.0448 |
| CHI | $2,094 | 1142 | +0.0146 |
| DEN | $4,533 | 710 | +0.0465 |
| LAX | $4,191 | 768 | +0.0399 |
| MIA | $6,647 | 1458 | +0.0376 |
| NY | $-1,706 | 913 | -0.0147 |
| PHIL | $1,964 | 778 | +0.0175 |

Engine checks:

| Check | Trades | PnL | Losing trades |
|---|---:|---:|---:|
| oracle (must never lose) | 29204 | $1,569,263 | 0 |
| in-spread market (must not trade) | 0 | $0 | 0 |
| normalised mid | 3446 | $-6,727 | 1238 |
| noise_matched_turnover | 5854 | $-18,674 | 2624 |
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
| PnL (nested, out-of-sample) | **$2,985** over 1089 days, 4700 trades |
| Sharpe (ann.) | **0.42** [-0.81, 1.70] stationary bootstrap |
| Newey-West t | 0.67 |
| Deflated Sharpe | **0.000** (48 configs tried; ≥0.95 to believe) |
| PBO (CSCV) | **0.40** (924 splits; ≤0.2 to believe) |
| Max drawdown | $2,794 |
| Same picks, at-touch fills (upper bound) | $4,820 |
| Hit rate | 59.8% |
| Return on outlay | +1.29% |
| EV vs realised per contract | +0.0718 vs +0.0065 |
| Attribution | alpha vs mid $-10,830 · spread $13,815 · fees $-0 |

By period:

| Period | PnL | Trades | per contract |
|---|---:|---:|---:|
| 2023H2 | $-372 | 698 | -0.0053 |
| 2024H1 | $1,486 | 566 | +0.0343 |
| 2024H2 | $634 | 545 | +0.0125 |
| 2025H1 | $680 | 1040 | +0.0062 |
| 2025H2 | $1,769 | 1346 | +0.0133 |
| 2026H1 | $-1,212 | 505 | -0.0217 |

By city:

| City | PnL | Trades | per contract |
|---|---:|---:|---:|
| AUS | $991 | 815 | +0.0141 |
| CHI | $-2,188 | 917 | -0.0233 |
| DEN | $1,797 | 313 | +0.0567 |
| LAX | $3,228 | 407 | +0.0571 |
| MIA | $-1,292 | 1064 | -0.0134 |
| NY | $-735 | 811 | -0.0086 |
| PHIL | $1,184 | 373 | +0.0422 |

Engine checks:

| Check | Trades | PnL | Losing trades |
|---|---:|---:|---:|
| oracle (must never lose) | 13032 | $400,311 | 0 |
| uninformed market maker | 18459 | $-52,290 | 8071 |
| noise_matched_turnover | 4005 | $-10,558 | 1709 |

Robustness (LadderNet · maker θ 0.04 · until next GFS):

| Scenario | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| base: trade-through fills | $5,869 | 0.94 | 3922 |
| touch fills, 50% queue share | $7,289 | 1.13 | 4492 |
| maker fee 0.0175 | $4,382 | 0.74 | 3545 |
| no price improvement | $2,800 | 0.43 | 3813 |
| horizon 1h | $2,099 | 0.50 | 2565 |
| horizon to close | $5,869 | 0.94 | 3922 |
| size ×10 | $905 | 0.05 | 3922 |

Top configs over the full period (in-sample ceiling, not a result):

| Config | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| LadderNet · maker θ 0.04 · until next GFS | $5,869 | 0.94 | 3922 |
| pool · market+GFS+obs · 365d · maker θ 0.04 · until next GFS | $6,503 | 0.92 | 4739 |
| pool · market+GFS · maker θ 0.04 · until next GFS | $5,644 | 0.85 | 4431 |
| pool · market+GFS+obs · 365d · maker θ 0.04 · 4h | $7,037 | 0.76 | 6168 |
| LadderNet · maker θ 0.04 · 4h | $4,862 | 0.63 | 5135 |
| market (tempered) · maker θ 0.04 · until next GFS | $2,347 | 0.55 | 2399 |
