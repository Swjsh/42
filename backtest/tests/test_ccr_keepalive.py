"""Guard: ccr_keepalive.py -- the claude-code-router (CCR) gateway keepalive.

CCR died overnight 07-08->07-09 with no auto-restart; every LLM scheduled fire
failed ConnectionRefused until a manual restart the next day. This locks in:
probe-up skips restart; probe-down attempts restart then re-probes; the J-ping
fires only at the consecutive-failure threshold and only ONCE per episode
(de-dupe, reset on recovery); the whole thing fails open on any exception; and
every subprocess spawn carries creationflags=CREATE_NO_WINDOW (OP-27 L41 --
this repo REDs on bare-console spawns).
"""
from __future__ import annotations

import importlib.util
import json
import re
import socket
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_SCRIPT = REPO / "setup" / "scripts" / "ccr_keepalive.py"


def _load():
    for p in (REPO / "setup" / "scripts",):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    spec = importlib.util.spec_from_file_location("ccr_keepalive", _SCRIPT)
    m = importlib.util.module_from_spec(spec)
    sys.modules["ccr_keepalive"] = m
    spec.loader.exec_module(m)  # type: ignore
    return m


def _fake_popen_recorder(captured):
    def _fake(cmd, **kw):
        captured["cmd"] = cmd
        captured["kw"] = kw
        return type("FakeProc", (), {"pid": 12345})()
    return _fake


# ---- _probe_ccr -- real sockets, no mocking (non-vacuous) ----------------------------

def test_probe_ccr_true_when_port_open():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    try:
        m = _load()
        assert m._probe_ccr(host="127.0.0.1", port=port, timeout=1.0) is True
    finally:
        srv.close()


def test_probe_ccr_false_when_port_closed():
    # Bind to get a genuinely free ephemeral port, then close it before probing --
    # nothing is listening there, so the connect must be refused.
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    port = srv.getsockname()[1]
    srv.close()
    m = _load()
    assert m._probe_ccr(host="127.0.0.1", port=port, timeout=1.0) is False


# ---- main() orchestration -------------------------------------------------------------

def test_up_path_writes_state_and_skips_restart(tmp_path, monkeypatch):
    m = _load()
    monkeypatch.setattr(m, "STATE_FILE", tmp_path / "ccr-keepalive.json")
    monkeypatch.setattr(m, "LOG_DIR", tmp_path)
    monkeypatch.setattr(m, "_probe_ccr", lambda *a, **k: True)

    def _boom(*a, **k):
        raise AssertionError("restart must NOT be invoked when the probe is already up")
    monkeypatch.setattr(m.subprocess, "Popen", _boom)

    assert m.main() == 0
    state = json.loads((tmp_path / "ccr-keepalive.json").read_text(encoding="utf-8"))
    assert state["port_up"] is True
    assert state["consecutive_failures"] == 0
    assert state["ping_sent_this_episode"] is False
    assert state["ts_et"]  # non-empty


def test_down_path_attempts_restart_then_recovers(tmp_path, monkeypatch):
    m = _load()
    monkeypatch.setattr(m, "STATE_FILE", tmp_path / "ccr-keepalive.json")
    monkeypatch.setattr(m, "LOG_DIR", tmp_path)
    monkeypatch.setattr(m, "OUTBOX", tmp_path / "discord-outbox.jsonl")

    probe_calls = {"n": 0}
    def _probe(*a, **k):
        probe_calls["n"] += 1
        return probe_calls["n"] >= 2  # first probe down, post-restart re-probe up
    monkeypatch.setattr(m, "_probe_ccr", _probe)

    captured = {}
    monkeypatch.setattr(m.subprocess, "Popen", _fake_popen_recorder(captured))
    monkeypatch.setattr(m.time, "sleep", lambda s: None)

    assert m.main() == 0
    assert probe_calls["n"] == 2, "must re-probe after the restart attempt"
    assert captured, "restart must be attempted when the initial probe is down"
    assert captured["kw"]["creationflags"] & m._CREATE_NO_WINDOW

    state = json.loads((tmp_path / "ccr-keepalive.json").read_text(encoding="utf-8"))
    assert state["port_up"] is True
    assert state["consecutive_failures"] == 0
    assert state["last_restart_et"]
    assert not (tmp_path / "discord-outbox.jsonl").exists(), "recovered on first try -- no ping"


def test_down_path_restart_fails_increments_consecutive_failures(tmp_path, monkeypatch):
    m = _load()
    state_file = tmp_path / "ccr-keepalive.json"
    state_file.write_text(json.dumps({
        "ts_et": "2026-07-09 12:00:00", "port_up": False, "consecutive_failures": 1,
        "last_restart_et": "2026-07-09 11:55:00", "ping_sent_this_episode": False,
    }), encoding="utf-8")
    monkeypatch.setattr(m, "STATE_FILE", state_file)
    monkeypatch.setattr(m, "LOG_DIR", tmp_path)
    monkeypatch.setattr(m, "OUTBOX", tmp_path / "discord-outbox.jsonl")
    monkeypatch.setattr(m, "_probe_ccr", lambda *a, **k: False)  # always down
    monkeypatch.setattr(m.subprocess, "Popen", _fake_popen_recorder({}))
    monkeypatch.setattr(m.time, "sleep", lambda s: None)

    assert m.main() == 0
    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["port_up"] is False
    assert state["consecutive_failures"] == 2  # incremented from 1
    assert state["ping_sent_this_episode"] is False  # still below threshold(3)
    assert not (tmp_path / "discord-outbox.jsonl").exists()


def test_ping_fires_at_threshold_and_dedupes_within_episode(tmp_path, monkeypatch):
    """Non-vacuous bite: calls main() twice. Fire 1 crosses the >=3 threshold and
    pings once; fire 2 stays down but must NOT add a second outbox line."""
    m = _load()
    state_file = tmp_path / "ccr-keepalive.json"
    outbox = tmp_path / "discord-outbox.jsonl"
    cfg = tmp_path / ".discord-config.json"
    cfg.write_text(json.dumps({"user_id": "207983230618435584"}), encoding="utf-8")

    state_file.write_text(json.dumps({
        "ts_et": "t", "port_up": False, "consecutive_failures": 2,
        "last_restart_et": "t", "ping_sent_this_episode": False,
    }), encoding="utf-8")
    monkeypatch.setattr(m, "STATE_FILE", state_file)
    monkeypatch.setattr(m, "LOG_DIR", tmp_path)
    monkeypatch.setattr(m, "OUTBOX", outbox)
    monkeypatch.setattr(m, "DISCORD_CFG", cfg)
    monkeypatch.setattr(m, "_probe_ccr", lambda *a, **k: False)
    monkeypatch.setattr(m.subprocess, "Popen", _fake_popen_recorder({}))
    monkeypatch.setattr(m.time, "sleep", lambda s: None)

    # Fire 1: 2 -> 3 consecutive failures crosses the threshold -- exactly ONE ping.
    assert m.main() == 0
    lines = outbox.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["content"].startswith("<@207983230618435584> ")
    assert "CCR" in row["content"] and "127.0.0.1:3456" in row["content"]
    assert row["source"] == "ccr_keepalive"
    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["consecutive_failures"] == 3
    assert state["ping_sent_this_episode"] is True

    # Fire 2: still down, 3 -> 4 -- ALREADY pinged this episode -- no new line.
    assert m.main() == 0
    lines2 = outbox.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines2) == 1, "de-dupe must suppress a second ping within the same episode"
    state2 = json.loads(state_file.read_text(encoding="utf-8"))
    assert state2["consecutive_failures"] == 4
    assert state2["ping_sent_this_episode"] is True


def test_ping_resets_on_recovery_then_refires_next_episode(tmp_path, monkeypatch):
    m = _load()
    state_file = tmp_path / "ccr-keepalive.json"
    outbox = tmp_path / "discord-outbox.jsonl"
    cfg = tmp_path / ".discord-config.json"
    cfg.write_text(json.dumps({"user_id": "1"}), encoding="utf-8")

    monkeypatch.setattr(m, "STATE_FILE", state_file)
    monkeypatch.setattr(m, "LOG_DIR", tmp_path)
    monkeypatch.setattr(m, "OUTBOX", outbox)
    monkeypatch.setattr(m, "DISCORD_CFG", cfg)
    monkeypatch.setattr(m.subprocess, "Popen", _fake_popen_recorder({}))
    monkeypatch.setattr(m.time, "sleep", lambda s: None)

    # Start mid-episode: already pinged, 5 consecutive failures.
    state_file.write_text(json.dumps({
        "ts_et": "t", "port_up": False, "consecutive_failures": 5,
        "last_restart_et": "t", "ping_sent_this_episode": True,
    }), encoding="utf-8")

    # Recovery fire: probe up immediately -- resets everything, no ping (silent recovery).
    monkeypatch.setattr(m, "_probe_ccr", lambda *a, **k: True)
    assert m.main() == 0
    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["consecutive_failures"] == 0
    assert state["ping_sent_this_episode"] is False
    assert not outbox.exists()

    # New episode: pre-seed 2 failures (as if 2 more down-cycles already happened post-
    # recovery), then one more down fire crosses the threshold again -- proves the
    # de-dupe is PER-EPISODE, not a permanent latch.
    state_file.write_text(json.dumps({
        "ts_et": "t", "port_up": False, "consecutive_failures": 2,
        "last_restart_et": "t", "ping_sent_this_episode": False,
    }), encoding="utf-8")
    monkeypatch.setattr(m, "_probe_ccr", lambda *a, **k: False)
    assert m.main() == 0
    assert outbox.exists()
    lines = outbox.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1, "a fresh episode must be able to ping again"


def test_fail_open_main_propagates_but_main_safe_catches(tmp_path, monkeypatch):
    """Non-vacuous: proves main() really can raise (the guard isn't trivially a no-op)
    AND that _main_safe() -- the actual entry point -- swallows it and returns 0."""
    m = _load()
    monkeypatch.setattr(m, "STATE_FILE", tmp_path / "ccr-keepalive.json")
    monkeypatch.setattr(m, "LOG_DIR", tmp_path)

    def _boom(*a, **k):
        raise RuntimeError("simulated probe crash")
    monkeypatch.setattr(m, "_probe_ccr", _boom)

    with pytest.raises(RuntimeError):
        m.main()
    assert m._main_safe() == 0


# ---- _load_user_mention -- reused verbatim from trade_today_watcher.py ----------------

def test_load_user_mention_reads_config(tmp_path, monkeypatch):
    m = _load()
    cfg = tmp_path / ".discord-config.json"
    cfg.write_text('{"user_id": "207983230618435584"}', encoding="utf-8")
    monkeypatch.setattr(m, "DISCORD_CFG", cfg)
    assert m._load_user_mention() == "<@207983230618435584> "


def test_load_user_mention_fails_open_on_missing_config(tmp_path, monkeypatch):
    m = _load()
    monkeypatch.setattr(m, "DISCORD_CFG", tmp_path / "missing.json")
    assert m._load_user_mention() == ""


# ---- _restart_ccr -- direct node.exe primary, ccr.ps1 fallback -----------------------

def test_restart_uses_direct_node_when_present(tmp_path, monkeypatch):
    m = _load()
    fake_node = tmp_path / "node.exe"
    fake_node.write_text("", encoding="utf-8")
    fake_cli = tmp_path / "cli.js"
    fake_cli.write_text("", encoding="utf-8")
    monkeypatch.setattr(m, "NODE_EXE", fake_node)
    monkeypatch.setattr(m, "CCR_CLI", fake_cli)
    monkeypatch.setattr(m, "LOG_DIR", tmp_path)

    captured = {}
    monkeypatch.setattr(m.subprocess, "Popen", _fake_popen_recorder(captured))

    m._restart_ccr()
    assert captured["cmd"][0] == str(fake_node)
    assert str(fake_cli) in captured["cmd"]
    assert "start" in captured["cmd"]
    assert captured["kw"]["creationflags"] & m._CREATE_NO_WINDOW


def test_restart_falls_back_to_powershell_when_node_missing(tmp_path, monkeypatch):
    m = _load()
    monkeypatch.setattr(m, "NODE_EXE", tmp_path / "does-not-exist-node.exe")
    monkeypatch.setattr(m, "CCR_CLI", tmp_path / "does-not-exist-cli.js")
    monkeypatch.setattr(m, "LOG_DIR", tmp_path)

    captured = {}
    monkeypatch.setattr(m.subprocess, "Popen", _fake_popen_recorder(captured))

    m._restart_ccr()
    assert captured["cmd"][0] == "powershell.exe"
    assert "start" in captured["cmd"]
    assert str(m.CCR_PS1) in captured["cmd"]
    assert captured["kw"]["creationflags"] & m._CREATE_NO_WINDOW


# ---- OP-27 L41 window-leak discipline --------------------------------------------------

def test_create_no_window_on_every_subprocess_call():
    """Static assert on the source: every subprocess.(Popen|run|call|check_output|
    check_call)(...) call must carry creationflags= within its own argument list.
    Mirrors audit_window_leak_compliance.py's own depth-scan heuristic."""
    src = _SCRIPT.read_text(encoding="utf-8")
    calls = list(re.finditer(r"subprocess\.(Popen|run|call|check_output|check_call)\s*\(", src))
    assert calls, "expected at least one subprocess call in ccr_keepalive.py"
    for call_match in calls:
        start = call_match.start()
        tail = src[start:start + 800]
        depth = 0
        end = len(tail)
        for i, ch in enumerate(tail):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        call_text = tail[:end]
        assert "creationflags" in call_text, (
            f"subprocess call at offset {start} missing creationflags=CREATE_NO_WINDOW"
        )


def test_window_leak_audit_finds_no_violations_in_this_file():
    """Belt-and-suspenders: run the REAL repo-wide audit and confirm it doesn't flag
    ccr_keepalive.py (this file lives under setup/scripts, one of PY_AUDIT_ROOTS)."""
    audit_path = REPO / "setup" / "scripts" / "audit_window_leak_compliance.py"
    spec = importlib.util.spec_from_file_location("audit_window_leak_compliance", audit_path)
    aud = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(aud)  # type: ignore
    flags = aud._audit_py_missing_creationflags()
    offending = [f for f in flags if f["file"].replace("\\", "/").endswith("setup/scripts/ccr_keepalive.py")]
    assert offending == [], f"real audit flagged ccr_keepalive.py: {offending}"
