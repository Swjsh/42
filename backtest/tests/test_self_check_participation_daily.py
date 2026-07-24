"""Guard for check_participation_daily (self_check.py) -- the SELF-CHECK-WIRE closing
PARTICIPATION-DAILY-SELF-CHECK-WIRE (queue.md MED, filed off participation_cascade.py's own
module docstring, which names this exact hookup as the intended next step).

Pins, RED-on-regression:

  SEVERITY MAPPING -- RED (confirmed participation hole: an account formed
    >= RED_ENTER_VERDICT_FLOOR ENTER verdicts today and filled ZERO) surfaces as BROKEN;
    YELLOW (fills below the account's own daily-min target, but not zero) surfaces as
    DEGRADED, never BROKEN. IDLE (nothing scored today) and GREEN (target met) stay silent.

  STALENESS WINDOW -- the artifact only refreshes once/day (Gamma_ParticipationDaily,
    16:10 ET), so a stale/missing file is only judged (BROKEN) after 16:20 ET on a weekday --
    mirrors check_dress_rehearsal's evening-only staleness window (never false-alarms
    mid-session or on a not-yet-run day).

  WIRED INTO run() -- the check must actually execute inside self_check.run(), not just exist.

Run:  backtest/.venv/Scripts/python.exe -m pytest -q backtest/tests/test_self_check_participation_daily.py
"""
from __future__ import annotations

import datetime as dt
import importlib
import inspect
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
_SCRIPTS = str(ROOT / "setup" / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)


@pytest.fixture()
def sc():
    return importlib.import_module("self_check")


_EVENING = dt.datetime(2026, 7, 23, 16, 30)   # Thursday 16:30 ET -- past the 16:20 window
_MIDDAY = dt.datetime(2026, 7, 23, 12, 0)     # Thursday 12:00 ET -- artifact not written yet
_WEEKEND = dt.datetime(2026, 7, 25, 16, 30)   # Saturday
TODAY = "2026-07-23"


def _write(tmp_path, verdict, date, accounts=None):
    p = tmp_path / "participation-daily.json"
    p.write_text(json.dumps({
        "date": date,
        "verdict": verdict,
        "accounts": accounts or {
            "safe": {"fills": 0, "target_min": 2, "target_max": 4, "verdict": verdict,
                      "enter_verdicts": 6},
            "bold": {"fills": 2, "target_min": 2, "target_max": 4, "verdict": "GREEN",
                     "enter_verdicts": 4},
        },
    }), encoding="utf-8")
    return p


class TestSeverityMapping:
    def test_fresh_green_is_silent(self, sc, tmp_path):
        p = _write(tmp_path, "GREEN", TODAY,
                   accounts={"safe": {"fills": 3, "target_min": 2, "target_max": 4, "verdict": "GREEN"},
                             "bold": {"fills": 2, "target_min": 2, "target_max": 4, "verdict": "GREEN"}})
        assert sc.check_participation_daily(_EVENING, path=p) == []

    def test_fresh_idle_is_silent(self, sc, tmp_path):
        p = _write(tmp_path, "IDLE", TODAY,
                   accounts={"safe": {"fills": 0, "target_min": 2, "target_max": 4, "verdict": "IDLE"},
                             "bold": {"fills": 0, "target_min": 2, "target_max": 4, "verdict": "IDLE"}})
        assert sc.check_participation_daily(_EVENING, path=p) == []

    def test_overall_red_is_broken(self, sc, tmp_path):
        p = _write(tmp_path, "RED", TODAY)
        probs = sc.check_participation_daily(_EVENING, path=p)
        assert probs and sc._problem_is_broken(probs[0])
        assert "safe" in probs[0] and "bold" in probs[0]

    def test_overall_yellow_is_degraded_not_broken(self, sc, tmp_path):
        p = _write(tmp_path, "YELLOW", TODAY,
                   accounts={"safe": {"fills": 1, "target_min": 2, "target_max": 4, "verdict": "YELLOW"},
                             "bold": {"fills": 2, "target_min": 2, "target_max": 4, "verdict": "GREEN"}})
        probs = sc.check_participation_daily(_EVENING, path=p)
        assert probs and not any(sc._problem_is_broken(x) for x in probs)
        assert "safe" in probs[0] and "bold" not in probs[0]  # only the YELLOW account named


class TestStalenessWindow:
    def test_missing_artifact_silent_midday(self, sc, tmp_path):
        p = tmp_path / "nope.json"
        assert sc.check_participation_daily(_MIDDAY, path=p) == []

    def test_missing_artifact_broken_evening_weekday(self, sc, tmp_path):
        p = tmp_path / "nope.json"
        probs = sc.check_participation_daily(_EVENING, path=p)
        assert probs and sc._problem_is_broken(probs[0])

    def test_missing_artifact_silent_weekend(self, sc, tmp_path):
        p = tmp_path / "nope.json"
        assert sc.check_participation_daily(_WEEKEND, path=p) == []

    def test_stale_date_silent_midday(self, sc, tmp_path):
        p = _write(tmp_path, "GREEN", "2026-07-22")  # yesterday's run, not yet refreshed today
        assert sc.check_participation_daily(_MIDDAY, path=p) == []

    def test_stale_date_broken_evening_weekday(self, sc, tmp_path):
        p = _write(tmp_path, "GREEN", "2026-07-22")
        probs = sc.check_participation_daily(_EVENING, path=p)
        assert probs and sc._problem_is_broken(probs[0])


class TestWiredIntoRun:
    def test_wired_into_run(self, sc):
        assert "check_participation_daily(now)" in inspect.getsource(sc.run)
