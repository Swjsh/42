"""kitchen_stage1_runner.py -- the Stage-1 EXECUTION step the Kitchen chef-cook loop was
missing (GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05).

WHY THIS EXISTS: kitchen_provenance_audit.py found 81% of Kitchen verdict files cite no
artifact and 10% cite artifacts that don't exist -- because chef_nemotron's cook path
(`kitchen_daemon._run_task`) only ever asked a free model for a verdict + numbers; nothing
in the loop RAN anything. This script is the fix's execution half: a thin, deterministic
CLI wrapper around the EXISTING Stage-1 single-combo evaluator already used by the overnight
grinder pipeline -- `backtest.autoresearch.overnight_grinder.evaluate_combo` -- invoked with
ONE knob set (the candidate's own) instead of a 200-500-combo sweep. NO new backtest engine:
this calls the same function the grinder calls per-combo, just once, synchronously, in the
calling process (single worker, no multiprocessing pool).

DATA: the base engine's wide-window backtest is BS-synthetic option pricing over historical
SPY/VIX bars (`lib.pricing.black_scholes`, per `runner.load_data` / `run_with_params`) --
mechanism evidence only, NEVER real-fills evidence. Every artifact this script writes says
so explicitly (memory: project_free_kitchen_plan_b_hardened.md).

BOUNDED: measured wall time for one combo (empty combo, wide window 2025-01-01..2026-05-22
plus the 7 J-day cells) = ~65s single-threaded (probe: analysis/kitchen-review/_stage1_manual/
_probe_evalcombo.py, 2026-09-05). That's ~1.1 CPU-minute, far under the 5-minute grind-reaper
threshold (`setup/scripts/_shared.ps1#Stop-StaleClaudeProcesses`) -- this script does NOT need
a reaper exemption because it always finishes before the reaper's window opens. A hard
wall-clock cap (default 480s, `--timeout-s`) is still enforced via a watchdog thread so a
pathological combo can never hang the daemon; on timeout or exception the script writes NO
artifact and exits nonzero with a machine-readable reason on stderr.

SINGLE-WORKER LOCK: a candidate's runner invocation is fully synchronous inside the
daemon's own cook step (no background process, no pool) -- the daemon cannot start a second
one while this is running because it awaits this subprocess before calling the model. A
best-effort file lock (`automation/state/kitchen-stage1-runner.lock`) additionally guards
against two daemon processes (e.g. a stale one the keepalive hasn't reaped yet) racing this
script directly.

USAGE
  backtest/.venv/Scripts/python.exe setup/scripts/kitchen_stage1_runner.py \\
      --combo-json '{"super_stop": -0.20}' --slug my-candidate

OUTPUT (on success)
  Writes analysis/kitchen-review/stage1-runs/{slug}-{ts}.json (the evaluate_combo() result
  dict + provenance metadata: exact command, start/end ts, elapsed_s, engine_note).
  Prints ONE line to stdout: `STAGE1_OK <artifact_relpath>`.
  Appends one line to automation/state/kitchen-stage1-run-log.jsonl (the daemon-owned run
  log kitchen_reviewer.py cross-checks against candidate provenance blocks -- R3).

OUTPUT (on failure/timeout)
  Writes NO artifact. Prints `STAGE1_FAILED <reason>` to stdout. Still appends a
  status=RUNNER-FAILED row to the run log (so the reviewer can tell "never ran" apart from
  "ran and failed").

NEVER touches automation/prompts/heartbeat*.md, automation/state/params*.json, CLAUDE.md.
Never places orders (no MCP available; pure Python + pandas engine).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
BACKTEST_DIR = REPO / "backtest"
RUN_LOG = REPO / "automation" / "state" / "kitchen-stage1-run-log.jsonl"
OUT_DIR = REPO / "analysis" / "kitchen-review" / "stage1-runs"
LOCK_FILE = REPO / "automation" / "state" / "kitchen-stage1-runner.lock"

DEFAULT_TIMEOUT_S = 480.0  # 8 min hard cap; observed runtime ~65s for an empty combo

ENGINE_NOTE = (
    "MECHANISM EVIDENCE ONLY -- BS-synthetic option pricing over historical SPY/VIX bars "
    "(backtest.autoresearch.overnight_grinder.evaluate_combo -> lib.pricing.black_scholes). "
    "NOT real-fills evidence. Per memory project_free_kitchen_plan_b_hardened.md."
)


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "combo"


def _et_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class _Timeout(Exception):
    pass


def _run_with_timeout(fn, timeout_s: float):
    """Run fn() in a daemon thread and enforce a wall-clock cap. On timeout the worker
    thread is abandoned (best-effort -- Python cannot hard-kill a thread) and _Timeout is
    raised so the caller writes NO artifact."""
    result: dict = {}

    def _target():
        try:
            result["value"] = fn()
        except BaseException as exc:  # noqa: BLE001
            result["error"] = exc

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout_s)
    if t.is_alive():
        raise _Timeout(f"exceeded {timeout_s}s wall-time cap")
    if "error" in result:
        raise result["error"]
    return result.get("value")


def _append_run_log(row: dict) -> None:
    RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
    with RUN_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--combo-json", type=str, required=True,
                     help="JSON dict of orchestrator knob overrides -- the candidate's own knobs")
    ap.add_argument("--slug", type=str, default=None, help="candidate slug for the artifact filename")
    ap.add_argument("--timeout-s", type=float, default=DEFAULT_TIMEOUT_S)
    ap.add_argument("--task-id", type=str, default=None, help="kitchen cook-queue task id, for the run log")
    args = ap.parse_args()

    try:
        combo = json.loads(args.combo_json)
        if not isinstance(combo, dict):
            raise ValueError("--combo-json must decode to a JSON object")
    except (json.JSONDecodeError, ValueError) as exc:
        reason = f"bad_combo_json: {exc}"
        print(f"STAGE1_FAILED {reason}")
        _append_run_log({
            "ts": _et_now_iso(), "task_id": args.task_id, "combo": args.combo_json,
            "status": "RUNNER-FAILED", "reason": reason,
        })
        return 2

    slug = _slugify(args.slug or json.dumps(combo, sort_keys=True)[:40])
    command = (
        f"backtest/.venv/Scripts/python.exe setup/scripts/kitchen_stage1_runner.py "
        f"--combo-json '{json.dumps(combo, sort_keys=True)}' --slug {slug}"
    )

    lock_acquired = False
    try:
        LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        # Best-effort exclusive create; stale locks are not auto-broken here on purpose --
        # a held lock means another Stage-1 run is genuinely in flight (single-worker rule).
        fh = open(LOCK_FILE, "x")
        fh.write(f"{_et_now_iso()} pid={__import__('os').getpid()} slug={slug}\n")
        fh.close()
        lock_acquired = True
    except FileExistsError:
        reason = "single_worker_lock_held -- another Stage-1 run is in flight"
        print(f"STAGE1_FAILED {reason}")
        _append_run_log({
            "ts": _et_now_iso(), "task_id": args.task_id, "combo": combo, "slug": slug,
            "status": "RUNNER-FAILED", "reason": reason, "command": command,
        })
        return 3

    t0 = time.time()
    try:
        sys.path.insert(0, str(BACKTEST_DIR))
        from autoresearch.overnight_grinder import evaluate_combo  # noqa: E402

        result = _run_with_timeout(lambda: evaluate_combo(combo), args.timeout_s)
        elapsed_s = round(time.time() - t0, 2)

        OUT_DIR.mkdir(parents=True, exist_ok=True)
        ts_tag = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        artifact_path = OUT_DIR / f"{slug}-{ts_tag}.json"
        artifact_body = {
            "generated_at": _et_now_iso(),
            "slug": slug,
            "task_id": args.task_id,
            "combo": combo,
            "engine": "backtest.autoresearch.overnight_grinder.evaluate_combo",
            "engine_note": ENGINE_NOTE,
            "elapsed_s": elapsed_s,
            "command": command,
            "result": result,
        }
        artifact_path.write_text(json.dumps(artifact_body, indent=2, default=str), encoding="utf-8")
        artifact_rel = str(artifact_path.relative_to(REPO)).replace("\\", "/")

        _append_run_log({
            "ts": _et_now_iso(), "task_id": args.task_id, "combo": combo, "slug": slug,
            "status": "PROVENANCE-OK", "command": command, "artifact": artifact_rel,
            "elapsed_s": elapsed_s,
        })
        print(f"STAGE1_OK {artifact_rel}")
        return 0
    except _Timeout as exc:
        elapsed_s = round(time.time() - t0, 2)
        reason = f"timeout: {exc}"
        _append_run_log({
            "ts": _et_now_iso(), "task_id": args.task_id, "combo": combo, "slug": slug,
            "status": "RUNNER-FAILED", "reason": reason, "command": command,
            "elapsed_s": elapsed_s,
        })
        print(f"STAGE1_FAILED {reason}")
        return 4
    except Exception as exc:  # noqa: BLE001
        elapsed_s = round(time.time() - t0, 2)
        reason = f"{type(exc).__name__}: {exc}"
        _append_run_log({
            "ts": _et_now_iso(), "task_id": args.task_id, "combo": combo, "slug": slug,
            "status": "RUNNER-FAILED", "reason": reason, "command": command,
            "elapsed_s": elapsed_s,
        })
        print(f"STAGE1_FAILED {reason}")
        return 1
    finally:
        if lock_acquired:
            try:
                LOCK_FILE.unlink()
            except OSError:
                pass


if __name__ == "__main__":
    sys.exit(main())
