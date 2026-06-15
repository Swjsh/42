"""Darwinian filter weights for Gamma.

Each filter (e.g. `f5_bear_ribbon_stack`, `f9_bear_breakdown_bar`) has a
multiplicative weight in [0.3, 2.5] that drifts daily based on recent
contribution to winners vs losers.

Three usage modes (least to most invasive):
    1. ANALYTICS — surface weights in journal/dashboard so a poorly-performing
       filter is visible.
    2. PROPOSER BIAS — feed weights into the autoresearch proposer so low-weight
       filters are modified first.
    3. WEIGHTED ENTRY — replace `bear_score >= N` with weighted-sum threshold.
       (Most invasive; requires careful threshold calibration.)

This module currently implements (1) and (2). Mode (3) is ready to wire but
not active by default.
"""

from . import scorecard, weights

__all__ = ["scorecard", "weights"]
