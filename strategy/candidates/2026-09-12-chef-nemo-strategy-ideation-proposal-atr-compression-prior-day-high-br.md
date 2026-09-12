# CANDIDATE: strategy-ideation-proposal-atr-compression-prior-day-high-br

**Filed:** 2026-09-12
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'ATR_COMPRESSION_PRIOR_DAY_HIGH_BREAK' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: After a period of low volatility (ATR contraction), a break above the prior day's high with a strong close signals imminent upward expansion. Entry rule: Calculate ATR(5). If current ATR(5) is below its lowest value of the past 20 periods (contraction) AND price closes above the prior day's high AND the close lies in the upper 30% of the bar's range (strong close), then go long at the close of that bar. Exit shape: Stop at the low of the breakout bar (or prior day's low), target 1.5R, then trail the remainder with a 10% trailing stop from the high‑water mark. Regime hint: Effective across VIX levels but especially when VIX is not extremely low (<10) to avoid false breakouts; avoid major news windows (FOMC, earnings) where volatility spikes unpredictably. Novelty claim (why not already in the registry): Uses ATR contraction as a volatility filter together with a prior‑day‑high break and close‑quality condition; the registry includes BOLLINGER_SQUEEZE (Band width) but not ATR‑based contraction plus prior‑day‑high break, making this distinct. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-atr-compression-prior-day-high-br --task-id e271682b-fe5a-4220-a234-a2584d27b1c6 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
