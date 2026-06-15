"""REGIME_SWITCHER classifier — lookahead-safe regime assignment.

Implements the decision tree from strategy/regime_switcher.md Section 3.
Runs ONCE at 09:30:00 ET and assigns the day to one of:

    MACRO_VETO   (skip the day entirely)
    EVENT_VOL    -> OPENING_DRIVE_FADE (ODF)
    GAP_DAY      -> v14_ENHANCED
    TREND_DAY    -> SNIPER
    CHOP         -> SNIPER or VWAP_REJECTION_PRIME (sub-decision)
    FALLBACK     -> SNIPER (spine default)

CRITICAL: every input MUST be lookahead-safe (computable from data available
strictly BEFORE 09:30:01 ET). No today-after-09:30 data permitted.

Per CLAUDE.md OP 11/13: pure Python, no LLM in loop. Per OP 2: no
speculative branches — every comparison maps to an evidence-backed rule
in the spec.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------- Regime + strategy enums (kept as plain strings to be JSON-safe) ----------

REGIME_MACRO_VETO = "MACRO_VETO"
REGIME_EVENT_VOL = "EVENT_VOL"
REGIME_GAP_DAY = "GAP_DAY"
REGIME_TREND_DAY = "TREND_DAY"
REGIME_CHOP = "CHOP"
REGIME_FALLBACK = "FALLBACK"

STRATEGY_NONE = "NONE"
STRATEGY_ODF = "ODF"
STRATEGY_SNIPER = "SNIPER"
STRATEGY_V14E = "v14_enhanced"
STRATEGY_VWAP = "VWAP"

ALL_REGIMES = (
    REGIME_MACRO_VETO,
    REGIME_EVENT_VOL,
    REGIME_GAP_DAY,
    REGIME_TREND_DAY,
    REGIME_CHOP,
    REGIME_FALLBACK,
)

ALL_STRATEGIES = (
    STRATEGY_NONE,
    STRATEGY_ODF,
    STRATEGY_SNIPER,
    STRATEGY_V14E,
    STRATEGY_VWAP,
)


# ---------- Knob defaults (per spec Section 3 + Section 7) ----------

@dataclass(frozen=True)
class RegimeKnobs:
    """All thresholds used by classify_regime. Defaults match spec Section 3.

    Each knob is the upper/lower bound for a regime transition. Stage 1 grid
    sweeps the 6 most material knobs (per spec Section 7); the remaining 3
    are locked at their default.
    """

    # MACRO veto window in hours (spec §3 step 1)
    macro_proximity_hr: float = 24.0

    # EVENT_VOL thresholds (spec §3 step 2)
    vix_high_thresh: float = 22.0
    vix_jump_thresh: float = 1.5

    # GAP_DAY threshold (spec §3 step 3)
    gap_thresh: float = 1.00

    # TREND_DAY thresholds (spec §3 step 4)
    range_thresh: float = 5.00
    vix_low_thresh: float = 17.0

    # CHOP gate (spec §3 step 5)
    gap_chop_thresh: float = 1.00
    vix_chop_thresh: float = 20.0
    range_chop_thresh: float = 4.00

    # CHOP sub-decision: "SNIPER" or "VWAP" (spec §3 step 5 sub-decision)
    chop_default_strategy: str = STRATEGY_SNIPER


# ---------- Input bundle (frozen at 09:30:00 ET) ----------

@dataclass(frozen=True)
class RegimeInputs:
    """All lookahead-safe classifier inputs.

    Per spec Section 3 Inputs table:
      - gap_abs:               abs(spy_open_09:30 - spy_prior_close_16:00)
      - prior_range:           prior_session_high - prior_session_low (RTH)
      - vix_spot:              spot VIX at 09:30:00 ET
      - vix_change_1d:         vix_today_open - vix_prior_close
      - macro_proximity_hr:    hours until/since next FOMC/CPI/NFP (None = no event)
      - is_event_macro:        True if the proximate event is in {FOMC, CPI, NFP}
    """

    gap_abs: float
    prior_range: float
    vix_spot: float
    vix_change_1d: float
    macro_proximity_hr: Optional[float] = None
    is_event_macro: bool = False  # event must be FOMC/CPI/NFP to MACRO_VETO


# ---------- Decision tree (TOP-DOWN, first match wins) ----------

def classify_regime(
    gap_abs: float,
    prior_range: float,
    vix_spot: float,
    vix_change_1d: float,
    macro_proximity_hr: Optional[float],
    knobs: RegimeKnobs,
    is_event_macro: bool = False,
) -> str:
    """Apply the spec Section 3 decision tree to lookahead-safe inputs.

    Returns one of the REGIME_* strings.

    Decision order (precedence locked):
      1. MACRO_VETO  - macro event within window AND event in {FOMC, CPI, NFP}
      2. EVENT_VOL   - vix_spot > vix_high_thresh OR vix_change_1d > vix_jump_thresh
      3. GAP_DAY     - gap_abs > gap_thresh
      4. TREND_DAY   - prior_range > range_thresh AND vix_spot < vix_low_thresh
      5. CHOP        - gap_abs < gap_chop_thresh AND vix_spot < vix_chop_thresh
      6. FALLBACK    - none of the above
    """
    # 1. MACRO_VETO
    if (
        macro_proximity_hr is not None
        and macro_proximity_hr <= knobs.macro_proximity_hr
        and is_event_macro
    ):
        return REGIME_MACRO_VETO

    # 2. EVENT_VOL
    if vix_spot > knobs.vix_high_thresh or vix_change_1d > knobs.vix_jump_thresh:
        return REGIME_EVENT_VOL

    # 3. GAP_DAY
    if gap_abs > knobs.gap_thresh:
        return REGIME_GAP_DAY

    # 4. TREND_DAY
    if prior_range > knobs.range_thresh and vix_spot < knobs.vix_low_thresh:
        return REGIME_TREND_DAY

    # 5. CHOP
    if gap_abs < knobs.gap_chop_thresh and vix_spot < knobs.vix_chop_thresh:
        return REGIME_CHOP

    # 6. FALLBACK
    return REGIME_FALLBACK


def classify_regime_inputs(inputs: RegimeInputs, knobs: RegimeKnobs) -> str:
    """Convenience overload taking a RegimeInputs bundle."""
    return classify_regime(
        gap_abs=inputs.gap_abs,
        prior_range=inputs.prior_range,
        vix_spot=inputs.vix_spot,
        vix_change_1d=inputs.vix_change_1d,
        macro_proximity_hr=inputs.macro_proximity_hr,
        knobs=knobs,
        is_event_macro=inputs.is_event_macro,
    )


def regime_to_strategy(regime: str, knobs: RegimeKnobs, prior_range: Optional[float] = None) -> str:
    """Map a regime label to the active sub-strategy id.

    Per spec Section 3:
      - MACRO_VETO -> NONE  (skip the day)
      - EVENT_VOL  -> ODF   (opening drive fade)
      - GAP_DAY    -> v14_enhanced  (early-entry catches morning trend)
      - TREND_DAY  -> SNIPER  (level break momentum)
      - CHOP       -> sub-decision: VWAP if prior_range < range_chop_thresh else
                                    SNIPER (or whichever chop_default_strategy says)
      - FALLBACK   -> SNIPER  (spine default - most positive quarters)

    The CHOP sub-decision uses prior_range vs knobs.range_chop_thresh.
    If prior_range is None (caller didn't pass it), the sub-decision falls
    through to chop_default_strategy.
    """
    if regime == REGIME_MACRO_VETO:
        return STRATEGY_NONE
    if regime == REGIME_EVENT_VOL:
        return STRATEGY_ODF
    if regime == REGIME_GAP_DAY:
        return STRATEGY_V14E
    if regime == REGIME_TREND_DAY:
        return STRATEGY_SNIPER

    if regime == REGIME_CHOP:
        # Sub-decision: tight range -> VWAP magnet; wider chop -> SNIPER (strict filters)
        if prior_range is not None and prior_range < knobs.range_chop_thresh:
            return STRATEGY_VWAP
        # Larger chop or no prior_range provided -> chop_default_strategy
        if knobs.chop_default_strategy == STRATEGY_VWAP:
            return STRATEGY_VWAP
        return STRATEGY_SNIPER

    # FALLBACK -> spine default
    return STRATEGY_SNIPER


def regime_to_strategy_full(
    regime: str,
    knobs: RegimeKnobs,
    inputs: Optional[RegimeInputs] = None,
) -> str:
    """Like regime_to_strategy but takes the RegimeInputs bundle (preferred)."""
    pr = inputs.prior_range if inputs is not None else None
    return regime_to_strategy(regime, knobs, prior_range=pr)
