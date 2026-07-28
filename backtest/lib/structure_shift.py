"""structure_shift — CANONICAL structure-shift confirmation predicate (bear + bull).

SINGLE SOURCE OF TRUTH for the STRUCTURE-SHIFT-CONFIRMATION-AT-LEVELS mechanism.

  Pre-reg:  analysis/recommendations/prereg-structure-shift-confirmation-2026-07-28.json
  Doctrine: markdown/doctrine/J-MARKET-PHILOSOPHY.md ("Once price reaches a key level, I
            look for a shift in structure -- a failed push, a rejection, a break of
            momentum, higher lows forming after demand, lower highs forming after supply.")

Gap 1 named in the doctrine file: the engine confirms level-tied setups with LAGGING
EMA state (ribbon stack / HTF agreement) instead of watching for the structural shift
itself. These two functions are the structural shift detector that
``backtest/lib/filters.py`` wires in as a flag-gated OR-alternative (never a removal) to
those lagging confirmations -- see ``structure_shift_confirmation`` in
``evaluate_bearish_setup`` / ``evaluate_bullish_setup``.

FRAMING (fits the engine's per-tick n-2 stateless trigger convention -- no watch-state,
no persistence across ticks): ``bar_idx`` is "now" -- the current trigger bar under
evaluation this tick, in ``filters.BarContext``'s own sense (the bar that just closed).
The detector scans BACKWARD from ``bar_idx`` for an earlier rejection/reclaim bar ``R``
within the last ``k`` bars, then checks whether ``bar_idx`` ITSELF is the bar that
completes the structural shift against ``R``. The confirming bar is always ``bar_idx`` --
never a bar found by scanning forward -- so a live per-tick call and the historical
replay's forward scan land on the same entry bar: the tick whose own bar closes the
sequence is the one that acts, and its close is the entry price (pre-reg
``predicate_frozen`` + ENTRY-BAR-CONVENTION-RULING-2026-07-25 "entry at the confirmation
bar close").

Both functions are PURE / stateless / causal: they read only ``bars`` up to and
including ``bar_idx`` and ``levels_active``. No I/O, no mutation, nothing forward of
``bar_idx`` is ever touched.
"""

from __future__ import annotations

from typing import Optional, TypedDict

import pandas as pd

__all__ = ["StructureShift", "detect_structure_shift_bear", "detect_structure_shift_bull"]

# pre-reg "predicate_frozen.K_primary" (K_sensitivity=2 is the ONLY other point in the
# frozen search space -- both are just the `k` argument, no other knob exists per pre-reg's
# own "no_other_knobs" clause).
STRUCTURE_SHIFT_K_DEFAULT = 3


class StructureShift(TypedDict):
    """Descriptor for a confirmed structure shift.

    ``rejection_bar_idx``: index of the R bar (the level rejection for the bear side, the
        level reclaim for the bull side -- one field name for both, mirroring the pre-reg's
        single frozen descriptor shape).
    ``level``: the level R rejected (bear) or reclaimed (bull).
    ``confirmed_at_idx``: always equals the ``bar_idx`` passed in -- the confirming bar,
        which per the framing above is always "now."
    """

    rejection_bar_idx: int
    level: float
    confirmed_at_idx: int


def detect_structure_shift_bear(
    bars: pd.DataFrame,
    bar_idx: int,
    levels_active: list[float],
    k: int = STRUCTURE_SHIFT_K_DEFAULT,
) -> Optional[StructureShift]:
    """Bear structure-shift confirmation ending at ``bar_idx`` (the current trigger bar).

    Scans the ``k`` bars immediately BEFORE ``bar_idx`` (``[bar_idx-k, bar_idx-1]``,
    most-recent first) for a bar ``R`` that is itself a level rejection -- using the
    existing ``filters.detect_level_rejection`` semantics against ``levels_active`` (bar
    high above the level, close below it; picks the highest such level on that bar).

    For the first qualifying ``R`` found (scanning newest-to-oldest -- the freshest failed
    push is the most relevant one), checks whether ``bar_idx`` completes the shift:
    ``bar_idx``'s HIGH is a LOWER HIGH than R's high, AND ``bar_idx``'s LOW trades below
    ``min(R.low, R's rejected level)`` -- a failed retest followed by a break of both the
    prior swing low and the level itself ("lower highs forming after supply").

    Returns the ``StructureShift`` descriptor on the first qualifying ``R``, or ``None`` if
    no bar in the window produces both a rejection AND a bar_idx confirmation against it.

    Pure / causal: reads only ``bars.iloc[j]`` for ``j <= bar_idx``. Never mutates ``bars``.
    """
    from .filters import detect_level_rejection  # function-local: breaks the filters<->
    # structure_shift import cycle (filters.py imports this module at module scope; this
    # module must NOT import filters.py at module scope in return -- same pattern already
    # used by filters.py's own vwap_reclaim_failed_break delegator for the identical reason).

    if bars is None or not levels_active:
        return None
    try:
        n = len(bars)
    except TypeError:
        return None
    if bar_idx is None or bar_idx < 1 or bar_idx >= n:
        return None

    confirm_bar = bars.iloc[bar_idx]
    try:
        confirm_high = float(confirm_bar["high"])
        confirm_low = float(confirm_bar["low"])
    except (KeyError, TypeError, ValueError):
        return None

    window_start = max(0, bar_idx - k)
    for r_idx in range(bar_idx - 1, window_start - 1, -1):
        r_bar = bars.iloc[r_idx]
        level = detect_level_rejection(r_bar, levels_active)
        if level is None:
            continue
        r_high = float(r_bar["high"])
        r_low = float(r_bar["low"])
        if confirm_high < r_high and confirm_low < min(r_low, level):
            return StructureShift(
                rejection_bar_idx=r_idx,
                level=level,
                confirmed_at_idx=bar_idx,
            )
    return None


def detect_structure_shift_bull(
    bars: pd.DataFrame,
    bar_idx: int,
    levels_active: list[float],
    k: int = STRUCTURE_SHIFT_K_DEFAULT,
) -> Optional[StructureShift]:
    """Bull mirror of ``detect_structure_shift_bear``.

    Scans the ``k`` bars immediately before ``bar_idx`` for a bar ``R`` that is itself a
    level reclaim (``filters.detect_level_reclaim`` semantics: bar low below the level,
    close above it; picks the lowest such level).

    For the first qualifying ``R`` (newest-to-oldest), checks whether ``bar_idx`` completes
    the shift: ``bar_idx``'s LOW is a HIGHER LOW than R's low AND above the level, AND
    ``bar_idx``'s HIGH exceeds R's high ("higher lows forming after demand").

    Returns the ``StructureShift`` descriptor or ``None``. Pure / causal, same contract as
    the bear detector.
    """
    from .filters import detect_level_reclaim  # function-local: see detect_structure_shift_bear.

    if bars is None or not levels_active:
        return None
    try:
        n = len(bars)
    except TypeError:
        return None
    if bar_idx is None or bar_idx < 1 or bar_idx >= n:
        return None

    confirm_bar = bars.iloc[bar_idx]
    try:
        confirm_high = float(confirm_bar["high"])
        confirm_low = float(confirm_bar["low"])
    except (KeyError, TypeError, ValueError):
        return None

    window_start = max(0, bar_idx - k)
    for r_idx in range(bar_idx - 1, window_start - 1, -1):
        r_bar = bars.iloc[r_idx]
        level = detect_level_reclaim(r_bar, levels_active)
        if level is None:
            continue
        r_high = float(r_bar["high"])
        r_low = float(r_bar["low"])
        if confirm_low > r_low and confirm_low > level and confirm_high > r_high:
            return StructureShift(
                rejection_bar_idx=r_idx,
                level=level,
                confirmed_at_idx=bar_idx,
            )
    return None
