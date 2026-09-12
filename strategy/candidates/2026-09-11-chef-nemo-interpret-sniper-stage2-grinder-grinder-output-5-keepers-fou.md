# CANDIDATE: interpret-sniper-stage2-grinder-grinder-output-5-keepers-fou

**Filed:** 2026-09-11
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

Interpret sniper_stage2_grinder grinder output: 5 keepers found. Top: wide_pnl=40656.65, edge_capture=373.48, WR=0.932. Original intent: Auto-chain: sniper_stage2_grinder after sniper_overnight_grinder produced 5 keepers. Parent: Run sniper_overnight_grinde. For each keeper assess: (1) genuine edge or overfit? (2) which knob changes drove improvement vs baseline? (3) OP-20 disclosures that apply? (4) promote to LEADERBOARD or needs OOS walk-forward first? Keepers JSON: [{"combo":{"vol_mult":1.1,"body_min_cents":0.02,"min_stars":2,"strike_offset":2,"premium_stop_pct":-0.06,"tp1_premium_pct":0.4,"runner_target_pct":3.0,"profit_lock_threshold_pct":0.0,"profit_lock_stop_offset_pct":0.08,"tp1_qty_fraction":0.667,"qty":10,"proximity_dollars":1.5,"require_break_above_open":true},"pnl_4_29":181.84,"pnl_5_04":191.64,"by_day":{"2026-04-29":181.84,"2026-05-01":0,"2026-05-04":191.64,"2026-05-05":202.41,"2026-05-06":0,"2026-05-07":235.4,"2026-05-07_2":235.4},"winners_capture":373.48,"losers_added":0.0,"edge_capture":373.48,"wide_pnl":40656.65,"wide_n_trades":234,"wide_wr

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug interpret-sniper-stage2-grinder-grinder-output-5-keepers-fou --task-id 9a128c41-349a-4800-8a93-d6a3119dcaac --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
