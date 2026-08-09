"""Window-leak compliance audit.

Enforces CLAUDE.md OP-27 L41 (5-layer subprocess-spawn discipline). Scans
project code for the patterns that historically leaked visible cmd/conhost/
PowerShell/python windows:

  1. Bare `python ` invocations in run-*.ps1 scheduled-task scripts
     (must use Invoke-PythonHidden helper in _shared.ps1)

  2. subprocess.run / subprocess.Popen / subprocess.check_output calls in
     Python files WITHOUT `creationflags=` (must include CREATE_NO_WINDOW
     0x08000000 on win32)

  3. stdio MCP servers (.mcp.json / ~/.claude.json / ~/.claude/settings.json)
     launched by a BARE console binary (uvx/uv/node/npx/python/...) instead of
     the windowless pythonw shim setup/mcp/mcp_stdio_hidden.py. `claude --print`
     spawns MCP servers headless; a console-subsystem launcher then gets a fresh
     conhost window on EVERY tick (heartbeat x2 every 3 min, EOD, premarket).
     Fix: run setup/mcp/patch_mcp_hidden.py. (2026-06-20 window-leak root cause.)

  4. LIVE Windows Task Scheduler registrations whose action is a bare console
     launcher or an unapproved hidden-window chain (added 2026-07-14).

BLIND SPOT THAT SHIPPED THIS CHECK (J: "stop the fkin popups on my screen",
2026-07-14): checks 1-3 above are ALL static source-text scans over repo files
(.ps1 / .py / .mcp.json). None of them ever looked at what Windows Task
Scheduler actually has REGISTERED. A task's live action can be a bare
`powershell.exe -WindowStyle Hidden` or the retired `run_hidden.vbs`
ShellExecute chain (leaks a WindowsTerminal -Embedding window on every Win11
fire) and this audit reported GREEN regardless, because neither string lives
inside any `.ps1`/`.py`/`.json` file this script reads -- one lives in Task
Scheduler's own XML action, the other inside a `.vbs` file this script never
scanned at all. Root cause, concretely: Gamma_DiscordBridge fired every 5 min,
24/7, via wscript->run_hidden.vbs, invisible to this audit for weeks. Check 4
closes that gap by delegating to `audit_scheduled_tasks.py`, which already does
correct live-registry enumeration + classification (single source of truth --
not reimplemented here).

STRUCTURAL GUARD: an audit that scans zero files/tasks must never report GREEN
-- see `_scan_coverage()` / EMPTY_SCAN below. C7 doctrine: silent success is
failure; audit outputs, not exit codes.

Outputs:
  automation/state/window-leak-compliance-audit.json

Exit code 0 if clean, 1 if any violations.

Wired into run-crypto-daily.ps1 right after audit_scheduled_tasks.py. The
absence of either pattern is REQUIRED for any future re-enablement of
Gamma_CryptoRegression to be safe.
"""
from __future__ import annotations

import json
import re
import shlex
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePath

REPO = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO / "setup" / "scripts"
AUDIT_OUT = REPO / "automation" / "state" / "window-leak-compliance-audit.json"

# --- MCP-config window-leak check (3) -------------------------------------------------
# stdio MCP servers must launch via the windowless pythonw shim, NOT a bare console
# binary. Console-subsystem launchers (uvx/uv/node/npx/python/...) get a fresh conhost
# window when claude --print spawns them headless.
HOME = Path.home()
MCP_SHIM_BASENAME = "mcp_stdio_hidden.py"
# command basenames (lowercased, .exe stripped) that allocate a console when run headless
MCP_CONSOLE_LAUNCHERS = {
    "uvx", "uv", "node", "npx", "npm", "bun", "deno", "python", "cmd", "powershell", "pwsh",
}
# (path, mode) -- mode "PROJECT" means dig into projects[<this repo>].mcpServers
MCP_CONFIG_SOURCES = [
    (REPO / ".mcp.json", "TOP"),
    (HOME / ".claude" / "settings.json", "TOP"),
    (HOME / ".claude.json", "PROJECT"),
]

# --- Claude Code hook-command check (5) -----------------------------------------------
# BLIND SPOT THAT SHIPPED THIS CHECK (J: "too many cmd and windows popups", 2026-08-09):
# checks 1-4 cover .ps1 text, .py text, MCP launchers, and Task Scheduler actions. NONE of
# them looked at `hooks` in settings.json -- and PreToolUse/PostToolUse fire on EVERY tool
# call in EVERY project, interactive and headless, which makes an unwrapped hook command
# strictly the highest-frequency console-flash source on this box. Concretely: the GLOBAL
# PreToolUse hook sat at a bare `npx -y block-no-verify@1.1.2` for a month. npx resolves to
# a .cmd/.ps1 shim on Windows, so every single tool call flashed a console, and this audit
# reported GREEN throughout -- the string lives in ~/.claude/settings.json's `hooks` block,
# which nothing here read. Note this repo's OWN project hooks were already correctly wrapped
# via run_hook_hidden.py; only the global one was missed, which is exactly why the check has
# to be mechanical instead of relying on whoever edits a settings file remembering.
HOOK_CONFIG_SOURCES = [
    REPO / ".claude" / "settings.json",
    REPO / ".claude" / "settings.local.json",
    HOME / ".claude" / "settings.json",
    HOME / ".claude" / "settings.local.json",
]
# A hook command is compliant when it is launched by pythonw (GUI subsystem -> no console of
# its own) AND routed through a wrapper that applies CREATE_NO_WINDOW to the real child.
HOOK_APPROVED_WRAPPERS = {"run_hook_hidden.py", "hidden_hook.py"}
HOOK_CONSOLE_LAUNCHERS = {
    "npx", "npm", "node", "bun", "deno", "uvx", "uv",
    "python", "python3", "py", "cmd", "powershell", "pwsh", "wsl", "bash", "sh", "git",
}

# Files exempt from the bare-python rule (e.g., interactive launchers J runs by hand,
# the helper itself, etc.).
PS1_BARE_PYTHON_EXEMPT = {
    "_shared.ps1",  # contains the helper definition (intentional python.exe reference)
    # Interactive / manual scripts. These are NOT scheduled — they run only when J types them.
    "session-start-digest.ps1",
    "preflight-readiness-audit.ps1",
    "audit-silent-watcher-days.ps1",
    "compute-state-hash.ps1",
    "benchmark-throttle.ps1",
    "fire-stage0-selftest.ps1",
    "fire19-final-verify.ps1",
}

# Directories whose Python files we audit. Skip venv + test code.
PY_AUDIT_ROOTS = [
    SCRIPTS_DIR,
    REPO / "automation",
    REPO / "backtest" / "autoresearch",
    REPO / "backtest" / "lib",
    REPO / "crypto",
    REPO / "eod_deep",
]
PY_EXCLUDE_PARTS = {"venv", ".venv", "__pycache__", "node_modules", ".git"}

BARE_PYTHON_RE = re.compile(r"^\s*(\$\w+\s*=\s*)?python(\.exe)?\s", re.MULTILINE)
SUBPROC_CALL_RE = re.compile(
    r"subprocess\.(run|Popen|call|check_output|check_call)\s*\(",
)


def _audit_ps1_bare_python() -> list[dict]:
    flags: list[dict] = []
    if not SCRIPTS_DIR.exists():
        return flags
    for ps1 in SCRIPTS_DIR.glob("*.ps1"):
        if ps1.name in PS1_BARE_PYTHON_EXEMPT:
            continue
        try:
            text = ps1.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            flags.append({"file": str(ps1.relative_to(REPO)), "line": 0,
                          "flag": "READ_ERROR", "detail": str(e)})
            continue
        for m in BARE_PYTHON_RE.finditer(text):
            line_no = text.count("\n", 0, m.start()) + 1
            line = text.splitlines()[line_no - 1] if line_no <= text.count("\n") + 1 else ""
            flags.append({
                "file": str(ps1.relative_to(REPO)),
                "line": line_no,
                "flag": "PS1_BARE_PYTHON",
                "detail": line.strip()[:200],
                "fix": "Replace with Invoke-PythonHidden -ScriptPath <path> from _shared.ps1.",
            })
    return flags


def _iter_audit_py_files():
    seen: set[Path] = set()
    for root in PY_AUDIT_ROOTS:
        if not root.exists():
            continue
        for py in root.rglob("*.py"):
            if any(part in PY_EXCLUDE_PARTS for part in py.parts):
                continue
            if py in seen:
                continue
            seen.add(py)
            yield py


def _audit_py_missing_creationflags() -> list[dict]:
    flags: list[dict] = []
    for py in _iter_audit_py_files():
        try:
            text = py.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            flags.append({"file": str(py.relative_to(REPO)), "line": 0,
                          "flag": "READ_ERROR", "detail": str(e)})
            continue
        for m in SUBPROC_CALL_RE.finditer(text):
            start = m.start()
            # Look at the next ~600 chars of the call expression. Heuristic: the call
            # ends at the matching `)` (we don't fully parse, so we approximate by
            # capturing up to the next blank line OR until paren depth returns to 0).
            tail = text[start:start + 800]
            # naive depth scan
            depth = 0
            end = len(tail)
            for i, ch in enumerate(tail):
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            call_text = tail[:end]
            if "creationflags" in call_text:
                continue
            # Skip subprocess.DEVNULL constants (they appear in "subprocess.DEVNULL" alone)
            line_no = text.count("\n", 0, start) + 1
            flags.append({
                "file": str(py.relative_to(REPO)),
                "line": line_no,
                "flag": "PY_SUBPROCESS_NO_CREATIONFLAGS",
                "detail": text.splitlines()[line_no - 1].strip()[:200],
                "fix": "Add creationflags=0x08000000 (CREATE_NO_WINDOW) on win32. "
                       "Define `_CREATE_NO_WINDOW = 0x08000000 if sys.platform == 'win32' else 0` at module top.",
            })
    return flags


def _cmd_basename(command: str) -> str:
    b = Path(str(command)).name.lower()
    return b[:-4] if b.endswith(".exe") else b


def _server_is_shimmed(cfg: dict) -> bool:
    args = cfg.get("args") or []
    return (
        str(cfg.get("command", "")).lower().endswith("pythonw.exe")
        and len(args) >= 1
        and MCP_SHIM_BASENAME in str(args[0])
    )


def _audit_mcp_server_dict(servers: dict, source: str) -> list[dict]:
    flags: list[dict] = []
    for name, cfg in (servers or {}).items():
        if not isinstance(cfg, dict):
            continue
        command = cfg.get("command")
        if not command:
            continue
        if _server_is_shimmed(cfg):
            continue
        if _cmd_basename(command) in MCP_CONSOLE_LAUNCHERS:
            flags.append({
                "file": source,
                "line": 0,
                "flag": "MCP_UNWRAPPED_CONSOLE_LAUNCHER",
                "detail": f"server '{name}' command={command!r} flashes a console on every claude tick",
                "fix": "Wrap via setup/mcp/mcp_stdio_hidden.py under pythonw "
                       "(run: python setup/mcp/patch_mcp_hidden.py).",
            })
    return flags


def _audit_mcp_configs() -> list[dict]:
    flags: list[dict] = []
    for path, mode in MCP_CONFIG_SOURCES:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            flags.append({"file": str(path), "line": 0, "flag": "MCP_CONFIG_READ_ERROR",
                          "detail": str(e)})
            continue
        if mode == "TOP":
            flags += _audit_mcp_server_dict(data.get("mcpServers") or {}, str(path))
        elif mode == "PROJECT":
            for key, proj in (data.get("projects") or {}).items():
                if not isinstance(proj, dict):
                    continue
                if not key.replace("/", "\\").rstrip("\\").endswith("Desktop\\42"):
                    continue
                flags += _audit_mcp_server_dict(proj.get("mcpServers") or {},
                                                f"{path} [projects/{key}]")
    return flags


def _audit_live_task_registry() -> list[dict]:
    """Check (4): what Windows Task Scheduler ACTUALLY has registered, live.

    Delegates to audit_scheduled_tasks.py rather than re-implementing task
    enumeration + hidden-chain classification here -- that module already does
    it correctly (live PowerShell enumeration + _is_hidden()/_is_bare_console_launcher()
    classifiers), and duplicating the logic would just create a second place for
    the classification to go stale (exactly how run_hidden.vbs's approval rotted
    in the first place). One source of truth.

    A 0-task result is NOT a clean scan -- it means the PowerShell helper failed
    or Task Scheduler was unreachable. Reported as a hard flag, never silently
    swallowed into an empty (GREEN-looking) list.
    """
    try:
        sys.path.insert(0, str(SCRIPTS_DIR))
        import audit_scheduled_tasks as ast  # noqa: E402  (local import, sys.path just set)
    except Exception as e:
        return [{
            "file": "setup/scripts/audit_scheduled_tasks.py", "line": 0,
            "flag": "LIVE_TASK_AUDIT_IMPORT_FAILED",
            "detail": f"{type(e).__name__}: {e}",
            "fix": "audit_scheduled_tasks.py must import cleanly for live-registry coverage "
                   "to run at all -- this audit cannot see Task Scheduler without it.",
        }]

    try:
        tasks = ast._registered_tasks()
    except Exception as e:
        return [{
            "file": "setup/scripts/_list-gamma-tasks-json.ps1", "line": 0,
            "flag": "LIVE_TASK_SCAN_FAILED",
            "detail": f"{type(e).__name__}: {e}",
            "fix": "PowerShell task enumeration raised -- investigate Task Scheduler "
                   "service / the helper script directly.",
        }]

    if not tasks:
        # STRUCTURAL GUARD (2026-07-14): this is the exact failure class that let the
        # OLD version of this file report near-zero violations while a live 5-min
        # popup storm ran -- except inverted (there, the scan silently never looked;
        # here, guard against the scan silently finding nothing). Both must be loud.
        return [{
            "file": "setup/scripts/_list-gamma-tasks-json.ps1", "line": 0,
            "flag": "LIVE_TASK_SCAN_EMPTY",
            "detail": "0 scheduled tasks returned from a live enumeration that should "
                      "always see 80+ Gamma_* tasks on this box. Treating as a scan "
                      "FAILURE, not a clean box.",
            "fix": "Run `Get-ScheduledTask -TaskName Gamma_*` by hand and compare.",
        }]

    flags: list[dict] = []
    for t in tasks:
        name = t.get("name", "?")
        execute = t.get("execute", "")
        arguments = t.get("arguments", "")
        if t.get("state") == "Disabled":
            continue
        if ast._is_bare_console_launcher(execute):
            flags.append({
                "file": f"scheduled-task:{name}", "line": 0,
                "flag": "TASK_BARE_CONSOLE_LAUNCHER",
                "detail": f"execute={execute!r} args={arguments[:100]!r}",
                "fix": "Convert to wscript->run_exe_hidden.vbs->pythonw->"
                       "run_ps1_hidden.py (or run_cmd_hidden.py) chain.",
            })
        elif not ast._is_hidden(execute, arguments):
            flags.append({
                "file": f"scheduled-task:{name}", "line": 0,
                "flag": "TASK_VISIBLE_WINDOW",
                "detail": f"execute={execute!r} args={arguments[:100]!r}",
                "fix": "Not on an approved hidden-window chain -- see "
                       "audit_scheduled_tasks._is_hidden() for the current approved list.",
            })
    return flags


def _scan_coverage() -> dict:
    """Independent counts of what the static scans actually touched, so `main()` can
    tell 'scanned everything, found nothing' apart from 'scanned nothing' -- the two
    look identical in the flags list alone (both empty) but mean opposite things."""
    ps1_count = len(list(SCRIPTS_DIR.glob("*.ps1"))) if SCRIPTS_DIR.exists() else 0
    py_count = sum(1 for _ in _iter_audit_py_files())
    return {"ps1_files_scanned": ps1_count, "py_files_scanned": py_count}


def _hook_commands(cfg: dict) -> list[tuple[str, str]]:
    """Yield (event, command) for every `type: command` hook in a settings dict."""
    out: list[tuple[str, str]] = []
    hooks = cfg.get("hooks")
    if not isinstance(hooks, dict):
        return out
    for event, matchers in hooks.items():
        if not isinstance(matchers, list):
            continue
        for matcher in matchers:
            if not isinstance(matcher, dict):
                continue
            for hook in matcher.get("hooks", []) or []:
                if isinstance(hook, dict) and hook.get("type") == "command":
                    cmd = hook.get("command")
                    if isinstance(cmd, str) and cmd.strip():
                        out.append((str(event), cmd))
    return out


def _first_token(cmd: str) -> str:
    """Basename of a command's executable, lowercased, .exe stripped."""
    try:
        tok = shlex.split(cmd, posix=False)[0]
    except (ValueError, IndexError):
        tok = cmd.split()[0] if cmd.split() else ""
    tok = tok.strip('"').strip("'")
    base = PurePath(tok.replace("\\", "/")).name.lower()
    return base[:-4] if base.endswith(".exe") else base


def _audit_hook_commands() -> tuple[list[dict], int]:
    """Check (5): Claude Code hook commands must run through the hidden wrapper chain.

    Returns (flags, hooks_scanned). Highest-frequency surface on the box -- see
    HOOK_CONFIG_SOURCES above for the incident that shipped this check.
    """
    flags: list[dict] = []
    scanned = 0
    for path in HOOK_CONFIG_SOURCES:
        if not path.is_file():
            continue
        try:
            cfg = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            flags.append({
                "file": str(path), "line": 0, "flag": "HOOK_CONFIG_UNREADABLE",
                "detail": f"{type(e).__name__}: {e}",
                "fix": "Settings file must be valid JSON for its hooks to be auditable.",
            })
            continue

        for event, cmd in _hook_commands(cfg):
            scanned += 1
            launcher = _first_token(cmd)
            if launcher.startswith("pythonw") and any(w in cmd for w in HOOK_APPROVED_WRAPPERS):
                continue  # compliant: pythonw + a CREATE_NO_WINDOW wrapper
            if launcher in HOOK_CONSOLE_LAUNCHERS or launcher.startswith("python"):
                flags.append({
                    "file": str(path), "line": 0, "flag": "HOOK_BARE_CONSOLE_LAUNCHER",
                    "detail": f"[{event}] launcher {launcher!r} spawns a console on every "
                              f"tool call: {cmd[:110]}",
                    "fix": "Route through pythonw + a hidden wrapper, e.g. "
                           "`<pythonw.exe> ~/.claude/scripts/hidden_hook.py <cmd...>` "
                           "(or setup/scripts/run_hook_hidden.py for a .ps1).",
                })
    return flags, scanned


def main() -> int:
    ps1_flags = _audit_ps1_bare_python()
    py_flags = _audit_py_missing_creationflags()
    mcp_flags = _audit_mcp_configs()
    task_flags = _audit_live_task_registry()
    hook_flags, hooks_scanned = _audit_hook_commands()
    coverage = _scan_coverage()
    coverage["hook_commands_scanned"] = hooks_scanned

    empty_scan_flags: list[dict] = []
    # STRUCTURAL GUARD: these directories/the task registry are NEVER legitimately
    # empty on this box. A 0-count here means the scan itself broke, and that must
    # read as RED, not as "0 violations found" (indistinguishable from clean
    # otherwise -- this is precisely the blind spot that let the old 3-check version
    # of this audit miss a live popup storm for weeks: it isn't enough for a check to
    # exist, it has to be provable that it actually looked at something).
    if coverage["ps1_files_scanned"] == 0:
        empty_scan_flags.append({
            "file": str(SCRIPTS_DIR.relative_to(REPO)), "line": 0, "flag": "EMPTY_SCAN_PS1",
            "detail": "0 .ps1 files found under setup/scripts -- scan did not run for real.",
            "fix": "Verify SCRIPTS_DIR path and that setup/scripts/*.ps1 exist.",
        })
    if coverage["py_files_scanned"] == 0:
        empty_scan_flags.append({
            "file": "PY_AUDIT_ROOTS", "line": 0, "flag": "EMPTY_SCAN_PY",
            "detail": "0 .py files found under any PY_AUDIT_ROOTS -- scan did not run for real.",
            "fix": "Verify PY_AUDIT_ROOTS paths resolve under this REPO checkout.",
        })

    # This repo's own .claude/settings.local.json always defines hooks, so a 0 count means
    # the hook scan didn't actually look -- same C7 logic as the ps1/py empty guards.
    if hooks_scanned == 0:
        empty_scan_flags.append({
            "file": "HOOK_CONFIG_SOURCES", "line": 0, "flag": "EMPTY_SCAN_HOOKS",
            "detail": "0 hook commands found across any settings.json -- scan did not run "
                      "for real (this repo's .claude/settings.local.json defines several).",
            "fix": "Verify HOOK_CONFIG_SOURCES paths resolve and the settings files parse.",
        })

    all_flags = ps1_flags + py_flags + mcp_flags + task_flags + hook_flags + empty_scan_flags
    report = {
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "health": "RED" if all_flags else "GREEN",
        "ps1_bare_python_count": len(ps1_flags),
        "py_subprocess_no_creationflags_count": len(py_flags),
        "mcp_unwrapped_launcher_count": len(mcp_flags),
        "live_task_registry_count": len(task_flags),
        "hook_bare_console_count": len(hook_flags),
        "scan_coverage": coverage,
        "flags": all_flags,
    }
    AUDIT_OUT.parent.mkdir(parents=True, exist_ok=True)
    AUDIT_OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("=" * 70)
    print("WINDOW-LEAK COMPLIANCE AUDIT")
    print("=" * 70)
    print(f"  audited_at:    {report['audited_at']}")
    print(f"  HEALTH:        {report['health']}")
    print(f"  scan coverage: {coverage['ps1_files_scanned']} .ps1 files, "
          f"{coverage['py_files_scanned']} .py files")
    print(f"  PS1 bare `python`:                {report['ps1_bare_python_count']}")
    print(f"  Py subprocess w/o creationflags:  {report['py_subprocess_no_creationflags_count']}")
    print(f"  MCP servers w/o pythonw shim:     {report['mcp_unwrapped_launcher_count']}")
    print(f"  LIVE task registry violations:    {report['live_task_registry_count']}")
    print(f"  Hook cmds w/o hidden wrapper:     {report['hook_bare_console_count']} "
          f"({coverage['hook_commands_scanned']} scanned)")
    if all_flags:
        print(f"\n  FLAGS ({len(all_flags)}):")
        for f in all_flags[:25]:
            print(f"    [{f['flag']:<35}] {f['file']}:{f['line']}  {f['detail'][:90]}")
        if len(all_flags) > 25:
            print(f"    ... and {len(all_flags) - 25} more (full list in {AUDIT_OUT.relative_to(REPO)})")
    print(f"\n  report: {AUDIT_OUT.relative_to(REPO)}")
    return 0 if not all_flags else 1


if __name__ == "__main__":
    raise SystemExit(main())
