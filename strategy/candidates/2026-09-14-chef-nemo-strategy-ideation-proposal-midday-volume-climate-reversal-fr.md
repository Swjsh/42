# CANDIDATE: strategy-ideation-proposal-midday-volume-climate-reversal-fr

**Filed:** 2026-09-14
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'MIDDAY_VOLUME_CLIMATE_REVERSAL' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: A sudden drop in midday liquidity often precedes a reversal as participants step aside, allowing the opposite side to push price when volume returns. Entry rule: Between 11:30‑13:00 ET, if the 5‑minute volume falls below 0.6× the 20‑period average volume and price is within the opening range (i.e., between OR low and OR high), then wait for the first subsequent 5‑minute bar where volume > 1.2× average volume and the close is opposite to the morning bias (defined as price > VWAP at 10:30 → bullish bias, else bearish). Enter long if bias was bearish and close > VWAP, or short if bias was bullish and close < VWAP, at the close of that volume‑return bar. Exit shape: chart‑stop at the opposite side of the opening range (OR low for longs, OR high for shorts), target at 1.5R or a trailing stop of 10% off HWM Regime hint: Optimal when VIX is 14‑25 and the day is not a gap‑open > 0.5% (avoid GAP_AND_GO conditions); avoid the first and last 30 minutes Novelty claim (why not already in the registry): This setup focuses on midday volume contraction/expansion as a signal, a concept absent from the registry; the closest is VOLUME‑based filters in ENTRY_BODY_GATE_BEAR_REVAL etc., but none use a volume‑drop‑then‑surge pattern to anticipate a reversal. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-midday-volume-climate-reversal-fr --task-id 23984eca-1144-4f80-8bbd-dc9615275df2 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
