# CANDIDATE: strategy-ideation-proposal-rsi-extreme-vwap-divergence-free-

**Filed:** 2026-09-13
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'RSI_EXTREME_VWAP_DIVERGENCE' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: When price deviates significantly from VWAP while RSI reaches extreme levels (>80 for short, <20 for long), the deviation tends to revert, providing a mean‑reversion trade. Entry rule: Compute VWAP and RSI(14). If RSI > 80 AND (close‑VWAP)/VWAP > 0.003 (price >0.3% above VWAP), enter short at the close of that bar. If RSI < 20 AND (VWAP‑close)/VWAP > 0.003 (price >0.3% below VWAP), enter long at the close. Require the bar’s close to be opposite the deviation (short: close < open; long: close > open) to confirm a reversal candle. Exit shape: Stop placed beyond the recent swing point (short: above the high of the last 2 bars; long: below the low of the last 2 bars). Target set to return to VWAP (price crossing VWAP) or 1:1R, whichever comes first; after hitting VWAP, optionally trail runner using a premium‑stop % (e.g., 0.5% of price). Regime hint: Works best in choppy, low‑trend conditions where VIX is moderate (15‑25) and price frequently oscillates around VWAP. Avoid strong trending days where the ribbon shows a clear stack (EMA8>EMA13>EMA21 for longs or the reverse for shorts). Novelty claim (why not already in the registry): No existing strategy combines RSI extremes with VWAP deviation as the entry trigger; the closest is RSI_DIVERGENCE_BULL_WATCHER, which uses price‑RSI divergence, not VWAP distance, making this candidate distinct. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-rsi-extreme-vwap-divergence-free- --task-id 7b90128a-e3a9-41c7-bd65-77ed32f6c514 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
