"""Hidden launcher for cmd-style grind tasks (CREATE_NO_WINDOW).

Replaces cmd.exe /c "set ENV=VAL&& python.exe -m module > log 2>&1" task
actions with a windowless equivalent that never flashes OpenConsole.

Task action (SYSTEM pythonw as the outer wscript target -- see 2026-07-14 correction below):
    wscript.exe //nologo run_exe_hidden.vbs
        <system-pythonw>
        run_cmd_hidden.py
        --env KEY=VAL [--env KEY2=VAL2 ...]
        --log <log-file>
        --cwd <working-dir>
        -- <backtest-venv-pythonw> -m <module> [args...]

2026-07-14 CORRECTION (J: "stop the fkin popus on my screen"): this docstring used to
claim "using backtest venv pythonw — GUI subsystem, never allocates a console" as the
OUTER wscript target. That claim is FALSE for any target that imports pandas/numpy --
live-fire investigation this session (window-leak-detector.py, re-armed) proved a
MINIMAL stdlib-only script under backtest-venv-pythonw is clean, but a script that does
`import pandas` leaks a WindowsTerminal -Embedding console-host window regardless of
launcher mechanism (Shell.Run, WshShell.Exec, AND Python subprocess.Popen with
creationflags=CREATE_NO_WINDOW were all tested live and all three still leaked -- root
cause is below the level any of those can intercept). Since run_cmd_hidden.py itself is
stdlib-only, it is safe as either an outer OR inner hop; the actual heavy-import module
it launches (the real risk) still goes through the SAME creationflags=CREATE_NO_WINDOW
subprocess call either way, so putting run_cmd_hidden.py under system-pythonw instead of
venv-pythonw changes nothing about that inner risk -- it's a consistency choice (matches
every other pythonw-direct wscript target in this repo), not a fix by itself. The actual
popup suppression for the still-unresolved inner leak is window-leak-detector.py's
auto-hide mitigation (ShowWindow SW_HIDE on any service-rooted console-host window),
not anything in this file.

Why not run_ps1_hidden.py?  That script wraps a PowerShell .ps1 file.  The
grind tasks have no .ps1 wrapper — they run python directly.  A separate
launcher keeps the two concerns clean.

2026-06-26 — WS6 CMD popup fix.
"""
from __future__ import annotations

# === HEADLESS STDIO REDIRECT (OP-27 L41 layer 3) ========================================
import os as _os
import sys as _sys
from pathlib import Path as _Path

if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "run-cmd-hidden.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "run-cmd-hidden.stderr.log", "a", buffering=1, encoding="utf-8")
# ========================================================================================

import argparse
import datetime as dt
import subprocess
import sys
from pathlib import Path

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

REPO = Path(__file__).resolve().parents[2]
LOG_DIR = REPO / "automation" / "state" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
_LAUNCHER_LOG = LOG_DIR / f"run-cmd-hidden-{dt.date.today().isoformat()}.log"


def _log(msg: str) -> None:
    ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _LAUNCHER_LOG.open("a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Windowless grind launcher")
    parser.add_argument("--env", action="append", default=[], metavar="KEY=VAL",
                        help="Environment variable to inject (repeatable)")
    parser.add_argument("--log", default=None, metavar="FILE",
                        help="Path to redirect combined stdout+stderr (creates/appends)")
    parser.add_argument("--cwd", default=None, metavar="DIR",
                        help="Working directory for the child process")
    parser.add_argument("cmd", nargs=argparse.REMAINDER,
                        help="Command to run (everything after '--')")

    # Strip the leading '--' separator if present
    raw = list(argv[1:])
    try:
        sep_idx = raw.index("--")
        pre = raw[:sep_idx]
        post = raw[sep_idx + 1:]
    except ValueError:
        pre = raw
        post = []

    args = parser.parse_args(pre)
    cmd = post or args.cmd

    if not cmd:
        _log("FATAL: no command specified after '--'")
        return 2

    # Build environment: inherit current env, then overlay --env overrides
    env = dict(_os.environ)
    for kv in args.env:
        if "=" not in kv:
            _log(f"WARN: skipping malformed --env value (no '='): {kv!r}")
            continue
        k, v = kv.split("=", 1)
        env[k] = v

    # Resolve working directory
    cwd = str(Path(args.cwd).resolve()) if args.cwd else str(REPO / "backtest")

    # Resolve log file (combined stdout+stderr redirect)
    log_path: Path | None = None
    if args.log:
        log_path = Path(args.log)
        log_path.parent.mkdir(parents=True, exist_ok=True)

    # 2026-08-21 CONCURRENCY-MISATTRIBUTION FIX: this relay routinely has 5+ overlapping
    # run_cmd_hidden.py processes writing to the SAME shared per-date log file (verified
    # live 2026-08-21: 3208 'launching:' lines vs only 1944 completed pairings under the
    # old FIFO-of-1 parser -- a ~40% loss/misattribution rate, and a real risk of blaming
    # a script for a DIFFERENT concurrently-running script's non-zero exit). Tag both the
    # launching and exit lines with this process's own PID so self_check.py's parser can
    # pair them unambiguously instead of assuming strict line adjacency.
    _pid_tag = f"[pid={_os.getpid()}]"
    _log(f"launching: {' '.join(cmd)}  {_pid_tag}")
    _log(f"  cwd={cwd}  env_overrides={args.env}  log={args.log}")

    try:
        if log_path is not None:
            with log_path.open("a", encoding="utf-8") as log_fh:
                proc = subprocess.run(
                    cmd,
                    cwd=cwd,
                    env=env,
                    stdout=log_fh,
                    stderr=subprocess.STDOUT,
                    creationflags=_CREATE_NO_WINDOW,
                )
        else:
            proc = subprocess.run(
                cmd,
                cwd=cwd,
                env=env,
                capture_output=True,
                creationflags=_CREATE_NO_WINDOW,
            )
        _log(f"  exit={proc.returncode}  {_pid_tag}")
        return proc.returncode
    except FileNotFoundError as e:
        _log(f"  FATAL (FileNotFoundError): {e}")
        return 1
    except Exception as e:
        _log(f"  FATAL: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
