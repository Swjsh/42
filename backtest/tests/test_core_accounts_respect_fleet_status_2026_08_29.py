"""heartbeat_core must respect fleet/accounts.json `status` (handoff 2026-08-29 section 5.1).

THE GAP THIS CLOSES. `heartbeat_core.ACCOUNTS` is a hardcoded 2-entry dict and main()'s tick
loop iterated it directly. Nothing in this file read fleet/accounts.json, so flipping an arm's
`status` to "retired" there did NOTHING -- the live engine kept placing SPY 0DTE orders on that
account every minute. The 2026-08-28 risky-3 retirement appeared to work only because risky-3
runs the fleet_executor path, which DOES check status; safe-2 and bold-2 are driven directly by
this file and were unreachable by that switch. This is a prerequisite for the safe-2 retirement
at the September window close, and it is landed EARLY, while it is provably inert.

THE SECOND-ORDER TRAP, pinned below: main() gated the tick-completeness marker on
`set(ok_accounts) == set(ACCOUNTS)`. Filtering the loop without also filtering that comparison
would mean a retired arm permanently withholds the marker, freezing every paired-read consumer
on the last complete tick forever -- a far worse outage than the bug being fixed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import heartbeat_core as hc  # noqa: E402


def _write_accounts(tmp_path: Path, statuses: dict) -> Path:
    p = tmp_path / "accounts.json"
    p.write_text(json.dumps({"arms": [{"id": k, "status": v} for k, v in statuses.items()]}),
                 encoding="utf-8")
    return p


# ------------------------------------------------------------------ inertness (today)

def test_is_inert_against_the_real_accounts_json_as_shipped():
    """safe-2 and bold-2 are both status=active right now, so this change must be a no-op.
    If this ever fails, an arm's status changed and the ENGINE'S BEHAVIOUR changed with it --
    that is the intended mechanism, but it must never happen by accident."""
    live = json.loads((REPO / "automation" / "state" / "fleet" / "accounts.json")
                      .read_text(encoding="utf-8"))
    status = {a["id"]: a.get("status") for a in live["arms"]}
    assert status.get("safe-2") == "active"
    assert status.get("bold-2") == "active"
    assert hc.active_accounts() == hc.ACCOUNTS


def test_returns_a_copy_not_the_module_dict():
    """A caller mutating the result must not corrupt the module-level ACCOUNTS."""
    got = hc.active_accounts()
    got.pop("safe", None)
    assert "safe" in hc.ACCOUNTS


# ------------------------------------------------------------------ the filter works

def test_retiring_safe2_drops_only_safe(tmp_path, monkeypatch):
    monkeypatch.setattr(hc, "FLEET_ACCOUNTS",
                        _write_accounts(tmp_path, {"safe-2": "retired", "bold-2": "active"}))
    got = hc.active_accounts()
    assert set(got) == {"bold"}
    assert got["bold"]["fleet_arm"] == "bold-2"


def test_retiring_bold2_drops_only_bold(tmp_path, monkeypatch):
    monkeypatch.setattr(hc, "FLEET_ACCOUNTS",
                        _write_accounts(tmp_path, {"safe-2": "active", "bold-2": "retired"}))
    assert set(hc.active_accounts()) == {"safe"}


@pytest.mark.parametrize("status", ["retired", "dormant", "pending_build", "paused", ""])
def test_only_the_literal_string_active_keeps_an_arm_trading(status, tmp_path, monkeypatch):
    """Fail-CLOSED on the trading decision: anything that is not exactly 'active' stops that
    arm. A typo'd status must not read as 'keep trading'."""
    monkeypatch.setattr(hc, "FLEET_ACCOUNTS",
                        _write_accounts(tmp_path, {"safe-2": status, "bold-2": "active"}))
    assert set(hc.active_accounts()) == {"bold"}


def test_arm_absent_from_accounts_json_keeps_trading(tmp_path, monkeypatch):
    """Absence is not retirement. Only an arm PRESENT and explicitly not-active is dropped."""
    monkeypatch.setattr(hc, "FLEET_ACCOUNTS", _write_accounts(tmp_path, {"bold-2": "active"}))
    assert set(hc.active_accounts()) == {"safe", "bold"}


# ------------------------------------------------------------------ fail-open

@pytest.mark.parametrize("body", ["", "{", "null", "[]", '{"arms": []}', '{"no_arms": 1}'])
def test_unreadable_or_empty_config_fails_OPEN(body, tmp_path, monkeypatch):
    """A config-read failure must never silently stop the live engine trading (OP-25).
    The failure mode accepted here is 'keeps trading during a config outage'; the failure
    mode refused is 'silently goes dark'."""
    p = tmp_path / "accounts.json"
    p.write_text(body, encoding="utf-8")
    monkeypatch.setattr(hc, "FLEET_ACCOUNTS", p)
    assert hc.active_accounts() == hc.ACCOUNTS


def test_missing_file_fails_OPEN(tmp_path, monkeypatch):
    monkeypatch.setattr(hc, "FLEET_ACCOUNTS", tmp_path / "does-not-exist.json")
    assert hc.active_accounts() == hc.ACCOUNTS


def test_all_arms_retired_fails_OPEN_rather_than_going_silently_dark(tmp_path, monkeypatch):
    """Retiring BOTH core arms is not a thing this switch may do implicitly -- that is a
    'stop the engine' decision and it belongs to the ARMED flag, not to a status field."""
    monkeypatch.setattr(hc, "FLEET_ACCOUNTS",
                        _write_accounts(tmp_path, {"safe-2": "retired", "bold-2": "retired"}))
    assert hc.active_accounts() == hc.ACCOUNTS


# ------------------------------------------------------------------ the second-order trap

def test_tick_marker_records_the_accounts_the_tick_actually_owed(tmp_path, monkeypatch):
    """If the marker still recorded sorted(ACCOUNTS) while the loop ran a filtered set, every
    paired-read consumer would wait forever for a row that is never coming."""
    marker = tmp_path / "core-decisions-tick.json"
    monkeypatch.setattr(hc, "TICK_MARKER", marker)
    monkeypatch.setattr(hc, "STATE", tmp_path)
    import datetime as dt
    hc._write_tick_marker("2026-08-31T10:00:00.000001",
                          dt.datetime(2026, 8, 31, 10, 0, 0), accounts=["bold"])
    assert json.loads(marker.read_text(encoding="utf-8"))["accounts"] == ["bold"]


def test_tick_marker_defaults_to_all_accounts_when_not_told(tmp_path, monkeypatch):
    """Back-compat: the pre-existing 2-arg call shape must keep its old payload."""
    marker = tmp_path / "core-decisions-tick.json"
    monkeypatch.setattr(hc, "TICK_MARKER", marker)
    monkeypatch.setattr(hc, "STATE", tmp_path)
    import datetime as dt
    hc._write_tick_marker("2026-08-31T10:00:00.000002", dt.datetime(2026, 8, 31, 10, 0, 0))
    assert json.loads(marker.read_text(encoding="utf-8"))["accounts"] == sorted(hc.ACCOUNTS)


def test_main_compares_ok_accounts_against_the_filtered_set_not_ACCOUNTS():
    """Source-level pin. The completeness check must not reference the hardcoded dict again;
    if someone 'simplifies' it back to set(ACCOUNTS), a retired arm freezes the marker."""
    src = (REPO / "setup" / "scripts" / "heartbeat_core.py").read_text(encoding="utf-8")
    assert "if set(ok_accounts) == set(tick_accounts):" in src
    assert "if set(ok_accounts) == set(ACCOUNTS):" not in src
    assert "for account in tick_accounts:" in src
    assert "for account in ACCOUNTS:" not in src
