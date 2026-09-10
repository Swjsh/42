# CANDIDATE: investigate-the-bearish-rejection-setups-ribbon-spread-condi

**Filed:** 2026-09-09
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

Investigate the BEARISH_REJECTION setup's ribbon spread condition (≥30 cents Fast EMA to Slow EMA): count how many anchor day entries would have been blocked by a too-tight ribbon and assess the impact on win rate and avg P&L.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug investigate-the-bearish-rejection-setups-ribbon-spread-condi --task-id 90ff8f3c-7ba4-41ba-af06-ea02dbff1c18 --timeout-s 480.0 -> RUNNER-FAILED (timeout: exceeded 480.0s wall-time cap)
status: RUNNER-FAILED (timeout: exceeded 480.0s wall-time cap)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
