# CANDIDATE: strategy-ideation-proposal-vol-compression-named-level-break

**Filed:** 2026-09-15
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'VOL_COMPRESSION_NAMED_LEVEL_BREAK_SHORT' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: After ATR contracts to a low percentile, a break of a named level on elevated volume signals a short‑term reversal. Entry rule: If ATR(14) is below its 20‑day low AND price closes below the prior day’s high (named level) with volume > 1.5× the 20‑bar average volume, enter short at the close. Exit shape: Chart‑stop at the prior day’s low (structure invalidation), TP1 at 1R, runner using a 0.5% premium‑stop trailing trail. Regime hint: VIX > 22, time 10:00‑12:00, market structure showing a lower high on the 15‑min chart. Novelty claim (why not already in the registry): Similar to LEVEL_BREAK_FIRST_STRIKE but requires ATR contraction and a volume surge filter; no existing setup combines these three primitives. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-vol-compression-named-level-break --task-id fd815f48-9d52-49dc-af27-332aac351927 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
