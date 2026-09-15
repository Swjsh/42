# CANDIDATE: strategy-ideation-proposal-gap-fade-vwap-reversion-long-free

**Filed:** 2026-09-15
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'GAP_FADE_VWAP_REVERSION_LONG' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: A gap down at open that quickly fills back to VWAP within the first half‑hour indicates fading gap pressure and a long mean‑reversion opportunity. Entry rule: If the opening price is more than 0.5% below the prior close (gap down) and price crosses above VWAP within the first six 5‑min bars (30 min), enter long at the close of the bar that crosses above VWAP. Exit shape: Chart‑stop at the gap low (invalidation), TP1 at 1.5R, runner trail using a premium‑stop of 10% of ATR from the entry price. Regime hint: VIX < 22 and avoid the first 15 minutes after major news releases; trade between 09:30‑10:30 ET. Novelty claim (why not already in the registry): GAP_AND_GO trades the continuation of a gap in the same direction; this setup trades the fade/reversal of a gap back to VWAP, using a different directional bias and VWAP‑based trigger. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-gap-fade-vwap-reversion-long-free --task-id 76dea87e-40cc-413c-908a-dd49a730b224 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
