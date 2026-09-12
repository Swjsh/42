# CANDIDATE: strategy-ideation-proposal-harmonic-rsi-confluence-free-agen

**Filed:** 2026-09-12
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'HARMONIC_RSI_CONFLUENCE' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: Harmonic pattern completion at a key Fibonacci retracement, confirmed by RSI divergence, offers a high‑probability reversal signal. Entry rule: When a harmonic pattern (e.g., Gartley, Bat) completes within 0.2% of the 0.786 or 1.272 Fibonacci retracement of the prior swing, and RSI(14) shows bullish divergence (price lower low, RSI higher low) for longs or bearish divergence for shorts, enter on the close of the confirmation candle in the reversal direction. Exit shape: Stop at the pattern invalidation point (beyond the X‑point) or 0.75R; target at 1.5R or trail using an ATR‑based stop (ATR×2). Regime hint: Optimal in low‑volatility conditions (VIX < 18) and during the afternoon session (13:00‑15:00) when harmonic patterns tend to resolve; avoid high‑VIX (>25) or major news releases. Novelty claim (why not already in the registry): The registry contains no harmonic‑pattern or RSI‑divergence based entries; the closest is RSI_DIVERGENCE_BULL_WATCHER, which uses only RSI divergence without harmonic‑pattern confluence. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-harmonic-rsi-confluence-free-agen --task-id c9c6713d-aeb5-4198-9e06-3e1b6ecfd469 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
