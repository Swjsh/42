"""Guard: the supervisor's process-table read must return a REAL, non-empty table.

2026-09-09 incident. `live_process_table_text()` shelled out to `wmic`, which Windows 11
24H2+ REMOVED from the OS. The call raised WinError 2, the supervisor caught it and
proceeded "with empty table", and an empty table makes EVERY daemon's `pid in table` check
read as dead. The supervisor then relaunched all 9 daemons every 5 minutes: 126 discord
bridge starts in one day, 6 live bridges at once (each re-sending every outbox row) and 6
watchers racing on `.discord-watcher-state.json.tmp`, every race queueing an @J error
alert. That is what spammed J's Discord.

The failure was SILENT in the only way that mattered -- the supervisor logged "relaunching"
forever and nothing ever asserted the table was real. These tests make the empty table a
RED test instead of a nightly spam storm (C7: audit outputs, not exit codes).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import supervisor_keepalive as sk  # noqa: E402

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows process table")


def test_process_table_read_is_not_empty():
    """The live read must actually return processes. Empty == the wmic-removal bug."""
    table = sk.parse_process_table(sk.live_process_table_text())
    assert len(table) > 20, (
        f"process table returned {len(table)} pids -- an empty/tiny table makes every "
        "daemon read as dead and the supervisor relaunch all of them every 5 minutes"
    )


def test_process_table_contains_this_process():
    """Strongest possible check: the running interpreter MUST appear in its own snapshot."""
    table = sk.parse_process_table(sk.live_process_table_text())
    assert os.getpid() in table, (
        "the current process is missing from the supervisor's own process table -- "
        "liveness checks built on this table cannot be trusted"
    )


def test_no_wmic_dependency_remains():
    """wmic no longer exists on Windows 11 24H2+; nothing here may depend on it again."""
    src = (REPO / "setup" / "scripts" / "supervisor_keepalive.py").read_text(encoding="utf-8")
    offenders = [
        ln for ln in src.splitlines()
        if '"wmic"' in ln or "'wmic'" in ln or "wmic " in ln.split("#")[0]
    ]
    assert not offenders, f"supervisor still invokes wmic: {offenders}"


def test_cmdline_values_survive_the_round_trip():
    """Command lines must come back intact -- a mangled table silently breaks every check."""
    table = sk.parse_process_table(sk.live_process_table_text())
    populated = [c for c in table.values() if c.strip()]
    assert len(populated) > 10, "process table returned pids but essentially no command lines"
    assert any(".exe" in c.lower() for c in populated), "no command line looks like a real exe"
