# CANDIDATE: strategy-ideation-proposal-intraday-bos-ribbon-alignment-fre

**Filed:** 2026-09-13
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'INTRADAY_BOS_RIBBON_ALIGNMENT' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: A shift in market structure (break of structure) on the 15‑min chart, when aligned with an upward‑sloping EMA ribbon and price above VWAP, indicates a high‑probability intraday continuation. Entry rule: On the 15‑min chart, detect a bullish BOS (higher high > prior higher high and higher low > prior higher low) OR a bearish CHoCH (lower low < prior lower low and lower high < prior lower high). If the BOS/CHoCH bar closes above VWAP and the 9‑EMA > 21‑EMA > 55‑EMA (ribbon bullish alignment) for long (or the reverse for short), enter at the close of that bar. Exit shape: Stop at the most recent swing low/high that was broken (chart‑stop); target at 2×ATR or at the next named resistance/support level; if price reaches 1.5×ATR, switch to a premium‑stop trailing at 12 %. Regime hint: Effective when VIX < 18 and during the 11:00‑14:00 EST window when intraday trends tend to develop. Novelty claim (why not already in the registry): No existing setup uses a 15‑min BOS/CHoCH signal combined with EMA ribbon stacking and VWAP filter; the closest is TRENDLINE_BREAK_VOLUME or STRUCTURE_VETO_DIR_VS_TREND, but those rely on trendlines or structure veto, not a pure BOS/CHoCH with ribbon alignment. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-intraday-bos-ribbon-alignment-fre --task-id 0d1ea941-bf8e-44c4-bc00-c4b165a18ff2 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
