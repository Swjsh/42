# CANDIDATE: strategy-ideation-proposal-vwap-ribbon-boost-long-free-agent

**Filed:** 2026-09-15
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'VWAP_RIBBON_BOOST_LONG' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: Price pulling back to VWAP during a bullish EMA ribbon with above‑average volume tends to bounce, offering a long edge. Entry rule: If 9‑EMA > 20‑EMA > 50‑EMA (bullish ribbon) AND price crosses above VWAP from below on a bar where close > open AND volume > 1.5 * 20‑period average volume, enter long at the close of that bar. Exit shape: Initial stop at the swing low preceding entry (or 1 ATR below entry, whichever is tighter); target at 2 × ATR or trail using a chandelier exit (ATR × 3). Regime hint: Best when VIX < 20 and after the first 30 minutes of the session, when the intraday trend is intact (price above the 20‑EMA). Novelty claim (why not already in the registry): Similar to BULLISH_RECLAIM_RIDE_THE_RIBBON but uses VWAP as dynamic support, requires a volume surge and a bullish EMA ribbon alignment, making the entry condition structurally distinct. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-vwap-ribbon-boost-long-free-agent --task-id 92ed396c-d2be-48a2-b8da-2d77298220e9 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
