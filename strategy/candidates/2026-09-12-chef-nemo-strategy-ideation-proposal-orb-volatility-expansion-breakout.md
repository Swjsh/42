# CANDIDATE: strategy-ideation-proposal-orb-volatility-expansion-breakout

**Filed:** 2026-09-12
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'ORB_VOLATILITY_EXPANSION_BREAKOUT' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: A narrow opening range followed by a volume‑expanded breakout captures the initial imbalance and often leads to a sustained move. Entry rule: Define opening range (first 30 min) high and low; ORB width = (high‑low)/ATR(14). If ORB width < 0.4 (tight) and the breakout bar (first bar after 30 min) closes beyond the ORB high (long) or low (short) with volume > 2× average volume of the first 20 bars, enter in the breakout direction at the close of that bar. Exit shape: Stop = opposite ORB edge (low for long, high for short); target = 2 × ORB width or trail using chart‑stop at structure invalidation (a close back inside the ORB). Optionally take 50% profit at 1R and let the rest trail. Regime hint: Works best when VIX is low‑moderate (<20) and during the first hour after open; avoid on high‑VIX days (>30) or when ORB width is already wide (>0.8), indicating low edge. Novelty claim (why not already in the registry): Closest existing is ORB_RETEST_LONG, which waits for a retest of the ORB level. This candidate trades the initial breakout of a narrow ORB with volume confirmation, without waiting for a retest, making the entry timing and condition set different. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-orb-volatility-expansion-breakout --task-id 4e5ce11e-e072-4a18-ae8a-4479cb0d6c7f --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
