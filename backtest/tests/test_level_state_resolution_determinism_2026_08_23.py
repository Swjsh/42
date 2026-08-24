"""Guard: resolving a trigger PRICE to its LevelState is DETERMINISTIC and never
depends on dict-insertion order.

ROOT CAUSE (verified 2026-08-23 — see
analysis/deep-research/SEQUENCE-REJECTION-PARITY-PROBE-2026-08-23.md and the probe
tool backtest/tools/sequence_rejection_parity_probe_2026_08_23.py):

  filters.py resolved `rejection_level` (a float) to a LevelState by scanning
  `ctx.level_states.values()` in DICT-INSERTION ORDER and taking the FIRST entry
  within $0.05. No exact-key match, no role or recency tie-break. Whichever
  matching level was inserted first won, arbitrarily.

  The helper is SHARED by the live brain (setup/scripts/heartbeat_core.py, which
  rebuilds its dict every tick) and the offline ground truth
  (backtest/lib/orchestrator.py:869, whose dict is created ONCE and NEVER reset
  across a multi-day replay). At GT bar 1801 (2026-06-23 15:35 ET) the replay dict
  held a STALE 735.0300 (role=broken_to_support, EMPTY bounce_history, last touched
  bar 1405 = 2026-06-15) inserted BEFORE the real same-day 735.0000 (created bar
  1791). The lookup hit the stale object, read the wrong role, and returned False —
  a FALSE NEGATIVE on a genuine 3-bar lower-highs stairstep (735.28 -> 735.21 ->
  735.19, each closing back below the broken 735.00). LIVE was correct; the GT was
  the one that was wrong. That single mis-resolution is what surfaced as
  test_no_arm_overtrades' risky-1 extra=1 and test_three_arms_entry_faithful's
  risky-1 failure.

WHY THIS GUARD, NOT A WINDOW CHANGE:
  Live escaped the defect only BY ACCIDENT. It routinely holds two entries within
  $0.05 (measured: 1,238 of 13,879 live ticks across 6 sessions) and was protected
  purely by (a) argument ordering in heartbeat_core (levels_active before fhh) and
  (b) a $0.10 dedupe threshold that lives in a DIFFERENT file
  (setup/scripts/refresh_levels_intraday.py ROLE_EPSILON=0.10). Drop that knob below
  $0.05, or let any non-normalizing writer touch key-levels.json, and the LIVE
  trading path silently inherits the exact GT defect with real money behind it. The
  defect is the RESOLVER, so the resolver is what this pins — not either engine's
  windowing (C12/C6/C34).

These tests RED against the pre-fix insertion-order scan. See the writeup for the
quoted pre-fix failure output.
"""
from __future__ import annotations

import datetime as dt
import itertools
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
for _p in (str(BACKTEST), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib.filters import (  # noqa: E402
    BarContext,
    LevelState,
    detect_sequence_reclaim,
    detect_sequence_rejection,
    evaluate_bearish_setup,
    evaluate_bullish_setup,
)


def resolve_level_state(*args, **kwargs):
    """Thin lazy shim around lib.filters.resolve_level_state.

    Imported lazily ON PURPOSE: if the fix is ever reverted, a module-level import
    of a now-missing symbol would abort COLLECTION and every test in this file would
    report as one opaque ImportError. With the shim, the end-to-end golden tests
    below still RUN and fail with a real assertion naming the regressed BEHAVIOUR
    (sequence_rejection stopped firing), which is the diagnostic that matters.
    """
    from lib.filters import resolve_level_state as _impl

    return _impl(*args, **kwargs)

# --- The real bar-1801 geometry (2026-06-23 15:35:00-04:00) ------------------
REAL_LEVEL = 735.00
STALE_LEVEL = 735.03      # $0.03 away — inside the $0.05 lookup band
STALE_BAR = 1405          # 2026-06-15, eight sessions earlier
BROKEN_BAR = 1791         # same-day break of 735.00
_ALL_FILTERS = list(range(1, 13))


def _real_bear_state() -> LevelState:
    """735.0000 as it ACTUALLY stood at bar 1801: broken to resistance today, with
    the genuine 3-bar lower-highs stairstep."""
    return LevelState(
        price=REAL_LEVEL,
        role="broken_to_resistance",
        broken_at_bar_idx=BROKEN_BAR,
        bounce_history=[
            {"bar_idx": 1798, "high_reached": 735.28, "outcome": "rejected_close_below"},
            {"bar_idx": 1800, "high_reached": 735.21, "outcome": "rejected_close_below"},
            {"bar_idx": 1801, "high_reached": 735.19, "outcome": "rejected_close_below"},
        ],
    )


def _stale_bear_state() -> LevelState:
    """735.0300 as the never-reset GT dict held it: frozen on 2026-06-15, opposite
    role, empty history. Inserted BEFORE the real level, so it won the old scan."""
    return LevelState(
        price=STALE_LEVEL,
        role="broken_to_support",
        broken_at_bar_idx=STALE_BAR,
        bounce_history=[],
    )


def _stale_first_dict() -> dict:
    """Insertion order is the whole point: stale FIRST, real SECOND."""
    return {
        f"{STALE_LEVEL:.4f}": _stale_bear_state(),
        f"{REAL_LEVEL:.4f}": _real_bear_state(),
    }


# Trigger bar: high 735.19 > 735.00, close 734.90 < 735.00 -> rejection_level=735.00
_BEAR_BAR = pd.Series(
    {"open": 735.10, "high": 735.19, "low": 734.85, "close": 734.90, "volume": 1000}
)


def _bear_ctx(level_states: dict) -> BarContext:
    return BarContext(
        # ctx.bar_idx indexes into prior_bars, so it is the LOCAL position in this
        # 2-bar fixture frame. The REAL bar indices (1405 / 1791 / 1798-1801) live in
        # the LevelStates, which is where recency is read from.
        bar_idx=1,
        timestamp_et=dt.datetime(2026, 6, 23, 15, 35),
        bar=_BEAR_BAR,
        prior_bars=pd.DataFrame([_BEAR_BAR, _BEAR_BAR]),
        ribbon_now=None,
        ribbon_history=[],
        vix_now=15.0,
        vix_prior=15.0,
        vol_baseline_20=1.0,
        range_baseline_20=1.0,
        levels_active=[REAL_LEVEL],
        multi_day_levels=[],
        htf_15m_stack="BEAR",
        level_states=level_states,
    )


# ---------------------------------------------------------------------------
# NON-VACUOUS BITE — prove the crafted states really do drive the detectors, so
# the guards below are pinning a REAL flip and not asserting on inert data.
# ---------------------------------------------------------------------------
def test_bite_real_state_fires_and_stale_state_does_not():
    assert detect_sequence_rejection(_real_bear_state()) is True
    assert detect_sequence_rejection(_stale_bear_state()) is False


# ---------------------------------------------------------------------------
# (a) A stale near-price level inserted BEFORE the real one must resolve to the
#     REAL one. This is the bar-1801 defect. REDs against the pre-fix scan.
# ---------------------------------------------------------------------------
def test_stale_level_inserted_first_does_not_shadow_the_real_level():
    resolved = resolve_level_state(
        _stale_first_dict(), REAL_LEVEL, wanted_role="broken_to_resistance"
    )
    assert resolved is not None
    assert resolved.price == REAL_LEVEL
    assert resolved.role == "broken_to_resistance"
    assert len(resolved.bounce_history) == 3


def test_bar_1801_sequence_rejection_fires_end_to_end():
    """GOLDEN (bear): the full evaluate_bearish_setup path with the stale level
    inserted first must still fire sequence_rejection. Pre-fix this returned
    triggers WITHOUT sequence_rejection — the false negative that made GT disagree
    with live and RED test_no_arm_overtrades."""
    res = evaluate_bearish_setup(
        _bear_ctx(_stale_first_dict()), disable_filters=_ALL_FILTERS, min_triggers=1
    )
    assert res.rejection_level == REAL_LEVEL
    assert "sequence_rejection" in res.triggers_fired


def test_bar_1801_verdict_is_identical_without_the_stale_level():
    """Live's dict never contained 735.0300 — and after the fix GT resolves the same
    way live does. Same bar, with and without the stale entry, same triggers."""
    with_stale = evaluate_bearish_setup(
        _bear_ctx(_stale_first_dict()), disable_filters=_ALL_FILTERS, min_triggers=1
    )
    live_shaped = evaluate_bearish_setup(
        _bear_ctx({f"{REAL_LEVEL:.4f}": _real_bear_state()}),
        disable_filters=_ALL_FILTERS,
        min_triggers=1,
    )
    assert with_stale.triggers_fired == live_shaped.triggers_fired


# ---------------------------------------------------------------------------
# (a-mirror) The BULLISH reclaim path shares the same helper. GT bars
# 1573/1578/1581/1584/1597/1599 (2026-06-18) were mis-resolved here too — the old
# scan threw away a 10-entry same-day bounce_history for an empty stale one.
# ---------------------------------------------------------------------------
_BULL_LEVEL = 744.35
_BULL_STALE = 744.3734

_BULL_BAR = pd.Series(
    {"open": 744.20, "high": 744.80, "low": 744.10, "close": 744.60, "volume": 1000}
)


def _real_bull_state() -> LevelState:
    return LevelState(
        price=_BULL_LEVEL,
        role="broken_to_support",
        broken_at_bar_idx=1575,
        bounce_history=[
            {"bar_idx": 1595, "low_reached": 744.10, "outcome": "rejected_close_above"},
            {"bar_idx": 1596, "low_reached": 744.20, "outcome": "rejected_close_above"},
            {"bar_idx": 1597, "low_reached": 744.30, "outcome": "rejected_close_above"},
        ],
    )


def _stale_bull_state() -> LevelState:
    return LevelState(
        price=_BULL_STALE,
        role="broken_to_resistance",
        broken_at_bar_idx=STALE_BAR,
        bounce_history=[],
    )


def test_bull_stale_level_inserted_first_does_not_shadow_the_real_level():
    assert detect_sequence_reclaim(_real_bull_state()) is True
    assert detect_sequence_reclaim(_stale_bull_state()) is False

    ctx = BarContext(
        bar_idx=1,  # local position in the fixture frame; see _bear_ctx note
        timestamp_et=dt.datetime(2026, 6, 18, 11, 35),
        bar=_BULL_BAR,
        prior_bars=pd.DataFrame([_BULL_BAR, _BULL_BAR]),
        ribbon_now=None,
        ribbon_history=[],
        vix_now=15.0,
        vix_prior=15.0,
        vol_baseline_20=1.0,
        range_baseline_20=1.0,
        levels_active=[_BULL_LEVEL],
        multi_day_levels=[],
        htf_15m_stack="BULL",
        level_states={
            f"{_BULL_STALE:.4f}": _stale_bull_state(),
            f"{_BULL_LEVEL:.4f}": _real_bull_state(),
        },
    )
    res = evaluate_bullish_setup(ctx, disable_filters=_ALL_FILTERS, min_triggers=1)
    assert res.reclaim_level == _BULL_LEVEL
    assert "sequence_reclaim" in res.triggers_fired


# ---------------------------------------------------------------------------
# (b) Resolution is INDEPENDENT of insertion order.
# ---------------------------------------------------------------------------
def test_resolution_is_invariant_under_insertion_order_bar_1801():
    entries = [
        (f"{STALE_LEVEL:.4f}", _stale_bear_state()),
        (f"{REAL_LEVEL:.4f}", _real_bear_state()),
    ]
    seen = set()
    for perm in itertools.permutations(entries):
        resolved = resolve_level_state(
            dict(perm), REAL_LEVEL, wanted_role="broken_to_resistance"
        )
        seen.add((resolved.price, resolved.role, len(resolved.bounce_history)))
    assert seen == {(REAL_LEVEL, "broken_to_resistance", 3)}


def test_resolution_is_invariant_under_insertion_order_no_exact_key():
    """Harder case: the target matches NO key exactly, so the ranking path (role ->
    recency -> distance -> key) does all the work. Every permutation of four
    candidates must still land on the same object."""
    entries = [
        ("735.0000", LevelState(price=735.00, role="broken_to_resistance",
                                broken_at_bar_idx=1405, bounce_history=[])),
        ("735.0100", LevelState(price=735.01, role="broken_to_resistance",
                                broken_at_bar_idx=1791,
                                bounce_history=[{"bar_idx": 1801, "high_reached": 735.2}])),
        ("735.0300", LevelState(price=735.03, role="broken_to_support",
                                broken_at_bar_idx=1799, bounce_history=[])),
        ("735.0400", LevelState(price=735.04, role=None,
                                broken_at_bar_idx=None, bounce_history=[])),
    ]
    resolved = set()
    for perm in itertools.permutations(entries):
        state = resolve_level_state(
            dict(perm), 735.015, wanted_role="broken_to_resistance"
        )
        resolved.add(state.price)
    # Exactly one answer, and it is the role-applicable + most-recently-touched one.
    assert resolved == {735.01}


def test_resolution_is_invariant_when_every_candidate_is_equivalent():
    """Degenerate tie: same role, same recency, symmetric distance. The key
    tie-break must still make the answer single-valued."""
    entries = [
        ("735.0000", LevelState(price=735.00, role="broken_to_resistance",
                                broken_at_bar_idx=1791, bounce_history=[])),
        ("735.0200", LevelState(price=735.02, role="broken_to_resistance",
                                broken_at_bar_idx=1791, bounce_history=[])),
    ]
    resolved = {
        resolve_level_state(dict(perm), 735.01,
                            wanted_role="broken_to_resistance").price
        for perm in itertools.permutations(entries)
    }
    assert len(resolved) == 1


# ---------------------------------------------------------------------------
# (c) Exact-key match always wins — the key IS the level's identity.
# ---------------------------------------------------------------------------
def test_exact_key_wins_over_a_more_attractive_near_neighbour():
    """The exact-key entry here is deliberately the WEAKER candidate on every
    ranking axis (wrong role, older, and tied on nothing). It must still win."""
    states = {
        "735.0100": LevelState(price=735.01, role="broken_to_resistance",
                               broken_at_bar_idx=1801,
                               bounce_history=[{"bar_idx": 1801, "high_reached": 735.3}]),
        "735.0000": LevelState(price=735.00, role=None,
                               broken_at_bar_idx=1405, bounce_history=[]),
    }
    resolved = resolve_level_state(states, 735.00, wanted_role="broken_to_resistance")
    assert resolved.price == 735.00
    assert resolved.role is None


def test_exact_key_wins_regardless_of_insertion_order():
    a = ("735.0000", LevelState(price=735.00, role=None, broken_at_bar_idx=1405))
    b = ("735.0100", LevelState(price=735.01, role="broken_to_resistance",
                                broken_at_bar_idx=1801))
    for perm in ((a, b), (b, a)):
        assert resolve_level_state(
            dict(perm), 735.00, wanted_role="broken_to_resistance"
        ).price == 735.00


# ---------------------------------------------------------------------------
# Boundary / no-op behaviour must be unchanged from the old scan.
# ---------------------------------------------------------------------------
def test_nothing_within_tolerance_resolves_to_none():
    states = {"735.5000": LevelState(price=735.50, role="broken_to_resistance")}
    assert resolve_level_state(states, 735.00, wanted_role="broken_to_resistance") is None


def test_empty_dict_and_none_target_resolve_to_none():
    assert resolve_level_state({}, 735.00, wanted_role="broken_to_resistance") is None
    assert resolve_level_state(
        _stale_first_dict(), None, wanted_role="broken_to_resistance"
    ) is None


def test_single_candidate_still_resolves_under_a_non_canonical_key():
    """Back-compat: callers/tests that key the dict as str(price) ("745.0", not
    "745.0000") get no exact-key hit and must still resolve via the scan."""
    state = LevelState(price=745.0, role="broken_to_support",
                       bounce_history=[{"low_reached": 743.0},
                                       {"low_reached": 744.0},
                                       {"low_reached": 744.5}])
    resolved = resolve_level_state({str(745.0): state}, 745.0,
                                   wanted_role="broken_to_support")
    assert resolved is state


# ---------------------------------------------------------------------------
# NaN safety (adversarial-review cleanup, 2026-08-23) -- TWO real defects, one
# pre-existing (1a) and one a REGRESSION introduced by resolve_level_state
# itself (1b). Both paths are unreachable in production (broken_at_bar_idx and
# bounce_history bar_idx are always integers in practice; a NaN-priced
# LevelState never occurs live), which is why this is cleanup and not a hold --
# but a resolver that can raise ValueError inside the live brain, or silently
# ADMIT a candidate the old scan excluded, is worse than the bug it replaced.
# ---------------------------------------------------------------------------
def test_nan_broken_at_bar_idx_does_not_raise_inside_recency():
    """1a: `_level_state_recency` used to do bare `int(broken_at_bar_idx)` ->
    `ValueError: cannot convert float NaN to integer` whenever that field held
    NaN. Must not raise; the NaN recency signal is treated as UNINFORMATIVE
    (never claims to be "most recent"), so the real, non-NaN candidate wins the
    recency tie-break instead of crashing the lookup."""
    nan_state = LevelState(price=735.02, role="broken_to_resistance",
                            broken_at_bar_idx=float("nan"), bounce_history=[])
    real_state = LevelState(price=735.00, role="broken_to_resistance",
                            broken_at_bar_idx=1791, bounce_history=[])
    resolved = resolve_level_state(
        {"735.0200": nan_state, "735.0000": real_state},
        735.01, wanted_role="broken_to_resistance",
    )
    assert resolved is real_state


def test_nan_bounce_history_bar_idx_does_not_raise_inside_recency():
    """1a mirror: the SAME `int(...)` crash via the bounce_history branch of
    `_level_state_recency` (`last["bar_idx"]` holding NaN)."""
    nan_history_state = LevelState(
        price=735.02, role="broken_to_resistance", broken_at_bar_idx=1000,
        bounce_history=[{"bar_idx": float("nan"), "high_reached": 735.2}],
    )
    real_state = LevelState(price=735.00, role="broken_to_resistance",
                            broken_at_bar_idx=1791, bounce_history=[])
    resolved = resolve_level_state(
        {"735.0200": nan_history_state, "735.0000": real_state},
        735.01, wanted_role="broken_to_resistance",
    )
    assert resolved is real_state


def test_nan_priced_candidate_is_excluded_not_admitted():
    """1b REGRESSION (introduced by this diff, not pre-existing): the tier-2
    scan's `distance > tolerance` test silently evaluates False for a NaN price
    (NaN comparisons are always False), so a NaN-priced LevelState was ADMITTED
    into the ranking where the pre-2026-08-23 linear scan's own
    `abs(state.price - target) <= 0.05` excluded it cleanly (also False for
    NaN, but sitting on the admitting `if` instead of a `continue` guard).
    Must resolve to the real candidate, and to None when the NaN candidate is
    the ONLY one present -- never to the NaN-priced object."""
    nan_state = LevelState(price=float("nan"), role="broken_to_resistance",
                            broken_at_bar_idx=1791, bounce_history=[])
    real_state = LevelState(price=735.00, role="broken_to_resistance",
                            broken_at_bar_idx=1791, bounce_history=[])
    resolved = resolve_level_state(
        {"nan": nan_state, "735.0000": real_state},
        735.00, wanted_role="broken_to_resistance",
    )
    assert resolved is real_state

    assert resolve_level_state(
        {"nan": nan_state}, 735.00, wanted_role="broken_to_resistance"
    ) is None


def test_nan_priced_exact_key_falls_through_not_admitted():
    """Same 1b regression via the exact-key branch: a NaN price stored under the
    CANONICAL exact key (`"735.0000"`) must not be returned outright -- it
    fails closed and falls through to the (here, empty) tier-2 scan."""
    nan_state = LevelState(price=float("nan"), role="broken_to_resistance",
                            broken_at_bar_idx=1791, bounce_history=[])
    assert resolve_level_state(
        {"735.0000": nan_state}, 735.00, wanted_role="broken_to_resistance"
    ) is None


# ---------------------------------------------------------------------------
# Loud, consistent failure on a malformed object (adversarial-review item C7).
# ---------------------------------------------------------------------------
class _NoPriceAttr:
    """Duck-types nothing. Pre-cleanup, the tier-2 scan silently `continue`d
    past this (getattr(..., "price", None) -> None -> skip) while the
    exact-key branch was ASYMMETRIC and returned it raw -- exploding
    downstream in detect_sequence_rejection/_reclaim's `.role`/`.bounce_history`
    access instead of at the resolver boundary."""
    role = "broken_to_resistance"


def test_malformed_object_raises_in_tier2_scan_not_silently_skipped():
    with pytest.raises(AttributeError):
        resolve_level_state(
            {"735.0100": _NoPriceAttr()}, 735.00, wanted_role="broken_to_resistance"
        )


def test_malformed_object_raises_via_exact_key_not_returned_raw():
    """The asymmetric half of C7: pre-cleanup, THIS branch returned the
    malformed object outright with no tolerance check at all, instead of even
    the tier-2 scan's quiet skip. Must now raise, loud and consistent with the
    tier-2 branch."""
    with pytest.raises(AttributeError):
        resolve_level_state(
            {"735.0000": _NoPriceAttr()}, 735.00, wanted_role="broken_to_resistance"
        )
