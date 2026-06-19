#!/usr/bin/env python
"""guard_runner.py - background graduated-guards regression runner.

Launched DETACHED (headless, no window) by the PostToolUse hook after an engine
edit. Runs the fast lessons-graduated-to-code assertion suite and writes the
verdict to automation/state/guard-watch.json. The hook itself never waits on
pytest (this box runs 9+ always-on daemons; a synchronous run would block the
user for minutes - violating the "never disturb the user" rule). Instead the
hook reads the sentinel on the NEXT edit and surfaces any failure then.

Per CLAUDE.md lesson C8 (headless Windows spawn = CREATE_NO_WINDOW) and OP-25
(silent failure is the only true failure - a regression must surface LOUD).

Pure regression guard: never edits code, never places orders.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\jackw\Desktop\42")
STATE = ROOT / "automation" / "state"
WATCH = STATE / "guard-watch.json"
LOCK = STATE / ".guard-watch.lock"
BT = ROOT / "backtest"
CREATE_NO_WINDOW = 0x08000000


def _now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def main() -> int:
    edited = sys.argv[1] if len(sys.argv) > 1 else "(unknown)"
    started = _now()
    try:
        # Per-edit run = FAST logic guards only (`-m "not slow"`). The slow,
        # data-heavy guards (each runs a full backtest) collectively exceed this
        # 600s budget and would time out / false-block unrelated edits. They run
        # nightly / on demand via:  python -m pytest tests/test_graduated_guards.py -m slow
        proc = subprocess.run(
            [sys.executable.replace("pythonw", "python"), "-m", "pytest",
             "tests/test_graduated_guards.py", "-m", "not slow", "-q", "--no-header"],
            cwd=str(BT), capture_output=True, text=True, timeout=600,
            creationflags=CREATE_NO_WINDOW,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        last = out.strip().splitlines()[-1] if out.strip() else "(no pytest output)"
        status = "pass" if proc.returncode == 0 else "fail"
        summary = last
    except subprocess.TimeoutExpired:
        status, summary, out = "timeout", "graduated-guards exceeded 600s", ""
    except Exception as exc:  # never crash the runner silently
        status, summary, out = "error", f"runner exception: {exc}", ""

    payload = {
        "skill": "guard-runner",
        "status": status,
        "edited_file": edited,
        "summary": summary,
        "started_at": started,
        "finished_at": _now(),
        "surfaced": False,
        "tail": out.strip().splitlines()[-15:] if out.strip() else [],
    }
    WATCH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    try:
        LOCK.unlink()
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
