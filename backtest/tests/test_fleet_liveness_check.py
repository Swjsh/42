"""Guards for fleet_liveness_check -- the FLEET-LIVENESS-IN-ENGINE-HEALTH fix.

J caught a 2-of-6 fleet-account review TWICE (2026-06-25, then again 2026-07-27). The fleet_rest
arms (safe-3, risky-1, risky-3) trade via a SECOND execution path, invisible to the
mcp_heartbeat-scoped checks that already watch safe-2/bold-2. These tests pin the distinction
that was missing: on a weekday, a watched fleet arm with ZERO decision rows is a FAULT, not
quiet -- and that a monitor watching one execution path must not silently vouch for the other.
"""
import datetime as dt
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "setup" / "scripts"))

from fleet_liveness_check import (  # noqa: E402
    STATUS_ALL_TICKED,
    STATUS_NOT_APPLICABLE,
    STATUS_SOME_SILENT,
    STATUS_UNKNOWN,
    alarm_line,
    check_day,
)


def _accounts(*arms) -> dict:
    return {"arms": list(arms)}


def _arm(arm_id: str, status: str = "active", execution: str = "fleet_rest") -> dict:
    return {"id": arm_id, "status": status, "execution": execution}


def _write_accounts(tmp_path: Path, accounts: dict) -> Path:
    p = tmp_path / "accounts.json"
    p.write_text(json.dumps(accounts), encoding="utf-8")
    return p


def _write_decisions(tmp_path: Path, arm_id: str, day: str, n: int) -> None:
    """fleet_liveness_check derives the ledger path from FLEET_DIR / arm_id / decisions.jsonl,
    so tests monkeypatch FLEET_DIR to tmp_path rather than passing a path override (mirrors the
    module's real on-disk layout instead of adding a test-only seam)."""
    d = tmp_path / arm_id
    d.mkdir(parents=True, exist_ok=True)
    p = d / "decisions.jsonl"
    with open(p, "w", encoding="utf-8") as fh:
        for i in range(n):
            fh.write(json.dumps({"ts_et": f"{day}T10:{i % 60:02d}:00", "arm": arm_id}) + "\n")


# --------------------------------------------------------------- the incident itself
def test_one_silent_arm_among_active_ones_is_a_fault(tmp_path, monkeypatch):
    """THE regression class this file exists for: a watched arm with zero rows must RED, even
    while its siblings tick normally."""
    import fleet_liveness_check as flc
    monkeypatch.setattr(flc, "FLEET_DIR", tmp_path)
    accounts = _accounts(_arm("safe-3"), _arm("risky-1"), _arm("risky-3"))
    acc_path = _write_accounts(tmp_path, accounts)
    _write_decisions(tmp_path, "safe-3", "2026-07-27", 40)
    _write_decisions(tmp_path, "risky-1", "2026-07-27", 40)
    # risky-3's ledger EXISTS (prior history) but has zero rows for TODAY -- the true silent
    # signature, distinct from a missing/unreadable file (covered by its own UNKNOWN test).
    _write_decisions(tmp_path, "risky-3", "2026-07-26", 40)

    res = check_day("2026-07-27", accounts_path=acc_path)
    assert res["status"] == STATUS_SOME_SILENT
    assert res["silent_arms"] == ["risky-3"]
    assert set(res["checked_arms"]) == {"safe-3", "risky-1", "risky-3"}


def test_silent_arm_produces_a_spoken_alarm():
    res = {"date": "2026-07-27", "status": STATUS_SOME_SILENT, "silent_arms": ["risky-3"],
           "checked_arms": ["safe-3", "risky-1", "risky-3"], "reason": "x"}
    line = alarm_line(res)
    assert line and "risky-3" in line
    assert "2026-07-27" in line


# --------------------------------------------------------------- must NOT cry wolf
def test_all_arms_ticked_is_silent(tmp_path, monkeypatch):
    import fleet_liveness_check as flc
    monkeypatch.setattr(flc, "FLEET_DIR", tmp_path)
    accounts = _accounts(_arm("safe-3"), _arm("risky-1"), _arm("risky-3"))
    acc_path = _write_accounts(tmp_path, accounts)
    for arm_id in ("safe-3", "risky-1", "risky-3"):
        _write_decisions(tmp_path, arm_id, "2026-07-31", 300)

    res = check_day("2026-07-31", accounts_path=acc_path)
    assert res["status"] == STATUS_ALL_TICKED
    assert alarm_line(res) is None, "a fully-healthy day must produce no alarm line"


@pytest.mark.parametrize("weekend_day", ["2026-07-25", "2026-07-26"])  # Sat, Sun
def test_weekend_absence_is_expected_not_a_fault(tmp_path, monkeypatch, weekend_day):
    import fleet_liveness_check as flc
    monkeypatch.setattr(flc, "FLEET_DIR", tmp_path)
    accounts = _accounts(_arm("safe-3"))
    acc_path = _write_accounts(tmp_path, accounts)
    res = check_day(weekend_day, accounts_path=acc_path)
    assert res["status"] == STATUS_NOT_APPLICABLE
    assert alarm_line(res) is None


# --------------------------------------------------------------- scope discipline
def test_frozen_retired_and_dormant_arms_are_never_watched(tmp_path, monkeypatch):
    """safe-1 (retired) and mes-* (dormant/pending_build) must NOT be able to false-RED this
    check just because they never tick -- they are not expected to."""
    import fleet_liveness_check as flc
    monkeypatch.setattr(flc, "FLEET_DIR", tmp_path)
    accounts = _accounts(
        _arm("safe-3"),
        _arm("safe-1", status="retired"),
        _arm("mes-linear-sim", status="pending_build", execution="futures_sandbox_TT"),
        _arm("mes-mnq-div-futures", status="dormant", execution="futures_sandbox_TT"),
    )
    acc_path = _write_accounts(tmp_path, accounts)
    _write_decisions(tmp_path, "safe-3", "2026-07-31", 10)
    # None of the other three ever get a decisions.jsonl written.

    res = check_day("2026-07-31", accounts_path=acc_path)
    assert res["status"] == STATUS_ALL_TICKED
    assert res["checked_arms"] == ["safe-3"]


def test_mcp_heartbeat_arms_are_never_watched(tmp_path, monkeypatch):
    """safe-2/bold-2 are already covered by check_engine_core/check_heartbeat -- this module must
    not double-flag the same underlying fact under a different check name."""
    import fleet_liveness_check as flc
    monkeypatch.setattr(flc, "FLEET_DIR", tmp_path)
    accounts = _accounts(
        _arm("safe-3"),
        _arm("safe-2", execution="mcp_heartbeat"),
        _arm("bold-2", execution="mcp_heartbeat"),
    )
    acc_path = _write_accounts(tmp_path, accounts)
    _write_decisions(tmp_path, "safe-3", "2026-07-31", 10)
    # safe-2/bold-2 write nothing here -- must not matter, they are out of scope.

    res = check_day("2026-07-31", accounts_path=acc_path)
    assert res["status"] == STATUS_ALL_TICKED
    assert res["checked_arms"] == ["safe-3"]


# --------------------------------------------------------------- fail-open discipline
def test_unreadable_accounts_json_degrades_to_unknown_never_raises(tmp_path):
    res = check_day("2026-07-27", accounts_path=tmp_path / "does-not-exist.json")
    assert res["status"] == STATUS_UNKNOWN


def test_garbage_date_never_raises():
    assert check_day("not-a-date")["status"] == STATUS_UNKNOWN


def test_malformed_arm_ledger_lines_are_skipped_not_fatal(tmp_path, monkeypatch):
    import fleet_liveness_check as flc
    monkeypatch.setattr(flc, "FLEET_DIR", tmp_path)
    accounts = _accounts(_arm("safe-3"))
    acc_path = _write_accounts(tmp_path, accounts)
    d = tmp_path / "safe-3"
    d.mkdir(parents=True, exist_ok=True)
    (d / "decisions.jsonl").write_text(
        "{not json at all\n"
        + json.dumps({"ts_et": "2026-07-27T10:00:00"}) + "\n"
        + "2026-07-27 bare text line\n",
        encoding="utf-8",
    )
    res = check_day("2026-07-27", accounts_path=acc_path)
    assert res["status"] == STATUS_ALL_TICKED  # exactly 1 valid row counted, arm ticked


def test_unreadable_arm_ledger_is_not_confused_with_silent(tmp_path, monkeypatch):
    """An arm whose ledger cannot be read (missing file) is UNKNOWN for that arm, not proof it
    was silent -- fail-open, never a false accusation."""
    import fleet_liveness_check as flc
    monkeypatch.setattr(flc, "FLEET_DIR", tmp_path)
    accounts = _accounts(_arm("safe-3"), _arm("risky-1"))
    acc_path = _write_accounts(tmp_path, accounts)
    _write_decisions(tmp_path, "safe-3", "2026-07-27", 10)
    # risky-1 gets no directory at all (unreadable, not silent-with-evidence).

    res = check_day("2026-07-27", accounts_path=acc_path)
    assert res["status"] == STATUS_ALL_TICKED
    assert res["silent_arms"] == []
    assert res["unknown_arms"] == ["risky-1"]


def test_no_active_fleet_rest_arms_is_unknown_not_a_silent_fault(tmp_path, monkeypatch):
    import fleet_liveness_check as flc
    monkeypatch.setattr(flc, "FLEET_DIR", tmp_path)
    accounts = _accounts(_arm("safe-2", execution="mcp_heartbeat"))
    acc_path = _write_accounts(tmp_path, accounts)
    res = check_day("2026-07-27", accounts_path=acc_path)
    assert res["status"] == STATUS_UNKNOWN


# --------------------------------------------------------------- engine-health integration
def test_engine_health_fleet_ticked_flags_a_real_silent_arm(monkeypatch):
    """engine_health.check_fleet_ticked must go RED when the underlying module reports a
    silent arm -- proving the wiring, not just the module in isolation."""
    import datetime as dt
    from zoneinfo import ZoneInfo

    import engine_health as eh
    import fleet_liveness_check as flc

    def fake_check_day(day):
        return {"date": day, "status": flc.STATUS_SOME_SILENT, "silent_arms": ["risky-3"],
                "checked_arms": ["safe-3", "risky-1", "risky-3"], "unknown_arms": [],
                "reason": "1/3 fleet arm(s) recorded ZERO decisions today: ['risky-3']"}

    monkeypatch.setattr(flc, "check_day", fake_check_day)

    ET = ZoneInfo("America/New_York")
    res = eh.check_fleet_ticked(dt.datetime(2026, 7, 27, 18, 0, tzinfo=ET))
    assert res["status"] == "RED"
    assert "risky-3" in res["detail"]
    assert res["critical"] is True


def test_engine_health_fleet_ticked_is_not_market_open_suppressed(monkeypatch):
    """Post-close, this check must still be able to RED -- market-open suppression is exactly
    the bug class check_session_ran/check_levels_blind were built to close."""
    import datetime as dt
    from zoneinfo import ZoneInfo

    import engine_health as eh
    import fleet_liveness_check as flc

    def fake_check_day(day):
        return {"date": day, "status": flc.STATUS_SOME_SILENT, "silent_arms": ["safe-3"],
                "checked_arms": ["safe-3"], "unknown_arms": [], "reason": "x"}

    monkeypatch.setattr(flc, "check_day", fake_check_day)

    ET = ZoneInfo("America/New_York")
    res = eh.check_fleet_ticked(dt.datetime(2026, 7, 27, 20, 0, tzinfo=ET))
    assert res["status"] == "RED", "post-close suppression would repeat the 07-24 bug class"


def test_engine_health_fleet_ticked_quiet_on_weekend_and_midsession():
    import datetime as dt
    from zoneinfo import ZoneInfo

    import engine_health as eh

    ET = ZoneInfo("America/New_York")
    assert eh.check_fleet_ticked(dt.datetime(2026, 7, 25, 18, 0, tzinfo=ET))["status"] == "GREEN"
    assert eh.check_fleet_ticked(dt.datetime(2026, 7, 23, 11, 0, tzinfo=ET))["status"] == "GREEN"


def test_engine_health_fleet_ticked_registered_in_build_report():
    """The check must actually be wired into the fused report, not just defined -- guards
    against the 'built but never registered' shape (backtest/lib/watchers/runner.py's
    registry-catches-orphans lesson, applied here by source inspection)."""
    import inspect

    import engine_health as eh

    src = inspect.getsource(eh.build_report)
    assert "check_fleet_ticked(" in src
