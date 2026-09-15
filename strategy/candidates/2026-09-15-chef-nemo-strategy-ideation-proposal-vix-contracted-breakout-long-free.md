# CANDIDATE: strategy-ideation-proposal-vix-contracted-breakout-long-free

**Filed:** 2026-09-15
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'VIX_CONTRACTED_BREAKOUT_LONG' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: When near‑term volatility is depressed (VIX <13) and price breaks above the prior day’s high on expanding volume, a low‑volatility breakout is likely to trend. Entry rule: If the prior day’s VIX close is <13 and the current 5‑min bar closes above the prior day’s high with volume >2× the average volume of the last 20 bars, enter long at the bar’s close. Exit shape: Chart‑stop at the prior day’s low (or the most recent swing low), TP1 at 2R, runner trail using a premium‑stop of 15% of ATR from the entry price. Regime hint: Exclude FOMC days; trade between 09:45‑11:30 ET to avoid open‑chaos and late‑day drift. Novelty claim (why not already in the registry): VIX_REGIME_DAYSIDE only flags high/low VIX regimes; this adds a concrete breakout trigger with volume expansion and a specific VIX threshold, which is not present in any existing setup. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-vix-contracted-breakout-long-free --task-id 024a63f0-1e50-4a14-a1bd-e438a053e363 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
