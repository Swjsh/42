# CANDIDATE: strategy-ideation-proposal-vix-intraday-mean-reversion-short

**Filed:** 2026-09-14
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'VIX_INTRADAY_MEAN_REVERSION_SHORT' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: Short‑term VIX spikes often reverse intraday, dragging SPY with them; a bearish candle coinciding with an extreme VIX reading offers a short edge. Entry rule: When the 5‑minute VIX exceeds its 20‑period EMA by 1.5× (i.e., VIX > EMA_VIX20 + 1.5×ATR_VIX) and the SPY 5‑minute bar forms a bearish engulfing candle (close < open and the prior bullish bar’s high is exceeded), enter short at the close of the engulfing bar. Exit shape: chart‑stop above the high of the engulfing bar, target at the intraday VWAP or a 1:1 risk‑reward, whichever is reached first Regime hint: Works when intraday VIX > 18 and time is between 10:00‑14:30 ET; avoid periods when VIX is flat (<12) or during FOMC windows Novelty claim (why not already in the registry): No existing setup uses intraday VIX mean‑reversion combined with a candlestick pattern; the closest is VIX_REGIME_DAYSIDE which filters by daily VIX regime, not intraday spikes, and none combine VIX with engulfing candles. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-vix-intraday-mean-reversion-short --task-id 9c1530cd-b301-4ce3-b3a1-fffda87ebd12 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
