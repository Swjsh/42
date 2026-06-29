# Gym validators: double-bottom-adjacent (from 2026-06-29 missed-setups post-mortem)

Source: markdown/research/MISSED-SETUPS-POSTMORTEM-2026-06-29.md. N=1 discipline: assert DETECTION on fixtures, arm nothing.

Fixtures = the real 06-29 SPY 5m bars (in the post-mortem). Build crypto/validators/v{NN}_{slug}.py with run_offline()+run_live().

## v_double_bottom_adjacent_detects
On a fixture of the 06-29 10:10/10:15/10:20/10:25 bars, the patched adjacent-low double_bottom_detector FIRES at the 10:25 reclaim (close 736.06 > neckline 735.23), key_price≈732.12 — whereas the UNPATCHED detector returns None (asserts both, documenting the bug).

## v_double_bottom_empty_between_guard
Directly asserts that adjacent lows (low1_idx+1 == low2_idx) produce a non-None neckline = max(low1.high, low2.high) under the patch, instead of hitting `if not between: return None`.
