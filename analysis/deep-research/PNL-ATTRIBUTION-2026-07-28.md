# P&L ATTRIBUTION -- where the replay's +$5k comes from, where it leaks

Generated 2026-07-27T22:12:42.060203. Tool: `backtest/tools/pnl_attribution_2026_07_28.py`. Machine-readable: `analysis/deep-research/PNL-ATTRIBUTION-2026-07-28.json`.

Population: the 2026-07-23 full-history replay's 190 real-OPRA trades (`analysis\recommendations\engine-fullhist-replay-2026-07-23.json`), total **$+5,064.75** (recomputed from per-trade rows; matches stored headline $+5,064.75). PROVISIONAL per the replay's own fidelity disclosure: trade-level anchors vs live are 1/4 on 2026-07-17 (corrected 2026-07-25) -- entry layer diverges from live because live levels come from the curated key-levels.json feed while the replay recomputes levels from bars. Treat cohort CONTRASTS as the signal, not absolute dollars.

## Verdict (descriptive -- no search, no BH needed)

- **The money is level-tied.** LEVEL_tied (n=57) **$+5,098.05** + BOTH (n=9) $+1,796.80 = $+6,894.85 -- MORE than 100% of the book's $+5,064.75.
- **The leak is trendline-only.** TL_only (n=124, ALL bear) **$-1,830.10**, WR 0.19, $-14.76/trade.
- This is the P&L answer to the standing 233-vs-28 question: live bear ENTER verdicts are 233 trendline-only vs 28 level-tied (core-decisions.jsonl, re-counted tonight: 233 of 261) -- i.e. ~89% of live bear entry volume is the class that LOSES money in the 18-month replay, and the class that makes the money fires rarely.
- **Gate-add A/B result (pre-registered, full rerun, see bottom sections):** `min_triggers_bear` 1 -> 2 kills exactly the 120 singleton trendline bear entries; delta **+$2,568.05** (baseline $+5,064.75 -> variant $+7,632.80, WR 0.295 -> 0.473, maxDD -$2,233 -> -$1,881), **ALL 4 gates pass incl. held-out (+$652)** -- BUT delta-by-regime is 2025H1 +$1,218 / 2025H2 +$1,493 / **2026 -$143**, and the last live month's trendline-only fills are POSITIVE (+$565, n=35). Sub-window NOT stable -> **SHIP_CANDIDATE staged, NOT auto-ratify.**

## Replay cohort tables

### Replay by trigger_class

| Cohort | n | Total | $/trade | WR | drop-best | drop-worst | days +/- |
|---|---|---|---|---|---|---|---|
| LEVEL_tied | 57 | $+5,098.05 (101%) | $+89.44 | 0.47 | $+4,238.10 | $+5,677.05 | 25/26 |
| BOTH | 9 | $+1,796.80 (35%) | $+199.64 | 0.56 | $+1,140.80 | $+2,152.30 | 4/3 |
| TL_only | 124 | $-1,830.10 (-36%) | $-14.76 | 0.19 | $-2,446.10 | $-1,524.10 | 21/76 |

### Replay by tier

| Cohort | n | Total | $/trade | WR | drop-best | drop-worst | days +/- |
|---|---|---|---|---|---|---|---|
| SUPER | 37 | $+5,127.10 (101%) | $+138.57 | 0.51 | $+4,267.15 | $+5,706.10 | 18/14 |
| ELITE | 11 | $+2,758.20 (54%) | $+250.75 | 0.73 | $+2,052.65 | $+3,226.20 | 7/3 |
| LEVEL | 18 | $-990.45 (-20%) | $-55.03 | 0.28 | $-1,448.80 | $-666.45 | 5/12 |
| TRENDLINE | 124 | $-1,830.10 (-36%) | $-14.76 | 0.19 | $-2,446.10 | $-1,524.10 | 21/76 |

### Replay by setup

| Cohort | n | Total | $/trade | WR | drop-best | drop-worst | days +/- |
|---|---|---|---|---|---|---|---|
| BEARISH_REJECTION_RIDE_THE_RIBBON | 151 | $+2,729.35 (54%) | $+18.08 | 0.26 | $+2,023.80 | $+3,308.35 | 33/80 |
| BULLISH_RECLAIM_RIDE_THE_RIBBON | 39 | $+2,335.40 (46%) | $+59.88 | 0.41 | $+1,475.45 | $+2,659.40 | 16/21 |

### Replay by side

| Cohort | n | Total | $/trade | WR | drop-best | drop-worst | days +/- |
|---|---|---|---|---|---|---|---|
| P | 151 | $+2,729.35 (54%) | $+18.08 | 0.26 | $+2,023.80 | $+3,308.35 | 33/80 |
| C | 39 | $+2,335.40 (46%) | $+59.88 | 0.41 | $+1,475.45 | $+2,659.40 | 16/21 |

### Replay by entry_hour

| Cohort | n | Total | $/trade | WR | drop-best | drop-worst | days +/- |
|---|---|---|---|---|---|---|---|
| 13 | 40 | $+2,573.50 (51%) | $+64.34 | 0.35 | $+1,821.50 | $+2,819.50 | 14/25 |
| 09 | 23 | $+1,470.70 (29%) | $+63.94 | 0.43 | $+610.75 | $+1,938.70 | 10/13 |
| 14 | 40 | $+1,127.60 (22%) | $+28.19 | 0.28 | $+471.60 | $+1,483.10 | 11/29 |
| 11 | 32 | $+575.25 (11%) | $+17.98 | 0.22 | $-81.60 | $+817.25 | 7/25 |
| 12 | 33 | $+269.30 (5%) | $+8.16 | 0.24 | $-276.35 | $+429.30 | 8/25 |
| 15 | 4 | $-330.20 (-7%) | $-82.55 | 0.00 | $-288.80 | $-208.40 | 0/4 |
| 10 | 18 | $-621.40 (-12%) | $-34.52 | 0.33 | $-1,326.95 | $-42.40 | 6/12 |

### Replay by exit_family

| Cohort | n | Total | $/trade | WR | drop-best | drop-worst | days +/- |
|---|---|---|---|---|---|---|---|
| runner_stop | 35 | $+15,774.05 (311%) | $+450.69 | 1.00 | $+14,914.10 | $+15,637.50 | 32/0 |
| time_stop_15:50 (runner) | 4 | $+2,556.00 (50%) | $+639.00 | 1.00 | $+1,804.00 | $+1,984.00 | 4/0 |
| time_stop_15:50 | 6 | $+280.00 (6%) | $+46.67 | 0.67 | $-29.00 | $+586.00 | 4/2 |
| ribbon_flip_back | 19 | $+205.00 (4%) | $+10.79 | 0.42 | $-119.00 | $+322.00 | 8/10 |
| structure_stop | 34 | $-5,166.00 (-102%) | $-151.94 | 0.15 | $-5,546.00 | $-4,587.00 | 5/27 |
| premium_stop | 92 | $-8,584.30 (-169%) | $-93.31 | 0.00 | $-8,565.70 | $-8,194.30 | 0/80 |

### Replay by resolved_stop_mode

| Cohort | n | Total | $/trade | WR | drop-best | drop-worst | days +/- |
|---|---|---|---|---|---|---|---|
| structure | 66 | $+6,894.85 (136%) | $+104.47 | 0.48 | $+6,034.90 | $+7,473.85 | 29/27 |
| premium | 124 | $-1,830.10 (-36%) | $-14.76 | 0.19 | $-2,446.10 | $-1,524.10 | 21/76 |

### Replay by vix_band

| Cohort | n | Total | $/trade | WR | drop-best | drop-worst | days +/- |
|---|---|---|---|---|---|---|---|
| mid | 149 | $+2,462.55 (49%) | $+16.53 | 0.29 | $+1,757.00 | $+3,041.55 | 37/72 |
| low | 15 | $+1,768.65 (35%) | $+117.91 | 0.33 | $+908.70 | $+2,020.65 | 5/5 |
| elevated | 25 | $+767.55 (15%) | $+30.70 | 0.28 | $+15.55 | $+1,157.55 | 5/16 |
| unknown | 1 | $+66.00 (1%) | $+66.00 | 1.00 | $+0.00 | $+0.00 | 1/0 |

### Replay by day_type

| Cohort | n | Total | $/trade | WR | drop-best | drop-worst | days +/- |
|---|---|---|---|---|---|---|---|
| trend | 59 | $+3,516.95 (69%) | $+59.61 | 0.32 | $+2,657.00 | $+4,095.95 | 17/21 |
| range | 80 | $+2,629.10 (52%) | $+32.86 | 0.35 | $+1,923.55 | $+3,097.10 | 23/35 |
| unclassified | 3 | $+649.70 (13%) | $+216.57 | 0.67 | $+104.05 | $+725.90 | 2/1 |
| unknown | 1 | $+66.00 (1%) | $+66.00 | 1.00 | $+0.00 | $+0.00 | 1/0 |
| chop | 47 | $-1,797.00 (-35%) | $-38.23 | 0.13 | $-2,239.00 | $-1,561.00 | 5/36 |

### Replay by regime

| Cohort | n | Total | $/trade | WR | drop-best | drop-worst | days +/- |
|---|---|---|---|---|---|---|---|
| 2026 | 80 | $+3,486.70 (69%) | $+43.58 | 0.38 | $+2,734.70 | $+4,065.70 | 25/37 |
| 2025H2 | 72 | $+1,633.60 (32%) | $+22.69 | 0.24 | $+773.65 | $+1,915.60 | 17/33 |
| 2025H1 | 38 | $-55.55 (-1%) | $-1.46 | 0.24 | $-761.10 | $+250.45 | 6/23 |

### Replay by premium_band

| Cohort | n | Total | $/trade | WR | drop-best | drop-worst | days +/- |
|---|---|---|---|---|---|---|---|
| >=1.00 | 121 | $+4,216.75 (83%) | $+34.85 | 0.33 | $+3,356.80 | $+4,795.75 | 35/67 |
| 0.50-1.00 | 64 | $+868.05 (17%) | $+13.56 | 0.23 | $+212.05 | $+1,150.05 | 15/40 |
| 0.30-0.50 | 5 | $-20.05 (-0%) | $-4.01 | 0.20 | $-156.60 | $+96.95 | 1/4 |

### Replay by trigger_class_x_regime

| Cohort | n | Total | $/trade | WR | drop-best | drop-worst | days +/- |
|---|---|---|---|---|---|---|---|
| LEVEL_tied|2025H2 | 20 | $+2,884.45 (57%) | $+144.22 | 0.45 | $+2,024.50 | $+3,166.45 | 9/10 |
| LEVEL_tied|2026 | 27 | $+1,638.25 (32%) | $+60.68 | 0.52 | $+886.25 | $+2,217.25 | 13/10 |
| BOTH|2026 | 8 | $+1,140.80 (23%) | $+142.60 | 0.50 | $+608.80 | $+1,496.30 | 3/3 |
| TL_only|2026 | 45 | $+707.65 (14%) | $+15.73 | 0.27 | $+91.65 | $+857.65 | 11/28 |
| BOTH|2025H1 | 1 | $+656.00 (13%) | $+656.00 | 1.00 | $+0.00 | $+0.00 | 1/0 |
| LEVEL_tied|2025H1 | 10 | $+575.35 (11%) | $+57.53 | 0.40 | $-130.20 | $+824.35 | 3/6 |
| TL_only|2025H2 | 52 | $-1,250.85 (-25%) | $-24.05 | 0.15 | $-1,772.85 | $-1,096.65 | 8/30 |
| TL_only|2025H1 | 27 | $-1,286.90 (-25%) | $-47.66 | 0.15 | $-1,832.55 | $-980.90 | 2/18 |

### Replay by trigger_class_x_heldout

| Cohort | n | Total | $/trade | WR | drop-best | drop-worst | days +/- |
|---|---|---|---|---|---|---|---|
| LEVEL_tied|IS | 37 | $+4,623.65 (91%) | $+124.96 | 0.49 | $+3,763.70 | $+4,905.65 | 17/18 |
| BOTH|IS | 3 | $+960.40 (19%) | $+320.13 | 0.67 | $+304.40 | $+1,145.40 | 2/0 |
| BOTH|HELDOUT | 6 | $+836.40 (17%) | $+139.40 | 0.50 | $+304.40 | $+1,191.90 | 2/3 |
| LEVEL_tied|HELDOUT | 20 | $+474.40 (9%) | $+23.72 | 0.45 | $-277.60 | $+1,053.40 | 8/8 |
| TL_only|HELDOUT | 29 | $+68.45 (1%) | $+2.36 | 0.21 | $-435.80 | $+212.45 | 6/20 |
| TL_only|IS | 95 | $-1,898.55 (-37%) | $-19.98 | 0.19 | $-2,514.55 | $-1,592.55 | 15/56 |

### Replay by tier_x_side

| Cohort | n | Total | $/trade | WR | drop-best | drop-worst | days +/- |
|---|---|---|---|---|---|---|---|
| SUPER|C | 21 | $+3,325.85 (66%) | $+158.37 | 0.52 | $+2,465.90 | $+3,607.85 | 11/9 |
| ELITE|P | 11 | $+2,758.20 (54%) | $+250.75 | 0.73 | $+2,052.65 | $+3,226.20 | 7/3 |
| SUPER|P | 16 | $+1,801.25 (36%) | $+112.58 | 0.50 | $+1,145.25 | $+2,380.25 | 7/6 |
| LEVEL|C | 18 | $-990.45 (-20%) | $-55.03 | 0.28 | $-1,448.80 | $-666.45 | 5/12 |
| TRENDLINE|P | 124 | $-1,830.10 (-36%) | $-14.76 | 0.19 | $-2,446.10 | $-1,524.10 | 21/76 |

## Live fills -- independent check (journal/trades.csv)

Rows: 201 csv rows -> 195 valid (6 malformed/unparseable excluded, $+584.00 of parseable P&L among them, disclosed). Live window 2026-04-29..2026-07-27, ALL accounts (core safe/bold + fleet arms). Total across valid rows: **$-1,322.00**.

Trigger-class join: 70/195 live fills matched a core ENTER verdict (same date+side within 5.0min); unjoined mostly pre-2026-06-25 (before core-decisions.jsonl existed) + extra-setup fills (side-channel, no core verdict). 'unjoined' rows stay labeled, never guessed.

### Live by account_group

| Cohort | n | Total | $/trade | WR | drop-best | drop-worst | days +/- |
|---|---|---|---|---|---|---|---|
| core_safe | 36 | $+1,246.00 | $+34.61 | 0.28 | $-254.00 | $+2,016.00 | 5/8 |
| core_bold | 5 | $-469.00 | $-93.80 | 0.60 | $-563.00 | $-114.00 | 1/2 |
| other | 20 | $-599.00 | $-29.95 | 0.20 | $-677.00 | $-362.00 | 1/4 |
| fleet_safe | 60 | $-643.00 | $-10.72 | 0.07 | $-807.00 | $-548.00 | 1/9 |
| fleet_risky | 74 | $-857.00 | $-11.58 | 0.08 | $-1,205.00 | $-705.00 | 2/10 |

### Live by attribution

| Cohort | n | Total | $/trade | WR | drop-best | drop-worst | days +/- |
|---|---|---|---|---|---|---|---|
| (blank) | 29 | $+948.00 | $+32.69 | 0.28 | $-552.00 | $+1,718.00 | 5/8 |
| j_called | 1 | $+89.00 | $+89.00 | 1.00 | $+0.00 | $+0.00 | 1/0 |
| engine | 165 | $-2,359.00 | $-14.30 | 0.11 | $-2,707.00 | $-2,004.00 | 2/14 |

### Live by setup_family

| Cohort | n | Total | $/trade | WR | drop-best | drop-worst | days +/- |
|---|---|---|---|---|---|---|---|
| ribbon_ride | 159 | $-80.00 | $-0.50 | 0.13 | $-1,580.00 | $+690.00 | 7/16 |
| extra_setup | 16 | $-250.00 | $-15.62 | 0.19 | $-306.00 | $-184.00 | 1/4 |
| other/manual | 20 | $-992.00 | $-49.60 | 0.20 | $-1,081.00 | $-692.00 | 1/5 |

### Live by setup

| Cohort | n | Total | $/trade | WR | drop-best | drop-worst | days +/- |
|---|---|---|---|---|---|---|---|
| TRENDLINE_BREAK_RETEST | 1 | $+89.00 | $+89.00 | 1.00 | $+0.00 | $+0.00 | 1/0 |
| BULLISH_RECLAIM_RIDE_THE_RIBBON | 101 | $+24.00 | $+0.24 | 0.04 | $-1,476.00 | $+99.00 | 2/10 |
| bollinger_squeeze | 5 | $+21.00 | $+4.20 | 0.40 | $-35.00 | $+57.00 | 1/2 |
| vwap_reclaim_failed_break | 1 | $+18.00 | $+18.00 | 1.00 | $+0.00 | $+0.00 | 1/0 |
| BEARISH_REJECTION_RIDE_THE_RIBBON | 58 | $-104.00 | $-1.79 | 0.28 | $-834.00 | $+666.00 | 5/8 |
| UNCATEGORIZED_PROBE_MANUAL | 1 | $-120.00 | $-120.00 | 0.00 | $+0.00 | $+0.00 | 0/1 |
| vwap_continuation | 5 | $-136.00 | $-27.20 | 0.00 | $-126.00 | $-91.00 | 0/2 |
| vix_regime_dayside | 5 | $-153.00 | $-30.60 | 0.00 | $-147.00 | $-87.00 | 0/2 |
| UNCATEGORIZED_PROBE | 1 | $-260.00 | $-260.00 | 0.00 | $+0.00 | $+0.00 | 0/1 |
| UNCATEGORIZED_HOLD_TO_EXPIRY | 1 | $-300.00 | $-300.00 | 0.00 | $+0.00 | $+0.00 | 0/1 |
| UNKNOWN | 16 | $-401.00 | $-25.06 | 0.19 | $-410.00 | $-327.00 | 0/2 |

### Live by tier

| Cohort | n | Total | $/trade | WR | drop-best | drop-worst | days +/- |
|---|---|---|---|---|---|---|---|
| CORRECT | 6 | $+2,350.00 | $+391.67 | 0.83 | $+850.00 | $+3,120.00 | 5/1 |
| BASE | 23 | $+510.00 | $+22.17 | 0.26 | $+162.00 | $+662.00 | 2/2 |
| TRENDLINE | 11 | $+279.00 | $+25.36 | 0.55 | $+123.00 | $+441.00 | 1/2 |
| AUTO | 1 | $-24.00 | $-24.00 | 0.00 | $+0.00 | $+0.00 | 0/1 |
| LEVEL | 1 | $-305.00 | $-305.00 | 0.00 | $+0.00 | $+0.00 | 0/1 |
| SUPER | 1 | $-355.00 | $-355.00 | 0.00 | $+0.00 | $+0.00 | 0/1 |
| WRONG | 4 | $-725.00 | $-181.25 | 0.00 | $-680.00 | $-425.00 | 0/3 |
| (blank) | 34 | $-903.00 | $-26.56 | 0.18 | $-959.00 | $-666.00 | 1/7 |
| ELITE | 114 | $-2,149.00 | $-18.85 | 0.04 | $-2,158.00 | $-2,047.00 | 0/10 |

### Live by side

| Cohort | n | Total | $/trade | WR | drop-best | drop-worst | days +/- |
|---|---|---|---|---|---|---|---|
| C | 119 | $-480.00 | $-4.03 | 0.04 | $-1,980.00 | $-360.00 | 3/12 |
| P | 76 | $-842.00 | $-11.08 | 0.29 | $-1,572.00 | $-72.00 | 6/11 |

### Live by entry_hour

| Cohort | n | Total | $/trade | WR | drop-best | drop-worst | days +/- |
|---|---|---|---|---|---|---|---|
| 10 | 27 | $+497.00 | $+18.41 | 0.15 | $-233.00 | $+572.00 | 3/7 |
| 11 | 24 | $+128.00 | $+5.33 | 0.25 | $-220.00 | $+433.00 | 1/5 |
| 13 | 41 | $-1.00 | $-0.02 | 0.32 | $-471.00 | $+299.00 | 2/7 |
| 15 | 7 | $-84.00 | $-12.00 | 0.00 | $-79.00 | $-66.00 | 0/1 |
| 09 | 30 | $-506.00 | $-16.87 | 0.03 | $-2,006.00 | $+264.00 | 1/8 |
| 14 | 44 | $-609.00 | $-13.84 | 0.05 | $-665.00 | $-372.00 | 1/7 |
| 12 | 22 | $-747.00 | $-33.95 | 0.05 | $-836.00 | $-392.00 | 1/7 |

### Live by vix_band

| Cohort | n | Total | $/trade | WR | drop-best | drop-worst | days +/- |
|---|---|---|---|---|---|---|---|
| unknown | 3 | $+24.00 | $+8.00 | 0.33 | $-54.00 | $+60.00 | 1/1 |
| mid | 192 | $-1,346.00 | $-7.01 | 0.14 | $-2,846.00 | $-576.00 | 6/20 |

### Live by day_type

| Cohort | n | Total | $/trade | WR | drop-best | drop-worst | days +/- |
|---|---|---|---|---|---|---|---|
| trend | 10 | $+894.00 | $+89.40 | 0.10 | $-606.00 | $+1,194.00 | 1/3 |
| range | 78 | $-121.00 | $-1.55 | 0.22 | $-851.00 | $+649.00 | 3/4 |
| chop | 98 | $-1,040.00 | $-10.61 | 0.08 | $-1,510.00 | $-780.00 | 2/11 |
| unknown | 9 | $-1,055.00 | $-117.22 | 0.11 | $-1,133.00 | $-700.00 | 1/2 |

### Live by trigger_class_joined

| Cohort | n | Total | $/trade | WR | drop-best | drop-worst | days +/- |
|---|---|---|---|---|---|---|---|
| TL_only | 35 | $+565.00 | $+16.14 | 0.31 | $+217.00 | $+727.00 | 2/4 |
| unjoined | 125 | $-331.00 | $-2.65 | 0.10 | $-1,831.00 | $+439.00 | 6/17 |
| BOTH | 8 | $-507.00 | $-63.38 | 0.25 | $-563.00 | $-152.00 | 1/1 |
| LEVEL_tied | 27 | $-1,049.00 | $-38.85 | 0.07 | $-1,058.00 | $-744.00 | 0/5 |

### Live by trigger_class_x_setup_family

| Cohort | n | Total | $/trade | WR | drop-best | drop-worst | days +/- |
|---|---|---|---|---|---|---|---|
| unjoined|ribbon_ride | 94 | $+842.00 | $+8.96 | 0.07 | $-658.00 | $+1,612.00 | 5/11 |
| TL_only|ribbon_ride | 33 | $+700.00 | $+21.21 | 0.33 | $+352.00 | $+862.00 | 2/4 |
| BOTH|extra_setup | 2 | $+105.00 | $+52.50 | 1.00 | $+49.00 | $+56.00 | 1/0 |
| LEVEL_tied|other/manual | 1 | $-39.00 | $-39.00 | 0.00 | $+0.00 | $+0.00 | 0/1 |
| TL_only|other/manual | 2 | $-135.00 | $-67.50 | 0.00 | $-69.00 | $-66.00 | 0/1 |
| unjoined|extra_setup | 14 | $-355.00 | $-25.36 | 0.07 | $-373.00 | $-289.00 | 0/4 |
| BOTH|ribbon_ride | 6 | $-612.00 | $-102.00 | 0.00 | $-612.00 | $-257.00 | 0/1 |
| unjoined|other/manual | 17 | $-818.00 | $-48.12 | 0.24 | $-907.00 | $-518.00 | 1/5 |
| LEVEL_tied|ribbon_ride | 26 | $-1,010.00 | $-38.85 | 0.08 | $-1,019.00 | $-705.00 | 0/5 |

### Live ribbon_ride, engine-attributed only (n=149) -- replay's scope

### Live ribbon_ride/engine by trigger_class_joined

| Cohort | n | Total | $/trade | WR | drop-best | drop-worst | days +/- |
|---|---|---|---|---|---|---|---|
| TL_only | 33 | $+700.00 | $+21.21 | 0.33 | $+352.00 | $+862.00 | 2/4 |
| BOTH | 6 | $-612.00 | $-102.00 | 0.00 | $-612.00 | $-257.00 | 0/1 |
| LEVEL_tied | 24 | $-758.00 | $-31.58 | 0.08 | $-767.00 | $-453.00 | 0/4 |
| unjoined | 86 | $-1,439.00 | $-16.73 | 0.02 | $-1,446.00 | $-1,364.00 | 0/8 |

### Live ribbon_ride/engine by tier

| Cohort | n | Total | $/trade | WR | drop-best | drop-worst | days +/- |
|---|---|---|---|---|---|---|---|
| BASE | 23 | $+510.00 | $+22.17 | 0.26 | $+162.00 | $+662.00 | 2/2 |
| TRENDLINE | 10 | $+190.00 | $+19.00 | 0.50 | $+34.00 | $+352.00 | 1/2 |
| LEVEL | 1 | $-305.00 | $-305.00 | 0.00 | $+0.00 | $+0.00 | 0/1 |
| SUPER | 1 | $-355.00 | $-355.00 | 0.00 | $+0.00 | $+0.00 | 0/1 |
| ELITE | 114 | $-2,149.00 | $-18.85 | 0.04 | $-2,158.00 | $-2,047.00 | 0/10 |

### Live ribbon_ride/engine by side

| Cohort | n | Total | $/trade | WR | drop-best | drop-worst | days +/- |
|---|---|---|---|---|---|---|---|
| P | 52 | $-624.00 | $-12.00 | 0.25 | $-972.00 | $-269.00 | 2/6 |
| C | 97 | $-1,485.00 | $-15.31 | 0.02 | $-1,492.00 | $-1,410.00 | 0/8 |


---

## PRE-REGISTERED GATE-ADD A/B: min_triggers_bear 1 -> 2 (2026-07-27)

Tool: `backtest/tools/min_triggers_bear2_gate_ab_2026_07_28.py`; full result: `analysis/deep-research/min-triggers-bear2-ab-2026-07-28.json`. Prereg written to disk before the variant ran; contamination disclosed there (descriptive full-window slices, including held-out dates, were seen first -- and already predicted gate 4's direction).

**VERDICT: SHIP_CANDIDATE**

| Gate | Number | Pass |
|---|---|---|
| baseline anchor (must reproduce stored scorecard) | n=190 total=$+5,064.75 vs stored n=190 $+5,064.75 | True |
| 1 positive aggregate | delta $+2,568.05 ($+5,064.75 -> $+7,632.80) | True |
| 2 day-majority | 76 improved / 21 worsened of 97 changed days | True |
| 3 survives drop-best | $+2,147.45 after dropping best day (+$420.60) | True |
| 4 held-out positive | $+652.00 over 96 held-out days | True |

Trade diff: 120 removed (sum $-2,347.15), 4 added (sum $+184.90) -- added trades are replacement entries the baseline's open position had suppressed.

### Post-verification (too-good artifact hunt) -- delta closes exactly

- **Baseline anchor:** rerun reproduced the stored scorecard EXACTLY (n=190, $+5,064.75).
- **Delta accounting, to the cent:** removed 120 singleton bear trades ($-2,347.15) + 4
  replacement trades ($+184.90) + one leg-2 sizing knock-on ($+36.00: baseline's 12:40
  stop-out made the 14:00 tl+flip a leg-2, qty 5 -> 3 without it; verified by 1-day rerun)
  = $+2,568.05.
- **Gate 4 reconciles exactly:** 27 removed held-out singletons = $-652.00 -> delta +$652.00.
  The naive prediction (-$68) failed because descriptive TL_only|HELDOUT included two 2-trigger
  trendline+ribbon_flip WINNERS (+$382.40, +$338.05) that the knob KEEPS.
- **Variant profile:** n=74, WR 0.473 (was 0.295), $+103.15/trade (was $+26.66), maxDD
  $-1,880.85 (was $-2,233.40), fires 16.5% of days (was 36.4%), $/calendar-day $+19.72,
  median trading day $+3.00.

### The honest tension -- why this does NOT auto-ratify

Delta by regime: **2025H1 +$1,217.90, 2025H2 +$1,493.35, 2026 -$143.20.** All of the
improvement is 2025. Early-2026 singletons made +$752.60, held-out (2026-02-25 on) singletons
lost $-652.00, and the most recent LIVE month's joined trendline-only fills are POSITIVE
(+$565, n=35). The pre-registered 4-gate bar is met, but OP-11's sub_window_stable condition
is NOT -- stage as a recommendation, do not flip `filter_10_min_triggers_bear` on tonight's
evidence alone. Plausible reconciliation worth testing next: the 2026-07-27 levels fix
(7b4aa3f4) changes which fires are level-tied at all -- a better level feed may upgrade some
of today's trendline-only fires into level-tied entries, which is where ALL the money is.
