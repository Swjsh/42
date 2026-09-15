# CANDIDATE: interpret-shotgun-scalper-stage2-grinder-output-5-keepers-fo

**Filed:** 2026-09-15
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

Interpret shotgun_scalper_stage2 grinder output: 5 keepers found. Top: wide_pnl=15706.5, edge_capture=-36.0, WR=0.57. Original intent: Run shotgun_scalper_stage2 parameter sweep: SHOTGUN_SCALPER Stage-2 — relaxed gates, winning-region focus (1458 combos).. For each keeper assess: (1) genuine edge or overfit? (2) which knob changes drove improvement vs baseline? (3) OP-20 disclosures that apply? (4) promote to LEADERBOARD or needs OOS walk-forward first? Keepers JSON: [{"combo":{"tp_premium_pct":0.5,"stop_premium_pct":-0.3,"time_stop_min":10,"strike_offset":2,"chandelier_arm_pct":0.5,"vol_ratio_threshold":1.2},"by_day":{"2026-05-05":-36.0,"2026-05-06":81.0,"2026-05-07":87.0},"winners_capture":0,"losers_added":36.0,"edge_capture":-36.0,"edge_capture_pct":0.0,"max_edge_possible":0,"wide_pnl":15706.5,"wide_n_trades":1279,"wide_wr":0.57,"expectancy_per_trade":12.28,"sharpe":4.214,"top5_pct":0.184,"quarter_pnl":{"2025-Q1":1561.2,"2025-Q2":3732.0,"2025-Q3":2408.4,"2025-Q4":3237.3,"2026-Q1":2615.1,"2026-Q2":2152.5},"positive_quarters":6,"quarter_count":6,"max_draw

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug interpret-shotgun-scalper-stage2-grinder-output-5-keepers-fo --task-id 408c272a-b714-40cd-9278-6edae2748513 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
