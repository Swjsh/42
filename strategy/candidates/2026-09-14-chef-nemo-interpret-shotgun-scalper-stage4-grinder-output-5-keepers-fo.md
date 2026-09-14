# CANDIDATE: interpret-shotgun-scalper-stage4-grinder-output-5-keepers-fo

**Filed:** 2026-09-14
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

Interpret shotgun_scalper_stage4 grinder output: 5 keepers found. Top: wide_pnl=22084.2, edge_capture=506.55, WR=0.576. Original intent: Run shotgun_scalper_stage4 parameter sweep: SHOTGUN_SCALPER Stage-4 — HTF-gated directional scoring (288 combos). Find k. For each keeper assess: (1) genuine edge or overfit? (2) which knob changes drove improvement vs baseline? (3) OP-20 disclosures that apply? (4) promote to LEADERBOARD or needs OOS walk-forward first? Keepers JSON: [{"combo":{"tp_premium_pct":0.75,"stop_premium_pct":-0.35,"time_stop_min":12,"strike_offset":2,"chandelier_arm_pct":0.6,"vol_ratio_threshold":1.2},"by_day":{"2026-04-29":297.0,"2026-05-01":231.0,"2026-05-04":177.0,"2026-05-14":0,"2026-05-15":-195.45,"2026-05-05":-3.0,"2026-05-06":231.0,"2026-05-07":95.85},"winners_capture":509.55,"losers_added":3.0,"edge_capture":506.55,"edge_capture_pct":0.122,"max_edge_possible":4150,"wide_pnl":22084.2,"wide_n_trades":1199,"wide_wr":0.576,"expectancy_per_trade":18.42,"sharpe":5.093,"top5_pct":0.139,"quarter_pnl":{"2025-Q1":2960.55,"2025-Q2":5828.85,"2025-Q3"

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug interpret-shotgun-scalper-stage4-grinder-output-5-keepers-fo --task-id 3208c5b8-0d3a-4f48-b5c3-8c64f8909ae3 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
