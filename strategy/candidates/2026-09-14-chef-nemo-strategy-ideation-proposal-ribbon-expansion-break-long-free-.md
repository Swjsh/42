# CANDIDATE: strategy-ideation-proposal-ribbon-expansion-break-long-free-

**Filed:** 2026-09-14
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'RIBBON_EXPANSION_BREAK_LONG' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: An expanding EMA ribbon signals rising momentum; a break above the ribbon with a strong bullish bar captures continuation. Entry rule: When (EMA8 - EMA55) > 1.5 * ATR(14) and close > EMA55 and close > open and (close - open) > 0.5 * (high - low), go long. Exit shape: Chart‑stop at the most recent swing low (prior HH/LL structure), TP1 at 2.0×R, runner trail using a chandelier exit (ATR×3). Regime hint: VIX between 12‑25, time after 10:00, price above the 200‑period EMA (long‑term bias). Novelty claim (why not already in the registry): Differs from BULLISH_RECLAIM_RIDE_THE_RIBBON which waits for a pullback to the ribbon; this triggers on ribbon expansion without a pullback, providing a different entry signal. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-ribbon-expansion-break-long-free- --task-id b6dcf87a-2371-401c-b880-8fd45dc2e845 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
