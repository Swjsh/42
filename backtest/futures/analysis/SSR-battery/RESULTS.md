# SSR Battery -- RESULTS

> Written by run_ssr_battery.py. Verdict-first per family.

<!-- SSR-FAMILY-B:START -->
## Family B -- regime

**VERDICT: KILL** (0/8 cells clear) -- generated 2026-08-07T14:13:32.553816

Symbols: GC=F @ 1h/730d, OOS cut 2026-01-01

### Data provenance

- GC=F: 13762 rows, 2024-03-15 00:00:00-04:00 .. 2026-08-07 15:00:00-04:00

### Cell table

| symbol | dir | zone | sweep | n | oos_n | oos_mean | total_net | beats_bh | fdr | drop_top3 | clears |
|---|---|---|---|---|---|---|---|---|---|---|---|
| GC=F | long | 0.25 | 0.1 | 186 | 41 | -463.01 | -118332.14 | False | False | -196776.92 | no |
| GC=F | long | 0.25 | 0.25 | 174 | 40 | -1122.83 | -128851.44 | False | False | -207296.22 | no |
| GC=F | long | 0.5 | 0.1 | 224 | 54 | -687.48 | -83101.82 | False | False | -171176.48 | no |
| GC=F | long | 0.5 | 0.25 | 204 | 51 | -1455.8 | -73958.19 | False | False | -162032.85 | no |
| GC=F | short | 0.25 | 0.1 | 175 | 31 | 221.94 | 112291.13 | True | False | 41879.38 | no |
| GC=F | short | 0.25 | 0.25 | 135 | 24 | -954.9 | 41672.41 | True | False | -28739.34 | no |
| GC=F | short | 0.5 | 0.1 | 192 | 35 | 852.5 | 138803.74 | True | False | 40380.58 | no |
| GC=F | short | 0.5 | 0.25 | 154 | 30 | 287.83 | 78871.39 | True | False | -19551.77 | no |

### Nulls & disclosures

- null_unavailable cells (0 trades or no eligible null bars, excluded from BH-FDR family): 0/8
- shadow-column fallback counts: {'vix_agree_fallback': 0, 'mag7_breadth_fallback': 0, 'vix_fetch_failed': 0, 'mag7_fetch_failed': 0}
- skip/degenerate counts (summed across all cells): {'skipped_while_open': 756, 'skipped_no_next_bar': 0, 'skipped_degenerate': 1, 'skipped_no_future_bars': 0, 'runner_fallback_3r': 232, 'runner_capped_5r': 77, 'snapshot_missing': 0, 'shift_mode_unknown': 0}

<!-- SSR-FAMILY-B:END -->



<!-- SSR-FAMILY-A:START -->
## Family A -- smoke

**VERDICT: KILL** (0/24 cells clear) -- generated 2026-08-07T14:13:15.557860

Symbols: GC=F, NQ=F, ES=F @ 15m/60d, OOS cut 2026-07-20

### Data provenance

- GC=F: 4618 rows, 2026-05-28 00:00:00-04:00 .. 2026-08-07 15:15:00-04:00
- NQ=F: 4618 rows, 2026-05-28 00:00:00-04:00 .. 2026-08-07 15:15:00-04:00
- ES=F: 4618 rows, 2026-05-28 00:00:00-04:00 .. 2026-08-07 15:15:00-04:00

### Cell table

| symbol | dir | zone | sweep | n | oos_n | oos_mean | total_net | beats_bh | fdr | drop_top3 | clears |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ES=F | long | 0.25 | 0.1 | 45 | 14 | 94.68 | -8174.39 | False | False | -25977.6 | no |
| ES=F | long | 0.25 | 0.25 | 39 | 12 | -244.88 | -9389.46 | False | False | -27192.67 | no |
| ES=F | long | 0.5 | 0.1 | 50 | 15 | -354.78 | -16512.03 | False | False | -33118.31 | no |
| ES=F | long | 0.5 | 0.25 | 44 | 13 | -737.37 | -21664.6 | False | False | -38270.88 | no |
| ES=F | short | 0.25 | 0.1 | 65 | 15 | 831.63 | 3250.91 | True | False | -22131.82 | no |
| ES=F | short | 0.25 | 0.25 | 61 | 14 | 904.23 | -4624.54 | True | False | -30007.27 | no |
| ES=F | short | 0.5 | 0.1 | 71 | 19 | 763.76 | 3746.42 | True | False | -22258.67 | no |
| ES=F | short | 0.5 | 0.25 | 65 | 15 | 858.15 | -1402.18 | True | False | -27407.27 | no |
| GC=F | long | 0.25 | 0.1 | 30 | 7 | 828.02 | -25315.37 | True | False | -46307.85 | no |
| GC=F | long | 0.25 | 0.25 | 29 | 6 | 1116.78 | -27140.77 | True | False | -48133.25 | no |
| GC=F | long | 0.5 | 0.1 | 34 | 9 | 261.27 | -24137.13 | True | False | -46874.91 | no |
| GC=F | long | 0.5 | 0.25 | 33 | 8 | 407.0 | -26472.44 | True | False | -48797.44 | no |
| GC=F | short | 0.25 | 0.1 | 38 | 13 | -1862.97 | 9569.42 | False | False | -19892.94 | no |
| GC=F | short | 0.25 | 0.25 | 34 | 12 | -1776.56 | 5407.39 | False | False | -24054.97 | no |
| GC=F | short | 0.5 | 0.1 | 45 | 16 | -1497.97 | 56207.67 | False | False | 16847.41 | no |
| GC=F | short | 0.5 | 0.25 | 39 | 14 | -1360.33 | 45236.82 | False | False | 5876.56 | no |
| NQ=F | long | 0.25 | 0.1 | 47 | 16 | 448.83 | -136245.49 | True | False | -179466.12 | no |
| NQ=F | long | 0.25 | 0.25 | 44 | 17 | -298.0 | -145991.5 | True | False | -190097.13 | no |
| NQ=F | long | 0.5 | 0.1 | 54 | 16 | 340.88 | -77635.95 | True | False | -131253.52 | no |
| NQ=F | long | 0.5 | 0.25 | 52 | 17 | -121.66 | -89139.15 | True | False | -143483.53 | no |
| NQ=F | short | 0.25 | 0.1 | 50 | 17 | -396.4 | 30886.37 | True | False | -32813.22 | no |
| NQ=F | short | 0.25 | 0.25 | 47 | 16 | -1032.29 | 55484.84 | True | False | -20454.44 | no |
| NQ=F | short | 0.5 | 0.1 | 53 | 16 | -287.98 | 4365.09 | True | False | -54984.69 | no |
| NQ=F | short | 0.5 | 0.25 | 50 | 15 | -906.46 | 35671.96 | True | False | -36247.51 | no |

### Nulls & disclosures

- null_unavailable cells (0 trades or no eligible null bars, excluded from BH-FDR family): 0/24
- shadow-column fallback counts: {'vix_agree_fallback': 0, 'mag7_breadth_fallback': 0, 'vix_fetch_failed': 0, 'mag7_fetch_failed': 0}
- skip/degenerate counts (summed across all cells): {'skipped_while_open': 657, 'skipped_no_next_bar': 0, 'skipped_degenerate': 0, 'skipped_no_future_bars': 0, 'runner_fallback_3r': 47, 'runner_capped_5r': 73, 'snapshot_missing': 0, 'shift_mode_unknown': 0}

### Headline with/without 2026-08-07 exhibit date

- WITH: $-364,018.11  WITHOUT: $-300,829.63  (n=20 trades on that date)

### Exhibit-date (2026-08-07) trades by symbol

| symbol | n | total_net | n_winners | n_losers |
|---|---|---|---|---|
| ES=F | 12 | -7867.44 | 4 | 8 |
| NQ=F | 8 | -55321.04 | 0 | 8 |

<!-- SSR-FAMILY-A:END -->



