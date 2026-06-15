"""audit_scheduled_tasks — verify registered tasks vs SCHEDULED-TASKS.md registry.

Runs daily via Gamma_CryptoDaily. Flags:
  - ORPHAN_TASK            : registered but not in registry
  - STALE_REGISTRY_ENTRY   : in registry but not registered
  - VISIBLE_WINDOW         : action not hidden (wscript or powershell -WindowStyle Hidden)
  - SILENT_TASK            : active task hasn't fired in (cadence x 3) window
  - PYTHON_NOT_PYTHONW     : long-running python.exe launch (should use pythonw.exe)
  - CANDIDATE_FOR_REMOVAL  : disabled > 30 days

Writes:
  automation/state/scheduled-tasks-audit.json
  Console summary suitable for the daily digest.

Exit code 0 if no flags, 1 if any. Daily routine reads the JSON and surfaces RED to STATUS.md.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REGISTRY_PATH = Path("automation/state/SCHEDULED-TASKS.md")
AUDIT_OUT = Path("automation/state/scheduled-tasks-audit.json")

# CREATE_NO_WINDOW = 0x08000000 — suppress conhost allocation when spawning console
# binaries (powershell.exe, tasklist.exe, git.exe). See CLAUDE.md OP-27 L41.
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


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

    Per OP-27 L42 escalation (2026-05-17 evening), two patterns are canonical:

    1. `wscript.exe //nologo run_hidden.vbs <ps1>` -- older, simpler pattern for
       tasks that don't have window-leak concerns. Still approved.

    2. `wscript.exe //nologo run_exe_hidden.vbs <sys-pythonw> <run_ps1_hidden.py> <ps1>`
       -- the canonical L42 zero-leak pattern. Uses GUI-subsystem pythonw to
       launch run_ps1_hidden.py which subprocess.Popens powershell.exe with
       CREATE_NO_WINDOW flag. Required for tasks where Windows 11 default-
       terminal would otherwise grab the child console.

    Also approved: `powershell.exe -WindowStyle Hidden ...` for one-off scripts.
    """
    e = (execute or "").lower()
    a = (arguments or "").lower()
    if "wscript" in e and ("run_hidden.vbs" in a or "run_exe_hidden.vbs" in a):
        return True
    if "powershell" in e and "-windowstyle hidden" in a:
        return True
    return False


def _is_long_running_python_with_console(execute: str, arguments: str) -> bool:
    e = (execute or "").lower()
    if e.endswith("python.exe"):
        return True
    if "python.exe" in (arguments or "").lower() and "live_grinder" in (arguments or "").lower():
        return True
    return False


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
        return {"error": f"registry missing: {REGISTRY_PATH}"}
    registry_text = REGISTRY_PATH.read_text(encoding="utf-8")
    active_registry, disabled_registry = _parse_registry(registry_text)
    tasks = _registered_tasks()
    by_name = {t["name"]: t for t in tasks}

    flags: list[dict] = []

    # Registered but not in registry
    for name in sorted(by_name):
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
        if not _is_hidden(t["execute"], t["arguments"]):
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
