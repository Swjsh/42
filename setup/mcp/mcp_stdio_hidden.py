"""mcp_stdio_hidden.py -- run a stdio MCP server with NO visible console window.

PROBLEM (the chronic "cmd windows keep popping up" leak)
  Claude Code spawns stdio MCP servers WITHOUT windowsHide / CREATE_NO_WINDOW. When the
  parent `claude.exe` is itself headless (a `claude --print` tick has no console of its
  own), every console-subsystem MCP launcher it spawns -- `uvx`, `uv`, `node`, `npx`,
  console `python` -- gets a BRAND-NEW conhost console window allocated by Windows,
  because there is no parent console to inherit. Result: a visible black window flashes on
  every tick (heartbeat every 3 min x2 accounts, premarket, EOD, every persona task).
  Confirmed empirically: each `uvx.exe`/`node.exe` MCP child owns a `conhost.exe ... 0x4`
  child (the window). Documented chronic leak: window-leak-detector.py docstring,
  CLAUDE.md OP-27 / L41 / lessons C8 (headless spawn = GUI-subsystem parent + CREATE_NO_WINDOW).

FIX
  Point the MCP server `command` at THIS script, run under `pythonw.exe`. `pythonw` is
  GUI-subsystem, so it NEVER allocates a console for itself. It then re-spawns the real
  server with CREATE_NO_WINDOW (Windows is required to honor the flag and allocate no
  console for the console-subsystem child), inheriting the exact stdio pipes Claude Code
  opened for the stdio transport. Net effect: the MCP server speaks JSON-RPC over the same
  stdin/stdout, but no conhost window is ever created.

USAGE (.mcp.json / ~/.claude.json mcpServers)
    "command": "C:\\Users\\jackw\\AppData\\Local\\Programs\\Python\\Python313\\pythonw.exe",
    "args": ["C:\\Users\\jackw\\Desktop\\42\\setup\\mcp\\mcp_stdio_hidden.py",
             "uvx", "alpaca-mcp-server"]

  The first arg after this script is the launcher (resolved on PATH); the rest are its
  args. Env is inherited from the parent, so the server's API-key env still flows through.

Stdlib-only so it runs under any pythonw. Exit code propagates from the child.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

# CREATE_NO_WINDOW gives the child a console that has NO window (and the whole subtree
# inherits it, so uv/python grandchildren don't allocate their own). On its own, though,
# the conhost can still FLASH visible for a few ms at creation when the parent itself is
# console-less (which a pythonw shim is). STARTUPINFO + SW_HIDE forces the window hidden
# from the first frame, killing the flash. We set BOTH -- belt and suspenders.
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
# Strategy override (for setup/mcp/_test_mcp_shim.py flash benchmarking only). Production
# default is "hide" = CREATE_NO_WINDOW + STARTF_USESHOWWINDOW/SW_HIDE.
_STRATEGY = os.environ.get("MCP_HIDE_STRATEGY", "hide").lower()


def _spawn_kwargs() -> dict:
    kw: dict = {"stdin": 0, "stdout": 1, "stderr": 2, "close_fds": False}
    if sys.platform != "win32":
        return kw
    flags = 0
    if _STRATEGY in ("hide", "cnw"):
        flags |= _CREATE_NO_WINDOW
    if _STRATEGY in ("hide", "swhide"):
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE  # 0 -- create the console window hidden
        kw["startupinfo"] = si
    kw["creationflags"] = flags
    return kw


def main(argv: list[str]) -> int:
    cmd = argv[1:]
    if not cmd:
        sys.stderr.write("mcp_stdio_hidden: no command given\n")
        return 2

    # Claude passes a bare launcher name ("uvx", "node"); resolve it on PATH so the child
    # spawn never depends on cwd. Fall back to the bare name (let the OS resolve / error).
    exe = shutil.which(cmd[0]) or cmd[0]
    real = [exe] + cmd[1:]

    # Pass the OS standard handles (fds 0/1/2) EXPLICITLY. Under pythonw, sys.stdin/out/err
    # are None, but the OS-level fds 0/1/2 ARE the pipes Claude Code handed us -- passing
    # the integer fds forces STARTF_USESTDHANDLES so the child inherits the real pipes
    # (not a fresh console).
    try:
        proc = subprocess.Popen(real, **_spawn_kwargs())
    except FileNotFoundError:
        sys.stderr.write(f"mcp_stdio_hidden: command not found: {cmd[0]}\n")
        return 127

    try:
        return proc.wait()
    except KeyboardInterrupt:
        try:
            proc.terminate()
        except Exception:
            pass
        return 130


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
