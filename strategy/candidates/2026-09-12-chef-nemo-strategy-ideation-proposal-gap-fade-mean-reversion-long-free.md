# CANDIDATE: strategy-ideation-proposal-gap-fade-mean-reversion-long-free

**Filed:** 2026-09-12
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'GAP_FADE_MEAN_REVERSION_LONG' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: Large gap‑down openings often reverse intraday when VIX is elevated and price fills a meaningful portion of the gap quickly. Entry rule: If the open gaps down >0.5% from the prior close AND the current VIX > 20 AND price retraces upward to fill at least 50% of the gap size within the first 30 minutes (i.e., reaches open + 0.5 × gap), enter long at the close of the bar that achieves that 50% fill. Exit shape: Stop placed at the low of the gap bar (or the open price), target set to fill 100% of the gap (i.e., prior close) or 1.5R whichever is smaller; if price passes the prior close, trail the remainder with a chandelier exit (ATR*2). Regime hint: Best during high‑VIX (>20) environments after news‑driven gaps; avoid low‑VIX (<12) regimes where gaps tend to persist. Novelty claim (why not already in the registry): Uses a gap‑fade mechanism with a VIX filter and a specific 50% gap‑fill timing rule; the registry contains GAP_AND_GO (continuation) but not a mean‑reversion gap fade with VIX condition, making this distinct. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-gap-fade-mean-reversion-long-free --task-id a7747a3e-fcfa-456d-8820-a5518ce17866 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
