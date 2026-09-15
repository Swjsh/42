# CANDIDATE: strategy-ideation-proposal-rsi-divergence-market-structure-s

**Filed:** 2026-09-15
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'RSI_DIVERGENCE_MARKET_STRUCTURE_SHORT' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: Bearish RSI divergence combined with a downside market structure break of structure, while price is below VWAP and the ribbon is bearish, signals a short‑side edge. Entry rule: If RSI(14) makes a lower high while price makes a higher high (bearish divergence) AND a market structure BOS (break of prior low) occurs AND price < VWAP AND 9‑EMA < 20‑EMA < 50‑EMA (bearish ribbon), enter short at the close of the BOS bar. Exit shape: Stop at the swing high preceding entry (or 1 ATR above entry); target at 1.5 × ATR or trail using a chandelier exit (ATR × 3). Regime hint: Optimal when VIX > 20 and during midday hours (10:30‑14:30) when intraday trends are prone to reversal; avoid the first and last 30 minutes. Novelty claim (why not already in the registry): Distinct from RSI_DIVERGENCE_BULL_WATCHER (bullish only) and BEARISH_REJECTION_RIDE_THE_RIBBON (level‑based rejection); this combines RSI divergence, market structure BOS, VWAP filter, and bearish ribbon alignment. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-rsi-divergence-market-structure-s --task-id de1b1eb5-b022-438e-80a0-d465509448eb --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
