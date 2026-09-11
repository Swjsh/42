# P5-TOPCELL-REAL-FILLS-CONFIRM — mass-grind P5 survivors on real OPRA fills via exit_manager

Generated: 2026-07-11T19:27:03.624754. Source: `backtest/tools/p5_topcell_real_fills_confirm.py`.

## FINDING 1 — tp1_premium_pct / tp1_qty_fraction are DEAD AXES within the P5-survivor set

Only **6 distinct** (strike,stop,lock,trail,time_stop) shapes exist among all 106 P5 survivors — the literal top-5-by-ranking are all the SAME shape (verified byte-identical n/expectancy/wr/max_dd across 4 different tp1 targets in the raw funnel data). Mechanism: `simulate_trade_real` arms the trailing profit-lock on the FIRST profitable tick pre-TP1 when `profit_lock_threshold_pct` stays at its default 0 (mass_grind never sets it) — TP1 is resolved by the lock or the stop before any tested TP1 % is reached, so tp1_premium_pct/tp1_qty_fraction never bind. See module docstring FINDING 1 for the full mechanism trace.

## VERDICT TABLE (LAYER A — exit_manager, LOCAL bars, same entries)

**Read the LIVE column as the ratification number.** The 'sim full-scope' column is EXPLORATORY only — FINDING 2 (disclosures) found it does NOT reconcile with the recorded backtest number on a bar-level trace; do not treat it as a validated sim-parity replica.

| shape | recorded (sim, funnel) | **LIVE post_tp1 (ratification)** | sim full-scope (exploratory, unreconciled) |
|---|---|---|---|
| OTM-1_stop-8_trailing0.15 | n=399 exp=$34.32 | n=381 exp=$25.62 | n=381 exp=$-60.67 |
| OTM-2_stop-8_trailing0.15 | n=398 exp=$32.37 | n=375 exp=$7.11 | n=375 exp=$-38.3 |
| OTM-1_stop-12_trailing0.15 | n=399 exp=$27.84 | n=381 exp=$18.98 | n=381 exp=$-91.01 |
| OTM-1_stop-8_fixed | n=434 exp=$26.27 | n=415 exp=$34.06 | n=415 exp=$-3.49 |
| OTM-1_stop-8_trailing0.22 | n=417 exp=$26.75 | n=399 exp=$12.0 | n=399 exp=$-47.25 |
| ATM_stop-8_trailing0.15 | n=401 exp=$27.41 | n=380 exp=$30.22 | n=380 exp=$-90.42 |

## LAYER B (real fleet-fills anchor, LIVE post_tp1 scope, PUT-only)

| shape | n anchor positions | candidate total | control (actual_ribbon_ride) total | no_regression |
|---|---|---|---|:--:|
| OTM-1_stop-8_trailing0.15 | 18/18 | $68.33 | $23.7 | True |
| OTM-2_stop-8_trailing0.15 | 18/18 | $115.38 | $23.7 | True |
| OTM-1_stop-12_trailing0.15 | 18/18 | $-33.83 | $23.7 | False |
| OTM-1_stop-8_fixed | 18/18 | $424.38 | $23.7 | True |
| OTM-1_stop-8_trailing0.22 | 18/18 | $129.92 | $23.7 | True |
| ATM_stop-8_trailing0.15 | 18/18 | $239.98 | $23.7 | True |

## Per-shape detail

### `OTM-1_stop-8_trailing0.15` (rank 1/106 in the P5 set)

- **Verdict: PASS** — LAYER A LIVE positive ($25.62/tr) AND LAYER B anchor no-regression vs control -- survives the exit_manager ratification check; vs recorded funnel exp $34.32/tr (sim, NOT the ratification authority per standing doctrine): LIVE post_tp1 is $-8.7/tr different -- the scope-mismatch's real economic impact on this population (see FINDING 2 for why the 'sim full-scope' column could not be used as a clean isolated-variable comparison instead)
- combo: strike=OTM-1(so=1) stop=-0.08 lock=trailing trail=0.15 ts=10 | recorded tp/tq used for repro: 0.3/0.5
- LAYER 0 (run_cell repro): n=399, expectancy=$34.32, edge_capture=$13695.32 — recorded funnel: n=399, expectancy=$34.32, edge_capture=$1816.22 (parity: True)
- LAYER A LIVE (post_tp1, ratification authority): n=381 (of 399, 18 no local bars), expectancy=$25.62/tr, total=$9762.5, WR=0.236
  - IS(2025) exp=$10.31 (n=246) | OOS(2026) exp=$53.53 (n=135)
  - top-3-day concentration: 0.334
- LAYER A sim-full-scope (EXPLORATORY, unreconciled -- FINDING 2): expectancy=$-60.67/tr, total=$-23116.8
- LAYER B anchor: 18 real fleet PUT positions replayed — candidate $68.33 vs control(actual_ribbon_ride) $23.7 -> no_regression=True

### `OTM-2_stop-8_trailing0.15` (rank 2/106 in the P5 set)

- **Verdict: PASS** — LAYER A LIVE positive ($7.11/tr) AND LAYER B anchor no-regression vs control -- survives the exit_manager ratification check; vs recorded funnel exp $32.37/tr (sim, NOT the ratification authority per standing doctrine): LIVE post_tp1 is $-25.26/tr different -- the scope-mismatch's real economic impact on this population (see FINDING 2 for why the 'sim full-scope' column could not be used as a clean isolated-variable comparison instead)
- combo: strike=OTM-2(so=2) stop=-0.08 lock=trailing trail=0.15 ts=10 | recorded tp/tq used for repro: 0.3/0.8
- LAYER 0 (run_cell repro): n=398, expectancy=$32.37, edge_capture=$12882.54 — recorded funnel: n=398, expectancy=$32.37, edge_capture=$2187.34 (parity: True)
- LAYER A LIVE (post_tp1, ratification authority): n=375 (of 398, 23 no local bars), expectancy=$7.11/tr, total=$2667.7, WR=0.189
  - IS(2025) exp=$-1.09 (n=245) | OOS(2026) exp=$22.57 (n=130)
  - top-3-day concentration: 0.643
- LAYER A sim-full-scope (EXPLORATORY, unreconciled -- FINDING 2): expectancy=$-38.3/tr, total=$-14364.3
- LAYER B anchor: 18 real fleet PUT positions replayed — candidate $115.38 vs control(actual_ribbon_ride) $23.7 -> no_regression=True

### `OTM-1_stop-12_trailing0.15` (rank 3/106 in the P5 set)

- **Verdict: MIXED** — LAYER A LIVE positive ($18.98/tr) but LAYER B real-fleet anchor shows REGRESSION vs control ($-33.83 < $23.7); vs recorded funnel exp $27.84/tr (sim, NOT the ratification authority per standing doctrine): LIVE post_tp1 is $-8.86/tr different -- the scope-mismatch's real economic impact on this population (see FINDING 2 for why the 'sim full-scope' column could not be used as a clean isolated-variable comparison instead)
- combo: strike=OTM-1(so=1) stop=-0.12 lock=trailing trail=0.15 ts=10 | recorded tp/tq used for repro: 0.3/0.5
- LAYER 0 (run_cell repro): n=399, expectancy=$27.84, edge_capture=$11107.3 — recorded funnel: n=399, expectancy=$27.84, edge_capture=$1764.98 (parity: True)
- LAYER A LIVE (post_tp1, ratification authority): n=381 (of 399, 18 no local bars), expectancy=$18.98/tr, total=$7232.75, WR=0.283
  - IS(2025) exp=$3.08 (n=246) | OOS(2026) exp=$47.97 (n=135)
  - top-3-day concentration: 0.444
- LAYER A sim-full-scope (EXPLORATORY, unreconciled -- FINDING 2): expectancy=$-91.01/tr, total=$-34675.2
- LAYER B anchor: 18 real fleet PUT positions replayed — candidate $-33.83 vs control(actual_ribbon_ride) $23.7 -> no_regression=False

### `OTM-1_stop-8_fixed` (rank 4/106 in the P5 set)

- **Verdict: PASS** — LAYER A LIVE positive ($34.06/tr) AND LAYER B anchor no-regression vs control -- survives the exit_manager ratification check; vs recorded funnel exp $26.27/tr (sim, NOT the ratification authority per standing doctrine): LIVE post_tp1 is $7.79/tr different -- the scope-mismatch's real economic impact on this population (see FINDING 2 for why the 'sim full-scope' column could not be used as a clean isolated-variable comparison instead)
- combo: strike=OTM-1(so=1) stop=-0.08 lock=fixed trail=0.0 ts=10 | recorded tp/tq used for repro: 1.5/0.8
- LAYER 0 (run_cell repro): n=434, expectancy=$26.27, edge_capture=$11400.6 — recorded funnel: n=434, expectancy=$26.27, edge_capture=$1475.23 (parity: True)
- LAYER A LIVE (post_tp1, ratification authority): n=415 (of 434, 19 no local bars), expectancy=$34.06/tr, total=$14133.4, WR=0.094
  - IS(2025) exp=$22.76 (n=265) | OOS(2026) exp=$54.01 (n=150)
  - top-3-day concentration: 0.474
- LAYER A sim-full-scope (EXPLORATORY, unreconciled -- FINDING 2): expectancy=$-3.49/tr, total=$-1447.6
- LAYER B anchor: 18 real fleet PUT positions replayed — candidate $424.38 vs control(actual_ribbon_ride) $23.7 -> no_regression=True

### `OTM-1_stop-8_trailing0.22` (rank 5/106 in the P5 set)

- **Verdict: PASS** — LAYER A LIVE positive ($12.0/tr) AND LAYER B anchor no-regression vs control -- survives the exit_manager ratification check; vs recorded funnel exp $26.75/tr (sim, NOT the ratification authority per standing doctrine): LIVE post_tp1 is $-14.75/tr different -- the scope-mismatch's real economic impact on this population (see FINDING 2 for why the 'sim full-scope' column could not be used as a clean isolated-variable comparison instead)
- combo: strike=OTM-1(so=1) stop=-0.08 lock=trailing trail=0.22 ts=10 | recorded tp/tq used for repro: 0.3/0.8
- LAYER 0 (run_cell repro): n=417, expectancy=$26.75, edge_capture=$11154.66 — recorded funnel: n=417, expectancy=$26.75, edge_capture=$1467.72 (parity: True)
- LAYER A LIVE (post_tp1, ratification authority): n=399 (of 417, 18 no local bars), expectancy=$12.0/tr, total=$4788.4, WR=0.228
  - IS(2025) exp=$1.83 (n=257) | OOS(2026) exp=$30.41 (n=142)
  - top-3-day concentration: 0.416
- LAYER A sim-full-scope (EXPLORATORY, unreconciled -- FINDING 2): expectancy=$-47.25/tr, total=$-18854.24
- LAYER B anchor: 18 real fleet PUT positions replayed — candidate $129.92 vs control(actual_ribbon_ride) $23.7 -> no_regression=True

### `ATM_stop-8_trailing0.15` (rank 6/106 in the P5 set)

- **Verdict: PASS** — LAYER A LIVE positive ($30.22/tr) AND LAYER B anchor no-regression vs control -- survives the exit_manager ratification check; vs recorded funnel exp $27.41/tr (sim, NOT the ratification authority per standing doctrine): LIVE post_tp1 is $2.81/tr different -- the scope-mismatch's real economic impact on this population (see FINDING 2 for why the 'sim full-scope' column could not be used as a clean isolated-variable comparison instead)
- combo: strike=ATM(so=0) stop=-0.08 lock=trailing trail=0.15 ts=10 | recorded tp/tq used for repro: 0.5/0.8
- LAYER 0 (run_cell repro): n=401, expectancy=$27.41, edge_capture=$10992.51 — recorded funnel: n=401, expectancy=$27.41, edge_capture=$1276.71 (parity: True)
- LAYER A LIVE (post_tp1, ratification authority): n=380 (of 401, 21 no local bars), expectancy=$30.22/tr, total=$11483.5, WR=0.187
  - IS(2025) exp=$9.52 (n=249) | OOS(2026) exp=$69.57 (n=131)
  - top-3-day concentration: 0.344
- LAYER A sim-full-scope (EXPLORATORY, unreconciled -- FINDING 2): expectancy=$-90.42/tr, total=$-34359.1
- LAYER B anchor: 18 real fleet PUT positions replayed — candidate $239.98 vs control(actual_ribbon_ride) $23.7 -> no_regression=True

## Disclosures

- FINDING 2 (methodological, found while validating this script): the 'sim_full_scope' column does NOT reconcile with simulate_trade_real's actual recorded funnel number on a bar-by-bar trace (verified on a specific winning trade: simulate_trade_real recorded max_adverse_premium=$0.49 against an entry of $0.89 -- an 45% adverse excursion, WAY past both the -8% raw stop AND the ratcheted profit-lock floor -- yet did NOT stop the trade out; it later exited profitably via the trailing lock at $1.003). exit_manager's ARM_SCOPE_FULL is documented as 'simulator parity' but this trace shows it is NOT byte-parity with simulate_trade_real's actual bar-walk for a zero-arm-threshold trailing shape -- the exact root cause (something in simulate_trade_real's bar/TP1/stop sequencing not yet isolated) was NOT fully found within this session's time budget. CONSEQUENCE: 'sim_full_scope' below is reported as an EXPLORATORY, NOT-RECONCILED comparison, NOT as a validated sim-parity replica -- do not treat its absolute numbers as authoritative. This does NOT weaken the LIVE (post_tp1) column: per standing doctrine ('exit-shape RATIFICATION evidence = exit_manager replay on real fills, never sim absolute dollars'), simulate_trade_real's number was never the target of reconciliation for the PRIMARY verdict -- LIVE post_tp1 is the real, current, production exit_manager code path, run correctly against the parity-verified (LAYER 0) entry population and real local bars, independent of whether it reproduces simulate_trade_real's more optimistic accounting. Flagged for follow-up, not resolved here: (a) exit_manager.py's ARM_SCOPE_FULL parity claim needs its own dedicated validation pass; (b) t4_exit_matrix.py/t5_confirmatory_matrix.py's shared _load_bars uses '>=' on entry_ts (includes the fill bar in the replay loop) where simulate_trade_real's own bar-walk starts one bar LATER (verified: simulator_real.py:492, opt_idx=entry_idx_opt+1) -- this script uses '>' (excludes the fill bar) after finding the '>=' convention materially changed LIVE-scope results (e.g. this cell's LIVE expectancy moved from -$20.23/tr to +$25.62/tr after the fix) -- T4/T5's own prior conclusions (which used '>=') were NOT re-audited here (out of scope) but may be mildly pessimism-biased on any candidate whose stop/arm condition is reachable from the fill bar itself.
- SCOPE: literal 'top 5 by summary ranking' collapses to ONE distinct shape (tp1_premium_pct/tp1_qty_fraction are dead axes within the P5-survivor set, verified byte-identical funnel rows) -- this run instead confirms all 6 GENUINELY DISTINCT shapes among the 106 survivors, at the same 'handful, not a grind' compute budget the ticket specified.
- LAYER A qty=10 fixed (t4_exit_matrix.py convention) -- absolute $/expectancy are RELATIVE, not the OP-16 absolute (same caveat as every T4/T5 pass).
- LAYER A uses LOCAL 5-min OPRA bars (backtest/data/options/, zero network) -- touch-based stops, 1-min close timing not modeled (same disclosed gap as t4_exit_matrix.py).
- LAYER A ribbon_flip_back=False always (premium-shape replay only, matches every prior anchor/matrix study in this repo).
- LAYER B anchor is PUT-only (exit_shape_parity_study.replay_position hardcodes side='P', a pre-existing limitation of the reused tool, not modified here) -- CALL fleet positions counted and excluded, not silently dropped.
- LAYER B SAMPLE SIZE CAVEAT (important, do not conflate): this run's control total is computed on the CURRENT fills-ledger's 18 PUT-only positions, NOT the ~79-position full-position-set anchor that produced the commonly-cited actual_ribbon_ride totals (-$757.10 in analysis/exit-parity/exit-shape-parity-2026-07-08.json 2026-07-08; the similar '-$893' figure CLAUDE.md cites is from yet another snapshot/date). This script's control_total ($23.70, all 6 shapes share the identical 18-position control replay) is a SMALLER, MORE RECENT, PUT-only-filtered number -- it is NOT a reproduction of and should NOT be compared directly to the -$757/-$893 headline figures. The candidate-vs-control DELTA on this SAME 18-position pool is still a valid relative comparison (both sides replayed on identical real fills via the identical exit_manager call) -- the absolute control number is just not the famous one.
- LAYER B anchor tests the STOP/TP1/LOCK/TRAIL portion of each P5 shape against REAL fleet entries -- it does NOT re-select strike (the anchor's entries are whatever strike the live engine actually filled), matching T4/T5's own established anchor scope exactly.
- LAYER 0 (run_cell) reproduces the ORIGINAL mass_grind combo+kwargs convention exactly (strategy_space_grind.run_cell, the same function mass_grind.py's worker called) -- its n/expectancy is cross-checked against the recorded funnel row as a parity sanity check before layer A/B are trusted.

---
_KILL/PARTIAL is a fully valid outcome: the known profit_lock_arm_scope sim-vs-live mismatch was flagged as the exact reason the backtest number 'is ranking evidence, not yet a live-equivalent number' (dormant-asset audit SS1) — this script exists to resolve that, either direction._
