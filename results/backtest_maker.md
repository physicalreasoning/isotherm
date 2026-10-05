# Backtest

**Taker:** fills at the read-time quote, Kalshi quadratic fees, size capped at a share of post-read volume. **Maker:** rest at or inside the touch, filled only by later prints strictly through our price (no queue model needed). Both held to settlement; fixed $10,000 bankroll; daily PnL, Sharpe annualised by √365. **Headline = nested selection**: each quarter trades the config with the best Sharpe on earlier quarters only. See docs/EVALS.md for what each number can and cannot tell you.

## d0_08 · maker

| | |
|---|---|
| PnL (nested, out-of-sample) | **$-12,477** over 1095 days, 8829 trades |
| Sharpe (ann.) | **-1.02** [-2.25, 0.21] stationary bootstrap |
| Newey-West t | -1.66 |
| Deflated Sharpe | **0.000** (32 configs tried; ≥0.95 to believe) |
| PBO (CSCV) | **0.03** (924 splits; ≤0.2 to believe) |
| Max drawdown | $18,351 |
| Hit rate | 53.3% |
| Return on outlay | -2.56% |
| EV vs realised per contract | +0.0848 vs -0.0103 |
| Attribution | alpha vs mid $-70,423 · spread $57,946 · fees $-0 |

By period:

| Period | PnL | Trades | per contract |
|---|---:|---:|---:|
| 2023H2 | $-2,169 | 920 | -0.0212 |
| 2024H1 | $-201 | 612 | -0.0039 |
| 2024H2 | $6,446 | 1302 | +0.0315 |
| 2025H1 | $-7,205 | 2458 | -0.0175 |
| 2025H2 | $-3,745 | 1823 | -0.0162 |
| 2026H1 | $-5,602 | 1714 | -0.0264 |

By city:

| City | PnL | Trades | per contract |
|---|---:|---:|---:|
| AUS | $-4,705 | 1666 | -0.0216 |
| CHI | $3,614 | 1687 | +0.0168 |
| DEN | $-4,002 | 875 | -0.0332 |
| LAX | $421 | 1026 | +0.0029 |
| MIA | $239 | 1305 | +0.0015 |
| NY | $-4,154 | 1493 | -0.0164 |
| PHIL | $-3,890 | 777 | -0.0375 |

Engine checks:

| Check | Trades | PnL | Losing trades |
|---|---:|---:|---:|
| oracle (must never lose) | 12808 | $511,839 | 0 |
| uninformed market maker | 17080 | $-42,779 | 7990 |
| noise_matched_turnover | 9081 | $-29,195 | 4759 |

Robustness (EMOS · NBM · maker θ 0.04 · 1h):

| Scenario | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| base: trade-through fills | $-47,922 | -2.70 | 11429 |
| touch fills, 50% queue share | $-49,985 | -2.70 | 13541 |
| maker fee 0.0175 | $-50,604 | -2.87 | 11270 |
| no price improvement | $-34,751 | -2.03 | 9395 |
| horizon 1h | $-47,922 | -2.70 | 11429 |
| horizon to close | $-243,506 | -7.02 | 18821 |
| size ×10 | $-146,126 | -3.04 | 11429 |

Top configs over the full period (in-sample ceiling, not a result):

| Config | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| market (tempered) · maker θ 0.02 · 1h | $955 | 0.09 | 9210 |
| market (tempered) · maker θ 0.01 · 1h | $-1,909 | -0.16 | 13521 |
| pool · all · maker θ 0.04 · 1h | $-5,712 | -0.50 | 6382 |
| market (tempered) · maker θ 0.00 · 1h | $-8,383 | -0.61 | 16893 |
| pool · all · maker θ 0.02 · 1h | $-10,254 | -0.70 | 10111 |
| market (tempered) · maker θ 0.04 · 1h | $-5,535 | -0.77 | 4282 |

## d0_12 · maker

| | |
|---|---|
| PnL (nested, out-of-sample) | **$-34,665** over 1095 days, 8306 trades |
| Sharpe (ann.) | **-2.31** [-3.71, -1.10] stationary bootstrap |
| Newey-West t | -3.74 |
| Deflated Sharpe | **0.000** (32 configs tried; ≥0.95 to believe) |
| PBO (CSCV) | **0.00** (924 splits; ≤0.2 to believe) |
| Max drawdown | $40,167 |
| Hit rate | 47.0% |
| Return on outlay | -7.50% |
| EV vs realised per contract | +0.1197 vs -0.0227 |
| Attribution | alpha vs mid $-115,918 · spread $81,253 · fees $-0 |

By period:

| Period | PnL | Trades | per contract |
|---|---:|---:|---:|
| 2023H2 | $-5,879 | 858 | -0.0675 |
| 2024H1 | $-183 | 566 | -0.0046 |
| 2024H2 | $7,725 | 1555 | +0.0179 |
| 2025H1 | $-15,984 | 2415 | -0.0317 |
| 2025H2 | $-12,977 | 2005 | -0.0407 |
| 2026H1 | $-7,367 | 907 | -0.0509 |

By city:

| City | PnL | Trades | per contract |
|---|---:|---:|---:|
| AUS | $-7,309 | 1498 | -0.0282 |
| CHI | $-3,812 | 1397 | -0.0149 |
| DEN | $-935 | 864 | -0.0049 |
| LAX | $-5,049 | 742 | -0.0308 |
| MIA | $-6,125 | 1457 | -0.0256 |
| NY | $-4,646 | 1521 | -0.0156 |
| PHIL | $-6,789 | 827 | -0.0564 |

Engine checks:

| Check | Trades | PnL | Losing trades |
|---|---:|---:|---:|
| oracle (must never lose) | 11764 | $545,805 | 0 |
| uninformed market maker | 19196 | $-101,869 | 9808 |
| noise_matched_turnover | 8453 | $-34,834 | 4658 |

Robustness (pool · all · maker θ 0.04 · 1h):

| Scenario | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| base: trade-through fills | $-21,771 | -1.76 | 6948 |
| touch fills, 50% queue share | $-19,868 | -1.58 | 7351 |
| maker fee 0.0175 | $-22,058 | -1.85 | 6524 |
| no price improvement | $-23,043 | -1.70 | 6725 |
| horizon 1h | $-21,771 | -1.76 | 6948 |
| horizon to close | $-97,534 | -6.15 | 10508 |
| size ×10 | $-247,407 | -4.50 | 6948 |

Top configs over the full period (in-sample ceiling, not a result):

| Config | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| pool · all · maker θ 0.04 · 1h | $-21,771 | -1.76 | 6948 |
| pool · market+NBM · maker θ 0.04 · 1h | $-22,711 | -1.86 | 6972 |
| market (tempered) · maker θ 0.04 · 1h | $-17,210 | -1.92 | 6136 |
| pool · market+NBM · maker θ 0.02 · 1h | $-32,602 | -2.08 | 10795 |
| pool · all · maker θ 0.02 · 1h | $-34,338 | -2.19 | 10759 |
| pool · all · maker θ 0.01 · 1h | $-45,804 | -2.66 | 13681 |

## d1_16 · maker

| | |
|---|---|
| PnL (nested, out-of-sample) | **$-8,071** over 1089 days, 5785 trades |
| Sharpe (ann.) | **-0.91** [-2.20, 0.40] stationary bootstrap |
| Newey-West t | -1.39 |
| Deflated Sharpe | **0.000** (32 configs tried; ≥0.95 to believe) |
| PBO (CSCV) | **0.14** (924 splits; ≤0.2 to believe) |
| Max drawdown | $11,773 |
| Hit rate | 57.2% |
| Return on outlay | -2.65% |
| EV vs realised per contract | +0.0852 vs -0.0127 |
| Attribution | alpha vs mid $-23,620 · spread $15,550 · fees $-0 |

By period:

| Period | PnL | Trades | per contract |
|---|---:|---:|---:|
| 2023H2 | $-977 | 729 | -0.0139 |
| 2024H1 | $2,247 | 323 | +0.0858 |
| 2024H2 | $1,069 | 745 | +0.0128 |
| 2025H1 | $278 | 1687 | +0.0015 |
| 2025H2 | $-1,283 | 1106 | -0.0122 |
| 2026H1 | $-9,406 | 1195 | -0.0560 |

By city:

| City | PnL | Trades | per contract |
|---|---:|---:|---:|
| AUS | $-990 | 935 | -0.0106 |
| CHI | $-2,692 | 1038 | -0.0217 |
| DEN | $-2,015 | 593 | -0.0305 |
| LAX | $-1,320 | 629 | -0.0147 |
| MIA | $2,305 | 1077 | +0.0223 |
| NY | $-3,727 | 964 | -0.0325 |
| PHIL | $370 | 549 | +0.0082 |

Engine checks:

| Check | Trades | PnL | Losing trades |
|---|---:|---:|---:|
| oracle (must never lose) | 8672 | $208,850 | 0 |
| uninformed market maker | 11916 | $-25,116 | 5085 |
| noise_matched_turnover | 5883 | $-12,141 | 2730 |

Robustness (EMOS · NBM · maker θ 0.04 · 1h):

| Scenario | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| base: trade-through fills | $-12,657 | -1.77 | 6756 |
| touch fills, 50% queue share | $-12,014 | -1.59 | 8670 |
| maker fee 0.0175 | $-14,073 | -1.99 | 6627 |
| no price improvement | $-11,651 | -1.79 | 4952 |
| horizon 1h | $-12,657 | -1.77 | 6756 |
| horizon to close | $-251,874 | -7.39 | 19985 |
| size ×10 | $-32,337 | -1.77 | 6756 |

Top configs over the full period (in-sample ceiling, not a result):

| Config | PnL | Sharpe | Trades |
|---|---:|---:|---:|
| pool · all · maker θ 0.04 · 1h | $1,852 | 0.37 | 3368 |
| pool · all · maker θ 0.04 · 4h | $993 | 0.11 | 6520 |
| market (tempered) · maker θ 0.04 · 4h | $219 | 0.04 | 3368 |
| pool · market+NBM · maker θ 0.04 · 4h | $-1,639 | -0.16 | 6776 |
| pool · all · maker θ 0.02 · 1h | $-1,116 | -0.18 | 5947 |
| pool · market+NBM · maker θ 0.04 · 1h | $-940 | -0.18 | 3545 |
