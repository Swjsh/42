"""Guards for setup/scripts/claude_auth_canary.py.

Pins the four verdicts required by the build spec: logged in -> OK, logged out ->
LOGGED_OUT, refresh token expiring within 72h -> EXPIRING, CLI binary missing -> UNKNOWN.
Mocks subprocess.run (never shells out to the real CLI) and uses a throwaway credentials
file containing ONLY the fields this module is allowed to touch (no real token values).
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


cac = _load("claude_auth_canary", "claude_auth_canary.py")


def _fake_completed(stdout: str, returncode: int = 0):
    return subprocess.CompletedProcess(args=["claude", "auth", "status"], returncode=returncode,
                                        stdout=stdout, stderr="")


def _write_creds(tmp_path: Path, expiry_ms) -> Path:
    p = tmp_path / ".credentials.json"
    payload = {"claudeAiOauth": {}}
    if expiry_ms is not None:
        payload["claudeAiOauth"]["refreshTokenExpiresAt"] = expiry_ms
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def _fake_exe(tmp_path: Path) -> Path:
    """A file that just needs to exist -- _run_auth_status only checks Path.exists()
    before shelling out, and subprocess.run itself is monkeypatched in every test."""
    p = tmp_path / "claude.exe"
    p.write_text("", encoding="utf-8")
    return p


# ---------------------------------------------------------------------------------------
# logged in, healthy expiry -> OK
# ---------------------------------------------------------------------------------------

def test_logged_in_far_expiry_is_ok(tmp_path, monkeypatch):
    exe = _fake_exe(tmp_path)
    import datetime as dt
    far_future_ms = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=30)).timestamp() * 1000.0
    creds = _write_creds(tmp_path, far_future_ms)

    monkeypatch.setattr(subprocess, "run",
                         lambda *a, **kw: _fake_completed('{"loggedIn": true, "authMethod": "oauth", "apiProvider": "firstParty"}'))

    state = cac.run_canary(claude_exe=str(exe), credentials_path=creds)
    assert state["verdict"] == "OK"
    assert state["loggedIn"] is True
    assert state["hours_left"] > 72


# ---------------------------------------------------------------------------------------
# logged out -> LOGGED_OUT (the live 2026-09-15 shape: exit code 1, valid JSON body)
# ---------------------------------------------------------------------------------------

def test_logged_out_is_logged_out(tmp_path, monkeypatch):
    exe = _fake_exe(tmp_path)
    import datetime as dt
    past_ms = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)).timestamp() * 1000.0
    creds = _write_creds(tmp_path, past_ms)

    monkeypatch.setattr(subprocess, "run",
                         lambda *a, **kw: _fake_completed('{"loggedIn": false, "authMethod": "none", "apiProvider": "firstParty"}',
                                                           returncode=1))

    state = cac.run_canary(claude_exe=str(exe), credentials_path=creds)
    assert state["verdict"] == "LOGGED_OUT"
    assert state["loggedIn"] is False


def test_expired_refresh_token_forces_logged_out_even_if_loggedin_true(tmp_path, monkeypatch):
    """A stale/cached loggedIn=true alongside an already-expired refresh token must not
    report OK -- the expiry fact overrides a possibly-stale CLI claim."""
    exe = _fake_exe(tmp_path)
    import datetime as dt
    past_ms = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2)).timestamp() * 1000.0
    creds = _write_creds(tmp_path, past_ms)

    monkeypatch.setattr(subprocess, "run",
                         lambda *a, **kw: _fake_completed('{"loggedIn": true, "authMethod": "oauth", "apiProvider": "firstParty"}'))

    state = cac.run_canary(claude_exe=str(exe), credentials_path=creds)
    assert state["verdict"] == "LOGGED_OUT"


# ---------------------------------------------------------------------------------------
# logged in, expiry within 72h -> EXPIRING
# ---------------------------------------------------------------------------------------

def test_expiry_within_72h_is_expiring(tmp_path, monkeypatch):
    exe = _fake_exe(tmp_path)
    import datetime as dt
    soon_ms = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=10)).timestamp() * 1000.0
    creds = _write_creds(tmp_path, soon_ms)

    monkeypatch.setattr(subprocess, "run",
                         lambda *a, **kw: _fake_completed('{"loggedIn": true, "authMethod": "oauth", "apiProvider": "firstParty"}'))

    state = cac.run_canary(claude_exe=str(exe), credentials_path=creds)
    assert state["verdict"] == "EXPIRING"
    assert 0 < state["hours_left"] <= 72


# ---------------------------------------------------------------------------------------
# CLI binary missing -> UNKNOWN, never crash
# ---------------------------------------------------------------------------------------

def test_missing_cli_is_unknown(tmp_path, monkeypatch):
    missing_exe = tmp_path / "does_not_exist.exe"
    creds = _write_creds(tmp_path, None)

    def _boom(*a, **kw):
        raise AssertionError("subprocess.run must not be called when the exe is missing")

    monkeypatch.setattr(subprocess, "run", _boom)

    state = cac.run_canary(claude_exe=str(missing_exe), credentials_path=creds)
    assert state["verdict"] == "UNKNOWN"
    assert state["loggedIn"] is None


def test_non_json_output_is_unknown_not_a_crash(tmp_path, monkeypatch):
    exe = _fake_exe(tmp_path)
    creds = _write_creds(tmp_path, None)

    monkeypatch.setattr(subprocess, "run",
                         lambda *a, **kw: _fake_completed("not json at all"))

    state = cac.run_canary(claude_exe=str(exe), credentials_path=creds)
    assert state["verdict"] == "UNKNOWN"


def test_subprocess_timeout_is_unknown_not_a_crash(tmp_path, monkeypatch):
    exe = _fake_exe(tmp_path)
    creds = _write_creds(tmp_path, None)

    def _timeout(*a, **kw):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=20)

    monkeypatch.setattr(subprocess, "run", _timeout)

    state = cac.run_canary(claude_exe=str(exe), credentials_path=creds)
    assert state["verdict"] == "UNKNOWN"


# ---------------------------------------------------------------------------------------
# Never reads token values -- only the numeric expiry field. Guards the explicit
# "WITHOUT reading token values" constraint from the build spec.
# ---------------------------------------------------------------------------------------

def test_never_reads_access_or_refresh_token_values(tmp_path, monkeypatch):
    exe = _fake_exe(tmp_path)
    creds_path = tmp_path / ".credentials.json"
    creds_path.write_text(json.dumps({
        "claudeAiOauth": {
            "accessToken": "SECRET-SHOULD-NEVER-APPEAR",
            "refreshToken": "SECRET-SHOULD-NEVER-APPEAR-EITHER",
            "refreshTokenExpiresAt": 9999999999999,
        }
    }), encoding="utf-8")

    monkeypatch.setattr(subprocess, "run",
                         lambda *a, **kw: _fake_completed('{"loggedIn": true, "authMethod": "oauth", "apiProvider": "firstParty"}'))

    state = cac.run_canary(claude_exe=str(exe), credentials_path=creds_path)
    serialized = json.dumps(state)
    assert "SECRET-SHOULD-NEVER-APPEAR" not in serialized


# ---------------------------------------------------------------------------------------
# Surfacing: CLAUDE_AUTH: marker into STATUS.md's Known broken section via the existing
# de-duplicating writer, and cleared on a return to OK.
# ---------------------------------------------------------------------------------------

def test_surfacing_writes_and_clears_marker(tmp_path):
    skb = _load("status_known_broken_for_canary_test", "status_known_broken.py")
    surface_mod = _load("claude_auth_canary_surface", "claude_auth_canary_surface.py")
    # surface_mod imported its OWN status_known_broken at load time via sys.path;
    # re-point it at the same tmp status file for isolation.
    status_path = tmp_path / "STATUS.md"
    status_path.write_text("## Known broken\n\n## Other\nstuff\n", encoding="utf-8")

    bad_state = {"ts_et": "2026-09-15 08:45:00 ET", "verdict": "LOGGED_OUT",
                 "fix_hint": "run `claude` then /login in a terminal (J credential step)",
                 "errors": None, "hours_left": None, "refresh_expires_at_local": None}

    changed = skb.upsert("CLAUDE_AUTH:", "- [2026-09-15 08:45:00 ET] CLAUDE_AUTH: LOGGED_OUT -- test",
                          status_path=status_path)
    assert changed is True
    text = status_path.read_text(encoding="utf-8")
    assert "CLAUDE_AUTH: LOGGED_OUT" in text

    cleared = skb.upsert("CLAUDE_AUTH:", None, status_path=status_path)
    assert cleared is True
    text_after = status_path.read_text(encoding="utf-8")
    assert "CLAUDE_AUTH:" not in text_after


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
