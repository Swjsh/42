# CANDIDATE: strategy-ideation-proposal-vwap-opening-range-rsi-divergence

**Filed:** 2026-09-15
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'VWAP_OPENING_RANGE_RSI_DIVERGENCE_LONG' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: When price opens outside the opening range, trades above VWAP, and shows bullish hidden RSI divergence, an intraday long edge exists. Entry rule: If the first 5‑min bar after 09:30 closes above the opening range high, price is above VWAP, and RSI(14) makes a higher low while price makes a lower low on the same bar, enter long at the bar’s close. Exit shape: Chart‑stop at the opening range low (structure invalidation), TP1 at 1.5R, runner trailed 15% off the high‑water mark using a chandelier exit. Regime hint: VIX < 18, time 09:30‑10:30, ribbon bullish (EMA9 > EMA21 > EMA55). Novelty claim (why not already in the registry): Closest existing setups are ORB_RETEST_LONG and VWAP_CONTINUATION; this adds the opening‑range‑high break, VWAP filter, and bullish hidden RSI divergence condition, which are not combined in any registry entry. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-vwap-opening-range-rsi-divergence --task-id 269d6106-8a26-4db8-93d5-064bb6eb8ede --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
