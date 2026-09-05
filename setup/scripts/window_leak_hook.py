"""Event-driven window-leak hider for Project Gamma (instant, pre-paint).

Complements the polling window-leak-detector.py: a SetWinEventHook on
EVENT_OBJECT_SHOW fires the instant a window becomes visible, so a leaked
service-rooted console-host window (WindowsTerminal -Embedding / conhost /
OpenConsole) is SW_HIDE'd within a frame of appearing -- effectively never
seen. Hide-only, never kills the underlying pythonw work process.

Safety gate is identical to the poller: only ever hides windows whose
ancestry is svchost/services/wininit-rooted (Task Scheduler / Session 0),
and NEVER a window descending from explorer.exe (a terminal J opened
himself). Games/apps aren't console-host images so they're untouched.

Singleton via a named kernel mutex (no pid-file/PID-reuse foot-gun).

2026-07-23: shipped for J "STOP ALL POPUPS NOW" -- the 0.1s poller still left
a sub-100ms flash; this closes it to imperceptible. Poller stays as backstop.
"""
from __future__ import annotations

import collections
import ctypes
import ctypes.wintypes as wt
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

# === headless stdio redirect (pythonw has no console) ===================================
if os.path.basename(sys.executable).lower().startswith("pythonw"):
    _ld = Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _ld.mkdir(parents=True, exist_ok=True)
    sys.stdout = open(_ld / "window-leak-hook.stdout.log", "a", buffering=1, encoding="utf-8")
    sys.stderr = open(_ld / "window-leak-hook.stderr.log", "a", buffering=1, encoding="utf-8")
# ========================================================================================

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"
PID_FILE = STATE / "window-leak-hook.pid"
LOG = STATE / "logs" / f"window-leak-hook-{dt.date.today().isoformat()}.log"

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

EVENT_OBJECT_SHOW = 0x8002
WINEVENT_OUTOFCONTEXT = 0x0000
WINEVENT_SKIPOWNPROCESS = 0x0002
SW_HIDE = 0
OBJID_WINDOW = 0
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
TH32CS_SNAPPROCESS = 0x00000002
ERROR_ALREADY_EXISTS = 183

CONSOLE_HOST = {"windowsterminal.exe", "openconsole.exe", "conhost.exe"}
SERVICE_ROOTS = {"svchost.exe", "services.exe", "wininit.exe"}


def _log(msg: str) -> None:
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(f"[{dt.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")
    except Exception:
        pass


# === fast image-name lookup (no subprocess) =============================================
kernel32.OpenProcess.restype = wt.HANDLE
kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
kernel32.QueryFullProcessImageNameW.restype = wt.BOOL
kernel32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]
kernel32.CloseHandle.argtypes = [wt.HANDLE]


def _image_name(pid: int) -> str:
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    try:
        size = wt.DWORD(260)
        buf = ctypes.create_unicode_buffer(260)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value).lower()
        return ""
    finally:
        kernel32.CloseHandle(h)


def _full_image_path(pid: int) -> str:
    """Full image path (not just basename) -- used for leak-attribution reporting only,
    on the (already-open) toolhelp snapshot's pid list. Never called before SW_HIDE."""
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    try:
        size = wt.DWORD(1024)
        buf = ctypes.create_unicode_buffer(1024)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return buf.value
        return ""
    finally:
        kernel32.CloseHandle(h)


# === leak attribution (2026-09-05, GOAL-SILENT-RIG S3) ==================================
# "A leak can never again be silent for days" -- record, next to every HID line, which
# console-subsystem processes were CREATED in the 3s before the hide. No `wmi`/`pywin32`
# package is installed in this venv (checked live this session), so attribution uses the
# toolhelp snapshot this file already takes for _parent_map() + GetProcessTimes (pure
# ctypes, zero subprocess spawns) rather than a WMIC child process -- keeps the hide path
# fast and never blocks or delays the SW_HIDE call, which always runs first.
class _FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wt.DWORD), ("dwHighDateTime", wt.DWORD)]


kernel32.GetProcessTimes.restype = wt.BOOL
kernel32.GetProcessTimes.argtypes = [
    wt.HANDLE, ctypes.POINTER(_FILETIME), ctypes.POINTER(_FILETIME),
    ctypes.POINTER(_FILETIME), ctypes.POINTER(_FILETIME),
]

_FILETIME_EPOCH_OFFSET = 11644473600  # seconds between 1601-01-01 and 1970-01-01


def _filetime_to_unix(ft: "_FILETIME") -> float:
    ticks = (ft.dwHighDateTime << 32) | ft.dwLowDateTime
    return ticks / 10_000_000 - _FILETIME_EPOCH_OFFSET


def _process_create_time(pid: int) -> "float | None":
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return None
    try:
        creation, exit_, kernel_, user_ = _FILETIME(), _FILETIME(), _FILETIME(), _FILETIME()
        if kernel32.GetProcessTimes(h, ctypes.byref(creation), ctypes.byref(exit_),
                                    ctypes.byref(kernel_), ctypes.byref(user_)):
            return _filetime_to_unix(creation)
        return None
    except Exception:
        return None
    finally:
        kernel32.CloseHandle(h)


def _attribute_recent_processes(pm: dict, within_seconds: float = 3.0) -> list[dict]:
    """Among the already-open toolhelp snapshot's processes, which were CREATED within the
    last `within_seconds`? Those are the likely spawn behind the just-hidden window. Called
    AFTER ShowWindow(SW_HIDE) in _handle_show -- attribution never delays the hide itself."""
    now = time.time()
    out: list[dict] = []
    for pid, (name, ppid) in pm.items():
        ct = _process_create_time(pid)
        if ct is None:
            continue
        age = now - ct
        if age < 0 or age > within_seconds:
            continue
        parent_name = pm.get(ppid, ("?", 0))[0]
        out.append({
            "pid": pid, "name": name, "parent": parent_name,
            "image": _full_image_path(pid) or name,
        })
    return out


# === proc_trace.py cross-reference (2026-09-05, GOAL-SILENT-RIG R4a) ====================
# _attribute_recent_processes() above can only name a process that is STILL ALIVE in the
# toolhelp snapshot taken right after a hide -- a short-lived process whose PARENT already
# exited by the time the hide fires shows up as "(parent=?)" (exactly the live 14:00:0x
# incident: 4 pythonw.exe entries, no parent nameable). proc_trace.py records EVERY process
# creation the instant it happens (WMI eventing, not polling) with the parent's name/cmdline
# looked up IMMEDIATELY, to automation/state/logs/proc-trace-<date>.jsonl -- this reads the
# last `within_seconds` of THAT file as a second, richer attribution source. Bounded (only
# tails the last _PROC_TRACE_TAIL_BYTES of the file, never a full-file read) and wrapped in
# its own try/except at the call site so a missing/corrupt/huge trace file can never delay
# or crash a hide -- the hide + the toolhelp-based attribution above always run first.
_PROC_TRACE_TAIL_BYTES = 256 * 1024


def _proc_trace_path_for_date(d: dt.date, log_dir: Path = STATE / "logs") -> Path:
    """PURE: mirrors proc_trace.py's own _log_path_for_date naming convention -- duplicated
    here (rather than imported) so this file never depends on proc_trace.py's import-time
    side effects (log-dir creation, headless stdio redirect) just to read its output."""
    return log_dir / f"proc-trace-{d.isoformat()}.jsonl"


def _read_recent_proc_trace_events(within_seconds: float = 2.0,
                                    now: "float | None" = None,
                                    log_dir: Path = STATE / "logs") -> list[dict]:
    """Tail the last _PROC_TRACE_TAIL_BYTES of today's (and, near midnight, yesterday's)
    proc-trace-<date>.jsonl and return the parsed rows whose ts_local falls within the last
    `within_seconds` of `now` (real time.time() if not given). Returns [] on any error
    (missing file, corrupt JSON, proc_trace.py not running) -- fail-open, this is a
    best-effort second attribution source, never a hide-path dependency."""
    now = now if now is not None else time.time()
    now_ms = now * 1000.0
    window_ms = within_seconds * 1000.0
    out: list[dict] = []
    for d in (dt.date.today(), dt.date.today() - dt.timedelta(days=1)):
        path = _proc_trace_path_for_date(d, log_dir=log_dir)
        try:
            if not path.exists():
                continue
            size = path.stat().st_size
            with path.open("rb") as f:
                if size > _PROC_TRACE_TAIL_BYTES:
                    f.seek(size - _PROC_TRACE_TAIL_BYTES)
                data = f.read().decode("utf-8", errors="ignore")
            for raw in data.splitlines():
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    row = json.loads(raw)
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue
                if not isinstance(row, dict) or "ts_local" not in row:
                    continue
                try:
                    ts = float(row["ts_local"])
                except (TypeError, ValueError):
                    continue
                age_ms = now_ms - ts
                if 0 <= age_ms <= window_ms:
                    out.append(row)
        except Exception:
            continue  # fail-open: a bad day's trace file must never block another day's
    out.sort(key=lambda r: r.get("ts_local", 0))
    return out


def _format_proc_trace_chain(events: list[dict], limit: int = 5) -> str:
    """PURE: render a bounded list of proc_trace rows as one human-readable parent-chain
    string for the HID log line -- name+cmdline for the process AND its parent (the whole
    point: a dead parent is still named here, since proc_trace.py looked it up at creation
    time, not after the fact)."""
    if not events:
        return "none"
    parts = []
    for r in events[:limit]:
        name = r.get("name") or "?"
        cmd = r.get("cmdline") or ""
        pname = r.get("parent_name") or "?"
        pcmd = r.get("parent_cmdline") or ""
        parts.append(f'{name} (cmd="{cmd}") <- parent {pname} (cmd="{pcmd}")')
    return "; ".join(parts)


_leak_sources: "collections.Counter[str]" = collections.Counter()
_hidden_today = 0
_flush_date = dt.date.today()


def _flush_daily_summary(for_date: dt.date, hidden_count: int,
                          sources: "collections.Counter[str]") -> None:
    """Write ONE 'WINDOW-LEAK: N windows hidden, top sources: ...' line to STATUS.md's
    Known-broken section via the shared de-duplicating upsert helper, when hidden_count > 0.
    Fail-open by design (status_known_broken.upsert already fails open; this wraps the
    import too) -- a broken STATUS.md write must never crash the hider."""
    if hidden_count <= 0:
        return
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import status_known_broken as skb  # noqa: PLC0415
    except Exception as ex:
        _log(f"daily summary: status_known_broken unavailable: {ex}")
        return
    top = sources.most_common(5)
    top_str = ", ".join(f"{img} x{n}" for img, n in top) if top else "unattributed"
    line = (f"- [{dt.datetime.now():%Y-%m-%dT%H:%M} ET] WINDOW-LEAK: {hidden_count} windows "
            f"hidden, top sources: {top_str}")
    try:
        skb.upsert("WINDOW-LEAK:", line)
        _log(f"daily summary flushed for {for_date.isoformat()}: {line}")
    except Exception as ex:
        _log(f"daily summary: upsert failed: {ex}")


def _maybe_flush_daily_summary() -> None:
    """Called opportunistically (on every hide, and on an hourly WM_TIMER so a quiet day
    after a leaky one still flushes) -- rolls the day over and flushes the PREVIOUS day's
    summary exactly once."""
    global _flush_date, _hidden_today, _leak_sources
    today = dt.date.today()
    if today == _flush_date:
        return
    _flush_daily_summary(_flush_date, _hidden_today, _leak_sources)
    _flush_date = today
    _hidden_today = 0
    _leak_sources = collections.Counter()


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wt.DWORD),
        ("cntUsage", wt.DWORD),
        ("th32ProcessID", wt.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID", wt.DWORD),
        ("cntThreads", wt.DWORD),
        ("th32ParentProcessID", wt.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wt.DWORD),
        ("szExeFile", ctypes.c_wchar * 260),
    ]


def _parent_map() -> dict:
    """{pid: (image_name_lower, ppid)} from a single toolhelp snapshot."""
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    m: dict = {}
    if not snap or snap == wt.HANDLE(-1).value:
        return m
    try:
        e = PROCESSENTRY32W()
        e.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        if not kernel32.Process32FirstW(snap, ctypes.byref(e)):
            return m
        while True:
            m[int(e.th32ProcessID)] = (e.szExeFile.lower(), int(e.th32ParentProcessID))
            if not kernel32.Process32NextW(snap, ctypes.byref(e)):
                break
    finally:
        kernel32.CloseHandle(snap)
    return m


def _service_rooted(pid: int, pm: dict) -> bool:
    """Mirror of window-leak-detector._is_service_rooted: explorer-rooted = safe (J's own),
    svchost/services/wininit in the first 4 hops = Task-Scheduler/Session-0 leak."""
    names = []
    cur = pid
    for _ in range(4):
        info = pm.get(cur)
        if not info:
            break
        names.append(info[0])
        cur = info[1]
        if cur == 0:
            break
    if "explorer.exe" in names:
        return False
    return any(n in SERVICE_ROOTS for n in names)


GetWindowThreadProcessId = user32.GetWindowThreadProcessId
GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
ShowWindow = user32.ShowWindow
ShowWindow.argtypes = [wt.HWND, ctypes.c_int]

WinEventProcType = ctypes.WINFUNCTYPE(
    None, wt.HANDLE, wt.DWORD, wt.HWND, wt.LONG, wt.LONG, wt.DWORD, wt.DWORD
)

_hidden = 0


def _handle_show(hHook, event, hwnd, idObject, idChild, thread, ts):
    global _hidden, _hidden_today
    try:
        if idObject != OBJID_WINDOW or not hwnd:
            return
        pid = wt.DWORD()
        GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        p = int(pid.value)
        if not p:
            return
        name = _image_name(p)
        if name not in CONSOLE_HOST:
            return  # cheap path: not a console host -> ignore
        pm = _parent_map()
        if _service_rooted(p, pm):
            # HIDE FIRST -- attribution below never delays or blocks the hide itself.
            ShowWindow(hwnd, SW_HIDE)
            _hidden += 1
            _hidden_today += 1
            try:
                recent = _attribute_recent_processes(pm)
            except Exception as ex:
                recent = []
                _log(f"attribution error (hide already applied): {ex}")
            for r in recent:
                _leak_sources[r["image"]] += 1
            attrib = "; ".join(f"{r['image']} (parent={r['parent']})" for r in recent[:5]) or "none"
            try:
                trace_events = _read_recent_proc_trace_events(within_seconds=2.0)
            except Exception as ex:
                trace_events = []
                _log(f"proc_trace read error (hide already applied): {ex}")
            proc_trace_chain = _format_proc_trace_chain(trace_events)
            _log(f"HID #{_hidden} hwnd={int(hwnd)} pid={p} img={name} recent_procs=[{attrib}] "
                 f"proc_trace=[{proc_trace_chain}]")
            _maybe_flush_daily_summary()
    except Exception as ex:  # never let a callback crash the hook
        _log(f"cb error: {ex}")


_CB = WinEventProcType(_handle_show)  # keep a ref alive for the process lifetime


def main() -> int:
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / "logs").mkdir(parents=True, exist_ok=True)

    # Singleton: named mutex auto-releases on process death -> no PID-reuse foot-gun.
    kernel32.CreateMutexW.restype = wt.HANDLE
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.LPCWSTR]
    _mutex = kernel32.CreateMutexW(None, False, "Global\\GammaWindowLeakHookSingleton")
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        _log("sibling hook already running -> exiting")
        return 0

    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")

    SetWinEventHook = user32.SetWinEventHook
    SetWinEventHook.restype = wt.HANDLE
    SetWinEventHook.argtypes = [
        wt.DWORD, wt.DWORD, wt.HMODULE, WinEventProcType, wt.DWORD, wt.DWORD, wt.DWORD
    ]
    hook = SetWinEventHook(
        EVENT_OBJECT_SHOW, EVENT_OBJECT_SHOW, None, _CB,
        0, 0, WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS,
    )
    if not hook:
        _log(f"FATAL: SetWinEventHook failed err={ctypes.get_last_error()}")
        return 1
    _log(f"hook installed pid={os.getpid()}")

    # Hourly WM_TIMER: closes the gap where a leaky day is followed by a fully quiet one --
    # _maybe_flush_daily_summary() otherwise only runs opportunistically on a hide, so a
    # summary could sit unflushed indefinitely if nothing leaks after midnight.
    WM_TIMER = 0x0113
    _DAILY_FLUSH_TIMER_ID = 1
    user32.SetTimer(None, _DAILY_FLUSH_TIMER_ID, 60 * 60 * 1000, None)

    # Standard Win32 message loop -- required to receive OUTOFCONTEXT events.
    GetMessageW = user32.GetMessageW
    GetMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT]
    TranslateMessage = user32.TranslateMessage
    DispatchMessageW = user32.DispatchMessageW
    msg = wt.MSG()
    while True:
        ret = GetMessageW(ctypes.byref(msg), None, 0, 0)
        if ret == 0 or ret == -1:
            break
        if msg.message == WM_TIMER and msg.wParam == _DAILY_FLUSH_TIMER_ID:
            try:
                _maybe_flush_daily_summary()
            except Exception as ex:
                _log(f"timer flush error: {ex}")
        TranslateMessage(ctypes.byref(msg))
        DispatchMessageW(ctypes.byref(msg))

    user32.UnhookWinEvent(hook)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
