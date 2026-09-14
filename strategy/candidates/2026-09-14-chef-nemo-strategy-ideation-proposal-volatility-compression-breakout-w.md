# CANDIDATE: strategy-ideation-proposal-volatility-compression-breakout-w

**Filed:** 2026-09-14
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'VOLATILITY_COMPRESSION_BREAKOUT_WITH_VOLUME_SPIKE' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: A volatility‑contracted opening range followed by a breakout on above‑average volume captures the imminent expansion phase. Entry rule: If ATR(5) < 0.8 * ATR(10) for the prior three bars (vol compression) and the first‑15‑minute OR width < 0.2% of price, wait for a breakout above OR high (long) or below OR low (short) on a bar with volume > 1.5 * the 20‑bar average volume; enter at the breakout bar’s close. Exit shape: Stop at the opposite side of the OR (chart‑stop), TP1 at 2R, runner using a chandelier trail (ATR * 3) or premium‑stop 20%. Regime hint: Works best in low‑volatility regimes (VIX < 18) and mid‑morning (10:00‑11:30 EST) when compression tends to resolve; avoid high‑VIX expansion days. Novelty claim (why not already in the registry): The nearest analog is BOLLINGER_SQUEEZE, which relies on Bollinger Band width. This concept uses ATR contraction, OR width, and a volume‑spike trigger, making it structurally different and not present in the registry. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-volatility-compression-breakout-w --task-id e30b7bcc-18ce-4eed-8a1c-e50685c5d194 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
