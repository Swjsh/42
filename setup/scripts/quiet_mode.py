"""Quiet Mode -- after-hours blackout so the rig never touches J's machine.

J directive 2026-08-24: "everything needs to be turned off after market hours."
Popups and a 4-worker backtest grind pegging four cores were landing on top of
his gaming session. This is the standing instrument that retires the question.

WHAT IT DOES, in the quiet window (weekday 18:00-23:00 ET, plus weekend 08:00-23:00;
23:00-08:00 is a LOUD maintenance band -- see the band comment below):
  * Disables every non-essential Gamma_* scheduled task, recording each one's
    prior state first so restore is exact.
  * Stops the Kitchen daemon and any project-owned worker pool it spawned, so no
    CPU-heavy grind survives.
  * Leaves the ESSENTIAL set running -- see ESSENTIAL below.

FAIL-OPEN BY DOCTRINE (OP-25). Any error path restores rather than leaving the
rig disabled: a quiet mode that silently eats J's trading day is worse than a
popup. `--enforce` outside the quiet window ALWAYS restores, and the restore is
idempotent, so a crash mid-blackout self-heals on the next 5-minute fire.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

# === HEADLESS STDIO REDIRECT (OP-27 L41 layer 3) ========================================
# Under pythonw.exe there is no console, so bare print() raises and takes the whole
# process down before anything reaches the log -- verified live 2026-08-24, the scheduled
# task exited 1 in under a second having written nothing at all.
if os.path.basename(sys.executable).lower().startswith("pythonw"):
    _log_dir = Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    sys.stdout = open(_log_dir / "quiet-mode.stdout.log", "a", buffering=1, encoding="utf-8")
    sys.stderr = open(_log_dir / "quiet-mode.stderr.log", "a", buffering=1, encoding="utf-8")
# ========================================================================================

ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "automation" / "state"
RESTORE_FILE = STATE_DIR / "quiet-mode-restore.json"
STATUS_FILE = STATE_DIR / "quiet-mode.json"
HOLD_FILE = STATE_DIR / "quiet-hold.json"
LOG_FILE = STATE_DIR / "quiet-mode.log"

# ET comes from et_clock, never zoneinfo: this box runs Mountain time, and the system
# Python has no tzdata, so ZoneInfo("America/New_York") raises at import under the
# scheduled task's interpreter (verified live 2026-08-24 -- exit 1, nothing logged).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from et_clock import ET_TZ as ET  # noqa: E402

# The blackout exists to keep the rig off J's EVENING (popups + a 4-worker grind on
# top of his gaming session). It was never meant to be a 16-hour outage.
#
# 2026-08-26 STARVATION FIX. The original 16:00->08:00 window disabled 68 tasks whose
# ONLY trigger falls inside that window -- the entire EOD pipeline, the nightly guard
# suite, the GitHub secrets audit, unattended-health itself. Those tasks could never
# run again: quiet mode disabled them before their trigger time and restored them
# after it, every single night, silently. Two bands fix it without touching J's evening:
#   * a post-close GRACE to 18:00 so the 16:00-17:45 EOD chain completes, and
#   * a LOUD MAINTENANCE band 23:00->08:00, when J is asleep and a popup costs nothing,
#     so the nightly safety/learning layer runs.
QUIET_START_HOUR = 18       # 18:00 ET -- after the EOD chain has finished writing
MAINTENANCE_START_HOUR = 23  # 23:00 ET -- blackout lifts, nightly work runs
MAINTENANCE_END_HOUR = 8     # 08:00 ET -- when Gamma_LaunchTV opens the trading day

# Tasks that stay alive even in the blackout.
#   - the trading chain, so a market day is never lost to quiet mode
#   - the window-leak detector, which IS the popup guard
#   - quiet mode itself, or it could never restore
ESSENTIAL = {
    "Gamma_QuietMode",
    "Gamma_WindowLeakDetectorKeepalive",
    # Cockpit action-cards/army-view fire path (build spec sec 4/7 step 8, 2026-08-29) posts
    # to the companion at :4317 -- disabling it mid-quiet-window silently breaks that path
    # with no error surfaced to J (the click just does nothing). Node process, $0, read-only
    # liveness probe -- no reason to hold it down like the LLM/CPU producers below.
    "Gamma_CompanionKeepalive",
    "Gamma_LaunchTV",
    "Gamma_TvWatchdog",
    "Gamma_Premarket",
    "Gamma_PremarketReadiness",
    "Gamma_PreopenReadiness",
    "Gamma_ScoutPremarket",
    "Gamma_OpenBellStatus",
    "Gamma_HeartbeatCore",
    "Gamma_Heartbeat",
    "Gamma_Heartbeat_Aggressive",
    "Gamma_SightBeacon",
    "Gamma_MarketKeepAwake",
    "Gamma_EodFlatten",
    "Gamma_EodFlatten_Aggressive",
    "Gamma_EodFlattenCore",
}

# Command-line substrings identifying project-owned CPU hogs to stop in the blackout.
HEAVY_PROCESS_MARKERS = (
    "kitchen_daemon.py",
    "autoresearch.",
    "multiprocessing-fork",
    "shotgun_scalper",
    "_grind",
)

NO_WINDOW = 0x08000000
STATE_READY = "3"  # TASK_STATE: 1=Disabled 2=Queued 3=Ready 4=Running


def _log(msg: str) -> None:
    line = f"{dt.datetime.now(ET).isoformat()} {msg}"
    # The file is the durable record; the console is a nicety. Never let a dead
    # stdout stop the log line from landing on disk.
    try:
        print(line, flush=True)
    except (OSError, ValueError, AttributeError):
        pass
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def _ps(script: str) -> str:
    """Run PowerShell and return stdout. Raises on non-zero exit."""
    out = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, timeout=180, creationflags=NO_WINDOW,
    )
    if out.returncode != 0:
        raise RuntimeError(f"powershell failed: {out.stderr.strip()[:400]}")
    return out.stdout


def in_quiet_window(now: dt.datetime | None = None) -> bool:
    """True when the rig must stay off J's machine.

    Bands, in precedence order:
      23:00-08:00 any day  -> LOUD  (maintenance: J is asleep, nightly work runs)
      weekend              -> quiet
      weekday 18:00-23:00  -> quiet (J's evening)
      weekday 08:00-18:00  -> LOUD  (trading day + the post-close EOD chain)
    """
    now = now or dt.datetime.now(ET)
    hour = now.hour
    # Maintenance band wins over everything, weekends included: a nightly guard that
    # only runs Mon-Fri is a guard that misses every weekend regression.
    if hour >= MAINTENANCE_START_HOUR or hour < MAINTENANCE_END_HOUR:
        return False
    if now.weekday() >= 5:  # weekend daytime + evening stays quiet
        return True
    return hour >= QUIET_START_HOUR


def _gamma_tasks() -> dict[str, str]:
    raw = _ps(
        "Get-ScheduledTask | Where-Object {$_.TaskName -like 'Gamma*'} | "
        "Select-Object TaskName,State | ConvertTo-Json -Depth 3 -Compress"
    ).strip()
    if not raw:
        return {}
    data = json.loads(raw)
    if isinstance(data, dict):
        data = [data]
    return {r["TaskName"]: str(r["State"]) for r in data}


def _set_tasks(names: list[str], enable: bool) -> int:
    if not names:
        return 0
    verb = "Enable-ScheduledTask" if enable else "Disable-ScheduledTask"
    ok = 0
    # Chunk so one bad name cannot poison the whole batch.
    for start in range(0, len(names), 25):
        chunk = names[start:start + 25]
        quoted = ",".join("'" + n.replace("'", "''") + "'" for n in chunk)
        script = (
            "foreach($n in @(" + quoted + ")){ try{ " + verb + " -TaskName $n "
            "-ErrorAction Stop | Out-Null; 'OK' } catch { 'FAIL' } }"
        )
        try:
            ok += _ps(script).count("OK")
        except Exception as exc:  # noqa: BLE001 -- surfaced, never swallowed
            _log(f"WARN task batch {verb} failed: {exc}")
    return ok


def _load_restore_list() -> list[str]:
    if not RESTORE_FILE.exists():
        return []
    try:
        return list(json.loads(RESTORE_FILE.read_text(encoding="utf-8")).get("restore_to_ready", []))
    except (OSError, ValueError) as exc:
        _log(f"WARN unreadable restore file ({exc}) -- treating as empty")
        return []


def _save_restore_list(names: list[str]) -> None:
    RESTORE_FILE.write_text(json.dumps({
        "recorded_at": dt.datetime.now(ET).isoformat(),
        "restore_to_ready": sorted(set(names)),
    }, indent=2), encoding="utf-8")


def _stop_heavy_processes() -> list[str]:
    """Kill project-owned CPU hogs. Never touches anything outside the repo path."""
    script = (
        "Get-CimInstance Win32_Process -Filter \"Name like '%python%'\" | "
        "Select-Object ProcessId,CommandLine | ConvertTo-Json -Depth 3 -Compress"
    )
    try:
        raw = _ps(script).strip()
    except Exception as exc:  # noqa: BLE001
        _log(f"WARN could not enumerate processes: {exc}")
        return []
    if not raw:
        return []
    rows = json.loads(raw)
    if isinstance(rows, dict):
        rows = [rows]

    me = os.getpid()
    root = str(ROOT)
    killed: list[str] = []
    for row in rows:
        cl = row.get("CommandLine") or ""
        pid = row.get("ProcessId")
        if pid == me or not cl:
            continue
        # Two-part gate: must belong to this repo AND look like heavy R&D.
        # multiprocessing workers carry no repo path, so they match by marker alone.
        if root not in cl and "multiprocessing-fork" not in cl:
            continue
        if not any(m in cl for m in HEAVY_PROCESS_MARKERS):
            continue
        try:
            subprocess.run(["taskkill", "/PID", str(pid), "/F", "/T"],
                           capture_output=True, timeout=30, creationflags=NO_WINDOW)
            killed.append(f"{pid}:{cl[:70]}")
        except Exception as exc:  # noqa: BLE001
            _log(f"WARN kill {pid} failed: {exc}")
    return killed


# === PRESENCE GATE (J 2026-08-29) =======================================================
# The 23:00 ET maintenance band assumes J is asleep. On 2026-08-29 at 23:30 ET he was
# gaming: the blackout lifted, ~68 tasks fired at once, and two of them flashed a console
# window that stole focus mid-match. The clock was never the real constraint -- "is J at
# the machine" is. This holds the blackout while a fullscreen app owns the foreground.
#
# FAIL-OPEN: every path here returns "no hold" on error, so a broken detector degrades to
# exactly the clock-only behaviour that shipped before it.
GWL_STYLE = -16
WS_CAPTION = 0x00C00000
WS_THICKFRAME = 0x00040000


def _foreground_fullscreen() -> str | None:
    """Return the foreground exe name if it is genuinely fullscreen, else None.

    The discriminator is window STYLE, not size. A merely MAXIMISED window (browser,
    terminal, editor) keeps WS_CAPTION/WS_THICKFRAME and its rect also covers the
    monitor -- matching on geometry alone would hold the blackout forever and starve
    the nightly maintenance band. Fullscreen and borderless-fullscreen games drop both
    styles, which is what this tests.
    """
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None

        style = user32.GetWindowLongW(hwnd, GWL_STYLE)
        if style & (WS_CAPTION | WS_THICKFRAME):
            return None  # framed window -> not a fullscreen app

        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return None

        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                        ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        mon = user32.MonitorFromWindow(hwnd, 2)  # MONITOR_DEFAULTTONEAREST
        if not user32.GetMonitorInfoW(mon, ctypes.byref(mi)):
            return None
        m = mi.rcMonitor
        if (rect.left, rect.top, rect.right, rect.bottom) != (m.left, m.top, m.right, m.bottom):
            return None

        # Name it for the log -- diagnosing "why did quiet mode hold" needs the culprit.
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        name = f"pid {pid.value}"
        try:
            kernel32 = ctypes.windll.kernel32
            h = kernel32.OpenProcess(0x1000, False, pid.value)  # QUERY_LIMITED_INFORMATION
            if h:
                buf = ctypes.create_unicode_buffer(512)
                size = wintypes.DWORD(512)
                if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                    name = os.path.basename(buf.value) or name
                kernel32.CloseHandle(h)
        except Exception:  # noqa: BLE001 -- naming is a nicety, the hold is the point
            pass
        return name
    except Exception as exc:  # noqa: BLE001
        _log(f"WARN fullscreen probe failed ({exc}) -- no presence hold")
        return None


def _manual_hold() -> str | None:
    """Honour an explicit `--hold` until its expiry."""
    if not HOLD_FILE.exists():
        return None
    try:
        until = dt.datetime.fromisoformat(
            json.loads(HOLD_FILE.read_text(encoding="utf-8"))["until"])
    except (OSError, ValueError, KeyError) as exc:
        _log(f"WARN unreadable hold file ({exc}) -- clearing")
        HOLD_FILE.unlink(missing_ok=True)
        return None
    if dt.datetime.now(ET) >= until:
        HOLD_FILE.unlink(missing_ok=True)
        return None
    return f"manual hold until {until:%H:%M %Z}"


def _in_trading_band(now: dt.datetime | None = None) -> bool:
    """Weekday 08:00-18:00 ET. A presence hold must NEVER reach into the trading day."""
    now = now or dt.datetime.now(ET)
    return now.weekday() < 5 and MAINTENANCE_END_HOUR <= now.hour < QUIET_START_HOUR


def presence_hold(now: dt.datetime | None = None) -> str | None:
    """Reason to stay quiet despite the clock saying LOUD, or None."""
    if _in_trading_band(now):
        return None
    manual = _manual_hold()
    if manual:
        return manual
    app = _foreground_fullscreen()
    return f"fullscreen app in foreground ({app})" if app else None
# ========================================================================================


def _write_status(active: bool, detail: dict) -> None:
    STATUS_FILE.write_text(json.dumps({
        "quiet_active": active,
        "updated_at": dt.datetime.now(ET).isoformat(),
        "quiet_window_et": (
            f"weekday {QUIET_START_HOUR:02d}:00-{MAINTENANCE_START_HOUR:02d}:00 ET + weekend "
            f"{MAINTENANCE_END_HOUR:02d}:00-{MAINTENANCE_START_HOUR:02d}:00; "
            f"LOUD maintenance band {MAINTENANCE_START_HOUR:02d}:00-{MAINTENANCE_END_HOUR:02d}:00"
        ),
        **detail,
    }, indent=2), encoding="utf-8")


def go_quiet() -> int:
    tasks = _gamma_tasks()
    if not tasks:
        _log("ERROR no Gamma tasks enumerated -- refusing to act")
        return 1

    newly = [n for n, state in tasks.items()
             if n not in ESSENTIAL and state == STATE_READY]
    # Record BEFORE disabling, merged with anything a previous fire already took
    # down, so a crash mid-blackout still leaves an exact restore list on disk.
    _save_restore_list(_load_restore_list() + newly)

    disabled = _set_tasks(newly, enable=False)
    killed = _stop_heavy_processes()
    _log(f"QUIET ON: disabled={disabled}/{len(newly)} killed={len(killed)}")
    for k in killed:
        _log(f"  killed {k}")
    _write_status(True, {"disabled_now": disabled,
                         "total_held_down": len(_load_restore_list()),
                         "killed_count": len(killed)})
    return 0


def go_loud() -> int:
    names = _load_restore_list()
    if not names:
        _write_status(False, {"note": "nothing to restore"})
        return 0
    enabled = _set_tasks(names, enable=True)
    _log(f"QUIET OFF: re-enabled={enabled}/{len(names)}")
    if enabled == len(names):
        RESTORE_FILE.unlink(missing_ok=True)
    else:
        _log("WARN partial restore -- keeping restore file for the next fire")
    _write_status(False, {"restored_count": enabled, "expected": len(names)})
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="After-hours blackout enforcer")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--enforce", action="store_true", help="apply whatever the clock says")
    g.add_argument("--on", action="store_true", help="force quiet now")
    g.add_argument("--off", action="store_true", help="force restore now")
    g.add_argument("--hold", type=float, metavar="HOURS", nargs="?", const=4.0,
                   help="stay quiet for HOURS (default 4) regardless of the clock")
    g.add_argument("--release", action="store_true", help="clear a manual hold")
    g.add_argument("--status", action="store_true")
    args = ap.parse_args()

    if args.status:
        now = dt.datetime.now(ET)
        print(f"ET now      : {now:%Y-%m-%d %H:%M:%S %a}")
        print(f"quiet window: {in_quiet_window(now)}")
        print(f"presence hold: {presence_hold(now) or 'none'}")
        print(f"held down   : {len(_load_restore_list())} tasks")
        if STATUS_FILE.exists():
            print(STATUS_FILE.read_text(encoding="utf-8"))
        return 0

    try:
        if args.hold is not None:
            until = dt.datetime.now(ET) + dt.timedelta(hours=args.hold)
            HOLD_FILE.write_text(json.dumps({"until": until.isoformat()}, indent=2),
                                 encoding="utf-8")
            _log(f"HOLD set until {until.isoformat()}")
            return go_quiet()
        if args.release:
            HOLD_FILE.unlink(missing_ok=True)
            _log("HOLD cleared")
            return go_loud() if not in_quiet_window() else go_quiet()
        if args.on:
            return go_quiet()
        if args.off:
            HOLD_FILE.unlink(missing_ok=True)
            return go_loud()
        if in_quiet_window():
            return go_quiet()
        held = presence_hold()
        if held:
            _log(f"QUIET HELD past the clock: {held}")
            return go_quiet()
        return go_loud()
    except Exception as exc:  # noqa: BLE001
        # FAIL OPEN: never leave the rig disabled because the enforcer broke.
        _log(f"ERROR enforcer failed ({exc}) -- restoring")
        try:
            go_loud()
        except Exception as exc2:  # noqa: BLE001
            _log(f"FATAL restore also failed: {exc2}")
            return 2
        return 1


if __name__ == "__main__":
    sys.exit(main())
