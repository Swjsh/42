# CANDIDATE: strategy-ideation-proposal-vol-compression-rsi-extreme-short

**Filed:** 2026-09-12
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'VOL_COMPRESSION_RSI_EXTREME_SHORT' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: In elevated volatility (VIX>25), a Bollinger Band squeeze combined with RSI>70 at the upper band and bearish ribbon alignment signals a short opportunity for mean reversion. Entry rule: VIX > 25, Bollinger Band width (upper-lower)/middle below its 20-period average (volatility compression), RSI(14) > 70, high of current bar >= upper Bollinger Band, ribbon (8,13,21 EMA) bearish (8<13<21), enter short at the open of the next bar. Exit shape: Stop above the upper Bollinger Band or the high of the entry bar (whichever is higher), initial target at 1.0R, then trail runner using a chandelier exit (3x ATR(22)) from the highest high since entry. Regime hint: Trade only between 9:30 ET and 12:00 ET to avoid afternoon low volatility, avoid FOMC days (but no direct news primitive, so rely on VIX and time). Novelty claim (why not already in the registry): Closest existing setup is BOLLINGER_SQUEEZE, which typically enters on the breakout of the squeeze in the direction of the trend; this strategy fades the extreme (short at upper band) during the squeeze, requiring RSI>70 and bearish ribbon, which BOLLINGER_SQUEEZE does not include. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-vol-compression-rsi-extreme-short --task-id ccb19456-3239-4565-9206-5069f43ec449 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
