# EXIT-ARM-THRESHOLD A/B scorecard -- ITERATION 2 -- 2026-07-28

**VERDICT: ARM NOTHING** -- G4 (runner-cohort hard veto) FAILS UNIFORMLY across all three cells (delta: F1=$-6,700.90, F2=$-4,888.50, F3=$-3,897.55) -- this alone is sufficient to ARM NOTHING per the non-negotiable G4 veto, regardless of G1-G3/G6/G7. The runner-cohort axis IS coherent ('monotonic_improving_with_higher_arm_pct', values {'F1_arm0.20': -6700.9, 'F2_arm0.30': -4888.5, 'F3_arm0.40': -3897.55}) -- damage shrinks monotonically as the arm threshold rises from 0.20 to 0.40 -- but never turns positive within the tested range: a higher threshold only DAMPENS the mechanism's harm to the profit engine, it does not eliminate it. G7 note: the AGGREGATE axis is non-monotonic ('non_monotonic_spike_at_F2_NOISE', values {'F1_arm0.20': -43.2, 'F2_arm0.30': 1807.1, 'F3_arm0.40': 1324.55}) -- any lone positive cell on that axis is NOISE per the pre-reg's own dose-response criterion and must not be read as favoring that cell.

Pre-reg: `analysis/recommendations/prereg-exit-armpct-2026-07-28.json`. Generated 2026-07-28T17:34:14.127236. Runtime 3.7s.

Prior iteration: `analysis/recommendations/exit-armscope-tp1-ab-2026-07-28.md` (commit `c53922a9`) -- ARM_NOTHING -- G4 runner-cohort veto: -$7,758.85 at arm_pct=0.05

## Population

- Source (entries UNCHANGED, exit-only test, SAME population as iteration 1): `analysis/recommendations/engine-fullhist-replay-2026-07-23.json`
- N trades: 190 (excluded no-OPRA=0, no-SPY-day=0)
- CONTROL reconciliation vs source replay: 0 mismatches (must be 0 for this scorecard to be trusted)

## Per-cell G1-G7 verdict table

| Gate | F1 (arm=0.20) | F2 (arm=0.30) | F3 (arm=0.40) |
|---|---|---|---|
| G1 positive aggregate | $-43.20 FAIL | $+1,807.10 PASS | $+1,324.55 PASS |
| G2 majority changed + | 41/27 PASS | 36/23 PASS | 26/18 PASS |
| G3 survives drop-best1 | $-569.70 FAIL | $+1,280.60 PASS | $+798.05 PASS |
| G4 runner cohort (n=35) | $-6,700.90 FAIL | $-4,888.50 FAIL | $-3,897.55 FAIL |
| G5 look-ahead guard | PASS (real) | PASS (real) | PASS (real) |
| G6 today's trade | $+486.25 PASS | $+486.25 PASS | $+486.25 PASS |
| CLEARS G1-G6 | no | no | no |
| **G7 dose-response (GLOBAL)** | colspan: shape=`monotonic_improving_with_higher_arm_pct` (COHERENT) | | |

## G7 dose-response detail (the axis this iteration exists to test)

Runner-cohort delta by threshold (deciding axis): F1(0.20)=$-6,700.90, F2(0.30)=$-4,888.50, F3(0.40)=$-3,897.55 -> shape = **monotonic_improving_with_higher_arm_pct** (COHERENT)

Aggregate delta by threshold (cross-check): F1(0.20)=$-43.20, F2(0.30)=$+1,807.10, F3(0.40)=$+1,324.55 -> shape = **non_monotonic_spike_at_F2_NOISE** (INCOHERENT)

Axes agree: False.

## Runner-cohort effect (G4 detail, the book's profit engine -- the deciding number)

Anchor check: n=35 (expected 35, match=True); control_pnl_sum=$+15,774.05 (expected $+15,774.05, match=True)

| Cell | Arm pct | Cohort P&L | Delta vs CONTROL | N worse | N better | N unchanged | G4 |
|---|---|---|---|---|---|---|---|
| F1 | 20% | $+9,073.15 | $-6,700.90 | 21 | 0 | 14 | FAIL |
| F2 | 30% | $+10,885.55 | $-4,888.50 | 18 | 0 | 17 | FAIL |
| F3 | 40% | $+11,876.50 | $-3,897.55 | 14 | 0 | 21 | FAIL |

## Today's 2026-07-28 Bold trade under each cell (G6, signal-level)

Entry 1.38 x5 SPY260728C00741000, level_reclaim @741.0. signal-level reconstruction from automation/state/core-decisions.jsonl exit_pass ticks (real live IEX-derived best/worst premium the engine observed each minute) -- no same-day OPRA cache exists; NOT a walk_exit_manager bar replay, disclosed as such (SAME loader/replayer as iteration 1: ab1.load_today_bold_ticks / ab1.replay_today_trade). N real ticks used: 138.

| Cell | Exit P&L | Exit reason | vs CONTROL |
|---|---|---|---|
| CONTROL | $-305.00 | structure_stop @ 741.0 | -- |
| F1 | $+181.25 | profit_lock_floor @ 1.74 | $+486.25 |
| F2 | $+181.25 | profit_lock_floor @ 1.74 | $+486.25 |
| F3 | $+181.25 | profit_lock_floor @ 1.74 | $+486.25 |

## Changed-trade tables (top 15 by |delta| per cell)

### F1 (arm=20%) -- top 15 of 68 changed trades

| Date | Symbol | Tier | CONTROL | F1 | Delta | Control exit | F1 exit |
|---|---|---|---|---|---|---|---|
| 2025-08-22 | SPY250822C00639000 | SUPER | $+859.95 | $+51.75 | $-808.20 | runner_stop @ 6.35 | profit_lock_floor @ 2.42 |
| 2026-01-29 | SPY260129P00690000 | ELITE | $+656.85 | $+49.05 | $-607.80 | runner_stop @ 4.6 | profit_lock_floor @ 2.13 |
| 2026-06-11 | SPY260611C00734000 | SUPER | $+752.00 | $+175.80 | $-576.20 | time_stop_15:50 (runner) | profit_lock_floor @ 2.69 |
| 2025-01-29 | SPY250129P00602000 | TRENDLINE | $-306.00 | $+220.50 | $+526.50 | time_stop_15:50 | profit_lock_floor @ 2.98 |
| 2025-08-12 | SPY250812C00638000 | SUPER | $+572.00 | $+45.90 | $-526.10 | time_stop_15:50 (runner) | profit_lock_floor @ 1.68 |
| 2025-02-21 | SPY250221P00603000 | ELITE | $+616.00 | $+116.20 | $-499.80 | time_stop_15:50 (runner) | profit_lock_floor @ 1.47 |
| 2026-01-06 | SPY260106C00690000 | SUPER | $-252.00 | $+205.10 | $+457.10 | structure_stop @ 689.43 | profit_lock_floor @ 1.0 |
| 2026-03-05 | SPY260305P00682000 | TRENDLINE | $-106.20 | $+333.45 | $+439.65 | premium_stop @ 1.42 | profit_lock_floor @ 2.88 |
| 2025-11-04 | SPY251104P00678000 | TRENDLINE | $+418.20 | $+21.80 | $-396.40 | runner_stop @ 2.09 | profit_lock_floor @ 1.16 |
| 2025-09-25 | SPY250925P00659000 | TRENDLINE | $+522.00 | $+127.00 | $-395.00 | runner_stop @ 2.12 | profit_lock_floor @ 1.22 |
| 2025-12-11 | SPY251211C00686000 | SUPER | $+486.20 | $+102.00 | $-384.20 | runner_stop @ 1.92 | profit_lock_floor @ 1.22 |
| 2026-05-18 | SPY260518P00741000 | TRENDLINE | $+504.25 | $+121.80 | $-382.45 | runner_stop @ 3.27 | profit_lock_floor @ 2.18 |
| 2026-05-26 | SPY260526C00751000 | LEVEL | $-236.00 | $+119.40 | $+355.40 | structure_stop @ 749.9 | profit_lock_floor @ 1.54 |
| 2026-01-27 | SPY260127C00694000 | SUPER | $+442.00 | $+93.20 | $-348.80 | runner_stop @ 2.21 | profit_lock_floor @ 1.51 |
| 2025-08-20 | SPY250820P00636000 | TRENDLINE | $-111.60 | $+229.95 | $+341.55 | premium_stop @ 1.49 | profit_lock_floor @ 2.63 |

### F2 (arm=30%) -- top 15 of 59 changed trades

| Date | Symbol | Tier | CONTROL | F2 | Delta | Control exit | F2 exit |
|---|---|---|---|---|---|---|---|
| 2026-06-11 | SPY260611C00734000 | SUPER | $+752.00 | $+175.80 | $-576.20 | time_stop_15:50 (runner) | profit_lock_floor @ 2.69 |
| 2025-01-29 | SPY250129P00602000 | TRENDLINE | $-306.00 | $+220.50 | $+526.50 | time_stop_15:50 | profit_lock_floor @ 2.98 |
| 2025-02-21 | SPY250221P00603000 | ELITE | $+616.00 | $+116.20 | $-499.80 | time_stop_15:50 (runner) | profit_lock_floor @ 1.47 |
| 2026-01-06 | SPY260106C00690000 | SUPER | $-252.00 | $+205.10 | $+457.10 | structure_stop @ 689.43 | profit_lock_floor @ 1.0 |
| 2026-03-05 | SPY260305P00682000 | TRENDLINE | $-106.20 | $+333.45 | $+439.65 | premium_stop @ 1.42 | profit_lock_floor @ 2.88 |
| 2025-09-25 | SPY250925P00659000 | TRENDLINE | $+522.00 | $+127.00 | $-395.00 | runner_stop @ 2.12 | profit_lock_floor @ 1.22 |
| 2025-12-11 | SPY251211C00686000 | SUPER | $+486.20 | $+102.00 | $-384.20 | runner_stop @ 1.92 | profit_lock_floor @ 1.22 |
| 2026-05-18 | SPY260518P00741000 | TRENDLINE | $+504.25 | $+121.80 | $-382.45 | runner_stop @ 3.27 | profit_lock_floor @ 2.18 |
| 2025-03-20 | SPY250320P00566000 | TRENDLINE | $-100.80 | $+261.00 | $+361.80 | premium_stop @ 1.01 | profit_lock_floor @ 1.91 |
| 2026-05-26 | SPY260526C00751000 | LEVEL | $-236.00 | $+119.40 | $+355.40 | structure_stop @ 749.9 | profit_lock_floor @ 1.54 |
| 2026-01-27 | SPY260127C00694000 | SUPER | $+442.00 | $+93.20 | $-348.80 | runner_stop @ 2.21 | profit_lock_floor @ 1.51 |
| 2025-08-20 | SPY250820P00636000 | TRENDLINE | $-111.60 | $+229.95 | $+341.55 | premium_stop @ 1.49 | profit_lock_floor @ 2.63 |
| 2026-06-25 | SPY260625P00733000 | SUPER | $-246.00 | $+95.25 | $+341.25 | structure_stop @ 733.4773412770263 | profit_lock_floor @ 1.66 |
| 2026-06-08 | SPY260608P00742000 | SUPER | $+439.90 | $+110.85 | $-329.05 | runner_stop @ 3.01 | profit_lock_floor @ 1.76 |
| 2026-02-04 | SPY260204P00690000 | TRENDLINE | $+6.00 | $+323.10 | $+317.10 | ribbon_flip_back | profit_lock_floor @ 3.25 |

### F3 (arm=40%) -- top 15 of 44 changed trades

| Date | Symbol | Tier | CONTROL | F3 | Delta | Control exit | F3 exit |
|---|---|---|---|---|---|---|---|
| 2026-06-11 | SPY260611C00734000 | SUPER | $+752.00 | $+175.80 | $-576.20 | time_stop_15:50 (runner) | profit_lock_floor @ 2.69 |
| 2025-01-29 | SPY250129P00602000 | TRENDLINE | $-306.00 | $+220.50 | $+526.50 | time_stop_15:50 | profit_lock_floor @ 2.98 |
| 2025-02-21 | SPY250221P00603000 | ELITE | $+616.00 | $+116.20 | $-499.80 | time_stop_15:50 (runner) | profit_lock_floor @ 1.47 |
| 2026-01-06 | SPY260106C00690000 | SUPER | $-252.00 | $+205.10 | $+457.10 | structure_stop @ 689.43 | profit_lock_floor @ 1.0 |
| 2026-03-05 | SPY260305P00682000 | TRENDLINE | $-106.20 | $+333.45 | $+439.65 | premium_stop @ 1.42 | profit_lock_floor @ 2.88 |
| 2025-09-25 | SPY250925P00659000 | TRENDLINE | $+522.00 | $+127.00 | $-395.00 | runner_stop @ 2.12 | profit_lock_floor @ 1.22 |
| 2025-12-11 | SPY251211C00686000 | SUPER | $+486.20 | $+102.00 | $-384.20 | runner_stop @ 1.92 | profit_lock_floor @ 1.22 |
| 2026-05-18 | SPY260518P00741000 | TRENDLINE | $+504.25 | $+121.80 | $-382.45 | runner_stop @ 3.27 | profit_lock_floor @ 2.18 |
| 2025-03-20 | SPY250320P00566000 | TRENDLINE | $-100.80 | $+261.00 | $+361.80 | premium_stop @ 1.01 | profit_lock_floor @ 1.91 |
| 2026-05-26 | SPY260526C00751000 | LEVEL | $-236.00 | $+119.40 | $+355.40 | structure_stop @ 749.9 | profit_lock_floor @ 1.54 |
| 2025-08-20 | SPY250820P00636000 | TRENDLINE | $-111.60 | $+229.95 | $+341.55 | premium_stop @ 1.49 | profit_lock_floor @ 2.63 |
| 2026-06-25 | SPY260625P00733000 | SUPER | $-246.00 | $+95.25 | $+341.25 | structure_stop @ 733.4773412770263 | profit_lock_floor @ 1.66 |
| 2026-06-08 | SPY260608P00742000 | SUPER | $+439.90 | $+110.85 | $-329.05 | runner_stop @ 3.01 | profit_lock_floor @ 1.76 |
| 2026-02-04 | SPY260204P00690000 | TRENDLINE | $+6.00 | $+323.10 | $+317.10 | ribbon_flip_back | profit_lock_floor @ 3.25 |
| 2026-05-18 | SPY260518P00737000 | ELITE | $+446.45 | $+132.00 | $-314.45 | runner_stop @ 2.86 | profit_lock_floor @ 2.04 |

## Arming recommendation

- Decision: **ARM_NOTHING**
- Reason: G4 (runner-cohort hard veto) FAILS UNIFORMLY across all three cells (delta: F1=$-6,700.90, F2=$-4,888.50, F3=$-3,897.55) -- this alone is sufficient to ARM NOTHING per the non-negotiable G4 veto, regardless of G1-G3/G6/G7. The runner-cohort axis IS coherent ('monotonic_improving_with_higher_arm_pct', values {'F1_arm0.20': -6700.9, 'F2_arm0.30': -4888.5, 'F3_arm0.40': -3897.55}) -- damage shrinks monotonically as the arm threshold rises from 0.20 to 0.40 -- but never turns positive within the tested range: a higher threshold only DAMPENS the mechanism's harm to the profit engine, it does not eliminate it. G7 note: the AGGREGATE axis is non-monotonic ('non_monotonic_spike_at_F2_NOISE', values {'F1_arm0.20': -43.2, 'F2_arm0.30': 1807.1, 'F3_arm0.40': 1324.55}) -- any lone positive cell on that axis is NOISE per the pre-reg's own dose-response criterion and must not be read as favoring that cell.

## Honest caveats

- G6 (today's trade) is reconstructed from real live tick data (core-decisions.jsonl), NOT an OPRA bar replay -- no same-day cache exists for 2026-07-28. Signal-level, disclosed, SAME loader as iteration 1. ribbon_flip_back held False throughout (not logged per-tick) -- immaterial, the real exit was structure_stop.
- The 190-trade population is Safe-account (core_safe) RIDE_THE_RIBBON entries only, same scope as iteration 1. Today's motivating trade was Bold -- the exit SHAPE is shared across accounts so the mechanism finding transfers, but the aggregate dollar figures are a Safe-account-only estimate of effect size.
- G4's 'no regression' bar is cohort-AGGREGATE, not per-trade -- see the N worse/N better/N unchanged columns for the per-trade distribution within a cell.
- G7 is evaluated on the runner-cohort delta axis as the deciding number (per the task brief); the aggregate-delta axis is reported as a cross-check, and any disagreement between the two axes is called out explicitly above rather than silently resolved.
- Multiplicity: this is exit-shape cell #189-191 tested this week on this book (iteration 1's pre-reg counted ~188 cumulative before this run). The prior on any single exit cell shipping remains LOW; G4 and G7 exist precisely because of that prior.
- kill_criteria_post_arm (per the frozen pre-reg): forward 10 sessions or n>=8 fills; if realized expectancy is worse than the counterfactual control behavior, revert.

---
_Source: `backtest/tools/exit_armpct_ab_2026_07_28.py` (extends `backtest/tools/exit_armscope_ab_2026_07_28.py`, iteration 1). Full trade-level JSON: `analysis/recommendations/exit-armpct-ab-2026-07-28.json`._
