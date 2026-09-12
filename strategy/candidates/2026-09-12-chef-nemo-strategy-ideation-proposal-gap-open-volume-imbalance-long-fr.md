# CANDIDATE: strategy-ideation-proposal-gap-open-volume-imbalance-long-fr

**Filed:** 2026-09-12
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'GAP_OPEN_VOLUME_IMBALANCE_LONG' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: A gap up accompanied by a surge in volume on the opening bar often signals sustained intraday buying pressure, especially when the gap fills less than 50% within the first 30 minutes. Entry rule: Identify a gap up where today's open > prior day's high by at least 0.3% and the opening 5‑min bar volume > 2 × average volume of the previous 20 opening bars. If, by 10:00 ET, price has retraced less than 50% of the gap size (i.e., close > open + 0.5*gap), go long at the 10:00 bar close. Exit shape: Stop at the low of the opening bar (chart‑stop), target at 2R, then switch to a runner trailed by a 15% chandelier exit from the highest high after hitting 1R. Regime hint: Effective when VIX is low‑moderate (<20) and the prior day closed in the upper half of its range (indicating bullish bias); avoid on high‑VIX (>30) or after major news events. Novelty claim (why not already in the registry): While GAP_AND_GO exists, it simply buys on any gap up with a break of the opening range high. This candidate adds a volume‑surge filter, a gap‑fill‑percentage constraint, and a delayed entry (10:00) to avoid false breakouts, making it structurally distinct. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-gap-open-volume-imbalance-long-fr --task-id 9b59d27f-855a-468e-95da-456e036ed181 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
