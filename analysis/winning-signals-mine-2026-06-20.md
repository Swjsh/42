# Winning-signal mine — native futures fleet (2026-06-20)

> Hunting robust positive-expectancy subsets inside the losing whole. A slice only counts if it is net-positive on **BOTH** MES and MNQ independently (n≥25 each) — cross-instrument agreement is the overfitting guard. Avg = $/contract/trade.

- Universe: MES 2,611 signals, MNQ 2,254 signals.

## Setup × direction (n≥40 each instrument)

| Setup \| dir | robust avg | combined n | comb WR | MES (n/avg) | MNQ (n/avg) | both+ |
|---|--:|--:|--:|--:|--:|:--:|
| LEVEL_REJECT_LIVE | long | +19.58 | 273 | 67% | 169/+19.6 | 104/+47.0 | YES |
| OPEN_REJECTION | short | -0.63 | 325 | 62% | 162/-0.6 | 163/+17.7 | no |
| BEARISH_REJECTION_v14e | short | -1.50 | 560 | 19% | 279/-1.5 | 281/+5.0 | no |
| TRENDLINE_BREAK_RETEST | short | -1.59 | 264 | 54% | 195/-0.7 | 69/-1.6 | no |
| TRENDLINE_BREAK_RETEST | long | -10.64 | 289 | 45% | 226/-10.6 | 63/+9.2 | no |
| BULLISH_RECLAIM_RIDE_THE_RIBBON | long | -12.08 | 259 | 46% | 128/-12.1 | 131/+16.9 | no |
| ERL_IRL_SWEEP_FVG | short | -14.71 | 455 | 70% | 237/-14.7 | 218/-3.5 | no |
| LEVEL_REJECT_LIVE | short | -16.07 | 365 | 62% | 210/-5.9 | 155/-16.1 | no |
| ERL_IRL_SWEEP_FVG | long | -24.72 | 505 | 68% | 257/-24.7 | 248/+14.3 | no |
| NAMED_LEVEL_WICK_BOUNCE | long | -43.45 | 637 | 28% | 323/-26.5 | 314/-43.5 | no |
| BEARISH_REJECTION_MORNING | short | -52.99 | 344 | 56% | 163/-23.4 | 181/-53.0 | no |

## Setup × dir × VIX-band — WINNERS only (n≥25 each)

| Setup \| dir \| vix | robust avg | comb n | comb WR | MES | MNQ |
|---|--:|--:|--:|--:|--:|
| LEVEL_REJECT_LIVE | long | ELEV(18-22) | +59.71 | 67 | 82% | 39/+59.7 | 28/+97.5 |
| ERL_IRL_SWEEP_FVG | short | ELEV(18-22) | +13.81 | 128 | 72% | 66/+13.8 | 62/+26.0 |
| OPEN_REJECTION | short | MID(15-18) | +0.77 | 155 | 66% | 78/+0.8 | 77/+53.8 |
| BEARISH_REJECTION_v14e | short | HIGH(>22) | +0.02 | 121 | 37% | 59/+20.2 | 62/+0.0 |

## Confidence × direction (all, n≥25 each)

| key | robust avg | comb n | comb WR | MES | MNQ | both+ |
|---|--:|--:|--:|--:|--:|:--:|
| conf=medium | short | -6.21 | 1144 | 55% | 666/-6.2 | 478/-0.3 | no |
| conf=high | short | -8.86 | 884 | 65% | 460/-6.3 | 424/-8.9 | no |
| conf=medium | long | -12.76 | 1699 | 43% | 879/-12.8 | 820/-7.0 | no |
| conf=high | long | -17.28 | 421 | 52% | 193/-17.3 | 228/+26.0 | no |
| conf=low | short | -20.00 | 465 | 19% | 253/-10.0 | 212/-20.0 | no |
| conf=low | long | -33.76 | 252 | 32% | 160/-12.5 | 92/-33.8 | no |

## Per-setup aggregate (context — MES, all dirs)

| setup | n | net $ | WR | avg |
|---|--:|--:|--:|--:|
| LEVEL_REJECT_LIVE | 379 | +2078 | 63% | +5.48 |
| ORB_RETEST_LONG | 22 | +112 | 59% | +5.11 |
| LEVEL_BREAK_FIRST_STRIKE | 3 | +10 | 67% | +3.45 |
| OPEN_REJECTION | 162 | -101 | 57% | -0.63 |
| BEARISH_REJECTION_v14e | 279 | -418 | 20% | -1.50 |
| TBR_HIGH_VOL | 207 | -1083 | 53% | -5.23 |
| TRENDLINE_BREAK_RETEST | 421 | -2546 | 46% | -6.05 |
| BULLISH_RECLAIM_RIDE_THE_RIBBON | 128 | -1546 | 45% | -12.08 |
| BEARISH_REVERSAL_AT_LEVEL_ON_BULL_RIBBON | 30 | -413 | 50% | -13.78 |
| ERL_IRL_SWEEP_FVG | 494 | -9841 | 60% | -19.92 |
| BEARISH_REJECTION_MORNING | 163 | -3808 | 55% | -23.36 |
| NAMED_LEVEL_WICK_BOUNCE | 323 | -8571 | 28% | -26.53 |

## Read

**5 robust positive slices** (positive on both instruments). Top candidates to build on:
- `LEVEL_REJECT_LIVE | long | ELEV(18-22)` — robust +$59.71/contract, combined n=67, WR 82%
- `LEVEL_REJECT_LIVE | long` — robust +$19.58/contract, combined n=273, WR 67%
- `ERL_IRL_SWEEP_FVG | short | ELEV(18-22)` — robust +$13.81/contract, combined n=128, WR 72%
- `OPEN_REJECTION | short | MID(15-18)` — robust +$0.77/contract, combined n=155, WR 66%
- `BEARISH_REJECTION_v14e | short | HIGH(>22)` — robust +$0.02/contract, combined n=121, WR 37%
