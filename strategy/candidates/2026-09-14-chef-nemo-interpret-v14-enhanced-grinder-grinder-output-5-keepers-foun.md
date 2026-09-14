# CANDIDATE: interpret-v14-enhanced-grinder-grinder-output-5-keepers-foun

**Filed:** 2026-09-14
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

Interpret v14_enhanced_grinder grinder output: 5 keepers found. Top: wide_pnl=26601.2, edge_capture=499.64, WR=0.649. Original intent: Run v14_enhanced_grinder parameter sweep: V14E variant sweep — includes 5/12 anchor day + SNIPER-style profit-lock knobs. For each keeper assess: (1) genuine edge or overfit? (2) which knob changes drove improvement vs baseline? (3) OP-20 disclosures that apply? (4) promote to LEADERBOARD or needs OOS walk-forward first? Keepers JSON: [{"combo":{"strike_offset_bear":0,"min_triggers_bear":1,"premium_stop_pct_bear":-0.2,"tp1_qty_fraction":0.5,"no_trade_before":"09:35","profit_lock_threshold_pct":0.05,"profit_lock_stop_offset_pct":0.1,"tp1_premium_pct":0.3,"runner_target_premium_pct":2.5},"pnl_4_29":294.15,"pnl_5_04":201.18,"pnl_5_12":25.87,"by_day":{"2026-04-29":294.15,"2026-05-01":-21.56,"2026-05-04":201.18,"2026-05-12":25.87,"2026-05-05":0.0,"2026-05-06":0.0,"2026-05-07":230.59},"winners_capture":499.64,"losers_added":0.0,"edge_capture":499.64,"wide_pnl":26601.2,"wide_n_trades":404,"wide_wr":0.649,"top5_pct":0.148,"quarter_

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug interpret-v14-enhanced-grinder-grinder-output-5-keepers-foun --task-id 4c11a1ed-217a-4564-bd5d-a414aa2e71ce --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
