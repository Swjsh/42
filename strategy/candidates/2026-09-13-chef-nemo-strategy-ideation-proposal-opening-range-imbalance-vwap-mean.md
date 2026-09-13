# CANDIDATE: strategy-ideation-proposal-opening-range-imbalance-vwap-mean

**Filed:** 2026-09-13
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'OPENING_RANGE_IMBALANCE_VWAP_MEANREV_LONG' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: When price opens beyond the opening range and VWAP lies on the opposite side, the market tends to revert to VWAP as liquidity rebalances, offering a long edge if the imbalance is to the downside. Entry rule: Calculate the opening range (first 30‑min high‑low). If the 30‑min close is below the opening range low (downside imbalance) AND the VWAP at that time is above the opening range mid‑point AND the 5‑EMA is above the 20‑EMA (ribbon bullish alignment), enter long at the close of the 30‑min bar. Exit shape: Stop at the opening range low (chart‑stop); target at 1.5×ATR above entry or at the day’s VWAP, whichever is reached first; if price exceeds VWAP, trail with a 10 % premium‑stop. Regime hint: Works best when VIX < 15 (low volatility) and after 10:00 EST to avoid early‑morning noise. Novelty claim (why not already in the registry): Unlike ORB_RETEST_LONG which buys on a retest of the opening range level, this setup enters on the initial imbalance condition and uses VWAP‑ribbon confluence as the trigger; no existing setup combines opening‑range imbalance with VWAP‑above‑midpoint and EMA ribbon alignment. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-opening-range-imbalance-vwap-mean --task-id 72be47a4-828b-4e40-abdc-92deaacfba04 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
