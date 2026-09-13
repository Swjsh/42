# CANDIDATE: strategy-ideation-proposal-gap-fade-structure-invalidation-f

**Filed:** 2026-09-13
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'GAP_FADE_STRUCTURE_INVALIDATION' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: When the market gaps beyond the prior day’s high or low but fails to make a new higher high (gap‑up) or lower low (gap‑down) in the first 45 minutes, the gap is likely to fade, providing a mean‑reversion opportunity. Entry rule: If opening price > prior day’s high (gap‑up) AND the highest high among the first three 5‑minute bars (09:30‑09:45) ≤ prior day’s high, enter short at the close of the third bar. If opening price < prior day’s low (gap‑down) AND the lowest low among those bars ≥ prior day’s low, enter long at the close of the third bar. Exit shape: Stop placed beyond the gap extreme (short: stop above gap‑up high; long: stop below gap‑down low). Target set to fill the gap (price returning to prior day’s close) or 1:1.5R, whichever is reached first; exit early if price makes a new high/low after entry (chart‑stop). Regime hint: Effective when overnight volatility is low (VIX < 18) and prior day’s range is narrow (ATR < 20‑day average), reducing chance of continuation. Avoid during high‑impact news (FOMC, CPI, payrolls) where gaps often persist. Novelty claim (why not already in the registry): While GAP_AND_GO targets gap continuation, this candidate focuses on gap fade when structure fails to confirm—a concept absent from the registry and killed list. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-gap-fade-structure-invalidation-f --task-id 1bd11c0b-9185-415b-a589-e3554498cde6 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
