# CANDIDATE: strategy-ideation-proposal-ema-ribbon-squeeze-breakout-long-

**Filed:** 2026-09-12
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'EMA_RIBBON_SQUEEZE_BREAKOUT_LONG' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: When the 8/21/55 EMA ribbon contracts to a narrow range (low ATR) indicating suppressed volatility, a breakout above the ribbon with above-average volume signals an imminent intraday trend. Entry rule: Calculate the 8,21,55 EMA ribbon; compute ribbon width as (highest EMA - lowest EMA) / ATR(14). If ribbon width < 0.5 for at least 3 consecutive 5‑min bars and the current bar closes above the highest EMA with volume > 1.5 * average volume of the last 20 bars, go long at close. Exit shape: Initial stop at the lowest EMA of the ribbon (chart‑stop), target 1.5R, then trail remaining position with a chandelier exit (ATR×3) from highest high. Regime hint: Best in low‑VIX (<15) and non‑trend‑chop (ADX <20) environments; avoid during high‑VIX (>25) or strong trend days where ribbon is already expanded. Novelty claim (why not already in the registry): Unlike BOLLINGER_SQUEEZE which uses Bollinger Bands width, this setup uses the EMA ribbon width relative to ATR, capturing compression of the trend‑following moving averages themselves; no existing registry entry uses EMA ribbon width as a volatility filter. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-ema-ribbon-squeeze-breakout-long- --task-id d9cd5731-d64d-4fbc-a2eb-fac27b48dbda --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
