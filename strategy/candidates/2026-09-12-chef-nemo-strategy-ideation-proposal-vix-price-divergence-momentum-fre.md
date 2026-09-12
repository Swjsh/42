# CANDIDATE: strategy-ideation-proposal-vix-price-divergence-momentum-fre

**Filed:** 2026-09-12
**Filer:** kitchen-daemon (Stage-1-gated cook, GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05)
**Status:** DRAFT (RUNNER-FAILED -- NEEDS-RATIFICATION per Rule 9)

## Hypothesis

STRATEGY-IDEATION PROPOSAL 'VIX_PRICE_DIVERGENCE_MOMENTUM' (free-agent ideation organ, NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). Thesis: Trade SPY in direction of VIX-price divergence (e.g., VIX lower high vs SPY higher high) only when SPY fails to sustain break of prior session extreme on weakening volume. Entry rule: Short: VIX forms lower high (current VIX high < prior VIX high) AND SPY forms higher high (current SPY high > prior SPY high) over last 30m AND SPY fails to breach prior day high on two consecutive bars with volume <90% of 20-bar avg AND bar closes below prior bar low; Long: VIX forms higher low AND SPY forms lower low AND SPY fails to breach prior day low on two bars with volume <90% AND bar closes above prior bar high. Exit shape: Stop beyond recent swing point (short stop above recent swing high, long stop below recent swing low); TP at 1x risk to prior session extreme (prior day low for short, prior day high for long); exit if VIX-price divergence resolves (VIX and SPY make same-direction extreme). Regime hint: VIX > 18 (ensures meaningful volatility for mean reversion); 11:00-14:00 EST to avoid open drive and late-day drift; avoid high-impact news windows. Novelty claim (why not already in the registry): Distinct from VIX_REGIME_DAYSIDE (which uses VIX absolute levels) and RSI_DIVERGENCE_BULL_WATCHER (uses RSI, not VIX); no existing setup uses VIX-price divergence with volume failure condition. Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness before any further ratification.

## Provenance

provenance: C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe C:\Users\jackw\Desktop\42\setup\scripts\kitchen_stage1_runner.py --combo-json {} --slug strategy-ideation-proposal-vix-price-divergence-momentum-fre --task-id 3b82ba24-f921-40cc-bfef-5fe8b94eecfa --timeout-s 480.0 -> RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
status: RUNNER-FAILED (single_worker_lock_held -- another Stage-1 run is in flight)
engine_note: MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars (backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md.

NO NUMBERS ARE PRESENT IN THIS FILE. Per GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05 a verdict or numeric claim cannot be written unless the Stage-1 runner executed successfully and produced an artifact. Cross-check: automation/state/kitchen-stage1-run-log.jsonl.

## Pre-merge gate

N/A -- runner failed, no evidence exists to gate on. Re-enqueue after the failure is understood (see reason above); do not hand-write numbers in to unblock this.
