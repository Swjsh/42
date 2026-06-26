# B10 — Exit Audit + Bounded Exit-Knob Sweep (3-edge book, real OPRA fills)

- Run: 2026-06-21  |  Window: 2025-01-01..2026-05-15  |  Trading days: 342
- Fills: real OPRA via lib.simulator_real.simulate_trade_real (C1)  |  OOS split: IS=2025 / OOS=2026  |  qty=3, premium stop -0.08
- Baseline v15 exits: {'tp1_premium_pct': 0.3, 'tp1_qty_fraction': 0.5, 'runner_target_pct': 2.5, 'time_stop_et': '15:50'}
- Sweep grid: {'tp1_premium_pct': [0.3, 0.5, 0.75], 'tp1_qty_fraction': [0.5, 0.667], 'runner_target_pct': [2.0, 2.5, 3.0], 'time_stop_et': ['15:30', '15:50'], 'n_configs_per_book': 36}

## VERDICT: **EXIT_IMPROVEMENT**

> At least one exit config cleared ALL gates (expectancy-lift + no-regression + OOS-drop-top5 + IS-broad-based) for a book (see Improvements). Reported for REVOKE.

## Phase 1 — Exit audit (which exit actually fires? L148/C30/C28)

| book | n | exp/tr | total$ | WR% | TP1-hit% | **runner-TARGET%** | **STOP%** | time-stop% | lvl/rib% | target near-dead? | stop>70%? |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Safe-2_ATM | 301 | $51.87 | $15613.96 | 52.5 | 35.5 | 0.7 | 46.8 | 7.6 | 44.9 | True | False |
| Bold_ITM2 | 225 | $97.21 | $21871.82 | 52.4 | 35.1 | 0.0 | 47.1 | 12.4 | 40.4 | True | False |

Exit-reason raw counts per book:
- **Safe-2_ATM**: {'TP1_THEN_RUNNER_RIBBON': 82, 'EXIT_ALL_PREMIUM_STOP': 141, 'EXIT_ALL_RIBBON_FLIP_BACK': 50, 'EXIT_ALL_LEVEL_STOP': 3, 'TP1_THEN_RUNNER_TIME': 21, 'EXIT_ALL_TIME_STOP': 2, 'TP1_THEN_RUNNER_TARGET': 2}
- **Bold_ITM2**: {'TP1_THEN_RUNNER_RIBBON': 51, 'EXIT_ALL_PREMIUM_STOP': 106, 'EXIT_ALL_RIBBON_FLIP_BACK': 37, 'TP1_THEN_RUNNER_TIME': 25, 'EXIT_ALL_LEVEL_STOP': 3, 'EXIT_ALL_TIME_STOP': 3}

## Phase 2 — Bounded exit-knob sweep (top configs by expectancy lift)

### Safe-2_ATM
- baseline (v15): exp=$51.87 total=$15613.96 n=301 | IS exp=$41.71 (n=220) OOS exp=$79.47 (n=81)

| tp1% | tp1_qty | runner× | time | exp/tr | lift$ | IS-lift$ | changed-net$ | n_better/worse | oos_exp | oos_drop5 | lift? | no-reg? | oos? | IS-broad? | CLEARS ALL |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0.75 | 0.5 | 3.0 | 15:30 | $65.1 | $13.23 | $5.75 | $3980.61 | 66/41 | $113.01 | $68.98 | True | True | True | True | **YES** |
| 0.75 | 0.5 | 2.0 | 15:30 | $64.66 | $12.79 | $8.52 | $3848.61 | 60/47 | $103.85 | $63.43 | True | True | True | True | **YES** |
| 0.75 | 0.5 | 2.5 | 15:30 | $64.51 | $12.64 | $6.83 | $3804.11 | 68/39 | $107.89 | $65.86 | True | True | True | True | **YES** |
| 0.75 | 0.667 | 2.0 | 15:30 | $62.63 | $10.76 | $11.52 | $3238.86 | 54/53 | $88.19 | $58.38 | True | True | True | True | **YES** |
| 0.75 | 0.667 | 2.5 | 15:30 | $62.63 | $10.76 | $11.52 | $3238.86 | 54/53 | $88.19 | $58.38 | True | True | True | True | **YES** |
| 0.75 | 0.667 | 3.0 | 15:30 | $62.63 | $10.76 | $11.52 | $3238.86 | 54/53 | $88.19 | $58.38 | True | True | True | True | **YES** |
| 0.75 | 0.5 | 2.0 | 15:50 | $62.25 | $10.38 | $6.42 | $3123.61 | 54/53 | $100.61 | $63.87 | True | True | True | True | **YES** |
| 0.75 | 0.5 | 3.0 | 15:50 | $61.08 | $9.21 | $1.83 | $2771.61 | 65/42 | $108.71 | $71.35 | True | True | True | True | **YES** |
| 0.75 | 0.5 | 2.5 | 15:50 | $60.66 | $8.79 | $3.19 | $2644.11 | 69/38 | $103.45 | $67.76 | True | True | True | True | **YES** |
| 0.75 | 0.667 | 2.0 | 15:50 | $60.0 | $8.13 | $9.1 | $2445.86 | 53/54 | $84.95 | $58.56 | True | True | True | True | **YES** |
| 0.75 | 0.667 | 2.5 | 15:50 | $60.0 | $8.13 | $9.1 | $2445.86 | 53/54 | $84.95 | $58.56 | True | True | True | True | **YES** |
| 0.75 | 0.667 | 3.0 | 15:50 | $60.0 | $8.13 | $9.1 | $2445.86 | 53/54 | $84.95 | $58.56 | True | True | True | True | **YES** |

### Bold_ITM2
- baseline (v15): exp=$97.21 total=$21871.82 n=225 | IS exp=$84.33 (n=165) OOS exp=$132.63 (n=60)

| tp1% | tp1_qty | runner× | time | exp/tr | lift$ | IS-lift$ | changed-net$ | n_better/worse | oos_exp | oos_drop5 | lift? | no-reg? | oos? | IS-broad? | CLEARS ALL |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0.75 | 0.5 | 3.0 | 15:30 | $114.38 | $17.17 | $12.63 | $3862.64 | 50/29 | $162.26 | $92.21 | True | True | True | True | **YES** |
| 0.75 | 0.5 | 3.0 | 15:50 | $113.93 | $16.72 | $12.05 | $3762.64 | 54/25 | $162.2 | $93.96 | True | True | True | True | **YES** |
| 0.75 | 0.5 | 2.5 | 15:30 | $112.95 | $15.74 | $11.9 | $3541.14 | 51/28 | $158.91 | $91.75 | True | True | True | True | **YES** |
| 0.75 | 0.5 | 2.5 | 15:50 | $112.24 | $15.03 | $11.27 | $3381.14 | 55/24 | $157.97 | $92.57 | True | True | True | True | **YES** |
| 0.75 | 0.5 | 2.0 | 15:30 | $110.91 | $13.7 | $11.12 | $3083.64 | 44/35 | $153.43 | $85.61 | True | True | True | True | **YES** |
| 0.75 | 0.5 | 2.0 | 15:50 | $110.88 | $13.67 | $10.72 | $3075.64 | 47/32 | $154.4 | $88.73 | True | True | True | True | **YES** |
| 0.5 | 0.5 | 3.0 | 15:30 | $105.63 | $8.42 | $4.33 | $1895.14 | 59/20 | $152.31 | $85.82 | True | True | True | True | **YES** |
| 0.5 | 0.5 | 3.0 | 15:50 | $105.22 | $8.01 | $3.79 | $1802.14 | 64/15 | $152.24 | $87.23 | True | True | True | True | **YES** |
| 0.75 | 0.667 | 2.0 | 15:50 | $104.88 | $7.67 | $11.17 | $1725.14 | 37/42 | $130.66 | $82.83 | True | True | True | True | **YES** |
| 0.75 | 0.667 | 2.5 | 15:50 | $104.88 | $7.67 | $11.17 | $1725.14 | 37/42 | $130.66 | $82.83 | True | True | True | True | **YES** |
| 0.75 | 0.667 | 3.0 | 15:50 | $104.88 | $7.67 | $11.17 | $1725.14 | 37/42 | $130.66 | $82.83 | True | True | True | True | **YES** |
| 0.5 | 0.5 | 2.5 | 15:30 | $104.67 | $7.46 | $3.6 | $1679.14 | 58/21 | $150.71 | $85.34 | True | True | True | True | **YES** |

## Improvements (cleared ALL gates: lift + no-regression + OOS-drop-top5 + IS-broad) — reported for REVOKE

- **Safe-2_ATM** cfg={'tp1_premium_pct': 0.3, 'tp1_qty_fraction': 0.5, 'runner_target_pct': 2.0, 'time_stop_et': '15:30'}: exp lift $2.15 (IS $46.48 / OOS $74.51), changed-net $646.5 (12 better / 15 worse), OOS exp $74.51 (drop-top5 $40.93)
- **Safe-2_ATM** cfg={'tp1_premium_pct': 0.3, 'tp1_qty_fraction': 0.5, 'runner_target_pct': 2.0, 'time_stop_et': '15:50'}: exp lift $0.77 (IS $44.55 / OOS $74.63), changed-net $231.5 (6 better / 17 worse), OOS exp $74.63 (drop-top5 $41.25)
- **Safe-2_ATM** cfg={'tp1_premium_pct': 0.3, 'tp1_qty_fraction': 0.5, 'runner_target_pct': 2.5, 'time_stop_et': '15:30'}: exp lift $2.28 (IS $45.01 / OOS $78.97), changed-net $684.0 (13 better / 8 worse), OOS exp $78.97 (drop-top5 $41.95)
- **Safe-2_ATM** cfg={'tp1_premium_pct': 0.3, 'tp1_qty_fraction': 0.5, 'runner_target_pct': 3.0, 'time_stop_et': '15:30'}: exp lift $1.57 (IS $43.92 / OOS $79.3), changed-net $472.5 (15 better / 10 worse), OOS exp $79.3 (drop-top5 $43.22)
- **Safe-2_ATM** cfg={'tp1_premium_pct': 0.5, 'tp1_qty_fraction': 0.5, 'runner_target_pct': 2.0, 'time_stop_et': '15:30'}: exp lift $1.5 (IS $42.2 / OOS $83.69), changed-net $449.68 (72 better / 35 worse), OOS exp $83.69 (drop-top5 $48.84)
- **Safe-2_ATM** cfg={'tp1_premium_pct': 0.5, 'tp1_qty_fraction': 0.667, 'runner_target_pct': 2.0, 'time_stop_et': '15:30'}: exp lift $0.6 (IS $43.6 / OOS $76.56), changed-net $178.68 (67 better / 40 worse), OOS exp $76.56 (drop-top5 $54.42)
- **Safe-2_ATM** cfg={'tp1_premium_pct': 0.5, 'tp1_qty_fraction': 0.667, 'runner_target_pct': 2.5, 'time_stop_et': '15:30'}: exp lift $0.6 (IS $43.6 / OOS $76.56), changed-net $178.68 (67 better / 40 worse), OOS exp $76.56 (drop-top5 $54.42)
- **Safe-2_ATM** cfg={'tp1_premium_pct': 0.5, 'tp1_qty_fraction': 0.667, 'runner_target_pct': 3.0, 'time_stop_et': '15:30'}: exp lift $0.6 (IS $43.6 / OOS $76.56), changed-net $178.68 (67 better / 40 worse), OOS exp $76.56 (drop-top5 $54.42)
- **Safe-2_ATM** cfg={'tp1_premium_pct': 0.75, 'tp1_qty_fraction': 0.5, 'runner_target_pct': 2.0, 'time_stop_et': '15:30'}: exp lift $12.79 (IS $50.23 / OOS $103.85), changed-net $3848.61 (60 better / 47 worse), OOS exp $103.85 (drop-top5 $63.43)
- **Safe-2_ATM** cfg={'tp1_premium_pct': 0.75, 'tp1_qty_fraction': 0.5, 'runner_target_pct': 2.0, 'time_stop_et': '15:50'}: exp lift $10.38 (IS $48.13 / OOS $100.61), changed-net $3123.61 (54 better / 53 worse), OOS exp $100.61 (drop-top5 $63.87)
- **Safe-2_ATM** cfg={'tp1_premium_pct': 0.75, 'tp1_qty_fraction': 0.5, 'runner_target_pct': 2.5, 'time_stop_et': '15:30'}: exp lift $12.64 (IS $48.54 / OOS $107.89), changed-net $3804.11 (68 better / 39 worse), OOS exp $107.89 (drop-top5 $65.86)
- **Safe-2_ATM** cfg={'tp1_premium_pct': 0.75, 'tp1_qty_fraction': 0.5, 'runner_target_pct': 2.5, 'time_stop_et': '15:50'}: exp lift $8.79 (IS $44.9 / OOS $103.45), changed-net $2644.11 (69 better / 38 worse), OOS exp $103.45 (drop-top5 $67.76)
- **Safe-2_ATM** cfg={'tp1_premium_pct': 0.75, 'tp1_qty_fraction': 0.5, 'runner_target_pct': 3.0, 'time_stop_et': '15:30'}: exp lift $13.23 (IS $47.46 / OOS $113.01), changed-net $3980.61 (66 better / 41 worse), OOS exp $113.01 (drop-top5 $68.98)
- **Safe-2_ATM** cfg={'tp1_premium_pct': 0.75, 'tp1_qty_fraction': 0.5, 'runner_target_pct': 3.0, 'time_stop_et': '15:50'}: exp lift $9.21 (IS $43.54 / OOS $108.71), changed-net $2771.61 (65 better / 42 worse), OOS exp $108.71 (drop-top5 $71.35)
- **Safe-2_ATM** cfg={'tp1_premium_pct': 0.75, 'tp1_qty_fraction': 0.667, 'runner_target_pct': 2.0, 'time_stop_et': '15:30'}: exp lift $10.76 (IS $53.23 / OOS $88.19), changed-net $3238.86 (54 better / 53 worse), OOS exp $88.19 (drop-top5 $58.38)
- **Safe-2_ATM** cfg={'tp1_premium_pct': 0.75, 'tp1_qty_fraction': 0.667, 'runner_target_pct': 2.0, 'time_stop_et': '15:50'}: exp lift $8.13 (IS $50.81 / OOS $84.95), changed-net $2445.86 (53 better / 54 worse), OOS exp $84.95 (drop-top5 $58.56)
- **Safe-2_ATM** cfg={'tp1_premium_pct': 0.75, 'tp1_qty_fraction': 0.667, 'runner_target_pct': 2.5, 'time_stop_et': '15:30'}: exp lift $10.76 (IS $53.23 / OOS $88.19), changed-net $3238.86 (54 better / 53 worse), OOS exp $88.19 (drop-top5 $58.38)
- **Safe-2_ATM** cfg={'tp1_premium_pct': 0.75, 'tp1_qty_fraction': 0.667, 'runner_target_pct': 2.5, 'time_stop_et': '15:50'}: exp lift $8.13 (IS $50.81 / OOS $84.95), changed-net $2445.86 (53 better / 54 worse), OOS exp $84.95 (drop-top5 $58.56)
- **Safe-2_ATM** cfg={'tp1_premium_pct': 0.75, 'tp1_qty_fraction': 0.667, 'runner_target_pct': 3.0, 'time_stop_et': '15:30'}: exp lift $10.76 (IS $53.23 / OOS $88.19), changed-net $3238.86 (54 better / 53 worse), OOS exp $88.19 (drop-top5 $58.38)
- **Safe-2_ATM** cfg={'tp1_premium_pct': 0.75, 'tp1_qty_fraction': 0.667, 'runner_target_pct': 3.0, 'time_stop_et': '15:50'}: exp lift $8.13 (IS $50.81 / OOS $84.95), changed-net $2445.86 (53 better / 54 worse), OOS exp $84.95 (drop-top5 $58.56)
- **Bold_ITM2** cfg={'tp1_premium_pct': 0.3, 'tp1_qty_fraction': 0.5, 'runner_target_pct': 2.5, 'time_stop_et': '15:30'}: exp lift $2.04 (IS $86.06 / OOS $135.53), changed-net $459.0 (14 better / 13 worse), OOS exp $135.53 (drop-top5 $73.47)
- **Bold_ITM2** cfg={'tp1_premium_pct': 0.3, 'tp1_qty_fraction': 0.5, 'runner_target_pct': 3.0, 'time_stop_et': '15:30'}: exp lift $3.0 (IS $86.78 / OOS $137.13), changed-net $675.0 (17 better / 12 worse), OOS exp $137.13 (drop-top5 $73.03)
- **Bold_ITM2** cfg={'tp1_premium_pct': 0.3, 'tp1_qty_fraction': 0.5, 'runner_target_pct': 3.0, 'time_stop_et': '15:50'}: exp lift $0.94 (IS $85.1 / OOS $134.03), changed-net $212.0 (7 better / 2 worse), OOS exp $134.03 (drop-top5 $74.53)
- **Bold_ITM2** cfg={'tp1_premium_pct': 0.5, 'tp1_qty_fraction': 0.5, 'runner_target_pct': 2.0, 'time_stop_et': '15:30'}: exp lift $4.75 (IS $86.86 / OOS $143.48), changed-net $1068.14 (54 better / 25 worse), OOS exp $143.48 (drop-top5 $79.19)
- **Bold_ITM2** cfg={'tp1_premium_pct': 0.5, 'tp1_qty_fraction': 0.5, 'runner_target_pct': 2.0, 'time_stop_et': '15:50'}: exp lift $4.57 (IS $86.27 / OOS $144.44), changed-net $1029.14 (57 better / 22 worse), OOS exp $144.44 (drop-top5 $82.32)
- **Bold_ITM2** cfg={'tp1_premium_pct': 0.5, 'tp1_qty_fraction': 0.5, 'runner_target_pct': 2.5, 'time_stop_et': '15:30'}: exp lift $7.46 (IS $87.93 / OOS $150.71), changed-net $1679.14 (58 better / 21 worse), OOS exp $150.71 (drop-top5 $85.34)
- **Bold_ITM2** cfg={'tp1_premium_pct': 0.5, 'tp1_qty_fraction': 0.5, 'runner_target_pct': 2.5, 'time_stop_et': '15:50'}: exp lift $7.07 (IS $87.34 / OOS $150.84), changed-net $1590.14 (66 better / 13 worse), OOS exp $150.84 (drop-top5 $88.47)
- **Bold_ITM2** cfg={'tp1_premium_pct': 0.5, 'tp1_qty_fraction': 0.5, 'runner_target_pct': 3.0, 'time_stop_et': '15:30'}: exp lift $8.42 (IS $88.66 / OOS $152.31), changed-net $1895.14 (59 better / 20 worse), OOS exp $152.31 (drop-top5 $85.82)
- **Bold_ITM2** cfg={'tp1_premium_pct': 0.5, 'tp1_qty_fraction': 0.5, 'runner_target_pct': 3.0, 'time_stop_et': '15:50'}: exp lift $8.01 (IS $88.12 / OOS $152.24), changed-net $1802.14 (64 better / 15 worse), OOS exp $152.24 (drop-top5 $87.23)
- **Bold_ITM2** cfg={'tp1_premium_pct': 0.75, 'tp1_qty_fraction': 0.5, 'runner_target_pct': 2.0, 'time_stop_et': '15:30'}: exp lift $13.7 (IS $95.45 / OOS $153.43), changed-net $3083.64 (44 better / 35 worse), OOS exp $153.43 (drop-top5 $85.61)
- **Bold_ITM2** cfg={'tp1_premium_pct': 0.75, 'tp1_qty_fraction': 0.5, 'runner_target_pct': 2.0, 'time_stop_et': '15:50'}: exp lift $13.67 (IS $95.05 / OOS $154.4), changed-net $3075.64 (47 better / 32 worse), OOS exp $154.4 (drop-top5 $88.73)
- **Bold_ITM2** cfg={'tp1_premium_pct': 0.75, 'tp1_qty_fraction': 0.5, 'runner_target_pct': 2.5, 'time_stop_et': '15:30'}: exp lift $15.74 (IS $96.23 / OOS $158.91), changed-net $3541.14 (51 better / 28 worse), OOS exp $158.91 (drop-top5 $91.75)
- **Bold_ITM2** cfg={'tp1_premium_pct': 0.75, 'tp1_qty_fraction': 0.5, 'runner_target_pct': 2.5, 'time_stop_et': '15:50'}: exp lift $15.03 (IS $95.6 / OOS $157.97), changed-net $3381.14 (55 better / 24 worse), OOS exp $157.97 (drop-top5 $92.57)
- **Bold_ITM2** cfg={'tp1_premium_pct': 0.75, 'tp1_qty_fraction': 0.5, 'runner_target_pct': 3.0, 'time_stop_et': '15:30'}: exp lift $17.17 (IS $96.96 / OOS $162.26), changed-net $3862.64 (50 better / 29 worse), OOS exp $162.26 (drop-top5 $92.21)
- **Bold_ITM2** cfg={'tp1_premium_pct': 0.75, 'tp1_qty_fraction': 0.5, 'runner_target_pct': 3.0, 'time_stop_et': '15:50'}: exp lift $16.72 (IS $96.38 / OOS $162.2), changed-net $3762.64 (54 better / 25 worse), OOS exp $162.2 (drop-top5 $93.96)
- **Bold_ITM2** cfg={'tp1_premium_pct': 0.75, 'tp1_qty_fraction': 0.667, 'runner_target_pct': 2.0, 'time_stop_et': '15:30'}: exp lift $7.4 (IS $95.3 / OOS $130.21), changed-net $1666.14 (36 better / 43 worse), OOS exp $130.21 (drop-top5 $81.02)
- **Bold_ITM2** cfg={'tp1_premium_pct': 0.75, 'tp1_qty_fraction': 0.667, 'runner_target_pct': 2.0, 'time_stop_et': '15:50'}: exp lift $7.67 (IS $95.5 / OOS $130.66), changed-net $1725.14 (37 better / 42 worse), OOS exp $130.66 (drop-top5 $82.83)
- **Bold_ITM2** cfg={'tp1_premium_pct': 0.75, 'tp1_qty_fraction': 0.667, 'runner_target_pct': 2.5, 'time_stop_et': '15:30'}: exp lift $7.4 (IS $95.3 / OOS $130.21), changed-net $1666.14 (36 better / 43 worse), OOS exp $130.21 (drop-top5 $81.02)
- **Bold_ITM2** cfg={'tp1_premium_pct': 0.75, 'tp1_qty_fraction': 0.667, 'runner_target_pct': 2.5, 'time_stop_et': '15:50'}: exp lift $7.67 (IS $95.5 / OOS $130.66), changed-net $1725.14 (37 better / 42 worse), OOS exp $130.66 (drop-top5 $82.83)
- **Bold_ITM2** cfg={'tp1_premium_pct': 0.75, 'tp1_qty_fraction': 0.667, 'runner_target_pct': 3.0, 'time_stop_et': '15:30'}: exp lift $7.4 (IS $95.3 / OOS $130.21), changed-net $1666.14 (36 better / 43 worse), OOS exp $130.21 (drop-top5 $81.02)
- **Bold_ITM2** cfg={'tp1_premium_pct': 0.75, 'tp1_qty_fraction': 0.667, 'runner_target_pct': 3.0, 'time_stop_et': '15:50'}: exp lift $7.67 (IS $95.5 / OOS $130.66), changed-net $1725.14 (37 better / 42 worse), OOS exp $130.66 (drop-top5 $82.83)

> **C28/C30 honest read:** the lift is driven almost entirely by raising `tp1_premium_pct` (0.30 -> 0.50/0.75) — i.e. take partial profit LATER / let more of the position run — NOT by the runner-target knob (which the Phase-1 audit shows is a near-dead knob, hit <1% of the time). The take-profit threshold is a real exit lever; the runner cap is theater. Tradeoff to weigh before flipping: a higher TP1 banks less early and carries more theta/stop exposure on the days it does not run — verify against the per-trade variance, not just the mean.

## WP-4 caveat resolved — VARIANCE / DOWNSIDE audit (the mean is real but it is RISK_UP, not a clean win)

> Generated by `backtest/autoresearch/_b10_exit_variance.py` → `analysis/recommendations/B10-EXIT-VARIANCE.json`. The open caveat above ("verify the variance, not just the mean") is now answered with real OPRA numbers. **Winning config** = tp1=0.75 / tp1_qty=0.50 / runner=3.0x / time=15:30 vs **v15 baseline** tp1=0.30 / 0.50 / 2.5x / 15:50.

### Per-trade distribution (real OPRA fills, 342 trading days)

| book | metric | baseline +30% | winning +75% | read |
|---|---|---|---|---|
| **Safe-2 ATM** | mean | $51.87 | **$65.10** | +$13.23 mean lift (confirmed) |
| | std | $155.54 | **$201.99** | variance up +30% |
| | **Sharpe/tr (mean/std)** | **0.3335** | **0.3223** | **DROPS** — risk grows faster than return |
| | skew | 2.782 | 2.831 | more right-tail dependent |
| | median trade | **+$21.60** | **−$24.72** | **median flips POSITIVE→NEGATIVE** |
| | P05 / P25 | −$75.12 / −$33.84 | −$81.36 / −$39.60 | left tail deeper |
| | P75 / P95 | $67.20 / $377.40 | $104.25 / $559.50 | right tail richer (where the mean comes from) |
| | % losing trades | 47.5% | **59.5%** | majority of trades now lose |
| | worst single trade | −$211.68 | −$211.68 | unchanged (stop caps tail) |
| **Bold ITM-2** | mean | $97.21 | **$114.38** | +$17.17 mean lift (confirmed) |
| | std | $238.95 | **$292.69** | variance up +22% |
| | **Sharpe/tr** | **0.4068** | **0.3908** | **DROPS** |
| | median trade | **+$31.50** | **−$52.32** | **median flips POSITIVE→NEGATIVE** |
| | P05 / P25 | −$90.72 / −$65.76 | −$93.79 / −$69.12 | left tail deeper |
| | P75 / P95 | $147.00 / $692.34 | $207.00 / $799.80 | right tail richer |
| | % losing trades | 47.6% | **57.3%** | majority now lose |
| | worst single trade | −$223.68 | −$223.68 | unchanged |

**The shape:** +75% TP1 makes the book MORE lottery-like — the median trade turns negative, >57% of trades lose, and the entire positive expectancy is carried by a fatter right tail (P95 up ~$180–$110). The mean rises but per-trade Sharpe falls in BOTH books. This is precisely the "raises the mean by taking on disproportionate tail risk" failure mode the caveat warned about.

### Downside-specific — the no-run-day exposure (trades that get WORSE under +75%)

| book | shared | n worse | $ given back | n better | $ gained | net | mechanism |
|---|---|---|---|---|---|---|---|
| **Safe-2 ATM** | 301 | **41** | **−$4,156** | 66 | +$8,137 | +$3,981 | 87.8% of worse trades never hit TP1; **36 of 41 flip green→red**; worse-set mean $98.38→**−$2.99** |
| **Bold ITM-2** | 225 | **29** | **−$3,997** | 50 | +$7,860 | +$3,863 | 86.2% never hit TP1; **22 of 29 flip green→red**; worse-set mean $179.18→**+$41.33** |

- **Worse-set exit mix at +75% is dominated by `EXIT_ALL_PREMIUM_STOP`** (36/41 Safe, 22/29 Bold). This is the caveat's exact mechanism, confirmed: on days the trade does NOT run, +30% would have banked the partial at TP1 and de-risked; +75% leaves TP1 unreached, so the full position rides to the −8% stop or to time. The give-back is **banked profit converted into losses**, not merely "less upside."
- The net of the changed set is still positive (+$3,981 / +$3,863) — that is the same number the Phase-2 no-regression gate already passed. The new finding is **HOW that net is composed**: ~$4K of realized winners are sacrificed to capture ~$8K of bigger winners. That is a higher-variance bet, not a free lunch.

### Book-level (daily-equity) risk

| book | metric | baseline +30% | winning +75% | read |
|---|---|---|---|---|
| **Safe-2 ATM** | **max drawdown** | **−$836.40** | **−$1,282.41** | **+53.3% deeper** (material) |
| | worst day | −$423.36 | −$423.36 | unchanged |
| | downside dev (daily) | $70.07 | $84.32 | +20% |
| | Sharpe (annualized) | **5.777** | **5.251** | DROPS |
| | **Sortino (annualized)** | 23.742 | **24.757** | marginally HOLDS/up |
| **Bold ITM-2** | **max drawdown** | **−$847.80** | **−$1,269.66** | **+49.8% deeper** (material) |
| | worst day | −$447.36 | −$447.36 | unchanged |
| | downside dev (daily) | $79.20 | $90.74 | +15% |
| | Sharpe (annualized) | **6.452** | **6.238** | DROPS |
| | **Sortino (annualized)** | 29.422 | **30.217** | marginally HOLDS/up |

- **maxDD widens ~50% on BOTH books** (−$836→−$1,282 Safe; −$848→−$1,270 Bold). Threshold for "material worsening" was set at +25%; both blow past it. This is the single most important risk number: a Safe-2 maxDD of −$1,282 is **2.1× the −$600/day kill-switch** and ~3× a single worst day, so the higher-TP1 drawdown is no longer "~1.4× a single bad day" (the WP-0/B9 sizing assumption) — it is materially larger and must be sized around.
- **Sortino marginally improves** while **Sharpe drops** — a tell-tale of fatter UP-tail. Sortino ignores upside volatility, so the richer P95 winners inflate it; the symmetric Sharpe (and the per-trade Sharpe) correctly penalizes the added two-sided variance. When Sharpe and Sortino disagree like this, the honest read is "more upside-skewed, not more risk-adjusted-efficient."

### VERDICT: **RISK_UP** (both books) — NOT a clean auto-flip

The decisive read: **+75% TP1 raises the MEAN by taking on disproportionate tail/drawdown risk.** Concretely, in BOTH books: higher mean ✔ — but per-trade Sharpe DROPS, median trade flips negative, % losing trades crosses 57–60%, and book maxDD widens ~50% (material). Book Sortino marginally holds only because it ignores the (growing) upside variance. This fails the CLEAN_WIN bar (which required higher mean AND per-trade-Sharpe holds AND maxDD not materially worse).

**WP-4 therefore needs J's explicit risk-tradeoff call**, presented as both numbers: "+$13.23/tr (Safe) / +$17.17/tr (Bold) higher expected value, in exchange for ~50% deeper max drawdown, a per-trade Sharpe that slips, and a majority-losing / right-tail-dependent return shape." A pure-expectancy maximizer flips it; a drawdown-sensitive operator at a $2K account near a −$600 kill-switch may NOT want a −$1,282 historical maxDD. **Bull-tape caveat applies: the OOS is 2026-bull, so the rich right tail is partly bull-flattered and the realized maxDD in chop/bear could be deeper than −$1,282.** The comparison itself (tp75 vs tp30 on the same tape) is bias-cancelled and robust; the absolute Sharpe/Sortino are not a forecast.

> Intermediate configs (tp1=+50%) capture roughly half the mean lift ($8.42/tr Safe, $7.46/tr Bold per Phase-2) with materially less variance — if J wants the expectancy bump without the full drawdown hit, **+50% is the risk-moderated middle**, and is the recommended fallback if J declines full +75%.

## How to read this

- **Phase 1** is the L148/C30 dead-knob audit: if `runner-TARGET%` < ~10% the 2.5x runner cap almost never fires (near-dead knob — sweeping it is theater). `STOP%` > 70% (C28) means exit-tuning is diminishing-returns — the trades are dying at the stop, not at the exit target, so the lever that matters is ENTRY/STOP, not the take-profit.
- **Phase 2** gates honestly: a config must lift book expectancy AND net-improve the trades it actually changes (no-regression, L174) AND survive OOS-alone with the 5 best OOS trades removed (C4 single-trade-carry guard).
- **EXIT_CONFIRMED_OPTIMAL** = the honest 'stop chasing exits' verdict; **EXIT_IMPROVEMENT** = a config genuinely beats v15 on real fills and is reported for REVOKE.
- Real OPRA fills (C1); per-trade EXPECTANCY not WR (OP-14); exits-only sweep (entries identical — `shared_keys` confirms).
