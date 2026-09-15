# CANDIDATE: strategy-ideation-proposal-opening-range-width-vix-trend-sho

**Filed:** 2026-09-15
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'OPENING_RANGE_WIDTH_VIX_TREND_SHORT' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: A narrow opening range coupled with an intraday rise in VIX predicts an afternoon sell‑off. Entry rule: If the first 30‑min opening range (high‑low) is < 0.2% of SPY’s price AND intraday VIX > VIX at open + 0.5 points, enter short at the 10:45 close. Exit shape: Chart‑stop at the opening range high (structure invalidation), TP1 at 2R, runner using a 0.3% premium‑stop trailing trail. Regime hint: VIX open > 18, time 10:00‑14:00, overall market structure showing a lower high on the 60‑min chart. Novelty claim (why not already in the registry): Resembles GAP_AND_GO but uses opening‑range width and an intraday VIX rise filter; no existing setup combines these specific criteria. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-opening-range-width-vix-trend-sho --task-id c9581e4a-5257-4e3d-bdae-8647d67849a5 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
