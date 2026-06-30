# Gym validators: double-bottom-adjacent (from 2026-06-29 missed-setups post-mortem)

Source: markdown/research/MISSED-SETUPS-POSTMORTEM-2026-06-29.md. N=1 discipline: assert DETECTION on fixtures, arm nothing.

Fixtures = the real 06-29 SPY 5m bars (in the post-mortem). Build crypto/validators/v{NN}_{slug}.py with run_offline()+run_live().

## v_double_bottom_adjacent_detects
On a fixture of the 06-29 10:10/10:15/10:20/10:25 bars, the patched adjacent-low double_bottom_detector FIRES at the 10:25 reclaim (close 736.06 > neckline 735.23), key_price≈732.12 — whereas the UNPATCHED detector returns None (asserts both, documenting the bug).

## v_double_bottom_empty_between_guard
Directly asserts that adjacent lows (low1_idx+1 == low2_idx) produce a non-None neckline = max(low1.high, low2.high) under the patch, instead of hitting `if not between: return None`.

<!-- SUPERSEDED 2026-06-29 conductor :: The MISSED-SETUPS-POSTMORTEM-2026-06-29.md that SPAWNED this spec later ran its own redundancy + base-rate + call-side + OOS triage and REJECTED all three detector ideas: DUAL_REJECTION = 'largely REDUNDANT (level_rejection already fires at bear 8)' + filter-5 relaxation is a coin-flip / OOS-NEGATIVE loser (do NOT arm); double-bottom adjacent patch 'made ZERO difference (identical n=318)... empirically irrelevant' and the call edge 'washes out by EOD, likely theta-eaten'. DUAL_REJECTION_SEQUENCE_BREAKDOWN + vol_expansion_ratio detectors do NOT exist -> building these validators = building NEW detector code the same document says not to build. The ONE load-bearing residual this spec groped toward (frozen-key-levels can't silently rot) was SHIPPED instead as engine_health.check_level_feed + test_engine_health_level_feed.py (13/13). Verify-don't-inherit (L181/L185); compound-don't-accumulate (OP-22). Revisit only if the regime shifts to trend-down (the post-mortem's own revisit condition). -->
