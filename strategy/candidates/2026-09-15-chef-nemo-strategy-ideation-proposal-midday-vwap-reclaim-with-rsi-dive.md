# CANDIDATE: strategy-ideation-proposal-midday-vwap-reclaim-with-rsi-dive

**Filed:** 2026-09-15
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'MIDDAY_VWAP_RECLAIM_WITH_RSI_DIVERGENCE' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: A bullish RSI divergence on a VWAP pullback after 11:30 hints at trend resumption. Entry rule: After 11:30, if price touches VWAP within ±0.2%, RSI(14) makes a higher low while price makes a lower low, and the EMA ribbon (8,21,55) is stacked bullish, go long. Exit shape: Chart‑stop at the most recent swing low (HH/HL invalidation), TP1 at 2×R, runner trailed using a chandelier exit. Regime hint: VIX between 12‑22, ADX < 20 (choppy) but EMA ribbon still bullish. Novelty claim (why not already in the registry): Closest to VWAP_RECLAIM_FAILED_BREAK (a short on failed break); this is a long that adds a bullish RSI divergence condition and requires the EMA ribbon to be bullish. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-midday-vwap-reclaim-with-rsi-dive --task-id fa501799-21f0-4333-a626-011fc2595116 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
