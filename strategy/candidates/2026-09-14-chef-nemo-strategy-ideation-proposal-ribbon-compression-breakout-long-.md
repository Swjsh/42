# CANDIDATE: strategy-ideation-proposal-ribbon-compression-breakout-long-

**Filed:** 2026-09-14
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'RIBBON_COMPRESSION_BREAKOUT_LONG' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: When the EMA8‑21‑55 ribbon compresses tightly, a breakout with increased volume signals the start of a short‑term trend. Entry rule: Define ribbon compression as the span between EMA8 and EMA55 being ≤0.10% of price for at least three consecutive 5‑minute bars. Enter long when price closes above the high of the compression range on a bar with volume ≥1.8× the 20‑bar average volume, and the ribbon is still compressed (EMA8‑EMA55 span ≤0.10%). Exit shape: Stop placed at the low of the compression range; target at 2R or a chandelier trail (20% below highest high) with an optional time‑based exit after 60 minutes if target not hit. Regime hint: Effective in low‑volatility environments (VIX <15) and during the mid‑morning (10:00‑12:00 EST) when compression often precedes intraday moves. Novelty claim (why not already in the registry): Unlike BOLLINGER_SQUEEZE which uses Bollinger Band width, this setup uses EMA ribbon compression and adds a volume‑surge condition; no existing setup uses EMA ribbon compression as the trigger. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-ribbon-compression-breakout-long- --task-id 48cadddc-ae67-40a7-81a0-99637287b87c --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
