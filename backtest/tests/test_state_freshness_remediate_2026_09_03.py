"""Guard tests for setup/scripts/state_freshness_remediate.py -- the DIRECT-INVOCATION
remediator for state_freshness_audit's STALE-BY-SESSION entries, built 2026-09-03 for queue
item STATE-FRESHNESS-AUTO-REMEDIATOR (self-generated 2026-08-10 conductor AFTERHOURS from
strategy/candidates/_lesson-inbox/state-freshness-detector-no-remediator-2026-08-10.md).

Coverage (each a RED-proofed contract -- see the docstring on each test for the exact
behavior it locks in):
  * a STALE-BY-SESSION, allowlisted entry gets its writer invoked (mocked) and, once the
    post-invocation audit says GREEN, is recorded remediated=True
  * a MISSING entry is NEVER invoked -- needs a human
  * an UNKNOWN (malformed) entry is NEVER invoked
  * a STALE-BY-AGE entry is NEVER invoked (only the session-date axis is in scope)
  * a writer NOT on WRITER_ALLOWLIST is reported ("not_on_allowlist"), never run
  * a second attempt for the same writer within the cooldown window is skipped
  * a producer that raises leaves the entry stale (remediated is never force-set True) and
    no exception escapes run()
  * run() refuses outright during the 09:30-15:55 ET trading band -- audit_fn is never even
    called
  * `run()` never raises even when audit_fn itself raises (fails open to UNKNOWN)
  * the real `_default_starter` never raises on a nonexistent interpreter/binary

Pure monkeypatched audit_fn/starter + a frozen clock. No real subprocess, no real market
data, no Windows dependency.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import state_freshness_remediate as sfr  # noqa: E402

# Wednesday 2026-09-02, 20:00 ET -- well outside the RTH band.
AFTER_HOURS = datetime(2026, 9, 2, 20, 0, 0)
# Wednesday 2026-09-02, 11:00 ET -- inside the RTH band.
RTH = datetime(2026, 9, 2, 11, 0, 0)
# Saturday 2026-09-05, 11:00 ET -- weekend, same wall-clock as RTH but never a trading day.
WEEKEND = datetime(2026, 9, 5, 11, 0, 0)

ALLOWLISTED_WRITER = "setup/scripts/confluence_producer.py"
NON_ALLOWLISTED_WRITER = "setup/scripts/heartbeat_core.py"


def _entry(path="automation/state/confluence-zones.json", writer=ALLOWLISTED_WRITER,
           status="RED", reasons=None):
    return {
        "path": path,
        "writer": writer,
        "task": "Gamma_Confluence",
        "status": status,
        "reasons": reasons if reasons is not None else [
            f"{path} STALE BY SESSION: generated_at=2026-09-01 but expected 2026-09-02 "
            f"(writer {writer} / task Gamma_Confluence is not writing)"
        ],
    }


def _audit_with(entries, verdict="RED"):
    def _fn():
        return {"verdict": verdict, "checked_at_et": "2026-09-02 20:00:00", "entries": entries}
    return _fn


# ---------------------------------------------------------------------------
# _is_stale_by_session_only
# ---------------------------------------------------------------------------

def test_stale_by_session_only_true_for_pure_session_staleness():
    assert sfr._is_stale_by_session_only(_entry()) is True


def test_stale_by_session_only_false_for_missing():
    e = _entry(reasons=["automation/state/confluence-zones.json MISSING"])
    assert sfr._is_stale_by_session_only(e) is False


def test_stale_by_session_only_false_for_stale_by_age():
    e = _entry(reasons=[
        "automation/state/confluence-zones.json STALE BY AGE: 45.0m > 40m budget while its "
        "window 09:32-16:05 is OPEN (writer x / task y)"
    ])
    assert sfr._is_stale_by_session_only(e) is False


def test_stale_by_session_only_false_for_unknown_status():
    e = _entry(status="UNKNOWN", reasons=["unreadable (OSError)"])
    assert sfr._is_stale_by_session_only(e) is False


def test_stale_by_session_only_false_for_green():
    e = _entry(status="GREEN", reasons=[])
    assert sfr._is_stale_by_session_only(e) is False


# ---------------------------------------------------------------------------
# run() -- core remediation loop
# ---------------------------------------------------------------------------

def test_run_invokes_allowlisted_writer_and_marks_remediated_from_post_audit(monkeypatch, tmp_path):
    monkeypatch.setattr(sfr, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(sfr, "LOG_PATH", tmp_path / "log.jsonl")

    stale_entry = _entry()
    fresh_entry = _entry(status="GREEN", reasons=[])
    calls = []
    audit_calls = {"n": 0}

    def fake_audit():
        audit_calls["n"] += 1
        # first call (pre): stale.  second call (verify-after): fresh.
        return {"verdict": "RED", "checked_at_et": "x",
                "entries": [stale_entry if audit_calls["n"] == 1 else fresh_entry]}

    def fake_starter(script_rel, dry_run=False):
        calls.append((script_rel, dry_run))
        return {"invoked": True, "returncode": 0}

    out = sfr.run(now_et=AFTER_HOURS, starter=fake_starter, audit_fn=fake_audit)

    assert calls == [(ALLOWLISTED_WRITER, False)]
    assert out["n_candidates"] == 1
    assert out["actions"][0]["outcome"] == "invoked"
    assert out["actions"][0]["remediated"] is True
    assert audit_calls["n"] == 2  # pre + verify-after


def test_run_never_invokes_missing_entry(monkeypatch, tmp_path):
    monkeypatch.setattr(sfr, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(sfr, "LOG_PATH", tmp_path / "log.jsonl")

    missing = _entry(reasons=["automation/state/confluence-zones.json MISSING"])
    calls = []

    def fake_starter(script_rel, dry_run=False):
        calls.append(script_rel)
        return {"invoked": True, "returncode": 0}

    out = sfr.run(now_et=AFTER_HOURS, starter=fake_starter, audit_fn=_audit_with([missing]))

    assert calls == []
    assert out["n_candidates"] == 0
    assert out["actions"] == []


def test_run_never_invokes_unknown_entry(monkeypatch, tmp_path):
    monkeypatch.setattr(sfr, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(sfr, "LOG_PATH", tmp_path / "log.jsonl")

    unknown = _entry(status="UNKNOWN", reasons=["malformed json (line 3)"])
    calls = []

    def fake_starter(script_rel, dry_run=False):
        calls.append(script_rel)
        return {"invoked": True, "returncode": 0}

    out = sfr.run(now_et=AFTER_HOURS, starter=fake_starter, audit_fn=_audit_with([unknown]))

    assert calls == []
    assert out["n_candidates"] == 0


def test_run_never_invokes_stale_by_age_entry(monkeypatch, tmp_path):
    monkeypatch.setattr(sfr, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(sfr, "LOG_PATH", tmp_path / "log.jsonl")

    stale_age = _entry(reasons=[
        "automation/state/confluence-zones.json STALE BY AGE: 45.0m > 40m budget while its "
        "window 09:32-16:05 is OPEN (writer x / task y)"
    ])
    calls = []

    def fake_starter(script_rel, dry_run=False):
        calls.append(script_rel)
        return {"invoked": True, "returncode": 0}

    out = sfr.run(now_et=AFTER_HOURS, starter=fake_starter, audit_fn=_audit_with([stale_age]))

    assert calls == []
    assert out["n_candidates"] == 0


def test_run_reports_non_allowlisted_writer_without_running_it(monkeypatch, tmp_path):
    monkeypatch.setattr(sfr, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(sfr, "LOG_PATH", tmp_path / "log.jsonl")

    e = _entry(path="automation/state/core-decisions.jsonl", writer=NON_ALLOWLISTED_WRITER)
    calls = []

    def fake_starter(script_rel, dry_run=False):
        calls.append(script_rel)
        return {"invoked": True, "returncode": 0}

    out = sfr.run(now_et=AFTER_HOURS, starter=fake_starter, audit_fn=_audit_with([e]))

    assert calls == []
    assert out["actions"][0]["outcome"] == "not_on_allowlist"
    assert "resolved_script" not in out["actions"][0]


def test_run_respects_per_writer_cooldown(monkeypatch, tmp_path):
    monkeypatch.setattr(sfr, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(sfr, "LOG_PATH", tmp_path / "log.jsonl")

    stale_entry = _entry()
    calls = []

    def fake_starter(script_rel, dry_run=False):
        calls.append(script_rel)
        return {"invoked": True, "returncode": 0}

    sfr.run(now_et=AFTER_HOURS, starter=fake_starter,
            audit_fn=_audit_with([stale_entry]), cooldown_min=60)
    assert calls == [ALLOWLISTED_WRITER]

    # second attempt 5 minutes later -- within the 60-min cooldown -- must NOT re-invoke
    out2 = sfr.run(now_et=AFTER_HOURS + timedelta(minutes=5), starter=fake_starter,
                   audit_fn=_audit_with([stale_entry]), cooldown_min=60)
    assert calls == [ALLOWLISTED_WRITER]
    assert out2["actions"][0]["outcome"] == "skipped_cooldown"

    # third attempt past the cooldown window -- must re-invoke
    out3 = sfr.run(now_et=AFTER_HOURS + timedelta(minutes=65), starter=fake_starter,
                   audit_fn=_audit_with([stale_entry]), cooldown_min=60)
    assert calls == [ALLOWLISTED_WRITER, ALLOWLISTED_WRITER]
    assert out3["actions"][0]["outcome"] == "invoked"


def test_run_producer_raises_leaves_entry_stale_no_exception_escapes(monkeypatch, tmp_path):
    monkeypatch.setattr(sfr, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(sfr, "LOG_PATH", tmp_path / "log.jsonl")

    stale_entry = _entry()

    def raising_starter(script_rel, dry_run=False):
        # simulate what _default_starter itself would return on a caught exception --
        # run() must never let this propagate, and must not claim remediated=True.
        return {"invoked": True, "error": "RuntimeError: boom",
                "traceback_tail": "Traceback...boom"}

    # post-audit still shows the SAME stale entry (producer didn't actually fix anything)
    out = sfr.run(now_et=AFTER_HOURS, starter=raising_starter,
                  audit_fn=_audit_with([stale_entry]))

    assert out["actions"][0]["outcome"] == "invoked"
    assert out["actions"][0]["remediated"] is False
    assert "error" in out["actions"][0]


def test_run_refuses_during_trading_band_audit_never_called(monkeypatch, tmp_path):
    monkeypatch.setattr(sfr, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(sfr, "LOG_PATH", tmp_path / "log.jsonl")

    audit_called = {"n": 0}

    def fake_audit():
        audit_called["n"] += 1
        return {"verdict": "RED", "entries": [_entry()]}

    out = sfr.run(now_et=RTH, starter=lambda *a, **k: {"invoked": True}, audit_fn=fake_audit)

    assert out["refused"] is True
    assert "trading band" in out["reason"]
    assert audit_called["n"] == 0
    assert out["actions"] == []


def test_run_does_not_refuse_on_weekend_same_wall_clock(monkeypatch, tmp_path):
    monkeypatch.setattr(sfr, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(sfr, "LOG_PATH", tmp_path / "log.jsonl")

    out = sfr.run(now_et=WEEKEND, starter=lambda *a, **k: {"invoked": True, "returncode": 0},
                  audit_fn=_audit_with([_entry()]))
    assert out["refused"] is False


def test_run_dry_run_never_invokes_never_persists_cooldown(monkeypatch, tmp_path):
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(sfr, "STATE_PATH", state_path)
    monkeypatch.setattr(sfr, "LOG_PATH", tmp_path / "log.jsonl")

    calls = []

    def fake_starter(script_rel, dry_run=False):
        assert dry_run is True
        calls.append(script_rel)
        return {"invoked": False, "dry_run": True, "cmd": ["python", script_rel]}

    out = sfr.run(now_et=AFTER_HOURS, dry_run=True, starter=fake_starter,
                  audit_fn=_audit_with([_entry()]))

    assert calls == [ALLOWLISTED_WRITER]  # starter IS called so the caller can see the cmd
    assert out["actions"][0]["outcome"] == "dry_run"
    assert "remediated" not in out["actions"][0]
    assert not state_path.exists()  # cooldown must never persist on a dry run


def test_run_fails_open_when_audit_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(sfr, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(sfr, "LOG_PATH", tmp_path / "log.jsonl")

    def _raise():
        raise RuntimeError("boom")

    out = sfr.run(now_et=AFTER_HOURS, starter=lambda *a, **k: {"invoked": True},
                  audit_fn=_raise)
    assert out["verdict"] == "UNKNOWN"
    assert out["actions"] == []


def test_run_logs_real_actions(monkeypatch, tmp_path):
    monkeypatch.setattr(sfr, "STATE_PATH", tmp_path / "state.json")
    log_path = tmp_path / "log.jsonl"
    monkeypatch.setattr(sfr, "LOG_PATH", log_path)

    stale_entry = _entry()
    fresh_entry = _entry(status="GREEN", reasons=[])
    n = {"c": 0}

    def fake_audit():
        n["c"] += 1
        return {"verdict": "RED", "entries": [stale_entry if n["c"] == 1 else fresh_entry]}

    sfr.run(now_et=AFTER_HOURS, starter=lambda *a, **k: {"invoked": True, "returncode": 0},
            audit_fn=fake_audit)

    assert log_path.exists()
    row = json.loads(log_path.read_text(encoding="utf-8").splitlines()[-1])
    assert row["n_candidates"] == 1


def test_real_default_starter_never_raises_on_bad_interpreter(monkeypatch):
    """Belt-and-braces: even the REAL _default_starter must fail open if the subprocess
    call itself blows up (bad interpreter path, permissions, etc)."""
    def _boom(*a, **k):
        raise FileNotFoundError("no interpreter here")
    monkeypatch.setattr(sfr.subprocess, "run", _boom)
    result = sfr._default_starter("setup/scripts/confluence_producer.py")
    assert result["invoked"] is True
    assert "error" in result
    assert "traceback_tail" in result


def test_writer_allowlist_excludes_known_dangerous_writers():
    """Locks in the deliberate exclusions from the module docstring -- if any of these
    ever appear in WRITER_ALLOWLIST it is a live-order or kill-switch blast-radius bug,
    not a style nit."""
    dangerous = {
        "setup/scripts/heartbeat_core.py",
        "automation/state/fleet/build_shared_signal.py",
        "automation/prompts/premarket.md + setup/scripts/daily_loss_guard.py",
        "setup/scripts/futures_trader_runner.py -> futures_trader_core._write_heartbeat",
        "setup/scripts/futures_trader_runner.py --backend tastytrade",
        "backtest/futures/futures_live_data.write_freshness_snapshot",
        "backtest/futures/futures_eod.py",
        "automation/prompts/premarket.md + setup/scripts/premarket_deterministic_fallback.py",
    }
    assert dangerous.isdisjoint(sfr.WRITER_ALLOWLIST.keys())
