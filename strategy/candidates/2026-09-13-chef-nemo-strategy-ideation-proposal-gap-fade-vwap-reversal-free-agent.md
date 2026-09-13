# CANDIDATE: strategy-ideation-proposal-gap-fade-vwap-reversal-free-agent

**Filed:** 2026-09-13
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'GAP_FADE_VWAP_REVERSAL' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: When the market gaps open beyond the prior day’s VWAP and VIX is elevated, the gap tends to fill as mean‑reversion pressure returns price to the prior day’s VWAP. Entry rule: If today’s opening price is above prior day’s VWAP + 0.5×ATR (gap up) OR below prior day’s VWAP – 0.5×ATR (gap down) AND VIX > 20 (elevated) AND the first 5‑min bar closes back inside the prior day’s VWAP band (±0.25×ATR), then enter opposite direction at the close of that 5‑min bar (short for gap up, long for gap down). Exit shape: Stop at the high/low of the gap bar (chart‑stop); target at prior day’s VWAP; if price reaches VWAP early, exit half and trail remainder with a 15 % premium‑stop. Regime hint: Best during 09:30‑10:15 EST when gap fill propensity is highest and VIX > 20 (heightened uncertainty). Novelty claim (why not already in the registry): GAP_AND_GO trades gap continuations; this fades gaps using VWAP as the magnet and requires VIX elevation and a quick reversal signal, a combination not present in the registry. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-gap-fade-vwap-reversal-free-agent --task-id c9537747-bcdd-43bb-bc77-a2cfc0928fb9 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
