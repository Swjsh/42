# CANDIDATE: interpret-overnight-grinder-grinder-output-5-keepers-found-t

**Filed:** 2026-09-12
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

Interpret overnight_grinder grinder output: 5 keepers found. Top: wide_pnl=6688.35, edge_capture=670.6, WR=0.393. Original intent: Run overnight_grinder parameter sweep: General v14/v15 parameter sweep — 432 combos, wide_pnl differentiator. Find keepe. For each keeper assess: (1) genuine edge or overfit? (2) which knob changes drove improvement vs baseline? (3) OP-20 disclosures that apply? (4) promote to LEADERBOARD or needs OOS walk-forward first? Keepers JSON: [{"combo":{"super_stop":-0.15,"super_tp1":0.75,"runner_target":3.0,"level_qty":18,"level_stop":-0.12,"level_tp1":0.3,"trendline_stop":-0.06},"pnl_4_29":0.0,"pnl_5_04":670.6,"by_day":{"2026-04-29":0.0,"2026-05-01":0.0,"2026-05-04":670.6,"2026-05-05":0.0,"2026-05-06":0.0,"2026-05-07":74.29,"2026-05-07_2":74.29},"winners_capture":670.6,"losers_added":0.0,"edge_capture":670.6,"wide_pnl":6688.35,"wide_n_trades":28,"wide_wr":0.393,"top5_pct":1.067,"quarter_pnl":{"2025-Q1":-487.28,"2025-Q2":-123.97,"2025-Q3":-572.83,"2025-Q4":1282.53,"2026-Q1":3977.66,"2026-Q2":2612.25},"positive_quarters":3,"quarter

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug interpret-overnight-grinder-grinder-output-5-keepers-found-t --task-id 0a37a2ac-8d5e-40e9-831a-4d77e9047b65 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
