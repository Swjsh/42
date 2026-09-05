"""Guard: proc_trace_keepalive.py's PURE relaunch-decision logic -- GOAL-SILENT-RIG-2026-09-05
R4a.

Drives should_relaunch()/find_tracer_pid()/is_tracer_process_line() with FAKE wmic-shaped
text -- zero real subprocess calls, zero real launches. Mirrors
crypto_twin_keepalive.py/quote_recorder_keepalive.py's own pid-cross-check discipline: a
fake process list stands in for the live process table.
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "setup" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import proc_trace_keepalive as ptk  # noqa: E402


def _wmic_record(pid: int, cmdline: str) -> str:
    """One wmic '/FORMAT:LIST' record, blank-line-terminated -- matches the real tool's shape."""
    return f"CommandLine={cmdline}\nProcessId={pid}\n\n"


TRACER_CMDLINE = (
    r'"C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe" '
    r'"C:\Users\jackw\Desktop\42\setup\scripts\proc_trace.py"'
)
UNRELATED_CMDLINE = r'"C:\Windows\System32\svchost.exe" -k netsvcs'
KEEPALIVE_SELF_CMDLINE = (
    r'"C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe" '
    r'"C:\Users\jackw\Desktop\42\setup\scripts\proc_trace_keepalive.py"'
)


def test_is_tracer_process_line_matches_real_tracer():
    assert ptk.is_tracer_process_line(TRACER_CMDLINE) is True
    assert ptk.is_tracer_process_line(UNRELATED_CMDLINE) is False


def test_is_tracer_process_line_never_matches_the_keepalive_itself():
    """The false-positive class crypto_twin_keepalive.py's own docstring calls out: a bare
    substring match on 'proc_trace' would make the keepalive mistake ITSELF
    (proc_trace_keepalive.py, which contains 'proc_trace') for the tracer being alive."""
    assert ptk.is_tracer_process_line(KEEPALIVE_SELF_CMDLINE) is False


def test_find_tracer_pid_locates_the_right_record_among_many():
    text = (
        _wmic_record(111, UNRELATED_CMDLINE)
        + _wmic_record(222, KEEPALIVE_SELF_CMDLINE)
        + _wmic_record(333, TRACER_CMDLINE)
    )
    assert ptk.find_tracer_pid(text) == 333


def test_find_tracer_pid_none_when_absent():
    text = _wmic_record(111, UNRELATED_CMDLINE) + _wmic_record(222, KEEPALIVE_SELF_CMDLINE)
    assert ptk.find_tracer_pid(text) is None


def test_find_tracer_pid_handles_trailing_record_without_blank_line():
    """wmic's LIST output sometimes doesn't end with a trailing blank line -- the final
    record must still be parsed."""
    text = f"CommandLine={TRACER_CMDLINE}\nProcessId=444"
    assert ptk.find_tracer_pid(text) == 444


def test_should_relaunch_bite_true_when_no_tracer_alive():
    """NON-VACUOUS BITE: an empty/unrelated process table -> must relaunch."""
    text = _wmic_record(111, UNRELATED_CMDLINE)
    relaunch, pid = ptk.should_relaunch(text)
    assert relaunch is True
    assert pid is None


def test_should_relaunch_bite_false_when_tracer_alive():
    """NON-VACUOUS BITE: a live tracer record -> must NOT relaunch, and must report its pid."""
    text = _wmic_record(111, UNRELATED_CMDLINE) + _wmic_record(555, TRACER_CMDLINE)
    relaunch, pid = ptk.should_relaunch(text)
    assert relaunch is False
    assert pid == 555


def test_should_relaunch_ignores_the_keepalive_itself():
    """A process table with ONLY the keepalive running (no tracer) must still say relaunch --
    proves the keepalive doesn't accidentally treat its own liveness as the tracer's."""
    text = _wmic_record(222, KEEPALIVE_SELF_CMDLINE)
    relaunch, pid = ptk.should_relaunch(text)
    assert relaunch is True
    assert pid is None


def test_should_relaunch_empty_table_relaunches():
    relaunch, pid = ptk.should_relaunch("")
    assert relaunch is True
    assert pid is None


def test_launch_tracer_fails_open_when_sys_pythonw_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(ptk, "SYS_PYTHONW", tmp_path / "does-not-exist-pythonw.exe")
    monkeypatch.setattr(ptk, "LOG_FILE", tmp_path / "test.log")
    ok, pid = ptk.launch_tracer()
    assert ok is False
    assert pid is None


def test_launch_tracer_fails_open_when_script_missing(monkeypatch, tmp_path):
    fake_pythonw = tmp_path / "fake_pythonw.exe"
    fake_pythonw.write_bytes(b"")
    monkeypatch.setattr(ptk, "SYS_PYTHONW", fake_pythonw)
    monkeypatch.setattr(ptk, "PROC_TRACE_SCRIPT", tmp_path / "does-not-exist.py")
    monkeypatch.setattr(ptk, "LOG_FILE", tmp_path / "test.log")
    ok, pid = ptk.launch_tracer()
    assert ok is False
    assert pid is None


def test_main_attempts_launch_when_wmic_read_fails(monkeypatch, tmp_path):
    """A wmic read failure must fail toward AVAILABILITY (attempt a launch) rather than
    silently leaving the tracer dead forever -- same discipline as crypto_twin_keepalive."""
    monkeypatch.setattr(ptk, "LOG_FILE", tmp_path / "test.log")

    def _raise():
        raise RuntimeError("wmic unavailable")

    launch_calls = []

    def _fake_launch():
        launch_calls.append(True)
        return True, 999

    monkeypatch.setattr(ptk, "_live_process_lines", _raise)
    monkeypatch.setattr(ptk, "launch_tracer", _fake_launch)
    rc = ptk.main()
    assert rc == 0
    assert launch_calls == [True]


def test_main_safe_never_raises_even_on_total_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(ptk, "LOG_FILE", tmp_path / "test.log")

    def _explode():
        raise RuntimeError("boom")

    monkeypatch.setattr(ptk, "main", _explode)
    assert ptk._main_safe() == 0
