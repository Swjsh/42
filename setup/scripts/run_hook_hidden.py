"""Hidden launcher for Claude Code hook commands (.claude/settings.local.json `command` field).

Root cause (2026-07-03, J: "cmd popups every few minutes"): hook commands were invoked
as bare `powershell -NoProfile -ExecutionPolicy Bypass -File <script>` directly by Claude
Code's hook runner, with no window-hiding at all. PreToolUse/PostToolUse fire on EVERY
tool call (interactive AND every scheduled `claude --print` task), so this was a far
higher-frequency console-flash source than any Task Scheduler action -- the surface the
2026-06-20 fix (audit_scheduled_tasks.py) never covered, since hooks aren't Task Scheduler
entries. Fix: the same CREATE_NO_WINDOW technique already proven throughout
setup/scripts/ (see run_ps1_hidden.py), applied at the hook-invocation layer.

Contract: TRUE passthrough. stdin/stdout/stderr are wired to sys.stdin/stdout/stderr
EXPLICITLY. This is NOT redundant with "omit the args" -- subprocess.run defaults to
close_fds=True, which on Windows means an *omitted* stdin/stdout/stderr does NOT reliably
propagate this process's own std handles to the child (confirmed empirically 2026-07-03:
omitting them silently dropped the doctrine guard's stderr block-message even though the
exit code passed through fine). Passing the sys.* objects explicitly forces Python to wire
STARTF_USESTDHANDLES with the real handles. This matters because two hooks use exit-code +
stderr as a real signal Claude Code acts on:
  - hook-market-hours-doctrine-guard.ps1 soft-blocks live-trading-config edits during
    market hours via exit 2 + a stderr message (Rule 9 enforcement).
  - hook-pytest-on-engine-edit.ps1 surfaces graduated-guard regressions the same way.
Do NOT add capture_output=True or stdout=/stderr=PIPE here -- that would buffer output
in this process instead of letting Claude Code read it directly, and risks silently
swallowing a block/regression message. Verified by direct old-vs-new diff (exit code AND
stderr text compared) before this script was wired into settings.local.json.

Usage: pythonw.exe run_hook_hidden.py <ps1-path> [args...]
"""
from __future__ import annotations

import subprocess
import sys

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        return 0  # malformed invocation -- fail open, never block Claude
    ps1_path = argv[1]
    extra_args = argv[2:]
    cmd = [
        "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-WindowStyle", "Hidden", "-NonInteractive", "-File", ps1_path,
    ] + extra_args
    try:
        # Explicit sys.* handles -- see module docstring for why omitting them is unsafe.
        proc = subprocess.run(
            cmd,
            stdin=sys.stdin,
            stdout=sys.stdout,
            stderr=sys.stderr,
            creationflags=_CREATE_NO_WINDOW,
            timeout=30,
        )
        return proc.returncode
    except subprocess.TimeoutExpired:
        return 0  # hooks must never hang Claude -- fail open
    except Exception:
        return 0  # a broken launcher must never become a blocker


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
