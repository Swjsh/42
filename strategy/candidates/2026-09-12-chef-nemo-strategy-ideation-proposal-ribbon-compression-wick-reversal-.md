# CANDIDATE: strategy-ideation-proposal-ribbon-compression-wick-reversal-

**Filed:** 2026-09-12
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'RIBBON_COMPRESSION_WICK_REVERSAL' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: Reverse tight EMA ribbon compressions (<0.15% width) showing rejection wicks >60% of bar range, anticipating mean reversion to ribbon median. Entry rule: Long: Ribbon width (EMA55-EMA8) < 0.15% of price for 3 consecutive 5m bars AND bar closes above ribbon with lower wick >60% of bar range AND volume > 1.2x 20-bar avg volume; Short: Ribbon width <0.15% AND bar closes below ribbon with upper wick >60% AND volume >1.2x 20-bar avg volume. Exit shape: Stop at opposite ribbon edge (long stop below EMA8, short stop above EMA55); TP at 1.5x risk to ribbon median; exit if ribbon re-expands >0.3% width. Regime hint: VIX 16-26 (avoid low-VIX noise and high-VIX trend failures); 10:00-14:00 EST to exclude opening/gap-driven moves and late-day drift. Novelty claim (why not already in the registry): Unlike BOLLINGER_SQUEEZE (uses BB width, not EMA ribbon) and BULLISH_RECLAIM_RIDE_THE_RIBBON (trades ribbon reclamation, not compression reversals); no killed list equivalent exists for EMA ribbon compression wick reversals. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-ribbon-compression-wick-reversal- --task-id b6a7a028-2d68-4144-9ea2-9b682f67c903 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
