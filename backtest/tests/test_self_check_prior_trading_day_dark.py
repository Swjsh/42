"""Guard for self_check.check_prior_trading_day_dark -- the ENGINE-WIDE dark-trading-day
VISIBILITY instrument (2026-07-24).

Motivation: the 2026-07-15 scar (see self_check._calendar_staleness / the module comment
above check_macro_calendar_freshness) diagnosed ONE producer (Gamma_MacroCalendar) missing
its fire because an overnight event left no interactive logon session through the trigger
window -- LogonType=Interactive is this repo's universal task-registration convention, and
StartWhenAvailable=True does NOT retroactively catch a missed Interactive-logon task even
once the session resumes (a documented Task Scheduler limitation).

2026-07-24 repeated the SAME mechanism at a much larger scope: the box slept from
2026-07-23 21:48 MT through 2026-07-25 09:12 MT (~35.4h, Kernel-Power evt id 42 -> next
System-log activity two days later), spanning the ENTIRE Friday 2026-07-24 RTH session.
core-decisions.jsonl has ZERO rows dated 2026-07-24 for either account -- confirmed live
against the production ledger this fire. Three of the six critical scheduled tasks already
had WakeToRun=True set (Premarket/LaunchTV/EodFlatten) and NONE of them woke the machine
(powercfg /lastwake showed "Wake Source Count - 0" for the eventual Saturday wake) -- so
wake-timers alone are not a sufficient fix; LogonType is the more likely mechanism (matches
the 2026-07-15 scar exactly), but changing LogonType needs elevated (admin) privileges this
automated session does not have, so it is queued as a manual follow-up.

This is a RE-VIOLATED lesson (OP-25: "a re-violated lesson MUST become a test") -- every
OTHER staleness check in self_check.py is scoped to "today, weekday, after some time" and
therefore self-heals invisibly once Monday's fresh ticks arrive; a fully-dark PAST trading
day discovered on a weekend read (exactly this incident) had no first-class check of its
own before this. This pins:

  1. A completed trading day with ZERO RTH-window rows in core-decisions.jsonl for EITHER
     account renders BROKEN/RED (matches _problem_is_broken's "RED" substring rule).
  2. A completed trading day WITH at least one RTH row (even a single HOLD tick) renders no
     problem at all -- the check only fires on a fully-dark day, never on a quiet one.
  3. `run()` looks BACKWARD (previous completed trading day), not at "today" -- so it fires
     correctly even when invoked on a weekend, unlike every "today, weekday" check in this
     file.
  4. A weekend/holiday correctly anchors to the last real trading day (Friday before a
     Sat/Sun read; the day before a holiday is skipped).
  5. Fail-open: a missing/unreadable ledger returns [] (no false BROKEN) -- this check only
     asserts on POSITIVE evidence of a populated-but-RTH-empty ledger for a specific date,
     never on "file missing entirely".
  6. `run()` actually wires the check into `problems` (source-level, no live I/O needed).

Mirrors test_self_check_pdt_status.py's import convention (spec_from_file_location, so this
survives running as a lone file without setup/scripts pre-imported)."""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
MOD_PATH = REPO / "setup" / "scripts" / "self_check.py"

_spec = importlib.util.spec_from_file_location("self_check", MOD_PATH)
sc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sc)


def _write_calendar(tmp_path, holidays=None) -> Path:
    p = tmp_path / "calendar.json"
    p.write_text(json.dumps({"holidays": holidays or []}), encoding="utf-8")
    return p


def _write_decisions(tmp_path, rows: list[dict]) -> Path:
    p = tmp_path / "core-decisions.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + ("\n" if rows else ""), encoding="utf-8")
    return p


# ---- the exact 2026-07-24 scar, reproduced ----

def test_zero_rth_rows_on_completed_trading_day_is_broken(tmp_path):
    cal = _write_calendar(tmp_path)
    # Friday 07-24 has ZERO rows at all -- Saturday read, exactly the incident.
    dec = _write_decisions(tmp_path, [
        {"ts_et": "2026-07-23T15:55:04", "account": "bold", "verdict": "HOLD"},
    ])
    now = dt.datetime(2026, 7, 25, 11, 42, 0)  # Saturday
    out = sc.check_prior_trading_day_dark(now, core_path=dec, calendar_path=cal)
    assert len(out) == 1
    assert "ENGINE DARK ALL DAY (RED)" in out[0]
    assert "2026-07-24" in out[0]
    assert sc._problem_is_broken(out[0])


def test_at_least_one_rth_row_is_clean(tmp_path):
    cal = _write_calendar(tmp_path)
    dec = _write_decisions(tmp_path, [
        {"ts_et": "2026-07-24T10:15:00", "account": "safe", "verdict": "HOLD"},
    ])
    now = dt.datetime(2026, 7, 25, 11, 42, 0)  # Saturday
    assert sc.check_prior_trading_day_dark(now, core_path=dec, calendar_path=cal) == []


def test_row_outside_rth_window_does_not_count(tmp_path):
    """A row that lands OUTSIDE 09:30-15:55 ET (e.g. a stray after-hours log) must not mask
    a genuinely dark RTH session -- only real trading-window activity clears the flag."""
    cal = _write_calendar(tmp_path)
    dec = _write_decisions(tmp_path, [
        {"ts_et": "2026-07-24T20:00:00", "account": "safe", "verdict": "HOLD"},
    ])
    now = dt.datetime(2026, 7, 25, 11, 42, 0)
    out = sc.check_prior_trading_day_dark(now, core_path=dec, calendar_path=cal)
    assert len(out) == 1
    assert "ENGINE DARK ALL DAY (RED)" in out[0]


def test_weekday_read_anchors_to_previous_trading_day():
    # A Monday read at 09:00 ET should look back to Friday, not Sunday/Saturday.
    now = dt.datetime(2026, 7, 27, 9, 0, 0)  # Monday
    holidays = set()
    target = sc._last_completed_trading_day(now, holidays)
    assert target == "2026-07-24"


def test_holiday_is_skipped_when_anchoring():
    # Friday 07-03-2026 is a market holiday (per this file's live calendar.json). A Monday
    # read after a holiday-adjacent Friday must still land on the last REAL trading day.
    now = dt.datetime(2026, 7, 6, 9, 0, 0)  # Monday
    holidays = {"2026-07-03"}
    target = sc._last_completed_trading_day(now, holidays)
    assert target == "2026-07-02"  # Thursday -- Friday 07-03 is a holiday, weekend skipped too


def test_missing_ledger_fails_open(tmp_path):
    cal = _write_calendar(tmp_path)
    missing = tmp_path / "does-not-exist.jsonl"
    now = dt.datetime(2026, 7, 25, 11, 42, 0)
    assert sc.check_prior_trading_day_dark(now, core_path=missing, calendar_path=cal) == []


def test_run_wires_the_check_into_problems():
    import inspect
    src = inspect.getsource(sc.run)
    assert "check_prior_trading_day_dark" in src
