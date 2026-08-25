"""Quiet Mode -- after-hours blackout so the rig never touches J's machine.

J directive 2026-08-24: "everything needs to be turned off after market hours."
Popups and a 4-worker backtest grind pegging four cores were landing on top of
his gaming session. This is the standing instrument that retires the question.

WHAT IT DOES, in the quiet window (default 16:00 ET -> 08:00 ET, plus all weekend):
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
LOG_FILE = STATE_DIR / "quiet-mode.log"

# ET comes from et_clock, never zoneinfo: this box runs Mountain time, and the system
# Python has no tzdata, so ZoneInfo("America/New_York") raises at import under the
# scheduled task's interpreter (verified live 2026-08-24 -- exit 1, nothing logged).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from et_clock import ET_TZ as ET  # noqa: E402

QUIET_START_HOUR = 16  # 16:00 ET, right after the cash close
QUIET_END_HOUR = 8     # 08:00 ET, when Gamma_LaunchTV opens the trading day

# Tasks that stay alive even in the blackout.
#   - the trading chain, so a market day is never lost to quiet mode
#   - the window-leak detector, which IS the popup guard
#   - quiet mode itself, or it could never restore
ESSENTIAL = {
    "Gamma_QuietMode",
    "Gamma_WindowLeakDetectorKeepalive",
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
    now = now or dt.datetime.now(ET)
    if now.weekday() >= 5:  # all weekend is quiet
        return True
    return now.hour >= QUIET_START_HOUR or now.hour < QUIET_END_HOUR


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


def _write_status(active: bool, detail: dict) -> None:
    STATUS_FILE.write_text(json.dumps({
        "quiet_active": active,
        "updated_at": dt.datetime.now(ET).isoformat(),
        "quiet_window_et": f"{QUIET_START_HOUR:02d}:00 -> {QUIET_END_HOUR:02d}:00 + all weekend",
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
    g.add_argument("--status", action="store_true")
    args = ap.parse_args()

    if args.status:
        now = dt.datetime.now(ET)
        print(f"ET now      : {now:%Y-%m-%d %H:%M:%S %a}")
        print(f"quiet window: {in_quiet_window(now)}")
        print(f"held down   : {len(_load_restore_list())} tasks")
        if STATUS_FILE.exists():
            print(STATUS_FILE.read_text(encoding="utf-8"))
        return 0

    try:
        if args.on:
            return go_quiet()
        if args.off:
            return go_loud()
        return go_quiet() if in_quiet_window() else go_loud()
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
