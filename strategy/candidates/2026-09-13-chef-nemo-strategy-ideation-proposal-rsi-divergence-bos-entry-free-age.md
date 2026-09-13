# CANDIDATE: strategy-ideation-proposal-rsi-divergence-bos-entry-free-age

**Filed:** 2026-09-13
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'RSI_DIVERGENCE_BOS_ENTRY' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: A bearish (or bullish) RSI divergence on the 5‑minute chart that coincides with a break of market structure (BOS) and ribbon alignment offers a high‑probability reversal entry. Entry rule: Calculate 14‑period RSI on 5‑minute bars. Identify a bearish divergence when price makes a higher high while RSI makes a lower high, or a bullish divergence when price makes a lower low while RSI makes a higher low. If the divergence occurs within the last three bars and the price subsequently breaks the most recent swing high (for bullish divergence) or swing low (for bearish divergence) – i.e., a BOS – and the 5‑period EMA is above the 8‑period EMA (bullish) or below (bearish) confirming ribbon direction, enter long on bullish divergence/BOS or short on bearish divergence/BOS at the close of the breakout bar. Exit shape: Stop placed beyond the swing point that was broken (above swing high for shorts, below swing low for longs); target 1.8× risk or use a chandelier trail at 1.5× ATR. Regime hint: Best when VIX is between 14‑25 and the session shows choppy price action (price alternating HH/LH patterns) rather than a strong monotonic trend. Novelty claim (why not already in the registry): While RSI_DIVERGENCE_BULL_WATCHER exists in the ideation ledger, it is not an implemented setup. The closest actual registry entry is VWAP_CONTINUATION, which is unrelated. This candidate uniquely combines RSI divergence with a market‑structure break (BOS) and ribbon confirmation, a combination not present in any existing setup. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-rsi-divergence-bos-entry-free-age --task-id 9e490251-1ae4-4716-9563-88c38518240f --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
