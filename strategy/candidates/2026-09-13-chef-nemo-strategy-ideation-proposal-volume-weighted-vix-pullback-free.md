# CANDIDATE: strategy-ideation-proposal-volume-weighted-vix-pullback-free

**Filed:** 2026-09-13
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'VOLUME_WEIGHTED_VIX_PULLBACK' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: When VIX declines intraday while price pulls back to the VWAP on declining volume, the pullback often finds support/resistance and resumes the prior trend. Entry rule: Calculate 5‑period VWAP; if VIX (1‑min) drops >0.5 points over the last 10 min AND price retraces to within 0.2×ATR of the VWAP on volume < 0.8× average 20‑period volume, then enter in the direction of the prevailing higher‑timeframe trend (determined by 30‑min EMA stack: long if 30‑min 9‑EMA > 21‑EMA, short otherwise) at the close of the bar that meets the conditions. Exit shape: Stop at the recent swing point opposite the entry direction (chart‑stop); target at 1.5×ATR; if price reaches 1×ATR, switch to a chandelier trail (1.5×ATR). Regime hint: Works when VIX is between 14 and 25 and during the 10:00‑12:00 EST window when intraday mean‑reversion cycles are common. Novelty claim (why not already in the registry): While VIX_REGIME_DAYSIDE and RSI_DIVERGENCE_BULL_WATCHER exist, none combine intraday VIX decline, VWAP pullback, and volume‑drying filter to enter in the direction of the higher‑timeframe EMA trend. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-volume-weighted-vix-pullback-free --task-id 2eb30035-1d25-4a41-ab0d-b39d71b2c17a --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
