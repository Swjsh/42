"""Smoke test for mcp_stdio_hidden.py.

Proves the shim is safe to put in front of a LIVE trading MCP server:
  1. STDIO round-trips: the real `uvx alpaca-mcp-server` completes the MCP `initialize`
     handshake through the shim (so heartbeat/EOD ticks keep their Alpaca tools).
  2. NO visible window: no top-level visible window is owned by any process in the shim's
     subtree while the server runs (the whole point of the fix).

Run:  python setup/mcp/_test_mcp_shim.py
Exit: 0 = both checks PASS, 1 = a check FAILED.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SHIM = REPO / "setup" / "mcp" / "mcp_stdio_hidden.py"
PYTHONW = r"C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
CNW = 0x08000000


def _alpaca_env() -> dict:
    cfg = json.loads((REPO / ".mcp.json").read_text(encoding="utf-8"))
    env = dict(os.environ)
    env.update(cfg["mcpServers"]["alpaca"].get("env", {}))
    return env


def _descendants(root_pid: int) -> set[int]:
    """All PIDs in the subtree rooted at root_pid (inclusive), via one wmic snapshot."""
    out = subprocess.check_output(
        ["wmic", "process", "get", "ProcessId,ParentProcessId", "/format:csv"],
        creationflags=CNW, stderr=subprocess.DEVNULL, timeout=15,
    ).decode("utf-8", "ignore")
    parent: dict[int, int] = {}
    for line in out.splitlines():
        parts = line.split(",")
        if len(parts) < 3:
            continue
        try:
            # wmic /format:csv emits columns ALPHABETICALLY: Node,ParentProcessId,ProcessId
            ppid, pid = int(parts[-2]), int(parts[-1])
        except ValueError:
            continue
        parent[pid] = ppid
    kids: dict[int, list[int]] = {}
    for pid, ppid in parent.items():
        kids.setdefault(ppid, []).append(pid)
    seen, stack = set(), [root_pid]
    while stack:
        p = stack.pop()
        if p in seen:
            continue
        seen.add(p)
        stack.extend(kids.get(p, []))
    return seen


def _visible_windows_for(pids: set[int]) -> list[tuple]:
    user32 = ctypes.windll.user32
    found: list[tuple] = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(hwnd, _lparam):
        if user32.IsWindowVisible(hwnd):
            pid = wt.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value in pids:
                n = user32.GetWindowTextLengthW(hwnd)
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                found.append((hwnd, pid.value, buf.value))
        return True

    user32.EnumWindows(cb, 0)
    return found


def main() -> int:
    if not SHIM.exists():
        print(f"FAIL: shim not found at {SHIM}")
        return 1
    if not Path(PYTHONW).exists():
        print(f"FAIL: pythonw not found at {PYTHONW}")
        return 1

    print("Launching: pythonw mcp_stdio_hidden.py uvx alpaca-mcp-server ...")
    proc = subprocess.Popen(
        [PYTHONW, str(SHIM), "uvx", "alpaca-mcp-server"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=_alpaca_env(), cwd=str(REPO), creationflags=CNW,
    )

    stdio_ok = False
    try:
        req = {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "shim-smoketest", "version": "0.0.1"},
            },
        }
        proc.stdin.write((json.dumps(req) + "\n").encode())
        proc.stdin.flush()

        # Give the server (uv cold-start) up to 60s to answer id:1.
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            line = proc.stdout.readline()
            if not line:
                if proc.poll() is not None:
                    break
                continue
            try:
                msg = json.loads(line.decode("utf-8", "ignore").strip())
            except json.JSONDecodeError:
                continue  # skip any non-JSON banner noise
            if msg.get("id") == 1 and ("result" in msg or "error" in msg):
                stdio_ok = "result" in msg
                info = msg.get("result", {}).get("serverInfo", {})
                print(f"  initialize response: result={'result' in msg} serverInfo={info}")
                break

        # No-window proof: while the server is fully up, no subtree process owns a
        # visible top-level window.
        time.sleep(1.0)
        subtree = _descendants(proc.pid)
        vis = _visible_windows_for(subtree)
        window_ok = len(vis) == 0
        print(f"  subtree pids={len(subtree)}  visible windows={len(vis)}  {vis if vis else ''}")
    finally:
        try:
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                           creationflags=CNW, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=10)
        except Exception:
            pass

    print(f"\nSTDIO handshake : {'PASS' if stdio_ok else 'FAIL'}")
    print(f"No visible window: {'PASS' if window_ok else 'FAIL'}")
    return 0 if (stdio_ok and window_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
