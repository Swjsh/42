# CANDIDATE: strategy-ideation-proposal-ribbon-squeeze-breakout-long-free

**Filed:** 2026-09-12
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'RIBBON_SQUEEZE_BREAKOUT_LONG' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: When the EMA ribbon contracts to low volatility, a breakout above the ribbon with increased volume signals resumption of the short‑term trend. Entry rule: Calculate the 8,13,21,34 EMA ribbon; ribbon width = (highest EMA - lowest EMA) / ATR(14). If ribbon width < 0.5 for two consecutive 5‑min bars and the close of the current bar is above the highest EMA and volume > 1.5 × average volume of the last 20 bars, enter long at the close. Exit shape: Initial stop = lowest EMA of the ribbon at entry; target = 2 × (entry - stop) or trail using chandelier exit (ATR × 3) after 1R profit. Regime hint: Best in low‑VIX (<15) and the first 2 hours after open; avoid during high‑VIX (>25) or choppy sessions marked by alternating HH/LL within 20 bars. Novelty claim (why not already in the registry): Closest existing setup is BOLLINGER_SQUEEZE, which uses Bollinger Band width. This candidate uses EMA ribbon width, requires a two‑bar tight condition and volume confirmation, making the logic structurally different. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-ribbon-squeeze-breakout-long-free --task-id 9c428488-ddf1-4b47-9ec4-cc6e0b324179 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
