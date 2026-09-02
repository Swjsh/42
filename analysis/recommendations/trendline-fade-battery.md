# Trendline FADE entry battery -- TREND-FADE-PREREG (2026-07-14)

Prereg: `prereg-trendline-fade-battery-2026-07-14.json` (frozen, run verbatim). Elapsed: 238.4s. 78191 qualifying lines, 51534 candidate episodes across 3 fade variants.

Motivation: S1's break-battery killed CONTINUATION entries 12/12 but disclosed the opposite-direction null beating the real trade OOS in 10/12 cells. This battery promotes fading to a first-class, pre-registered hypothesis (own nulls, own pass bar) with 2 new variants S1 never tested.

| Cell | n | Exp/tr | OOS Exp | WF | p | BH-sig | Beats nulls | Verdict |
|---|---|---|---|---|---|---|---|---|
| F1_fade_immediate::body::resistance(fade-of-bullish) | 9025 | 16.8 | 55.63 | None | 0.0353 | YES | both | **FAIL** |
| F1_fade_immediate::body::support(fade-of-bearish) | 11363 | -16.21 | -50.79 | -58.477 | 0.0217 | YES | both | **FAIL** |
| F1_fade_immediate::wick::resistance(fade-of-bullish) | 4816 | -8.69 | -18.35 | None | 0.4203 | no | both | **FAIL** |
| F1_fade_immediate::wick::support(fade-of-bearish) | 5865 | -32.43 | 15.4 | None | 0.0012 | YES | both | **FAIL** |
| F2_fade_reclaim_confirmed::body::resistance(fade-of-bullish) | 933 | -86.29 | -224.99 | None | 0.0013 | YES | neither | **FAIL** |
| F2_fade_reclaim_confirmed::body::support(fade-of-bearish) | 918 | -153.5 | 57.99 | None | 0.0 | YES | both | **FAIL** |
| F2_fade_reclaim_confirmed::wick::resistance(fade-of-bullish) | 513 | 85.7 | 67.84 | 0.698 | 0.0193 | YES | both | **FAIL** |
| F2_fade_reclaim_confirmed::wick::support(fade-of-bearish) | 507 | -99.86 | -51.47 | None | 0.0041 | YES | both | **FAIL** |
| F3_fade_low_volume::body::resistance(fade-of-bullish) | 4092 | 30.83 | 80.51 | 21.224 | 0.0218 | YES | both | **PASS** |
| F3_fade_low_volume::body::support(fade-of-bearish) | 4477 | -17.8 | -23.47 | None | 0.1748 | no | both | **FAIL** |
| F3_fade_low_volume::wick::resistance(fade-of-bullish) | 1826 | 20.78 | -74.35 | -1.049 | 0.283 | no | both | **FAIL** |
| F3_fade_low_volume::wick::support(fade-of-bearish) | 2059 | -22.91 | 117.75 | None | 0.2551 | no | both | **FAIL** |

Verdict counts: {'PASS': 1, 'FAIL': 11, 'INCONCLUSIVE_UNDERPOWERED': 0}