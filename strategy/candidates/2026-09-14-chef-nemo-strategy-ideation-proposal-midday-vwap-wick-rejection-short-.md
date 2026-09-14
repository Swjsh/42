# CANDIDATE: strategy-ideation-proposal-midday-vwap-wick-rejection-short-

**Filed:** 2026-09-14
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'MIDDAY_VWAP_WICK_REJECTION_SHORT' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: A pronounced upper wick rejecting VWAP in the midday session, accompanied by weakening momentum, signals a short‑term reversal. Entry rule: After 11:00 EST, when price approaches VWAP from below and forms a candle with an upper wick ≥60% of the total range and closes below VWAP, and RSI(14) <40, and volume on that bar is ≤0.8× the 20‑bar average volume, then enter short at the close of that candle. Exit shape: Stop placed at the high of the wick candle; target set at 1R or at the VWAP level, with an optional trailing stop of 10% ATR. Regime hint: Most reliable when VIX is moderate (12‑22) and the market is not in a strong trend (price action shows alternating higher highs/lows); avoid during strong trending days (ADX >25). Novelty claim (why not already in the registry): While BEARISH_REJECTION_RIDE_THE_RIBBON uses ribbon‑based rejection, this setup focuses on VWAP wick rejection, RSI weakness, and volume‑dryness, none of which are required in the existing bearish rejection ribbon. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-midday-vwap-wick-rejection-short- --task-id 4ad58540-53ff-4997-a71f-033b0bc1e00c --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
