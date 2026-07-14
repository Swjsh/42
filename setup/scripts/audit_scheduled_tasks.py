"""audit_scheduled_tasks — verify registered tasks vs SCHEDULED-TASKS.md registry.

Runs daily via Gamma_CryptoDaily. Flags:
  - ORPHAN_TASK            : registered but not in registry
  - STALE_REGISTRY_ENTRY   : in registry but not registered
  - BARE_CMD_POWERSHELL    : HARD FAIL -- bare cmd.exe/powershell.exe/.bat action (always
                             flashes OpenConsole on Win11; convert to
                             wscript->run_exe_hidden.vbs chain)
  - VISIBLE_WINDOW         : action not on the wscript->pythonw hidden chain (subtler patterns,
                             including the retired wscript->run_hidden.vbs ShellExecute path)
  - SILENT_TASK            : active task hasn't fired in (cadence x 3) window
  - PYTHON_NOT_PYTHONW     : long-running python.exe launch (should use pythonw.exe)
  - CANDIDATE_FOR_REMOVAL  : disabled > 30 days

Enumeration: `setup/scripts/_list-gamma-tasks-json.ps1` returns every `Gamma_*` task PLUS
a small explicit `$ExtraTaskNames` allowlist of other repo-managed automation registered
under a different name (e.g. SwjshAK-BrainSync). Those extra tasks are exempt from
ORPHAN_TASK/STALE_REGISTRY_ENTRY (SCHEDULED-TASKS.md is Gamma's own registry, not theirs)
but ARE fully subject to every window-leak safety check below -- see KNOWN_EXTERNAL_TASKS.

Writes:
  automation/state/scheduled-tasks-audit.json
  Console summary suitable for the daily digest.

Exit code 0 if no flags, 1 if any. Daily routine reads the JSON and surfaces RED to STATUS.md.

STRUCTURAL GUARD (2026-07-14, J: "stop the fkin popups on my screen"): a 0-task scan
(PowerShell helper failure, task-scheduler service down, etc.) must NEVER read as a clean
GREEN -- see the `total_registered == 0` hard-fail in `audit()`. A previous sibling
auditor (audit_window_leak_compliance.py) silently reported near-zero violations for
weeks not because there were none, but because it never looked at the live task registry
at all -- only at source-file text patterns. Silent-pass-on-empty-scan is the same failure
mode one layer up; guarded here explicitly so it can't recur.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
# TZ-SYSTEMIC FIX (2026-06-26): machine is Mountain time; datetime.now().weekday() returns
# Mountain weekday, which can be Saturday (5) when ET is still Friday.  Weekend-suppression
# logic that depends on the local weekday must use ET weekday.
from et_clock import et_weekday as _et_weekday  # DST-aware ET weekday

REGISTRY_PATH = Path("automation/state/SCHEDULED-TASKS.md")
AUDIT_OUT = Path("automation/state/scheduled-tasks-audit.json")

# CREATE_NO_WINDOW = 0x08000000 — suppress conhost allocation when spawning console
# binaries (powershell.exe, tasklist.exe, git.exe). See CLAUDE.md OP-27 L41.
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# Repo-managed automation registered under a non-Gamma_ name (see the matching
# $ExtraTaskNames array in _list-gamma-tasks-json.ps1, which is what actually pulls
# these into `tasks` below). SCHEDULED-TASKS.md is Gamma's OWN registry -- these
# will never appear in it, so they're exempt from ORPHAN_TASK/STALE_REGISTRY_ENTRY,
# but every window-leak safety check still runs against them normally.
KNOWN_EXTERNAL_TASKS = {"SwjshAK-BrainSync"}


def _powershell_file(path: Path) -> str:
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(path)],
        capture_output=True, text=True, check=False,
        creationflags=_CREATE_NO_WINDOW,
    ).stdout


def _parse_registry(text: str) -> tuple[set[str], set[str]]:
    """Return (active_names, disabled_names) parsed from the registry's markdown tables."""
    active: set[str] = set()
    disabled: set[str] = set()
    section = None
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("## Active"):
            section = "active"
            continue
        if s.startswith("## Disabled"):
            section = "disabled"
            continue
        if s.startswith("## "):
            section = None
            continue
        if section in ("active", "disabled") and s.startswith("| `Gamma_"):
            m = re.match(r"^\|\s*`(Gamma_[^`]+)`", s)
            if m:
                (active if section == "active" else disabled).add(m.group(1))
    return active, disabled


def _registered_tasks() -> list[dict]:
    """Return list of {name, state, execute, arguments, last_run, last_result, next_run}."""
    helper = Path("setup/scripts/_list-gamma-tasks-json.ps1")
    raw = _powershell_file(helper)
    if not raw.strip():
        return []
    parsed = json.loads(raw)
    return parsed if isinstance(parsed, list) else [parsed]


def _is_hidden(execute: str, arguments: str) -> bool:
    """Approved hidden-window patterns per OP-27.

    2026-07-14 CORRECTION (J: "stop the fkin popups on my screen" -- root cause was
    this exact function silently approving a proven-leaky pattern): `run_hidden.vbs`
    was DEMOTED from approved to NOT-hidden. It was carried as "older pattern, still
    approved" ever since the 2026-05-17 escalation, but `run_ps1_hidden.py`'s own
    docstring (written that SAME evening) documents the actual finding: `run_hidden.vbs`
    uses `WScript.Shell.Run` (ShellExecute), which "still leaks WindowsTerminal
    -Embedding windows on Windows 11 default-terminal configs" -- the fix that evening
    was to STOP using it, not to keep approving it. Whoever wrote this function's
    docstring transcribed the old pattern as still-good instead of retired. Live proof
    2026-07-14: Gamma_DiscordBridge fires every 5 min via this exact chain, 24/7 --
    the highest-frequency violator on the box, invisible to this audit until now
    because this function said it was fine.

    Canonical patterns, current:

    1. `wscript.exe //nologo run_exe_hidden.vbs <pythonw> <run_ps1_hidden.py> <ps1>`
       -- canonical L42 zero-leak pattern for PowerShell-wrapped tasks. Uses Python
       `subprocess.Popen(..., creationflags=CREATE_NO_WINDOW)` -- CreateProcess
       directly, which Windows is REQUIRED to honor.

    2. `wscript.exe //nologo run_exe_hidden.vbs <pythonw> <run_cmd_hidden.py> [args]`
       -- canonical WS6 zero-leak pattern for cmd-style grind tasks (2026-06-26).
       run_cmd_hidden.py accepts --env KEY=VAL + -- <python-exe> -m <module>.

    3. `wscript.exe //nologo run_hidden_exec.vbs <ps1> [args]` -- WshShell.Exec
       (CreateProcess) instead of Shell.Run (ShellExecute); also bypasses the WT
       DefaultTerminal handler. Approved alternative when no Python hop is wanted.

    4. A direct GUI-subsystem `pythonw.exe` action -- no console ever allocated,
       regardless of launcher (Task Scheduler included).

    NOT hidden: `wscript.exe //nologo run_hidden.vbs <ps1>` -- Shell.Run/ShellExecute,
    routes through the Win11 DefaultTerminal handler, leaks a `WindowsTerminal
    -Embedding` window on EVERY fire. Retired 2026-07-14; any task still on this
    pattern must be converted to #1 above.

    NOT hidden: a DIRECT `powershell.exe -WindowStyle Hidden` action. Task Scheduler
    allocates the console (OpenConsole.exe -Embedding on Win11) and SHOWS it before
    PowerShell applies -WindowStyle Hidden ~200ms later -> a visible black flash on EVERY
    fire (root-caused 2026-06-20 via Gamma_CryptoGrinderKeepalive, every 5 min = ~288
    flashes/day).

    NOT hidden: a DIRECT `cmd.exe /c ...` action, or a bare `.bat` action (Task
    Scheduler spawns cmd.exe to interpret it). Same allocation problem.
    """
    e = (execute or "").lower()
    a = (arguments or "").lower()
    if "wscript" in e and ("run_exe_hidden.vbs" in a or "run_hidden_exec.vbs" in a):
        return True
    if e.endswith("pythonw.exe"):
        return True
    return False


def _is_bare_console_launcher(execute: str) -> bool:
    """Return True if the task action is a bare console-subsystem launcher.

    Bare cmd.exe, powershell.exe, or a direct .bat/.cmd action (Task Scheduler
    spawns cmd.exe to interpret those) ALWAYS flash a console window on
    Windows 11 (OpenConsole -Embedding) before any -WindowStyle Hidden takes
    effect.  These MUST be converted to the wscript -> run_exe_hidden.vbs ->
    pythonw -> run_cmd_hidden.py / run_ps1_hidden.py chain.

    This check is a HARD FAIL in the audit (exit 1) -- not a warn -- because
    a regressed task will flash on every fire (up to 288 times/day for 5-min
    cadence tasks).  There is no acceptable reason to have a bare cmd.exe,
    bare powershell.exe, or bare .bat/.cmd Gamma task action.
    """
    e = (execute or "").strip().lower()
    # Match basename only so full paths like C:\Windows\System32\cmd.exe also match
    basename = e.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
    if basename in ("cmd.exe", "powershell.exe", "pwsh.exe"):
        return True
    return basename.endswith(".bat") or basename.endswith(".cmd")


def _is_long_running_python_with_console(execute: str, arguments: str) -> bool:
    e = (execute or "").lower()
    if e.endswith("python.exe"):
        return True
    if "python.exe" in (arguments or "").lower() and "live_grinder" in (arguments or "").lower():
        return True
    return False


HOOKS_SETTINGS_PATH = Path(".claude/settings.local.json")


def _is_bare_hook_command(command: str) -> bool:
    """Return True if a Claude Code hook `command` string is a bare console launcher.

    Root-caused 2026-07-03 (J: "cmd popups every few minutes"): PreToolUse/PostToolUse
    hooks fire on EVERY tool call across every session (interactive AND every scheduled
    `claude --print` task) -- a far higher-frequency flash source than any Task Scheduler
    action, and a surface this audit never covered before since hooks aren't Task
    Scheduler entries. Same Win11 OpenConsole-before-WindowStyle-Hidden mechanism as
    BARE_CMD_POWERSHELL applies here too. Fix: route through
    setup/scripts/run_hook_hidden.py (pythonw.exe + CREATE_NO_WINDOW), the same pattern
    _is_hidden() already approves for scheduled tasks.
    """
    first_tok = (command or "").strip().split(" ", 1)[0].strip('"')
    basename = first_tok.rsplit("\\", 1)[-1].rsplit("/", 1)[-1].lower()
    return basename in ("cmd.exe", "cmd", "powershell.exe", "powershell", "pwsh.exe", "pwsh")


def _audit_hooks() -> list[dict]:
    """Flag any .claude/settings.local.json hook `command` that isn't hidden-window-safe."""
    flags: list[dict] = []
    if not HOOKS_SETTINGS_PATH.exists():
        return flags
    try:
        data = json.loads(HOOKS_SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        flags.append({"flag": "HOOKS_UNPARSEABLE", "task": str(HOOKS_SETTINGS_PATH),
                      "note": f"{type(e).__name__}: {e}"})
        return flags
    for phase, entries in (data.get("hooks") or {}).items():
        for entry in entries:
            for h in entry.get("hooks", []):
                cmd = h.get("command", "")
                if h.get("type") != "command" or not cmd:
                    continue
                if _is_bare_hook_command(cmd):
                    flags.append({"flag": "BARE_HOOK_POWERSHELL", "task": f"hook:{phase}",
                                  "note": f"HARD FAIL -- bare console launcher in hook command: "
                                          f"{cmd[:100]!r}. Route through setup/scripts/run_hook_hidden.py."})
    return flags


def _parse_iso(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def _last_run_age_hours(last_run: str | None) -> float | None:
    if not last_run:
        return None
    dt = _parse_iso(last_run)
    if dt is None:
        return None
    # 1999 sentinel means never run
    if dt.year < 2020:
        return None
    return (datetime.now(dt.tzinfo) - dt).total_seconds() / 3600


def audit() -> dict:
    if not REGISTRY_PATH.exists():
        return {"error": f"registry missing: {REGISTRY_PATH}", "health": "RED"}
    registry_text = REGISTRY_PATH.read_text(encoding="utf-8")
    active_registry, disabled_registry = _parse_registry(registry_text)
    tasks = _registered_tasks()

    # STRUCTURAL GUARD (2026-07-14): a scan that returns zero tasks (PowerShell helper
    # crashed, Task Scheduler service unreachable, malformed JSON silently swallowed)
    # must never be indistinguishable from "all clear". `_registered_tasks()` already
    # returns [] on that failure mode -- treat it as a hard error, not a clean report.
    if not tasks:
        return {"error": "0 tasks returned by _registered_tasks() -- PowerShell helper "
                          "failure or empty Task Scheduler query; NOT a clean scan",
                "health": "RED"}

    by_name = {t["name"]: t for t in tasks}

    flags: list[dict] = []

    # Claude Code hook commands (.claude/settings.local.json) -- separate surface from
    # Task Scheduler actions, same hidden-window requirement. See _audit_hooks docstring.
    flags.extend(_audit_hooks())

    # Registered but not in registry (external repo-managed tasks are known-external
    # by design -- see KNOWN_EXTERNAL_TASKS -- not an accidental orphan).
    for name in sorted(by_name):
        if name in KNOWN_EXTERNAL_TASKS:
            continue
        if name not in active_registry and name not in disabled_registry:
            flags.append({"flag": "ORPHAN_TASK", "task": name,
                          "note": f"task registered but not in {REGISTRY_PATH}"})

    # In registry but not registered
    for name in sorted(active_registry):
        if name not in by_name:
            flags.append({"flag": "STALE_REGISTRY_ENTRY", "task": name,
                          "note": "registry says active but task not registered"})

    # Window visibility + python console + silent task
    for t in tasks:
        name = t["name"]
        state = t["state"]
        if state == "Disabled":
            continue
        if _is_bare_console_launcher(t["execute"]):
            # HARD FAIL: bare cmd.exe / powershell.exe flashes a window on EVERY fire.
            # This is distinct from VISIBLE_WINDOW (which catches subtler patterns) and
            # is always a bug -- there is no approved use of a bare console launcher.
            flags.append({"flag": "BARE_CMD_POWERSHELL", "task": name,
                          "note": f"HARD FAIL -- bare console launcher: execute={t['execute']!r}. "
                                  f"Convert to wscript->run_exe_hidden.vbs->pythonw->run_cmd_hidden.py chain."})
        elif not _is_hidden(t["execute"], t["arguments"]):
            flags.append({"flag": "VISIBLE_WINDOW", "task": name,
                          "note": f"execute={t['execute']!r} args={t['arguments'][:80]!r}"})
        if _is_long_running_python_with_console(t["execute"], t["arguments"]):
            flags.append({"flag": "PYTHON_NOT_PYTHONW", "task": name,
                          "note": "long-running python.exe should use pythonw.exe"})

        # Silent-task check using simple rules:
        # If a task hasn't fired in 24 hours, flag it (unless its cadence is weekly)
        age_h = _last_run_age_hours(t.get("last_run"))
        if age_h is None:
            # never ran or unparseable — flag only if was supposed to run
            continue
        # Weekend false-positive suppression: weekday-only tasks are expected silent on
        # Sat/Sun. Max legitimate gap = ~62h (Thu EOD -> Mon premarket); allow 70h.
        _today_dow = _et_weekday()  # 5=Sat, 6=Sun — ET (not local Mountain) — TZ-SYSTEMIC fix
        if _today_dow >= 5 and age_h <= 70:
            continue
        # Heuristic: anything > 26h old without successful run = SILENT
        if age_h > 26 and "Weekly" not in name and "Monday" not in name:
            flags.append({"flag": "SILENT_TASK", "task": name,
                          "note": f"last ran {age_h:.1f}h ago — expected within 26h"})

    health = "RED" if flags else "GREEN"
    summary = {
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "total_registered": len(tasks),
        "active_registered": sum(1 for t in tasks if t["state"] != "Disabled"),
        "disabled_registered": sum(1 for t in tasks if t["state"] == "Disabled"),
        "registry_active": len(active_registry),
        "registry_disabled": len(disabled_registry),
        "flags_count": len(flags),
        "flags": flags,
        "health": health,
    }
    return summary


def main():
    out = audit()
    AUDIT_OUT.parent.mkdir(parents=True, exist_ok=True)
    AUDIT_OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print("=" * 70)
    print("SCHEDULED-TASKS AUDIT")
    print("=" * 70)
    if "error" in out:
        print(f"  ERROR: {out['error']}")
        sys.exit(1)
    print(f"  audited_at:           {out['audited_at']}")
    print(f"  registered active:    {out['active_registered']}  (registry says: {out['registry_active']})")
    print(f"  registered disabled:  {out['disabled_registered']}  (registry says: {out['registry_disabled']})")
    print(f"  HEALTH:               {out['health']}")
    if out["flags"]:
        print(f"  FLAGS ({len(out['flags'])}):")
        for f in out["flags"]:
            print(f"    [{f['flag']:<22s}] {f['task']:<35s} {f['note']}")
    else:
        print(f"  FLAGS:                none -- registry & reality in sync, all windows hidden")
    print()
    print(f"  scorecard: {AUDIT_OUT}")
    sys.exit(0 if not out["flags"] else 1)


if __name__ == "__main__":
    main()
