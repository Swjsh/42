# CANDIDATE: strategy-ideation-proposal-tpo-value-area-break-free-agent-i

**Filed:** 2026-09-12
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'TPO_VALUE_AREA_BREAK' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: A decisive break of the prior day's TPO value area with above‑average volume signals continuation of the auction direction. Entry rule: Calculate prior day's TPO value area high (VAH) and low (VAL). Go long when close > VAH and volume > 1.5× the 20‑bar average volume; go short when close < VAL and volume > 1.5× average volume. Exit shape: Stop at the opposite value‑area edge (VAL for longs, VAH for shorts) or 1R; target at 2R or trail using a chandelier exit (ATR×3). Regime hint: Works best in trending regimes (ADX > 20) with VIX < 25; avoid choppy, low‑volume sessions (ADX < 15) or pre‑news windows. Novelty claim (why not already in the registry): No existing candidate uses TPO/value‑area concepts; the nearest is LEVEL_BREAK_FIRST_STRIKE, which relies on predefined price levels rather than market‑profile derived value areas. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-tpo-value-area-break-free-agent-i --task-id bea9fd3b-c59a-46f8-be35-96c2d26d3865 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
