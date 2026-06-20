"""Window-leak compliance audit.

Enforces CLAUDE.md OP-27 L41 (5-layer subprocess-spawn discipline). Scans
project code for the two patterns that historically leaked visible cmd/conhost/
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
import sys
from datetime import datetime, timezone
from pathlib import Path

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


def main() -> int:
    ps1_flags = _audit_ps1_bare_python()
    py_flags = _audit_py_missing_creationflags()
    mcp_flags = _audit_mcp_configs()
    all_flags = ps1_flags + py_flags + mcp_flags
    report = {
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "health": "RED" if all_flags else "GREEN",
        "ps1_bare_python_count": len(ps1_flags),
        "py_subprocess_no_creationflags_count": len(py_flags),
        "mcp_unwrapped_launcher_count": len(mcp_flags),
        "flags": all_flags,
    }
    AUDIT_OUT.parent.mkdir(parents=True, exist_ok=True)
    AUDIT_OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("=" * 70)
    print("WINDOW-LEAK COMPLIANCE AUDIT")
    print("=" * 70)
    print(f"  audited_at:    {report['audited_at']}")
    print(f"  HEALTH:        {report['health']}")
    print(f"  PS1 bare `python`:                {report['ps1_bare_python_count']}")
    print(f"  Py subprocess w/o creationflags:  {report['py_subprocess_no_creationflags_count']}")
    print(f"  MCP servers w/o pythonw shim:     {report['mcp_unwrapped_launcher_count']}")
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
