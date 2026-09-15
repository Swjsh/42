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
    downgrade to watch-only) AND --loop (the whole point of R2).

    ISOLATION (load-bearing, root-caused 2026-09-13 -- same class of bug
    test_twin_chaos_drill.py's module docstring documents for ledger_path): this test calls
    the REAL ctk.launch_loop(), which calls _write_pid_file(proc.pid) with no explicit path.
    _write_pid_file/_read_pid_file used to default `pid_file: Path = PID_FILE` -- a value
    bound ONCE at module-import time -- so monkeypatching `ctk.PID_FILE` below did NOT
    redirect that write; it landed on the REAL automation/state/crypto-twin-loop.pid,
    overwriting the live loop's actual pid (2024) with this test's fake one (9999) every time
    this test ran, most recently caught at 10:33:41 ET on 2026-09-13. Fixed at the source
    (_write_pid_file/_read_pid_file now resolve PID_FILE fresh inside the function body), but
    this test ALSO asserts the real path is untouched so a future regression in that fix is
    caught right here, not just by the session-wide conftest guard.

    SECOND ISOLATION LEAK (found 2026-09-15, TWIN-LOOP-SINGLETON-GUARD audit): launch_loop()
    also calls `_log(...)`, which reads the module-level `LOG_FILE` global -- unlike PID_FILE
    at the time of the above incident, `_log` already re-reads its global fresh on every call
    rather than binding it as a default argument, so `monkeypatch.setattr(ctk, "LOG_FILE",
    ...)` DOES correctly redirect it (no source change needed here, only this test gained the
    missing monkeypatch). Before this fix, every run of this test wrote a literal
    '[...] launched crypto_twin_health.py --live --loop PID=9999 duration=86400s (24h
    recycle)' line into the REAL automation/state/logs/crypto-twin-keepalive-<date>.log --
    confirmed present in crypto-twin-keepalive-2026-09-09.log ('PID=9999') sitting next to a
    genuine 'loop alive (pid=333)' line from production, i.e. test pollution of a real log a
    human/Fable might read as production evidence."""
    captured = {}

    class _FakeProc:
        pid = 9999

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        return _FakeProc()

    real_pid_file = ctk.PID_FILE
    real_pid_file_before = (real_pid_file.read_bytes() if real_pid_file.exists() else None)
    fake_pid_file = tmp_path / "crypto-twin-loop.pid"
    real_log_file = ctk.LOG_FILE
    real_log_file_before = (real_log_file.read_bytes() if real_log_file.exists() else None)
    fake_log_file = tmp_path / "crypto-twin-keepalive-test.log"

    monkeypatch.setattr(ctk.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(ctk.time, "sleep", lambda s: None)
    monkeypatch.setattr(ctk, "PID_FILE", fake_pid_file)
    monkeypatch.setattr(ctk, "LOG_FILE", fake_log_file)
    ok, pid = ctk.launch_loop()
    assert ok is True
    assert pid == 9999
    cmd = captured["cmd"]
    assert "--live" in cmd
    assert "--loop" in cmd
    assert str(ctk.SYS_PYTHONW) == cmd[0]
    assert str(ctk.TWIN_HEALTH_SCRIPT) == cmd[1]

    # The write must have landed on the monkeypatched tmp_path file, and the REAL production
    # pid file must be byte-identical to before this test ran (or still absent, if it never
    # existed) -- the regression this test exists to catch.
    assert fake_pid_file.exists(), "launch_loop() must write via the (monkeypatched) PID_FILE"
    real_pid_file_after = (real_pid_file.read_bytes() if real_pid_file.exists() else None)
    assert real_pid_file_after == real_pid_file_before, (
        "launch_loop()/_write_pid_file() wrote to the REAL production pid file despite "
        "monkeypatching ctk.PID_FILE -- the 2026-09-13 bound-default regression is back"
    )
    assert fake_log_file.exists(), "launch_loop() must log via the (monkeypatched) LOG_FILE"
    assert "PID=9999" in fake_log_file.read_text(encoding="utf-8")
    real_log_file_after = (real_log_file.read_bytes() if real_log_file.exists() else None)
    assert real_log_file_after == real_log_file_before, (
        "launch_loop()/_log() wrote a fake PID=9999 line into the REAL production keepalive "
        "log despite monkeypatching ctk.LOG_FILE -- the 2026-09-15 test-pollution regression "
        "(confirmed in crypto-twin-keepalive-2026-09-09.log) is back"
    )