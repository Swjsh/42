# CANDIDATE: strategy-ideation-proposal-ribbon-convergence-rsi-reverse-fr

**Filed:** 2026-09-14
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'RIBBON_CONVERGENCE_RSI_REVERSE' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: A tightly coiled EMA ribbon combined with an extreme RSI test at the ribbon’s edge often precedes a reversal. Entry rule: When (EMA55 - EMA8) < 0.3 * ATR(14) (ribbon tight) and price touches EMA8 or EMA55 within 0.1*ATR and ((touch EMA8 and RSI(14) < 30) or (touch EMA55 and RSI(14) > 70)) and the bar shows an engulfing reversal (bullish engulfing when touching EMA8, bearish engulfing when touching EMA55), go long on EMA8 touch or short on EMA55 touch. Exit shape: Chart‑stop at the opposite outer EMA (stop at EMA55 for longs, EMA8 for shorts), TP1 at 1.5×R, runner trail using a chandelier exit. Regime hint: VIX between 14‑22, time 10:00‑14:00, price within prior day’s high‑low (chop‑neutral). Novelty claim (why not already in the registry): Unlike VWAP_CONTINUATION which relies on a VWAP pullback, this uses ribbon compression, RSI extremes, and engulfing reversals at the ribbon’s edges, a unique combination not present in the registry. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-ribbon-convergence-rsi-reverse-fr --task-id 9addd754-a7b3-4394-a401-b434ed4d3129 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
