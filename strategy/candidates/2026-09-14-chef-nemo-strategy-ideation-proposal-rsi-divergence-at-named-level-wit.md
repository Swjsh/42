# CANDIDATE: strategy-ideation-proposal-rsi-divergence-at-named-level-wit

**Filed:** 2026-09-14
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'RSI_DIVERGENCE_AT_NAMED_LEVEL_WITH_STRUCTURE_CONFIRM' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: Bullish RSI divergence at a named support level, confirmed by a break of structure, provides a precise long entry with defined risk. Entry rule: Define a named level (prior day low, VWAP, or Asian session low). When price makes a lower low but RSI makes a higher low (bullish divergence) and then closes above the prior bar’s high (BOS) while staying above the named level, enter long at that close. Exit shape: Stop at the named level (chart‑stop), TP1 at 1.5R, runner trail using the 8/21 EMA crossover (exit when 8 EMA crosses below 21 EMA). Regime hint: Effective in VIX 15‑25, avoiding the first 15 minutes after open and the last 15 minutes before close; optimal between 10:00‑14:30 EST. Novelty claim (why not already in the registry): Similar to RSI_DIVERGENCE_BULL_WATCHER (a gate) but this is a full entry strategy that adds a named‑level filter and a BOS confirmation, which together are not represented in the existing registry or killed list. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-rsi-divergence-at-named-level-wit --task-id 2a3b7011-3279-4a66-838f-bdd730566895 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
