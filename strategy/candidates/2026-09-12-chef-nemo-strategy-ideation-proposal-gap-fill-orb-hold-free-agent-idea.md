# CANDIDATE: strategy-ideation-proposal-gap-fill-orb-hold-free-agent-idea

**Filed:** 2026-09-12
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'GAP_FILL_ORB_HOLD' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: Trade gap fills that successfully test and hold the opening range, expecting continuation in gap-fill direction after ORB validation. Entry rule: Long: Gap down >0.3% (open < prior day close -0.3%) AND price fills gap (reaches prior day close) within first 30m AND subsequent retest of ORB low closes above ORB low with volume >1.1x 5-bar avg volume AND bar is bullish (close > open); Short: Gap up >0.3% AND price fills gap (reaches prior day close) within 30m AND retest of ORB high closes below ORB high with volume >1.1x 5-bar avg volume AND bar is bearish (close < open). Exit shape: Stop beyond ORB extreme (long stop below ORB low, short stop above ORB high); TP at 1.5x risk to prior day extreme (prior day high for long, prior day low for short); exit if price re-opens gap with closing penetration. Regime hint: VIX < 26; only when first 5m volume >1.3x 20-bar avg volume (confirms gap authenticity); avoid days with ORB width <0.2% (choppy ORB). Novelty claim (why not already in the registry): Differs from GAP_AND_GO (trades gap continuation without ORB test) and ORB_RETEST_LONG (trades ORB retests after breakout) by requiring gap fill → ORB hold → gap-fill direction trade; no killed list equivalent combines gap fill with ORB validation. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-gap-fill-orb-hold-free-agent-idea --task-id 62a778fd-9fc9-4743-8452-9e56f70d4758 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
