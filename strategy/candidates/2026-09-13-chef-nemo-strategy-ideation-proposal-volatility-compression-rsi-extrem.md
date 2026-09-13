# CANDIDATE: strategy-ideation-proposal-volatility-compression-rsi-extrem

**Filed:** 2026-09-13
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'VOLATILITY_COMPRESSION_RSI_EXTREME_BREAKOUT' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: After a period of ATR‑based volatility contraction, an RSI extreme (>80 or <20) combined with a break of the prior day’s high/low on increased volume signals a short‑term continuation move. Entry rule: Compute 20‑period ATR; if current ATR is below its 20‑period low (volatility compression) AND RSI(14) > 80 (or <20 for short) AND price breaks above the prior day’s high with volume > 1.5× average 20‑period volume, go long at the break bar close; for short, mirror with RSI<20 and break below prior day’s low. Exit shape: Initial stop at the midpoint of the compression range (the low‑high of that period); target at 2×ATR; if price reaches 1.5×ATR, switch to a chandelier trail (2×ATR) to let a runner develop. Regime hint: Ideal when VIX is between 12 and 22 (moderate) and during the 10:30‑13:30 EST window when intraday momentum tends to persist. Novelty claim (why not already in the registry): While BOLLINGER_SQUEEZE looks at price bands, this uses ATR contraction and RSI extremes with prior‑day level break and volume filter; no existing setup combines volatility compression (ATR) with RSI extreme and prior‑day high/low break. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-volatility-compression-rsi-extrem --task-id f9bd52db-1f68-4920-9377-fa3601a9775e --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
