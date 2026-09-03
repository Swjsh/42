# WALKER-MAGNITUDE-BIAS-VS-SIGN-FIDELITY (2026-09-03) -- RESEARCH

Scope: harness fidelity only -- decides no strategy, places no order, arms nothing.

## Magnitude criterion (pre-registered this run)
- N floor: 20
- |aggregate_ratio - 1| <= 0.4
- median_abs_error_dollars <= $40
- Derivation: Anchored to whole_engine_null.py's V9 (n=121, 2026-09-02 run): aggregate_ratio 0.6452, median_abs_error $15.00 -- the best-attested walker application in this repo (it gates a frozen prereg's own verdict). Tolerance set generously ABOVE those numbers so V9 clears with room rather than being fitted flush to it; the PDT anchor's own numbers (ratio 4.09, median $32.40) fail the ratio leg by a wide margin (|4.09-1|=3.09 >> 0.40) even though its median alone would pass -- which is why both conditions are required, not either.

## Reproduction check
- Matches queue-item numbers exactly: **True**
- n=43  sign_agreement=95.35%

## Mechanism tests (ruling candidates in/out)
- **slippage_contribution**: RULED OUT as dominant
- **fill_mode_sensitivity**: RULED OUT as loser-side driver (loser_ratio identical across fill modes)
- **bar_resolution_sensitivity**: RULED OUT as loser-side driver (loser_ratio identical 1-min vs 5-min)
- **stage_agreement**: RULED OUT as dominant (stage-mismatch is a small minority of loser error)

## Root cause + fix
- Location: `backtest/tools/multileg_exit_walk.py#walk (research tool, not trading-path)`
- Mechanism: ExitAction carries no `price` field, so every non-tp1 SELL leg fell through to `state.runner_stop_premium or worst_in`. runner_stop_premium is set at entry to entry_premium*(1+stop_pct) and is never None afterward, so worst_in (the bar price fill_mode controls) was dead code for structure_stop/ribbon_flip/time_stop -- every one of those market-style exits priced at the STATIC catastrophe/premium-stop level instead of the bar's real price.
- Fix: market_stage_fill_fix=True kwarg on walk(), default False (byte-identical for every existing caller until it opts in).
- Before: aggregate_ratio=4.0922  median_abs_error=$32.4  verdict=FAIL
- After:  aggregate_ratio=2.8357  median_abs_error=$31.8  verdict=FAIL
- Excess-ratio reduction: 40.6%

## Big anchor population
- Window 2026-06-01..2026-09-02, n_walked=128 (n_missing_bars=4)
- aggregate_ratio=31.5702  verdict=FAIL

## Outstanding prereg RUNs -- can they be believed on dollars?
- **recency-qty-clamp**: NO -- shares multileg_exit_walk with the PDT study; this run shows that walker fails the magnitude criterion even after the market-stage fix. Sign-trustworthy, dollar-suspect, unchanged from this item's original caveat.
- **runner-finite-tgt**: NO -- same walker family, same caveat.
- **profit-lock-arm-scope**: NO -- same walker family; ALSO carries its own named sim-vs-live profit-lock scope divergence (queue item's own caveat) on top of this one.

## Known limitations
- big_anchor_population's aggregate_ratio (31.5702) is inflated by a near-zero denominator: actual_total_dollars=-141.0 is a small difference between winners ($7619.0) and losers ($-7760.0) that mostly cancel. The winners_ratio (1.0024) and losers_ratio (1.5287) are the trustworthy read here, not the aggregate ratio alone -- same caveat whole_engine_null.py's own magnitude_fidelity note already carries for exactly this reason.
- The market-stage fill fix is NOT a full fix -- aggregate_ratio improved but did not reach the criterion. The remaining gap after the fix is not diagnosed by this run.
- mechanism_bar_resolution restricts to rows with BOTH a 5-min OPRA cache and a 1-min highres cache (paired comparison) -- a smaller n than the full anchor set; see n_common.
- This study reuses pdt_blocked_counterfactual.py's shape/trigger-level resolution for every variant (canonical_shape / anchor_trigger_level) rather than reimplementing it -- any defect in THAT resolution logic is inherited here too, not independently re-verified.
