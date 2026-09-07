"""test_trendline_shadow_weekend_false_alarm_2026_09_07.py -- guards for the weekend/holiday
false-alarm fix in trendline_shadow.py + the new market_calendar.is_trading_day() helper.

ROOT CAUSE (self-audit 2026-09-06 batch, 12 gap-lines from one false alarm):
`Gamma_TrendlineShadow` fires literally every day (`run-trendline-shadow.ps1` has no weekday
gate) and calls `trendline_shadow.py --date <today's ET date>` unconditionally. On a day the
market never opened (weekend, holiday) the cumulative spy_5m_*.csv legitimately has zero bars
for that date -- by the calendar, not by any producer defect -- but `run()` could not tell that
apart from a genuine feed outage: both hit the same "SKIPPED, not empty" -> exit 2 path, and the
PS1 wrapper escalated exit 2 to STATUS.md's `## Known broken` as "BLIND :: cumulative spy_5m
file did not refresh". That happened on both 2026-09-05 (Sat) and 2026-09-06 (Sun), and the
09-06 line fed an entire self-audit batch's worth of catastrophizing (systematic directional
bias, cascade into TradeAutopsy/FuturesEdge3Sim/ThetaClock, "no automatic recovery trigger")
about a data pipeline that was never touched.

THE FIX
  1. `market_calendar.is_trading_day(date_str)` -- True/False/None (unknown), weekday + known-
     holiday check, self-healing exactly like the existing `market_close_et` cache-then-refresh
     contract.
  2. `trendline_shadow.main()` short-circuits to a clean exit 0 (no STATUS write, no FATAL/
     SKIPPED path reached at all) the moment `is_trading_day(a.date) is False`. `None` (cache
     unresolvable) and `True` both fall through to the EXISTING behavior unchanged -- fail-open,
     never suppress a genuine miss on an unresolved guess.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = REPO / "setup" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import market_calendar as mc  # noqa: E402
import trendline_shadow as T  # noqa: E402


# ---------------------------------------------------------------------------
# market_calendar.is_trading_day
# ---------------------------------------------------------------------------

def test_weekend_is_never_a_trading_day_no_cache_needed(tmp_path):
    """Sat/Sun is a pure calendar fact -- must return False without even touching the
    holiday cache (a missing/broken cal_path must not turn a weekend into 'unknown')."""
    missing_cal = tmp_path / "does-not-exist.json"
    assert mc.is_trading_day("2026-09-05", cal_path=missing_cal) is False  # Saturday
    assert mc.is_trading_day("2026-09-06", cal_path=missing_cal) is False  # Sunday


def test_known_holiday_is_not_a_trading_day(tmp_path):
    cal = tmp_path / "calendar.json"
    cal.write_text(
        '{"year_range": ["2026-01-01", "2026-12-31"], "holidays": ["2026-09-07"]}',
        encoding="utf-8",
    )
    # 2026-09-07 is a Monday (Labor Day) -- weekday, but a known holiday.
    assert mc.is_trading_day("2026-09-07", cal_path=cal) is False


def test_normal_weekday_not_in_holidays_is_a_trading_day(tmp_path):
    cal = tmp_path / "calendar.json"
    cal.write_text(
        '{"year_range": ["2026-01-01", "2026-12-31"], "holidays": ["2026-09-07"]}',
        encoding="utf-8",
    )
    assert mc.is_trading_day("2026-09-08", cal_path=cal) is True  # Tuesday, not a holiday


def test_unresolvable_year_returns_none_not_a_guess(tmp_path):
    """Cache doesn't cover the year AND the live refresh has no creds to succeed with --
    must return None (unknown), never guess True or False."""
    cal = tmp_path / "calendar.json"
    cal.write_text('{"year_range": ["2025-01-01", "2025-12-31"], "holidays": []}', encoding="utf-8")
    with patch.object(mc, "refresh_calendar_from_alpaca", return_value=False):
        assert mc.is_trading_day("2026-09-08", cal_path=cal, creds={}) is None


def test_malformed_date_string_returns_none():
    assert mc.is_trading_day("not-a-date") is None


# ---------------------------------------------------------------------------
# trendline_shadow.main() short-circuit
# ---------------------------------------------------------------------------

def test_main_skips_cleanly_on_non_trading_day(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["trendline_shadow.py", "--date", "2026-09-06"])
    with patch.object(T, "load_bars") as mock_load_bars, \
         patch("market_calendar.is_trading_day", return_value=False):
        rc = T.main()
    assert rc == 0
    mock_load_bars.assert_not_called()  # never even opens the bar file -- no false "run() saw nothing"
    out = capsys.readouterr().out
    assert "not a trading day" in out
    assert "BLIND" not in out
    assert "FAILED" not in out


def test_main_falls_through_unchanged_when_trading_day_unknown(monkeypatch):
    """None (unresolvable) must NOT be treated as False -- the existing run() path still
    executes, so a genuine feed outage on an actual trading day is never masked."""
    monkeypatch.setattr(sys, "argv", ["trendline_shadow.py", "--date", "2026-09-08"])
    with patch.object(T, "load_bars") as mock_load_bars, \
         patch.object(T, "run", return_value=0) as mock_run, \
         patch("market_calendar.is_trading_day", return_value=None):
        mock_load_bars.return_value.__getitem__.return_value.unique.return_value = ["2026-09-08"]
        rc = T.main()
    assert rc == 0
    mock_run.assert_called_once_with(["2026-09-08"])


def test_main_falls_through_unchanged_on_confirmed_trading_day(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["trendline_shadow.py", "--date", "2026-09-04"])
    with patch.object(T, "load_bars") as mock_load_bars, \
         patch.object(T, "run", return_value=0) as mock_run, \
         patch("market_calendar.is_trading_day", return_value=True):
        mock_load_bars.return_value.__getitem__.return_value.unique.return_value = ["2026-09-04"]
        rc = T.main()
    assert rc == 0
    mock_run.assert_called_once_with(["2026-09-04"])


def test_seed_mode_never_consults_is_trading_day(monkeypatch):
    """--seed replays the whole bar file -- there is no single 'today' to gate on, so the
    calendar check must not even be attempted."""
    monkeypatch.setattr(sys, "argv", ["trendline_shadow.py", "--seed"])
    with patch.object(T, "load_bars") as mock_load_bars, \
         patch.object(T, "run", return_value=0) as mock_run, \
         patch("market_calendar.is_trading_day") as mock_itd:
        mock_load_bars.return_value.__getitem__.return_value.unique.return_value = \
            ["2026-08-20", "2026-08-21"]
        rc = T.main()
    assert rc == 0
    mock_itd.assert_not_called()
    mock_run.assert_called_once_with(["2026-08-20", "2026-08-21"])


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
