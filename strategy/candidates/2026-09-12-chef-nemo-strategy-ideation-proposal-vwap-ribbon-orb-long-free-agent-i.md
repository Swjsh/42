# CANDIDATE: strategy-ideation-proposal-vwap-ribbon-orb-long-free-agent-i

**Filed:** 2026-09-12
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'VWAP_RIBBON_ORB_LONG' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: When price opens above VWAP with a bullish EMA ribbon and breaks the opening range high on elevated volume, intraday momentum persists. Entry rule: At market open, if SPY's open price > VWAP (calculated from prior close) AND the 9 EMA > 21 EMA > 55 EMA (bullish ribbon) AND price breaks above the opening range high (highest high of first 5‑min bars) with volume on the breakout bar > 1.5 * average volume of previous 20 bars, then go long at the close of that bar. Exit shape: Initial stop at the opening range low (or 0.5% below entry), target 1.5R, then trail the remaining position with a chandelier exit (ATR(3)*3) or exit on a close below VWAP. Regime hint: Best in low‑to‑moderate VIX (<18) and during the first 90 minutes after the open; avoid choppy sessions where the ribbon is flat or volume is thin. Novelty claim (why not already in the registry): Similar to VWAP_CONTINUATION but adds a bullish EMA ribbon requirement and a volume‑filtered ORB break, making the setup more selective; this exact combination is not present in the known registry or killed list. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-vwap-ribbon-orb-long-free-agent-i --task-id 1861b695-59fd-4658-92d1-d4cffda6c739 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
