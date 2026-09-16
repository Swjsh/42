# CANDIDATE: strategy-ideation-proposal-vwap-ribbon-pullback-long-free-ag

**Filed:** 2026-09-15
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'VWAP_RIBBON_PULLBACK_LONG' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: In an intraday uptrend, price tends to find support at the VWAP when it coincides with the rising EMA ribbon, offering a high‑probability long entry. Entry rule: When SPY price is above VWAP, above the 9EMA>20EMA>50EMA ribbon (all three ascending), and the 5‑minute close pulls back to within 0.1% of VWAP while touching or crossing the 20EMA, and RSI(14) is between 45 and 55, enter long at the close of that bar. Exit shape: Initial stop at the lower 20EMA of the ribbon or 0.5% below entry, whichever is tighter; take profit 1 at 1.5R, then trail remaining position with a 10% ATR‑based chandelier exit. Regime hint: Works best when VIX < 18 and time between 09:45‑11:30 ET; avoid during FOMC windows or high‑impact news. Novelty claim (why not already in the registry): Unlike VWAP_CONTINUATION which enters on VWAP breaks in direction of trend, this setup requires a pullback to VWAP that also aligns with the EMA ribbon, a confluence not captured by any existing registry entry. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-vwap-ribbon-pullback-long-free-ag --task-id 70b30f06-ef55-4d93-b58f-f11cf682f34e --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
