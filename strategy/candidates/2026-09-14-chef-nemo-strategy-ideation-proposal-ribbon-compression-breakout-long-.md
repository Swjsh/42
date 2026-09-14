# CANDIDATE: strategy-ideation-proposal-ribbon-compression-breakout-long-

**Filed:** 2026-09-14
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'RIBBON_COMPRESSION_BREAKOUT_LONG' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: A tight EMA ribbon signals low volatility; a breakout with increased volume captures the ensuing expansion move. Entry rule: When the 8‑,21‑,34‑period EMA ribbon width (max-min) is less than 0.5×ATR(14) for three consecutive 5‑minute bars, and the next bar closes above the high of the third compression bar with volume > 1.5× the 20‑period average volume, enter long at the close of that breakout bar. Exit shape: chart‑stop at the low of the third compression bar, target at 2×ATR or TP1 at 1.5R with runner trailing 20% off HWM Regime hint: Best when VIX is between 12‑22 and the market is not in a strong trend ribbon‑duration > 8 bars (avoid MAX_RIBBON_DUR_8 conditions); avoid major news windows (first 30 min after open and 15‑16 ET) Novelty claim (why not already in the registry): While BOLLINGER_SQUEEZE uses Bollinger Band width, this concept applies the same squeeze logic to the EMA ribbon, a primitive not used in any existing setup; additionally it requires a volume expansion filter not present in the squeezed‑ribbon killed list. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-ribbon-compression-breakout-long- --task-id 9936d6d6-d147-4b7d-999d-208d858391ae --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
