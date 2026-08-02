# PRETP1-BE-FLOOR-ISOLATED A/B scorecard -- ITERATION 4 -- 2026-08-02

**VERDICT: ARM NOTHING** -- G4 (runner-cohort hard veto) FAILS UNIFORMLY across all three cells (delta: P1=$-3,650.45, P2=$-905.45, P3=$-459.00) -- this alone is sufficient to ARM NOTHING per the non-negotiable G4 veto, regardless of G1-G3/G6/G5. The runner-cohort axis IS coherent ('monotonic_improving_with_higher_arm_pct', values {'P1_arm0.30': -3650.45, 'P2_arm0.50': -905.45, 'P3_arm0.70': -459.0}).

Pre-reg: `analysis/recommendations/prereg-pretp1-be-floor-isolated-2026-08-02.json`. Generated 2026-08-02T02:13:26.491159. Runtime 4.4s.

**Knob-isolation check: 0 violations** (should be 0 -- profit_lock_mode stays 'trailing' throughout this iteration, so no runner-cohort trade should ever show mechanism (b) posttp1_lost_trailing_protection; a nonzero count here is a red flag on the knob's isolation, checked before trusting the rest of this scorecard).

Prior iterations (all ARM_NOTHING):
- `analysis/recommendations/exit-armscope-tp1-ab-2026-07-28.md` -- ARM_NOTHING -- G4 runner-cohort veto: -$7,758.85 at arm_pct=0.05 (trailing mode)
- `analysis/recommendations/exit-armpct-ab-2026-07-28.md` -- ARM_NOTHING -- G4 fails uniformly 0.20/0.30/0.40 (trailing mode); damage shrinks monotonically but never turns positive
- `analysis/recommendations/be-floor-ab-2026-07-29.md` -- ARM_NOTHING -- CONFOUNDED: 'fixed' mode silently disabled post-TP1 trailing (25/27 degraded-trade mechanism), not a clean pre-TP1-only test

## Population

- Source (entries UNCHANGED, exit-only test, SAME population as iterations 1-3): `analysis/recommendations/engine-fullhist-replay-2026-07-23.json`
- N trades: 191 (excluded no-OPRA=0, no-SPY-day=0)
- CONTROL reconciliation vs source replay: 0 mismatches (must be 0 for this scorecard to be trusted)

## Per-cell G1-G6 verdict table

| Gate | P1 (arm=0.30) | P2 (arm=0.50) | P3 (arm=0.70) |
|---|---|---|---|
| G1 positive aggregate | $-1,105.85 FAIL | $-595.25 FAIL | $-252.00 FAIL |
| G2 majority changed + | 33/13 PASS | 12/5 PASS | 2/1 PASS |
| G3 survives drop-best1 | $-1,411.85 FAIL | $-901.25 FAIL | $-358.20 FAIL |
| G4 runner cohort (n=35) | $-3,650.45 FAIL | $-905.45 FAIL | $-459.00 FAIL |
| G6 today's trade | $+305.00 PASS | $+305.00 PASS | $+0.00 FAIL |
| CLEARS G1-G4,G6 | no | no | no |
| **G5 dose-response (GLOBAL)** | colspan: shape=`monotonic_improving_with_higher_arm_pct` (COHERENT) | | |

## G5 dose-response detail (ascending arm_pct: P1 0.30 < P2 0.50 < P3 0.70)

Runner-cohort delta by threshold (deciding axis): P1(0.30)=$-3,650.45, P2(0.50)=$-905.45, P3(0.70)=$-459.00 -> shape = **monotonic_improving_with_higher_arm_pct** (COHERENT)

Aggregate delta by threshold (cross-check): P1(0.30)=$-1,105.85, P2(0.50)=$-595.25, P3(0.70)=$-252.00 -> shape = **monotonic_improving_with_higher_arm_pct** (COHERENT)

Axes agree: True.

## Runner-cohort effect (G4 detail, the book's profit engine -- the deciding number)

Anchor check: n=35 (expected 35, match=True); control_pnl_sum=$+15,774.05 (expected $+15,774.05, match=True)

| Cell | Arm pct | Cohort P&L | Delta vs CONTROL | N worse | N better | N unchanged | G4 |
|---|---|---|---|---|---|---|---|
| P1 | 30% | $+12,123.60 | $-3,650.45 | 9 | 0 | 26 | FAIL |
| P2 | 50% | $+14,868.60 | $-905.45 | 2 | 0 | 33 | FAIL |
| P3 | 70% | $+15,315.05 | $-459.00 | 1 | 0 | 34 | FAIL |

### G4 mechanism breakdown of DEGRADED runner-cohort trades

Mechanism (b) posttp1_lost_trailing_protection should be STRUCTURALLY IMPOSSIBLE this iteration (profit_lock_mode stays 'trailing' throughout) -- flagged loudly, not silently averaged in, if it ever appears.

| Cell | pretp1_roundtrip_to_entry | KNOB ISOLATION VIOLATIONS (should be 0) | other |
|---|---|---|---|
| P1 | 9 | 0 | 0 |
| P2 | 2 | 0 | 0 |
| P3 | 1 | 0 | 0 |

### Worst-degraded runner-cohort trades (top 10 by |delta|, any cell)

| Cell | Date | Symbol | Mechanism | CONTROL | Cell | Delta |
|---|---|---|---|---|---|---|
| P1 | 2026-05-18 | SPY260518P00741000 | pretp1_roundtrip_to_entry | $+504.25 | $+0.00 | $-504.25 |
| P1 | 2025-12-11 | SPY251211C00686000 | pretp1_roundtrip_to_entry | $+486.20 | $+0.00 | $-486.20 |
| P1 | 2026-07-17 | SPY260717P00745000 | pretp1_roundtrip_to_entry | $+459.00 | $+0.00 | $-459.00 |
| P2 | 2026-07-17 | SPY260717P00745000 | pretp1_roundtrip_to_entry | $+459.00 | $+0.00 | $-459.00 |
| P3 | 2026-07-17 | SPY260717P00745000 | pretp1_roundtrip_to_entry | $+459.00 | $+0.00 | $-459.00 |
| P1 | 2026-05-18 | SPY260518P00737000 | pretp1_roundtrip_to_entry | $+446.45 | $+0.00 | $-446.45 |
| P2 | 2026-05-18 | SPY260518P00737000 | pretp1_roundtrip_to_entry | $+446.45 | $+0.00 | $-446.45 |
| P1 | 2026-06-08 | SPY260608P00742000 | pretp1_roundtrip_to_entry | $+439.90 | $+0.00 | $-439.90 |
| P1 | 2026-04-21 | SPY260421P00707000 | pretp1_roundtrip_to_entry | $+384.75 | $+0.00 | $-384.75 |
| P1 | 2026-05-07 | SPY260507P00733000 | pretp1_roundtrip_to_entry | $+382.40 | $+0.00 | $-382.40 |

## Today's 2026-07-28 Bold trade under each cell (G6, signal-level)

Entry 1.38 x5 SPY260728C00741000, level_reclaim @741.0. signal-level reconstruction from automation/state/core-decisions.jsonl exit_pass ticks (real live IEX-derived best/worst premium the engine observed each minute) -- no same-day OPRA cache exists; NOT a walk_exit_manager bar replay, disclosed as such (SAME loader/replayer as iterations 1-3: ab1.load_today_bold_ticks / ab1.replay_today_trade). N real ticks used: 138.

| Cell | Exit P&L | Exit reason | vs CONTROL |
|---|---|---|---|
| CONTROL | $-305.00 | structure_stop @ 741.0 | -- |
| P1 | $+0.00 | profit_lock_floor @ 1.38 | $+305.00 |
| P2 | $+0.00 | profit_lock_floor @ 1.38 | $+305.00 |
| P3 | $-305.00 | structure_stop @ 741.0 | $+0.00 |

## Changed-trade tables (top 15 by |delta| per cell)

### P1 (arm=30%) -- top 15 of 46 changed trades

| Date | Symbol | Tier | CONTROL | P1 | Delta | Control exit | P1 exit |
|---|---|---|---|---|---|---|---|
| 2026-06-11 | SPY260611C00734000 | SUPER | $+752.00 | $+0.00 | $-752.00 | time_stop_15:40 (runner) | profit_lock_floor @ 2.1 |
| 2026-05-18 | SPY260518P00741000 | TRENDLINE | $+504.25 | $+0.00 | $-504.25 | runner_stop @ 3.27 | profit_lock_floor @ 1.77 |
| 2025-12-11 | SPY251211C00686000 | SUPER | $+486.20 | $+0.00 | $-486.20 | runner_stop @ 1.92 | profit_lock_floor @ 1.02 |
| 2026-07-17 | SPY260717P00745000 | SUPER | $+459.00 | $+0.00 | $-459.00 | runner_stop @ 2.29 | profit_lock_floor @ 1.12 |
| 2026-05-18 | SPY260518P00737000 | ELITE | $+446.45 | $+0.00 | $-446.45 | runner_stop @ 2.86 | profit_lock_floor @ 1.6 |
| 2026-06-08 | SPY260608P00742000 | SUPER | $+439.90 | $+0.00 | $-439.90 | runner_stop @ 3.01 | profit_lock_floor @ 1.39 |
| 2026-04-21 | SPY260421P00707000 | TRENDLINE | $+384.75 | $+0.00 | $-384.75 | runner_stop @ 2.68 | profit_lock_floor @ 1.17 |
| 2026-05-07 | SPY260507P00733000 | TRENDLINE | $+382.40 | $+0.00 | $-382.40 | runner_stop @ 2.41 | profit_lock_floor @ 1.41 |
| 2026-06-24 | SPY260624P00734000 | SUPER | $+309.00 | $+0.00 | $-309.00 | time_stop_15:40 | profit_lock_floor @ 1.64 |
| 2025-01-29 | SPY250129P00602000 | TRENDLINE | $-306.00 | $+0.00 | $+306.00 | time_stop_15:40 | profit_lock_floor @ 2.24 |
| 2025-07-07 | SPY250707P00622000 | TRENDLINE | $+276.30 | $+0.00 | $-276.30 | runner_stop @ 1.85 | profit_lock_floor @ 0.91 |
| 2025-08-19 | SPY250819P00641000 | TRENDLINE | $+271.20 | $+0.00 | $-271.20 | runner_stop @ 1.8 | profit_lock_floor @ 0.91 |
| 2026-01-06 | SPY260106C00690000 | SUPER | $-252.00 | $+0.00 | $+252.00 | structure_stop @ 689.43 | profit_lock_floor @ 0.71 |
| 2026-06-25 | SPY260625P00733000 | SUPER | $-246.00 | $+0.00 | $+246.00 | structure_stop @ 733.4773412770263 | profit_lock_floor @ 1.34 |
| 2026-05-26 | SPY260526C00751000 | LEVEL | $-236.00 | $+0.00 | $+236.00 | structure_stop @ 749.9 | profit_lock_floor @ 1.24 |

### P2 (arm=50%) -- top 15 of 17 changed trades

| Date | Symbol | Tier | CONTROL | P2 | Delta | Control exit | P2 exit |
|---|---|---|---|---|---|---|---|
| 2026-06-11 | SPY260611C00734000 | SUPER | $+752.00 | $+0.00 | $-752.00 | time_stop_15:40 (runner) | profit_lock_floor @ 2.1 |
| 2026-07-17 | SPY260717P00745000 | SUPER | $+459.00 | $+0.00 | $-459.00 | runner_stop @ 2.29 | profit_lock_floor @ 1.12 |
| 2026-05-18 | SPY260518P00737000 | ELITE | $+446.45 | $+0.00 | $-446.45 | runner_stop @ 2.86 | profit_lock_floor @ 1.6 |
| 2026-06-24 | SPY260624P00734000 | SUPER | $+309.00 | $+0.00 | $-309.00 | time_stop_15:40 | profit_lock_floor @ 1.64 |
| 2025-01-29 | SPY250129P00602000 | TRENDLINE | $-306.00 | $+0.00 | $+306.00 | time_stop_15:40 | profit_lock_floor @ 2.24 |
| 2026-01-06 | SPY260106C00690000 | SUPER | $-252.00 | $+0.00 | $+252.00 | structure_stop @ 689.43 | profit_lock_floor @ 0.71 |
| 2025-09-26 | SPY250926C00661000 | LEVEL | $-119.00 | $+0.00 | $+119.00 | time_stop_15:40 | profit_lock_floor @ 0.72 |
| 2025-08-20 | SPY250820P00636000 | TRENDLINE | $-111.60 | $+0.00 | $+111.60 | premium_stop @ 1.49 | profit_lock_floor @ 1.86 |
| 2026-03-05 | SPY260305P00682000 | TRENDLINE | $-106.20 | $+0.00 | $+106.20 | premium_stop @ 1.42 | profit_lock_floor @ 1.77 |
| 2025-08-20 | SPY250820P00636000 | TRENDLINE | $-101.00 | $+0.00 | $+101.00 | premium_stop @ 0.81 | profit_lock_floor @ 1.01 |
| 2025-03-20 | SPY250320P00566000 | TRENDLINE | $-100.80 | $+0.00 | $+100.80 | premium_stop @ 1.01 | profit_lock_floor @ 1.26 |
| 2025-01-13 | SPY250113P00578000 | TRENDLINE | $-91.20 | $+0.00 | $+91.20 | premium_stop @ 1.22 | profit_lock_floor @ 1.52 |
| 2025-02-25 | SPY250225P00595000 | TRENDLINE | $-70.20 | $+0.00 | $+70.20 | premium_stop @ 0.94 | profit_lock_floor @ 1.17 |
| 2026-05-14 | SPY260514P00748000 | TRENDLINE | $-58.20 | $+0.00 | $+58.20 | premium_stop @ 0.78 | profit_lock_floor @ 0.97 |
| 2025-07-15 | SPY250715P00624000 | TRENDLINE | $-46.20 | $+0.00 | $+46.20 | premium_stop @ 0.62 | profit_lock_floor @ 0.77 |

### P3 (arm=70%) -- top 3 of 3 changed trades

| Date | Symbol | Tier | CONTROL | P3 | Delta | Control exit | P3 exit |
|---|---|---|---|---|---|---|---|
| 2026-07-17 | SPY260717P00745000 | SUPER | $+459.00 | $+0.00 | $-459.00 | runner_stop @ 2.29 | profit_lock_floor @ 1.12 |
| 2026-03-05 | SPY260305P00682000 | TRENDLINE | $-106.20 | $+0.00 | $+106.20 | premium_stop @ 1.42 | profit_lock_floor @ 1.77 |
| 2025-03-20 | SPY250320P00566000 | TRENDLINE | $-100.80 | $+0.00 | $+100.80 | premium_stop @ 1.01 | profit_lock_floor @ 1.26 |

## Arming recommendation

- Decision: **ARM_NOTHING**
- Reason: G4 (runner-cohort hard veto) FAILS UNIFORMLY across all three cells (delta: P1=$-3,650.45, P2=$-905.45, P3=$-459.00) -- this alone is sufficient to ARM NOTHING per the non-negotiable G4 veto, regardless of G1-G3/G6/G5. The runner-cohort axis IS coherent ('monotonic_improving_with_higher_arm_pct', values {'P1_arm0.30': -3650.45, 'P2_arm0.50': -905.45, 'P3_arm0.70': -459.0}).

## Honest caveats

- This is a STRUCTURALLY CLEANER test than iteration 3 -- pre_tp1_be_floor_arm_pct is a NEW, independent knob (never sets profit_lock_armed, never touches profit_lock_mode) -- but the mechanism-isolation claim is itself verified empirically above (knob isolation violations, should be 0), not just assumed from the code read.
- G6 (today's trade) is reconstructed from real live tick data (core-decisions.jsonl), NOT an OPRA bar replay -- no same-day cache exists for 2026-07-28. Signal-level, disclosed, SAME loader as iterations 1-3. ribbon_flip_back held False throughout (not logged per-tick) -- immaterial, the real exit was structure_stop.
- The 190-trade population is Safe-account (core_safe) RIDE_THE_RIBBON entries only, same scope as iterations 1-3. Today's motivating trade was Bold -- the exit SHAPE is shared across accounts so the mechanism finding transfers, but the aggregate dollar figures are a Safe-account-only estimate of effect size.
- G4's 'no regression' bar is cohort-AGGREGATE, not per-trade -- see the N worse/N better/N unchanged columns for the per-trade distribution within a cell, and the mechanism breakdown table for WHY each worse trade degraded.
- G5 is evaluated on the runner-cohort delta axis as the deciding number (per the task brief); the aggregate-delta axis is reported as a cross-check.
- Multiplicity: this is the FOURTH arm-axis cell tested on this book this week (iterations 1-3 counted a large cumulative cell count before this run). If this iteration also fails, the profit-lock-mechanism axis is exhausted per the pre-reg's own arming_rule -- the queue item's next candidate is THETA-NOT-GIVEBACK (hold-time/underlying-stall class), not another profit-lock variant.
- kill_criteria_post_arm (per the frozen pre-reg): forward 10 sessions or n>=8 fills; if realized expectancy is worse than the counterfactual control behavior, revert.

---
_Source: `backtest/tools/pretp1_be_floor_isolated_ab_2026_08_02.py` (extends `backtest/tools/exit_armscope_ab_2026_07_28.py`, iteration 1; gate pattern reused from `backtest/tools/be_floor_ab_2026_07_29.py`, iteration 3). Full trade-level JSON: `analysis/recommendations/pretp1-be-floor-isolated-ab-2026-08-02.json`._
