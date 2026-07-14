# Trendline break entry battery -- S1 (2026-07-14)

Prereg: `prereg-trendline-break-battery-2026-07-14.json` (frozen, run verbatim). Elapsed: 187.0s. 78191 qualifying lines, 48336 candidate episodes across 3 variants.

| Cell | n | Exp/tr | OOS Exp | WF | p | BH-sig | Beats nulls | Verdict |
|---|---|---|---|---|---|---|---|---|
| V1_close_through_immediate::body::resistance(bullish) | 8959 | -184.02 | -181.67 | None | 0.0 | YES | partial | **FAIL** |
| V1_close_through_immediate::body::support(bearish) | 11089 | -150.02 | -131.32 | None | 0.0 | YES | partial | **FAIL** |
| V1_close_through_immediate::wick::resistance(bullish) | 4801 | -131.58 | -98.07 | None | 0.0 | YES | partial | **FAIL** |
| V1_close_through_immediate::wick::support(bearish) | 5678 | -152.66 | -171.99 | None | 0.0 | YES | partial | **FAIL** |
| V2_break_retest_entry::body::resistance(bullish) | 973 | -182.89 | -101.72 | None | 0.0 | YES | partial | **FAIL** |
| V2_break_retest_entry::body::support(bearish) | 1122 | -76.0 | -53.64 | None | 0.0 | YES | both | **FAIL** |
| V2_break_retest_entry::wick::resistance(bullish) | 322 | -252.06 | -151.43 | None | 0.0 | YES | partial | **FAIL** |
| V2_break_retest_entry::wick::support(bearish) | 409 | -67.82 | -126.86 | None | 0.0055 | YES | partial | **FAIL** |
| V3_break_volume_expansion::body::resistance(bullish) | 2573 | -87.36 | -78.46 | None | 0.0 | YES | partial | **FAIL** |
| V3_break_volume_expansion::body::support(bearish) | 4121 | -82.38 | -84.96 | None | 0.0 | YES | partial | **FAIL** |
| V3_break_volume_expansion::wick::resistance(bullish) | 1765 | -40.62 | -2.78 | None | 0.0005 | YES | both | **FAIL** |
| V3_break_volume_expansion::wick::support(bearish) | 2329 | -99.93 | -120.42 | None | 0.0 | YES | partial | **FAIL** |

Verdict counts: {'PASS': 0, 'FAIL': 12, 'INCONCLUSIVE_UNDERPOWERED': 0}