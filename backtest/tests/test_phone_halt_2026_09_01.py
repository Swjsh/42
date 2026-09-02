"""TASK B5-phone-halt: J's phone-reachable emergency HALT/RESUME (setup/scripts/halt_command.py,
wired into setup/scripts/discord-responder.py).

Covers:
  * parse_command recognizes HALT <arm> / HALT ALL / HALT <arm|ALL> FLATTEN / RESUME <arm|ALL>,
    and returns None for everything else (so discord-responder.py's normal ship/shelve/revert/
    Q&A pipeline is untouched by a non-halt message).
  * Breaker writers: core-arm (safe-2/bold-2 schema) and fleet-arm (safe-3/risky-1 schema)
    each set tripped/reason/at/escalation_unresolved correctly while PRESERVING unrelated
    fields already in the file (never truncate to a fresh object).
  * FLATTEN refuses (does not call close_all_spy_options) on a failed broker read, and only
    acts on a confirmed-OK read.
  * Non-allowlisted authors are refused, allowlisted authors are dispatched.
  * The existing correction-capture denylist does not swallow HALT/RESUME text.

Every test operates on tmp_path fixtures or monkeypatched module globals -- NEVER on the real
automation/state/circuit-breaker.json, aggressive/circuit-breaker.json, fleet/*/circuit-
breaker.json, kill-switch-*.json, logs/halt-*.log, or STATUS.md. `_log_halt` and
`_flag_live_watch` are monkeypatched to no-ops in every test except their own two dedicated
I/O tests, which point explicitly at tmp_path.
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import halt_command as hc  # noqa: E402

# Captured BEFORE the autouse fixture below monkeypatches hc._log_halt / hc._flag_live_watch
# (module-level, so patching hc.<name> patches every reference to it) -- the two dedicated
# I/O tests near the bottom call these directly to exercise the REAL implementation.
_REAL_LOG_HALT = hc._log_halt
_REAL_FLAG_LIVE_WATCH = hc._flag_live_watch


@pytest.fixture(autouse=True)
def _no_real_io(monkeypatch):
    """Never let a test under this file touch the real logs/ or STATUS.md."""
    monkeypatch.setattr(hc, "_log_halt", lambda *a, **k: None)
    monkeypatch.setattr(hc, "_flag_live_watch", lambda *a, **k: None)


# ---------------------------------------------------------------------------------
# parse_command
# ---------------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("HALT safe-2", {"verb": "HALT", "target": "safe-2", "flatten": False}),
    ("halt SAFE-2", {"verb": "HALT", "target": "safe-2", "flatten": False}),
    ("  HALT   bold-2  ", {"verb": "HALT", "target": "bold-2", "flatten": False}),
    ("HALT ALL", {"verb": "HALT", "target": "ALL", "flatten": False}),
    ("halt all", {"verb": "HALT", "target": "ALL", "flatten": False}),
    ("HALT safe-3 FLATTEN", {"verb": "HALT", "target": "safe-3", "flatten": True}),
    ("HALT ALL FLATTEN", {"verb": "HALT", "target": "ALL", "flatten": True}),
    ("HALT risky-1 flatten", {"verb": "HALT", "target": "risky-1", "flatten": True}),
    ("RESUME safe-2", {"verb": "RESUME", "target": "safe-2", "flatten": False}),
    ("RESUME ALL", {"verb": "RESUME", "target": "ALL", "flatten": False}),
    ("resume risky-1", {"verb": "RESUME", "target": "risky-1", "flatten": False}),
])
def test_parse_command_recognizes_all_shapes(text, expected):
    assert hc.parse_command(text) == expected


@pytest.mark.parametrize("text", [
    "", None, "ship gp-2026-06-18-001", "shelve gp-2026-06-18-001",
    "revert gp-2026-06-18-001", "status?", "how are we doing today",
    "HALT", "HALTING safe-2", "RESUMED safe-2", "halting the account safe-2",
    "please HALT safe-2 immediately",
])
def test_parse_command_returns_none_for_non_halt_text(text):
    """CRITICAL: must not collide with the existing ship/shelve/revert/Q&A pipeline. A
    message like 'HALTING safe-2' or 'please HALT safe-2' must fall through to whatever
    discord-responder.py already does with it, not be silently mis-parsed as a command."""
    assert hc.parse_command(text) is None


def test_unknown_arm_inside_a_recognized_shape_is_not_none():
    """'HALT nonsense-arm' IS a recognized HALT shape (arm resolution happens later, in
    _execute/_resolve_targets, with the active roster in the refusal message)."""
    cmd = hc.parse_command("HALT nonsense-arm")
    assert cmd == {"verb": "HALT", "target": "nonsense-arm", "flatten": False}


# ---------------------------------------------------------------------------------
# Core-arm breaker writer (safe-2 / bold-2 schema)
# ---------------------------------------------------------------------------------

SAFE_BREAKER_FIXTURE = {
    "tripped": False, "tripped_at": None, "tripped_reason": None,
    "starting_equity_today": 5562.85, "current_equity": 5562.85,
    "daily_loss_limit_dollars": 1668.86, "daily_loss_limit_pct": 0.3,
    "max_drawdown_today_pct": 0.0, "day_trades_used_5d": 6,
    "last_reset": "2026-09-01T08:30:02-04:00",
}

BOLD_BREAKER_FIXTURE = {
    "daily_loss_kill_switch_pct": 0.5, "tripped": False, "session_id": "2026-09-01",
    "equity_start_of_day": 5749.47, "equity_current": 5749.47, "loss_pct": 0.0,
    "trip_reason": None, "tripped_at_et": None, "day_trades_used_5d": 5,
}


@pytest.fixture
def core_breakers(tmp_path, monkeypatch):
    safe_path = tmp_path / "circuit-breaker.json"
    bold_path = tmp_path / "aggressive-circuit-breaker.json"
    safe_path.write_text(json.dumps(SAFE_BREAKER_FIXTURE), encoding="utf-8")
    bold_path.write_text(json.dumps(BOLD_BREAKER_FIXTURE), encoding="utf-8")
    fake = {
        "safe-2": {"path": safe_path, "reason_field": "tripped_reason",
                   "at_field": "tripped_at"},
        "bold-2": {"path": bold_path, "reason_field": "trip_reason",
                   "at_field": "tripped_at_et"},
    }
    monkeypatch.setattr(hc, "CORE_BREAKERS", fake)
    return fake


def test_halt_core_arm_trips_and_preserves_other_fields(core_breakers):
    res = hc.halt_core_arm("safe-2", reason="J_HALT_DISCORD test", by="207983230618435584")
    assert res == {"arm": "safe-2", "kind": "core", "ok": True, "action": "TRIPPED"}
    written = json.loads(core_breakers["safe-2"]["path"].read_text(encoding="utf-8"))
    assert written["tripped"] is True
    assert written["tripped_reason"] == "J_HALT_DISCORD test"
    assert written["tripped_at"]  # non-empty
    assert written["escalation_unresolved"] is True
    # Untouched fields survive byte-identical.
    assert written["starting_equity_today"] == 5562.85
    assert written["daily_loss_limit_pct"] == 0.3
    assert written["day_trades_used_5d"] == 6


def test_halt_core_arm_bold_schema_uses_its_own_field_names(core_breakers):
    hc.halt_core_arm("bold-2", reason="J_HALT_DISCORD test", by="j")
    written = json.loads(core_breakers["bold-2"]["path"].read_text(encoding="utf-8"))
    assert written["tripped"] is True
    assert written["trip_reason"] == "J_HALT_DISCORD test"
    assert written["tripped_at_et"]
    assert written["escalation_unresolved"] is True
    # safe-2's field names must NOT appear on the bold schema (the C9 symmetry trap).
    assert "tripped_reason" not in written
    assert written["equity_start_of_day"] == 5749.47  # preserved


def test_resume_core_arm_clears_escalation_but_leaves_tripped(core_breakers):
    hc.halt_core_arm("safe-2", reason="x", by="j")
    res = hc.resume_core_arm("safe-2", by="j")
    assert res["tripped_still"] is True
    written = json.loads(core_breakers["safe-2"]["path"].read_text(encoding="utf-8"))
    assert written["tripped"] is True  # rule 9: RESUME never un-trips directly
    assert written["escalation_unresolved"] is False


def test_halt_core_arm_missing_file_reports_error(tmp_path, monkeypatch):
    fake = {"safe-2": {"path": tmp_path / "nope.json", "reason_field": "tripped_reason",
                        "at_field": "tripped_at"}}
    monkeypatch.setattr(hc, "CORE_BREAKERS", fake)
    res = hc.halt_core_arm("safe-2", reason="x", by="j")
    assert res["ok"] is False
    assert res["action"] == "ERROR"


# ---------------------------------------------------------------------------------
# Fleet-arm breaker writer (safe-3 / risky-1 schema, automation/state/fleet/<arm>/)
# ---------------------------------------------------------------------------------

FLEET_BREAKER_FIXTURE = {
    "tripped": False, "tripped_at": None, "tripped_reason": None,
    "starting_equity_today": 5852.7, "current_equity": 5852.7,
    "daily_loss_limit_pct": 0.3, "max_drawdown_today_pct": 0.0,
    "last_reset": "2026-09-01T09:31:04-0400",
    "_note": "fleet arm safe-3 daily kill-switch (-30% of SoD).",
}


@pytest.fixture
def fleet_dirs(tmp_path, monkeypatch):
    fleet_dir = tmp_path / "fleet"
    state_dir = tmp_path / "state"
    (fleet_dir / "safe-3").mkdir(parents=True)
    (state_dir).mkdir(parents=True)
    (fleet_dir / "safe-3" / "circuit-breaker.json").write_text(
        json.dumps(FLEET_BREAKER_FIXTURE), encoding="utf-8"
    )
    monkeypatch.setattr(hc, "FLEET_DIR", fleet_dir)
    monkeypatch.setattr(hc, "STATE_DIR", state_dir)
    return {"fleet_dir": fleet_dir, "state_dir": state_dir}


def test_halt_fleet_arm_writes_the_enforced_breaker_and_the_audit_file(fleet_dirs):
    res = hc.halt_fleet_arm("safe-3", reason="J_HALT_DISCORD test", by="j")
    assert res == {"arm": "safe-3", "kind": "fleet", "ok": True, "action": "TRIPPED"}

    # THE FILE fleet_live.py's _load_or_arm_breaker() actually reads every tick.
    enforced = json.loads(
        (fleet_dirs["fleet_dir"] / "safe-3" / "circuit-breaker.json").read_text(encoding="utf-8")
    )
    assert enforced["tripped"] is True
    assert enforced["tripped_reason"] == "J_HALT_DISCORD test"
    assert enforced["tripped_at"]
    assert enforced["starting_equity_today"] == 5852.7  # preserved

    # The audit-parity file eod_flatten.py's escalation path also writes (unenforced today).
    ks = json.loads(
        (fleet_dirs["state_dir"] / "kill-switch-safe-3.json").read_text(encoding="utf-8")
    )
    assert ks["armed"] is True
    assert ks["arm"] == "safe-3"


def test_halt_fleet_arm_creates_breaker_if_absent(fleet_dirs):
    """safe-3 had a pre-existing file (via fixture); risky-1 does not -- HALT must still
    work (originate a fresh breaker) rather than refuse."""
    res = hc.halt_fleet_arm("risky-1", reason="x", by="j")
    assert res["ok"] is True
    written = json.loads(
        (fleet_dirs["fleet_dir"] / "risky-1" / "circuit-breaker.json").read_text(encoding="utf-8")
    )
    assert written["tripped"] is True


def test_resume_fleet_arm_clears_escalation_and_removes_kill_switch_file(fleet_dirs):
    hc.halt_fleet_arm("safe-3", reason="x", by="j")
    ks_path = fleet_dirs["state_dir"] / "kill-switch-safe-3.json"
    assert ks_path.exists()
    res = hc.resume_fleet_arm("safe-3", by="j")
    assert res["tripped_still"] is True
    assert not ks_path.exists()
    written = json.loads(
        (fleet_dirs["fleet_dir"] / "safe-3" / "circuit-breaker.json").read_text(encoding="utf-8")
    )
    assert written["tripped"] is True
    assert written["escalation_unresolved"] is False


# ---------------------------------------------------------------------------------
# FLATTEN: fail-closed on a failed broker read (the task's explicit requirement)
# ---------------------------------------------------------------------------------

class _FakeFleetBroker:
    def __init__(self, *, creds=None, positions=None, read_ok=True, close_result=None):
        self._creds = creds if creds is not None else {"safe-3": {"key": "k", "secret": "s",
                                                                   "base_url": "https://x"}}
        self._positions = positions or []
        self._read_ok = read_ok
        self._close_result = close_result or {"closed": [], "errors": []}
        self.close_calls = []

    def load_creds(self):
        return self._creds

    def open_spy_option_positions_checked(self, creds):
        return (list(self._positions), self._read_ok)

    def close_all_spy_options(self, creds, *, live, arm=None, reason=None):
        self.close_calls.append({"live": live, "arm": arm, "reason": reason})
        return self._close_result


def test_flatten_refuses_when_broker_read_fails(monkeypatch):
    fake = _FakeFleetBroker(read_ok=False)
    monkeypatch.setattr(hc, "fleet_broker", fake)
    res = hc.flatten_arm("safe-3", by="j")
    assert res["ok"] is False
    assert res["action"] == "ABORT_READ_FAILED"
    assert "broker read failed" in res["message"]
    assert fake.close_calls == [], "a failed read must NEVER be treated as green-light to flatten"


def test_flatten_noop_when_confirmed_flat(monkeypatch):
    fake = _FakeFleetBroker(read_ok=True, positions=[])
    monkeypatch.setattr(hc, "fleet_broker", fake)
    res = hc.flatten_arm("safe-3", by="j")
    assert res["action"] == "NOOP_ALREADY_FLAT"
    assert fake.close_calls == []


def test_flatten_submits_live_true_when_positions_open(monkeypatch):
    fake = _FakeFleetBroker(
        read_ok=True,
        positions=[{"symbol": "SPY260901C00760000", "qty": "2"}],
        close_result={"closed": ["SPY260901C00760000"], "errors": []},
    )
    monkeypatch.setattr(hc, "fleet_broker", fake)
    res = hc.flatten_arm("safe-3", by="207983230618435584")
    assert res["action"] == "FLATTENED"
    assert res["live_flag_used"] is True
    assert fake.close_calls == [{"live": True, "arm": "safe-3",
                                  "reason": fake.close_calls[0]["reason"]}]
    assert "J_HALT_DISCORD_FLATTEN" in fake.close_calls[0]["reason"]
    assert res["before"] == ["SPY260901C00760000"]


def test_flatten_no_creds_for_arm_refuses(monkeypatch):
    fake = _FakeFleetBroker(creds={})
    monkeypatch.setattr(hc, "fleet_broker", fake)
    res = hc.flatten_arm("safe-3", by="j")
    assert res["ok"] is False
    assert res["action"] == "ABORT_NO_CREDS"
    assert fake.close_calls == []


# ---------------------------------------------------------------------------------
# Allowlist / dispatch
# ---------------------------------------------------------------------------------

J_ID = "207983230618435584"
STRANGER_ID = "999999999999999999"


def test_non_allowlisted_author_is_refused(monkeypatch):
    monkeypatch.setattr(hc, "_active_spy_arms", lambda: ["safe-2", "bold-2", "safe-3", "risky-1"])
    ack = hc.handle_message("HALT safe-2", STRANGER_ID, allowlist={J_ID})
    assert ack is not None
    assert "Refused" in ack
    assert STRANGER_ID in ack


def test_allowlisted_author_is_dispatched(core_breakers, monkeypatch):
    monkeypatch.setattr(hc, "_active_spy_arms", lambda: ["safe-2", "bold-2"])
    ack = hc.handle_message("HALT safe-2", J_ID, allowlist={J_ID})
    assert ack is not None
    assert "HALTED" in ack
    written = json.loads(core_breakers["safe-2"]["path"].read_text(encoding="utf-8"))
    assert written["tripped"] is True


def test_non_halt_message_returns_none_regardless_of_author(monkeypatch):
    monkeypatch.setattr(hc, "_active_spy_arms", lambda: ["safe-2"])
    assert hc.handle_message("ship gp-2026-06-18-001", J_ID, allowlist={J_ID}) is None
    assert hc.handle_message("status?", STRANGER_ID, allowlist={J_ID}) is None


def test_empty_allowlist_refuses_even_j(monkeypatch):
    """If .discord-config.json is unreadable/empty, NO ONE is allowlisted -- fail closed,
    never fail open to 'anyone can HALT'."""
    monkeypatch.setattr(hc, "_active_spy_arms", lambda: ["safe-2"])
    ack = hc.handle_message("HALT safe-2", J_ID, allowlist=set())
    assert "Refused" in ack


def test_halt_all_dispatches_every_active_arm(core_breakers, fleet_dirs, monkeypatch):
    monkeypatch.setattr(hc, "_active_spy_arms",
                         lambda: ["safe-3", "safe-2", "risky-1", "bold-2"])
    ack = hc.handle_message("HALT ALL", J_ID, allowlist={J_ID})
    for arm in ("safe-3", "safe-2", "risky-1", "bold-2"):
        assert arm in ack
    safe2 = json.loads(core_breakers["safe-2"]["path"].read_text(encoding="utf-8"))
    bold2 = json.loads(core_breakers["bold-2"]["path"].read_text(encoding="utf-8"))
    safe3 = json.loads((fleet_dirs["fleet_dir"] / "safe-3" / "circuit-breaker.json")
                        .read_text(encoding="utf-8"))
    risky1 = json.loads((fleet_dirs["fleet_dir"] / "risky-1" / "circuit-breaker.json")
                         .read_text(encoding="utf-8"))
    assert safe2["tripped"] and bold2["tripped"] and safe3["tripped"] and risky1["tripped"]


def test_unknown_arm_is_refused_with_active_roster_listed(monkeypatch):
    monkeypatch.setattr(hc, "_active_spy_arms", lambda: ["safe-2", "bold-2", "safe-3", "risky-1"])
    ack = hc.handle_message("HALT not-a-real-arm", J_ID, allowlist={J_ID})
    assert "Unknown arm" in ack
    assert "safe-2" in ack and "risky-1" in ack


def test_halt_flatten_composes_halt_then_flatten(core_breakers, monkeypatch):
    """'HALT safe-2 FLATTEN' on a CORE arm: HALT still uses the core-breaker writer;
    FLATTEN still goes through fleet_broker (core arms are real broker accounts too --
    fleet_broker.load_creds() covers all arms including safe-2/bold-2, confirmed against
    the live secrets.json roster)."""
    monkeypatch.setattr(hc, "_active_spy_arms", lambda: ["safe-2"])
    fake = _FakeFleetBroker(
        creds={"safe-2": {"key": "k", "secret": "s", "base_url": "https://x"}},
        positions=[{"symbol": "SPY260901P00755000", "qty": "3"}],
        close_result={"closed": ["SPY260901P00755000"], "errors": []},
    )
    monkeypatch.setattr(hc, "fleet_broker", fake)
    ack = hc.handle_message("HALT safe-2 FLATTEN", J_ID, allowlist={J_ID})
    assert "HALTED" in ack
    assert "live=True order submitted" in ack
    assert fake.close_calls[0]["live"] is True
    written = json.loads(core_breakers["safe-2"]["path"].read_text(encoding="utf-8"))
    assert written["tripped"] is True


def test_flatten_refused_message_surfaces_in_halt_flatten_ack(core_breakers, monkeypatch):
    monkeypatch.setattr(hc, "_active_spy_arms", lambda: ["safe-2"])
    fake = _FakeFleetBroker(
        creds={"safe-2": {"key": "k", "secret": "s", "base_url": "https://x"}},
        read_ok=False,
    )
    monkeypatch.setattr(hc, "fleet_broker", fake)
    ack = hc.handle_message("HALT safe-2 FLATTEN", J_ID, allowlist={J_ID})
    assert "HALTED" in ack  # the halt itself still succeeded
    assert "broker read failed -- NOT flattening" in ack
    assert fake.close_calls == []


# ---------------------------------------------------------------------------------
# _log_halt / _flag_live_watch -- dedicated I/O tests, explicit tmp paths only.
# ---------------------------------------------------------------------------------

def test_log_halt_writes_to_the_given_log_dir(tmp_path):
    # Use the REAL function captured before the autouse fixture patched hc._log_halt --
    # `hc._log_halt` at this point IN THIS TEST is the no-op stub (same module object).
    _REAL_LOG_HALT("HALT test-arm by=j reason=x", log_dir=tmp_path)
    files = list(tmp_path.glob("halt-*.log"))
    assert len(files) == 1
    assert "HALT test-arm by=j reason=x" in files[0].read_text(encoding="utf-8")


def test_flag_live_watch_creates_section_and_inserts_newest_first(tmp_path):
    status = tmp_path / "STATUS.md"
    status.write_text("## Known broken\n\n- nothing\n", encoding="utf-8")
    _REAL_FLAG_LIVE_WATCH("- [ts] PHONE HALT :: HALT safe-2 by=j", status_md_path=status)
    text = status.read_text(encoding="utf-8")
    assert "## Live watch" in text
    assert "PHONE HALT :: HALT safe-2" in text
    assert text.index("## Live watch") < text.index("## Known broken")

    _REAL_FLAG_LIVE_WATCH("- [ts2] PHONE HALT :: RESUME safe-2 by=j", status_md_path=status)
    text2 = status.read_text(encoding="utf-8")
    # newest line inserted right after the marker -> appears BEFORE the first HALT line.
    assert text2.index("RESUME safe-2") < text2.index("HALT safe-2")


# ---------------------------------------------------------------------------------
# Correction-denylist parity (discord-responder.py) -- HALT/RESUME must not be swallowed.
# ---------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def responder_module():
    spec = importlib.util.spec_from_file_location(
        "_discord_responder_probe", SCRIPTS / "discord-responder.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_discord_responder_probe"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("text", [
    "HALT safe-2", "HALT ALL", "HALT safe-3 FLATTEN", "RESUME safe-2", "RESUME ALL",
    "HALT bold-2 -- the day is going wrong, stop trading now",
])
def test_correction_denylist_does_not_swallow_halt(responder_module, text):
    """_detect_correction must not fire on ordinary HALT/RESUME text (it would only ever
    TAG the message for skill-author triage, never consume it -- but confirming it does
    not even tag closes the task's explicit 'ensure the denylist does not swallow
    HALT/RESUME' requirement with a real assertion instead of a read-the-code claim)."""
    assert responder_module._detect_correction(text) is None


def test_responder_module_imports_halt_command(responder_module):
    """Wiring check: discord-responder.py's module namespace has halt_command available
    at the name main() calls (halt_command.handle_message)."""
    assert hasattr(responder_module, "halt_command")
    assert responder_module.halt_command is hc
    assert hasattr(responder_module.halt_command, "handle_message")
