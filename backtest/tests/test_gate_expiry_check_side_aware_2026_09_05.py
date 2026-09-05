"""test_gate_expiry_check_side_aware_2026_09_05.py -- GOAL-GATE-NET-COST-2026-09-05 SIDE-TASK.

Pins the side-aware fix ported into `autoresearch.gate_expiry_check._stop_level_for_row`
(2026-09-05), found while N2 hand-checked `setup/scripts/gate_net_cost_walk.py` against a real
bear (put) fill: the pre-fix field-priority fallback (`trigger_level_exact` ->
`bull_reclaim_level_raw` -> `bear_rejection_level_raw`, checked in that FIXED order regardless
of `side`) returned a BULL-side level for a BEAR/put trade whenever `bull_reclaim_level_raw`
happened to be populated on a put-side decision row -- backwards for a put, whose structure
stop should sit ABOVE spot, not at a bull reclaim level below it.

RED-PROOF (run this session): reverting `_stop_level_for_row` to the naive fixed-priority
order (temporarily monkeypatched inline below, mirroring
`test_gate_net_cost_walk_2026_09_05.py::test_naive_level_order_would_mistrigger_winner`) makes
`test_bear_row_never_returns_bull_level` fail -- the naive order returns 761.51 (the bull
level) for a put-side row where the real fix returns 764.22 (the bear level).
"""
from __future__ import annotations

import pandas as pd

from autoresearch import gate_expiry_check as gec


def _fake_spy() -> pd.DataFrame:
    # Minimal frame -- only reached by _swing_stop, which none of the populated-level cases
    # below hit; kept small and real-shaped (has the columns _swing_stop indexes) in case a
    # future row variant falls through to it.
    return pd.DataFrame(
        {
            "high": [765.0, 766.0, 764.5, 763.0, 762.0],
            "low": [762.0, 763.0, 762.5, 761.0, 760.0],
            "close": [763.5, 764.5, 763.5, 762.0, 761.0],
        }
    )


def _naive_stop_level_for_row(row: dict, spy: pd.DataFrame, bar_idx: int, side: str) -> float:
    """The PRE-FIX behavior, reimplemented inline (never imported) so this RED-proof does not
    depend on the fixed source staying byte-identical to some old snapshot."""
    for key in ("trigger_level_exact", "bull_reclaim_level_raw", "bear_rejection_level_raw"):
        v = row.get(key)
        if v is not None:
            return float(v)
    return gec._swing_stop(spy, bar_idx, side)


def test_bear_row_never_returns_bull_level():
    """A put-side (bear) row with BOTH raw fields populated must resolve to the BEAR level,
    never the bull one -- the exact real-fill shape this bug hit (bull_reclaim_level_raw
    populated on a bear trigger row)."""
    spy = _fake_spy()
    row = {
        "trigger_level_exact": None,
        "bull_reclaim_level_raw": 761.51,   # the wrong-side level the naive order picked
        "bear_rejection_level_raw": 764.22,  # the correct bear structure level
    }
    level = gec._stop_level_for_row(row, spy, bar_idx=2, side="P")
    assert level == 764.22, f"expected the bear-side level 764.22, got {level}"
    assert level != 761.51, "must never return the bull-side level for a put trade"


def test_bull_row_never_returns_bear_level():
    """Symmetric case: a call-side (bull) row must resolve to the bull level even when a
    bear level is also populated."""
    spy = _fake_spy()
    row = {
        "trigger_level_exact": None,
        "bull_reclaim_level_raw": 761.51,
        "bear_rejection_level_raw": 764.22,
    }
    level = gec._stop_level_for_row(row, spy, bar_idx=2, side="C")
    assert level == 761.51, f"expected the bull-side level 761.51, got {level}"
    assert level != 764.22, "must never return the bear-side level for a call trade"


def test_trigger_level_exact_wins_regardless_of_side():
    spy = _fake_spy()
    row = {"trigger_level_exact": 763.0, "bull_reclaim_level_raw": 761.51,
           "bear_rejection_level_raw": 764.22}
    assert gec._stop_level_for_row(row, spy, bar_idx=2, side="P") == 763.0
    assert gec._stop_level_for_row(row, spy, bar_idx=2, side="C") == 763.0


def test_no_raw_level_falls_back_to_swing_stop():
    """Neither raw field populated (e.g. a trendline_rejection trigger row) -> falls back to
    `_swing_stop`, matching `gate_net_cost_walk._stop_level_for_wave_row`'s same fallback."""
    spy = _fake_spy()
    row = {"trigger_level_exact": None, "bull_reclaim_level_raw": None,
           "bear_rejection_level_raw": None}
    level = gec._stop_level_for_row(row, spy, bar_idx=2, side="P")
    expected = gec._swing_stop(spy, 2, "P")
    assert level == expected


def test_naive_order_would_mistrigger_this_exact_row():
    """RED-PROOF: the naive fixed-priority order (pre-fix) picks the bull level for this
    put-side row -- demonstrating the mistrigger this fix corrected. This test asserts the
    NAIVE helper's (wrong) output differs from the FIXED helper's (correct) output on the
    same row; if a future edit made the fixed helper regress to naive behavior, this
    assertion's inequality would flip to equality and the test would fail, catching it."""
    spy = _fake_spy()
    row = {"trigger_level_exact": None, "bull_reclaim_level_raw": 761.51,
           "bear_rejection_level_raw": 764.22}
    naive_level = _naive_stop_level_for_row(row, spy, bar_idx=2, side="P")
    fixed_level = gec._stop_level_for_row(row, spy, bar_idx=2, side="P")
    assert naive_level == 761.51  # the bug's actual pre-fix output
    assert fixed_level == 764.22  # the fix's correct output
    assert naive_level != fixed_level, "naive and fixed must disagree on this fixture -- that disagreement IS the bug"
