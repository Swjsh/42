# CANDIDATE: strategy-ideation-proposal-opening-range-volume-imbalance-lo

**Filed:** 2026-09-13
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'OPENING_RANGE_VOLUME_IMBALANCE_LONG' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: When the first 30‑minute opening range shows strong buying volume bias (up‑volume ≥1.5× down‑volume) and price closes above that range’s VWAP, the intraday bias favors continuation upward. Entry rule: Calculate volume of up‑closing bars vs down‑closing bars from 09:30‑10:00. If up_volume/down_volume ≥ 1.5 AND the 10:00 bar close > VWAP(09:30‑10:00), enter long at the close of the 10:00 bar (or next bar open). Exit shape: Initial stop at the low of the opening range (or 0.5×ATR below entry). Target 1:2 risk‑reward; after 1R profit, trail runner with a chandelier exit (ATR×3). Regime hint: Best when VIX < 20 and prior day’s close is within 0.5% of the opening range (avoid large gaps). Stay clear of the first 30 min after major news releases (e.g., FOMC, CPI). Novelty claim (why not already in the registry): Differs from ORB_RETEST_LONG, which uses price retest of the opening range high/low; this candidate uses volume imbalance within the range plus a VWAP close condition, a combination not present in the registry. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-opening-range-volume-imbalance-lo --task-id 752e58ad-7454-4e36-99a0-12ecfe453576 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
