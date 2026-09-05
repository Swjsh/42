"""Guard (GOAL-SILENT-RIG-2026-09-05 L2): setup/scripts/presence_gate.py.

Pins the "is J at the keyboard" fan-in used by kitchen_daemon.py's grinder
spawn and the crypto grinder keepalives. Uses a fake presence-file fixture and
an injected idle-seconds value -- never touches the live
automation/state/quiet-presence.json or the real Win32 idle counter.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import presence_gate as pg  # noqa: E402


def _write_presence(tmp_path: Path, seen: dt.datetime, app: str = "r5apex_dx12.exe") -> Path:
    p = tmp_path / "quiet-presence.json"
    p.write_text(json.dumps({"last_fullscreen_at": seen.isoformat(), "app": app}), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# fullscreen signal
# ---------------------------------------------------------------------------

def test_recent_fullscreen_flags_present(tmp_path):
    now = dt.datetime(2026, 9, 5, 12, 0, 0, tzinfo=dt.timezone.utc)
    seen = now - dt.timedelta(seconds=120)  # 2 min ago, within 10-min window
    presence_file = _write_presence(tmp_path, seen)

    result = pg.check_presence(presence_file=presence_file, now=now, idle_seconds_override=999)
    assert result.present is True
    assert any("fullscreen" in r for r in result.reasons)


def test_stale_fullscreen_does_not_flag_present(tmp_path):
    now = dt.datetime(2026, 9, 5, 12, 0, 0, tzinfo=dt.timezone.utc)
    seen = now - dt.timedelta(seconds=900)  # 15 min ago, outside 10-min window
    presence_file = _write_presence(tmp_path, seen)

    result = pg.check_presence(presence_file=presence_file, now=now, idle_seconds_override=999)
    assert result.present is False


def test_missing_presence_file_fails_open_no_signal(tmp_path):
    missing = tmp_path / "does-not-exist.json"
    result = pg.check_presence(presence_file=missing, idle_seconds_override=999)
    assert result.fullscreen_age_s is None
    assert result.present is False


def test_malformed_presence_file_fails_open(tmp_path):
    p = tmp_path / "quiet-presence.json"
    p.write_text("{not valid json", encoding="utf-8")
    result = pg.check_presence(presence_file=p, idle_seconds_override=999)
    assert result.fullscreen_age_s is None
    assert result.present is False


# ---------------------------------------------------------------------------
# idle-time signal (injected, never real GetLastInputInfo)
# ---------------------------------------------------------------------------

def test_recent_input_flags_present(tmp_path):
    missing = tmp_path / "no-file.json"
    result = pg.check_presence(presence_file=missing, idle_seconds_override=10)
    assert result.present is True
    assert any("last input" in r for r in result.reasons)


def test_long_idle_does_not_flag_present(tmp_path):
    missing = tmp_path / "no-file.json"
    result = pg.check_presence(presence_file=missing, idle_seconds_override=600)
    assert result.present is False


def test_both_signals_combine_in_reasons(tmp_path):
    now = dt.datetime(2026, 9, 5, 12, 0, 0, tzinfo=dt.timezone.utc)
    seen = now - dt.timedelta(seconds=60)
    presence_file = _write_presence(tmp_path, seen)
    result = pg.check_presence(presence_file=presence_file, now=now, idle_seconds_override=5)
    assert result.present is True
    assert len(result.reasons) == 2


# ---------------------------------------------------------------------------
# should_yield() convenience wrapper
# ---------------------------------------------------------------------------

def test_should_yield_matches_check_presence(tmp_path):
    missing = tmp_path / "no-file.json"
    assert pg.should_yield(presence_file=missing, idle_seconds_override=1) is True
    assert pg.should_yield(presence_file=missing, idle_seconds_override=9999) is False


# ---------------------------------------------------------------------------
# get_idle_seconds() -- only assert it never raises and returns a sane type
# ---------------------------------------------------------------------------

def test_get_idle_seconds_never_raises():
    result = pg.get_idle_seconds()
    assert result is None or isinstance(result, float)


# ---------------------------------------------------------------------------
# main() --conductor-check (GOAL-SILENT-RIG-2026-09-05 R4b): the conductor
# launchers' rail-0 gate needs a stable exit-code contract, mirroring
# conductor_budget.py's --check (exit 3 == skip the Claude spawn). These tests
# monkeypatch pg.check_presence directly rather than touching the real
# quiet-presence.json / Win32 idle counter, so the DECISION function is what's
# under test, not the live machine's actual presence state.
# ---------------------------------------------------------------------------

def _fake_check_presence(*, present: bool, reasons=("fake",)):
    def _fn(**kwargs):
        return pg.PresenceCheck(present=present, reasons=reasons, fullscreen_age_s=None, idle_s=None)
    return _fn


def test_conductor_check_exits_3_when_present(monkeypatch, capsys):
    monkeypatch.setattr(pg, "check_presence", _fake_check_presence(present=True, reasons=("fullscreen app foreground 10s ago (<600s)",)))
    rc = pg.main(["--conductor-check"])
    assert rc == pg.EXIT_PRESENT == 3
    out = capsys.readouterr().out
    assert "PRESENT" in out


def test_conductor_check_exits_0_when_clear(monkeypatch, capsys):
    monkeypatch.setattr(pg, "check_presence", _fake_check_presence(present=False, reasons=()))
    rc = pg.main(["--conductor-check"])
    assert rc == pg.EXIT_CLEAR == 0
    out = capsys.readouterr().out
    assert "CLEAR" in out


def test_plain_main_without_conductor_check_always_exits_0(monkeypatch):
    """Without --conductor-check, main() keeps its original CLI smoke-test contract
    (always exit 0) -- this flag must be strictly additive, never change the default
    `python setup/scripts/presence_gate.py` behavior other callers may already rely on."""
    monkeypatch.setattr(pg, "check_presence", _fake_check_presence(present=True))
    assert pg.main([]) == 0
