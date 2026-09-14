# CANDIDATE: interpret-sniper-real-fills-grinder-grinder-output-5-keepers

**Filed:** 2026-09-14
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

Interpret sniper_real_fills_grinder grinder output: 5 keepers found. Top: wide_pnl=-90.8, edge_capture=-126.0, WR=0.5. Original intent: Auto-chain: sniper_real_fills_grinder after sniper_stage2_grinder produced 5 keepers. Parent: Auto-chain: sniper_stage2_. For each keeper assess: (1) genuine edge or overfit? (2) which knob changes drove improvement vs baseline? (3) OP-20 disclosures that apply? (4) promote to LEADERBOARD or needs OOS walk-forward first? Keepers JSON: [{"combo":{"vol_mult":1.1,"body_min_cents":0.02,"min_stars":2,"strike_offset":2,"premium_stop_pct":-0.1,"tp1_premium_pct":0.5,"tp1_qty_fraction":0.5,"runner_target_pct":2.0,"profit_lock_threshold_pct":0.05,"profit_lock_stop_offset_pct":0.05,"qty":10,"proximity_dollars":1.5,"require_break_above_open":true},"pnl_4_29":-329.0,"pnl_5_04":110.0,"pnl_5_05":-236.0,"pnl_5_06":0.0,"pnl_5_07":0,"pnl_5_12":120.5,"by_day":{"2025-01-07":0,"2025-01-10":694.2,"2025-01-16":-345.0,"2025-01-24":-143.0,"2025-01-30":138.0,"2025-01-31":-26.0,"2025-02-06":33.5,"2025-02-07":0,"2025-02-11":-247.0,"2025-02-12":-382.0,

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug interpret-sniper-real-fills-grinder-grinder-output-5-keepers --task-id 8c10e119-e8f3-45dd-98eb-09fc09cad829 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
