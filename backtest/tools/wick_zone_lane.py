"""wick_zone_lane.py -- shelf_wick_hold_closed_bar_v1: the WICK-ENTRY-LANE detector
(pre-reg: analysis/recommendations/prereg-wick-lane-2026-07-31.json, frozen 2026-07-31
16:47:56 ET BEFORE any run).

J directive 2026-07-31: "have one of the risky accounts get in off the wick." The shape:
price wicks INTO a PERSISTENT multi-week shelf zone and rejects it WITHOUT a close-cross
-- J's 737.68 call on 2026-07-31 (SHELF 737.03-738.63, 10:15 bar low 737.68, V-recovery)
and the 2026-07-30 ~12:40 wick to 737.75 into the same shelf (recovery bar 12:45).

GRAVEYARD CONSTRAINT HONORED (ZONE-WIDTH-2026-07-28): banding the CLOSE-cross detector
tested negative on both pre-registered bands. This is NOT a widened cross -- the trigger
is a WICK-TOUCH (bar low penetrates INTO the zone) + RECOVERY (close back at/above the
zone top), i.e. the zone is never lost on a close at all.

TWO SEPARATELY-NAMED VARIANTS (lane brief mandate):
  * shelf_wick_hold_closed_bar_v1  -- THIS module's detect_* functions. Evaluated on a
    CLOSED 5m bar; historically testable; the 390-day study runs this one.
  * shelf_wick_hold_live_tick_v1   -- forward-only SPEC, deliberately NOT implemented as
    a backtest (no historical tick/bid path exists in the cache): intra-bar, the tick low
    prints inside a persistent shelf zone AND the live bid recovers to >= zone_hi - 0.10
    before the bar closes -> immediate entry (the standing Bold live-trigger convention:
    Bold enters on live bid crossing a level, not a closed bar). Forward shadow only.

ZONE UNIVERSE (the "w>=4" restriction): daily_context.py shelf zones ONLY -- the levels
compiler v2's weight scale (refresh_levels_intraday.py) assigns w5 to multi-week shelves
and nothing else reaches w4 (prior-day HLC=3, intraday=2). Zones for session D are
computed from daily SIP bars in [D - 60 calendar days, D) -- strictly-prior completed
sessions, no look-ahead (C6) -- through the PRODUCTION functions
daily_context._find_shelf_candidates + _merge_shelf_candidates (imported, never
reimplemented; band $1.60 / >=3 touches / >=10 session span).

PERSISTENCE (lane 3's FRESH/PERSISTENT artifacts had not landed at freeze; disclosed
fallback per the lane brief): a zone at D is PERSISTENT iff its band overlaps some zone
computed identically for the PRIOR RTH session.

All wick constants are the PRODUCTION bear wick-detector module constants imported from
backtest/lib/filters.py (WICK_MIN_PCT_OF_RANGE=0.50, WICK_MIN_DOLLARS=0.15,
WICK_CLOSE_TOLERANCE=0.10). ZERO new tunables in this module.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from typing import Optional

_REPO = Path(__file__).resolve().parents[1]           # backtest/
_ROOT = _REPO.parent                                    # repo root
for _p in (str(_REPO), str(_ROOT / "setup" / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib.filters import (  # noqa: E402  -- PRODUCTION constants, never re-declared
    WICK_CLOSE_TOLERANCE,
    WICK_MIN_DOLLARS,
    WICK_MIN_PCT_OF_RANGE,
)
from daily_context import (  # noqa: E402  -- PRODUCTION shelf pipeline, never re-implemented
    _find_shelf_candidates,
    _merge_shelf_candidates,
)

ZONE_LOOKBACK_CALENDAR_DAYS = 60   # daily_context.LOOKBACK_DAYS -- the live compiler's window


# ---------------------------------------------------------------------------- zones

def shelf_zones_for_session(daily_bars: list[dict], session: dt.date) -> list[dict]:
    """Shelf zones IN FORCE coming into `session`: production candidate scan + merge over
    the daily bars in [session - 60 calendar days, session). Bars must be dicts with
    date/o/h/l/c/v keys (daily_context's own schema), chronological. STRICTLY-PRIOR bars
    only -- passing today's (even partial) bar is a look-ahead bug the tests RED on."""
    lo_date = (session - dt.timedelta(days=ZONE_LOOKBACK_CALENDAR_DAYS)).isoformat()
    hi_date = session.isoformat()
    window = [b for b in daily_bars if lo_date <= b["date"] < hi_date]
    return _merge_shelf_candidates(_find_shelf_candidates(window))


def zones_overlap(a: dict, b: dict) -> bool:
    return not (a["band_high"] < b["band_low"] or a["band_low"] > b["band_high"])


def classify_persistent(zones_today: list[dict], zones_prior_session: list[dict]) -> list[dict]:
    """PERSISTENT subset of today's zones: band overlaps some prior-session zone."""
    return [z for z in zones_today
            if any(zones_overlap(z, p) for p in zones_prior_session)]


# ---------------------------------------------------------------------------- predicates

def detect_shelf_wick_hold_bull(bar, persistent_zones: list[dict]) -> Optional[dict]:
    """shelf_wick_hold_closed_bar_v1, BULL side (primary -- J's named shape).

    For persistent shelf zone [lo, hi], on a closed 5m bar:
      F1 open >= lo                       (bar begins at/above the shelf: a support test,
                                           not an upward breakout from below)
      F2 low <= hi                        (wick penetrates INTO the zone)
      F3 close >= hi - WICK_CLOSE_TOLERANCE  (recovered to/above the zone top -- the zone
                                           was never lost on a close; NOT a widened cross)
      F4 (close - low) >= max(WICK_MIN_DOLLARS, WICK_MIN_PCT_OF_RANGE * (high - low))

    Tiebreak: highest band_high (the nearest defended shelf). Returns the fired zone dict
    (band_low/band_high/...) or None. trigger_level for the structure stop is the FAR edge
    (band_low): invalidation = the zone actually fails on a closed bar.
    """
    if not persistent_zones:
        return None
    o = float(bar["open"]); h = float(bar["high"])
    lo_ = float(bar["low"]); c = float(bar["close"])
    bar_range = h - lo_
    if bar_range <= 0:
        return None
    wick = c - lo_
    if wick < max(WICK_MIN_DOLLARS, WICK_MIN_PCT_OF_RANGE * bar_range):
        return None                                             # F4
    fired = [z for z in persistent_zones
             if o >= z["band_low"]                              # F1
             and lo_ <= z["band_high"]                          # F2
             and c >= z["band_high"] - WICK_CLOSE_TOLERANCE]    # F3
    if not fired:
        return None
    return max(fired, key=lambda z: z["band_high"])


def detect_shelf_wick_hold_bear(bar, persistent_zones: list[dict]) -> Optional[dict]:
    """shelf_wick_hold_closed_bar_v1, BEAR side (secondary -- exact mirror at an overhead
    shelf): F1 open <= hi; F2 high >= lo; F3 close <= lo + WICK_CLOSE_TOLERANCE;
    F4 (high - close) >= same threshold. Tiebreak: lowest band_low. trigger_level for the
    structure stop = band_high (far edge)."""
    if not persistent_zones:
        return None
    o = float(bar["open"]); h = float(bar["high"])
    lo_ = float(bar["low"]); c = float(bar["close"])
    bar_range = h - lo_
    if bar_range <= 0:
        return None
    wick = h - c
    if wick < max(WICK_MIN_DOLLARS, WICK_MIN_PCT_OF_RANGE * bar_range):
        return None                                             # F4
    fired = [z for z in persistent_zones
             if o <= z["band_high"]                             # F1
             and h >= z["band_low"]                             # F2
             and c <= z["band_low"] + WICK_CLOSE_TOLERANCE]     # F3
    if not fired:
        return None
    return min(fired, key=lambda z: z["band_low"])
