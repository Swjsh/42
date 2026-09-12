# CANDIDATE: strategy-ideation-proposal-orb-vwap-divergence-fade-free-age

**Filed:** 2026-09-12
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'ORB_VWAP_DIVERGENCE_FADE' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: Fade opening range breaks that fail to hold VWAP, expecting reversion to intraday value area as smart money traps breakout chasers. Entry rule: Long: ORB low broken on open with volume > 1.5x 5-bar avg volume AND price closes below VWAP within first 15m AND close > ORB low; Short: ORB high broken on open with volume > 1.5x 5-bar avg volume AND price closes above VWAP within first 15m AND close < ORB high. Exit shape: Initial stop at ORB extreme (low for long, high for short); TP1 at 1x risk to VWAP; runner trails 10% below HWM (long) or above LWM (short) using chandelier exit. Regime hint: VIX < 22 (low volatility expansion phase); 09:45-10:30 EST to avoid first 15m noise and midday chop; avoid FOMC days. Novelty claim (why not already in the registry): Differs from ORB_RETEST_LONG (which buys ORB retests after breakout) by fading ORB breaks that reject VWAP; distinct from VWAP_CONTINUATION (which requires VWAP hold) by targeting VWAP reversion after ORB failure. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-orb-vwap-divergence-fade-free-age --task-id 4d625656-19dc-4b90-bb1e-78eb40017a22 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
