# EXIT-ARMSCOPE-TP1 A/B scorecard -- 2026-07-28

**VERDICT: ARM NOTHING** -- no cell cleared all required gates.

Pre-reg: `analysis/recommendations/prereg-exit-armscope-tp1-2026-07-28.json`. Generated 2026-07-28T17:21:55.526294. Runtime 4.6s.

## Population

- Source (entries UNCHANGED, exit-only test): `analysis/recommendations/engine-fullhist-replay-2026-07-23.json`
- N trades: 190 (excluded no-OPRA=0, no-SPY-day=0)
- CONTROL reconciliation vs source replay: 0 mismatches (must be 0 for this scorecard to be trusted)

## Per-cell G1-G6 verdict table

| Gate | E1 (arm_scope=full) | E2 (tp1=0.5) | E3 (both) |
|---|---|---|---|
| G1 positive aggregate | $-482.10 FAIL | $-2,491.55 FAIL | $-1,892.15 FAIL |
| G2 majority changed + | 54/30 PASS | 15/41 FAIL | 54/44 PASS |
| G3 survives drop-best1 | $-1,008.60 FAIL | $-3,095.05 FAIL | $-2,495.65 FAIL |
| G4 runner cohort (n=35) | $-7,758.85 FAIL | $-5,615.70 FAIL | $-9,448.40 FAIL |
| G5 look-ahead guard | PASS (real) | PASS (vacuous) | PASS (real) |
| G6 today's trade | $+305.00 PASS | $+603.20 (not gated) | $+305.00 PASS |
| CLEARS ALL REQUIRED | no | no | no |

## Runner-cohort effect (G4 detail, the book's profit engine)

Anchor check: n=35 (expected 35, match=True); control_pnl_sum=$+15,774.05 (expected $+15,774.05, match=True)

| Cell | Cohort P&L | Delta vs CONTROL | N worse | N better | N unchanged | G4 |
|---|---|---|---|---|---|---|
| E1 | $+8,015.20 | $-7,758.85 | 22 | 0 | 13 | FAIL |
| E2 | $+10,158.35 | $-5,615.70 | 35 | 0 | 0 | FAIL |
| E3 | $+6,325.65 | $-9,448.40 | 35 | 0 | 0 | FAIL |

## Today's 2026-07-28 Bold trade under each cell (G6, signal-level)

Entry 1.38 x5 SPY260728C00741000, level_reclaim @741.0. signal-level reconstruction from automation/state/core-decisions.jsonl exit_pass ticks (real live IEX-derived best/worst premium the engine observed each minute) -- no same-day OPRA cache exists; NOT a walk_exit_manager bar replay, disclosed as such. N real ticks used: 138.

| Cell | Exit P&L | Exit reason | vs CONTROL |
|---|---|---|---|
| CONTROL | $-305.00 | structure_stop @ 741.0 | -- |
| E1 | $+0.00 | profit_lock_floor @ 1.38 | $+305.00 |
| E2 | $+298.20 | runner_stop @ 1.84 | $+603.20 |
| E3 | $+0.00 | profit_lock_floor @ 1.38 | $+305.00 |

## Changed-trade tables (top 15 by |delta| per cell)

### E1 -- top 15 of 84 changed trades

| Date | Symbol | Tier | CONTROL | E1 | Delta | Control exit | E1 exit |
|---|---|---|---|---|---|---|---|
| 2025-08-22 | SPY250822C00639000 | SUPER | $+859.95 | $+51.75 | $-808.20 | runner_stop @ 6.35 | profit_lock_floor @ 2.42 |
| 2026-01-29 | SPY260129P00690000 | ELITE | $+656.85 | $+49.05 | $-607.80 | runner_stop @ 4.6 | profit_lock_floor @ 2.13 |
| 2026-06-11 | SPY260611C00734000 | SUPER | $+752.00 | $+175.80 | $-576.20 | time_stop_15:50 (runner) | profit_lock_floor @ 2.69 |
| 2025-01-08 | SPY250108P00590000 | TRENDLINE | $+545.65 | $+0.00 | $-545.65 | runner_stop @ 3.82 | profit_lock_floor @ 1.64 |
| 2025-01-29 | SPY250129P00602000 | TRENDLINE | $-306.00 | $+220.50 | $+526.50 | time_stop_15:50 | profit_lock_floor @ 2.98 |
| 2025-08-12 | SPY250812C00638000 | SUPER | $+572.00 | $+45.90 | $-526.10 | time_stop_15:50 (runner) | profit_lock_floor @ 1.68 |
| 2025-02-21 | SPY250221P00603000 | ELITE | $+616.00 | $+116.20 | $-499.80 | time_stop_15:50 (runner) | profit_lock_floor @ 1.47 |
| 2026-01-06 | SPY260106C00690000 | SUPER | $-252.00 | $+205.10 | $+457.10 | structure_stop @ 689.43 | profit_lock_floor @ 1.0 |
| 2026-05-18 | SPY260518P00737000 | ELITE | $+446.45 | $+0.00 | $-446.45 | runner_stop @ 2.86 | profit_lock_floor @ 1.6 |
| 2026-03-05 | SPY260305P00682000 | TRENDLINE | $-106.20 | $+333.45 | $+439.65 | premium_stop @ 1.42 | profit_lock_floor @ 2.88 |
| 2026-07-06 | SPY260706C00749000 | SUPER | $+421.60 | $+0.00 | $-421.60 | runner_stop @ 2.11 | profit_lock_floor @ 1.17 |
| 2025-11-04 | SPY251104P00678000 | TRENDLINE | $+418.20 | $+21.80 | $-396.40 | runner_stop @ 2.09 | profit_lock_floor @ 1.16 |
| 2025-09-25 | SPY250925P00659000 | TRENDLINE | $+522.00 | $+127.00 | $-395.00 | runner_stop @ 2.12 | profit_lock_floor @ 1.22 |
| 2025-12-11 | SPY251211C00686000 | SUPER | $+486.20 | $+102.00 | $-384.20 | runner_stop @ 1.92 | profit_lock_floor @ 1.22 |
| 2026-05-18 | SPY260518P00741000 | TRENDLINE | $+504.25 | $+121.80 | $-382.45 | runner_stop @ 3.27 | profit_lock_floor @ 2.18 |

### E2 -- top 15 of 56 changed trades

| Date | Symbol | Tier | CONTROL | E2 | Delta | Control exit | E2 exit |
|---|---|---|---|---|---|---|---|
| 2025-01-29 | SPY250129P00602000 | TRENDLINE | $-306.00 | $+297.50 | $+603.50 | time_stop_15:50 | runner_stop @ 2.98 |
| 2026-06-11 | SPY260611C00734000 | SUPER | $+752.00 | $+268.60 | $-483.40 | time_stop_15:50 (runner) | runner_stop @ 2.69 |
| 2026-01-06 | SPY260106C00690000 | SUPER | $-252.00 | $+229.90 | $+481.90 | structure_stop @ 689.43 | runner_stop @ 1.0 |
| 2026-03-05 | SPY260305P00682000 | TRENDLINE | $-106.20 | $+288.15 | $+394.35 | premium_stop @ 1.42 | runner_stop @ 2.88 |
| 2025-02-21 | SPY250221P00603000 | ELITE | $+616.00 | $+227.10 | $-388.90 | time_stop_15:50 (runner) | runner_stop @ 1.73 |
| 2025-08-20 | SPY250820P00636000 | TRENDLINE | $-111.60 | $+262.65 | $+374.25 | premium_stop @ 1.49 | runner_stop @ 2.63 |
| 2025-03-20 | SPY250320P00566000 | TRENDLINE | $-100.80 | $+256.50 | $+357.30 | premium_stop @ 1.01 | runner_stop @ 1.91 |
| 2025-09-26 | SPY250926C00661000 | LEVEL | $-119.00 | $+203.40 | $+322.40 | time_stop_15:50 | runner_stop @ 0.92 |
| 2026-02-04 | SPY260204P00690000 | TRENDLINE | $+6.00 | $+324.70 | $+318.70 | ribbon_flip_back | runner_stop @ 3.25 |
| 2025-08-20 | SPY250820P00636000 | TRENDLINE | $-101.00 | $+214.70 | $+315.70 | premium_stop @ 0.81 | runner_stop @ 1.33 |
| 2025-01-13 | SPY250113P00578000 | TRENDLINE | $-91.20 | $+218.45 | $+309.65 | premium_stop @ 1.22 | runner_stop @ 2.18 |
| 2025-07-17 | SPY250717C00625000 | SUPER | $+541.00 | $+244.60 | $-296.40 | runner_stop @ 2.21 | runner_stop @ 1.47 |
| 2025-09-25 | SPY250925P00659000 | TRENDLINE | $+522.00 | $+252.40 | $-269.60 | runner_stop @ 2.12 | runner_stop @ 1.5 |
| 2026-01-02 | SPY260102P00682000 | TRENDLINE | $+502.60 | $+238.00 | $-264.60 | runner_stop @ 1.68 | runner_stop @ 1.19 |
| 2026-07-20 | SPY260720P00744000 | SUPER | $+489.40 | $+241.50 | $-247.90 | runner_stop @ 1.97 | runner_stop @ 1.45 |

### E3 -- top 15 of 98 changed trades

| Date | Symbol | Tier | CONTROL | E3 | Delta | Control exit | E3 exit |
|---|---|---|---|---|---|---|---|
| 2025-08-22 | SPY250822C00639000 | SUPER | $+859.95 | $+51.75 | $-808.20 | runner_stop @ 6.35 | profit_lock_floor @ 2.42 |
| 2026-01-29 | SPY260129P00690000 | ELITE | $+656.85 | $+49.05 | $-607.80 | runner_stop @ 4.6 | profit_lock_floor @ 2.13 |
| 2025-01-29 | SPY250129P00602000 | TRENDLINE | $-306.00 | $+297.50 | $+603.50 | time_stop_15:50 | runner_stop @ 2.98 |
| 2025-01-08 | SPY250108P00590000 | TRENDLINE | $+545.65 | $+0.00 | $-545.65 | runner_stop @ 3.82 | profit_lock_floor @ 1.64 |
| 2025-08-12 | SPY250812C00638000 | SUPER | $+572.00 | $+45.90 | $-526.10 | time_stop_15:50 (runner) | profit_lock_floor @ 1.68 |
| 2025-02-21 | SPY250221P00603000 | ELITE | $+616.00 | $+116.20 | $-499.80 | time_stop_15:50 (runner) | profit_lock_floor @ 1.47 |
| 2026-06-11 | SPY260611C00734000 | SUPER | $+752.00 | $+268.60 | $-483.40 | time_stop_15:50 (runner) | runner_stop @ 2.69 |
| 2026-01-06 | SPY260106C00690000 | SUPER | $-252.00 | $+229.90 | $+481.90 | structure_stop @ 689.43 | runner_stop @ 1.0 |
| 2026-05-18 | SPY260518P00737000 | ELITE | $+446.45 | $+0.00 | $-446.45 | runner_stop @ 2.86 | profit_lock_floor @ 1.6 |
| 2026-07-06 | SPY260706C00749000 | SUPER | $+421.60 | $+0.00 | $-421.60 | runner_stop @ 2.11 | profit_lock_floor @ 1.17 |
| 2025-11-04 | SPY251104P00678000 | TRENDLINE | $+418.20 | $+21.80 | $-396.40 | runner_stop @ 2.09 | profit_lock_floor @ 1.16 |
| 2025-09-25 | SPY250925P00659000 | TRENDLINE | $+522.00 | $+127.00 | $-395.00 | runner_stop @ 2.12 | profit_lock_floor @ 1.22 |
| 2026-03-05 | SPY260305P00682000 | TRENDLINE | $-106.20 | $+288.15 | $+394.35 | premium_stop @ 1.42 | runner_stop @ 2.88 |
| 2025-12-11 | SPY251211C00686000 | SUPER | $+486.20 | $+102.00 | $-384.20 | runner_stop @ 1.92 | profit_lock_floor @ 1.22 |
| 2026-05-18 | SPY260518P00741000 | TRENDLINE | $+504.25 | $+121.80 | $-382.45 | runner_stop @ 3.27 | profit_lock_floor @ 2.18 |

## Arming recommendation

- Decision: **ARM_NOTHING**
- Reason: no cell cleared all required gates

## Honest caveats

- G6 (today's trade) is reconstructed from real live tick data (core-decisions.jsonl), NOT an OPRA bar replay -- no same-day cache exists for 2026-07-28. This is disclosed, signal-level, and uses the exact same em.plan_exit_actions decision core as every other cell, but ribbon_flip_back is held False throughout (not logged per-tick in the source) -- immaterial here since the real exit was structure_stop, not a ribbon flip.
- The 190-trade population is Safe-account (core_safe) entries only, per engine-fullhist-replay-2026-07-23.json's documented scope (RIDE_THE_RIBBON family only; Bold/aggressive and the extra setups are not in this population). Today's motivating trade was Bold -- the exit SHAPE (RIBBON_RIDE) is shared across both accounts, so the mechanism finding transfers, but the 190-trade aggregate numbers are a Safe-account-only estimate of the effect size.
- G4's 'no regression' bar is cohort-AGGREGATE, not per-trade -- see the N worse/N better/N unchanged columns above for the per-trade distribution within a passing or failing cell.
- kill_criteria_post_arm (per the frozen pre-reg): forward 10 sessions or n>=8 fills; if realized expectancy is worse than the counterfactual control behavior, revert.

---
_Source: `backtest/tools/exit_armscope_ab_2026_07_28.py`. Full trade-level JSON: `analysis/recommendations/exit-armscope-tp1-ab-2026-07-28.json`._
