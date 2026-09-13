# CANDIDATE: strategy-ideation-proposal-ribbon-compression-breakout-free-

**Filed:** 2026-09-12
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'RIBBON_COMPRESSION_BREAKOUT' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: When the EMA ribbon contracts to a narrow band, a breakout in the direction of the prior higher‑timeframe trend captures a volatility‑expansion edge. Entry rule: Compute the average distance between the 8‑EMA and 55‑EMA over the last 20 bars; if this distance contracts to <0.15*ATR(14) for at least 3 consecutive bars (compression phase) AND the 200‑EMA slope (higher‑timeframe trend) is up, then enter long on the first close above the high of the compression box; for a down trend, enter short on the first close below the low of the compression box. Exit shape: Stop at the opposite edge of the compression box; TP1 at 1.5R; runner trailed by 15% off the highest/lowest close since entry (HWM/LWM). Regime hint: Works in VIX 12‑22 range; avoid periods when VIX >25 (expansion noise) or when the 200‑EMA is flat (no clear trend). Novelty claim (why not already in the registry): No existing setup uses explicit ribbon‑distance compression as a trigger; the closest is LEVEL_BREAK_FIRST_STRIKE or BOLLINGER_SQUEEZE, but those rely on price levels or Bollinger Bands, not EMA ribbon width. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-ribbon-compression-breakout-free- --task-id 6a0ef096-38ac-471b-b832-e2c10a67c2fc --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
