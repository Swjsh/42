# CANDIDATE: interpret-shotgun-scalper-stage3-grinder-output-5-keepers-fo

**Filed:** 2026-09-12
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

Interpret shotgun_scalper_stage3 grinder output: 5 keepers found. Top: wide_pnl=19720.8, edge_capture=285.0, WR=0.567. Original intent: Run shotgun_scalper_stage3 parameter sweep: SHOTGUN_SCALPER Stage-3 — directional participation scoring (972 combos). Fi. For each keeper assess: (1) genuine edge or overfit? (2) which knob changes drove improvement vs baseline? (3) OP-20 disclosures that apply? (4) promote to LEADERBOARD or needs OOS walk-forward first? Keepers JSON: [{"combo":{"tp_premium_pct":1.5,"stop_premium_pct":-0.35,"time_stop_min":15,"strike_offset":2,"chandelier_arm_pct":0.5,"vol_ratio_threshold":1.0},"by_day":{"2026-04-29":54.0,"2026-05-01":234.0,"2026-05-04":177.0,"2026-05-14":0,"2026-05-15":0,"2026-05-05":-180.0,"2026-05-06":132.0,"2026-05-07":291.0},"winners_capture":465.0,"losers_added":180.0,"edge_capture":285.0,"edge_capture_pct":0.069,"max_edge_possible":4150,"wide_pnl":19720.8,"wide_n_trades":1399,"wide_wr":0.567,"expectancy_per_trade":14.1,"sharpe":4.074,"top5_pct":0.169,"quarter_pnl":{"2025-Q1":3775.35,"2025-Q2":2291.1,"2025-Q3":1799.85

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug interpret-shotgun-scalper-stage3-grinder-output-5-keepers-fo --task-id 9d36403d-7ad3-4af7-a966-015d190db647 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
