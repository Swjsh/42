# CANDIDATE: strategy-ideation-proposal-vol-comp-vwap-break-short-free-ag

**Filed:** 2026-09-14
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'VOL_COMP_VWAP_BREAK_SHORT' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: When volatility contracts and price breaks below VWAP‑ATR on expanding volume, a short‑term down move is likely. Entry rule: When ATR(14) < 0.5 * ATR(20) (volatility compression) and close < VWAP - ATR and close < open and (open - close) > 0.6 * (high - low) (strong bearish bar) and volume > 1.5 * volume of the prior bar, go short. Exit shape: Chart‑stop at the most recent swing high (prior HH/LL structure), TP1 at 2.0×R, runner trail using an ATR×2 trailing stop. Regime hint: VIX < 15, time after 11:00 to avoid morning noise, price below the 20‑period EMA (downtrend bias). Novelty claim (why not already in the registry): While BOLLINGER_SQUEEZE exists, this uses volatility compression with a VWAP‑ATR break and volume confirmation for a short entry, a distinct logic not covered. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-vol-comp-vwap-break-short-free-ag --task-id 5c11002d-a604-47de-8cdc-79c35da467f1 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
