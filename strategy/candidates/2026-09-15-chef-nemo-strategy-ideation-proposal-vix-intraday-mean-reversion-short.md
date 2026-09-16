# CANDIDATE: strategy-ideation-proposal-vix-intraday-mean-reversion-short

**Filed:** 2026-09-15
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'VIX_INTRADAY_MEAN_REVERSION_SHORT' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: Short‑term spikes in intraday VIX often revert to its 30‑minute VWAP, and SPY tends to exhibit bearish price action during such spikes, offering a short mean‑reversion edge. Entry rule: Calculate the 30‑minute VWAP of VIX (using 5‑minute bars). When the current VIX exceeds its 30‑min VWAP by >15% and the concurrent 5‑minute SPY bar closes lower than its open with an upper wick ≥60% of the bar’s total range, enter short at the close of that SPY bar. Exit shape: Stop placed above the high of the entry bar; target 1 at a 0.5% move in SPY (≈1R) or when VIX returns to within 5% of its 30‑min VWAP, whichever occurs first; remaining position can be trailed with a 8‑bar chandelier exit on SPY. Regime hint: Works when overall VIX level is between 14‑28 (avoid extreme low/high) and during regular trading hours 09:30‑15:45 ET; avoid during major news spikes that can cause sustained VIX elevation. Novelty claim (why not already in the registry): No existing strategy uses intraday VIX deviation as a trigger for SPY short entries; the closest is VIX_REGIME_DAYSIDE which filters by daily VIX levels, not intraday mean‑reversion. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-vix-intraday-mean-reversion-short --task-id d1e6fd09-49ae-43ae-8000-2c0379941059 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
