# CANDIDATE: strategy-ideation-proposal-midday-volume-spike-failure-rever

**Filed:** 2026-09-12
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'MIDDAY_VOLUME_SPIKE_FAILURE_REVERSAL' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: A sudden volume spike in the midday window that fails to extend price beyond the prior swing indicates exhaustion and a mean‑reversion opportunity. Entry rule: Between 11:00‑13:00, if volume exceeds 2.0× the 20‑period average volume AND price makes a new high (for long bias) or new low (for short bias) but then closes back inside the prior 10‑bar range (i.e., fails to hold the breakout), then enter at the close of the failure bar in the opposite direction (short after a failed up‑breakout, long after a failed down‑breakout). Exit shape: Stop placed beyond the extreme of the failed breakout (above the high for shorts, below the low for longs); TP1 at 1R; remaining half trailed by premium‑stop % (e.g., 0.5% of entry price) or chart‑stop at the prior swing point. Regime hint: Effective when VIX is between 15‑25 (moderate volatility) and the market is not in a strong trend (ADX <20 or 200‑EMA slope flat); avoid first and last 30 minutes. Novelty claim (why not already in the registry): Unlike VWAP_RECLAIM_FAILED_BREAK or LEVEL_BREAK_FIRST_STRIKE, this setup uses a volume‑spike failure criterion rather than price‑level retest, and it is confined to the midday window, which is not captured by any existing named setup. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-midday-volume-spike-failure-rever --task-id 6f69ef4c-ef7c-4a63-8556-44a58d74003b --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
