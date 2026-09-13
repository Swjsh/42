# CANDIDATE: strategy-ideation-proposal-volatility-contraction-vwap-recla

**Filed:** 2026-09-13
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'VOLATILITY_CONTRACTION_VWAP_RECLAIM' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: After a volatility contraction (ATR below its 20‑period mean) where price hovers near VWAP, a breakout above VWAP on expanding volume signals a trend resumption, offering a long entry with a volatility‑based stop. Entry rule: Compute ATR(14) and its 20‑bar MA. If ATR < 0.8×ATR_MA for ≥3 consecutive bars AND |close‑VWAP|/VWAP < 0.001 during that contraction, then on the next bar where close > VWAP AND volume > 1.5×average volume of prior 20 bars, enter long at the close of that breakout bar. Exit shape: Initial stop at the lowest low of the contraction period (or 1.5×ATR below entry). Target using a chandelier exit (ATR×3) after achieving 1R profit; consider TP1 at 1.5R. Regime hint: Best in low VIX (<15) and during midday (10:30‑14:30) when volatility contractions are more likely to resolve. Avoid the first and last 30 minutes of the session where unrelated volatility spikes occur. Novelty claim (why not already in the registry): Differs from BOLLINGER_SQUEEZE, which uses Bollinger Band width as the compression signal; this candidate uses ATR contraction plus proximity to VWAP, combined with a volume‑expanding VWAP reclaim—a unique combination not in the registry. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-volatility-contraction-vwap-recla --task-id ec25063f-43b5-44bc-9c1d-b9d87b8944fb --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
