# CANDIDATE: strategy-ideation-proposal-volatility-compression-breakout-l

**Filed:** 2026-09-14
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'VOLATILITY_COMPRESSION_BREAKOUT_LONG' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: A contraction in ATR below its 20‑period low followed by a breakout above the prior day high with expanding volume captures explosive moves. Entry rule: When the 5‑minute ATR(5) is lower than the lowest ATR(5) of the past 20 bars and the close exceeds the prior day's high, and volume on that bar is >1.5× the 20‑period average volume, enter long at the close. Exit shape: Stop at the low of the breakout bar or the 20‑period ATR below entry, whichever is higher; TP1 at 2R, runner trailed with chandelier trail (ATR*2.5). Regime hint: Effective when VIX > 16 (enough volatility to expand) and during the mid‑day window (10:00‑14:00) when compression patterns often resolve; avoid low‑VIX (<12) dead‑zoned sessions. Novelty claim (why not already in the registry): Distinct from volatility‑based entries in the registry (none exist); it combines ATR compression, prior day high break, and volume surge, unlike BOLLINGER_SQUEEZE which uses Bollinger Band width and close inside/outside bands. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-volatility-compression-breakout-l --task-id 730a29f5-86cb-4a04-9742-90d8bab5900d --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
