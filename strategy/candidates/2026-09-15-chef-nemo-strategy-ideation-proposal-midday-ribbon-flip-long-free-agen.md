# CANDIDATE: strategy-ideation-proposal-midday-ribbon-flip-long-free-agen

**Filed:** 2026-09-15
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'MIDDAY_RIBBON_FLIP_LONG' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: A bullish alignment of the 8/21/55 EMA ribbon during the midday lull, accompanied by above‑average volume, signals resumption of the morning trend. Entry rule: After 11:00 ET, if the 8 EMA crosses above the 21 EMA and the 21 EMA is above the 55 EMA on a 5‑min bar with volume >1.5× the average volume of the prior four bars, go long at the bar’s close. Exit shape: Chart‑stop at the swing low preceding the entry, TP1 at 1.5R, runner trail using a chandelier exit (ATR×3) from the high‑water mark. Regime hint: VIX between 12‑22, avoiding the first and last 30 minutes of the session. Novelty claim (why not already in the registry): While BULLISH_RECLAIM_RIDE_THE_RIBBON focuses on price reclaiming the ribbon after a dip, this setup requires a fresh ribbon flip with a volume expansion filter and a strict midday window, making it structurally distinct. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-midday-ribbon-flip-long-free-agen --task-id 2791c2d5-bf09-4e9f-bd19-5bacf148fac3 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
