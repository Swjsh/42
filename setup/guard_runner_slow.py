#!/usr/bin/env python
"""guard_runner_slow.py - NIGHTLY data-heavy graduated-guards runner.

Companion to setup/guard_runner.py. The per-edit PostToolUse hook runs only the
FAST logic guards (`-m "not slow"`, ~2s) so an engine edit is never blocked. The
SLOW guards (`-m slow`) each load the 16-month master SPY/VIX CSV and run one or
more full backtests (20-60s each, ~35 of them) - far over the 600s per-edit
budget. Excluding them from the hook is correct, but they must still run SOMEWHERE
or the regression coverage is silently dropped. This script is that "somewhere":
a once-nightly, $0, pure-Python gate fired by the Gamma_GuardsNightly scheduled
task (after-hours, never during 09:30-15:55 ET market hours - L54 heartbeat).

Behaviour:
  * Runs `pytest -m slow` over the graduated-guards file with a generous timeout.
  * ALWAYS writes the verdict to automation/state/guard-watch-slow.json (a SEPARATE
    sentinel from the per-edit guard-watch.json - it must never clobber a pending
    per-edit failure signal).
  * On a transition INTO broken (prior run was pass/absent, this run is not pass)
    appends ONE loud, timestamped line to STATUS.md "## Known broken" (OP-25:
    silent failure is the only true failure). A persisting failure is NOT re-spammed
    every night; a recovery flips the sentinel back to pass.

Per CLAUDE.md OP-25 (fail loud) + OP-26 (regression surface) + lesson C8 (headless
Windows spawn = CREATE_NO_WINDOW). Pure regression guard: never edits engine code,
never places orders.

Manual run (foreground, shows output):
    cd backtest && python -m pytest tests/test_graduated_guards.py -m slow -q
"""
from __future__ import annotations

# === HEADLESS STDIO REDIRECT (OP-27 L41 layer 3, 2026-07-14 popup-storm fix) =====
# When launched via pythonw.exe (no console), Windows 11's default-terminal setting
# can allocate a visible WindowsTerminal -Embedding window on the FIRST stderr/stdout
# write. Redirect stdio to log files BEFORE any other import gets a chance to write.
# Root-caused live 2026-07-14 (J: "stop the fkin popus on my screen") via the
# re-armed window-leak-detector.py: this exact script, launched wscript->
# run_exe_hidden.vbs->backtest-venv-pythonw with NO relay layer, was caught flashing
# a WindowsTerminal window on a real Start-ScheduledTask fire within 45s.
import os as _os
import sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[1] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "guard-runner-slow.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "guard-runner-slow.stderr.log", "a", buffering=1, encoding="utf-8")
# ==================================================================================

import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\jackw\Desktop\42")
STATE = ROOT / "automation" / "state"
WATCH_SLOW = STATE / "guard-watch-slow.json"
STATUS = ROOT / "automation" / "overnight" / "STATUS.md"
BT = ROOT / "backtest"
CREATE_NO_WINDOW = 0x08000000
# 35 data-heavy guards x up to ~60s each, with headroom. The scheduled task's own
# ExecutionTimeLimit is set wider than this so pytest's timeout fires first (clean
# verdict) rather than Task Scheduler killing the process (no verdict written).
TIMEOUT_S = 3000


def _now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _prior_status() -> str | None:
    """Status of the previous nightly run, or None if no sentinel yet."""
    try:
        return json.loads(WATCH_SLOW.read_text(encoding="utf-8")).get("status")
    except (OSError, ValueError):
        return None


def _flag_status_md(status: str, summary: str) -> None:
    """Append ONE loud line under '## Known broken' on a transition into broken."""
    try:
        text = STATUS.read_text(encoding="utf-8")
    except OSError:
        return
    marker = "## Known broken"
    if marker not in text:
        return
    line = (
        f"- [{_now()}] GRADUATED-GUARDS-SLOW {status.upper()} :: {summary} :: "
        "re-run: cd backtest && python -m pytest tests/test_graduated_guards.py -m slow -q"
    )
    # Insert newest-first, immediately after the section header.
    head, _, tail = text.partition(marker + "\n")
    STATUS.write_text(f"{head}{marker}\n\n{line}\n{tail.lstrip(chr(10))}", encoding="utf-8")


def _run_twin_gauntlet_conductor_hook() -> None:
    """B2b SECONDARY hook -- the GUARANTEED-nightly fallback for the "trading-path
    commit without a twin-gauntlet pass" advisory flag (markdown/planning/
    TWIN-PROGRAM.md value stream #2). PRIMARY hook lives in run-conductor.ps1
    (fires more often, but only when the conductor wakes); Gamma_GuardsNightly
    fires once/night UNCONDITIONALLY, closing the gap a quiet conductor night
    would otherwise leave. Both call-sites share ONE watermark file
    (automation/state/crypto-twin/gauntlet-conductor-watermark.json) so calling
    from both is idempotent. Fail-open: must never affect THIS script's own
    slow-guard verdict or WATCH_SLOW payload."""
    try:
        scripts_dir = str(ROOT / "setup" / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import twin_gauntlet_conductor_hook as tgch
        tgch.run_check()
    except Exception:  # noqa: BLE001 -- advisory only, never let this affect the real guard
        pass


def main() -> int:
    started = _now()
    prior = _prior_status()
    try:
        proc = subprocess.run(
            [sys.executable.replace("pythonw", "python"), "-m", "pytest",
             "tests/test_graduated_guards.py",
             # 2026-07-30 (blind-engine repair follow-up): the live scheduled-task drift guard.
             # SCHEDULED-TASKS.md:39 documented this suite as "runs under Gamma_GuardsNightly"
             # but nothing actually invoked it -- a false wiring claim the repair's own
             # adversarial verifier caught (the exact silent-gap class this suite exists to
             # detect: 49 documented-Active tasks were sitting Disabled for days, including the
             # level refresher that blinded the engine on 2026-07-30). Wiring it here makes the
             # doc claim TRUE instead of editing the doc to match the gap.
             "tests/test_scheduled_task_triggers_live.py",
             "-m", "slow", "-q", "--no-header"],
            cwd=str(BT), capture_output=True, text=True, timeout=TIMEOUT_S,
            creationflags=CREATE_NO_WINDOW,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        last = out.strip().splitlines()[-1] if out.strip() else "(no pytest output)"
        if proc.returncode == 0:
            status = "pass"
        elif proc.returncode == 5:
            status = "notests"  # marker matched nothing -> wiring problem, surface it
        else:
            status = "fail"
        summary = last
    except subprocess.TimeoutExpired:
        status, summary, out = "timeout", f"slow graduated-guards exceeded {TIMEOUT_S}s", ""
    except Exception as exc:  # never crash the runner silently
        status, summary, out = "error", f"runner exception: {exc}", ""

    payload = {
        "skill": "guard-runner-slow",
        "status": status,
        "summary": summary,
        "started_at": started,
        "finished_at": _now(),
        "tail": out.strip().splitlines()[-20:] if out.strip() else [],
    }
    WATCH_SLOW.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # Loud on transition INTO broken; don't re-spam a persisting failure.
    if status != "pass" and prior in ("pass", None):
        _flag_status_md(status, summary)

    # B2b secondary hook -- see _run_twin_gauntlet_conductor_hook's docstring.
    # Independent of this run's pass/fail/timeout outcome above.
    _run_twin_gauntlet_conductor_hook()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
