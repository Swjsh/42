"""Canonical G5 anchor-no-regression check.

WHY THIS FILE EXISTS (L160, 2026-06-18):
The G5 "anchor-no-regression" gate was re-implemented inline in ~15 sweep scripts.
Several used the formula `curr_anchor >= base_anchor * 0.90`, which is WRONG when
`base_anchor` is negative: multiplying a negative baseline by 0.90 moves the
threshold TOWARD zero (i.e. demands the candidate be 10% BETTER), so a genuinely
anchor-neutral change (curr == base) is silently REJECTED. The fix is an
absolute-value tolerance band:

    curr_anchor >= base_anchor - abs(base_anchor) * tolerance_pct

That reads correctly for both signs: "allow the candidate to be up to
tolerance_pct WORSE than baseline, in absolute dollars."

L160 was fixed in two scripts but the broken form kept reappearing in new sweep
scripts (prose failed as a control). This module is the single source of truth so
new code calls one tested function instead of re-deriving the formula. The
graduated guard `test_l160_anchor_no_regression_*` in test_graduated_guards.py
both unit-tests this helper AND scans the tree for the broken `* 0.9` pattern.
"""

from __future__ import annotations


def anchor_no_regression(
    base_anchor: float,
    curr_anchor: float,
    tolerance_pct: float = 0.10,
) -> bool:
    """Return True if the candidate's anchor P&L has NOT regressed beyond tolerance.

    Sign-correct for negative baselines (the L160 foot-gun). "No regression" means
    the candidate is allowed to be at most ``tolerance_pct`` WORSE than the baseline
    in absolute dollar terms:

        curr_anchor >= base_anchor - abs(base_anchor) * tolerance_pct

    Args:
        base_anchor: Baseline (production) summed anchor-trade P&L. May be negative.
        curr_anchor: Candidate summed anchor-trade P&L over the same anchor dates.
        tolerance_pct: Fraction of |base_anchor| the candidate may give up. 0.10 = 10%.

    Examples:
        >>> anchor_no_regression(-354.0, -354.0)   # identical -> neutral -> PASS
        True
        >>> anchor_no_regression(-354.0, -500.0)   # much worse -> FAIL
        False
        >>> anchor_no_regression(1000.0, 950.0)    # 5% worse (positive) -> PASS
        True
        >>> anchor_no_regression(1000.0, 800.0)    # 20% worse (positive) -> FAIL
        False
    """
    if tolerance_pct < 0:
        raise ValueError(f"tolerance_pct must be >= 0, got {tolerance_pct}")
    threshold = base_anchor - abs(base_anchor) * tolerance_pct
    return curr_anchor >= threshold
