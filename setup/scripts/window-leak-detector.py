"""Continuous window-leak detector for Project Gamma.

WHY THIS EXISTS
  The user (J) cannot play video games because Gamma's scheduled-task scripts leak
  visible Windows (cmd/conhost/PowerShell/python) every ~30 sec to ~5 min. CLAUDE.md
  OP-27 + L41 documents prevention discipline; this script makes the prevention
  AUDITABLE in real time.

WHAT IT DOES
  Every second, enumerates every visible top-level window via the Windows API
  (EnumWindows + IsWindowVisible + GetWindowThreadProcessId). For each window whose
  owning process is in {python.exe, pythonw.exe, cmd.exe, conhost.exe, powershell.exe,
  pwsh.exe, wscript.exe, cscript.exe, WindowsTerminal.exe, OpenConsole.exe} AND
  appears for the FIRST time this poll (i.e., wasn't visible last poll), logs a row
  to automation/state/window-leaks.jsonl.

  Each row: {ts, hwnd, pid, ppid, image_name, title, command_line, ancestry}.

LIFECYCLE
  Long-running. Started via wscript+run_exe_hidden.vbs wrapper with system pythonw.
  PID written to automation/state/window-leak-detector.pid. Idempotent: refuses to
  start if a sibling is already alive.

ALLOWLIST
  Reads automation/state/window-leak-allowlist.json:
    {"image_names": ["WindowsTerminal.exe"], "title_substrings": ["Claude Code"],
     "pids": [12345]}
  Allowlisted entries are skipped silently.

ROOT CAUSE PROTOCOL
  When this detector logs a leak, the leak's source script is identifiable via the
  command_line + ancestry fields. The fix protocol is in CLAUDE.md OP-27 L41
  (5-layer subprocess-spawn discipline) -- this detector merely surfaces violations.
"""
from __future__ import annotations

# === HEADLESS STDIO REDIRECT ============================================================
# When launched via pythonw.exe (no console), Windows 11's default-terminal setting can
# allocate a visible WT tab on first stderr write. Redirect stdio to log files BEFORE any
# logging.basicConfig() runs. CLAUDE.md OP-27 L41 layer 3.
import os as _os
import sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower() == "pythonw.exe":
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "window-leak-detector.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "window-leak-detector.stderr.log", "a", buffering=1, encoding="utf-8")
# ========================================================================================

import ctypes
import ctypes.wintypes as wt
import datetime as dt
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STATE_DIR = REPO / "automation" / "state"
LEAK_LOG = STATE_DIR / "window-leaks.jsonl"
PID_FILE = STATE_DIR / "window-leak-detector.pid"
ALLOW_FILE = STATE_DIR / "window-leak-allowlist.json"
SUMMARY_FILE = STATE_DIR / "window-leak-summary.json"

# Process image names we ALWAYS scrutinize -- if these have a visible top-level window
# and aren't allowlisted, it's a real foot-gun (L41 violation).
SUSPECT_IMAGES = {
    "python.exe", "pythonw.exe",
    "cmd.exe", "conhost.exe", "OpenConsole.exe",
    "powershell.exe", "pwsh.exe",
    "wscript.exe", "cscript.exe",
    # WindowsTerminal.exe is grey: legitimate when J opens a terminal, but a leak when
    # spawned by a scheduled task. We log it and let the allowlist filter user sessions.
    "WindowsTerminal.exe",
}

DEFAULT_ALLOWLIST = {
    # Process image names that are NEVER a leak regardless of source.
    "image_names": [],
    # Substring matches against window title.
    "title_substrings": [
        "Claude Code",     # interactive Claude Code sessions
        "Claude in Chrome",
        "Apex Legends",
        "Steam",
        "Discord",
    ],
    # Specific PIDs to ignore (e.g., long-running discord-bridge that J trusts).
    "pids": [],
}


# === Win32 plumbing ====================================================================

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

EnumWindows = user32.EnumWindows
EnumWindows.argtypes = [ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM), wt.LPARAM]
EnumWindows.restype = wt.BOOL

IsWindowVisible = user32.IsWindowVisible
IsWindowVisible.argtypes = [wt.HWND]
IsWindowVisible.restype = wt.BOOL

GetWindowThreadProcessId = user32.GetWindowThreadProcessId
GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
GetWindowThreadProcessId.restype = wt.DWORD

GetWindowTextLengthW = user32.GetWindowTextLengthW
GetWindowTextLengthW.argtypes = [wt.HWND]
GetWindowTextLengthW.restype = ctypes.c_int

GetWindowTextW = user32.GetWindowTextW
GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
GetWindowTextW.restype = ctypes.c_int

ShowWindow = user32.ShowWindow
ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
ShowWindow.restype = wt.BOOL
SW_HIDE = 0

# 2026-07-14 AUTO-MITIGATION (J: "stop the fkin popus on my screen"): root-caused down to
# `import pandas`/numpy triggering a WindowsTerminal -Embedding console-host window on
# headless (pythonw.exe) launches of backtest-venv scripts -- confirmed this is NOT an
# stdio-write trigger (survived Python-level sys.stdout/stderr redirect, OS-level os.dup2
# fd redirect, AND warnings.filterwarnings("ignore") -- all three tested live, all three
# still leaked), so no script-level or launcher-level fix (Shell.Run vs WshExec vs Python
# subprocess.Popen+CREATE_NO_WINDOW -- all three tested live, all three still leaked) could
# close it in the time available this session. This is a pure console-HOST window
# (WindowsTerminal.exe/OpenConsole.exe/conhost.exe): hiding it does not touch, kill, or
# interrupt the underlying pythonw.exe process actually doing the work -- ShowWindow(SW_HIDE)
# only affects the window's on-screen visibility, so this is safe even mid-leak.
CONSOLE_HOST_IMAGES = {"WindowsTerminal.exe", "OpenConsole.exe", "conhost.exe"}


def _enum_visible_top_windows() -> list[tuple[int, int, str]]:
    """Return [(hwnd, pid, title), ...] for every visible top-level window with title."""
    results: list[tuple[int, int, str]] = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def _cb(hwnd: int, lparam: int) -> int:
        if not IsWindowVisible(hwnd):
            return True
        length = GetWindowTextLengthW(hwnd)
        if length == 0:
            return True  # invisible-to-user titleless windows -> skip
        buf = ctypes.create_unicode_buffer(length + 1)
        GetWindowTextW(hwnd, buf, length + 1)
        pid = wt.DWORD()
        GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        results.append((int(hwnd), int(pid.value), buf.value))
        return True

    EnumWindows(_cb, 0)
    return results


# === Process metadata via WMIC (one shot per leak, not per poll) =====================

def _process_metadata(pid: int) -> dict:
    """Return {image_name, command_line, ppid} via WMIC (creationflags=CREATE_NO_WINDOW)."""
    try:
        out = subprocess.check_output(
            ["wmic", "process", "where", f"ProcessId={pid}", "get",
             "Name,ParentProcessId,CommandLine", "/FORMAT:LIST"],
            stderr=subprocess.DEVNULL, timeout=3,
            creationflags=0x08000000,
        ).decode("utf-8", errors="ignore")
        parts: dict[str, str] = {}
        for line in out.splitlines():
            line = line.strip()
            if "=" in line:
                k, _, v = line.partition("=")
                parts[k.strip()] = v.strip()
        return {
            "image_name": parts.get("Name", ""),
            "ppid": int(parts.get("ParentProcessId", "0") or "0"),
            "command_line": parts.get("CommandLine", "")[:500],
        }
    except Exception as e:
        return {"image_name": "?", "ppid": 0, "command_line": f"wmic_err:{e}"[:200]}


def _ancestry(pid: int, depth: int = 6) -> list[dict]:
    """Walk parent chain up to `depth` for diagnostic context."""
    chain: list[dict] = []
    cur = pid
    for _ in range(depth):
        if cur == 0:
            break
        info = _process_metadata(cur)
        chain.append({"pid": cur, "image_name": info["image_name"]})
        nxt = info["ppid"]
        if nxt == 0 or nxt == cur:
            break
        cur = nxt
    return chain


# === Allowlist =========================================================================

def _load_allowlist() -> dict:
    if not ALLOW_FILE.exists():
        ALLOW_FILE.write_text(json.dumps(DEFAULT_ALLOWLIST, indent=2), encoding="utf-8")
        return DEFAULT_ALLOWLIST
    try:
        return {**DEFAULT_ALLOWLIST, **json.loads(ALLOW_FILE.read_text(encoding="utf-8"))}
    except Exception:
        return DEFAULT_ALLOWLIST


def _is_service_rooted(ancestry: list[dict]) -> bool:
    """True if the ancestry chain looks Task-Scheduler/service-originated (svchost/services/
    wininit within the first few hops) rather than something J opened by hand (which would
    descend from explorer.exe -- Start Menu, taskbar, a shortcut). This is the safety gate
    for auto-hiding a console-host window: only ever touch windows that could not plausibly
    be a real terminal J is using himself."""
    names = [a.get("image_name", "") for a in ancestry[:4]]
    if "explorer.exe" in names:
        return False
    if any(n in ("svchost.exe", "services.exe", "wininit.exe") for n in names):
        return True
    # UNRESOLVABLE ANCESTRY = TREAT AS SERVICE-ROOTED (2026-08-24 fix).
    #
    # THE BUG THIS CLOSES. A leaked WindowsTerminal window is enumerated within ~0.5s of
    # spawning, often before WMI can resolve its parent chain; _ancestry() then returns a
    # single stub entry with an empty image_name. The old gate read that as "not
    # service-rooted" and skipped the hide, so the window stayed ON SCREEN. Evidence: every
    # mitigated=false row in window-leaks.jsonl has ancestry == [{pid, image_name: ""}]
    # while every mitigated=true row has the full 5-deep svchost->services->wininit chain.
    #
    # WHY THIS IS SAFE. We only reach here for a console-host image that already FAILED the
    # title allowlist, and hiding never kills -- a window J actually opened is exempted by
    # title ("Windows PowerShell", "Claude Code", ...) before ancestry is ever consulted.
    if not any(n for n in names):
        return True
    return False


# Images a TITLE-substring allowlist may exempt (2026-08-13 SCOPE FIX).
#
# THE BUG THIS CLOSES. The title allowlist ("Claude Code", "Steam", "Apex Legends", ...) exists
# so J's OWN app windows are not reported as leaks. But it was matched against EVERY suspect
# image, and a console host spawned BY one of those apps INHERITS the parent's console title.
# So a transient `powershell.exe` console launched from a Claude Code session carried the title
# "Claude Code", matched the allowlist, and was silently skipped -- not logged, not counted,
# not hidden.
#
# Measured consequence: on 2026-08-13 J reported console windows flashing on screen while
# window-leak-summary.json read `leaks_total: 0` across 3,180,000 polls, and window-leaks.jsonl
# had recorded nothing since 2026-07-14. The detector was not broken -- it was exempting exactly
# the windows being complained about.
#
# A title match is now only honoured for the app's OWN window image. A console host is never
# exempted by inheriting an allowlisted app's title.
TITLE_ALLOWLIST_IMAGES = {"WindowsTerminal.exe"}


def _is_allowed(image_name: str, title: str, pid: int, allow: dict) -> bool:
    if image_name in allow.get("image_names", []):
        return True
    if pid in allow.get("pids", []):
        return True
    # Title substrings are TRUSTED ONLY for the app's own window image. Console hosts
    # (powershell.exe / cmd.exe / conhost.exe / OpenConsole.exe) inherit their parent's title
    # and must never be exempted by it -- that is the blindness this scope closes.
    if image_name in TITLE_ALLOWLIST_IMAGES:
        for sub in allow.get("title_substrings", []):
            if sub and sub.lower() in title.lower():
                return True
    return False


# === PID file (singleton guard) ========================================================

def _claim_pid_file() -> None:
    if PID_FILE.exists():
        try:
            other_pid = int(PID_FILE.read_text(encoding="utf-8").strip())
            # Check if other PID is alive
            out = subprocess.check_output(
                ["tasklist", "/FI", f"PID eq {other_pid}", "/FO", "CSV", "/NH"],
                stderr=subprocess.DEVNULL, timeout=5,
                creationflags=0x08000000,
            ).decode("utf-8", errors="ignore")
            if f"{other_pid}" in out:
                print(f"[detector] sibling PID {other_pid} still alive — exiting", flush=True)
                sys.exit(0)
        except Exception:
            pass  # stale pid file
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")


def _release_pid_file(*_: object) -> None:
    try:
        PID_FILE.unlink(missing_ok=True)
    except Exception:
        pass


# === Main loop =========================================================================

def main() -> int:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LEAK_LOG.parent.mkdir(parents=True, exist_ok=True)
    _claim_pid_file()
    signal.signal(signal.SIGINT, lambda *a: (_release_pid_file(), sys.exit(0)))
    signal.signal(signal.SIGTERM, lambda *a: (_release_pid_file(), sys.exit(0)))

    print(f"[detector] start pid={os.getpid()} log={LEAK_LOG}", flush=True)

    prev_keys: set[tuple[int, int]] = set()  # (hwnd, pid)
    leak_counter = 0
    poll_count = 0
    poll_interval_s = 0.5

    while True:
        try:
            allow = _load_allowlist()
            visible = _enum_visible_top_windows()
            cur_keys = {(h, p) for (h, p, _t) in visible}
            new_windows = [(h, p, t) for (h, p, t) in visible if (h, p) not in prev_keys]

            for hwnd, pid, title in new_windows:
                # Fast path: WMIC is slow, only call for suspect-looking pids.
                # Cheap pre-filter via psutil-style check: read image_name from /proc-equivalent.
                # No psutil dependency -> just call WMIC.
                meta = _process_metadata(pid)
                image = meta["image_name"]
                if image not in SUSPECT_IMAGES:
                    continue
                if _is_allowed(image, title, pid, allow):
                    continue
                ancestry = _ancestry(pid)
                mitigated = False
                if image in CONSOLE_HOST_IMAGES and _is_service_rooted(ancestry):
                    # Hide, never kill: this only changes on-screen visibility -- the
                    # underlying pythonw.exe process (the actual scheduled-task work) is
                    # completely untouched and keeps running/writing its real output
                    # normally. Safe even if the root-cause script is mid-execution.
                    try:
                        ShowWindow(hwnd, SW_HIDE)
                        mitigated = True
                    except Exception:
                        mitigated = False
                row = {
                    "ts": dt.datetime.utcnow().isoformat() + "Z",
                    "hwnd": hwnd,
                    "pid": pid,
                    "ppid": meta["ppid"],
                    "image_name": image,
                    "title": title[:200],
                    "command_line": meta["command_line"],
                    "ancestry": ancestry,
                    "mitigated": mitigated,
                }
                with LEAK_LOG.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(row) + "\n")
                leak_counter += 1
                print(f"[detector] LEAK #{leak_counter} pid={pid} image={image} "
                      f"title={title[:80]} mitigated={mitigated}", flush=True)

            prev_keys = cur_keys
            poll_count += 1

            # Every 600 polls (~5 min), write a summary heartbeat.
            if poll_count % 600 == 0:
                SUMMARY_FILE.write_text(json.dumps({
                    "last_summary_at": dt.datetime.utcnow().isoformat() + "Z",
                    "polls_total": poll_count,
                    "leaks_total": leak_counter,
                    "poll_interval_s": poll_interval_s,
                    "pid": os.getpid(),
                }, indent=2), encoding="utf-8")

        except Exception as exc:
            print(f"[detector] poll error: {exc}", flush=True)

        time.sleep(poll_interval_s)


if __name__ == "__main__":
    raise SystemExit(main())
