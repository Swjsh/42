# CANDIDATE: run-a-counterfactual-stage-1-backtest-with-the-vix-confirmat

**Filed:** 2026-09-09
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

Run a counterfactual Stage-1 backtest with the VIX confirmation rule disabled and compute edge_capture on the 7 anchor days; then run OOS/WF on a 6-month window to confirm the rule's effect is not transient.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug run-a-counterfactual-stage-1-backtest-with-the-vix-confirmat --task-id 0bcb3611-5987-4cc6-bc47-9dda3fec2154 --timeout-s 480.0 -> RUNNER-FAILED (timeout: exceeded 480.0s wall-time cap)
status: RUNNER-FAILED (timeout: exceeded 480.0s wall-time cap)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
