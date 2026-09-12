# CANDIDATE: strategy-ideation-proposal-ofi-orb-fade-free-agent-ideation-

**Filed:** 2026-09-12
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'OFI_ORB_FADE' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: Extreme order‑flow imbalance during the opening range that fails to push price beyond the range predicts a fade reversal. Entry rule: Compute order‑flow imbalance (OFI) as volume‑weighted price change over the first 15 min. If OFI > +2σ and price fails to break above the opening‑range high (close < ORH), go short; if OFI < -2σ and price fails to break below the opening‑range low (close > ORL), go long. Exit shape: Initial stop at the opposite opening‑range edge (ORL for shorts, ORH for longs) or 1R; target at 1R or trail using 10% of ATR(14). Regime hint: Effective when VIX is moderate (15‑25) and the market is not in a strong trend (ADX < 20); avoid extremely low VIX (<12) or high‑impact news periods. Novelty claim (why not already in the registry): No existing setup uses order‑flow imbalance; the nearest is GATE_POSTFIX_COSTING (not in registry) but none of the registered strategies incorporate OFI or opening‑range fade logic. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-ofi-orb-fade-free-agent-ideation- --task-id bba9f479-efed-4f2e-bfb9-a11b3e3a459a --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
