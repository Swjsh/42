#!/usr/bin/env python
"""guard_runner_slow.py - NIGHTLY data-heavy graduated-guards runner.

Companion to setup/guard_runner.py. The per-edit PostToolUse hook runs only the
FAST logic guards (`-m "not slow"`, ~2s) so an engine edit is never blocked. The
SLOW guards (`-m slow`) each load the 16-month master SPY/VIX CSV and run one or
more full backtests (20-60s each, ~35 of them) - far over the 600s per-edit
budget. Excluding them from the hook is correct, but they must still run SOMEWHERE
or the regression coverage is silently dropped. This script is that "somewhere":
a once-nightly, $0, pure-Python gate fired by the Gamma_GuardsNightly scheduled
task (after-hours, never during 09:30-15:55 ET market hours - L54 heartbeat).

Behaviour:
  * Runs `pytest -m slow` over the graduated-guards file with a generous timeout.
  * ALWAYS writes the verdict to automation/state/guard-watch-slow.json (a SEPARATE
    sentinel from the per-edit guard-watch.json - it must never clobber a pending
    per-edit failure signal).
  * On a transition INTO broken (prior run was pass/absent, this run is not pass)
    appends ONE loud, timestamped line to STATUS.md "## Known broken" (OP-25:
    silent failure is the only true failure). A persisting failure is NOT re-spammed
    every night; a recovery flips the sentinel back to pass.

Per CLAUDE.md OP-25 (fail loud) + OP-26 (regression surface) + lesson C8 (headless
Windows spawn = CREATE_NO_WINDOW). Pure regression guard: never edits engine code,
never places orders.

Manual run (foreground, shows output):
    cd backtest && python -m pytest tests/test_graduated_guards.py -m slow -q
"""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\jackw\Desktop\42")
STATE = ROOT / "automation" / "state"
WATCH_SLOW = STATE / "guard-watch-slow.json"
STATUS = ROOT / "automation" / "overnight" / "STATUS.md"
BT = ROOT / "backtest"
CREATE_NO_WINDOW = 0x08000000
# 35 data-heavy guards x up to ~60s each, with headroom. The scheduled task's own
# ExecutionTimeLimit is set wider than this so pytest's timeout fires first (clean
# verdict) rather than Task Scheduler killing the process (no verdict written).
TIMEOUT_S = 3000


def _now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _prior_status() -> str | None:
    """Status of the previous nightly run, or None if no sentinel yet."""
    try:
        return json.loads(WATCH_SLOW.read_text(encoding="utf-8")).get("status")
    except (OSError, ValueError):
        return None


def _flag_status_md(status: str, summary: str) -> None:
    """Append ONE loud line under '## Known broken' on a transition into broken."""
    try:
        text = STATUS.read_text(encoding="utf-8")
    except OSError:
        return
    marker = "## Known broken"
    if marker not in text:
        return
    line = (
        f"- [{_now()}] GRADUATED-GUARDS-SLOW {status.upper()} :: {summary} :: "
        "re-run: cd backtest && python -m pytest tests/test_graduated_guards.py -m slow -q"
    )
    # Insert newest-first, immediately after the section header.
    head, _, tail = text.partition(marker + "\n")
    STATUS.write_text(f"{head}{marker}\n\n{line}\n{tail.lstrip(chr(10))}", encoding="utf-8")


def main() -> int:
    started = _now()
    prior = _prior_status()
    try:
        proc = subprocess.run(
            [sys.executable.replace("pythonw", "python"), "-m", "pytest",
             "tests/test_graduated_guards.py", "-m", "slow", "-q", "--no-header"],
            cwd=str(BT), capture_output=True, text=True, timeout=TIMEOUT_S,
            creationflags=CREATE_NO_WINDOW,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        last = out.strip().splitlines()[-1] if out.strip() else "(no pytest output)"
        if proc.returncode == 0:
            status = "pass"
        elif proc.returncode == 5:
            status = "notests"  # marker matched nothing -> wiring problem, surface it
        else:
            status = "fail"
        summary = last
    except subprocess.TimeoutExpired:
        status, summary, out = "timeout", f"slow graduated-guards exceeded {TIMEOUT_S}s", ""
    except Exception as exc:  # never crash the runner silently
        status, summary, out = "error", f"runner exception: {exc}", ""

    payload = {
        "skill": "guard-runner-slow",
        "status": status,
        "summary": summary,
        "started_at": started,
        "finished_at": _now(),
        "tail": out.strip().splitlines()[-20:] if out.strip() else [],
    }
    WATCH_SLOW.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # Loud on transition INTO broken; don't re-spam a persisting failure.
    if status != "pass" and prior in ("pass", None):
        _flag_status_md(status, summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
