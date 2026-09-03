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
    monkeypatch.setattr(sfh, "PENDING_PATH", tmp_path / "pending.json")
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
    monkeypatch.setattr(sfh, "PENDING_PATH", tmp_path / "pending.json")
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
    monkeypatch.setattr(sfh, "PENDING_PATH", tmp_path / "pending.json")
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
    monkeypatch.setattr(sfh, "PENDING_PATH", tmp_path / "pending.json")
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
    monkeypatch.setattr(sfh, "PENDING_PATH", tmp_path / "pending.json")
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
    monkeypatch.setattr(sfh, "PENDING_PATH", tmp_path / "pending.json")
    log_path = tmp_path / "log.jsonl"
    monkeypatch.setattr(sfh, "LOG_PATH", log_path)

    sfh.run(now=NOW, starter=lambda *a, **k: {"started": True, "returncode": 0})

    assert log_path.exists()
    row = json.loads(log_path.read_text(encoding="utf-8").splitlines()[-1])
    assert row["n_red"] == 1


# ---------------------------------------------------------------------------
# SELFHEAL-VERIFY-EFFECT-AUDIT (2026-09-03): effect verification
# ---------------------------------------------------------------------------
# Before this fix, start_task's `ok = proc.returncode == 0` was the ONLY success signal --
# the same C7 shape as the pre-c941567c Invoke-TvLaunchSafe blind spot: "Start-ScheduledTask
# returned 0" was reported as success even when the mapped producer never actually wrote a
# fresh file. Since Start-ScheduledTask returns almost immediately (long before the real
# producer finishes), the effect can't be judged synchronously -- these tests prove the
# deferred re-audit-on-next-pass verification both ways: healed (path left RED on the next
# run() call) -> effect_verified=True; still RED past the grace window -> effect_verified=False.

def _fake_audit_status(path_status: dict, task_field="Gamma_TradeToday (every 2 min)"):
    """Build a fake sfa.audit() reporting the given {path: status} map."""
    def _audit():
        return {
            "verdict": "RED" if any(v == "RED" for v in path_status.values()) else "GREEN",
            "checked_at_et": "2026-07-31 01:00:00",
            "entries": [
                {"path": p, "status": s, "task": task_field,
                 "reasons": [f"{p} STALE" if s == "RED" else ""]}
                for p, s in path_status.items()
            ],
        }
    return _audit


def test_effect_verified_true_when_target_left_red_on_next_pass(monkeypatch, tmp_path):
    """A self-heal started on pass 1; by pass 2 (a few minutes later, well within the grace
    window) the target path is GREEN -- the force-start actually worked. Must be reported
    effect_verified=True and the path must drop out of the pending set (no false alarm on
    pass 3)."""
    path = "automation/state/trade-today.json"
    monkeypatch.setattr(sfh, "COOLDOWN_PATH", tmp_path / "cooldown.json")
    monkeypatch.setattr(sfh, "PENDING_PATH", tmp_path / "pending.json")
    monkeypatch.setattr(sfh, "LOG_PATH", tmp_path / "log.jsonl")

    # Pass 1: RED, force-start attempted and "succeeds" (returncode 0).
    monkeypatch.setattr(sfh, "sfa", type(
        "M", (), {"audit": staticmethod(_fake_audit_status({path: "RED"}))}))
    out1 = sfh.run(now=NOW, starter=lambda t, dry_run=False: {"started": True, "returncode": 0})
    assert out1["actions"][0]["outcome"] == "start_attempted"
    assert sfh.PENDING_PATH.exists(), "a successful start must register a pending verification"

    # Pass 2 (3 min later, well within EFFECT_VERIFY_GRACE_MIN): the producer actually ran
    # and the path is now GREEN.
    from datetime import timedelta
    monkeypatch.setattr(sfh, "sfa", type(
        "M", (), {"audit": staticmethod(_fake_audit_status({path: "GREEN"}))}))
    out2 = sfh.run(now=NOW + timedelta(minutes=3),
                    starter=lambda t, dry_run=False: {"started": True, "returncode": 0})
    assert out2["verify_results"] == [
        {"path": path, "task": "Gamma_TradeToday", "effect_verified": True, "age_min": 3.0}
    ]

    # Pass 3: the pending entry must have been cleared -- no repeated verify result for it.
    out3 = sfh.run(now=NOW + timedelta(minutes=6),
                    starter=lambda t, dry_run=False: {"started": True, "returncode": 0})
    assert out3["verify_results"] == []


def test_effect_verified_false_when_target_still_red_past_grace(monkeypatch, tmp_path):
    """The C7 case this audit item exists to catch: Start-ScheduledTask returned 0 (no
    exception) but the mapped producer's target path is STILL RED after
    EFFECT_VERIFY_GRACE_MIN minutes -- the self-heal ran but did not heal. Must be
    reported effect_verified=False, loudly, not silently dropped."""
    path = "automation/state/trade-today.json"
    monkeypatch.setattr(sfh, "COOLDOWN_PATH", tmp_path / "cooldown.json")
    monkeypatch.setattr(sfh, "PENDING_PATH", tmp_path / "pending.json")
    monkeypatch.setattr(sfh, "LOG_PATH", tmp_path / "log.jsonl")
    monkeypatch.setattr(sfh, "sfa", type(
        "M", (), {"audit": staticmethod(_fake_audit_status({path: "RED"}))}))

    sfh.run(now=NOW, starter=lambda t, dry_run=False: {"started": True, "returncode": 0})

    from datetime import timedelta
    # 15 min later (> the 10-min default grace) the path is STILL RED -- Start-ScheduledTask
    # "succeeded" but the producer never actually refreshed the file.
    out = sfh.run(now=NOW + timedelta(minutes=15),
                   starter=lambda t, dry_run=False: {"started": True, "returncode": 0},
                   cooldown_min=0)  # cooldown=0 so this call's OWN start doesn't mask the assertion
    unresolved = [v for v in out["verify_results"] if v["path"] == path]
    assert unresolved == [
        {"path": path, "task": "Gamma_TradeToday", "effect_verified": False,
         "age_min": 15.0, "reason": "still_red_after_grace"}
    ]


def test_effect_verified_kept_pending_within_grace_window(monkeypatch, tmp_path):
    """A path still RED only 4 minutes after a force-start (< the 10-min grace) must NOT be
    reported as failed yet -- it must stay in the pending set for a later pass, since the
    producer plausibly just hasn't finished running."""
    path = "automation/state/trade-today.json"
    monkeypatch.setattr(sfh, "COOLDOWN_PATH", tmp_path / "cooldown.json")
    monkeypatch.setattr(sfh, "PENDING_PATH", tmp_path / "pending.json")
    monkeypatch.setattr(sfh, "LOG_PATH", tmp_path / "log.jsonl")
    monkeypatch.setattr(sfh, "sfa", type(
        "M", (), {"audit": staticmethod(_fake_audit_status({path: "RED"}))}))

    sfh.run(now=NOW, starter=lambda t, dry_run=False: {"started": True, "returncode": 0})

    from datetime import timedelta
    out = sfh.run(now=NOW + timedelta(minutes=4),
                   starter=lambda t, dry_run=False: {"started": True, "returncode": 0},
                   cooldown_min=999)  # long cooldown so pass 2 doesn't re-attempt/re-register
    assert out["verify_results"] == [], (
        "still within the grace window -- must not yet be judged a failure")
    pending = json.loads(sfh.PENDING_PATH.read_text(encoding="utf-8"))
    assert path in pending, "must still be tracked for a later verification pass"


def test_effect_verification_never_touches_cooldown_or_dry_run_path(monkeypatch, tmp_path):
    """--dry-run must never persist a pending-verification entry (mirrors the existing
    dry-run/cooldown contract) -- a dry-run preview must have zero side effects."""
    path = "automation/state/trade-today.json"
    pending_path = tmp_path / "pending.json"
    monkeypatch.setattr(sfh, "COOLDOWN_PATH", tmp_path / "cooldown.json")
    monkeypatch.setattr(sfh, "PENDING_PATH", pending_path)
    monkeypatch.setattr(sfh, "LOG_PATH", tmp_path / "log.jsonl")
    monkeypatch.setattr(sfh, "sfa", type(
        "M", (), {"audit": staticmethod(_fake_audit_status({path: "RED"}))}))

    sfh.run(now=NOW, dry_run=True, starter=lambda t, dry_run=False: {"started": True, "dry_run": True})
    assert not pending_path.exists()


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
