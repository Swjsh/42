# CANDIDATE: strategy-ideation-proposal-opening-range-vwap-reclaim-volume

**Filed:** 2026-09-14
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'OPENING_RANGE_VWAP_RECLAIM_VOLUME_SPIKE_LONG' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: Price that opens inside the opening range and then reclaims VWAP on above-average volume with bullish ribbon alignment signals short-term buying pressure. Entry rule: When the first 30‑minute opening range (OR) is defined, price subsequently pulls back to touch or cross below the VWAP, then closes above VWAP on a bar with volume ≥1.5× the 20‑bar average volume, and the 8‑,21‑,55‑EMA ribbon is bullish (EMA8 > EMA21 > EMA55). Exit shape: Initial stop placed at the OR low; target at 1.5R or a trailing chandelier exit (20% below highest high since entry). Regime hint: Best in low‑to‑moderate volatility (VIX <18) and during the first 90 minutes after open; avoid when VIX >22 or during major news windows. Novelty claim (why not already in the registry): Similar to VWAP_CONTINUATION and ORB_RETEST_LONG but adds a volume‑spike filter and explicit ribbon‑bullish requirement, which are not present in those setups. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-opening-range-vwap-reclaim-volume --task-id cf37c1c5-a9b1-46e6-aeed-60ea60cd1ee0 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
