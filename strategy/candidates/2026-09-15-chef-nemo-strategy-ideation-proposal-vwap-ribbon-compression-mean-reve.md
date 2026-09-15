# CANDIDATE: strategy-ideation-proposal-vwap-ribbon-compression-mean-reve

**Filed:** 2026-09-15
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'VWAP_RIBBON_COMPRESSION_MEAN_REVERT_LONG' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: When price deviates sharply from VWAP while the EMA ribbon compresses, mean reversion to VWAP offers a long edge. Entry rule: If |price – VWAP| > 1.5×ATR(14) AND the absolute difference between EMA9 and EMA55 is < 0.5×ATR(14) AND price is below VWAP, enter long at the bar’s close. Exit shape: Chart‑stop at the most recent swing low (HH/HL invalidation), TP1 at VWAP (mean‑reversion target), runner trailed using a chandelier exit. Regime hint: VIX between 15‑25, time 11:30‑13:30, market choppy (no clear HH/LL sequence on the 30‑min chart). Novelty claim (why not already in the registry): Nearest is VWAP_RECLAIM_FAILED_BREAK; this adds a ribbon‑compression condition and a fixed ATR‑based deviation threshold, which are not present together in any registry entry. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-vwap-ribbon-compression-mean-reve --task-id 82b1ac99-28c7-46cf-9918-58779d0a4ff9 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
