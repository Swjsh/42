"""Guard: supervisor_keepalive.py -- ONE-process merge of 9 keepalive tasks
(GOAL-SILENT-RIG-2026-09-05 R7).

Every test drives PURE logic (parse_process_table, run_once over an INJECTED registry/
table, and the individual _check_*/_spawn_* functions with monkeypatched subprocess.Popen)
-- zero real wmic/subprocess calls, zero real process launches, zero real HTTP requests.

RED-PROOFED (2026-09-05): before shipping, `run_once` had NO try/except around
`spec.check`/`spec.spawn` -- a single daemon raising inside check() propagated out of
run_once and skipped every daemon after it in registry order. Reverted the try/except
locally, re-ran `test_run_once_one_daemon_raising_does_not_block_the_rest` ->
`RuntimeError: boom` uncaught, test FAILED as expected; restored the guard, re-ran -> PASS.
Same proof-of-need applies to the CREATE_NO_WINDOW assertions below: an earlier draft of
_spawn_kitchen_daemon omitted `creationflags=_DETACHED_PROCESS | _CREATE_NO_WINDOW`
entirely -- `test_spawn_kitchen_daemon_uses_system_pythonw_and_create_no_window` failed on
that draft (missing kwarg -> KeyError) before the flags were added.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "setup" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import supervisor_keepalive as sk  # noqa: E402


# ── parse_process_table ──────────────────────────────────────────────────────

def _wmic_record(pid: int, cmdline: str) -> str:
    return f"CommandLine={cmdline}\nProcessId={pid}\n\n"


def test_parse_process_table_basic():
    text = _wmic_record(111, "svchost.exe -k netsvcs") + _wmic_record(222, "python.exe foo.py")
    table = sk.parse_process_table(text)
    assert table == {111: "svchost.exe -k netsvcs", 222: "python.exe foo.py"}


def test_parse_process_table_empty():
    assert sk.parse_process_table("") == {}


def test_parse_process_table_trailing_record_no_blank_line():
    """wmic's LAST record in a whole dump sometimes has no trailing blank line."""
    text = _wmic_record(111, "a.exe") + "CommandLine=b.exe\nProcessId=222"
    table = sk.parse_process_table(text)
    assert table == {111: "a.exe", 222: "b.exe"}


def test_parse_process_table_skips_unparseable_pid():
    text = "CommandLine=weird.exe\nProcessId=notanumber\n\n" + _wmic_record(333, "ok.exe")
    table = sk.parse_process_table(text)
    assert table == {333: "ok.exe"}


# ── run_once over an injected registry (no real daemons, no real subprocess) ────────────

def _spec(name, alive: bool, spawn_ok: bool = True, spawn_pid: int = 9999,
          check_raises: Exception | None = None, spawn_raises: Exception | None = None):
    calls = {"check": 0, "spawn": 0}

    def check(table):
        calls["check"] += 1
        if check_raises:
            raise check_raises
        return alive, f"{name} alive={alive}", (1 if alive else None)

    def spawn():
        calls["spawn"] += 1
        if spawn_raises:
            raise spawn_raises
        return spawn_ok, (spawn_pid if spawn_ok else None), f"{name} spawn ok={spawn_ok}"

    return sk.DaemonSpec(name, check, spawn), calls


def test_run_once_alive_daemon_never_calls_spawn():
    spec, calls = _spec("alive-one", alive=True)
    outcomes = sk.run_once(registry=[spec], table={})
    assert calls["check"] == 1
    assert calls["spawn"] == 0
    assert outcomes[0].action == "alive"
    assert outcomes[0].alive is True


def test_run_once_dead_daemon_calls_spawn_and_reports_relaunched():
    spec, calls = _spec("dead-one", alive=False, spawn_ok=True, spawn_pid=4242)
    outcomes = sk.run_once(registry=[spec], table={})
    assert calls["spawn"] == 1
    assert outcomes[0].action == "relaunched"
    assert outcomes[0].pid == 4242


def test_run_once_spawn_failure_is_reported_not_raised():
    spec, calls = _spec("bad-spawn", alive=False, spawn_ok=False)
    outcomes = sk.run_once(registry=[spec], table={})
    assert outcomes[0].action == "spawn_failed"
    assert outcomes[0].pid is None


def test_run_once_one_daemon_raising_does_not_block_the_rest():
    """The whole point of the merge: one bad daemon must never hide the other 9's status."""
    bad_spec, bad_calls = _spec("bad", alive=False, check_raises=RuntimeError("boom"))
    good_spec, good_calls = _spec("good", alive=True)
    outcomes = sk.run_once(registry=[bad_spec, good_spec], table={})
    assert len(outcomes) == 2
    assert outcomes[0].name == "bad"
    assert outcomes[0].action in ("spawn_failed", "relaunched")  # treated as dead -> attempted spawn
    assert outcomes[1].name == "good"
    assert outcomes[1].action == "alive"
    assert good_calls["check"] == 1  # the second daemon still ran


def test_run_once_spawn_raising_is_caught_and_reported():
    spec, calls = _spec("spawn-raises", alive=False, spawn_raises=RuntimeError("spawn boom"))
    outcomes = sk.run_once(registry=[spec], table={})
    assert outcomes[0].action == "spawn_failed"
    assert "spawn boom" in outcomes[0].detail


def test_run_once_process_table_read_failure_falls_back_to_empty_table(monkeypatch):
    """A wmic hiccup on the ONE shared read must not crash the whole run -- every daemon
    just reads as dead against an empty table (fail toward availability)."""
    def boom():
        raise RuntimeError("wmic boom")
    monkeypatch.setattr(sk, "live_process_table_text", boom)
    spec, calls = _spec("x", alive=False, spawn_ok=True)
    outcomes = sk.run_once(registry=[spec])  # table=None -> triggers the real read path
    assert calls["check"] == 1
    assert outcomes[0].action == "relaunched"


# ── sibling-module reuse: check() functions read the SHARED table, never a fresh subprocess ──

def test_check_crypto_twin_reuses_sibling_predicate_against_shared_table():
    import crypto_twin_keepalive as ctk
    table = {333: (r'"pythonw.exe" "crypto_twin_health.py" --live --loop --duration-sec 86400')}
    alive, detail, pid = sk._check_crypto_twin(table)
    assert alive is True
    assert pid == 333


def test_check_crypto_twin_dead_when_only_oneshot_seen():
    table = {222: r'"pythonw.exe" "crypto_twin_health.py" --live'}
    alive, detail, pid = sk._check_crypto_twin(table)
    assert alive is False


def test_check_proc_trace_reuses_sibling_predicate():
    table = {555: r'"pythonw.exe" "proc_trace.py"'}
    alive, detail, pid = sk._check_proc_trace(table)
    assert alive is True
    assert pid == 555


def test_check_proc_trace_excludes_its_own_keepalive():
    table = {555: r'"pythonw.exe" "proc_trace_keepalive.py"'}
    alive, detail, pid = sk._check_proc_trace(table)
    assert alive is False


def test_check_window_leak_hook_alive(tmp_path, monkeypatch):
    import window_leak_hook_keepalive as whk
    pid_file = tmp_path / "window-leak-hook.pid"
    pid_file.write_text("777", encoding="utf-8")
    monkeypatch.setattr(whk, "PID_FILE", pid_file)
    table = {777: r'"pythonw.exe" "window_leak_hook.py"'}
    alive, detail, pid = sk._check_window_leak_hook(table)
    assert alive is True
    assert pid == 777


def test_check_window_leak_hook_dead_when_pid_gone(tmp_path, monkeypatch):
    import window_leak_hook_keepalive as whk
    pid_file = tmp_path / "window-leak-hook.pid"
    pid_file.write_text("777", encoding="utf-8")
    monkeypatch.setattr(whk, "PID_FILE", pid_file)
    alive, detail, pid = sk._check_window_leak_hook({})  # 777 not in table
    assert alive is False


def test_check_window_leak_detector_recycles_when_over_age(tmp_path, monkeypatch):
    import window_leak_detector_keepalive as wld
    pid_file = tmp_path / "window-leak-detector.pid"
    pid_file.write_text("888", encoding="utf-8")
    monkeypatch.setattr(wld, "PID_FILE", pid_file)
    monkeypatch.setattr(wld, "_detector_runtime_s", lambda live_pid=None: wld.MAX_DETECTOR_AGE_S + 1)
    table = {888: "python.exe window-leak-detector.py"}
    alive, detail, pid = sk._check_window_leak_detector(table)
    assert alive is False
    assert "WEDGE-RECYCLE" in detail


def test_check_quote_recorder_alive(tmp_path, monkeypatch):
    import quote_recorder_keepalive as qrk
    status_file = tmp_path / "quote-recorder-status.json"
    status_file.write_text(json.dumps({"pid": 999}), encoding="utf-8")
    monkeypatch.setattr(qrk, "STATUS_FILE", status_file)
    table = {999: "pythonw.exe quote_recorder.py --loop"}
    alive, detail, pid = sk._check_quote_recorder(table)
    assert alive is True
    assert pid == 999


# ── ported (no sibling module) checks: kitchen / discord / companion / dashboard ─────────

def test_check_kitchen_daemon_alive_and_fresh(tmp_path, monkeypatch):
    pid_file = tmp_path / "kitchen-daemon.pid"
    status_file = tmp_path / "kitchen-status.json"
    pid_file.write_text(json.dumps({"pid": 1010}), encoding="utf-8")
    status_file.write_text(json.dumps({"idle": False}), encoding="utf-8")
    monkeypatch.setattr(sk, "KITCHEN_PID_FILE", pid_file)
    monkeypatch.setattr(sk, "KITCHEN_STATUS_FILE", status_file)
    table = {1010: "pythonw.exe kitchen_daemon.py run"}
    alive, detail, pid = sk._check_kitchen_daemon(table)
    assert alive is True
    assert pid == 1010


def test_check_kitchen_daemon_dead_when_pid_not_in_table(tmp_path, monkeypatch):
    pid_file = tmp_path / "kitchen-daemon.pid"
    pid_file.write_text(json.dumps({"pid": 1010}), encoding="utf-8")
    monkeypatch.setattr(sk, "KITCHEN_PID_FILE", pid_file)
    monkeypatch.setattr(sk, "KITCHEN_STATUS_FILE", tmp_path / "nope.json")
    alive, detail, pid = sk._check_kitchen_daemon({})
    assert alive is False


def test_check_kitchen_daemon_wedge_when_status_stale(tmp_path, monkeypatch):
    import os
    import time as _time
    pid_file = tmp_path / "kitchen-daemon.pid"
    status_file = tmp_path / "kitchen-status.json"
    pid_file.write_text(json.dumps({"pid": 1010}), encoding="utf-8")
    status_file.write_text(json.dumps({"idle": False}), encoding="utf-8")
    old = _time.time() - 30 * 60  # 30 min ago > 25 min wedge threshold
    os.utime(status_file, (old, old))
    monkeypatch.setattr(sk, "KITCHEN_PID_FILE", pid_file)
    monkeypatch.setattr(sk, "KITCHEN_STATUS_FILE", status_file)
    table = {1010: "pythonw.exe kitchen_daemon.py run"}
    alive, detail, pid = sk._check_kitchen_daemon(table)
    assert alive is False
    assert "WEDGED" in detail


def test_check_kitchen_daemon_idle_stale_code_recycles(tmp_path, monkeypatch):
    pid_file = tmp_path / "kitchen-daemon.pid"
    status_file = tmp_path / "kitchen-status.json"
    pid_file.write_text(json.dumps({"pid": 1010}), encoding="utf-8")
    status_file.write_text(json.dumps({"idle": True}), encoding="utf-8")
    monkeypatch.setattr(sk, "KITCHEN_PID_FILE", pid_file)
    monkeypatch.setattr(sk, "KITCHEN_STATUS_FILE", status_file)
    monkeypatch.setattr(sk.kdp, "gather_and_decide",
                         lambda status_file, pid_file: (True, "idle+stale-code (fake)"))
    table = {1010: "pythonw.exe kitchen_daemon.py run"}
    alive, detail, pid = sk._check_kitchen_daemon(table)
    assert alive is False
    assert "idle+stale-code" in detail


def test_spawn_kitchen_daemon_uses_system_pythonw_and_create_no_window(tmp_path, monkeypatch):
    monkeypatch.setattr(sk, "KITCHEN_PID_FILE", tmp_path / "no-pid.json")

    class _FakeProc:
        pid = 5555

    captured = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return _FakeProc()

    monkeypatch.setattr(sk.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(sk.time, "sleep", lambda s: None)

    ok, pid, detail = sk._spawn_kitchen_daemon()
    assert ok is True
    assert pid == 5555
    assert captured["cmd"][0] == str(sk.SYS_PYTHONW)
    assert "kitchen_daemon.py" in captured["cmd"][1]
    assert captured["kwargs"]["creationflags"] & sk._CREATE_NO_WINDOW


def test_check_discord_bridge_alive_when_pid_in_table(tmp_path, monkeypatch):
    pid_file = tmp_path / "discord-bridge.pid"
    pid_file.write_text("2020|2026-09-05T00:00:00", encoding="utf-8")
    monkeypatch.setattr(sk, "DISCORD_BRIDGE_PID", pid_file)
    table = {2020: "pythonw.exe discord-bridge.py"}
    alive, detail, pid = sk._check_discord_bridge(table)
    assert alive is True
    assert pid == 2020


def test_check_discord_bridge_dead_when_pid_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(sk, "DISCORD_BRIDGE_PID", tmp_path / "nope.pid")
    alive, detail, pid = sk._check_discord_bridge({})
    assert alive is False


def test_spawn_discord_bridge_uses_system_pythonw_and_create_no_window(tmp_path, monkeypatch):
    pid_file = tmp_path / "discord-bridge.pid"
    monkeypatch.setattr(sk, "DISCORD_BRIDGE_PID", pid_file)

    class _FakeProc:
        pid = 6060

    captured = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        # simulate the real script writing its own pid file on successful start
        pid_file.write_text("6060|2026-09-05T00:00:00", encoding="utf-8")
        return _FakeProc()

    monkeypatch.setattr(sk.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(sk.time, "sleep", lambda s: None)

    ok, pid, detail = sk._spawn_discord_bridge()
    assert ok is True
    assert captured["cmd"][0] == str(sk.SYS_PYTHONW)
    assert "discord-bridge.py" in captured["cmd"][1]
    assert captured["kwargs"]["creationflags"] & sk._CREATE_NO_WINDOW


def test_spawn_discord_bridge_failure_reported_when_pid_file_never_appears(tmp_path, monkeypatch):
    pid_file = tmp_path / "discord-bridge.pid"
    monkeypatch.setattr(sk, "DISCORD_BRIDGE_PID", pid_file)

    class _FakeProc:
        pid = 7070

    monkeypatch.setattr(sk.subprocess, "Popen", lambda cmd, **kw: _FakeProc())
    monkeypatch.setattr(sk.time, "sleep", lambda s: None)

    ok, pid, detail = sk._spawn_discord_bridge()
    assert ok is False  # process started but never wrote its own pid file -> not proven alive


# ── companion / dashboard: HTTP-probe + port-conflict guard, no real sockets ────────────

def test_check_companion_alive_on_http_200(monkeypatch):
    monkeypatch.setattr(sk, "_http_probe", lambda url, ok_codes: True)
    alive, detail, pid = sk._check_companion({})
    assert alive is True


def test_check_companion_port_conflict_never_spawns(monkeypatch):
    monkeypatch.setattr(sk, "_http_probe", lambda url, ok_codes: False)
    monkeypatch.setattr(sk, "_port_bound", lambda port: True)
    alive, detail, pid = sk._check_companion({})
    assert alive is False
    assert "port conflict" in detail


def test_spawn_companion_uses_node_create_no_window(monkeypatch, tmp_path):
    fake_script = tmp_path / "server.js"
    fake_script.write_text("", encoding="utf-8")
    monkeypatch.setattr(sk, "COMPANION_SCRIPT", fake_script)
    monkeypatch.setattr(sk, "_resolve_node", lambda: r"C:\Program Files\nodejs\node.exe")

    captured = {}

    class _FakeProc:
        pid = 8080

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return _FakeProc()

    monkeypatch.setattr(sk.subprocess, "Popen", fake_popen)
    ok, pid, detail = sk._spawn_companion()
    assert ok is True
    assert pid == 8080
    assert captured["kwargs"]["creationflags"] & sk._CREATE_NO_WINDOW


def test_check_dashboard_alive_on_http_2xx(monkeypatch):
    monkeypatch.setattr(sk, "_http_probe", lambda url, ok_codes: True)
    alive, detail, pid = sk._check_dashboard({})
    assert alive is True


def test_spawn_dashboard_requires_next_build(monkeypatch, tmp_path):
    monkeypatch.setattr(sk, "DASHBOARD_DIR", tmp_path)  # no .next under here
    monkeypatch.setattr(sk, "_resolve_node", lambda: r"C:\Program Files\nodejs\node.exe")
    ok, pid, detail = sk._spawn_dashboard()
    assert ok is False
    assert ".next" in detail


# ── registry sanity floor -- guards against an accidental empty/short registry ──────────

def test_registry_has_all_nine_daemons():
    names = {spec.name for spec in sk.REGISTRY}
    assert names == {
        "companion", "dashboard", "kitchen_daemon", "discord_bridge", "discord_watcher",
        "quote_recorder", "crypto_twin", "window_leak_detector", "window_leak_hook",
        "proc_trace",
    }
