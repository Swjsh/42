# CANDIDATE: modify-list-gamma-tasks-jsonps1-to-emit-days-interval-for-da

**Filed:** 2026-09-09
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

Modify `_list-gamma-tasks-json.ps1` to emit `days_interval` for `DailyTrigger` tasks and update `expected_gap_minutes()` in `unattended_health.py` to use it, then add a guard test in `backtest/tests/test_unattended_health.py` to verify every-n-day triggers are scored at their real cadence.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug modify-list-gamma-tasks-jsonps1-to-emit-days-interval-for-da --task-id bc955145-d6e1-40e5-928f-56c09d067446 --timeout-s 480.0 -> RUNNER-FAILED (subprocess_timeout>540.0s)
status: RUNNER-FAILED (subprocess_timeout>540.0s)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
