# CANDIDATE: strategy-ideation-proposal-midday-vwap-retest-with-rsi-diver

**Filed:** 2026-09-12
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'MIDDAY_VWAP_RETEST_WITH_RSI_DIVERGENCE_SHORT' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: After the morning rally, a retest of VWAP accompanied by bearish RSI divergence on the 5‑min chart often precedes a short‑term reversal in the early afternoon. Entry rule: Between 11:00‑13:00 ET, if price touches VWAP (±0.1% tolerance) and the RSI(14) makes a lower high while price makes a higher high (bearish divergence) on the same 5‑min bar, enter short at the close of that bar. Exit shape: Stop placed above the recent swing high (chart‑stop), take profit at 1R, then trail remaining with a premium‑stop of 10% of the ATR from the highest high since entry. Regime hint: Works when VIX is moderate (15‑25) and the morning session shows a clear upward thrust (price > VWAP + 0.5% at 10:30); avoid in low‑VIX (<12) choppy markets. Novelty claim (why not already in the registry): No existing setup combines a timed VWAP retest window with intraday RSI divergence; the closest is VWAP_RECLAIM_FAILED_BREAK which looks at price failing to reclaim VWAP after a break, but does not incorporate RSI divergence or a specific midday window. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-midday-vwap-retest-with-rsi-diver --task-id 35c133d3-4927-4c5d-8349-6bd68bf0a98d --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
