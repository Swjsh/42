# CANDIDATE: strategy-ideation-proposal-rsi-bullish-divergence-vwap-long-

**Filed:** 2026-09-12
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'RSI_BULLISH_DIVERGENCE_VWAP_LONG' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: Bullish RSI divergence combined with price above VWAP indicates weakening downward momentum and a likely bounce. Entry rule: Identify a bullish RSI(14) divergence: price makes a lower low while RSI makes a higher low over the last 3‑5 bars. Simultaneously, price must be above the intraday VWAP. Enter long at the close of the bar where the RSI higher low is confirmed (the bar forming the higher low), provided it is above VWAP. Exit shape: Stop at the recent swing low (low of the divergence low bar) or 0.5% below entry, target 1.5R, then trail with a 12% trailing stop from the high‑water mark. Regime hint: Effective in choppy, moderate‑volume periods and when VIX is in the 12‑22 range; avoid strongly trending days where divergences often fail. Novelty claim (why not already in the registry): Pairs a classic bullish RSI divergence with an intraday VWAP filter; the registry lists RSI_DIVERGENCE_BULL_WATCHER as a gate/watch but not an entry rule that requires both divergence and VWAP alignment, so this combination is novel. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-rsi-bullish-divergence-vwap-long- --task-id 000cc722-91ad-4b0e-9b5e-39dbc837c0d5 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
