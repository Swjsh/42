# CANDIDATE: strategy-ideation-proposal-afternoon-vol-compression-breakou

**Filed:** 2026-09-15
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'AFTERNOON_VOL_COMPRESSION_BREAKOUT_LONG' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: A contraction of intraday volatility (low ATR) in the early afternoon often precedes a expansion‑driven breakout that can be caught with a volume‑filtered entry. Entry rule: Between 12:00‑13:30 ET, compute ATR(14) of the 5‑minute chart; when ATR falls below 0.15% of the current price for three consecutive 5‑minute bars, mark the compression zone. Enter long at the first 5‑minute close that exceeds the highest high of the compression zone by at least 0.05% and is accompanied by volume >1.5× the average 5‑minute volume of the prior 20 days. Exit shape: Stop at the lowest low of the compression zone; target 1 at 2× the ATR‑based risk, then trail with a 20‑bar highest‑high exit. Regime hint: VIX between 12‑22; avoid during lunch‑time low‑liquidity periods (12:00‑13:00) on Fridays. Novelty claim (why not already in the registry): No existing setup uses an intraday ATR compression trigger combined with a volume‑surge breakout; the closest is BOLLINGER_SQUEEZE which relies on Bollinger Bands, not ATR‑based compression and volume filter. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-afternoon-vol-compression-breakou --task-id b4b080b7-2743-4d6b-9b16-d645fe4c1c8a --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
