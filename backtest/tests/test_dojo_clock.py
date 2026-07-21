"""Guard: setup/scripts/dojo/clock.py -- TV replay cursor <-> engine bar-time mapping.

clock.py is pure (no I/O) and load-bearing for the DOJO lockstep invariant (TV cursor ==
engine bar, drift = hard stop -- DOJO-ARCHITECTURE-DECISION.md). This guard exercises every
boundary named in the module's own docstrings: resolve_cursor's epoch validation + DST
correctness, is_rth's session edges + weekend, and latest_closed_5m_bar_et's pre-RTH /
mid-session grid-floor / >=16:00 clamp / weekend behaviour.

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_dojo_clock.py -v
"""
from __future__ import annotations

import importlib.util
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
ET = ZoneInfo("America/New_York")


def _load_clock():
    """Load dojo/clock.py directly by path -- no sys.path pollution, no package needed
    (clock.py has zero imports beyond stdlib, so this is safe in isolation)."""
    path = os.path.join(ROOT, "setup", "scripts", "dojo", "clock.py")
    spec = importlib.util.spec_from_file_location("dojo_clock", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


clock = _load_clock()


def _et(y, mo, d, h, mi, s=0):
    return datetime(y, mo, d, h, mi, s, tzinfo=ET)


# ============================================================ resolve_cursor ====

def test_resolve_cursor_rejects_zero_epoch():
    with pytest.raises(ValueError):
        clock.resolve_cursor(0)


def test_resolve_cursor_rejects_negative_epoch():
    with pytest.raises(ValueError):
        clock.resolve_cursor(-1)


def test_resolve_cursor_rejects_negative_float_epoch():
    with pytest.raises(ValueError):
        clock.resolve_cursor(-100.5)


def test_resolve_cursor_rejects_non_numeric():
    with pytest.raises(ValueError):
        clock.resolve_cursor("not-an-epoch")  # type: ignore[arg-type]


def test_resolve_cursor_rejects_none():
    with pytest.raises(ValueError):
        clock.resolve_cursor(None)  # type: ignore[arg-type]


def test_resolve_cursor_returns_tz_aware_et():
    """epoch=1 (1969-12-31 19:00:01 EST) -- must come back aware, in ET (-5, EST at that
    instant), never naive."""
    dt = clock.resolve_cursor(1)
    assert dt.tzinfo is not None
    assert dt.utcoffset() is not None
    assert dt.utcoffset().total_seconds() / 3600 == -5


def test_resolve_cursor_summer_edt_correct():
    """2026-07-17 10:15:00 ET (EDT, UTC-4) -- a real curriculum-day cursor."""
    expected = _et(2026, 7, 17, 10, 15, 0)
    epoch = int(expected.timestamp())
    got = clock.resolve_cursor(epoch)
    assert got == expected
    assert got.hour == 10 and got.minute == 15
    assert got.utcoffset().total_seconds() / 3600 == -4


def test_resolve_cursor_winter_est_correct():
    """2026-01-15 10:15:00 ET (EST, UTC-5) -- DST-aware conversion, not a fixed -4 offset.
    This is the exact TZ-SYSTEMIC scar class (project memory: naive UTC-4 joins are wrong
    in winter) -- resolve_cursor must go through zoneinfo, never a fixed offset."""
    expected = _et(2026, 1, 15, 10, 15, 0)
    epoch = int(expected.timestamp())
    got = clock.resolve_cursor(epoch)
    assert got == expected
    assert got.hour == 10 and got.minute == 15
    assert got.utcoffset().total_seconds() / 3600 == -5


def test_resolve_cursor_accepts_float_epoch():
    expected = _et(2026, 7, 17, 9, 35, 0)
    epoch = expected.timestamp()  # float
    got = clock.resolve_cursor(epoch)
    assert got.hour == 9 and got.minute == 35


def test_resolve_cursor_utc_roundtrip_matches_direct_conversion():
    """Cross-check against a hand-built UTC->ET conversion, independent of the module's own
    astimezone call, so a bug in the ET_TZ constant itself wouldn't cheat this test."""
    utc_dt = datetime(2026, 7, 17, 14, 15, 0, tzinfo=timezone.utc)  # 10:15 EDT
    epoch = int(utc_dt.timestamp())
    got = clock.resolve_cursor(epoch)
    assert got.astimezone(timezone.utc) == utc_dt


# ============================================================ is_rth ====

def test_is_rth_requires_aware_datetime():
    naive = datetime(2026, 7, 17, 10, 15, 0)
    with pytest.raises(ValueError):
        clock.is_rth(naive)


def test_is_rth_pre_open_false():
    assert clock.is_rth(_et(2026, 7, 17, 9, 29, 59)) is False


def test_is_rth_open_edge_true():
    """09:30:00 ET is the open edge -- inclusive."""
    assert clock.is_rth(_et(2026, 7, 17, 9, 30, 0)) is True


def test_is_rth_midday_true():
    assert clock.is_rth(_et(2026, 7, 17, 12, 0, 0)) is True


def test_is_rth_last_instant_true():
    assert clock.is_rth(_et(2026, 7, 17, 15, 59, 59)) is True


def test_is_rth_close_edge_false():
    """16:00:00 ET is the close edge -- exclusive (session already over)."""
    assert clock.is_rth(_et(2026, 7, 17, 16, 0, 0)) is False


def test_is_rth_after_hours_false():
    assert clock.is_rth(_et(2026, 7, 17, 17, 0, 0)) is False


def test_is_rth_overnight_false():
    assert clock.is_rth(_et(2026, 7, 17, 3, 0, 0)) is False


def test_is_rth_saturday_false():
    # 2026-07-18 is a Saturday.
    assert clock.is_rth(_et(2026, 7, 18, 12, 0, 0)) is False


def test_is_rth_sunday_false():
    # 2026-07-19 is a Sunday.
    assert clock.is_rth(_et(2026, 7, 19, 12, 0, 0)) is False


def test_is_rth_accepts_non_et_aware_datetime():
    """Must normalize via astimezone(ET), not assume the caller already passed ET."""
    utc_open = datetime(2026, 7, 17, 13, 30, 0, tzinfo=timezone.utc)  # 09:30 EDT
    assert clock.is_rth(utc_open) is True
    utc_pre = datetime(2026, 7, 17, 13, 29, 0, tzinfo=timezone.utc)  # 09:29 EDT
    assert clock.is_rth(utc_pre) is False


# ============================================================ latest_closed_5m_bar_et ====

def test_latest_closed_bar_requires_aware_datetime():
    naive = datetime(2026, 7, 17, 10, 15, 0)
    with pytest.raises(ValueError):
        clock.latest_closed_5m_bar_et(naive)


def test_latest_closed_bar_before_first_close_is_none():
    """09:32 ET -- before the 09:35 first RTH bar close -- no closed bar yet."""
    assert clock.latest_closed_5m_bar_et(_et(2026, 7, 17, 9, 32, 0)) is None


def test_latest_closed_bar_just_before_first_close_is_none():
    assert clock.latest_closed_5m_bar_et(_et(2026, 7, 17, 9, 34, 59)) is None


def test_latest_closed_bar_at_market_open_is_none():
    assert clock.latest_closed_5m_bar_et(_et(2026, 7, 17, 9, 30, 0)) is None


def test_latest_closed_bar_at_first_close_exact():
    """Exactly 09:35:00 ET -- the first bar just closed."""
    got = clock.latest_closed_5m_bar_et(_et(2026, 7, 17, 9, 35, 0))
    assert got == _et(2026, 7, 17, 9, 35, 0)


def test_latest_closed_bar_mid_bar_floors_to_previous_close():
    """09:37 ET is mid-formation of the 09:35-09:40 bar -- the latest CLOSED bar is 09:35."""
    got = clock.latest_closed_5m_bar_et(_et(2026, 7, 17, 9, 37, 0))
    assert got == _et(2026, 7, 17, 9, 35, 0)


def test_latest_closed_bar_at_second_close_exact():
    got = clock.latest_closed_5m_bar_et(_et(2026, 7, 17, 9, 40, 0))
    assert got == _et(2026, 7, 17, 9, 40, 0)


def test_latest_closed_bar_mid_session_floors_to_5min_grid():
    """13:22 ET -> the 13:15-13:20 bar closed at 13:20; 13:22 is 2min into the next bar."""
    got = clock.latest_closed_5m_bar_et(_et(2026, 7, 17, 13, 22, 0))
    assert got == _et(2026, 7, 17, 13, 20, 0)


def test_latest_closed_bar_mid_session_one_second_before_close():
    """13:24:59 ET -- one second before the 13:25 close -- still floors to 13:20."""
    got = clock.latest_closed_5m_bar_et(_et(2026, 7, 17, 13, 24, 59))
    assert got == _et(2026, 7, 17, 13, 20, 0)


def test_latest_closed_bar_at_close_clamps_to_1600():
    got = clock.latest_closed_5m_bar_et(_et(2026, 7, 17, 16, 0, 0))
    assert got == _et(2026, 7, 17, 16, 0, 0)


def test_latest_closed_bar_after_close_clamps_to_1600():
    """18:00 ET (well after close) still clamps to the session's last bar, 16:00 -- does
    NOT keep floor-stepping past the session end."""
    got = clock.latest_closed_5m_bar_et(_et(2026, 7, 17, 18, 0, 0))
    assert got == _et(2026, 7, 17, 16, 0, 0)


def test_latest_closed_bar_far_after_close_still_clamps():
    got = clock.latest_closed_5m_bar_et(_et(2026, 7, 17, 23, 59, 0))
    assert got == _et(2026, 7, 17, 16, 0, 0)


def test_latest_closed_bar_weekend_saturday_is_none():
    assert clock.latest_closed_5m_bar_et(_et(2026, 7, 18, 12, 0, 0)) is None


def test_latest_closed_bar_weekend_sunday_is_none():
    assert clock.latest_closed_5m_bar_et(_et(2026, 7, 19, 12, 0, 0)) is None


def test_latest_closed_bar_returned_tzinfo_is_et():
    got = clock.latest_closed_5m_bar_et(_et(2026, 7, 17, 10, 15, 0))
    assert got is not None
    assert got.tzinfo is not None
    assert got.utcoffset().total_seconds() / 3600 == -4


def test_latest_closed_bar_normalizes_non_et_input():
    """A UTC-aware cursor must be normalized to ET before grid math, not misread as if the
    UTC wall-clock numbers were already ET (which would silently shift the whole grid)."""
    utc_cursor = datetime(2026, 7, 17, 17, 22, 0, tzinfo=timezone.utc)  # 13:22 EDT
    got = clock.latest_closed_5m_bar_et(utc_cursor)
    assert got == _et(2026, 7, 17, 13, 20, 0)


def test_latest_closed_bar_winter_dst_grid_still_correct():
    """EST day (2026-01-15): 10:07 ET floors to 10:05 -- DST must not perturb the 5-min grid
    math (grid is computed in ET wall-clock terms after zoneinfo normalization)."""
    got = clock.latest_closed_5m_bar_et(_et(2026, 1, 15, 10, 7, 0))
    assert got == _et(2026, 1, 15, 10, 5, 0)
