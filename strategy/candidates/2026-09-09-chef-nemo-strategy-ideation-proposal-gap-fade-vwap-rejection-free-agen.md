# CANDIDATE: strategy-ideation-proposal-gap-fade-vwap-rejection-free-agen

**Filed:** 2026-09-09
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'GAP_FADE_VWAP_REJECTION' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: A gap up that fails to hold above VWAP in the first 20 minutes indicates fading momentum and a likely mean‑reversion short. Entry rule: If the gap up from prior close to today’s open exceeds 0.25% and price does not close above VWAP by the 20‑minute bar (close < VWAP) with a bearish close (close < open), enter short at the close of that bar. Exit shape: Stop at the high of the gap bar (or 0.5×ATR above entry), target at 1.5R, then trail using a chandelier exit (ATR×3) or stop if price moves back above VWAP with a bullish close. Regime hint: Most effective when VIX > 18 (elevated volatility) and time between 09:30–10:00 EST. Novelty claim (why not already in the registry): Unlike GAP_AND_GO (which trades gap continuation) and VWAP_RECLAIM_FAILED_BREAK (which looks for a failed break after a gap), this candidate specifically fades gaps that fail to reclaim VWAP, a distinct short‑bias condition. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-gap-fade-vwap-rejection-free-agen --task-id 898c44fc-4465-43fa-9cac-941963054fa9 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
