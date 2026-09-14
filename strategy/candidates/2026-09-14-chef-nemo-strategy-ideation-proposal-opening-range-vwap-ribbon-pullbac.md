# CANDIDATE: strategy-ideation-proposal-opening-range-vwap-ribbon-pullbac

**Filed:** 2026-09-14
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'OPENING_RANGE_VWAP_RIBBON_PULLBACK_LONG' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: A pullback to VWAP within the opening range, supported by a bullish EMA ribbon, signals institutional buying on dip and offers a high‑probability long entry. Entry rule: After the first 5‑minute bar, if price crosses below VWAP but stays above the OR low, and the 8/21/55 EMA ribbon is bullish (8 EMA > 21 EMA > 55 EMA), enter long at the close of the bar that touches VWAP. Exit shape: Chart‑stop at OR low (structure invalidation), TP1 at 1.5R, runner trail 10% off high‑water‑mark. Regime hint: Best when VIX < 20 and during the first 30 minutes after open (09:30‑10:00 EST); avoid choppy sessions where the ribbon is flat or tangled. Novelty claim (why not already in the registry): Closest existing setup is VWAP_RECLAIM_FAILED_BREAK, which looks for a failed VWAP break after a gap. This proposal instead uses a VWAP pullback within the OR combined with ribbon confirmation, a distinct entry condition not present in the registry. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-opening-range-vwap-ribbon-pullbac --task-id a3f5c186-ae7b-4eeb-8010-282b879582cd --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
