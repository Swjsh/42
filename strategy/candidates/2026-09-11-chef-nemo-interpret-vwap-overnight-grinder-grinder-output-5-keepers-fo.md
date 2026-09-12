# CANDIDATE: interpret-vwap-overnight-grinder-grinder-output-5-keepers-fo

**Filed:** 2026-09-11
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

Interpret vwap_overnight_grinder grinder output: 5 keepers found. Top: wide_pnl=587.72, edge_capture=40.01, WR=0.833. Original intent: Run vwap_overnight_grinder parameter sweep: VWAP anchored entry sweep — VWAP reclaim / rejection combos. Find keepers wi. For each keeper assess: (1) genuine edge or overfit? (2) which knob changes drove improvement vs baseline? (3) OP-20 disclosures that apply? (4) promote to LEADERBOARD or needs OOS walk-forward first? Keepers JSON: [{"combo":{"vol_mult":1.5,"proximity_dollars":0.15,"lookback_bars":2,"body_min_cents":0.05,"premium_stop_pct":-0.14,"tp1_premium_pct":0.5,"runner_target_pct":2.0,"strike_offset":2,"qty":3,"tp1_qty_fraction":0.667,"profit_lock_threshold_pct":0.1,"profit_lock_stop_offset_pct":0.05,"require_ribbon_agreement":true,"ribbon_min_spread_cents":30.0},"pnl_4_29":0,"pnl_5_04":0,"by_day":{"2026-04-29":0,"2026-05-01":40.01,"2026-05-04":0,"2026-05-05":40.54,"2026-05-06":0,"2026-05-07":0,"2026-05-07_2":0},"winners_capture":40.01,"losers_added":0.0,"edge_capture":40.01,"wide_pnl":587.72,"wide_n_trades":12,"wi

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug interpret-vwap-overnight-grinder-grinder-output-5-keepers-fo --task-id bad982fc-9bc2-489f-8262-de2505a87505 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
