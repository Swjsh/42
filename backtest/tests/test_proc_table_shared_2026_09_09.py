"""Guard: the shared `_proc_table` module (setup/scripts/_proc_table.py) must return a
REAL, non-empty process table, and no non-test/non-vendored file under setup/scripts/ may
still shell out to `wmic`.

2026-09-09 incident. Windows 11 24H2+ REMOVED `wmic.exe` from the OS. Every keepalive /
watchdog module that shelled out to `wmic` for a liveness check got WinError 2 on every
call and silently read "not running" for everything -- the supervisor alone relaunched all
9 always-on daemons every 5 minutes (126 discord-bridge starts in one day; 6 concurrent
bridges spamming J's Discord). `_proc_table.py` is the ONE shared, importable replacement
(PowerShell CIM, CREATE_NO_WINDOW) every sibling module was ported to use -- these tests
make an empty/wmic-dependent table a RED test instead of a nightly spam storm (C7: audit
outputs, not exit codes).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO / "setup" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import _proc_table as pt  # noqa: E402

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows process table")


def test_process_table_read_is_not_empty():
    """The live read must actually return processes. Empty == the wmic-removal bug."""
    table = pt.parse_process_table(pt.process_table_text())
    assert len(table) > 20, (
        f"process table returned {len(table)} pids -- an empty/tiny table makes every "
        "daemon read as dead and every keepalive relaunch it every fire"
    )


def test_process_table_contains_this_process():
    """Strongest possible check: the running interpreter MUST appear in its own snapshot."""
    table = pt.parse_process_table(pt.process_table_text())
    assert os.getpid() in table, (
        "the current process is missing from _proc_table's own process table -- "
        "liveness checks built on this table cannot be trusted"
    )


def test_process_cmdline_returns_a_populated_python_string():
    """process_cmdline() for this own live pid must return a non-empty string naming the
    interpreter -- the single-pid lookup path every sibling keepalive/watchdog now uses."""
    cmdline = pt.process_cmdline(os.getpid())
    assert cmdline, "process_cmdline(os.getpid()) returned empty/None for a live process"
    assert "python" in cmdline.lower(), f"cmdline does not look like a python process: {cmdline!r}"


def test_process_cmdline_returns_none_for_a_dead_pid():
    """A pid that matches no live process at all must return None, not raise or misread."""
    assert pt.process_cmdline(999999) is None


def test_no_wmic_dependency_remains_anywhere_in_setup_scripts():
    """wmic no longer exists on Windows 11 24H2+; no non-test, non-vendored .py file under
    setup/scripts/ may invoke it (comments/docstrings mentioning wmic historically are fine
    -- only an actual invocation, e.g. `["wmic", ...]` or a bare `wmic ` command token, is
    disallowed)."""
    offenders: list[str] = []
    for path in SCRIPTS_DIR.rglob("*.py"):
        rel = path.relative_to(SCRIPTS_DIR).as_posix()
        if ".tts-venv" in rel:
            continue  # vendored third-party -- out of scope
        if rel.startswith("__pycache__") or "__pycache__" in rel:
            continue
        try:
            src = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for i, line in enumerate(src.splitlines(), start=1):
            code = line.split("#", 1)[0]
            if '"wmic"' in code or "'wmic'" in code:
                offenders.append(f"{rel}:{i}: {line.strip()}")
    assert not offenders, "wmic invocation(s) remain under setup/scripts/:\n" + "\n".join(offenders)
