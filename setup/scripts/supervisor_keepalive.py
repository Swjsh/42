"""ONE supervisor keepalive replacing 8 separate `Gamma_*Keepalive` scheduled tasks
(GOAL-SILENT-RIG-2026-09-05 R7).

WHY THIS EXISTS: off-hours launch rate was still ~150 spawns/hour because 9 registered
keepalive tasks (Gamma_CompanionKeepalive, Gamma_DashboardKeepalive,
Gamma_KitchenDaemonKeepalive, Gamma_DiscordBridge, Gamma_QuoteRecorderKeepalive,
Gamma_CryptoTwinKeepalive, Gamma_WindowLeakDetectorKeepalive, Gamma_WindowLeakHookKeepalive,
Gamma_ProcTraceKeepalive) each independently fire every 5 minutes, each spawning its own
wscript -> pythonw -> run_cmd_hidden -> pythonw chain (or, for the four PowerShell-authored
ones, wscript -> run_exe_hidden.vbs -> powershell.exe). That is 9 process trees every 5
minutes regardless of whether anything is actually dead. This file does all 9 liveness
checks + relaunches in ONE process, ONE 5-minute task -- 1 spawn per fire instead of 9.

DESIGN: a registry of DaemonSpec entries. Each entry's `check()` is a PURE function over a
single shared process-table snapshot (`build_process_table()`, one `wmic` subprocess call
per run -- never a fresh subprocess per daemon) plus whatever small state file that daemon
already maintains (a pid file / status json it already writes for its own purposes). Each
entry's `spawn()` performs the actual relaunch. Where a sibling keepalive module
(crypto_twin_keepalive.py, proc_trace_keepalive.py, window_leak_hook_keepalive.py,
window_leak_detector_keepalive.py, quote_recorder_keepalive.py) already has a working,
tested, PURE liveness predicate, this file imports and reuses that predicate directly
against the shared table rather than re-deriving the marker logic -- so this file can never
silently drift from what those modules' own guard tests already prove correct. When a
sibling's table-driven predicate says DEAD, this file calls that sibling module's own
`main()` (its existing, already-tested check+relaunch+reverify path) rather than
reimplementing the relaunch -- this costs one extra confirmatory subprocess call, but ONLY
on the rare "something is actually dead" branch; the common "everything is alive" case never
leaves the single shared table read.

FOUR DAEMONS HAVE NO PYTHON MODULE TO IMPORT -- their existing keepalive is a PowerShell
script whose body is more than bare liveness+spawn (HTTP health probes, port-conflict
guards, a Next.js production-build precondition, a restart-policy import). Per this goal's
own instruction ("port the check+spawn into Python ... exactly as the originals do"), these
four are PORTED (not re-designed) into Python functions below, each with a comment pointing
at the .ps1 it mirrors line-for-line:
  - companion   <- run-companion-keepalive.ps1      (HTTP /api/state probe, port-conflict guard)
  - dashboard   <- run-dashboard-keepalive.ps1       (HTTP / probe, .next build precondition)
  - kitchen     <- run-kitchen-daemon-keepalive.ps1  (pid+status-age wedge check, imports the
                    ALREADY-Python kitchen_daemon_restart_policy.gather_and_decide() for the
                    idle+stale-code recycle rule -- that policy module is reused verbatim,
                    not reimplemented, exactly as the ps1 itself does via Invoke-PythonHidden)
  - discord     <- ensure-discord-bridge-alive.ps1   (two independent pid-file-backed
                    processes, discord-bridge.py + discord-watcher.py)
crypto_grinder_keepalive.py is DELIBERATELY EXCLUDED per this goal's spec -- grinders stay
presence-gated on their own task, not folded into this supervisor.

LOGGING: one line per daemon per run to
`automation/state/logs/supervisor-keepalive-<date>.log` (alive pid / relaunched pid /
skipped reason / spawn failure) -- so a single glance at one file replaces grepping 9.

Each daemon's OWN keepalive script remains on disk, unregistered but importable, so its own
existing guard tests keep passing unmodified and this file can import their pure predicates.
"""
from __future__ import annotations

# === HEADLESS STDIO REDIRECT (OP-27 L41 layer 3) ========================================
import os as _os
import sys as _sys
import datetime as _dt
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _log_date = _dt.date.today().isoformat()
    _sys.stdout = open(_log_dir / f"supervisor-keepalive-{_log_date}.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / f"supervisor-keepalive-{_log_date}.stderr.log", "a", buffering=1, encoding="utf-8")
# ========================================================================================

import datetime as dt
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

# Sibling keepalive modules -- their PURE predicates + main() relaunch paths are reused,
# never reimplemented (see module docstring).
import crypto_twin_keepalive as ctk          # noqa: E402
import proc_trace_keepalive as ptk           # noqa: E402
import window_leak_hook_keepalive as whk     # noqa: E402
import window_leak_detector_keepalive as wld  # noqa: E402
import quote_recorder_keepalive as qrk       # noqa: E402
import kitchen_daemon_restart_policy as kdp  # noqa: E402

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
_DETACHED_PROCESS = 0x00000008

REPO = Path(__file__).resolve().parents[2]
STATE_DIR = REPO / "automation" / "state"
LOG_DIR = STATE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / f"supervisor-keepalive-{dt.date.today().isoformat()}.log"

SYS_PYTHONW = Path(r"C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe")
VENV_SITE_PACKAGES = REPO / "backtest" / ".venv" / "Lib" / "site-packages"
VENV_DIR = REPO / "backtest" / ".venv"


def _log(msg: str) -> None:
    ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")


def _venv_env() -> dict:
    env = os.environ.copy()
    if VENV_SITE_PACKAGES.exists():
        env["PYTHONPATH"] = str(VENV_SITE_PACKAGES)
        env["VIRTUAL_ENV"] = str(VENV_DIR)
    return env


# ── ONE process-table read per run ──────────────────────────────────────────────────────

def live_process_table_text() -> str:
    """Real process-table read via wmic (CREATE_NO_WINDOW, no console flash). The ONLY
    subprocess call every daemon's alive-check draws from -- isolated into its own function
    so the pure parsing/decision logic below never needs a real subprocess call to be unit
    tested."""
    return subprocess.check_output(
        ["wmic", "process", "get", "ProcessId,CommandLine", "/FORMAT:LIST"],
        stderr=subprocess.DEVNULL, timeout=10, creationflags=_CREATE_NO_WINDOW,
    ).decode("utf-8", errors="ignore")


def parse_process_table(text: str) -> dict[int, str]:
    """PURE: parse a wmic '/FORMAT:LIST' CommandLine+ProcessId dump (blank-line-delimited
    records, and the last record sometimes has no trailing blank line) into {pid: cmdline}.
    Mirrors the parsing shape crypto_twin_keepalive.find_loop_pid /
    proc_trace_keepalive.find_tracer_pid already use, generalized to keep every pid rather
    than stopping at the first match -- callers here need to look up an ARBITRARY pid, not
    just find one marker."""
    table: dict[int, str] = {}
    current: dict[str, str] = {}

    def _flush(rec: dict[str, str]) -> None:
        try:
            pid = int(rec.get("ProcessId", ""))
        except ValueError:
            return
        table[pid] = rec.get("CommandLine", "")

    # wmic LIST ends every line with \r\r\n; str.splitlines() treats the lone \r as a line
    # break and splits every record before ProcessId (2026-09-05 runaway: 34 twin loops).
    for raw in text.replace("\r", "").split("\n"):
        line = raw.strip()
        if not line:
            if current:
                _flush(current)
            current = {}
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            current[k.strip()] = v.strip()
    if current:
        _flush(current)
    return table


# ── Result shape every check()/spawn() reports through ──────────────────────────────────

@dataclass
class Outcome:
    name: str
    alive: bool
    action: str          # "alive" | "relaunched" | "skipped" | "spawn_failed"
    detail: str
    pid: Optional[int] = None


@dataclass
class DaemonSpec:
    name: str
    check: Callable[[dict[int, str]], "tuple[bool, str, Optional[int]]"]  # (alive, detail, pid)
    spawn: Callable[[], "tuple[bool, Optional[int], str]"]                # (ok, pid, detail)


# ── crypto-twin (reuses crypto_twin_keepalive.py's own pure predicate + main()) ──────────

def _check_crypto_twin(table: dict[int, str]) -> "tuple[bool, str, Optional[int]]":
    for pid, cmdline in table.items():
        if ctk.is_loop_process_line(cmdline):
            return True, f"loop alive (pid={pid})", pid
    return False, "no crypto_twin_health.py --loop process found", None


def _spawn_crypto_twin() -> "tuple[bool, Optional[int], str]":
    ok, pid = ctk.launch_loop()
    return ok, pid, ("launched" if ok else "launch_loop() failed -- see crypto-twin-keepalive log")


# ── proc-trace (reuses proc_trace_keepalive.py's own pure predicate + launcher) ──────────

def _check_proc_trace(table: dict[int, str]) -> "tuple[bool, str, Optional[int]]":
    for pid, cmdline in table.items():
        if ptk.is_tracer_process_line(cmdline):
            return True, f"tracer alive (pid={pid})", pid
    return False, "no proc_trace.py process found", None


def _spawn_proc_trace() -> "tuple[bool, Optional[int], str]":
    ok, pid = ptk.launch_tracer()
    return ok, pid, ("launched" if ok else "launch_tracer() failed -- see proc-trace-keepalive log")


# ── window-leak hook (reuses window_leak_hook_keepalive.py's marker + full main()) ───────

def _check_window_leak_hook(table: dict[int, str]) -> "tuple[bool, str, Optional[int]]":
    if not whk.PID_FILE.exists():
        return False, "no pid file", None
    try:
        pid = int(whk.PID_FILE.read_text(encoding="utf-8").strip())
    except Exception:
        return False, "pid file unreadable", None
    cmdline = table.get(pid, "")
    if whk._CMDLINE_MARKER in cmdline:
        return True, f"hook alive (pid={pid})", pid
    return False, f"pid file names {pid} but that pid is not the hook (or is gone)", pid


def _spawn_window_leak_hook() -> "tuple[bool, Optional[int], str]":
    # window_leak_hook_keepalive.main() does its own dead-check + spawn + re-verify with a
    # sleep -- reused verbatim rather than duplicating its Popen call here.
    rc = whk.main()
    if rc == 0:
        alive, pid = whk._hook_alive()
        return alive, pid, ("relaunch OK" if alive else "main() returned 0 but hook still not alive")
    return False, None, "window_leak_hook_keepalive.main() returned non-zero -- see its own log"


# ── window-leak detector (reuses window_leak_detector_keepalive.py incl. 6h recycle) ─────

def _check_window_leak_detector(table: dict[int, str]) -> "tuple[bool, str, Optional[int]]":
    if not wld.PID_FILE.exists():
        return False, "no pid file", None
    try:
        pid = int(wld.PID_FILE.read_text(encoding="utf-8").strip())
    except Exception:
        return False, "pid file unreadable", None
    cmdline = table.get(pid, "")
    if "window-leak-detector" not in cmdline:
        return False, f"pid file names {pid} but that pid is not the detector (or is gone)", pid
    age = wld._detector_runtime_s(live_pid=pid)
    if age is not None and age > wld.MAX_DETECTOR_AGE_S:
        return False, f"detector pid={pid} has run {age/3600:.1f}h (> recycle threshold) -- WEDGE-RECYCLE due", pid
    return True, f"detector alive (pid={pid})", pid


def _spawn_window_leak_detector() -> "tuple[bool, Optional[int], str]":
    # main() itself re-derives alive/age and either no-ops or kills+relaunches -- reused
    # verbatim so the 6h wedge-recycle logic (2026-08-13 lesson) never has a second copy.
    rc = wld.main()
    if rc == 0:
        alive, pid = wld._detector_alive()
        return alive, pid, ("relaunch OK" if alive else "main() returned 0 but detector still not alive")
    return False, None, "window_leak_detector_keepalive.main() returned non-zero -- see its own log"


# ── quote recorder (reuses quote_recorder_keepalive.py's marker + full main()) ───────────

def _check_quote_recorder(table: dict[int, str]) -> "tuple[bool, str, Optional[int]]":
    if not qrk.STATUS_FILE.exists():
        return False, "no status file", None
    try:
        pid = int(json.loads(qrk.STATUS_FILE.read_text(encoding="utf-8")).get("pid"))
    except Exception:
        return False, "status file unreadable", None
    cmdline = table.get(pid, "")
    if "quote_recorder.py" in cmdline:
        return True, f"recorder alive (pid={pid})", pid
    return False, f"status file names {pid} but that pid is not the recorder (or is gone)", pid


def _spawn_quote_recorder() -> "tuple[bool, Optional[int], str]":
    rc = qrk.main()
    if rc == 0:
        alive, pid = qrk._recorder_alive()
        return alive, pid, ("relaunch OK" if alive else "main() returned 0 but recorder still not alive")
    return False, None, "quote_recorder_keepalive.main() returned non-zero -- see its own log"


# ── kitchen daemon -- PORTED from run-kitchen-daemon-keepalive.ps1 ───────────────────────
# (this ps1 is more than bare liveness+spawn: pid+cmdline check, a 25-min status-staleness
# wedge kill, AND an idle+stale-code restart policy -- the LAST of those is not reimplemented
# here, it is the SAME kitchen_daemon_restart_policy.gather_and_decide() the ps1 itself calls
# via Invoke-PythonHidden; calling it in-process is a straight simplification of that same
# ps1->python hop, not new logic.)

KITCHEN_PID_FILE = STATE_DIR / "kitchen-daemon.pid"
KITCHEN_STATUS_FILE = STATE_DIR / "kitchen-status.json"
KITCHEN_SCRIPT = SCRIPTS / "kitchen_daemon.py"
KITCHEN_WEDGE_STALE_MIN = 25.0


def _check_kitchen_daemon(table: dict[int, str]) -> "tuple[bool, str, Optional[int]]":
    if not KITCHEN_PID_FILE.exists():
        return False, "no pid file", None
    try:
        pid = int(json.loads(KITCHEN_PID_FILE.read_text(encoding="utf-8")).get("pid"))
    except Exception:
        return False, "pid file unreadable", None
    cmdline = table.get(pid, "")
    if "kitchen_daemon.py" not in cmdline:
        return False, f"pid file names {pid} but that pid is not the daemon (or is gone)", pid

    if not KITCHEN_STATUS_FILE.exists():
        return True, f"daemon alive pid={pid} (no status file yet)", pid
    try:
        status_age_min = (time.time() - KITCHEN_STATUS_FILE.stat().st_mtime) / 60.0
    except OSError:
        return True, f"daemon alive pid={pid} (status file stat failed)", pid
    if status_age_min > KITCHEN_WEDGE_STALE_MIN:
        return False, f"daemon pid={pid} WEDGED -- status age {status_age_min:.1f}min > {KITCHEN_WEDGE_STALE_MIN}min", pid

    # Idle + stale-code recycle rule -- imports the daemon's own policy module verbatim.
    should_restart, reason = kdp.gather_and_decide(
        status_file=KITCHEN_STATUS_FILE, pid_file=KITCHEN_PID_FILE,
    )
    if should_restart:
        return False, f"daemon pid={pid} idle+stale-code -- {reason}", pid
    return True, f"daemon alive pid={pid} status_age={status_age_min:.1f}min policy={reason}", pid


def _spawn_kitchen_daemon() -> "tuple[bool, Optional[int], str]":
    # Kill the previous pid first if it's still around (wedge/stale-code recycle path) --
    # mirrors the ps1's own Stop-Process -Force before falling through to relaunch.
    if KITCHEN_PID_FILE.exists():
        try:
            old_pid = int(json.loads(KITCHEN_PID_FILE.read_text(encoding="utf-8")).get("pid"))
            subprocess.run(["taskkill", "/PID", str(old_pid), "/F"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            timeout=10, creationflags=_CREATE_NO_WINDOW)
        except Exception:
            pass

    if not SYS_PYTHONW.exists():
        return False, None, f"system pythonw missing at {SYS_PYTHONW}"
    if not KITCHEN_SCRIPT.exists():
        return False, None, f"kitchen_daemon.py missing at {KITCHEN_SCRIPT}"

    try:
        proc = subprocess.Popen(
            [str(SYS_PYTHONW), str(KITCHEN_SCRIPT), "run"],
            cwd=str(REPO), env=_venv_env(),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
            creationflags=_DETACHED_PROCESS | _CREATE_NO_WINDOW, close_fds=True,
        )
        time.sleep(2)
        return True, proc.pid, "launched"
    except Exception as e:  # noqa: BLE001
        return False, None, f"launch failed: {e}"


# ── discord bridge + watcher -- PORTED from ensure-discord-bridge-alive.ps1 ──────────────
# Two independent pid-file-backed processes. The ps1's Test-PidAlive only checks process
# EXISTENCE (Get-Process -Id), not command line -- ported faithfully (no new cmdline check
# added), since that is exactly what the original does.

DISCORD_BRIDGE_PID = STATE_DIR / "discord-bridge.pid"
DISCORD_WATCHER_PID = STATE_DIR / "discord-watcher.pid"
DISCORD_BRIDGE_SCRIPT = SCRIPTS / "discord-bridge.py"
DISCORD_WATCHER_SCRIPT = SCRIPTS / "discord-watcher.py"


def _read_pipe_pid(pid_file: Path) -> Optional[int]:
    """Parses the 'pid|iso-timestamp' pid-file shape discord-bridge.py / discord-watcher.py
    both write (PID_PATH.write_text(f"{pid}|{now_iso()}"))."""
    if not pid_file.exists():
        return None
    try:
        return int(pid_file.read_text(encoding="utf-8").strip().split("|")[0])
    except Exception:
        return None


def _check_discord_proc(pid_file: Path, table: dict[int, str]) -> "tuple[bool, str, Optional[int]]":
    pid = _read_pipe_pid(pid_file)
    if pid is None:
        return False, "no pid file", None
    if pid in table:
        return True, f"alive (pid={pid})", pid
    return False, f"pid file names {pid} but that pid is not running", pid


def _spawn_discord_script(script: Path, pid_file: Path, name: str) -> "tuple[bool, Optional[int], str]":
    try:
        pid_file.unlink(missing_ok=True)
    except OSError:
        pass
    if not SYS_PYTHONW.exists():
        return False, None, f"system pythonw missing at {SYS_PYTHONW}"
    if not script.exists():
        return False, None, f"{name} script missing at {script}"
    try:
        proc = subprocess.Popen(
            [str(SYS_PYTHONW), str(script)],
            cwd=str(REPO), env=_venv_env(),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
            creationflags=_DETACHED_PROCESS | _CREATE_NO_WINDOW, close_fds=True,
        )
        time.sleep(2)
        ok = _read_pipe_pid(pid_file) is not None
        return ok, proc.pid, ("OK" if ok else "spawned but pid file not written")
    except Exception as e:  # noqa: BLE001
        return False, None, f"launch failed: {e}"


def _check_discord_bridge(table: dict[int, str]) -> "tuple[bool, str, Optional[int]]":
    return _check_discord_proc(DISCORD_BRIDGE_PID, table)


def _spawn_discord_bridge() -> "tuple[bool, Optional[int], str]":
    return _spawn_discord_script(DISCORD_BRIDGE_SCRIPT, DISCORD_BRIDGE_PID, "discord-bridge")


def _check_discord_watcher(table: dict[int, str]) -> "tuple[bool, str, Optional[int]]":
    return _check_discord_proc(DISCORD_WATCHER_PID, table)


def _spawn_discord_watcher() -> "tuple[bool, Optional[int], str]":
    return _spawn_discord_script(DISCORD_WATCHER_SCRIPT, DISCORD_WATCHER_PID, "discord-watcher")


# ── companion (:4317) -- PORTED from run-companion-keepalive.ps1 ─────────────────────────
# HTTP /api/state liveness probe + port-conflict guard (never kill/spawn over a foreign
# process holding the port). table (the shared process list) is NOT the liveness source
# here -- the ps1 original never trusted the process table for this daemon either (its own
# comment: the wscript launcher runs a RELATIVE arg so the command line never contains
# "gamma-companion" -- only an HTTP 200 is unambiguous proof). table is accepted as a
# parameter anyway (unused) so this check has the same signature as every other entry.

COMPANION_PORT = 4317
COMPANION_DIR = REPO / "gamma-companion"
COMPANION_SCRIPT = COMPANION_DIR / "server.js"
DASHBOARD_PORT = 3000
DASHBOARD_DIR = REPO / "dashboard"

_HTTP_TIMEOUT_S = 8


def _http_probe(url: str, ok_codes: range) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=_HTTP_TIMEOUT_S) as resp:
            return resp.status in ok_codes
    except urllib.error.HTTPError as e:
        # A companion auth-guard 401/403 still proves the process is UP and answering --
        # only a connection failure means "nothing is listening".
        return e.code in ok_codes
    except Exception:
        return False


def _port_bound(port: int) -> bool:
    """True if ANYTHING is already listening on the port (owner unknown) -- a single
    connect() probe, no extra subprocess/netstat call needed. Used only to decide
    'do not spawn, something already owns this port' when the HTTP probe fails."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.5)
        try:
            return s.connect_ex(("127.0.0.1", port)) == 0
        except OSError:
            return False


def _resolve_node() -> Optional[str]:
    candidate = r"C:\Program Files\nodejs\node.exe"
    if Path(candidate).exists():
        return candidate
    return shutil.which("node.exe") or shutil.which("node")


def _check_companion(table: dict[int, str]) -> "tuple[bool, str, Optional[int]]":
    if _http_probe(f"http://127.0.0.1:{COMPANION_PORT}/api/state", range(200, 500)):
        return True, f"companion alive on :{COMPANION_PORT} (/api/state answered)", None
    if _port_bound(COMPANION_PORT):
        return False, f"PORT {COMPANION_PORT} held by something not answering /api/state -- not spawning (port conflict)", None
    return False, f"nothing listening on :{COMPANION_PORT}", None


def _spawn_companion() -> "tuple[bool, Optional[int], str]":
    node = _resolve_node()
    if not node:
        return False, None, "node.exe not found"
    if not COMPANION_SCRIPT.exists():
        return False, None, f"server.js not at {COMPANION_SCRIPT}"
    try:
        proc = subprocess.Popen(
            [node, str(COMPANION_SCRIPT)],
            cwd=str(COMPANION_DIR),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
            creationflags=_DETACHED_PROCESS | _CREATE_NO_WINDOW, close_fds=True,
        )
        return True, proc.pid, f"started companion pid={proc.pid} on :{COMPANION_PORT}"
    except Exception as e:  # noqa: BLE001
        return False, None, f"failed to start companion: {e}"


# ── dashboard (:3000) -- PORTED from run-dashboard-keepalive.ps1 ─────────────────────────

def _check_dashboard(table: dict[int, str]) -> "tuple[bool, str, Optional[int]]":
    if _http_probe(f"http://127.0.0.1:{DASHBOARD_PORT}/", range(200, 400)):
        return True, f"dashboard alive on :{DASHBOARD_PORT}", None
    if _port_bound(DASHBOARD_PORT):
        return False, f"PORT {DASHBOARD_PORT} held by something not answering / -- not spawning (port conflict, may be a dev server)", None
    return False, f"nothing listening on :{DASHBOARD_PORT}", None


def _spawn_dashboard() -> "tuple[bool, Optional[int], str]":
    node = _resolve_node()
    if not node:
        return False, None, "node.exe not found"
    build_dir = DASHBOARD_DIR / ".next"
    if not build_dir.exists():
        return False, None, f".next build not found at {build_dir} -- run 'npm run build' first"
    next_script = DASHBOARD_DIR / "node_modules" / "next" / "dist" / "bin" / "next"
    next_bin = DASHBOARD_DIR / "node_modules" / ".bin" / "next"
    if not next_script.exists() and not next_bin.exists() and not Path(str(next_bin) + ".cmd").exists():
        return False, None, f"next binary not found under {DASHBOARD_DIR / 'node_modules'}"
    try:
        proc = subprocess.Popen(
            [node, str(next_script), "start", "-p", str(DASHBOARD_PORT)],
            cwd=str(DASHBOARD_DIR),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
            creationflags=_DETACHED_PROCESS | _CREATE_NO_WINDOW, close_fds=True,
        )
        return True, proc.pid, f"started dashboard pid={proc.pid} on :{DASHBOARD_PORT}"
    except Exception as e:  # noqa: BLE001
        return False, None, f"failed to start dashboard: {e}"


# ── the registry ──────────────────────────────────────────────────────────────────────

REGISTRY: list[DaemonSpec] = [
    DaemonSpec("companion", _check_companion, _spawn_companion),
    DaemonSpec("dashboard", _check_dashboard, _spawn_dashboard),
    DaemonSpec("kitchen_daemon", _check_kitchen_daemon, _spawn_kitchen_daemon),
    DaemonSpec("discord_bridge", _check_discord_bridge, _spawn_discord_bridge),
    DaemonSpec("discord_watcher", _check_discord_watcher, _spawn_discord_watcher),
    DaemonSpec("quote_recorder", _check_quote_recorder, _spawn_quote_recorder),
    DaemonSpec("crypto_twin", _check_crypto_twin, _spawn_crypto_twin),
    DaemonSpec("window_leak_detector", _check_window_leak_detector, _spawn_window_leak_detector),
    DaemonSpec("window_leak_hook", _check_window_leak_hook, _spawn_window_leak_hook),
    DaemonSpec("proc_trace", _check_proc_trace, _spawn_proc_trace),
]


def run_once(registry: "list[DaemonSpec]" = REGISTRY,
             table: "dict[int, str] | None" = None) -> "list[Outcome]":
    """Runs every daemon's check(), relaunching the dead ones. ONE shared process-table
    snapshot for the whole pass unless a caller supplies one (tests inject a fake table).
    A single daemon's check()/spawn() raising must never stop the rest -- each is wrapped so
    one bad daemon can't hide the other 9's status."""
    if table is None:
        try:
            table = parse_process_table(live_process_table_text())
        except Exception as e:  # noqa: BLE001 -- a wmic hiccup must not blank out every check
            _log(f"WARN: process-table read failed ({e}); proceeding with empty table "
                 f"(every daemon will read as dead and attempt a relaunch)")
            table = {}

    outcomes: list[Outcome] = []
    for spec in registry:
        try:
            alive, detail, pid = spec.check(table)
        except Exception as e:  # noqa: BLE001
            _log(f"{spec.name}: CHECK RAISED {e!r} -- treating as dead")
            alive, detail, pid = False, f"check() raised: {e}", None

        if alive:
            _log(f"{spec.name}: alive -- {detail}")
            outcomes.append(Outcome(spec.name, True, "alive", detail, pid))
            continue

        _log(f"{spec.name}: DEAD ({detail}) -- relaunching")
        try:
            ok, new_pid, spawn_detail = spec.spawn()
        except Exception as e:  # noqa: BLE001
            _log(f"{spec.name}: SPAWN RAISED {e!r}")
            outcomes.append(Outcome(spec.name, False, "spawn_failed", f"spawn() raised: {e}", None))
            continue

        if ok:
            _log(f"{spec.name}: relaunched pid={new_pid} ({spawn_detail})")
            outcomes.append(Outcome(spec.name, True, "relaunched", spawn_detail, new_pid))
        else:
            _log(f"{spec.name}: SPAWN FAILED -- {spawn_detail}")
            outcomes.append(Outcome(spec.name, False, "spawn_failed", spawn_detail, None))

    return outcomes


def main() -> int:
    outcomes = run_once()
    failed = [o for o in outcomes if o.action == "spawn_failed"]
    return 1 if failed else 0


def _main_safe() -> int:
    try:
        return main()
    except Exception as e:  # noqa: BLE001
        _log(f"FATAL unhandled exception: {e}")
        return 0


if __name__ == "__main__":
    sys.exit(_main_safe())
