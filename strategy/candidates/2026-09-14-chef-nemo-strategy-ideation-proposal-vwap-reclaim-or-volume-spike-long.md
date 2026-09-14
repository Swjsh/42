# CANDIDATE: strategy-ideation-proposal-vwap-reclaim-or-volume-spike-long

**Filed:** 2026-09-14
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'VWAP_RECLAIM_OR_VOLUME_SPIKE_LONG' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: After the opening range sets, a return to VWAP on above‑average volume signals institutional buying and a likely continuation upward. Entry rule: Between 09:30‑11:30, if price crosses VWAP from below to above on a bar where volume > 1.5 * volume of the prior bar and close > VWAP, enter long. Exit shape: Chart‑stop at the opening range low, TP1 at 1.5×R, runner trail 20% off the high‑water mark. Regime hint: VIX < 20, price above the 20‑period EMA (uptrend), avoid choppy sessions (price within prior day’s high‑low). Novelty claim (why not already in the registry): Similar to VWAP_RECLAIM_FAILED_BREAK but requires a volume spike and occurs after the opening range rather than after a failed break, making it a distinct setup. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-vwap-reclaim-or-volume-spike-long --task-id a4be3195-e68e-46d4-b7c3-2766e51764d5 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
