# BE-FLOOR-PRETP1 A/B scorecard -- ITERATION 3 -- 2026-07-29

**VERDICT: ARM NOTHING** -- G4 (runner-cohort hard veto) FAILS UNIFORMLY across all three cells (delta: B1=$-5,965.05, B2=$-7,805.05, B3=$-3,208.05) -- this alone is sufficient to ARM NOTHING per the non-negotiable G4 veto, regardless of G1-G3/G6/G5. The runner-cohort axis IS coherent ('monotonic_improving_with_higher_arm_pct', values {'B2_arm0.20': -7805.05, 'B1_arm0.30': -5965.05, 'B3_arm0.50': -3208.05}).

Pre-reg: `analysis/recommendations/prereg-be-floor-2026-07-29.json`. Generated 2026-07-29T08:02:27.114638. Runtime 5.4s.

Prior iterations (trailing-mode arm axis, both ARM_NOTHING):
- `analysis/recommendations/exit-armscope-tp1-ab-2026-07-28.md` -- ARM_NOTHING -- G4 runner-cohort veto: -$7,758.85 at arm_pct=0.05 (trailing mode)
- `analysis/recommendations/exit-armpct-ab-2026-07-28.md` -- ARM_NOTHING -- G4 fails uniformly 0.20/0.30/0.40 (trailing mode); damage shrinks monotonically but never turns positive

## Population

- Source (entries UNCHANGED, exit-only test, SAME population as iterations 1-2): `analysis/recommendations/engine-fullhist-replay-2026-07-23.json`
- N trades: 190 (excluded no-OPRA=0, no-SPY-day=0)
- CONTROL reconciliation vs source replay: 0 mismatches (must be 0 for this scorecard to be trusted)

## Per-cell G1-G6 verdict table

| Gate | B1 (arm=0.30) | B2 (arm=0.20) | B3 (arm=0.50) |
|---|---|---|---|
| G1 positive aggregate | $-3,420.45 FAIL | $-4,594.45 FAIL | $-2,897.85 FAIL |
| G2 majority changed + | 39/33 PASS | 43/34 PASS | 20/30 FAIL |
| G3 survives drop-best1 | $-3,726.45 FAIL | $-4,900.45 FAIL | $-3,203.85 FAIL |
| G4 runner cohort (n=35) | $-5,965.05 FAIL | $-7,805.05 FAIL | $-3,208.05 FAIL |
| G6 today's trade | $+305.00 PASS | $+305.00 PASS | $+305.00 PASS |
| CLEARS G1-G4,G6 | no | no | no |
| **G5 dose-response (GLOBAL)** | colspan: shape=`monotonic_improving_with_higher_arm_pct` (COHERENT) | | |

## G5 dose-response detail (ascending arm_pct: B2 0.20 < B1 0.30 < B3 0.50)

Runner-cohort delta by threshold (deciding axis): B2(0.20)=$-7,805.05, B1(0.30)=$-5,965.05, B3(0.50)=$-3,208.05 -> shape = **monotonic_improving_with_higher_arm_pct** (COHERENT)

Aggregate delta by threshold (cross-check): B2(0.20)=$-4,594.45, B1(0.30)=$-3,420.45, B3(0.50)=$-2,897.85 -> shape = **monotonic_improving_with_higher_arm_pct** (COHERENT)

Axes agree: True.

## Runner-cohort effect (G4 detail, the book's profit engine -- the deciding number)

Anchor check: n=35 (expected 35, match=True); control_pnl_sum=$+15,774.05 (expected $+15,774.05, match=True)

| Cell | Arm pct | Cohort P&L | Delta vs CONTROL | N worse | N better | N unchanged | G4 |
|---|---|---|---|---|---|---|---|
| B1 | 30% | $+9,809.00 | $-5,965.05 | 29 | 6 | 0 | FAIL |
| B2 | 20% | $+7,969.00 | $-7,805.05 | 30 | 5 | 0 | FAIL |
| B3 | 50% | $+12,566.00 | $-3,208.05 | 27 | 8 | 0 | FAIL |

### G4 mechanism breakdown of DEGRADED runner-cohort trades

Per the pre-reg's structural_note: a degraded runner trade can come from (a) a genuine pre-TP1 round-trip back to entry (the hypothesis's predicted, rare mechanism) or (b) reaching TP1 normally but then losing the post-TP1 15%-trailing protection because profit_lock_mode=fixed never ratchets further once armed. Both are reported separately.

| Cell | pretp1_roundtrip_to_entry | posttp1_lost_trailing_protection | other |
|---|---|---|---|
| B1 | 9 | 20 | 0 |
| B2 | 12 | 18 | 0 |
| B3 | 2 | 25 | 0 |

### Worst-degraded runner-cohort trades (top 10 by |delta|, any cell)

| Cell | Date | Symbol | Mechanism | CONTROL | Cell | Delta |
|---|---|---|---|---|---|---|
| B2 | 2025-08-22 | SPY250822C00639000 | pretp1_roundtrip_to_entry | $+859.95 | $+0.00 | $-859.95 |
| B2 | 2026-01-29 | SPY260129P00690000 | pretp1_roundtrip_to_entry | $+656.85 | $+0.00 | $-656.85 |
| B1 | 2026-05-18 | SPY260518P00741000 | pretp1_roundtrip_to_entry | $+504.25 | $+0.00 | $-504.25 |
| B2 | 2026-05-18 | SPY260518P00741000 | pretp1_roundtrip_to_entry | $+504.25 | $+0.00 | $-504.25 |
| B1 | 2025-12-11 | SPY251211C00686000 | pretp1_roundtrip_to_entry | $+486.20 | $+0.00 | $-486.20 |
| B2 | 2025-12-11 | SPY251211C00686000 | pretp1_roundtrip_to_entry | $+486.20 | $+0.00 | $-486.20 |
| B1 | 2026-07-17 | SPY260717P00745000 | pretp1_roundtrip_to_entry | $+459.00 | $+0.00 | $-459.00 |
| B2 | 2026-07-17 | SPY260717P00745000 | pretp1_roundtrip_to_entry | $+459.00 | $+0.00 | $-459.00 |
| B3 | 2026-07-17 | SPY260717P00745000 | pretp1_roundtrip_to_entry | $+459.00 | $+0.00 | $-459.00 |
| B1 | 2026-05-18 | SPY260518P00737000 | pretp1_roundtrip_to_entry | $+446.45 | $+0.00 | $-446.45 |

## Today's 2026-07-28 Bold trade under each cell (G6, signal-level)

Entry 1.38 x5 SPY260728C00741000, level_reclaim @741.0. signal-level reconstruction from automation/state/core-decisions.jsonl exit_pass ticks (real live IEX-derived best/worst premium the engine observed each minute) -- no same-day OPRA cache exists; NOT a walk_exit_manager bar replay, disclosed as such (SAME loader/replayer as iterations 1-2: ab1.load_today_bold_ticks / ab1.replay_today_trade). N real ticks used: 138.

| Cell | Exit P&L | Exit reason | vs CONTROL |
|---|---|---|---|
| CONTROL | $-305.00 | structure_stop @ 741.0 | -- |
| B1 | $+0.00 | profit_lock_floor @ 1.38 | $+305.00 |
| B2 | $+0.00 | profit_lock_floor @ 1.38 | $+305.00 |
| B3 | $+0.00 | profit_lock_floor @ 1.38 | $+305.00 |

## Changed-trade tables (top 15 by |delta| per cell)

### B1 (arm=30%) -- top 15 of 72 changed trades

| Date | Symbol | Tier | CONTROL | B1 | Delta | Control exit | B1 exit |
|---|---|---|---|---|---|---|---|
| 2026-06-11 | SPY260611C00734000 | SUPER | $+752.00 | $+0.00 | $-752.00 | time_stop_15:50 (runner) | profit_lock_floor @ 2.1 |
| 2026-05-18 | SPY260518P00741000 | TRENDLINE | $+504.25 | $+0.00 | $-504.25 | runner_stop @ 3.27 | profit_lock_floor @ 1.77 |
| 2025-12-11 | SPY251211C00686000 | SUPER | $+486.20 | $+0.00 | $-486.20 | runner_stop @ 1.92 | profit_lock_floor @ 1.02 |
| 2026-07-17 | SPY260717P00745000 | SUPER | $+459.00 | $+0.00 | $-459.00 | runner_stop @ 2.29 | profit_lock_floor @ 1.12 |
| 2026-05-18 | SPY260518P00737000 | ELITE | $+446.45 | $+0.00 | $-446.45 | runner_stop @ 2.86 | profit_lock_floor @ 1.6 |
| 2026-06-08 | SPY260608P00742000 | SUPER | $+439.90 | $+0.00 | $-439.90 | runner_stop @ 3.01 | profit_lock_floor @ 1.39 |
| 2026-04-21 | SPY260421P00707000 | TRENDLINE | $+384.75 | $+0.00 | $-384.75 | runner_stop @ 2.68 | profit_lock_floor @ 1.17 |
| 2026-05-07 | SPY260507P00733000 | TRENDLINE | $+382.40 | $+0.00 | $-382.40 | runner_stop @ 2.41 | profit_lock_floor @ 1.41 |
| 2026-06-24 | SPY260624P00734000 | SUPER | $+309.00 | $+0.00 | $-309.00 | time_stop_15:50 | profit_lock_floor @ 1.64 |
| 2025-01-29 | SPY250129P00602000 | TRENDLINE | $-306.00 | $+0.00 | $+306.00 | time_stop_15:50 | profit_lock_floor @ 2.24 |
| 2026-02-26 | SPY260226P00690000 | SUPER | $+636.05 | $+332.00 | $-304.05 | runner_stop @ 4.7 | runner_stop @ 1.66 |
| 2025-01-10 | SPY250110P00585000 | ELITE | $+705.55 | $+420.00 | $-285.55 | runner_stop @ 4.96 | runner_stop @ 2.1 |
| 2025-07-07 | SPY250707P00622000 | TRENDLINE | $+276.30 | $+0.00 | $-276.30 | runner_stop @ 1.85 | profit_lock_floor @ 0.91 |
| 2025-08-19 | SPY250819P00641000 | TRENDLINE | $+271.20 | $+0.00 | $-271.20 | runner_stop @ 1.8 | profit_lock_floor @ 0.91 |
| 2026-01-29 | SPY260129P00690000 | ELITE | $+656.85 | $+394.00 | $-262.85 | runner_stop @ 4.6 | runner_stop @ 1.97 |

### B2 (arm=20%) -- top 15 of 77 changed trades

| Date | Symbol | Tier | CONTROL | B2 | Delta | Control exit | B2 exit |
|---|---|---|---|---|---|---|---|
| 2025-08-22 | SPY250822C00639000 | SUPER | $+859.95 | $+0.00 | $-859.95 | runner_stop @ 6.35 | profit_lock_floor @ 2.25 |
| 2026-06-11 | SPY260611C00734000 | SUPER | $+752.00 | $+0.00 | $-752.00 | time_stop_15:50 (runner) | profit_lock_floor @ 2.1 |
| 2026-01-29 | SPY260129P00690000 | ELITE | $+656.85 | $+0.00 | $-656.85 | runner_stop @ 4.6 | profit_lock_floor @ 1.97 |
| 2026-05-18 | SPY260518P00741000 | TRENDLINE | $+504.25 | $+0.00 | $-504.25 | runner_stop @ 3.27 | profit_lock_floor @ 1.77 |
| 2025-12-11 | SPY251211C00686000 | SUPER | $+486.20 | $+0.00 | $-486.20 | runner_stop @ 1.92 | profit_lock_floor @ 1.02 |
| 2026-07-17 | SPY260717P00745000 | SUPER | $+459.00 | $+0.00 | $-459.00 | runner_stop @ 2.29 | profit_lock_floor @ 1.12 |
| 2026-05-18 | SPY260518P00737000 | ELITE | $+446.45 | $+0.00 | $-446.45 | runner_stop @ 2.86 | profit_lock_floor @ 1.6 |
| 2026-06-08 | SPY260608P00742000 | SUPER | $+439.90 | $+0.00 | $-439.90 | runner_stop @ 3.01 | profit_lock_floor @ 1.39 |
| 2025-11-04 | SPY251104P00678000 | TRENDLINE | $+418.20 | $+0.00 | $-418.20 | runner_stop @ 2.09 | profit_lock_floor @ 1.11 |
| 2026-04-21 | SPY260421P00707000 | TRENDLINE | $+384.75 | $+0.00 | $-384.75 | runner_stop @ 2.68 | profit_lock_floor @ 1.17 |
| 2026-05-07 | SPY260507P00733000 | TRENDLINE | $+382.40 | $+0.00 | $-382.40 | runner_stop @ 2.41 | profit_lock_floor @ 1.41 |
| 2026-06-24 | SPY260624P00734000 | SUPER | $+309.00 | $+0.00 | $-309.00 | time_stop_15:50 | profit_lock_floor @ 1.64 |
| 2025-01-29 | SPY250129P00602000 | TRENDLINE | $-306.00 | $+0.00 | $+306.00 | time_stop_15:50 | profit_lock_floor @ 2.24 |
| 2026-02-26 | SPY260226P00690000 | SUPER | $+636.05 | $+332.00 | $-304.05 | runner_stop @ 4.7 | runner_stop @ 1.66 |
| 2025-01-10 | SPY250110P00585000 | ELITE | $+705.55 | $+420.00 | $-285.55 | runner_stop @ 4.96 | runner_stop @ 2.1 |

### B3 (arm=50%) -- top 15 of 50 changed trades

| Date | Symbol | Tier | CONTROL | B3 | Delta | Control exit | B3 exit |
|---|---|---|---|---|---|---|---|
| 2026-06-11 | SPY260611C00734000 | SUPER | $+752.00 | $+0.00 | $-752.00 | time_stop_15:50 (runner) | profit_lock_floor @ 2.1 |
| 2026-07-17 | SPY260717P00745000 | SUPER | $+459.00 | $+0.00 | $-459.00 | runner_stop @ 2.29 | profit_lock_floor @ 1.12 |
| 2026-05-18 | SPY260518P00737000 | ELITE | $+446.45 | $+0.00 | $-446.45 | runner_stop @ 2.86 | profit_lock_floor @ 1.6 |
| 2026-06-24 | SPY260624P00734000 | SUPER | $+309.00 | $+0.00 | $-309.00 | time_stop_15:50 | profit_lock_floor @ 1.64 |
| 2025-01-29 | SPY250129P00602000 | TRENDLINE | $-306.00 | $+0.00 | $+306.00 | time_stop_15:50 | profit_lock_floor @ 2.24 |
| 2026-02-26 | SPY260226P00690000 | SUPER | $+636.05 | $+332.00 | $-304.05 | runner_stop @ 4.7 | runner_stop @ 1.66 |
| 2025-01-10 | SPY250110P00585000 | ELITE | $+705.55 | $+420.00 | $-285.55 | runner_stop @ 4.96 | runner_stop @ 2.1 |
| 2026-01-29 | SPY260129P00690000 | ELITE | $+656.85 | $+394.00 | $-262.85 | runner_stop @ 4.6 | runner_stop @ 1.97 |
| 2025-07-21 | SPY250721C00629000 | SUPER | $+418.20 | $+164.00 | $-254.20 | runner_stop @ 2.09 | ribbon_flip_back (runner) |
| 2026-01-06 | SPY260106C00690000 | SUPER | $-252.00 | $+0.00 | $+252.00 | structure_stop @ 689.43 | profit_lock_floor @ 0.71 |
| 2026-05-21 | SPY260521C00742000 | SUPER | $+487.90 | $+240.00 | $-247.90 | runner_stop @ 2.44 | runner_stop @ 1.2 |
| 2025-12-11 | SPY251211C00686000 | SUPER | $+486.20 | $+718.00 | $+231.80 | runner_stop @ 1.92 | time_stop_15:50 (runner) |
| 2025-11-04 | SPY251104P00678000 | TRENDLINE | $+418.20 | $+636.00 | $+217.80 | runner_stop @ 2.09 | time_stop_15:50 (runner) |
| 2025-01-08 | SPY250108P00590000 | TRENDLINE | $+545.65 | $+328.00 | $-217.65 | runner_stop @ 3.82 | runner_stop @ 1.64 |
| 2026-05-18 | SPY260518P00736000 | SUPER | $+514.40 | $+309.00 | $-205.40 | runner_stop @ 2.06 | runner_stop @ 1.03 |

## Arming recommendation

- Decision: **ARM_NOTHING**
- Reason: G4 (runner-cohort hard veto) FAILS UNIFORMLY across all three cells (delta: B1=$-5,965.05, B2=$-7,805.05, B3=$-3,208.05) -- this alone is sufficient to ARM NOTHING per the non-negotiable G4 veto, regardless of G1-G3/G6/G5. The runner-cohort axis IS coherent ('monotonic_improving_with_higher_arm_pct', values {'B2_arm0.20': -7805.05, 'B1_arm0.30': -5965.05, 'B3_arm0.50': -3208.05}).

## Honest caveats

- STRUCTURAL NOTE (disclosed in the pre-reg before any run): switching profit_lock_mode to "fixed" changes THREE keys vs CONTROL, not two -- it removes the post-TP1 15%-trailing protection for any trade that reaches TP1, not just adding a pre-TP1 floor. Iterations 1-2 held profit_lock_mode="trailing" fixed throughout, so their runner-cohort damage came entirely from trades knocked out PRE-TP1; this file's G4 mechanism breakdown above separates that same pre-TP1 mechanism from the NEW post-TP1 mechanism this cell introduces.
- G6 (today's trade) is reconstructed from real live tick data (core-decisions.jsonl), NOT an OPRA bar replay -- no same-day cache exists for 2026-07-28. Signal-level, disclosed, SAME loader as iterations 1-2. ribbon_flip_back held False throughout (not logged per-tick) -- immaterial, the real exit was structure_stop.
- The 190-trade population is Safe-account (core_safe) RIDE_THE_RIBBON entries only, same scope as iterations 1-2. Today's motivating trade was Bold -- the exit SHAPE is shared across accounts so the mechanism finding transfers, but the aggregate dollar figures are a Safe-account-only estimate of effect size.
- G4's 'no regression' bar is cohort-AGGREGATE, not per-trade -- see the N worse/N better/N unchanged columns for the per-trade distribution within a cell, and the mechanism breakdown table for WHY each worse trade degraded.
- G5 is evaluated on the runner-cohort delta axis as the deciding number (per the task brief); the aggregate-delta axis is reported as a cross-check.
- Multiplicity: this is the third arm-axis cell tested on this book this week (iterations 1-2 counted ~191 cumulative before this run). The prior on any single exit cell shipping remains LOW; G4 and G5 exist precisely because of that prior.
- kill_criteria_post_arm (per the frozen pre-reg): forward 10 sessions or n>=8 fills; if realized expectancy is worse than the counterfactual control behavior, revert.

---
_Source: `backtest/tools/be_floor_ab_2026_07_29.py` (extends `backtest/tools/exit_armscope_ab_2026_07_28.py`, iteration 1). Full trade-level JSON: `analysis/recommendations/be-floor-ab-2026-07-29.json`._
