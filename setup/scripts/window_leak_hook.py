"""Event-driven window-leak hider for Project Gamma (instant, pre-paint).

Complements the polling window-leak-detector.py: a SetWinEventHook on
EVENT_OBJECT_SHOW fires the instant a window becomes visible, so a leaked
service-rooted console-host window (WindowsTerminal -Embedding / conhost /
OpenConsole) is SW_HIDE'd within a frame of appearing -- effectively never
seen. Hide-only, never kills the underlying pythonw work process.

Safety gate, UPDATED 2026-09-15: only ever hides windows whose ancestry is
svchost/services/wininit-rooted (Task Scheduler / Session 0), NEVER a window
descending from explorer.exe, AND (fixed 2026-09-15 -- this hook previously
never consulted it at all) never a window matching
automation/state/window-leak-allowlist.json (image_names/title_substrings/
pids, reloaded on mtime change, mirroring window-leak-detector.py's
_is_allowed). Games/apps aren't console-host images so they're untouched.

WindowsTerminal.exe / OpenConsole.exe are structurally EXCLUDED from the
hide-eligible set (see CONSOLE_HOST_HIDE_ELIGIBLE below) -- they are still
watched/logged but never ShowWindow(SW_HIDE)'d. Root cause: modern Windows
Terminal's DCOM-activation ancestry is byte-identical for J's own terminal
and a Task-Scheduler leak (verified live 2026-09-15, see
window-leak-allowlist.json's _why_windows_powershell for the full writeup),
so ancestry+title can never safely single one out. This is what hid J's
interactive PowerShell on 2026-09-15 ("powershell closes immediately when I
open it") -- HID #40-44 in window-leak-hook-2026-09-14.log, pid 23376.

Fail-open: if the allowlist file is missing or unreadable/corrupt, this hook
does NOT hide anything that session -- it logs loudly and skips the hide.
A hidden terminal J cannot use is worse than a visible leak.

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

# CONSOLE_HOST = watched for logging/attribution (all 3 console-host images).
# CONSOLE_HOST_HIDE_ELIGIBLE = the subset ShowWindow(SW_HIDE) may ever be called on.
#
# 2026-09-15 SAFETY FIX: windowsterminal.exe / openconsole.exe REMOVED from the
# hide-eligible set. Empirical check of window-leak-hook-2026-09-14.log: of every HID
# line ever written, 52 were windowsterminal.exe and 1 was openconsole.exe -- ZERO were
# a bare conhost.exe. That means auto-hide has, in practice, only ever fired on the one
# image this box cannot safely attribute (WT's DCOM-activation ancestry is identical for
# J's own terminal and a Task-Scheduler leak -- see window-leak-allowlist.json's
# _why_windows_powershell for the live verification). A legacy conhost.exe window IS
# still explorer-rooted when J opens it directly (no DCOM activation involved for the
# classic console host), so ancestry stays a valid, non-ambiguous signal for THAT image
# only. Per OP-0 safety framing: a hidden terminal J cannot use is worse than a visible
# leak, so WT/OpenConsole are watched (logged) but never hidden; only conhost.exe remains
# hide-eligible, and even then only after the allowlist below clears it.
CONSOLE_HOST = {"windowsterminal.exe", "openconsole.exe", "conhost.exe"}
CONSOLE_HOST_HIDE_ELIGIBLE = {"conhost.exe"}
SERVICE_ROOTS = {"svchost.exe", "services.exe", "wininit.exe"}

# === allowlist (2026-09-15 fix -- this hook never consulted this file before) ===========
# Mirrors window-leak-detector.py's _load_allowlist/_is_allowed exactly (kept as a literal
# port rather than a cross-file import so this long-running process never takes an
# import-time dependency on the poller script's module-load side effects; a dedicated
# pinning test -- test_window_leak_hook_matches_detector_allowlist_logic -- keeps the two
# implementations behaviorally identical). Reloaded whenever the file's mtime changes,
# since this process runs for hours/days between restarts.
ALLOWLIST_FILE = STATE / "window-leak-allowlist.json"
# Images a TITLE-substring allowlist may exempt (2026-08-13 detector SCOPE FIX, mirrored
# here). A console host inherits its parent's title, so a title match is only trusted for
# the app's OWN window image -- never a console host that merely inherited the title.
# Lowercase (unlike the detector's mixed-case set) because _image_name() above always
# lowercases its result -- kept case-insensitive so an allowlist edit in either case works.
TITLE_ALLOWLIST_IMAGES = {"windowsterminal.exe"}

GetWindowTextW = user32.GetWindowTextW
GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
GetWindowTextW.restype = ctypes.c_int
GetWindowTextLengthW = user32.GetWindowTextLengthW
GetWindowTextLengthW.argtypes = [wt.HWND]
GetWindowTextLengthW.restype = ctypes.c_int


def _window_title(hwnd) -> str:
    try:
        length = GetWindowTextLengthW(hwnd)
        if length == 0:
            return ""
        buf = ctypes.create_unicode_buffer(length + 1)
        GetWindowTextW(hwnd, buf, length + 1)
        return buf.value
    except Exception:
        return ""


_allow_cache: "dict | None" = None
_allow_mtime: "float | None" = None
_allow_load_failed_logged = False


def _load_allowlist() -> "dict | None":
    """Returns the parsed allowlist dict, or None on any failure (missing file, corrupt
    JSON, unreadable). None is a distinct, fail-OPEN-for-J signal from the caller's
    perspective: _handle_show treats None as "cannot prove this hide is safe -> skip the
    hide, log loudly" rather than falling back to an empty/default allowlist that would
    silently permit hides. Cached and reloaded only when the file's mtime changes."""
    global _allow_cache, _allow_mtime, _allow_load_failed_logged
    try:
        st = ALLOWLIST_FILE.stat()
    except Exception as ex:
        if not _allow_load_failed_logged:
            _log(f"ALLOWLIST MISSING/UNSTATABLE ({ex}) -- fail-open: no hides until it "
                 f"reappears at {ALLOWLIST_FILE}")
            _allow_load_failed_logged = True
        _allow_cache = None
        _allow_mtime = None
        return None
    if _allow_cache is not None and _allow_mtime == st.st_mtime:
        return _allow_cache
    try:
        data = json.loads(ALLOWLIST_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("allowlist root is not a JSON object")
        _allow_cache = data
        _allow_mtime = st.st_mtime
        _allow_load_failed_logged = False
        _log(f"allowlist (re)loaded mtime={st.st_mtime}")
        return data
    except Exception as ex:
        _log(f"ALLOWLIST CORRUPT ({ex}) -- fail-open: no hides until it is fixed at "
             f"{ALLOWLIST_FILE}")
        _allow_cache = None
        _allow_mtime = None
        return None


def _is_allowed(image_name: str, title: str, pid: int, allow: dict) -> bool:
    """Port of window-leak-detector.py's _is_allowed -- see that file's
    TITLE_ALLOWLIST_IMAGES comment for why title matches are scoped to the app's own
    window image rather than trusted for every console host. `image_name` here is always
    lowercase (this hook's _image_name() convention), so comparisons are lowercased on
    both sides for case-insensitive parity with the detector's mixed-case set/allowlist."""
    image_names_allow = {str(x).lower() for x in allow.get("image_names", [])}
    if image_name.lower() in image_names_allow:
        return True
    if pid in allow.get("pids", []):
        return True
    if image_name.lower() in TITLE_ALLOWLIST_IMAGES:
        for sub in allow.get("title_substrings", []):
            if sub and sub.lower() in title.lower():
                return True
    return False


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


def _decide(name: str, title: str, pid: int, pm: dict, allow: "dict | None") -> tuple[bool, str]:
    """PURE decision core of _handle_show -- given an already-console-host image name,
    its window title, pid, the process/parent map, and the loaded allowlist (or None for
    "unavailable"), returns (should_hide, reason). Extracted so the hide/no-hide policy
    is unit-testable without any live Win32 window/process -- see
    test_window_leak_hook.py. Callers must have already confirmed `name in CONSOLE_HOST`
    before calling this."""
    if name not in CONSOLE_HOST_HIDE_ELIGIBLE:
        return False, "not-hide-eligible (WindowsTerminal/OpenConsole, 2026-09-15 fix)"
    if not _service_rooted(pid, pm):
        return False, "explorer-rooted"
    if allow is None:
        return False, "allowlist-unavailable-fail-open"
    if _is_allowed(name, title, pid, allow):
        return False, "allowlisted"
    return True, "service-rooted-not-allowlisted"


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
        if not _service_rooted(p, pm):
            return  # explorer-rooted -> definitely J's own window, no log needed
        title = _window_title(hwnd)
        allow = _load_allowlist() if name in CONSOLE_HOST_HIDE_ELIGIBLE else None
        should_hide, reason = _decide(name, title, p, pm, allow)
        if not should_hide:
            _log(f"SKIP HIDE ({reason}) pid={p} img={name} title={title!r}")
            return
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
        _log(f"HID #{_hidden} hwnd={int(hwnd)} pid={p} img={name} title={title!r} "
             f"recent_procs=[{attrib}] proc_trace=[{proc_trace_chain}]")
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
