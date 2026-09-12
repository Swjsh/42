# CANDIDATE: strategy-ideation-proposal-vix-low-bos-pullback-long-free-ag

**Filed:** 2026-09-12
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'VIX_LOW_BOS_PULLBACK_LONG' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: When VIX is low (<12) and price makes a higher‑high break of structure after pulling back to the 20 EMA, the market tends to continue upward. Entry rule: When the prior bar's VIX < 12, price pulls back to touch or cross below the 20‑EMA but does not close below it; on the next bar, price makes a new higher high (BOS) above the prior swing high, then enter long at the close of that BOS bar. Exit shape: Stop placed at the low of the pullback bar (or 0.5% below entry), target 2R, with an optional runner trailed by a chandelier exit (ATR*2.5). Regime hint: Works best in low‑VIX environments, preferably the morning session (9:30‑11:30) when mean‑reversion is weaker; avoid high VIX (>20) or scheduled news events. Novelty claim (why not already in the registry): Combines a VIX regime filter with a market‑structure BOS after an EMA pullback; the registry contains VIX_REGIME_DAYSIDE and various BOS‑related gates but not this specific VIX‑low + EMA pullback + BOS entry rule. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-vix-low-bos-pullback-long-free-ag --task-id f3cb5cd8-cca9-40ba-ab66-d6aa2e8ab983 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
