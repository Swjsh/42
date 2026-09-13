# CANDIDATE: strategy-ideation-proposal-vix1d-contango-pullback-long-free

**Filed:** 2026-09-12
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'VIX1D_CONTANGO_PULLBACK_LONG' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: When the near‑term VIX (VIX1D) is in contango relative to VIX (VIX1D/VIX <0.95) and SPY pulls back to the 20‑EMA, the pullback often finds support, giving a long edge. Entry rule: If VIX1D/VIX ratio <0.95 for the current bar (contango) AND price closes below the 20‑EMA but above the 50‑EMA (a shallow pullback) AND the 8‑EMA is above the 21‑EMA (short‑term bullish ribbon), then enter long at the close of the pullback bar. Exit shape: Stop placed below the low of the pullback bar; TP1 at 1.5R; runner trailed by 10% off highest close since entry or chart‑stop at the prior swing high. Regime hint: Works best when VIX is between 12‑20 and time is after 10:30 (avoid first 30 min noise); avoid periods when VIX1D/VIX >1.05 (backwardation) as market expects near‑term volatility spikes. Novelty claim (why not already in the registry): No existing setup uses the VIX1D/VIX ratio as a filter; the closest is VIX_REGIME_DAYSIDE, which looks at VIX level alone, not the term‑structure relationship, making this approach distinct. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-vix1d-contango-pullback-long-free --task-id 86b638aa-b450-4a9d-b8e4-02a9b3fef660 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
