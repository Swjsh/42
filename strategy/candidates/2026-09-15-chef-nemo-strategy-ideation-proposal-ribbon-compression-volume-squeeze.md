# CANDIDATE: strategy-ideation-proposal-ribbon-compression-volume-squeeze

**Filed:** 2026-09-15
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'RIBBON_COMPRESSION_VOLUME_SQUEEZE_SHORT' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: A tightly contracted EMA ribbon coupled with three consecutive bars of below‑average volume precedes a mean‑reversion move to the downside. Entry rule: When the distance between the 8 EMA and 55 EMA is less than 0.1% of price for three consecutive 5‑min bars and each bar’s volume is under 0.8× the average volume of the prior ten bars, enter short at the close of the third bar. Exit shape: Chart‑stop at the recent swing high preceding the entry, TP1 at 1R, runner trail using a chandelier exit (ATR×3) from the high‑water mark. Regime hint: VIX > 20 and time after 10:00 ET to avoid opening‑range noise. Novelty claim (why not already in the registry): BOLLINGER_SQUEEZE uses Bollinger Band width; this substitutes ribbon compression and a volume‑dry‑up filter, making the mechanics and signals distinct from any existing setup. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-ribbon-compression-volume-squeeze --task-id de84e20f-ce24-404d-8d86-21c9f4f74a61 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
