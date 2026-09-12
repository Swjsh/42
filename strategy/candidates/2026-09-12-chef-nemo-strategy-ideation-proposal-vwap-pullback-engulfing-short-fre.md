# CANDIDATE: strategy-ideation-proposal-vwap-pullback-engulfing-short-fre

**Filed:** 2026-09-12
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'VWAP_PULLBACK_ENGULFING_SHORT' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: After an extended bullish move above VWAP, a bearish engulfing candle that retraces to VWAP signals a short‑term reversal. Entry rule: If price has been > VWAP + 0.3% for at least three consecutive 5‑min bars and the 8‑EMA is above the 21‑EMA (bullish ribbon), then look for a bearish engulfing candle (current close < prior open and current open > prior close) whose low touches or goes below VWAP; enter short at the close of that engulfing bar. Exit shape: Stop = highest high of the last three bars (or prior swing high); target = 1.5 × risk or exit when price re‑crosses VWAP to the upside; optionally trail using premium‑stop % (e.g., 0.2%) after 1R profit. Regime hint: Effective in moderate VIX (15‑25) and mid‑morning (10:00‑11:30 ET) when intraday trends tend to pause; avoid in strong trending days where price stays > VWAP + 0.5% for >4 hours. Novelty claim (why not already in the registry): Nearest is VWAP_RECLAIM_FAILED_BREAK, which trades a failed break of VWAP. This candidate requires a prior extended bullish stretch, a specific bearish engulfing pattern, and uses VWAP as a pullback trigger rather than a break failure, making the entry conditions distinct. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-vwap-pullback-engulfing-short-fre --task-id 195ad52a-6639-42f0-9fbd-4e5f5fe33e98 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
