"""Guard: the multi-bar `sequence_reclaim` trigger is DEAD-COUPLED to the
single-bar straddle (SLICE 3 of the #1 project thread — bull-unblock).

Context (queue BULL-UNBLOCK-REPLAY-PROBE — the rig has never filled an
ENTER_BULL in 2544 lifetime decisions):
  SLICE 1 retired `block_elite_bull` (net -$241, KEEP). SLICE 2 audited the
  structural `min_triggers_bull` lever (n=8, thin/fragile, NOT proposable).
  SLICE 3 (this guard) locates the LAST untested bull-unblock lever.

The finding (empirically proven, see the result JSON):
  `detect_sequence_reclaim` — the ONLY trigger that could catch a SMOOTH uptrend
  that never prints a single-bar straddle — is structurally coupled OFF. In
  `evaluate_bullish_setup` the level_state it needs is looked up ONLY when
  `reclaim_level is not None` (filters.py ~L937), and `reclaim_level` comes from
  `detect_level_reclaim` (the single-bar straddle). So sequence_reclaim can only
  ever appear as a REDUNDANT CO-TRIGGER of the straddle it depends on — never as
  an independent path. That is the exact structural root of "bull unreachable on
  smooth uptrends."

Why guard it:
  Decoupling sequence_reclaim (looking up its level_state independently of the
  straddle) is the last untested bull-unblock lever, but it is a filters.py
  LOGIC change (rail-4, J-gated) and the 25-day OPRA window cannot prove any bull
  sub-lever to significance regardless (SLICE 1+2). So the honest conclusion is
  the 0DTE-SPY bull frontier is DATA-GATED — the decouple is filed for a future
  WIDER-DATA probe. This guard PINS the current coupling as a known structural
  fact: if a future refactor silently decouples it (Case A starts firing
  sequence_reclaim), the guard RE-REDs so the bull entry surface change is a
  CONSCIOUS decision that re-runs the bull A/B (C14 dead-knob / C7).
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
for _p in (str(BACKTEST), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib.filters import (  # noqa: E402
    BarContext,
    LevelState,
    detect_level_reclaim,
    detect_sequence_reclaim,
    evaluate_bullish_setup,
)

LEVEL = 745.0
# Disable every filter EXCEPT 11 (the trigger filter) so the test isolates the
# trigger-assembly coupling and nothing else.
_ISOLATE_F11 = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12]


def _independent_reclaim_state() -> LevelState:
    """A broken_to_support level with 3 progressively HIGHER lows — the exact
    structure `detect_sequence_reclaim` fires on, present INDEPENDENT of any
    single-bar straddle."""
    return LevelState(
        price=LEVEL,
        role="broken_to_support",
        bounce_history=[
            {"low_reached": 743.0},
            {"low_reached": 744.0},
            {"low_reached": 744.5},
        ],
    )


def _ctx(bar: pd.Series, level_state: LevelState) -> BarContext:
    return BarContext(
        bar_idx=1,
        timestamp_et=dt.datetime(2026, 6, 15, 10, 30),
        bar=bar,
        prior_bars=pd.DataFrame([bar, bar]),
        ribbon_now=None,
        ribbon_history=[],
        vix_now=15.0,
        vix_prior=15.0,
        vol_baseline_20=1.0,
        range_baseline_20=1.0,
        levels_active=[LEVEL],
        multi_day_levels=[],
        htf_15m_stack="BULL",
        level_states={str(LEVEL): level_state},
    )


# Case A — smooth uptrend: the bar sits ENTIRELY ABOVE the level, so there is no
# single-bar straddle (detect_level_reclaim -> None).
_BAR_NO_STRADDLE = pd.Series(
    {"open": 746.2, "high": 747.0, "low": 746.0, "close": 746.5, "volume": 1000}
)
# Case B — control: the bar straddles the level (low < level < close), so
# detect_level_reclaim returns the level.
_BAR_STRADDLE = pd.Series(
    {"open": 744.5, "high": 746.0, "low": 744.0, "close": 745.5, "volume": 1000}
)


def test_bite_independent_sequence_reclaim_would_fire():
    """NON-VACUOUS BITE: the crafted level_state genuinely satisfies
    detect_sequence_reclaim on its own — so the coupling guard below is proving a
    REAL suppression, not asserting on a state that never fires anyway."""
    assert detect_sequence_reclaim(_independent_reclaim_state()) is True


def test_no_straddle_means_no_reclaim_level():
    assert detect_level_reclaim(_BAR_NO_STRADDLE, [LEVEL]) is None


def test_straddle_produces_reclaim_level():
    assert detect_level_reclaim(_BAR_STRADDLE, [LEVEL]) == LEVEL


def test_sequence_reclaim_is_dead_without_straddle():
    """THE COUPLING (golden): with a valid independent multi-bar reclaim present
    but NO single-bar straddle, `sequence_reclaim` is NOT in triggers_fired and
    filter 11 blocks. The multi-bar reclaim is structurally dead on smooth
    uptrends. If a future decouple lands, this FAILS -> forces a conscious re-audit."""
    res = evaluate_bullish_setup(
        _ctx(_BAR_NO_STRADDLE, _independent_reclaim_state()),
        disable_filters=_ISOLATE_F11,
        min_triggers=1,
    )
    assert res.reclaim_level is None
    assert "sequence_reclaim" not in res.triggers_fired
    assert res.triggers_fired == []
    assert 11 in res.blockers


def test_sequence_reclaim_fires_only_as_costraddle_cotrigger():
    """CONTROL: the SAME level_state, but now the bar straddles the level.
    sequence_reclaim DOES fire — proving it CAN fire, only ever coupled to the
    single-bar straddle (redundant co-trigger), never independently."""
    res = evaluate_bullish_setup(
        _ctx(_BAR_STRADDLE, _independent_reclaim_state()),
        disable_filters=_ISOLATE_F11,
        min_triggers=1,
    )
    assert res.reclaim_level == LEVEL
    assert "level_reclaim" in res.triggers_fired
    assert "sequence_reclaim" in res.triggers_fired
    assert 11 not in res.blockers
