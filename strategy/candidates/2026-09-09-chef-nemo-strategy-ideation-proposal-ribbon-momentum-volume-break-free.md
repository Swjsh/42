# CANDIDATE: strategy-ideation-proposal-ribbon-momentum-volume-break-free

**Filed:** 2026-09-09
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'RIBBON_MOMENTUM_VOLUME_BREAK' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: A bullish EMA ribbon alignment combined with a break above the 20‑EMA on expanding volume signals short‑term momentum continuation. Entry rule: When 9‑EMA > 20‑EMA > 50‑EMA (bullish ribbon) and price closes above the 20‑EMA with a bullish bar (close > open) and volume > 1.5× the average volume of the prior 20 bars, enter long at the close of that bar. Exit shape: Stop at the low of the breakout bar (or 0.5×ATR below entry), target at 2R, then trail using a premium‑stop % (e.g., 15% of ATR) or stop if price closes below the 9‑EMA. Regime hint: Works in trending regimes with VIX between 12‑22 and after 10:00 EST to avoid opening‑range noise. Novelty claim (why not already in the registry): Similar to BULLISH_RECLAIM_RIDE_THE_RIBBON but that setup focuses on reclaiming the ribbon after a rejection; this candidate requires a fresh break of the 20‑EMA with volume expansion, making the logic and entry conditions different. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-ribbon-momentum-volume-break-free --task-id 574e823e-12e7-41f2-8202-7566901936fa --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
