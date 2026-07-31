# LEVEL PERSISTENCE -- did we draw 20 different levels, or validate the same ones?

Generated 2026-07-31T14:47:44.048060. Tool: `backtest/tools/level_persistence_2026_07_31.py` (prereg frozen 2026-07-31 16:43:52 ET in its docstring, BEFORE any run). Machine-readable: `analysis/deep-research/LEVEL-PERSISTENCE-2026-07-31.json`.

## Verdict: **TV_OUTPERFORMS_DESCRIPTIVE_ONLY**

## Part 1 -- v2 snapshot continuity (2026-07-28..07-31; 07-30 snapshot MISSING, disclosed)

| Day | n levels | persisted from prior snapshot | new |
|---|--:|--:|--:|
| 2026-07-28 | 20 | -- | -- |
| 2026-07-29 | 20 | 20 | 0 |
| 2026-07-31 | 20 | 17 | 3 |

Full 07-28 -> 07-29 -> 07-31 chains: **17** of 20 today-levels.

## Part 2 -- does persistence predict? (66 level-tied real-OPRA replay trades; OHLC-derived levels, provenance gap disclosed)

### PRIMARY CELL (frozen): tol $0.4, lookback 5 trading days

| Cohort | n | Total | $/trade | WR | drop-best | drop-worst |
|---|--:|--:|--:|--:|--:|--:|
| FRESH | 7 | $+177.75 | $+25.39 | 0.29 | $-305.80 | $+426.75 |
| PERSISTENT | 5 | $+861.85 | $+172.37 | 0.60 | $+205.00 | $+1,097.85 |
| TOUCH_VALIDATED | 54 | $+5,855.25 | $+108.43 | 0.50 | $+4,995.30 | $+6,434.25 |
| UNKNOWN | 0 | -- | -- | -- | -- | -- |

- p (PERSISTENT-or-better vs FRESH) = 0.5810 (BH-sig at q=0.1: False)
- p (TOUCH_VALIDATED vs FRESH) = 0.6346 (BH-sig at q=0.1: False)

### All 9 sensitivity cells (frozen grid, ALL reported)

| Cell | FRESH n/$-tot/$-tr | PERSISTENT n/$-tot/$-tr | TOUCH_VAL n/$-tot/$-tr | p(TV vs F) | BH |
|---|---|---|---|--:|:--:|
| tol0.25_lb1 | 24 / $+1,877 / $+78 | 5 / $+881 / $+176 | 37 / $+4,137 / $+112 | 0.976 | n |
| tol0.25_lb10 | 9 / $-522 / $-58 | 3 / $+464 / $+155 | 54 / $+6,953 / $+129 | 0.336 | n |
| tol0.25_lb5 | 13 / $+92 / $+7 | 4 / $+1,670 / $+417 | 49 / $+5,133 / $+105 | 0.562 | n |
| tol0.4_lb1 | 18 / $+1,989 / $+110 | 9 / $+977 / $+109 | 39 / $+3,929 / $+101 | 0.817 | n |
| tol0.4_lb10 | 5 / $-718 / $-144 | 3 / $-254 / $-85 | 58 / $+7,867 / $+136 | 0.178 | n |
| tol0.4_lb5 | 7 / $+178 / $+25 | 5 / $+862 / $+172 | 54 / $+5,855 / $+108 | 0.635 | n |
| tol0.6_lb1 | 11 / $+1,079 / $+98 | 10 / $+1,599 / $+160 | 45 / $+4,217 / $+94 | 0.942 | n |
| tol0.6_lb10 | 2 / $-99 / $-50 | 0 / -- / -- | 64 / $+6,994 / $+109 | 0.911 | n |
| tol0.6_lb5 | 3 / $+313 / $+104 | 3 / $+289 / $+96 | 60 / $+6,293 / $+105 | 0.796 | n |

<details><summary>Primary-cell per-trade classification (66 rows)</summary>

| Date | Entry | Tier | Side | Level | Cohort | prior-day matches | touches | P&L |
|---|---|---|---|--:|---|--:|--:|--:|
| 2025-01-10 | 10:35 | ELITE | P | 585.195 | TOUCH_VALIDATED | 1 | 3 | $+705.55 |
| 2025-01-10 | 12:05 | ELITE | P | 580.51 | TOUCH_VALIDATED | 5 | 4 | $+12.00 |
| 2025-01-16 | 12:05 | SUPER | C | 593.38 | TOUCH_VALIDATED | 1 | 19 | $-160.00 |
| 2025-01-30 | 10:40 | LEVEL | C | 603.71 | TOUCH_VALIDATED | 1 | 16 | $-159.00 |
| 2025-02-12 | 14:40 | SUPER | C | 603.6 | TOUCH_VALIDATED | 2 | 38 | $-230.00 |
| 2025-02-21 | 14:05 | ELITE | P | 603.6 | TOUCH_VALIDATED | 2 | 4 | $+616.00 |
| 2025-03-03 | 10:35 | LEVEL | C | 596.0 | FRESH | 0 | 0 | $-249.00 |
| 2025-06-05 | 14:05 | ELITE | P | 595.98 | TOUCH_VALIDATED | 2 | 49 | $-230.00 |
| 2025-06-13 | 14:05 | SUPER | P | 600.0 | TOUCH_VALIDATED | 4 | 62 | $+656.00 |
| 2025-06-20 | 13:05 | ELITE | P | 595.52 | TOUCH_VALIDATED | 4 | 5 | $+397.80 |
| 2025-06-26 | 09:45 | LEVEL | C | 609.0 | FRESH | 0 | 0 | $-128.00 |
| 2025-07-09 | 09:45 | LEVEL | C | 623.87 | TOUCH_VALIDATED | 2 | 7 | $-252.00 |
| 2025-07-15 | 09:45 | LEVEL | C | 626.0 | TOUCH_VALIDATED | 4 | 42 | $-54.00 |
| 2025-07-17 | 09:40 | SUPER | C | 624.72 | TOUCH_VALIDATED | 5 | 133 | $+541.00 |
| 2025-07-21 | 09:45 | SUPER | C | 629.305 | TOUCH_VALIDATED | 1 | 6 | $+418.20 |
| 2025-08-08 | 09:40 | LEVEL | C | 634.11 | FRESH | 0 | 0 | $+412.20 |
| 2025-08-11 | 09:40 | SUPER | C | 637.0461014596233 | TOUCH_VALIDATED | 2 | 54 | $-282.00 |
| 2025-08-12 | 09:55 | SUPER | C | 637.26 | TOUCH_VALIDATED | 3 | 81 | $+572.00 |
| 2025-08-22 | 09:40 | SUPER | C | 637.755 | TOUCH_VALIDATED | 3 | 23 | $+859.95 |
| 2025-09-11 | 09:50 | LEVEL | C | 653.87 | TOUCH_VALIDATED | 1 | 20 | $+458.35 |
| 2025-09-23 | 09:55 | SUPER | C | 666.864279493517 | TOUCH_VALIDATED | 1 | 30 | $-35.00 |
| 2025-09-26 | 09:40 | LEVEL | C | 660.72 | TOUCH_VALIDATED | 4 | 56 | $-189.00 |
| 2025-09-26 | 12:25 | LEVEL | C | 660.38 | TOUCH_VALIDATED | 2 | 4 | $-119.00 |
| 2025-10-02 | 10:05 | SUPER | C | 669.0719879985901 | TOUCH_VALIDATED | 1 | 22 | $-164.00 |
| 2025-10-15 | 13:05 | ELITE | P | 663.8275103924964 | FRESH | 0 | 0 | $+483.55 |
| 2025-10-24 | 09:40 | LEVEL | C | 677.0 | FRESH | 0 | 0 | $-69.00 |
| 2025-10-27 | 09:40 | LEVEL | C | 682.72 | FRESH | 0 | 0 | $-30.00 |
| 2025-10-28 | 12:10 | LEVEL | C | 685.97 | PERSISTENT | 1 | 0 | $-84.00 |
| 2025-10-29 | 09:40 | SUPER | C | 688.72 | TOUCH_VALIDATED | 1 | 6 | $+21.00 |
| 2025-11-10 | 13:05 | LEVEL | C | 677.0 | TOUCH_VALIDATED | 3 | 17 | $-90.00 |
| 2025-12-11 | 12:40 | SUPER | C | 685.25 | TOUCH_VALIDATED | 5 | 63 | $+486.20 |
| 2026-01-06 | 10:55 | SUPER | C | 689.43 | TOUCH_VALIDATED | 3 | 7 | $-252.00 |
| 2026-01-26 | 10:45 | LEVEL | C | 692.0 | TOUCH_VALIDATED | 2 | 33 | $+24.00 |
| 2026-01-27 | 10:50 | SUPER | C | 694.2 | TOUCH_VALIDATED | 2 | 16 | $+442.00 |
| 2026-01-29 | 11:05 | ELITE | P | 690.485 | PERSISTENT | 3 | 1 | $+656.85 |
| 2026-02-03 | 13:05 | ELITE | P | 690.545 | TOUCH_VALIDATED | 4 | 53 | $+380.00 |
| 2026-02-26 | 11:05 | SUPER | P | 690.6 | TOUCH_VALIDATED | 1 | 20 | $+636.05 |
| 2026-05-08 | 09:50 | LEVEL | C | 735.45 | TOUCH_VALIDATED | 1 | 16 | $+32.00 |
| 2026-05-18 | 11:05 | ELITE | P | 739.0 | TOUCH_VALIDATED | 4 | 65 | $+446.45 |
| 2026-05-18 | 14:05 | SUPER | P | 737.0 | TOUCH_VALIDATED | 3 | 21 | $+514.40 |
| 2026-05-19 | 14:10 | SUPER | C | 736.6849381647099 | TOUCH_VALIDATED | 5 | 68 | $-280.00 |
| 2026-05-21 | 11:35 | SUPER | P | 738.85 | TOUCH_VALIDATED | 4 | 48 | $-189.00 |
| 2026-05-21 | 13:25 | SUPER | C | 741.3 | TOUCH_VALIDATED | 2 | 2 | $+487.90 |
| 2026-05-26 | 09:45 | LEVEL | C | 749.9 | PERSISTENT | 4 | 0 | $-236.00 |
| 2026-05-28 | 10:15 | SUPER | C | 750.2376720496296 | TOUCH_VALIDATED | 2 | 75 | $+172.00 |
| 2026-06-08 | 13:35 | SUPER | P | 742.0841623480467 | TOUCH_VALIDATED | 1 | 4 | $+439.90 |
| 2026-06-08 | 14:40 | SUPER | P | 742.0841623480467 | TOUCH_VALIDATED | 1 | 4 | $+532.00 |
| 2026-06-09 | 10:50 | SUPER | P | 738.1900024414062 | TOUCH_VALIDATED | 2 | 13 | $-390.00 |
| 2026-06-11 | 13:35 | SUPER | C | 732.5 | TOUCH_VALIDATED | 1 | 15 | $+752.00 |
| 2026-06-15 | 09:40 | LEVEL | C | 753.0 | PERSISTENT | 2 | 0 | $+66.00 |
| 2026-06-17 | 14:05 | SUPER | P | 750.8286009873198 | TOUCH_VALIDATED | 2 | 10 | $-355.50 |
| 2026-06-22 | 11:50 | ELITE | P | 746.1 | FRESH | 0 | 0 | $-242.00 |
| 2026-06-22 | 15:00 | SUPER | P | 743.8599853515625 | TOUCH_VALIDATED | 2 | 7 | $-50.00 |
| 2026-06-24 | 13:20 | SUPER | P | 735.15 | TOUCH_VALIDATED | 2 | 28 | $+309.00 |
| 2026-06-25 | 10:00 | SUPER | P | 730.8400268554688 | TOUCH_VALIDATED | 1 | 5 | $-579.00 |
| 2026-06-25 | 13:35 | SUPER | P | 733.4773412770263 | TOUCH_VALIDATED | 2 | 23 | $-246.00 |
| 2026-06-26 | 09:50 | ELITE | P | 729.7 | TOUCH_VALIDATED | 1 | 2 | $-468.00 |
| 2026-06-26 | 14:55 | SUPER | P | 732.0982057689337 | TOUCH_VALIDATED | 3 | 52 | $-240.00 |
| 2026-06-29 | 09:45 | LEVEL | C | 737.5 | TOUCH_VALIDATED | 1 | 12 | $-324.00 |
| 2026-07-06 | 09:45 | SUPER | C | 747.75 | TOUCH_VALIDATED | 4 | 49 | $+421.60 |
| 2026-07-06 | 14:20 | SUPER | C | 751.3099975585938 | TOUCH_VALIDATED | 1 | 5 | $-132.00 |
| 2026-07-08 | 13:30 | SUPER | C | 745.2977294921875 | TOUCH_VALIDATED | 4 | 20 | $-160.00 |
| 2026-07-15 | 09:55 | SUPER | C | 753.2 | TOUCH_VALIDATED | 2 | 19 | $-153.00 |
| 2026-07-17 | 13:55 | SUPER | P | 745.2 | PERSISTENT | 2 | 0 | $+459.00 |
| 2026-07-20 | 13:40 | SUPER | P | 744.5112751919311 | TOUCH_VALIDATED | 1 | 28 | $-185.00 |
| 2026-07-20 | 14:35 | SUPER | P | 744.1598866941566 | TOUCH_VALIDATED | 1 | 26 | $+489.40 |

</details>

## Part 4 -- J's literal question: today's 20 morning levels

Counts: {'NEW': 3, 'PERSISTED': 11, 'TOUCH_VALIDATED': 6}. PERSISTED matched vs the 07-29 morning snapshot (07-30 snapshot missing, disclosed); touch-validation uses the 07-30 SIP tape.

| Price | Label | Class | matched 07-29 | touches on 07-30 tape | J call |
|--:|---|---|---|--:|---|
| 729.79 | SHELF_728.99_730.59_2026-07-31 | **NEW** | -- | 0 |  |
| 731.22 | PRIOR_CLOSE_2026-06-26 | **PERSISTED** | PRIOR_CLOSE_2026-06-26 | 0 |  |
| 734.52 | PML_2026-06-29 | **TOUCH_VALIDATED** | PML_2026-06-29 | 5 |  |
| 735.1 | SHELF_734.30_735.90_2026-07-31 | **TOUCH_VALIDATED** | PML_2026-06-29, SHELF_735.03_736.63_2026-07-29 | 13 |  |
| 737.85 | SHELF_737.05_738.65_2026-07-31 | **TOUCH_VALIDATED** | MEMORY_SUP_138, SHELF_737.05_738.65_2026-07-29 | 27 | J called 737.68 -- today's exact low (called live) |
| 739.73 | SHELF_738.93_740.53_2026-07-31 | **TOUCH_VALIDATED** | MEMORY_SUP_85, SHELF_738.72_740.32_2026-07-29 | 35 | J called 739.72 -- bounce target (called live) |
| 740.76 | MEMORY_SUP_90 | **TOUCH_VALIDATED** | MEMORY_SUP_94, SHELF_740.39_741.99_2026-07-29 | 14 |  |
| 741.6 | SHELF_740.80_742.40_2026-07-31 | **TOUCH_VALIDATED** | MEMORY_SUP_94, SHELF_740.39_741.99_2026-07-29 | 13 |  |
| 742.79 | INTRADAY_PML_2026-07-31 | **PERSISTED** | SHELF_742.09_743.69_2026-07-29 | 1 | J called 742.97 -- premarket low call |
| 742.9 | MEMORY_RES_80 | **PERSISTED** | SHELF_742.09_743.69_2026-07-29 | 0 | J called 742.97 -- premarket low call |
| 743.25 | SHELF_742.45_744.05_2026-07-31 | **PERSISTED** | SHELF_742.09_743.69_2026-07-29, INTRADAY_PMH_2026-07-29 | 1 | J called 742.97 -- premarket low call |
| 744.13 | MEMORY_RES_85 | **NEW** | -- | 0 |  |
| 744.91 | MEMORY_RES_78 | **PERSISTED** | SHELF_744.18_745.78_2026-07-29 | 0 |  |
| 745.72 | MEMORY_RES_117 | **PERSISTED** | SHELF_744.18_745.78_2026-07-29 | 0 |  |
| 746.55 | INTRADAY_PMH_2026-07-31 | **NEW** | -- | 0 |  |
| 748.09 | SHELF_747.29_748.89_2026-07-31 | **PERSISTED** | SHELF_747.29_748.89_2026-07-29 | 0 |  |
| 750.98 | SHELF_750.18_751.78_2026-07-31 | **PERSISTED** | SHELF_750.18_751.78_2026-07-29 | 0 |  |
| 752.77 | SHELF_751.97_753.57_2026-07-31 | **PERSISTED** | SHELF_751.97_753.57_2026-07-29 | 0 |  |
| 754.71 | SHELF_753.91_755.51_2026-07-31 | **PERSISTED** | SHELF_753.91_755.51_2026-07-29 | 0 |  |
| 756.38 | SHELF_755.58_757.18_2026-07-31 | **PERSISTED** | SHELF_755.58_757.18_2026-07-29 | 0 |  |

## Part 3 -- weight-upgrade SPEC (NOT armed; evidence-thin per the frozen verdict rule)

TV outperformed FRESH directionally in the primary cell ($108 vs $25/trade, WR 0.50 vs 0.29) but is
NOT BH-significant (p=0.63; FRESH n=7 is tiny) -> per the frozen rule this section is a SPEC, not a ship.

- **Where:** the v2 compiler's `weight` field (shelves w5 / intraday w2 / memory unweighted today).
- **Computation (prior trading day SIP 5m RTH bars, per level zone = price +/- zone_width, 0.40 floor):**
  - `touches` = bars whose [low,high] intersects the zone (J's "rode 4 bars")
  - `flips` = sign changes of (close - level) across consecutive closes (J's "flipped on the dump")
  - `bounces` = bar tests zone AND closes >= 1 zone-width away (J's "12:40 bounce-and-rip")
- **Upgrade:** `weight_effective = weight + 1` if touches >= 2, `+1` more if flips >= 1 or bounces >= 1.
  Binary threshold only -- the touch-depth dose-response is FLAT (2-9: $111/tr, 10-29: $105, 30+: $109),
  so no deep-touch bonus.
- **Pre-registered A/B before any arming:** fullhist entry-layer variant (level-tied entries REQUIRE a
  touch-validated trigger level) vs baseline + a fleet-parallel arm pair for forward evidence; standard
  4 gates + sub-window stability; freeze via et_clock before the run. Kill if TV-gating drops level-tied
  n below ~40 without raising $/trade.

## Honest notes / post-hoc robustness (disclosed, NOT prereg)

- **Anchor closes to the cent:** FRESH + PERSISTENT + TV = $+6,894.85 = PNL-ATTRIBUTION-2026-07-28's
  level-tied total (57 LEVEL_tied + 9 BOTH). n = 7+5+54 = 66.
- **The FRESH cohort is tiny (n=7)** -- that is the finding, not just a power problem: among level-tied
  entries, genuinely never-seen levels barely exist. 82% of the level-tied money rides TOUCH-VALIDATED zones.
- **Static vs dynamic (post-hoc):** 18 trades fired on dynamic aVWAP-style trigger levels (>4dp floats);
  as a group they lost $-981.65. TV restricted to STATIC structural levels: **n=37, $+7,320.45,
  $+197.85/trade, WR 0.622**. The persistence edge concentrates in real static structure -- which is all
  the v2 compiler emits anyway.
- **Lookback sensitivity is coherent with the thesis:** at lookback=1 the TV-vs-FRESH contrast vanishes
  (FRESH there still contains 2-5-day-old levels); at lookback 5/10 FRESH turns flat/negative
  (lb10: -$144/trade) while TV holds ~$108-136/trade. Level age matters beyond yesterday.
- **No cell is BH-significant** (18 tests, q=0.10). Everything above is descriptive direction, not proof.
- **Generated_at in this file's header is machine-local time (MT = ET-2);** the prereg freeze stamp
  (2026-07-31 16:43:52 ET) is the authoritative clock reading.

## Provenance / disclosures

- **replay_source**: engine-fullhist-replay-2026-07-23.json
- **replay_levels**: OHLC-derived (lib/levels.py), NOT the live v2 compiler feed
- **bars_fullhist**: spy_5m_2025-01-01_2026-07-22.csv
- **bars_live**: spy_5m_2026-05-19_2026-07-31.csv
- **missing_snapshot_days**: ['2026-07-30']
- **pnl**: real-OPRA-only per-trade dollar_pnl from the replay JSON
