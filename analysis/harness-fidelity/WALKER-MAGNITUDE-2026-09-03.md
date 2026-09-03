# WALKER-MAGNITUDE-BIAS-VS-SIGN-FIDELITY (2026-09-03) -- RESEARCH

Scope: harness fidelity only -- decides no strategy, places no order, arms nothing.

## Magnitude criterion (pre-registered this run)
- N floor: 20
- |aggregate_ratio - 1| <= 0.4
- median_abs_error_dollars <= $40
- Derivation: Anchored to whole_engine_null.py's V9 (n=121, 2026-09-02 run): aggregate_ratio 0.6452, median_abs_error $15.00 -- the best-attested walker application in this repo (it gates a frozen prereg's own verdict). Tolerance set generously ABOVE those numbers so V9 clears with room rather than being fitted flush to it; the PDT anchor's own numbers (ratio 4.09, median $32.40) fail the ratio leg by a wide margin (|4.09-1|=3.09 >> 0.40) even though its median alone would pass -- which is why both conditions are required, not either.

## Reproduction check
- Matches queue-item numbers exactly: **False**
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
- Before: aggregate_ratio=3.8998  median_abs_error=$31.8  verdict=FAIL
- After:  aggregate_ratio=2.6433  median_abs_error=$31.55  verdict=FAIL
- Excess-ratio reduction: 43.3%

## 2026-09-03 follow-up (WALKER-MARKET-STAGE-FILL-ROOT-FIX)
- What changed: time_stop ONLY: moved out of the worst_in bucket into its own bar-CLOSE price (a clock event has no price-cross to reuse). structure_stop/ribbon_flip unchanged (still worst_in -- no premium threshold exists for either).
- What was tried and reverted: Extending _MARKET_STAGES to premium_stop, profit_lock_floor, trail, be_stop, runner_target (reasoning: a live market SELL always crosses the bid). MEASURED WORSE on the 43-row PDT anchor: aggregate_ratio 4.09 -> 4.88 (not better), driven almost entirely by premium_stop (stage abs error $516.90 -> $930.00). These 4 stages are numeric-threshold crossings of runner_stop_premium; the live engine polls once/minute and fires the instant a poll crosses, so the true fill sits near the THRESHOLD, not the coarse 5-min bar's full wick -- state.runner_stop_premium (unchanged, the OLD/default fallback) already models that. See multileg_exit_walk.py's own module-level note for the full account.

## Whole-engine V9 anchor validation (independent of the PDT anchor)
- n_rows=133 (n_missing_bars before=12 after=12)
- Before: aggregate_ratio=-1.3252  median_abs_error=$100.0  verdict=FAIL
- After:  aggregate_ratio=-0.241  median_abs_error=$42.0  verdict=FAIL

## 2026-09-03 follow-up, part 2: premium_stop_poll_model (WALKER-MARKET-STAGE-FILL-ROOT-FIX's own NEXT step)
- multileg_exit_walk.walk(premium_stop_poll_model=True): for premium_stop/profit_lock_floor/trail/be_stop legs (numeric threshold crossings of state.runner_stop_premium -- see multileg_exit_walk.py's _POLL_MODEL_STAGES module note), walks the cached 1-min OPRA bars (backtest/data/highres/) inside the firing 5-min bar's window and fires at the CLOSE of the first 1-min bar at/through the threshold -- the closest on-disk proxy to what a live once-a-minute quote poll would have observed. Falls back to the OLD state.runner_stop_premium price, disclosed per-trade as fill_model='5min_fallback', when no 1-min cache exists for the contract/date OR the cache exists but no 1-min close in the window actually reaches the threshold. Both new flags default False; byte-identical for every existing caller until BOTH are opted into together (premium_stop_poll_model requires market_stage_fill_fix=True to matter in practice, since the baseline every believed study already runs on is market_stage_fill_fix=True alone).

### PDT anchor (n=43), market_stage_fill_fix=True baseline vs +premium_stop_poll_model
- Before (market_stage_fill_fix only): aggregate_ratio=2.6433  median_abs_error=$31.55  verdict=FAIL
- After (+premium_stop_poll_model):  aggregate_ratio=3.2604  median_abs_error=$36.0  verdict=FAIL
- Excess-ratio reduction: -37.6%
- 1-min path: 18  5-min fallback: 12  not-applicable (no poll-model stage fired): 13  (n=43)
- Stage decomposition BEFORE: premium_stop $811.5 (n=22), structure_stop $581.0 (n=13), trail $387.5 (n=8)
- Stage decomposition AFTER: premium_stop $1018.5 (n=22), structure_stop $581.0 (n=13), trail $342.4 (n=8)

### V9 anchor, market_stage_fill_fix=True baseline vs +premium_stop_poll_model
- n_rows=133
- Before: aggregate_ratio=-0.241  median_abs_error=$42.0  verdict=FAIL
- After:  aggregate_ratio=-0.4409  median_abs_error=$45.0  verdict=FAIL
- 1-min path: 38  5-min fallback: 20  not-applicable: 63

## Big anchor population
- Window 2026-06-01..2026-09-02, n_walked=128 (n_missing_bars=4)
- aggregate_ratio=32.9723  verdict=FAIL

## Outstanding prereg RUNs -- can they be believed on dollars?
- **recency-qty-clamp**: NO -- shares multileg_exit_walk with the PDT study; this run shows that walker fails the magnitude criterion even after the market-stage fix. Sign-trustworthy, dollar-suspect, unchanged from this item's original caveat.
- **runner-finite-tgt**: NO -- same walker family, same caveat.
- **profit-lock-arm-scope**: NO -- same walker family; ALSO carries its own named sim-vs-live profit-lock scope divergence (queue item's own caveat) on top of this one.

## Known limitations
- big_anchor_population's aggregate_ratio (32.9723) is inflated by a near-zero denominator: actual_total_dollars=-141.0 is a small difference between winners ($7619.0) and losers ($-7760.0) that mostly cancel. The winners_ratio (1.0024) and losers_ratio (1.5542) are the trustworthy read here, not the aggregate ratio alone -- same caveat whole_engine_null.py's own magnitude_fidelity note already carries for exactly this reason.
- The market-stage fill fix is NOT a full fix -- aggregate_ratio improved but did not reach the criterion, on either anchor. Stage-level decomposition on the 43-row PDT anchor (post-fix) attributes the LARGEST remaining abs error to premium_stop ($811.50 of ~$1,780 total, n=22 legs) and structure_stop ($581.00, n=13), with trail a distant third ($387.50, n=8) -- premium_stop was NOT touched by this session's fix (see root_cause_and_fix.root_fix_2026_09_03_followup) and its residual error is a TIMING gap (the 5-min bar's own stop-crossing bar may not be the exact minute the live once-a-minute poll actually fired on), not a within-bar PRICING gap this module's fill_mode knob can address -- not diagnosed further by this run per the queue item's 'do not tune anything else to make the number move' instruction.
- mechanism_bar_resolution restricts to rows with BOTH a 5-min OPRA cache and a 1-min highres cache (paired comparison) -- a smaller n than the full anchor set; see n_common.
- This study reuses pdt_blocked_counterfactual.py's shape/trigger-level resolution for every variant (canonical_shape / anchor_trigger_level) rather than reimplementing it -- any defect in THAT resolution logic is inherited here too, not independently re-verified.
- premium_stop_poll_model (this run's 'NEXT' step) was IMPLEMENTED, MEASURED, and kept OFF by default: aggregate_ratio moved 2.6433 -> 3.2604 on the PDT anchor and -0.241 -> -0.4409 on the V9 anchor -- WORSE on both, not better. Root reason is provable, not just empirical: the OLD fallback price for these stages already IS the threshold (state.runner_stop_premium), the least-adverse price a downside cross can have; the poll model can only find a 1-min close at-or-through that same threshold, so it can never move a leg's price toward actual on a walker that already replays too negative -- it can only push further away. Full mechanism note: multileg_exit_walk.py's `_POLL_MODEL_STAGES` module comment. The residual this leaves behind is a DECISION-GRANULARITY gap (whether the live 1-min poll would have confirmed the cross the outer 5-min bar's decision already assumed), not a pricing gap -- fixing it would mean walking every position at native 1-min resolution end-to-end, not refining the fill price inside an already-5-min-decided bar. Out of scope for a pricing fix; not attempted here.

## Deviations
- Reproduction of the PDT study's own anchor numbers did not match exactly -- the ledger/cache may have changed since 2026-09-02. Proceeding with THIS run's numbers, disclosed as found not forced.
