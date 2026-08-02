"""Guards for BULL-VIX-SOFT-MODE-SOLE-BLOCKER-2026-08-03 (vix_soft_mode_bull).

Pre-reg: analysis/recommendations/prereg-bull-vix-soft-mode-2026-08-03.json (arms_frozen.
ARM_C_bull_soft_new_flag). Motivating study: analysis/deep-research/
FREQUENCY-CEILING-2026-08-03.md sec 4.

WHAT THIS PINS (C14 dead-knob discipline -- a flag that silently no-ops would make the whole
downstream A/B vacuous):

  1. Signature: `vix_soft_mode_bull` exists on `evaluate_bullish_setup`, default False
     (mirrors the prereg's own verification method: "confirmed by inspect.signature").
  2. VARY-AND-ASSERT, direction 1 (flag OFF == pre-existing behavior): when filter 8 would
     block (VIX elevated-or-rising) and the flag is False (default), blocker 8 fires and the
     bar is refused -- byte-identical to the function's behavior before this change existed.
  3. VARY-AND-ASSERT, direction 2 (flag ON changes behavior): the SAME blocked bar, flag
     True -- blocker 8 is gone, the bar PASSES, and bull_score is EXACTLY 1 lower than the
     equivalent bar where VIX passes filter 8 cleanly (isolates the demerit to exactly -1,
     matching bear's vix_soft_demerit mechanism).
  4. NO-OP WHEN INERT: when filter 8 was never going to block (VIX already passes), the flag
     produces a BYTE-IDENTICAL result whether True or False -- proves the flag only touches
     the one code path it claims to, nothing else.
  5. Bear/bull namespace non-collision: `vix_soft_mode_bull=True` never reaches
     `evaluate_bearish_setup` and has zero effect on bear-side scoring (mirrors the
     FREQUENCY-CEILING-2026-08-03 guard convention for filter-number namespacing).
  6. engine.score parity: `lib.engine.score.score_bull` (the generic **kwargs passthrough
     the live heartbeat_core.py path and every backtest tool both route through) is a
     faithful wrapper for the new kwarg -- proven directly, not assumed. This is the exact
     invariant orchestrator.py's "ENGINE-SCORE ASSERT-AGREE" per-bar assertion depends on;
     were it broken, any real run_backtest(vix_soft_mode_bull=True) call would crash with an
     AssertionError the first time filter 8 actually fires (GAMMA_ENGINE_SCORE_ASSERT=1 by
     default) -- which is exactly the regression this guard is designed to catch, and exactly
     the bug this authorship session found and fixed (orchestrator.py's ENGINE-SCORE
     ASSERT-AGREE oracle `bull_kwargs` dict was missing `vix_soft_mode_bull=vix_soft_mode_bull`
     until patched).

RED-PROOF (performed during authorship, this session): temporarily reverted the filters.py
`if vix_soft_mode_bull: vix_soft_demerit_bull = True / else: blockers.append(8)` branch back
to an unconditional `blockers.append(8)` (i.e. simulated the flag never having been built) --
`test_soft_mode_on_removes_blocker_and_costs_exactly_one_point` and
`test_engine_score_wraps_new_kwarg_faithfully` both failed exactly as expected (8 still in
blockers, passed stayed False). Reverted; full file green again.

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_bull_vix_soft_mode_2026_08_03.py -q
"""
from __future__ import annotations

import datetime as dt
import inspect
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
for _p in (str(BACKTEST), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib.engine import score_bull  # noqa: E402
from lib.filters import BarContext, evaluate_bearish_setup, evaluate_bullish_setup  # noqa: E402
from lib.ribbon import RibbonState  # noqa: E402


def _bull_ribbon(spread_cents: float = 50.0) -> RibbonState:
    return RibbonState(fast=541.0, pivot=540.0, slow=539.0, spread_cents=spread_cents, stack="BULL")


def _make_bar() -> pd.Series:
    # Green bar, close (541.2) above the active level (540.5) -> level_reclaim trigger.
    # Volume 750k >= 0.7 * 1,000,000 vol_baseline -> buyer-pressure filter 10 passes.
    return pd.Series({"open": 540.0, "high": 541.5, "low": 539.8, "close": 541.2, "volume": 750_000})


def _prior_bars() -> pd.DataFrame:
    return pd.DataFrame(
        [{"open": 540.0, "high": 540.4, "low": 539.6, "close": 540.0, "volume": 800_000}
         for _ in range(30)]
    )


def _bull_ctx(vix_now: float, vix_prior: float) -> BarContext:
    """Identical construction to test_engine_score_parity.py's _bull_ctx (clean_pass shape)
    with only vix_now/vix_prior varied -- every OTHER filter passes cleanly so filter 8 is
    provably the SOLE blocker in the failing-VIX cases below (mirrors the prereg's own
    'sole-blocker' cohort definition)."""
    ts = dt.datetime(2026, 5, 20, 10, 0, tzinfo=dt.timezone(dt.timedelta(hours=-4)))
    return BarContext(
        bar_idx=4, timestamp_et=ts, bar=_make_bar(), prior_bars=_prior_bars(),
        ribbon_now=_bull_ribbon(), ribbon_history=[_bull_ribbon()],
        vix_now=vix_now, vix_prior=vix_prior,
        vol_baseline_20=1_000_000.0, range_baseline_20=1.0,
        levels_active=[540.5], multi_day_levels=[], htf_15m_stack="BULL", level_states={},
    )


# VIX passes filter 8 cleanly (< 17.20): the baseline "what would this bar have scored
# without any VIX friction at all" reference point.
_VIX_PASSING = dict(vix_now=17.10, vix_prior=17.30)
# VIX fails filter 8 (rising, >= 17.20) but stays under the separate hard cap (filter 9,
# < 22.0) -- SOLE blocker per the prereg's own cohort definition.
_VIX_SOLE_BLOCKS_F8 = dict(vix_now=17.40, vix_prior=17.10)


# --------------------------------------------------------------------- 1. signature
def test_signature_has_vix_soft_mode_bull_default_false():
    params = inspect.signature(evaluate_bullish_setup).parameters
    assert "vix_soft_mode_bull" in params, (
        "evaluate_bullish_setup has no vix_soft_mode_bull parameter -- the mirrored flag "
        "was never added")
    assert params["vix_soft_mode_bull"].default is False


# --------------------------------------------------------------------- 2/3. vary-and-assert
def test_default_off_blocker_8_fires_when_vix_fails():
    """Direction 1: flag OFF (default) on a VIX-failing bar -- byte-identical to pre-change
    behavior. Sanity pre-condition: filter 8 really is the SOLE blocker here."""
    res = evaluate_bullish_setup(_bull_ctx(**_VIX_SOLE_BLOCKS_F8))
    assert res.blockers == [8], f"expected filter 8 as the SOLE blocker, got {res.blockers}"
    assert res.passed is False


def test_soft_mode_on_removes_blocker_and_costs_exactly_one_point():
    """Direction 2: flag ON on the SAME VIX-failing bar -- blocker gone, setup passes, and
    the score is exactly the clean-VIX score minus 1 (isolates the demerit)."""
    clean = evaluate_bullish_setup(_bull_ctx(**_VIX_PASSING))
    soft = evaluate_bullish_setup(_bull_ctx(**_VIX_SOLE_BLOCKS_F8), vix_soft_mode_bull=True)

    assert 8 not in soft.blockers, f"filter 8 still blocking under vix_soft_mode_bull=True: {soft.blockers}"
    assert soft.blockers == [], f"expected zero blockers once the sole blocker is demerited, got {soft.blockers}"
    assert soft.passed is True
    assert clean.passed is True
    assert soft.bull_score == clean.bull_score - 1, (
        f"expected exactly -1 demerit vs the clean-VIX bar: clean={clean.bull_score} "
        f"soft={soft.bull_score}")
    # Trigger set / reclaim level must be unaffected -- only the VIX gate changed.
    assert soft.triggers_fired == clean.triggers_fired
    assert soft.reclaim_level == clean.reclaim_level


# --------------------------------------------------------------------- 4. no-op when inert
def test_flag_is_byte_identical_no_op_when_vix_already_passes():
    """When filter 8 was never going to block, the flag must have ZERO effect -- proves this
    is a scoped, single-path change, not a broader behavior shift."""
    ctx = _bull_ctx(**_VIX_PASSING)
    off = evaluate_bullish_setup(ctx, vix_soft_mode_bull=False)
    on = evaluate_bullish_setup(ctx, vix_soft_mode_bull=True)
    assert off.passed == on.passed
    assert off.bull_score == on.bull_score
    assert off.blockers == on.blockers
    assert off.triggers_fired == on.triggers_fired
    assert off.reclaim_level == on.reclaim_level


# --------------------------------------------------------------------- 5. namespace non-collision
def test_bear_side_never_sees_the_bull_flag():
    """vix_soft_mode_bull is a bull-only parameter -- evaluate_bearish_setup has no such
    kwarg at all (passing it would be a TypeError, proving there is no shared/aliased state),
    and a bear ctx built to fail bear's OWN vix_soft_mode-less filter 8 still blocks exactly
    as before regardless of what the bull-side flag is doing elsewhere in the same process."""
    assert "vix_soft_mode_bull" not in inspect.signature(evaluate_bearish_setup).parameters
    with pytest.raises(TypeError):
        evaluate_bearish_setup(_bull_ctx(**_VIX_SOLE_BLOCKS_F8), vix_soft_mode_bull=True)  # type: ignore[call-arg]


# --------------------------------------------------------------------- 6. engine.score parity
def test_engine_score_wraps_new_kwarg_faithfully():
    """The generic **kwargs passthrough orchestrator.py's ENGINE-SCORE ASSERT-AGREE relies on
    (and the same surface heartbeat_core.py's score_params.bull_kwargs / any future live
    wiring would route through): lib.engine.score.score_bull must return a field-identical
    result to calling filters.evaluate_bullish_setup directly, for BOTH flag values, on the
    SOLE-BLOCKED bar. This is the exact invariant whose breakage this session found (missing
    vix_soft_mode_bull in orchestrator.py's oracle bull_kwargs dict) would have crashed every
    real run_backtest(vix_soft_mode_bull=True) call under GAMMA_ENGINE_SCORE_ASSERT=1
    (default) the first time filter 8 fired."""
    ctx = _bull_ctx(**_VIX_SOLE_BLOCKS_F8)
    for flag in (False, True):
        direct = evaluate_bullish_setup(ctx, vix_soft_mode_bull=flag)
        via_engine = score_bull(ctx, vix_soft_mode_bull=flag)
        assert via_engine.passed == direct.passed, f"flag={flag}: passed differs"
        assert via_engine.bull_score == direct.bull_score, f"flag={flag}: bull_score differs"
        assert via_engine.blockers == direct.blockers, f"flag={flag}: blockers differ"
        assert via_engine.triggers_fired == direct.triggers_fired, f"flag={flag}: triggers differ"
