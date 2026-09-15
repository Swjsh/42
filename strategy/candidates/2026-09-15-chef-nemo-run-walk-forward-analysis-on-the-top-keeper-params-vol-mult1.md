# CANDIDATE: run-walk-forward-analysis-on-the-top-keeper-params-vol-mult1

**Filed:** 2026-09-15
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

Run walk-forward analysis on the top keeper (params: vol_mult=1.1, body_min_cents=0.02, min_stars=2, strike_offset=2, premium_stop_pct=-0.06, tp1_premium_pct=0.4, runner_target_pct=3.0, profit_lock_threshold_pct=0.0, profit_lock_stop_offset_pct=0.08, tp1_qty_fraction=0.667, qty=10, proximity_dollars=1.5, require_break_above_open=true) across 2025-Q3 and 2026-Q1 to verify regime stability and OOS performance.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug run-walk-forward-analysis-on-the-top-keeper-params-vol-mult1 --task-id 93dfde6d-6c0b-4994-a33c-a2d3919fc560 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
