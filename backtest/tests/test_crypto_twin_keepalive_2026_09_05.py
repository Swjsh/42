"""Guard: crypto_twin_keepalive.py's PURE relaunch-decision logic -- GOAL-SILENT-RIG-2026-09-05 R2.

Drives should_relaunch()/find_loop_pid()/is_loop_process_line() with FAKE wmic-shaped text --
zero real subprocess calls, zero real launches. Mirrors quote_recorder_keepalive.py's own
pid-cross-check discipline: a fake process list stands in for the live process table.

RED-PROOFED (2026-09-05): confirmed each test fails against a deliberately broken
should_relaunch/find_loop_pid before the real implementation shipped -- see PROGRESS LOG in
automation/state/goals/GOAL-SILENT-RIG-2026-09-05.md for the quoted proof.
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "setup" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import crypto_twin_keepalive as ctk  # noqa: E402


def _wmic_record(pid: int, cmdline: str) -> str:
    """One wmic '/FORMAT:LIST' record, blank-line-terminated -- matches the real tool's shape."""
    return f"CommandLine={cmdline}\nProcessId={pid}\n\n"


LOOP_CMDLINE = (
    r'"C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe" '
    r'"C:\Users\jackw\Desktop\42\setup\scripts\crypto_twin_health.py" --live --loop '
    r'--duration-sec 86400'
)
ONESHOT_CMDLINE = (
    r'"C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe" '
    r'"C:\Users\jackw\Desktop\42\setup\scripts\crypto_twin_health.py" --live'
)
UNRELATED_CMDLINE = r'"C:\Windows\System32\svchost.exe" -k netsvcs'
KEEPALIVE_SELF_CMDLINE = (
    r'"C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe" '
    r'"C:\Users\jackw\Desktop\42\setup\scripts\crypto_twin_keepalive.py"'
)


def test_is_loop_process_line_requires_both_markers():
    assert ctk.is_loop_process_line(LOOP_CMDLINE) is True
    assert ctk.is_loop_process_line(ONESHOT_CMDLINE) is False  # no --loop
    assert ctk.is_loop_process_line(UNRELATED_CMDLINE) is False


def test_is_loop_process_line_never_matches_the_keepalive_itself():
    """The false-positive class quote_recorder_keepalive.py's docstring calls out: a bare
    substring match on the script's own name would make the keepalive think ITSELF is the
    thing it's supposed to be keeping alive."""
    assert ctk.is_loop_process_line(KEEPALIVE_SELF_CMDLINE) is False


def test_find_loop_pid_locates_the_right_record_among_many():
    text = (
        _wmic_record(111, UNRELATED_CMDLINE)
        + _wmic_record(222, ONESHOT_CMDLINE)
        + _wmic_record(333, LOOP_CMDLINE)
        + _wmic_record(444, KEEPALIVE_SELF_CMDLINE)
    )
    assert ctk.find_loop_pid(text) == 333


def test_find_loop_pid_none_when_absent():
    text = _wmic_record(111, UNRELATED_CMDLINE) + _wmic_record(222, ONESHOT_CMDLINE)
    assert ctk.find_loop_pid(text) is None


def test_find_loop_pid_handles_empty_text():
    assert ctk.find_loop_pid("") is None


def test_find_loop_pid_handles_trailing_record_with_no_blank_line():
    """wmic's LAST record in the whole dump sometimes has no trailing blank line -- the
    parser must still catch it (mirrors quote_recorder_keepalive.py's own end-of-loop
    fallback check)."""
    text = _wmic_record(111, UNRELATED_CMDLINE) + f"CommandLine={LOOP_CMDLINE}\nProcessId=999"
    assert ctk.find_loop_pid(text) == 999


def test_should_relaunch_false_when_loop_alive():
    text = _wmic_record(333, LOOP_CMDLINE)
    relaunch, pid = ctk.should_relaunch(text)
    assert relaunch is False
    assert pid == 333


def test_should_relaunch_true_when_only_old_oneshot_task_seen():
    """The OLD Gamma_CryptoTwin 1-min task's per-minute --live (no --loop) fires must NOT be
    mistaken for the new resident loop being alive -- otherwise the keepalive would never
    actually launch the loop while the old task is still transitionally enabled."""
    text = _wmic_record(222, ONESHOT_CMDLINE)
    relaunch, pid = ctk.should_relaunch(text)
    assert relaunch is True
    assert pid is None


def test_should_relaunch_true_when_process_table_empty():
    relaunch, pid = ctk.should_relaunch("")
    assert relaunch is True
    assert pid is None


def test_should_relaunch_true_when_nothing_matches():
    text = _wmic_record(111, UNRELATED_CMDLINE) + _wmic_record(444, KEEPALIVE_SELF_CMDLINE)
    relaunch, pid = ctk.should_relaunch(text)
    assert relaunch is True
    assert pid is None


def test_pid_file_round_trip(tmp_path):
    pid_file = tmp_path / "crypto-twin-loop.pid"
    ctk._write_pid_file(4242, pid_file)
    assert ctk._read_pid_file(pid_file) == 4242


def test_pid_file_missing_reads_none(tmp_path):
    assert ctk._read_pid_file(tmp_path / "nope.pid") is None


def test_pid_file_malformed_reads_none(tmp_path):
    p = tmp_path / "bad.pid"
    p.write_text("not json", encoding="utf-8")
    assert ctk._read_pid_file(p) is None


def test_main_relaunches_when_process_table_read_fails(monkeypatch):
    """A wmic read failure must fail TOWARD availability (attempt a launch) rather than
    silently leaving the twin dead -- C7."""
    monkeypatch.setattr(ctk, "_live_process_lines", lambda: (_ for _ in ()).throw(RuntimeError("wmic boom")))
    launched = {"called": False}
    monkeypatch.setattr(ctk, "launch_loop", lambda: (launched.__setitem__("called", True), (True, 1234))[1])
    rc = ctk.main()
    assert rc == 0
    assert launched["called"] is True


def test_main_does_not_relaunch_when_loop_already_alive(monkeypatch):
    monkeypatch.setattr(ctk, "_live_process_lines", lambda: _wmic_record(333, LOOP_CMDLINE))
    launched = {"called": False}
    monkeypatch.setattr(ctk, "launch_loop", lambda: (launched.__setitem__("called", True), (True, 1234))[1])
    rc = ctk.main()
    assert rc == 0
    assert launched["called"] is False


def test_launch_loop_command_includes_live_and_loop_flags(monkeypatch, tmp_path):
    """The launched command must carry --live (the old task's own flag -- never silently
    downgrade to watch-only) AND --loop (the whole point of R2)."""
    captured = {}

    class _FakeProc:
        pid = 9999

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        return _FakeProc()

    monkeypatch.setattr(ctk.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(ctk.time, "sleep", lambda s: None)
    monkeypatch.setattr(ctk, "PID_FILE", tmp_path / "crypto-twin-loop.pid")
    ok, pid = ctk.launch_loop()
    assert ok is True
    assert pid == 9999
    cmd = captured["cmd"]
    assert "--live" in cmd
    assert "--loop" in cmd
    assert str(ctk.SYS_PYTHONW) == cmd[0]
    assert str(ctk.TWIN_HEALTH_SCRIPT) == cmd[1]
