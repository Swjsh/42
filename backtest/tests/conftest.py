"""Test-suite bootstrap.

Puts this directory on `sys.path` so test modules can import shared fixture helpers
(`_broker_request_stub`) at module import time -- before each file's own
`sys.path.insert(...)` block runs, which is too late for a top-level `from ... import`.

Deliberately minimal: no fixtures, no autouse hooks, no collection tweaks. Every test file
here loads production modules by explicit path and manages its own sys.path for those; this
file changes none of that, so adding it cannot alter which module version any test imports.
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)


# ---------------------------------------------------------------------------------------
# quiet_mode LIVE-LOG ISOLATION (added 2026-09-03 00:50 ET, structural fix for a live incident)
#
# quiet_mode._log() appends to automation/state/quiet-mode.log on disk. Five test files
# imported quiet_mode without redirecting LOG_FILE, so every full-suite run planted fixture
# lines ("QUIET HELD past the clock ... r5apex_dx12.exe", weekday "PRESENCE -> research
# band" lines the real code cannot produce, "scheduler unreachable") into the PRODUCTION
# log. scheduled_task_staleness.parse_quiet_holds then read a phantom OPEN hold, closed it
# at `now`, and quiet_mode's catch-up sweep restarted the same five tasks every 5 minutes
# for an hour (2026-09-02 23:47 -> 2026-09-03 00:43 ET; McpDailyAudit 12x/hour). Fixing it
# per file is how it recurred; this autouse fixture redirects LOG_FILE (and the hold/status
# files beside it) for EVERY test as soon as quiet_mode is imported, regardless of file.
# ---------------------------------------------------------------------------------------
import pytest as _pytest


@_pytest.fixture(autouse=True)
def _quiet_mode_never_touches_live_state(monkeypatch, tmp_path):
    qm = sys.modules.get("quiet_mode")
    if qm is None:
        yield
        return
    for attr in ("LOG_FILE", "HOLD_FILE", "STATUS_FILE", "RESTORE_FILE"):
        if hasattr(qm, attr):
            monkeypatch.setattr(qm, attr, tmp_path / f"quiet-mode-{attr.lower()}")
    yield
