# CANDIDATE: strategy-ideation-proposal-vol-compression-orb-breakout-free

**Filed:** 2026-09-13
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'VOL_COMPRESSION_ORB_BREAKOUT' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: When the opening range contracts to a narrow band (low volatility) and then breaks out with a volume surge, the ensuing move tends to persist, providing a breakout long or short. Entry rule: Compute opening range width (ORH‑ORL) for the first 30 min. If the width is in the lowest 20% of the last 20 days (volatility compression) and the price breaks above ORH (for long) or below ORL (for short) on a bar with volume >1.5× the average 5‑minute volume of the same period, enter in the direction of the break at the close of that bar. Exit shape: Stop placed just inside the opposite side of the opening range (ORL for longs, ORH for shorts); target 2× risk or use a premium‑stop of 0.6% trailed by 8% of ATR. Regime hint: Effective when VIX <18 (low volatility environment) and avoid major news windows (first 15 min after open and 30 min before close). Novelty claim (why not already in the registry): Similar to BOLLINGER_SQUEEZE which uses Bollinger Band width, but this candidate uses the actual opening range width as a volatility proxy and couples the breakout with a volume spike, making it purely price/action‑based without relying on Bollinger calculations. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-vol-compression-orb-breakout-free --task-id bbce5508-d1ed-4558-abc7-1545baba20be --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
