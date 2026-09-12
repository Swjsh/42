# CANDIDATE: strategy-ideation-proposal-pcr-extreme-reversion-free-agent-

**Filed:** 2026-09-12
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'PCR_EXTREME_REVERSION' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: Extreme 0DTE put/call volume ratio signals exhaustion and intraday mean‑reversion when price is displaced from VWAP. Entry rule: If 0DTE put/call volume ratio > 2.0 and price is below VWAP with a bullish reversal candle (close > open and body > 50% of range), go long; if ratio < 0.5 and price above VWAP with a bearish reversal candle (close < open and body > 50% of range), go short. Exit shape: Initial stop at the nearest swing low (for longs) or swing high (for shorts) or 1R, whichever is tighter; take profit at 1.5R or trail with a chandelier exit (ATR×3). Regime hint: Best in low‑to‑moderate VIX (<20) and during the morning session (09:30‑11:30) when 0DTE activity peaks; avoid high‑VIX (>30) or news‑driven spikes. Novelty claim (why not already in the registry): No existing setup uses 0DTE put/call volume ratio as a primary filter; the closest is VWAP_CONTINUATION, which relies solely on price‑VWAP dynamics without options‑flow extremes. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-pcr-extreme-reversion-free-agent- --task-id 352f461d-3c48-4af4-9da9-c2bcf1ead3d2 --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
