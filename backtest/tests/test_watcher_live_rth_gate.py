"""Guard for the watcher_live RTH gate (C6 / L161 naive-ET re-violation, 2026-06-24).

ROOT CAUSE: `watcher_live.main()` gated "09:30-15:55 ET" on `dt.datetime.now()`
(the host's NAIVE LOCAL clock). The rig runs on Mountain time, so the gate read
09:30-15:55 MT = 11:30-17:55 ET. Intersected with the Windows trigger window
(07:30-13:55 MT = 09:30-15:55 ET), the watcher fleet only ever produced
observations 11:30-15:55 ET -- blind EVERY morning. These tests pin the gate to
true Eastern time so a revert to a naive-local clock fails loud.
"""
import datetime as dt

import pytz
import pytest

from autoresearch.watcher_live import _rth_gate_ok

ET = pytz.timezone("America/New_York")


def _et_from_utc(y, mo, d, h, mi):
    """Build an ET-localized datetime from a UTC wall time (DST handled by pytz)."""
    return dt.datetime(y, mo, d, h, mi, tzinfo=pytz.utc).astimezone(ET)


def test_morning_rth_was_the_bug_now_passes():
    # 2026-06-24 (Wed) 13:35 UTC == 09:35 ET (EDT) == 07:35 MT.
    # Under the old naive-local gate the host clock was 07:35 -> t < 09:30 -> SKIP.
    # The fleet must now correctly recognize this as 09:35 ET -> inside window.
    now_et = _et_from_utc(2026, 6, 24, 13, 35)
    assert now_et.strftime("%H:%M") == "09:35"
    assert _rth_gate_ok(now_et) is True


def test_open_boundary_inclusive():
    assert _rth_gate_ok(_et_from_utc(2026, 6, 24, 13, 30)) is True  # 09:30 ET


def test_close_boundary_inclusive():
    assert _rth_gate_ok(_et_from_utc(2026, 6, 24, 19, 55)) is True  # 15:55 ET


def test_before_open_skips():
    assert _rth_gate_ok(_et_from_utc(2026, 6, 24, 13, 25)) is False  # 09:25 ET


def test_after_close_skips():
    # 20:30 UTC == 16:30 ET. The old MT gate (14:30 MT) would have WRONGLY allowed
    # this; the ET gate correctly rejects it.
    assert _rth_gate_ok(_et_from_utc(2026, 6, 24, 20, 30)) is False


def test_weekend_skips():
    # 2026-06-27 is a Saturday; 17:00 UTC == 13:00 ET (inside the time window but
    # a weekend) -> must skip.
    sat = _et_from_utc(2026, 6, 27, 17, 0)
    assert sat.weekday() == 5
    assert _rth_gate_ok(sat) is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
