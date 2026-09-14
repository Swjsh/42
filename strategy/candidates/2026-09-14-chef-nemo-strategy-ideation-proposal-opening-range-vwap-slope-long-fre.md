# CANDIDATE: strategy-ideation-proposal-opening-range-vwap-slope-long-fre

**Filed:** 2026-09-14
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'OPENING_RANGE_VWAP_SLOPE_LONG' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: Early morning bias persists when VWAP slopes upward and price stays above VWAP, offering a high‑probability long. Entry rule: If the first 30‑minute opening range high > opening range low and the 5‑minute VWAP at 30 min is above its value at 15 min (positive slope) and price close of the 30‑min bar is above VWAP, then enter long at the close of the first 5‑minute bar after 30 min (i.e., at 35 min). Exit shape: chart-stop at opening range low, target at 1.5R or trailing 15% off HWM using premium‑stop % Regime hint: VIX < 20 and time between 09:30‑11:00 ET; avoid choppy days where ribbon width > ATR*1 Novelty claim (why not already in the registry): Unlike ORB_RETEST_LONG which waits for a retest of the opening range edge, this setup enters on the initial VWAP slope confirmation without requiring a retest; it also adds a VWAP slope condition absent from existing registrations. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-opening-range-vwap-slope-long-fre --task-id c074a3fa-406b-4dc0-98d5-ccbdc0cf9375 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
