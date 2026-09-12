# CANDIDATE: strategy-ideation-proposal-gex-pin-reversal-free-agent-ideat

**Filed:** 2026-09-12
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'GEX_PIN_REVERSAL' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: When dealer net gamma exposure approaches zero near the current price, gamma‑flip acceleration creates a short‑term breakout move. Entry rule: Enter long when |DNG| < 500M, price is within 0.1% of the DNG‑weighted strike, and ATR(14) expands >1.5× its 20‑bar average, with a close above the prior bar high; enter short under the same conditions with a close below the prior bar low. Exit shape: Stop at the opposite gamma‑flip level (where DNG crosses zero again) or 0.5R; target at 2R or trail using a premium‑stop of 10% of the entry price. Regime hint: Effective when VIX > 20 (elevated gamma sensitivity) and during midday (11:30‑13:30) when dealers rebalance gamma; avoid low‑VIX (<12) where gamma effects are weak. Novelty claim (why not already in the registry): The registry contains no setup referencing dealer net gamma exposure; the closest is VIX_REGIME_DAYSIDE, which uses VIX levels only, not dealer‑gamma dynamics. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-gex-pin-reversal-free-agent-ideat --task-id 31280ae2-696b-46e4-b5c8-dc741b883532 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
