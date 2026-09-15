# CANDIDATE: strategy-ideation-proposal-named-level-retest-vol-rsi-diverg

**Filed:** 2026-09-15
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'NAMED_LEVEL_RETEST_VOL_RSI_DIVERGENCE_LONG' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: A retest of a named level on declining volume with bullish RSI divergence signals a bounce long. Entry rule: If price touches within 0.1% of the prior week’s high (named level) on two consecutive bars, each bar’s volume is lower than the previous bar’s, and RSI(14) makes a higher low while price makes an equal or lower low, enter long at the close of the second bar. Exit shape: Chart‑stop at the prior week’s low (structure invalidation), TP1 at 1.5R, runner trailed 10% below the high‑water mark. Regime hint: VIX < 20, time 13:00‑15:00, ribbon neutral (EMA9 between EMA21 and EMA55). Novelty claim (why not already in the registry): Closest is NAMED_LEVEL_SECOND_TEST; this adds a volume‑decline requirement and bullish RSI divergence condition, which are not jointly present in any registry entry. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-named-level-retest-vol-rsi-diverg --task-id 98d7b3ce-ceb5-4a3c-b523-9046e42507d4 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
