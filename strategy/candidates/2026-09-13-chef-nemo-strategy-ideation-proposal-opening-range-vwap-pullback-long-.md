# CANDIDATE: strategy-ideation-proposal-opening-range-vwap-pullback-long-

**Filed:** 2026-09-13
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'OPENING_RANGE_VWAP_PULLBACK_LONG' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: After the first 30‑minute opening range, a pronounced move away from VWAP that subsequently pulls back to VWAP with bullish ribbon alignment offers a high‑probability mean‑reversion long. Entry rule: Calculate the opening range high/low from 09:30‑10:00 EST. If price moves >0.4% above ORH or below ORL and then closes within 0.1% of VWAP on a bullish candle (close>open) while the 5‑period EMA is above the 8‑period EMA and the 8‑period EMA above the 13‑period EMA (ribbon bullish), enter long at the close of that candle. Exit shape: Initial stop at the opposite side of the opening range (ORL for longs above ORH, ORH for longs below ORL); target 1.5× risk or trail with 12% of ATR chandelier exit. Regime hint: Works best when VIX is between 12‑22 and the session is not a strong trend day (price stays within 1.5× opening range width after first hour). Novelty claim (why not already in the registry): Closest existing setup is VWAP_RECLAIM_FAILED_BREAK, which looks for a failed break of VWAP after a move away. This candidate adds the opening range context and requires a bullish ribbon EMA stack, making the entry more selective and timing‑specific. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-opening-range-vwap-pullback-long- --task-id 857a1d78-47b5-428b-8a83-eaeb0f6b17ba --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
