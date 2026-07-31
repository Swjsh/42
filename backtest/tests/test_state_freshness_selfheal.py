"""Guard tests for setup/scripts/state_freshness_selfheal.py -- the REMEDIATION half
of state_freshness_audit.py, built 2026-07-31 after a LIVE incident: Gamma_TradeToday,
Gamma_BrokerFills and Gamma_EmaSnapshot all last fired 2026-07-29 despite Enabled=True,
State=Ready, LastTaskResult=0 (no crash), no hung process on the box, and a MANUAL
Start-ScheduledTask call succeeding immediately -- i.e. the scheduled trigger silently
stopped firing for >24h with zero Task Scheduler error signal, and NOTHING recovered it.
state_freshness_audit already DETECTED this (state_freshness RED in engine-health.json)
but only reports -- this module closes the loop by force-starting the mapped task.

Coverage (each a RED-proofed contract):
  * extract_task_name resolves a normal 'Gamma_X (...)' field to 'Gamma_X'
  * extract_task_name returns None for manual/n/a/empty/multi-writer/non-Gamma fields
  * run() calls the starter for each RED entry with a resolvable task
  * run() SKIPS a RED entry with an unresolvable task (never guesses)
  * run() respects cooldown: a second call within cooldown_min does NOT re-start
  * run() does NOT persist cooldown / does NOT call the starter's mutation on --dry-run
    (starter is still invoked so callers can see what WOULD happen, but with dry_run=True)
  * run() fails OPEN (never raises) when the underlying audit() raises
  * GREEN/YELLOW entries are never acted on -- only RED
  * every real action is appended to the log file

Pure filesystem + monkeypatched starter/audit. No network, no real Start-ScheduledTask
call, no Windows dependency.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import state_freshness_selfheal as sfh  # noqa: E402

NOW = datetime(2026, 7, 31, 1, 0, 0)


# ---------------------------------------------------------------------------
# extract_task_name
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("field,expected", [
    ("Gamma_TradeToday (every 2 min, 09:30-16:00 ET wd)", "Gamma_TradeToday"),
    ("Gamma_LevelRefresh (every 5 min, 24/7)", "Gamma_LevelRefresh"),
    ("Gamma_BrokerFills", "Gamma_BrokerFills"),
])
def test_extract_task_name_resolves_normal_field(field, expected):
    assert sfh.extract_task_name(field) == expected


@pytest.mark.parametrize("field", [
    None, "", "manual", "MANUAL", "n/a", "none",
    "premarket.md + daily_loss_guard.py",  # ambiguous multi-writer
    "42",  # not Gamma_-prefixed
    123,   # not a string at all
])
def test_extract_task_name_refuses_to_guess(field):
    assert sfh.extract_task_name(field) is None


# ---------------------------------------------------------------------------
# run() -- core remediation loop
# ---------------------------------------------------------------------------

def _fake_audit_red(task_field="Gamma_TradeToday (every 2 min)"):
    def _audit():
        return {
            "verdict": "RED",
            "checked_at_et": "2026-07-31 01:00:00",
            "entries": [
                {"path": "automation/state/trade-today.json", "status": "RED",
                 "task": task_field, "reasons": ["trade-today.json STALE BY SESSION"]},
                {"path": "automation/state/context-bundle.json", "status": "GREEN",
                 "task": "Gamma_ContextBundle", "reasons": []},
            ],
        }
    return _audit


def test_run_starts_the_mapped_task_for_a_red_entry(monkeypatch, tmp_path):
    monkeypatch.setattr(sfh, "sfa", type("M", (), {"audit": staticmethod(_fake_audit_red())}))
    monkeypatch.setattr(sfh, "COOLDOWN_PATH", tmp_path / "cooldown.json")
    monkeypatch.setattr(sfh, "LOG_PATH", tmp_path / "log.jsonl")

    calls = []

    def fake_starter(task_name, dry_run=False):
        calls.append((task_name, dry_run))
        return {"started": True, "returncode": 0}

    out = sfh.run(now=NOW, starter=fake_starter)

    assert out["n_red"] == 1
    assert calls == [("Gamma_TradeToday", False)]
    assert out["actions"][0]["outcome"] == "start_attempted"
    assert out["actions"][0]["started"] is True


def test_run_skips_green_entries(monkeypatch, tmp_path):
    monkeypatch.setattr(sfh, "sfa", type("M", (), {"audit": staticmethod(_fake_audit_red())}))
    monkeypatch.setattr(sfh, "COOLDOWN_PATH", tmp_path / "cooldown.json")
    monkeypatch.setattr(sfh, "LOG_PATH", tmp_path / "log.jsonl")

    calls = []

    def fake_starter(task_name, dry_run=False):
        calls.append(task_name)
        return {"started": True}

    out = sfh.run(now=NOW, starter=fake_starter)
    # sanity: the fixture's GREEN entry (context-bundle) never triggers a start
    assert all(a["path"] != "automation/state/context-bundle.json" for a in out["actions"])


def test_run_skips_unresolvable_task_never_guesses(monkeypatch, tmp_path):
    monkeypatch.setattr(sfh, "sfa", type(
        "M", (), {"audit": staticmethod(_fake_audit_red(task_field="manual"))}))
    monkeypatch.setattr(sfh, "COOLDOWN_PATH", tmp_path / "cooldown.json")
    monkeypatch.setattr(sfh, "LOG_PATH", tmp_path / "log.jsonl")

    calls = []

    def fake_starter(task_name, dry_run=False):
        calls.append(task_name)
        return {"started": True}

    out = sfh.run(now=NOW, starter=fake_starter)
    assert calls == []
    assert out["actions"][0]["outcome"] == "skipped_unresolvable_task"


def test_run_respects_cooldown(monkeypatch, tmp_path):
    monkeypatch.setattr(sfh, "sfa", type("M", (), {"audit": staticmethod(_fake_audit_red())}))
    monkeypatch.setattr(sfh, "COOLDOWN_PATH", tmp_path / "cooldown.json")
    monkeypatch.setattr(sfh, "LOG_PATH", tmp_path / "log.jsonl")

    calls = []

    def fake_starter(task_name, dry_run=False):
        calls.append(task_name)
        return {"started": True}

    sfh.run(now=NOW, starter=fake_starter, cooldown_min=20)
    assert calls == ["Gamma_TradeToday"]

    # Second call 5 minutes later -- still within the 20-min cooldown -- must NOT re-start.
    from datetime import timedelta
    out2 = sfh.run(now=NOW + timedelta(minutes=5), starter=fake_starter, cooldown_min=20)
    assert calls == ["Gamma_TradeToday"]  # unchanged
    assert out2["actions"][0]["outcome"] == "skipped_cooldown"

    # Third call past the cooldown window -- must re-start.
    out3 = sfh.run(now=NOW + timedelta(minutes=25), starter=fake_starter, cooldown_min=20)
    assert calls == ["Gamma_TradeToday", "Gamma_TradeToday"]
    assert out3["actions"][0]["outcome"] == "start_attempted"


def test_run_dry_run_still_calls_starter_but_flags_dry_run(monkeypatch, tmp_path):
    monkeypatch.setattr(sfh, "sfa", type("M", (), {"audit": staticmethod(_fake_audit_red())}))
    cooldown_path = tmp_path / "cooldown.json"
    monkeypatch.setattr(sfh, "COOLDOWN_PATH", cooldown_path)
    monkeypatch.setattr(sfh, "LOG_PATH", tmp_path / "log.jsonl")

    def fake_starter(task_name, dry_run=False):
        assert dry_run is True
        return {"started": False, "dry_run": True}

    sfh.run(now=NOW, dry_run=True, starter=fake_starter)
    # dry-run must never persist cooldown state
    assert not cooldown_path.exists()


def test_run_fails_open_when_audit_raises(monkeypatch):
    def _raise():
        raise RuntimeError("boom")
    monkeypatch.setattr(sfh, "sfa", type("M", (), {"audit": staticmethod(_raise)}))

    out = sfh.run(now=NOW, starter=lambda *a, **k: {"started": True})
    assert out["verdict"] == "UNKNOWN"
    assert out["actions"] == []


def test_run_logs_real_actions(monkeypatch, tmp_path):
    monkeypatch.setattr(sfh, "sfa", type("M", (), {"audit": staticmethod(_fake_audit_red())}))
    monkeypatch.setattr(sfh, "COOLDOWN_PATH", tmp_path / "cooldown.json")
    log_path = tmp_path / "log.jsonl"
    monkeypatch.setattr(sfh, "LOG_PATH", log_path)

    sfh.run(now=NOW, starter=lambda *a, **k: {"started": True, "returncode": 0})

    assert log_path.exists()
    row = json.loads(log_path.read_text(encoding="utf-8").splitlines()[-1])
    assert row["n_red"] == 1


def test_real_start_task_never_raises_on_bad_binary(monkeypatch):
    """Belt-and-braces: even the REAL start_task (not the test double) must fail open
    if the subprocess call itself blows up (e.g. powershell missing on a non-Windows
    CI runner)."""
    def _boom(*a, **k):
        raise FileNotFoundError("no powershell here")
    monkeypatch.setattr(sfh.subprocess, "run", _boom)
    result = sfh.start_task("Gamma_TradeToday")
    assert result["started"] is False
    assert "error" in result
