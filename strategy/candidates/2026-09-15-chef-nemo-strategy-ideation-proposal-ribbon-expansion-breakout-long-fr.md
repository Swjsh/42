# CANDIDATE: strategy-ideation-proposal-ribbon-expansion-breakout-long-fr

**Filed:** 2026-09-15
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'RIBBON_EXPANSION_BREAKOUT_LONG' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: An expanding EMA ribbon signals rising momentum; a breakout of recent highs with above‑average volume captures the move. Entry rule: When (EMA8 − EMA55) > 1.5× ATR(14) and price closes above the highest high of the last 20 bars with volume >1.3× the average volume of those 20 bars, go long. Exit shape: Chart‑stop at the prior swing low (structure invalidation), TP1 at 2×R, runner trailed at 1.5× ATR. Regime hint: VIX < 25, time 10:00‑14:00, EMA ribbon sloping upward. Novelty claim (why not already in the registry): Nearest is BEARISH_REJECTION_RIDE_THE_RIBBON (rides the ribbon after a rejection); this triggers on ribbon *expansion* and a volume‑confirmed breakout, a distinct logic. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-ribbon-expansion-breakout-long-fr --task-id 75ad4e88-30f6-4467-8a26-fb4fed8c30aa --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
