"""Restart-on-stale-code policy for the Kitchen daemon keepalive.

GOAL-RIG-HYGIENE-2026-09-05 H1. The existing keepalive
(run-kitchen-daemon-keepalive.ps1) already restarts a DEAD process (pid file points at
nothing alive) and a WEDGED one (kitchen-status.json hasn't moved in 25+ minutes). Neither
branch catches the case this file exists for: the daemon is alive, healthy, and CURRENTLY
IDLE, but it was started before the last edit to the code it imports -- so a shipped fix
sits un-deployed until the daemon happens to die or wedge on its own, which can be hours.

Restarting a BUSY daemon (kitchen-status.json idle=false) would kill an in-flight grinder
job mid-run -- explicitly forbidden by this goal's OPERATING RULES and by L27/L41 (headless
Windows spawn discipline: don't tear down a live worker to chase a code change). So the rule
is narrow: restart ONLY when idle AND stale-code, never otherwise.

`decide_restart` is a pure function over (idle, daemon_start_utc, script_mtimes_utc) so it
can be RED-proofed without touching any live file. `gather_and_decide` is the thin I/O
wrapper the keepalive script actually calls (via Invoke-PythonHidden -> this file's CLI).
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STATUS_FILE = REPO / "automation" / "state" / "kitchen-status.json"
PID_FILE = REPO / "automation" / "state" / "kitchen-daemon.pid"

# The scripts the daemon imports/execs on its hot path. Keep in sync with
# GOAL-RIG-HYGIENE-2026-09-05 H1 spec -- if the daemon starts importing another module on
# its critical path, add it here (and to the guard test's WATCHED_SCRIPTS mirror).
WATCHED_SCRIPTS = [
    REPO / "setup" / "scripts" / "kitchen_daemon.py",
    REPO / "setup" / "scripts" / "kitchen_stage1_runner.py",
    REPO / "setup" / "scripts" / "kitchen_reviewer.py",
    REPO / "setup" / "scripts" / "chef_nemotron.py",
]


def decide_restart(
    idle: bool,
    daemon_start_utc: dt.datetime,
    script_mtimes_utc: list[dt.datetime],
) -> tuple[bool, str]:
    """Pure decision function -- no filesystem or clock access. Returns (should_restart, reason)."""
    if not idle:
        return False, "daemon busy (idle=false) -- never restart mid-job"
    if not script_mtimes_utc:
        return False, "no watched scripts found on disk -- nothing to compare, refusing to restart blind"
    newest = max(script_mtimes_utc)
    if daemon_start_utc < newest:
        return True, (
            f"idle=true and daemon started {daemon_start_utc.isoformat()} predates newest "
            f"watched-script mtime {newest.isoformat()} -- shipped code not yet live"
        )
    return False, (
        f"idle=true but daemon started {daemon_start_utc.isoformat()} is current "
        f"(newest watched mtime {newest.isoformat()})"
    )


def _as_utc(value: dt.datetime) -> dt.datetime:
    return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)


def gather_and_decide(
    status_file: Path = STATUS_FILE,
    pid_file: Path = PID_FILE,
    watched_scripts: list[Path] | None = None,
) -> tuple[bool, str]:
    """I/O wrapper: read live status/pid/mtimes and apply decide_restart."""
    watched_scripts = watched_scripts if watched_scripts is not None else WATCHED_SCRIPTS
    if not status_file.exists():
        return False, f"status file missing: {status_file}"
    if not pid_file.exists():
        return False, f"pid file missing: {pid_file}"
    try:
        status = json.loads(status_file.read_text(encoding="utf-8"))
        pid_data = json.loads(pid_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return False, f"could not read status/pid json: {exc}"

    idle = bool(status.get("idle", False))
    started_raw = pid_data.get("started_at_utc")
    if not started_raw:
        return False, "pid file has no started_at_utc -- refusing to restart blind"
    started = _as_utc(dt.datetime.fromisoformat(started_raw))

    mtimes = [
        _as_utc(dt.datetime.fromtimestamp(p.stat().st_mtime, tz=dt.timezone.utc))
        for p in watched_scripts
        if p.exists()
    ]
    return decide_restart(idle, started, mtimes)


def main() -> int:
    should_restart, reason = gather_and_decide()
    print(json.dumps({"restart": should_restart, "reason": reason}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
