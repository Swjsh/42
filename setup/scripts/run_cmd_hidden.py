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

2026-09-10 -- W14 DEFAULT-LOG FIX (goal GOAL-WHY-THIS-WEEK-2026-09-10, item W14).
FINDING: when a task action omits --log (measured live this session: 92 of 104
Gamma_* tasks invoking this file do), the old code ran the child with
`subprocess.run(..., capture_output=True)` and only ever logged `proc.returncode`
to the shared per-date launcher log -- the captured stdout/stderr was read into
memory and thrown away, even on a crashing child with a live traceback. This is
the suspected root enabler of this codebase's C7 failure class ("silent success
is failure") -- see W10 in the goal file for a concrete incident this discarded
channel prevented from being root-caused.

FIX (this block): when --log is absent, DEFAULT to a per-command log file under
automation/state/logs/auto/<command-stem>.log instead of discarding output.
--log, when supplied, behaves exactly as before (unchanged code path).

RETENTION POLICY (OP-22: every append-only producer needs a cap; the parent
logs/ dir was already 746MB/8,054 files before this fix, and 92 new daily
producers would make that materially worse):
  1. Per-file rotation: a command's own auto-log rotates to <name>.log.1 (single
     backup, previous .1 clobbered) once it exceeds AUTO_LOG_MAX_FILE_BYTES.
  2. Directory-wide age prune: any file under logs/auto/ older than
     AUTO_LOG_MAX_AGE_DAYS (by mtime) is deleted.
  3. Directory-wide size cap: if logs/auto/ still exceeds AUTO_LOG_MAX_DIR_BYTES
     after (1)+(2), oldest-mtime-first deletion until under cap.
  4. Cheap by construction for 1-minute-cadence tasks (Gamma_LiveWatch fires
     every 60s): steps 2+3 are TIME-GATED behind a sentinel file
     (.last-prune-<date>) so the directory is actually scanned at most once per
     AUTO_PRUNE_INTERVAL_SECONDS, not on every invocation. A normal invocation's
     added cost is one stat + one append-open.
  5. Scope: pruning ONLY ever touches files inside logs/auto/ -- the directory
     this fix itself creates. It never touches logs/archive/ or any pre-existing
     log file it did not create.

FAIL-OPEN (hard requirement -- this launcher fires the trading engine's own
adjacent tasks): every step of the new default-log/prune/rotate logic is wrapped
in its own try/except Exception. Any failure anywhere in that path silently
falls back to the OLD behaviour (capture_output=True, output discarded) rather
than blocking or crashing the launch. A logging improvement must never be able
to prevent a scheduled task from running.

EXIT CODE CONTRACT: unchanged in every branch -- main() still returns exactly
proc.returncode (or the same 1/2 fallback ints as before) whether the default
log path succeeded, failed open, or --log was supplied explicitly. Existing
LastTaskResult / freshness guards are unaffected.
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

# --- W14 default-log-when---log-absent (2026-09-10) --------------------------------------
AUTO_LOG_DIR = LOG_DIR / "auto"
AUTO_LOG_MAX_FILE_BYTES = 5 * 1024 * 1024        # rotate a single command's log past this
AUTO_LOG_MAX_AGE_DAYS = 14                       # delete auto-log files older than this
AUTO_LOG_MAX_DIR_BYTES = 300 * 1024 * 1024       # then enforce this total cap, oldest-first
AUTO_PRUNE_INTERVAL_SECONDS = 3600               # only actually scan the dir this often
_AUTO_PRUNE_SENTINEL = AUTO_LOG_DIR / ".last-prune"


import re as _re

_SAFE_STEM_RE = _re.compile(r"[^A-Za-z0-9_-]+")
_MAX_STEM_LEN = 80


def _sanitize_stem(raw: str) -> str:
    """Collapse anything that is not [A-Za-z0-9_-] to '_' and cap length, so a
    command token that is NOT a clean script path (e.g. `python -c "<code>"`,
    which has no .py file at all) can never produce a garbage/oversized/invalid
    Windows filename or escape AUTO_LOG_DIR via path separators."""
    cleaned = _SAFE_STEM_RE.sub("_", raw).strip("_")
    cleaned = cleaned[:_MAX_STEM_LEN]
    return cleaned or "unknown"


def _derive_log_stem(cmd: list[str]) -> str:
    """Best-effort stable name for a command, e.g. ['...\\pythonw.exe', 'foo.py', '--x']
    -> 'foo'. Falls back to 'unknown' rather than raising -- callers must still wrap
    this in try/except since Path() on a malformed token could theoretically raise."""
    for tok in cmd:
        low = tok.lower()
        if low.endswith(".py") or low.endswith(".ps1"):
            stem = Path(tok).stem
            if stem:
                return _sanitize_stem(stem)
    # `python -m pkg.mod ...` -- the module IS the identity. Handled BEFORE the
    # reversed-token fallback below, which would otherwise pick the last FLAG
    # (`python -m a.b --daily` and `python -m c.d --daily` both -> '--daily.log',
    # silently merging two producers into one evidence channel -- the exact failure
    # this auto-log exists to prevent). No live task used `-m` when this was found
    # (verified 2026-09-10 against the registry: 0 of the 92), so this closes a
    # latent trap for the first `-m` task registered, not a current outage.
    for i, tok in enumerate(cmd):
        if tok == "-m" and i + 1 < len(cmd):
            mod = cmd[i + 1]
            if mod and not mod.startswith("-"):
                return _sanitize_stem(mod)

    # No script-like token found (e.g. `python -c "<code>"` or a bare module/exe
    # invocation) -- use the last non-python token as a fallback identifier,
    # sanitized so free-form code text can never become a raw filename.
    for tok in reversed(cmd):
        stem = Path(tok).stem
        if stem and not stem.lower().startswith("python"):
            return _sanitize_stem(stem)
    return "unknown"


def _rotate_if_oversized(path: Path) -> None:
    """Single-backup rotation for one command's own auto-log."""
    if path.exists() and path.stat().st_size > AUTO_LOG_MAX_FILE_BYTES:
        backup = path.with_suffix(path.suffix + ".1")
        if backup.exists():
            backup.unlink()
        path.rename(backup)


def _prune_auto_log_dir() -> None:
    """Time-gated age + size prune of AUTO_LOG_DIR only. Never touches any other
    directory. Gated behind a sentinel file so 1-minute-cadence tasks do not pay
    a full directory scan on every invocation."""
    now = dt.datetime.now().timestamp()
    if _AUTO_PRUNE_SENTINEL.exists():
        last = _AUTO_PRUNE_SENTINEL.stat().st_mtime
        if (now - last) < AUTO_PRUNE_INTERVAL_SECONDS:
            return
    _AUTO_PRUNE_SENTINEL.write_text(str(now), encoding="utf-8")

    files = [p for p in AUTO_LOG_DIR.iterdir() if p.is_file() and p != _AUTO_PRUNE_SENTINEL]

    # Age prune first.
    cutoff = now - (AUTO_LOG_MAX_AGE_DAYS * 86400)
    kept = []
    for p in files:
        if p.stat().st_mtime < cutoff:
            p.unlink()
        else:
            kept.append(p)

    # Then a total-size cap, oldest mtime first.
    kept.sort(key=lambda p: p.stat().st_mtime)
    total = sum(p.stat().st_size for p in kept)
    i = 0
    while total > AUTO_LOG_MAX_DIR_BYTES and i < len(kept):
        p = kept[i]
        total -= p.stat().st_size
        p.unlink()
        i += 1


def _default_auto_log_path(cmd: list[str]) -> Path:
    """Resolve (and prep) the default per-command auto-log path. Any failure here
    must be caught by the caller -- this function may raise."""
    AUTO_LOG_DIR.mkdir(parents=True, exist_ok=True)
    stem = _derive_log_stem(cmd)
    path = AUTO_LOG_DIR / f"{stem}.log"
    _rotate_if_oversized(path)
    try:
        _prune_auto_log_dir()
    except Exception:
        # Pruning is best-effort housekeeping, never load-bearing for the launch
        # itself -- a prune failure must not block writing this invocation's log.
        pass
    return path


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
    else:
        # W14: default to a per-command auto-log instead of discarding output.
        # FAIL OPEN -- any problem here (permissions, disk, weird cmd token,
        # prune bug) must silently fall back to the pre-fix behaviour
        # (log_path stays None -> capture_output=True, discarded) rather than
        # blocking or crashing this launch. This launcher fires trading-adjacent
        # tasks; a logging improvement must never be able to stop one.
        try:
            log_path = _default_auto_log_path(cmd)
        except Exception as e:
            _log(f"  WARN: default auto-log setup failed, falling back to discard: {e}")
            log_path = None

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

    # W14 FAIL-OPEN: opening our OWN auto-log (args.log was not given) must never be
    # able to block the launch. If it fails at open-time (race, permissions, disk
    # full since _default_auto_log_path resolved it), degrade to the pre-fix
    # discard behaviour for THIS invocation only. An explicit --log keeps its
    # original (non-degrading) behaviour unchanged -- the caller asked for that
    # file specifically.
    is_auto_log = (not args.log) and (log_path is not None)
    if is_auto_log:
        # Pre-open here (outside the main try below) so a failure degrades to
        # discard mode for this one invocation rather than being treated as a
        # launch-fatal error the way an explicit --log open failure is.
        try:
            log_fh = log_path.open("a", encoding="utf-8")
        except Exception as e:
            _log(f"  WARN: auto-log open failed, falling back to discard: {e}")
            log_fh = None
            log_path = None
    else:
        # Explicit --log (or no log at all): unchanged from pre-fix behaviour --
        # the open happens inside the try below, so an open failure there is
        # still launch-fatal exactly as it always was.
        log_fh = None

    try:
        if is_auto_log:
            if log_fh is not None:
                with log_fh:
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
        elif log_path is not None:
            with log_path.open("a", encoding="utf-8") as log_fh2:
                proc = subprocess.run(
                    cmd,
                    cwd=cwd,
                    env=env,
                    stdout=log_fh2,
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
