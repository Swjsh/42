# CANDIDATE: strategy-ideation-proposal-gap-fade-vwap-hold-free-agent-ide

**Filed:** 2026-09-12
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'GAP_FADE_VWAP_HOLD' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: When the market gaps at the open but price returns to and holds VWAP, the gap tends to fade, providing a counter‑gap edge. Entry rule: If the opening price gaps >0.2% above the prior day’s close (gap up) or <‑0.2% below (gap down) AND price crosses back to VWAP within the first 15 minutes AND closes on the same side of VWAP for two consecutive bars (holding VWAP), then enter in the direction opposite the gap (short after gap up, long after gap down) at the close of the second holding bar. Exit shape: Stop set at the extreme of the gap (above gap‑up high for shorts, below gap‑down low for longs); TP1 at 1R; runner trailed by chandelier exit (ATR*2.5) or chart‑stop at the VWAP. Regime hint: Optimal when VIX <20 (low volatility) and the gap occurs during regular session (not overnight news); avoid days with major scheduled events (FOMC, earnings) where gaps tend to persist. Novelty claim (why not already in the registry): Existing GAP_AND_GO trades gap continuation; this is the opposite — gap fade — and adds a VWAP‑hold confirmation, which is not present in any current setup. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-gap-fade-vwap-hold-free-agent-ide --task-id f22b03ad-7cfa-442a-9f0d-90fdea474d1a --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
