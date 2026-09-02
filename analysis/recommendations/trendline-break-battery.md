# Trendline break entry battery -- S1 (2026-07-14)

Prereg: `prereg-trendline-break-battery-2026-07-14.json` (frozen, run verbatim). Elapsed: 208.0s. 78191 qualifying lines, 48336 candidate episodes across 3 variants.

| Cell | n | Exp/tr | OOS Exp | WF | p | BH-sig | Beats nulls | Verdict |
|---|---|---|---|---|---|---|---|---|
| V1_close_through_immediate::body::resistance(bullish) | 9390 | -194.83 | -196.37 | None | 0.0 | YES | partial | **FAIL** |
| V1_close_through_immediate::body::support(bearish) | 11176 | -151.1 | -135.06 | None | 0.0 | YES | partial | **FAIL** |
| V1_close_through_immediate::wick::resistance(bullish) | 5095 | -139.95 | -116.47 | None | 0.0 | YES | partial | **FAIL** |
| V1_close_through_immediate::wick::support(bearish) | 5754 | -157.11 | -182.8 | None | 0.0 | YES | partial | **FAIL** |
| V2_break_retest_entry::body::resistance(bullish) | 1032 | -202.05 | -172.71 | None | 0.0 | YES | partial | **FAIL** |
| V2_break_retest_entry::body::support(bearish) | 1135 | -72.32 | -43.95 | None | 0.0 | YES | both | **FAIL** |
| V2_break_retest_entry::wick::resistance(bullish) | 341 | -248.34 | -183.52 | None | 0.0 | YES | partial | **FAIL** |
| V2_break_retest_entry::wick::support(bearish) | 436 | -98.69 | -201.96 | None | 0.0 | YES | neither | **FAIL** |
| V3_break_volume_expansion::body::resistance(bullish) | 2612 | -90.56 | -81.47 | None | 0.0 | YES | partial | **FAIL** |
| V3_break_volume_expansion::body::support(bearish) | 4162 | -86.52 | -99.12 | None | 0.0 | YES | partial | **FAIL** |
| V3_break_volume_expansion::wick::resistance(bullish) | 1788 | -44.37 | -8.21 | None | 0.0001 | YES | both | **FAIL** |
| V3_break_volume_expansion::wick::support(bearish) | 2376 | -112.33 | -153.14 | None | 0.0 | YES | partial | **FAIL** |

Verdict counts: {'PASS': 0, 'FAIL': 12, 'INCONCLUSIVE_UNDERPOWERED': 0}