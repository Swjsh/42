# CANDIDATE: strategy-ideation-proposal-ribbon-rsi-pullback-long-free-age

**Filed:** 2026-09-14
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'RIBBON_RSI_PULLBACK_LONG' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: A pullback to the rising EMA ribbon with RSI in the 40‑50 zone and a higher‑low structure offers a low‑risk long entry in an uptrend. Entry rule: When the 5‑minute low touches or crosses below the EMA20 (or the middle of the EMA9/EMA20/EMA50 ribbon) while the close is above EMA20, RSI(14) is between 40 and 50, and the last two swing lows form a higher‑low (HL) pattern, enter long at the close of the bar that touches EMA20. Exit shape: Stop below the recent swing low (the prior HL) or 0.5% below entry, whichever is lower; TP1 at 1.5R, runner trailed with a 15 % trailing‑stop of the highest close since entry. Regime hint: Ideal in VIX < 20 and when the 50‑EMA is sloping upward (trend); avoid when price is below the 200‑EMA or during choppy sessions with frequent HH/LL. Novelty claim (why not already in the registry): Differs from BULLISH_RECLAIM_RIDE_THE_RIBBON (which requires a VWAP reclaim after a dip) by using EMA20 as dynamic support, adding RSI momentum filter and HL structure, making it a pullback rather than a reclaim. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-ribbon-rsi-pullback-long-free-age --task-id 550f3ef8-91cd-4d0d-bf18-58578dc52a97 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
