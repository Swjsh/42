# L150: AGG is stop-dominant; runner value is in TP1+time/ribbon exits, NOT the 5.0x target

**Date:** 2026-06-17
**Found by:** exit type audit (backtest/autoresearch/agg_exit_type_audit.py)
**Evidence file:** analysis/recommendations/agg_exit_type_audit.json

## Symptom
AGG runner_target sweep showed all lower candidates (2.0-4.0) produce IS_delta=0, OOS_delta=0.
We hypothesized the runner target was "never hit." Needed to quantify.

## Root cause (quantified)
AGG IS (n=218): EXIT_ALL_PREMIUM_STOP = 72.9% of all trades (avg -$151/trade).
Only 1.8% of IS trades hit the 5.0x runner target. 0% OOS.

The runner leg value comes from:
1. TP1_THEN_RUNNER_TIME (10 trades IS, avg +$1,771) — trade reached TP1 then held to time stop at 15:40 ET
2. TP1_THEN_RUNNER_RIBBON (9 trades IS, avg +$765) — trade reached TP1 then exited on ribbon flip-back

The 5.0x target is a CEILING on unconstrained runner, not an expected exit point.
All AGG profit (IS +$10,019) concentrates in 14.7% of trades (TP1 then runner).

## Fix
No param change needed — runner_target=5.0 correctly functions as unconstrained.
Prevent: before sweeping runner_target, audit runner_target_hit_rate to confirm the knob is even binding.
A target never hit has no impact on results — which is why runner_target candidates 2.5-4.0 all produced IS_delta=0.

## Theme cross-reference
- Related: L109 (hardcoded runner_target in real-fills path), L148 (runner exits via ribbon/time_stop)
- Theme: C3 (SPY-price edge != option edge), C14 (dead/untested knob = silent no-op)
- New pattern: STOP-DOMINANT ARCHITECTURE — when 73%+ of trades exit at stop-loss, the P&L
  comes from survivor bias on the 15-20% that reach TP1. Audit exit distribution before
  assuming any exit knob is binding.
