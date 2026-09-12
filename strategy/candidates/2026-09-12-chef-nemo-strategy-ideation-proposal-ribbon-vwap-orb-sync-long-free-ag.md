# CANDIDATE: strategy-ideation-proposal-ribbon-vwap-orb-sync-long-free-ag

**Filed:** 2026-09-12
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'RIBBON_VWAP_ORB_SYNC_LONG' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: When price opens above the prior day's high and holds above VWAP with a bullish ribbon alignment, a pullback to VWAP on diminishing volume offers a high-probability long entry. Entry rule: Prior day's high is broken in the first 15 minutes (opening range high > prior day's high), current price above VWAP, ribbon (8,13,21 EMA) bullish (8>13>21), price pulls back to touch VWAP (within 0.1% of VWAP) with volume on the pullback bar below the 5-bar average volume, enter long at the close of the bar that closes above VWAP. Exit shape: Initial stop below the swing low of the pullback (or opening range low if closer), target at 1.5R, then trail runner using a 10% trailing stop from the highest high since entry. Regime hint: VIX < 20, time between 9:45 ET and 11:30 ET to avoid first 15 min noise and midday chop. Novelty claim (why not already in the registry): Closest existing setup is ORB_RETEST_LONG, which uses the opening range level for retest; this strategy uses VWAP as dynamic support during the pullback, requires bullish ribbon alignment, and filters by diminishing volume on the pullback, which ORB_RETEST_LONG does not incorporate. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-ribbon-vwap-orb-sync-long-free-ag --task-id 493c3402-6bf3-4b65-a188-adb38cb3fbb5 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
