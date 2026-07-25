"""Guards for engine_liveness_check -- the 2026-07-24 silent-outage fix.

That day the machine was off, core-decisions.jsonl logged 0 ticks, and every health surface still
read GREEN because "no activity" is indistinguishable from "market closed" to them. These tests
pin the distinction that was missing: on a weekday, ZERO ticks is a FAULT.
"""
import datetime as dt
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "setup" / "scripts"))

from engine_liveness_check import (  # noqa: E402
    MIN_RTH_TICKS,
    STATUS_DID_NOT_RUN,
    STATUS_NOT_APPLICABLE,
    STATUS_PARTIAL,
    STATUS_RAN,
    STATUS_UNKNOWN,
    alarm_line,
    check_day,
)


def _ledger(tmp_path: Path, day: str, n: int) -> Path:
    p = tmp_path / "core-decisions.jsonl"
    with open(p, "w", encoding="utf-8") as fh:
        for i in range(n):
            fh.write(json.dumps({"ts_et": f"{day}T10:{i % 60:02d}:00", "account": "safe"}) + "\n")
    return p


# --------------------------------------------------------------- the incident itself
def test_weekday_with_zero_ticks_is_a_fault(tmp_path):
    """THE regression this file exists for: a weekday that logged nothing must NOT read healthy."""
    led = _ledger(tmp_path, "2026-07-23", 5)  # ledger has other days, none for the target
    res = check_day("2026-07-24", path=led)   # a real Friday, the real outage
    assert res["status"] == STATUS_DID_NOT_RUN
    assert res["ticks"] == 0


def test_zero_tick_weekday_produces_a_spoken_alarm():
    res = {"date": "2026-07-24", "status": STATUS_DID_NOT_RUN, "ticks": 0, "reason": "x"}
    line = alarm_line(res)
    assert line and "did not run" in line.lower()
    assert "2026-07-24" in line


# --------------------------------------------------------------- must NOT cry wolf
def test_normal_trading_day_is_silent(tmp_path):
    led = _ledger(tmp_path, "2026-07-23", 772)
    res = check_day("2026-07-23", path=led)
    assert res["status"] == STATUS_RAN
    assert alarm_line(res) is None, "a healthy day must produce no alarm line"


@pytest.mark.parametrize("weekend_day", ["2026-07-25", "2026-07-26"])  # Sat, Sun
def test_weekend_absence_is_expected_not_a_fault(tmp_path, weekend_day):
    led = _ledger(tmp_path, "2026-07-23", 100)
    res = check_day(weekend_day, path=led)
    assert res["status"] == STATUS_NOT_APPLICABLE
    assert alarm_line(res) is None


# --------------------------------------------------------------- partial + degradation
def test_partial_session_is_flagged_but_distinct_from_dead(tmp_path):
    led = _ledger(tmp_path, "2026-07-23", MIN_RTH_TICKS - 1)
    res = check_day("2026-07-23", path=led)
    assert res["status"] == STATUS_PARTIAL
    assert alarm_line(res) is not None


def test_unreadable_ledger_degrades_to_unknown_never_raises(tmp_path):
    res = check_day("2026-07-23", path=tmp_path / "does-not-exist.jsonl")
    assert res["status"] == STATUS_UNKNOWN


def test_garbage_date_never_raises():
    assert check_day("not-a-date")["status"] == STATUS_UNKNOWN


def test_malformed_ledger_lines_are_skipped_not_fatal(tmp_path):
    p = tmp_path / "core-decisions.jsonl"
    p.write_text(
        "{not json at all\n"
        + json.dumps({"ts_et": "2026-07-23T10:00:00"}) + "\n"
        + "2026-07-23 bare text line\n",
        encoding="utf-8",
    )
    res = check_day("2026-07-23", path=p)
    assert res["status"] == STATUS_PARTIAL  # exactly 1 valid row counted
    assert res["ticks"] == 1


# --------------------------------------------------------------- brief integration
def test_eod_brief_leads_with_the_alarm_ahead_of_pnl(monkeypatch):
    """'$0 today' and 'the engine was dead today' must never sound alike to J."""
    import daily_brief

    monkeypatch.setattr(daily_brief, "_liveness_alarm",
                        lambda day: "Alarm. The engine did not run at all on 2026-07-24.")
    txt = daily_brief.compose_eod_text(
        {"day": "2026-07-24", "by_arm": [], "total_pnl": 0.0, "n_filled": 0, "n_unfilled": 0}
    )
    assert "did not run" in txt.lower()
    assert txt.index("did not run") < txt.index("No account traded"), "alarm must precede P&L"


def test_eod_brief_unchanged_when_engine_healthy(monkeypatch):
    import daily_brief

    monkeypatch.setattr(daily_brief, "_liveness_alarm", lambda day: None)
    txt = daily_brief.compose_eod_text(
        {"day": "2026-07-23", "by_arm": [], "total_pnl": -305.0, "n_filled": 2, "n_unfilled": 0}
    )
    assert "did not run" not in txt.lower()
    assert "down $305" in txt


def test_brief_survives_a_broken_liveness_module(monkeypatch):
    """Fail-open contract: the brief must still compose if the check itself explodes."""
    import daily_brief

    def boom(day):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(daily_brief, "engine_liveness_check", None, raising=False)
    monkeypatch.setattr(daily_brief, "check_day", boom, raising=False)
    txt = daily_brief.compose_eod_text(
        {"day": "2026-07-23", "by_arm": [], "total_pnl": 0.0, "n_filled": 0, "n_unfilled": 0}
    )
    assert "Gamma here" in txt


# --------------------------------------------------------------- engine-health integration
def test_engine_health_session_ran_flags_the_real_outage():
    """engine_health must go RED on 2026-07-24 -- the day it wrongly reported GREEN 13/13."""
    import datetime as dt
    from zoneinfo import ZoneInfo

    import engine_health as eh

    ET = ZoneInfo("America/New_York")
    res = eh.check_session_ran(dt.datetime(2026, 7, 24, 18, 0, tzinfo=ET))
    assert res["status"] == "RED"
    assert "DID NOT RUN" in res["detail"]


def test_engine_health_session_ran_is_not_market_open_suppressed():
    """The bug was 'market closed -> quiet OK'. This check must NOT suppress after the close."""
    import datetime as dt
    from zoneinfo import ZoneInfo

    import engine_health as eh

    ET = ZoneInfo("America/New_York")
    # 20:00 ET Friday: market long closed, yet the verdict must still be RED.
    res = eh.check_session_ran(dt.datetime(2026, 7, 24, 20, 0, tzinfo=ET))
    assert res["status"] == "RED", "post-close suppression is exactly the 07-24 bug"


def test_engine_health_session_ran_quiet_on_weekend_and_midsession():
    import datetime as dt
    from zoneinfo import ZoneInfo

    import engine_health as eh

    ET = ZoneInfo("America/New_York")
    assert eh.check_session_ran(dt.datetime(2026, 7, 25, 18, 0, tzinfo=ET))["status"] == "GREEN"
    assert eh.check_session_ran(dt.datetime(2026, 7, 23, 11, 0, tzinfo=ET))["status"] == "GREEN"
