# CANDIDATE: strategy-ideation-proposal-volume-weighted-level-bounce-free

**Filed:** 2026-09-12
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'VOLUME_WEIGHTED_LEVEL_BOUNCE' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: Bounce from prior session high/low on declining volume with bullish/bearish rejection candles, exploiting weak liquidity at key levels. Entry rule: Long: Price within 0.1% of prior day low AND volume on approach bar <80% of 20-bar avg volume AND touching bar has close > open AND lower wick >50% of bar range AND close > prior day low; Short: Price within 0.1% of prior day high AND volume on approach bar <80% of 20-bar avg volume AND touching bar has close < open AND upper wick >50% of bar range AND close < prior day high. Exit shape: Stop 0.2% beyond level (long stop below prior day low, short stop above prior day high); TP at 1.5x risk to opposite session level (e.g., prior day high for long from prior day low); exit if price re-tests level with closing penetration. Regime hint: VIX < 28; 10:00-14:30 EST (avoid first/last 30min); exclude days with gap >0.5% at open to reduce noise. Novelty claim (why not already in the registry): Differs from NAMED_LEVEL_SECOND_TEST (which likely tests levels after initial break) by requiring declining volume on approach and rejection candle on first touch; distinct from LEVEL_SWEEP_SNIPE (which targets stop hunts) by fading weak liquidity rather than chasing sweeps. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-volume-weighted-level-bounce-free --task-id d5f291e3-9424-4207-8fca-44a91ddd4c9d --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
