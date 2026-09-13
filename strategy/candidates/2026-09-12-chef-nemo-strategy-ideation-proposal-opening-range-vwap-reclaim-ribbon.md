# CANDIDATE: strategy-ideation-proposal-opening-range-vwap-reclaim-ribbon

**Filed:** 2026-09-12
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'OPENING_RANGE_VWAP_RECLAIM_RIBBON_ALIGN' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: Price that opens outside the opening range and then reclaims VWAP with an aligned EMA ribbon signals institutional participation and a mean‑reversion edge. Entry rule: If today's opening price is outside the pre‑market defined opening range (high/low of first 5 min) AND price crosses VWAP from below to above (long) or above to below (short) within the first 30 minutes AND the 8‑,21‑,55‑period EMA ribbon is all sloping same direction (all >0 slope for long, all <0 for short) THEN enter at the close of the bar that caused the VWAP cross. Exit shape: Initial stop at the opposite side of the opening range; TP1 at 1R; remaining position trailed by a chandelier exit (ATR*3) or chart‑stop at the nearest swing point. Regime hint: Best when VIX < 18 (low volatility) and time between 09:30‑10:30; avoid choppy sessions where the ribbon is flat. Novelty claim (why not already in the registry): Similar to ORB_RETEST_LONG and VWAP_CONTINUATION but adds the ribbon‑alignment filter and the requirement to open outside the range, which is absent from any existing setup. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-opening-range-vwap-reclaim-ribbon --task-id 87d90b11-93f9-439b-94c9-6c2ec91e02df --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
