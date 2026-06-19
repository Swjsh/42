"""Kitchen daemon -- 24/7 autonomous Chef R&D worker.

Reads cook-queue.jsonl, picks pending tasks ordered by priority+age, runs each
through the free-tier model ladder via chef_nemotron's CHEF_SYSTEM_PROMPT +
call_minimax(). Writes outputs to strategy/candidates/. Loops forever.

PER CLAUDE.md OP-30 (free-tier-first) + OP-22 (don't stop cooking) + OP-25
(engine-benefit autonomy). Per J directive 2026-05-21 "I need 24/7 free model
cooking ... Claude is the driver ... I am not any part of this at all."

ARCHITECTURE:
  cook-queue.jsonl  : append-only event log
      {"event": "create", "task_id": ..., "task": ..., "priority": ..., "ts": ...}
      {"event": "claim",   "task_id": ..., "ts": ..., "by_pid": ...}
      {"event": "complete","task_id": ..., "ts": ..., "output_path": ..., "cost_usd": ..., "model": ..., "tier": ...}
      {"event": "fail",    "task_id": ..., "ts": ..., "error": ..., "retry_count": ...}

  cook-status.json  : snapshot of current state per task_id (rewritten atomically)
  kitchen-daemon.pid: own PID + start time

OPERATING LOOP:
  1. Reap stale claims (in_progress > 30 min) -- they crashed, requeue
  2. Read queue, build {task_id: latest_event} map
  3. Find oldest PENDING task at HIGHEST priority
  4. Claim it (append "claim" event)
  5. Run chef_nemotron logic in-process (import + call)
  6. On success: append "complete" event + write output
     On fail: append "fail" event + bump retry_count; if retry < 3, requeue;
              else mark failed-permanent
  7. Sleep 60s, loop

HARD GUARDRAILS (enforced in code):
  * Never modifies automation/prompts/heartbeat*.md
  * Never modifies automation/state/params*.json
  * Never modifies CLAUDE.md
  * Never places orders
  * Daily-spend hard cap: $3/day on tier-3 paid fallback -- if breached, queue
    pauses (only :free tiers allowed for the rest of the day)
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional


REPO = Path(__file__).resolve().parents[2]
STATE_DIR = REPO / "automation" / "state"
QUEUE_FILE = STATE_DIR / "cook-queue.jsonl"
STATUS_FILE = STATE_DIR / "kitchen-status.json"
PID_FILE = STATE_DIR / "kitchen-daemon.pid"
STATUS_MD = REPO / "automation" / "overnight" / "STATUS.md"

sys.path.insert(0, str(REPO / "setup" / "scripts"))

# Import chef_nemotron's system prompt + model ladder + writer
from chef_nemotron import (  # noqa: E402
    CHEF_SYSTEM_PROMPT,
    MODEL_LADDER,
    _call_with_ladder,
    _write_candidate,
    _slugify,
    _gather_common_inputs,
)


_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# Configuration
SLEEP_BETWEEN_TASKS_S = 60
SLEEP_ON_EMPTY_QUEUE_S = 300         # 5 min when nothing to do
STALE_CLAIM_TIMEOUT_S = 1800         # 30 min => requeue
MAX_RETRY_PER_TASK = 3
PAID_TIER_DAILY_CAP_USD = 3.00       # if breached, refuse tier-3 paid calls for the rest of the day
SLEEP_AFTER_RATE_LIMIT_S = 600       # 10 min when free tiers all 429 (upper bound only — see D4)
MAX_TOKENS_PER_COOK = 10_000
HEARTBEAT_STATUS_INTERVAL_S = 60     # rewrite kitchen-status.json this often even if idle
TIER_429_COOLDOWN_S = 300.0          # D4: per-tier 429 cooldown (5 min)

PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}

# ────────────────────────────────────────────────────────────────────────────
# D4: Per-tier 429 cooldowns — routes tasks to available tiers without
# waiting the full SLEEP_AFTER_RATE_LIMIT_S when only some tiers are blocked.
# State lives in module-level dicts; protected by _TIER_LOCK.
# ────────────────────────────────────────────────────────────────────────────

_TIER_429_UNTIL: dict[int, float] = {}  # tier_idx -> monotonic time when it recovers
_TIER_LOCK = threading.Lock()


def _build_effective_ladder(paid_blocked: bool) -> list[str]:
    """Return MODEL_LADDER with 429-cooled and (if blocked) paid tiers removed."""
    now = time.monotonic()
    with _TIER_LOCK:
        blocked_tiers = {i for i, t in _TIER_429_UNTIL.items() if t > now}
    result = []
    for i, model in enumerate(MODEL_LADDER):
        if i in blocked_tiers:
            continue
        if paid_blocked and not model.endswith(":free"):
            continue
        result.append(model)
    return result


def _update_tier_429_state(result: dict) -> None:
    """Infer which tiers 429'd from the task result and mark them cooling."""
    ladder_used = int(result.get("ladder_used", -1))
    ok = result.get("ok", False)
    now = time.monotonic()
    recovery = now + TIER_429_COOLDOWN_S
    if ok and ladder_used > 0:
        # Tiers 0..(ladder_used-1) failed — mark them blocked
        with _TIER_LOCK:
            for i in range(ladder_used):
                _TIER_429_UNTIL[i] = recovery
    elif not ok and ladder_used == -1:
        # All tiers failed — mark all free tiers blocked
        with _TIER_LOCK:
            for i, model in enumerate(MODEL_LADDER):
                if model.endswith(":free"):
                    _TIER_429_UNTIL[i] = recovery


def _tier_min_sleep_s() -> float:
    """Return seconds until the next tier unblocks (for smart sleep on all-tiers-429)."""
    now = time.monotonic()
    with _TIER_LOCK:
        futures = [t for t in _TIER_429_UNTIL.values() if t > now]
    return min(futures) - now if futures else 0.0

# ────────────────────────────────────────────────────────────────────────────
# Grinder registry — pure-Python parameter sweep scripts wired into the loop
# ────────────────────────────────────────────────────────────────────────────

# backtest/ is one level below REPO; grinders are invoked with cwd=_BACKTEST_DIR
_BACKTEST_DIR = REPO / "backtest"
_GRINDER_STATE = _BACKTEST_DIR / "autoresearch" / "_state"

GRINDER_MAX_WORKERS = 4
GRINDER_POLL_INTERVAL_S = 30
GRINDER_TIMEOUT_S = 7200          # 2 h hard cap per grinder task
GRINDER_COOLDOWN_H = 4.0          # skip re-seed if ran within this many hours
GRINDER_MIN_FREE_BEFORE_SKIP = 3  # skip grinder if this many high/critical LLM tasks are pending

# Registry: name -> module + state_dir + defaults
GRINDER_REGISTRY: dict[str, dict] = {
    "overnight_grinder": {
        "module": "autoresearch.overnight_grinder",
        "state_dir": _GRINDER_STATE / "overnight_grinder",
        "default_hours": 8.0,   # bumped from 2.0 — full 432-combo sweep needs 6-8h
        "cooldown_h": 10.0,     # only re-queue after previous run fully finishes
        "description": "General v14/v15 parameter sweep — 432 combos, wide_pnl differentiator",
    },
    "v14_enhanced_grinder": {
        "module": "autoresearch.v14_enhanced_grinder",
        "state_dir": _GRINDER_STATE / "v14_enhanced_stage1",
        "default_hours": 8.0,   # bumped from 2.0 — 540-combo sweep
        "cooldown_h": 10.0,
        "description": "V14E variant sweep — includes 5/12 anchor day + SNIPER-style profit-lock knobs",
    },
    "sniper_overnight_grinder": {
        "module": "autoresearch.sniper_overnight_grinder",
        "state_dir": _GRINDER_STATE / "sniper_stage1",
        "default_hours": 2.0,
        "description": "SNIPER_LEVEL_BREAK parameter sweep — ★★+ level break triggers",
    },
    "bullish_grinder": {
        "module": "autoresearch.bullish_grinder",
        "state_dir": _GRINDER_STATE / "bullish_grinder",
        "default_hours": 2.0,
        "description": "BULLISH_RECLAIM_RIDE_THE_RIBBON parameter sweep",
    },
    # ── Extended grinders (T12 2026-05-21) ──────────────────────────────────
    "regime_switcher_grinder": {
        "module": "autoresearch.regime_switcher_grinder",
        "state_dir": _GRINDER_STATE / "regime_switcher_stage1",  # fixed: was "regime_switcher"
        "default_hours": 2.0,
        "cooldown_h": 6.0,  # slower rotation — wide sweep
        "description": "Regime-switching parameter sweep — VIX-regime-based filter knobs",
    },
    "vwap_overnight_grinder": {
        "module": "autoresearch.vwap_overnight_grinder",
        "state_dir": _GRINDER_STATE / "vwap_stage1",  # fixed: was "vwap_overnight"
        "default_hours": 2.0,
        "cooldown_h": 4.0,
        "description": "VWAP anchored entry sweep — VWAP reclaim / rejection combos",
    },
    "opening_drive_fade_grinder": {
        "module": "autoresearch.opening_drive_fade_grinder",
        "state_dir": _GRINDER_STATE / "opening_drive_fade_stage1",  # fixed: was "opening_drive_fade"
        "default_hours": 2.0,
        "cooldown_h": 4.0,
        "description": "Opening drive fade sweep — 09:30-10:00 exhaustion reversal knobs",
    },
    "sniper_stage2_grinder": {
        "module": "autoresearch.sniper_stage2_grinder",
        "state_dir": _GRINDER_STATE / "sniper_stage2",
        "default_hours": 1.5,
        "cooldown_h": 8.0,  # only run after sniper stage1 has fresh keepers
        "description": "SNIPER_LEVEL_BREAK Stage-2 refinement — refines top-5 keepers from stage1",
    },
    "shotgun_scalper_grinder": {
        "module": "autoresearch.shotgun_scalper_grinder",
        "state_dir": _GRINDER_STATE / "shotgun_scalper_stage1",
        "default_hours": 3.0,
        "cooldown_h": 6.0,
        "description": "SHOTGUN_SCALPER Stage-1 sweep — 2160-combo grid, strict keeper gates",
    },
    "sniper_real_fills_grinder": {
        "module": "autoresearch.sniper_real_fills_grinder",
        "state_dir": _GRINDER_STATE / "sniper_real_fills_stage1",
        "default_hours": 2.0,
        "cooldown_h": 8.0,  # run after sniper stage1/2 has fresh keepers
        "description": "SNIPER_LEVEL_BREAK real-fills validation grinder — OPRA fills vs BS-sim comparison",
    },
}


def _grinder_last_run_hours_ago(script_name: str) -> Optional[float]:
    """Return hours since the grinder last wrote progress.json, or None if never ran."""
    info = GRINDER_REGISTRY.get(script_name, {})
    progress_file = Path(info.get("state_dir", "")) / "progress.json"
    if not progress_file.exists():
        return None
    try:
        prog = json.loads(progress_file.read_text(encoding="utf-8"))
        last_update = prog.get("last_update") or prog.get("completed_at", "")
        if not last_update:
            return None
        lu_dt = datetime.fromisoformat(last_update.replace("Z", "+00:00"))
        if lu_dt.tzinfo is None:
            lu_dt = lu_dt.replace(tzinfo=datetime.now(timezone.utc).tzinfo)
        return (datetime.now(timezone.utc) - lu_dt.astimezone(timezone.utc)).total_seconds() / 3600
    except (json.JSONDecodeError, OSError, ValueError, AttributeError):
        return None


# ────────────────────────────────────────────────────────────────────────────
# DST-aware ET helper
# ────────────────────────────────────────────────────────────────────────────


def _et_offset_hours(dt_utc: datetime) -> int:
    y = dt_utc.year
    march = datetime(y, 3, 1, tzinfo=timezone.utc)
    days_to_sun = (6 - march.weekday()) % 7
    dst_start_utc = (march + timedelta(days=days_to_sun + 7)).replace(hour=7)
    nov = datetime(y, 11, 1, tzinfo=timezone.utc)
    days_to_sun = (6 - nov.weekday()) % 7
    dst_end_utc = (nov + timedelta(days=days_to_sun)).replace(hour=6)
    return -4 if (dst_start_utc <= dt_utc < dst_end_utc) else -5


def _et_now() -> datetime:
    now_utc = datetime.now(timezone.utc)
    return (now_utc + timedelta(hours=_et_offset_hours(now_utc))).replace(tzinfo=None)


# Headless launch redirect
if sys.platform == "win32" and os.path.basename(sys.executable).lower() == "pythonw.exe":
    _log_dir = STATE_DIR / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _today = _et_now().strftime("%Y-%m-%d")
    sys.stdout = open(_log_dir / f"kitchen-daemon-{_today}.stdout.log", "a", buffering=1, encoding="utf-8")
    sys.stderr = open(_log_dir / f"kitchen-daemon-{_today}.stderr.log", "a", buffering=1, encoding="utf-8")


def _log(msg: str) -> None:
    ts = _et_now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts} ET] {msg}", flush=True)


# ────────────────────────────────────────────────────────────────────────────
# Queue + status I/O
# ────────────────────────────────────────────────────────────────────────────


def _append_event(event: dict) -> None:
    """Append a single event row to the queue JSONL. Best-effort."""
    event = dict(event)  # don't mutate caller's dict
    event.setdefault("ts", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    try:
        QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(QUEUE_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, separators=(",", ":")) + "\n")
    except OSError as exc:
        _log(f"WARN append_event failed: {exc}")


def _load_queue() -> dict[str, dict]:
    """Return {task_id: collapsed_state} from all queue events.

    Collapsed state fields:
      task_id, task, priority, status, created_at, claimed_at, completed_at,
      output_path, cost_usd, model, tier, retry_count, last_error
    """
    out: dict[str, dict] = {}
    if not QUEUE_FILE.exists():
        return out
    bad_lines = 0
    try:
        # errors="replace": a single stray non-UTF-8 byte (e.g. a cp1252 0x97
        # em-dash) degrades to one replacement char instead of raising
        # UnicodeDecodeError mid-file and truncating the whole queue read.
        with open(QUEUE_FILE, encoding="utf-8", errors="replace") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    # Skip THIS malformed line only; never abort the whole read.
                    bad_lines += 1
                    if bad_lines <= 5:
                        _log(f"WARN load_queue: skipping malformed line {lineno}")
                    continue
                tid = ev.get("task_id")
                if not tid:
                    continue
                kind = ev.get("event")
                state = out.get(tid, {
                    "task_id": tid,
                    "status": "pending",
                    "retry_count": 0,
                    "cost_usd": 0.0,
                })
                if kind == "create":
                    state["task"] = ev.get("task", "")
                    state["priority"] = ev.get("priority", "medium")
                    state["created_at"] = ev.get("ts")
                    state["source"] = ev.get("source", "manual")
                    state["status"] = "pending"
                    # Grinder-sweep extra fields (ignored for llm_cook tasks)
                    state["task_type"] = ev.get("task_type", "llm_cook")
                    state["script_name"] = ev.get("script_name", "")
                    state["grinder_hours"] = float(ev.get("hours", 2.0))
                    state["grinder_workers"] = int(ev.get("workers", GRINDER_MAX_WORKERS))
                elif kind == "claim":
                    state["status"] = "in_progress"
                    state["claimed_at"] = ev.get("ts")
                    state["claimed_by_pid"] = ev.get("by_pid")
                elif kind == "complete":
                    state["status"] = "completed"
                    state["completed_at"] = ev.get("ts")
                    state["output_path"] = ev.get("output_path")
                    state["cost_usd"] = float(ev.get("cost_usd", 0.0) or 0.0)
                    state["model"] = ev.get("model")
                    state["tier"] = ev.get("tier")
                elif kind == "fail":
                    state["retry_count"] = state.get("retry_count", 0) + 1
                    state["last_error"] = ev.get("error", "")
                    if state["retry_count"] >= MAX_RETRY_PER_TASK:
                        state["status"] = "failed_permanent"
                    else:
                        state["status"] = "pending"  # requeue
                elif kind == "requeue":
                    state["status"] = "pending"
                    state["requeued_reason"] = ev.get("reason", "")
                out[tid] = state
    except OSError as exc:
        _log(f"WARN load_queue: {exc}")
    if bad_lines:
        _log(f"WARN load_queue: skipped {bad_lines} malformed line(s) total")
    return out


def _atomic_write_status(status: dict) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = STATUS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(status, indent=2), encoding="utf-8")
        tmp.replace(STATUS_FILE)
    except OSError as exc:
        _log(f"WARN status write: {exc}")


def _write_status_snapshot(queue: dict[str, dict], *, idle: bool, current_task: Optional[str] = None) -> None:
    now = _et_now()
    by_status: dict[str, int] = {}
    by_priority: dict[str, int] = {}
    recent_completed = []
    for tid, state in queue.items():
        s = state.get("status", "pending")
        by_status[s] = by_status.get(s, 0) + 1
        if s == "pending":
            p = state.get("priority", "medium")
            by_priority[p] = by_priority.get(p, 0) + 1
        if s == "completed":
            recent_completed.append({
                "task_id": tid[:8],
                "task": (state.get("task") or "")[:120],
                "completed_at": state.get("completed_at"),
                "cost_usd": state.get("cost_usd", 0.0),
                "model": state.get("model"),
                "tier": state.get("tier"),
                "output_path": state.get("output_path"),
            })
    recent_completed.sort(key=lambda r: (r.get("completed_at") or ""), reverse=True)
    today_cost = sum(r.get("cost_usd", 0.0) or 0.0
                     for r in recent_completed
                     if (r.get("completed_at") or "")[:10] == datetime.now(timezone.utc).date().isoformat())

    status = {
        "updated_at_et": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "daemon_pid": os.getpid(),
        "daemon_alive": True,
        "idle": idle,
        "current_task_id": current_task,
        "queue_summary": {
            "by_status": by_status,
            "by_priority_pending": by_priority,
            "total": len(queue),
        },
        "today_cost_usd_paid_tier": round(today_cost, 4),
        "today_cost_cap_usd": PAID_TIER_DAILY_CAP_USD,
        "recent_completed_top_10": recent_completed[:10],
        "model_ladder": MODEL_LADDER,
    }
    _atomic_write_status(status)


def _update_status_md(
    queue: dict[str, dict],
    *,
    last_cook_model: str = "?",
    last_cook_cost: float = 0.0,
    last_cook_ts: Optional[datetime] = None,
) -> None:
    """Write a one-line summary into the ## Kitchen section of STATUS.md.

    Finds or creates a ``## Kitchen`` header, replaces the line immediately
    after it, and writes back atomically (tmp → rename).  Never touches any
    other section.
    """
    try:
        # Compute values
        now_et = _et_now()
        n_pending = sum(1 for s in queue.values() if s.get("status") == "pending")
        if last_cook_ts is not None:
            elapsed_s = (now_et - last_cook_ts).total_seconds()
            min_ago = max(0, int(elapsed_s / 60))
        else:
            min_ago = 0

        summary_line = (
            f"Kitchen: alive, queue {n_pending} pending, "
            f"last cook {min_ago} min ago, "
            f"today ${_today_paid_spend(queue):.2f}, "
            f"model={last_cook_model}"
        )

        # Read existing file (or start empty)
        STATUS_MD.parent.mkdir(parents=True, exist_ok=True)
        existing = STATUS_MD.read_text(encoding="utf-8") if STATUS_MD.exists() else ""
        lines = existing.splitlines(keepends=True)

        # Find the ## Kitchen header
        kitchen_idx: Optional[int] = None
        for i, line in enumerate(lines):
            if line.rstrip("\n\r") == "## Kitchen":
                kitchen_idx = i
                break

        if kitchen_idx is None:
            # Append a new section at the end
            if lines and not lines[-1].endswith("\n"):
                lines.append("\n")
            lines.append("\n## Kitchen\n")
            lines.append(summary_line + "\n")
        else:
            # Replace (or insert) the line immediately after the header
            content_idx = kitchen_idx + 1
            if content_idx < len(lines):
                # Check if it's a content line (not another section header)
                if not lines[content_idx].startswith("##"):
                    lines[content_idx] = summary_line + "\n"
                else:
                    # Insert before the next section
                    lines.insert(content_idx, summary_line + "\n")
            else:
                lines.append(summary_line + "\n")

        new_text = "".join(lines)
        tmp = STATUS_MD.with_suffix(".tmp")
        tmp.write_text(new_text, encoding="utf-8")
        tmp.replace(STATUS_MD)
    except OSError as exc:
        _log(f"WARN _update_status_md: {exc}")


def _today_paid_spend(queue: dict[str, dict]) -> float:
    today = datetime.now(timezone.utc).date().isoformat()
    total = 0.0
    for state in queue.values():
        if state.get("status") != "completed":
            continue
        if not (state.get("completed_at") or "").startswith(today):
            continue
        if state.get("tier") == 3:  # only paid tier counts
            total += float(state.get("cost_usd", 0.0) or 0.0)
    return total


# ────────────────────────────────────────────────────────────────────────────
# Task selection + execution
# ────────────────────────────────────────────────────────────────────────────


def _pick_next_task(queue: dict[str, dict]) -> Optional[dict]:
    """Pick the next pending task: highest priority, then oldest."""
    pendings = [s for s in queue.values() if s.get("status") == "pending"]
    if not pendings:
        return None
    pendings.sort(key=lambda s: (
        PRIORITY_ORDER.get(s.get("priority", "medium"), 99),
        s.get("created_at") or "",
    ))
    return pendings[0]


def _reap_stale_claims(queue: dict[str, dict]) -> int:
    """Mark stale in-progress tasks as pending (their daemon presumably died)."""
    now_utc = datetime.now(timezone.utc)
    reaped = 0
    for state in list(queue.values()):
        if state.get("status") != "in_progress":
            continue
        claimed_at = state.get("claimed_at")
        if not claimed_at:
            continue
        try:
            claimed_dt = datetime.fromisoformat(claimed_at.replace("Z", "+00:00"))
            if claimed_dt.tzinfo is None:
                claimed_dt = claimed_dt.replace(tzinfo=timezone.utc)
            age_s = (now_utc - claimed_dt).total_seconds()
        except (ValueError, AttributeError):
            continue
        if age_s > STALE_CLAIM_TIMEOUT_S:
            _append_event({
                "event": "requeue",
                "task_id": state["task_id"],
                "reason": f"stale_claim age={int(age_s)}s exceeds {STALE_CLAIM_TIMEOUT_S}s",
            })
            reaped += 1
    return reaped


def _build_prompt_for_task(task_desc: str) -> str:
    """Same shape as chef_nemotron._build_task_prompt -- inline common context + task."""
    common = _gather_common_inputs()
    return (
        f"# Task\n\n{task_desc}\n\n"
        "## Inputs (inlined)\n\n"
        f"{common}\n\n"
        "## Your output\n\n"
        "Per the CANDIDATE TEMPLATE in the system prompt: one DRAFT candidate or "
        "analysis (or several separated by `---`). Be concrete, be honest about "
        "unknowns, no preamble, no chain-of-thought in the output."
    )


def _run_task(task_state: dict, *, paid_tier_blocked: bool) -> dict:
    """Execute one cook. Returns a result dict with ok/cost/output_path/tier/model."""
    task_desc = task_state.get("task", "")
    if not task_desc:
        return {"ok": False, "error": "empty_task_description"}

    # D4: build effective ladder — skips paid tiers (if cap hit) AND per-tier 429 cooldowns.
    effective = _build_effective_ladder(paid_blocked=paid_tier_blocked)
    if not effective:
        return {"ok": False, "error": "no_tiers_available_all_cooled_or_blocked"}
    global MODEL_LADDER
    saved_ladder = list(MODEL_LADDER)
    MODEL_LADDER = effective
    try:
        prompt = _build_prompt_for_task(task_desc)
        slug = _slugify(task_desc[:80])
        result = _call_with_ladder(
            prompt,
            max_tokens=MAX_TOKENS_PER_COOK,
            task_id=f"kitchen.cook.{slug[:30]}",
        )
    finally:
        MODEL_LADDER = saved_ladder

    # D4: update per-tier cooldown state based on what succeeded/failed
    _update_tier_429_state(result)

    if not result.get("ok"):
        return {"ok": False, "error": result.get("error", "unknown"),
                "tier": result.get("ladder_used", -1),
                "model": result.get("model_attempted", "unknown"),
                "cost_usd": float(result.get("cost_usd", 0.0) or 0.0)}

    content = (result.get("content") or "").strip()
    if not content:
        return {"ok": False, "error": "empty_content",
                "tier": result.get("ladder_used", -1),
                "model": result.get("model", "unknown"),
                "cost_usd": float(result.get("cost_usd", 0.0) or 0.0)}

    # Strip leading code fence if wrapped
    if content.startswith("```"):
        first_nl = content.find("\n")
        if first_nl > 0:
            content = content[first_nl + 1:]
        if content.rstrip().endswith("```"):
            content = content.rsplit("```", 1)[0].rstrip()

    model = result.get("model", "unknown")
    cost = float(result.get("cost_usd", 0.0) or 0.0)
    tier = int(result.get("ladder_used", -1))
    target = _write_candidate(content, slug, model=model, cost_usd=cost, ladder_used=tier)
    return {
        "ok": True,
        "output_path": str(target.relative_to(REPO)),
        "tier": tier,
        "model": model,
        "cost_usd": cost,
    }


# ────────────────────────────────────────────────────────────────────────────
# Grinder task runner
# ────────────────────────────────────────────────────────────────────────────


def _read_keepers(keepers_file: Path, max_keepers: int = 5) -> list[dict]:
    """Read the top N entries from a keepers.jsonl (sorted by wide_pnl desc)."""
    if not keepers_file.exists():
        return []
    rows: list[dict] = []
    try:
        with open(keepers_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    rows.sort(key=lambda k: float(k.get("wide_pnl", k.get("aggregate_pnl", 0)) or 0), reverse=True)
    return rows[:max_keepers]


def _format_grinder_summary(task_state: dict, keepers: list[dict], progress_file: Path) -> str:
    """Format a Markdown DRAFT candidate doc summarising grinder results."""
    script_name = task_state.get("script_name", "grinder")
    task_desc = task_state.get("task", "")

    prog: dict = {}
    if progress_file.exists():
        try:
            prog = json.loads(progress_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    completed = prog.get("completed", "?")
    total = prog.get("total_combos", "?")
    keepers_n = prog.get("keepers", len(keepers))
    best_edge = prog.get("best_edge_capture", "?")
    best_pnl = prog.get("best_wide_pnl", "?")

    lines = [
        f"# GRINDER RESULTS: {script_name.upper()}",
        "",
        f"**Task:** {task_desc}",
        f"**Combos swept:** {completed}/{total}  |  **Keepers:** {keepers_n}",
        f"**Best edge_capture:** {best_edge}  |  **Best wide_pnl:** ${best_pnl}",
        f"**Generated:** {_et_now().strftime('%Y-%m-%d %H:%M')} ET",
        "",
        "## Top Keepers (sorted by wide_pnl)",
        "",
    ]

    if not keepers:
        lines.append("*(no keepers — all combos failed floor gates or grinder produced no output)*")
    else:
        for i, k in enumerate(keepers[:5], 1):
            pnl = k.get("wide_pnl", k.get("aggregate_pnl", "?"))
            edge = k.get("edge_capture", "?")
            wr = k.get("win_rate", k.get("wide_wr", "?"))
            lines.append(f"### Keeper #{i}")
            lines.append(f"- **wide_pnl:** {pnl}  |  **edge_capture:** {edge}  |  **WR:** {wr}")
            skip_keys = {"wide_pnl", "aggregate_pnl", "edge_capture", "win_rate", "wide_wr",
                         "positive_quarters", "max_drawdown", "top5_pct", "quarter_pnl",
                         "wide_n_trades", "passed_floors"}
            params = {k2: v for k2, v in k.items() if k2 not in skip_keys}
            if params:
                lines.append(f"- **params:** `{json.dumps(params, separators=(',', ':'))}`")
            lines.append("")

    lines += [
        "## OP-20 Disclosures",
        f"- Sample bias: selected from {total} combos — overfit risk present",
        "- OOS validation: walk-forward required before ratification (OP-20)",
        "- Real-fills: simulator_real.py required before production (OP-20)",
        "- **DRAFT** — J ratification required per Rule 9 before any heartbeat.md / params.json change",
    ]
    return "\n".join(lines)


def _enqueue_grinder_analysis(original_task_desc: str, script_name: str, keepers: list[dict]) -> None:
    """Auto-enqueue a Nemotron LLM task to interpret the top grinder keepers."""
    if not keepers:
        return
    top = keepers[0]
    pnl = top.get("wide_pnl", top.get("aggregate_pnl", "?"))
    edge = top.get("edge_capture", "?")
    wr = top.get("win_rate", top.get("wide_wr", "?"))

    keepers_brief = json.dumps(keepers[:3], separators=(",", ":"))[:600]
    analysis_task = (
        f"Interpret {script_name} grinder output: {len(keepers)} keepers found. "
        f"Top: wide_pnl={pnl}, edge_capture={edge}, WR={wr}. "
        f"Original intent: {original_task_desc[:120]}. "
        f"For each keeper assess: (1) genuine edge or overfit? "
        f"(2) which knob changes drove improvement vs baseline? "
        f"(3) OP-20 disclosures that apply? "
        f"(4) promote to LEADERBOARD or needs OOS walk-forward first? "
        f"Keepers JSON: {keepers_brief}"
    )
    tid = enqueue_task(analysis_task, priority="high", source="grinder-auto")
    _log(f"GRINDER_SWEEP auto-enqueued analysis task_id={tid[:8]}")


def _run_grinder_task(task_state: dict) -> dict:
    """Spawn a pure-Python parameter-sweep grinder, monitor it, then auto-enqueue LLM analysis.

    Returns a result dict compatible with _run_task (ok/cost/output_path/tier/model).
    Grinder cost is $0 — pure Python, no LLM in the loop.
    """
    script_name = task_state.get("script_name", "overnight_grinder")
    info = GRINDER_REGISTRY.get(script_name)
    if not info:
        return {"ok": False, "error": f"unknown grinder script: {script_name!r} — not in GRINDER_REGISTRY"}

    hours = float(task_state.get("grinder_hours", info.get("default_hours", 2.0)))
    workers = int(task_state.get("grinder_workers", GRINDER_MAX_WORKERS))
    module = info["module"]
    state_dir = Path(info["state_dir"])
    progress_file = state_dir / "progress.json"
    keepers_file = state_dir / "keepers.jsonl"

    _log(f"GRINDER_SWEEP start script={script_name} module={module} hours={hours} workers={workers}")

    # Use system pythonw.exe (GUI subsystem) — never creates a console window.
    # Grinder scripts use the same hardcoded path for mp.set_executable so Pool workers also
    # use GUI-subsystem. stdout/stderr=DEVNULL + CREATE_NO_WINDOW are belt-and-suspenders.
    # Never fall back to sys.executable — if sys.executable were the venv stub (L41), every
    # worker spawn would re-exec as console python.exe and flash WindowsTerminal.
    _sys_pythonw = Path(r"C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe")
    if not _sys_pythonw.exists():
        _log(f"GRINDER_SWEEP ABORT: system pythonw missing at {_sys_pythonw}")
        return {"ok": False, "error": f"system pythonw not found: {_sys_pythonw}"}
    python_exe = _sys_pythonw

    # Build env: inherit current env + venv site-packages so grinder can import pandas/numpy
    env = os.environ.copy()
    venv_site = _BACKTEST_DIR / ".venv" / "Lib" / "site-packages"
    if venv_site.exists():
        existing_pp = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(venv_site) + (os.pathsep + existing_pp if existing_pp else "")
        env["VIRTUAL_ENV"] = str(_BACKTEST_DIR / ".venv")

    # FIX 2026-05-24: Delete stale progress.json BEFORE spawning so the monitor
    # loop doesn't see a previous run's "completed"/"deadline_reached" status and
    # immediately call proc.wait(timeout=10) on the just-launched (not yet ready) process.
    # Root cause of overnight_grinder failing in 10s after the real-fills upgrade.
    if progress_file.exists():
        try:
            progress_file.unlink()
            _log(f"GRINDER_SWEEP cleared stale progress.json for {script_name}")
        except OSError as exc:
            _log(f"GRINDER_SWEEP WARN could not clear progress.json: {exc}")

    cmd = [str(python_exe), "-m", module, "--hours", str(hours), "--workers", str(workers)]
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(_BACKTEST_DIR),
            env=env,
            creationflags=_CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"grinder spawn failed: {type(exc).__name__}: {exc}"}

    _log(f"GRINDER_SWEEP pid={proc.pid} spawned — polling every {GRINDER_POLL_INTERVAL_S}s")
    # FIX 2026-05-24: Use hours-based deadline so 8h sweeps aren't killed at 2h.
    # GRINDER_TIMEOUT_S (7200s=2h) is now a fallback floor only; grinders with
    # hours > 2 get a proportional deadline with 10-min buffer.
    task_timeout_s = max(GRINDER_TIMEOUT_S, hours * 3600 + 600)
    deadline = time.monotonic() + task_timeout_s
    _log(f"GRINDER_SWEEP deadline={task_timeout_s/3600:.1f}h (hours={hours} + 10min buffer)")
    last_log_t = time.monotonic()
    final_status = "unknown"

    while True:
        ret = proc.poll()  # None = still running

        # Parse progress.json for a clean status signal
        grinder_status = None
        completed = 0
        total = 0
        n_keepers = 0
        if progress_file.exists():
            try:
                prog = json.loads(progress_file.read_text(encoding="utf-8"))
                grinder_status = prog.get("status")
                completed = prog.get("completed", 0)
                total = prog.get("total_combos", 0)
                n_keepers = prog.get("keepers", 0)
            except (json.JSONDecodeError, OSError):
                pass

        if grinder_status in ("completed", "deadline_reached"):
            # Both are terminal states — "completed" means all combos swept,
            # "deadline_reached" means hours limit hit (still valid, may have keepers)
            final_status = f"done_via_progress_{grinder_status}"
            _log(f"GRINDER_SWEEP done ({grinder_status}) combos={completed}/{total} keepers={n_keepers}")
            if ret is None:
                try:
                    proc.wait(timeout=30)  # let it clean up (30s — was 10s, too short)
                except subprocess.TimeoutExpired:
                    # FIX 2026-05-24: Don't propagate — process is still alive but grinder
                    # reported done via progress.json. Kill it and move on.
                    _log(f"GRINDER_SWEEP WARN process still alive after 30s cleanup wait — terminating pid={proc.pid}")
                    try:
                        proc.terminate()
                    except OSError:
                        pass
            break

        if ret is not None:
            final_status = f"process_exited_rc={ret}"
            _log(f"GRINDER_SWEEP process exited rc={ret} combos={completed}/{total} keepers={n_keepers}")
            break

        if time.monotonic() > deadline:
            final_status = "timeout"
            _log(f"GRINDER_SWEEP timeout {GRINDER_TIMEOUT_S}s — terminating pid={proc.pid}")
            try:
                proc.terminate()
                proc.wait(timeout=15)
            except OSError:
                pass
            break

        # Progress heartbeat every 5 min
        if time.monotonic() - last_log_t > 300:
            pct = f"{completed}/{total}" if total else "?"
            _log(f"GRINDER_SWEEP heartbeat {pct} keepers={n_keepers}")
            last_log_t = time.monotonic()

        time.sleep(GRINDER_POLL_INTERVAL_S)

    # Read best keepers and write a summary candidate doc
    keepers = _read_keepers(keepers_file, max_keepers=5)
    summary_slug = _slugify(f"grinder-{script_name}-{_et_now().strftime('%Y%m%d-%H%M')}")
    summary_content = _format_grinder_summary(task_state, keepers, progress_file)
    target = _write_candidate(summary_content, summary_slug, model="grinder-python", cost_usd=0.0, ladder_used=-1)
    _log(f"GRINDER_SWEEP summary -> {target.relative_to(REPO)}")

    # Auto-enqueue Nemotron interpretation if we have something to analyse
    if keepers:
        _enqueue_grinder_analysis(task_state.get("task", ""), script_name, keepers)
    else:
        _log(f"GRINDER_SWEEP no keepers ({final_status}) — no analysis task enqueued")

    return {
        "ok": True,
        "output_path": str(target.relative_to(REPO)),
        "tier": -1,          # not an LLM tier
        "model": "grinder-python",
        "cost_usd": 0.0,     # pure Python, $0
    }


# ────────────────────────────────────────────────────────────────────────────
# PID file management
# ────────────────────────────────────────────────────────────────────────────


def _write_pid_file() -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "pid": os.getpid(),
            "started_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "python_exe": sys.executable,
        }
        PID_FILE.write_text(json.dumps(payload), encoding="utf-8")
    except OSError as exc:
        _log(f"WARN pid write: {exc}")


def _existing_daemon_alive() -> bool:
    """Check if another daemon is already running (PID file points to live pid)."""
    if not PID_FILE.exists():
        return False
    try:
        payload = json.loads(PID_FILE.read_text(encoding="utf-8"))
        other_pid = int(payload.get("pid", -1))
        if other_pid <= 0 or other_pid == os.getpid():
            return False
        # cross-platform liveness probe via WMI (Windows) or os.kill (POSIX)
        # Avoid os.kill on Windows — WinError 6 + CPython SystemError on stale handles
        # Use WMIC CommandLine check, NOT tasklist — tasklist only checks PID existence
        # and would match any process (e.g. svchost.exe) that reused a dead daemon's PID.
        if sys.platform == "win32":
            try:
                import subprocess as _sp
                out = _sp.run(
                    ["wmic", "process", "where", f"ProcessId={other_pid}",
                     "get", "CommandLine", "/value"],
                    capture_output=True, text=True, timeout=5,
                    creationflags=_CREATE_NO_WINDOW,
                )
                return "kitchen_daemon.py" in out.stdout
            except Exception:
                return False
        else:
            try:
                os.kill(other_pid, 0)
                return True
            except (OSError, ProcessLookupError):
                return False
    except (OSError, json.JSONDecodeError, ValueError):
        return False


def _cleanup_pid_file() -> None:
    try:
        PID_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def _install_signal_handlers() -> None:
    def handler(signum, frame):
        _log(f"signal {signum} received -- shutting down cleanly")
        _cleanup_pid_file()
        sys.exit(0)
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, handler)
        except (ValueError, OSError):
            pass


_heartbeat_stop = threading.Event()


def _start_status_heartbeat() -> threading.Thread:
    """Background thread that touches the status file mtime every 30s.
    Keeps the file 'fresh' for the keepalive wedge-detection check even when
    the main loop is blocked inside a long Nemotron cook. Best-effort -- if the
    status file doesn't exist yet, the touch is a no-op.
    """
    def _tick():
        while not _heartbeat_stop.is_set():
            try:
                if STATUS_FILE.exists():
                    now = time.time()
                    os.utime(STATUS_FILE, (now, now))
            except OSError:
                pass
            # Wait but stay responsive to stop signal
            _heartbeat_stop.wait(timeout=30.0)
    t = threading.Thread(target=_tick, name="kitchen-status-heartbeat", daemon=True)
    t.start()
    return t


# ────────────────────────────────────────────────────────────────────────────
# Main loop
# ────────────────────────────────────────────────────────────────────────────


def main() -> int:
    if _existing_daemon_alive():
        _log("another daemon is already alive; exiting")
        return 0

    _write_pid_file()
    _install_signal_handlers()
    _start_status_heartbeat()
    _log(f"kitchen daemon started pid={os.getpid()}")
    last_status_write = 0.0
    _STOP_FLAG = STATE_DIR / "kitchen-daemon.stop"

    try:
        while True:
            # Graceful stop: write automation/state/kitchen-daemon.stop to halt cleanly
            if _STOP_FLAG.exists():
                _log(f"stop flag found at {_STOP_FLAG} — exiting cleanly")
                try:
                    _STOP_FLAG.unlink()
                except OSError:
                    pass
                break

            queue = _load_queue()
            reaped = _reap_stale_claims(queue)
            if reaped:
                _log(f"reaped {reaped} stale claim(s)")
                queue = _load_queue()  # reload after writes

            paid_spend = _today_paid_spend(queue)
            paid_blocked = paid_spend >= PAID_TIER_DAILY_CAP_USD
            if paid_blocked:
                _log(f"PAID TIER BLOCKED today_spend=${paid_spend:.4f} >= cap=${PAID_TIER_DAILY_CAP_USD:.2f}")

            task = _pick_next_task(queue)

            now = time.monotonic()
            if (now - last_status_write) > HEARTBEAT_STATUS_INTERVAL_S or task is not None:
                _write_status_snapshot(queue, idle=(task is None), current_task=(task["task_id"] if task else None))
                last_status_write = now

            if task is None:
                _log(f"queue empty; sleeping {SLEEP_ON_EMPTY_QUEUE_S}s")
                time.sleep(SLEEP_ON_EMPTY_QUEUE_S)
                continue

            _log(f"claim task_id={task['task_id'][:8]} priority={task.get('priority')} desc={(task.get('task') or '')[:80]}")
            _append_event({
                "event": "claim",
                "task_id": task["task_id"],
                "by_pid": os.getpid(),
            })

            try:
                task_type = task.get("task_type", "llm_cook")
                if task_type == "grinder_sweep":
                    # Check: don't block urgent LLM tasks behind a 2h grinder
                    high_prio_llm = sum(
                        1 for s in queue.values()
                        if s.get("status") == "pending"
                        and s.get("task_type", "llm_cook") != "grinder_sweep"
                        and PRIORITY_ORDER.get(s.get("priority", "medium"), 99)
                        <= PRIORITY_ORDER["high"]
                    )
                    if high_prio_llm >= GRINDER_MIN_FREE_BEFORE_SKIP:
                        _log(
                            f"GRINDER_SWEEP deferred: {high_prio_llm} high/critical LLM tasks pending "
                            f"(threshold={GRINDER_MIN_FREE_BEFORE_SKIP})"
                        )
                        # Requeue at end of current cycle — put it back as pending
                        _append_event({
                            "event": "requeue",
                            "task_id": task["task_id"],
                            "reason": f"deferred: {high_prio_llm} high-priority LLM tasks ahead",
                        })
                        time.sleep(SLEEP_BETWEEN_TASKS_S)
                        continue
                    result = _run_grinder_task(task)
                else:
                    result = _run_task(task, paid_tier_blocked=paid_blocked)
            except Exception as exc:  # noqa: BLE001
                _log(f"EXCEPTION in dispatch: {exc}\n{traceback.format_exc()[:1500]}")
                result = {"ok": False, "error": f"exception: {type(exc).__name__}: {str(exc)[:300]}"}

            _cook_finish_ts = _et_now()
            _cook_model = result.get("model") or "?"
            _cook_cost = float(result.get("cost_usd", 0.0) or 0.0)

            if result["ok"]:
                _log(f"OK task={task['task_id'][:8]} tier={result.get('tier')} cost=${_cook_cost:.4f} -> {result.get('output_path')}")
                _append_event({
                    "event": "complete",
                    "task_id": task["task_id"],
                    "output_path": result.get("output_path"),
                    "cost_usd": _cook_cost,
                    "model": _cook_model,
                    "tier": result.get("tier"),
                })
            else:
                err = result.get("error", "unknown")
                _log(f"FAIL task={task['task_id'][:8]} error={err}")
                _append_event({
                    "event": "fail",
                    "task_id": task["task_id"],
                    "error": err,
                    "tier": result.get("tier", -1),
                })
                # D4: smart sleep — wait only until soonest tier unblocks, not full 600s
                if "RateLimitError" in str(err) or "429" in str(err) or "no_tiers_available" in str(err):
                    min_s = _tier_min_sleep_s()
                    sleep_s = max(30, min(min_s + 10, SLEEP_AFTER_RATE_LIMIT_S))
                    _log(f"all-tier rate-limit; D4 smart-sleep {sleep_s:.0f}s (min_recovery={min_s:.0f}s)")
                    queue = _load_queue()
                    _update_status_md(queue, last_cook_model=_cook_model,
                                      last_cook_cost=_cook_cost, last_cook_ts=_cook_finish_ts)
                    time.sleep(sleep_s)
                    continue

            # Update STATUS.md ## Kitchen section after every cook (success or fail)
            queue = _load_queue()
            _update_status_md(queue, last_cook_model=_cook_model,
                               last_cook_cost=_cook_cost, last_cook_ts=_cook_finish_ts)

            time.sleep(SLEEP_BETWEEN_TASKS_S)
    except KeyboardInterrupt:
        _log("keyboard interrupt; exiting")
    finally:
        _cleanup_pid_file()
        _log("daemon exit")
    return 0


# ────────────────────────────────────────────────────────────────────────────
# CLI helpers (also used by seeder + reviewer)
# ────────────────────────────────────────────────────────────────────────────


def enqueue_task(
    task: str,
    *,
    priority: str = "medium",
    source: str = "manual",
    task_type: str = "llm_cook",
    script_name: str = "",
    hours: float = 2.0,
    workers: int = GRINDER_MAX_WORKERS,
) -> str:
    """Public API: append a CREATE event for a new task. Returns task_id.

    For grinder_sweep tasks, also pass task_type="grinder_sweep", script_name=<name>,
    and optionally hours + workers (defaults: 2h / 4 workers).
    """
    task_id = str(uuid.uuid4())
    event: dict = {
        "event": "create",
        "task_id": task_id,
        "task": task,
        "priority": priority,
        "source": source,
    }
    if task_type != "llm_cook":
        event["task_type"] = task_type
    if script_name:
        event["script_name"] = script_name
        event["hours"] = hours
        event["workers"] = workers
    _append_event(event)
    return task_id


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("run", help="Run the daemon loop (default)")

    enq = sub.add_parser("enqueue", help="Enqueue a single task and exit")
    enq.add_argument("--task", required=True)
    enq.add_argument("--priority", default="medium", choices=list(PRIORITY_ORDER.keys()))
    enq.add_argument("--source", default="manual")
    enq.add_argument("--task-type", default="llm_cook",
                     choices=["llm_cook", "grinder_sweep"],
                     help="Task type: llm_cook (default) or grinder_sweep")
    enq.add_argument("--script-name", default="",
                     help="For grinder_sweep: grinder name from GRINDER_REGISTRY")
    enq.add_argument("--hours", type=float, default=2.0,
                     help="For grinder_sweep: max runtime in hours")
    enq.add_argument("--workers", type=int, default=GRINDER_MAX_WORKERS,
                     help="For grinder_sweep: parallel worker count")

    sub.add_parser("status", help="Print kitchen-status.json + queue summary, then exit")

    args = p.parse_args()
    cmd = args.cmd or "run"

    if cmd == "enqueue":
        tid = enqueue_task(
            args.task,
            priority=args.priority,
            source=args.source,
            task_type=args.task_type,
            script_name=args.script_name,
            hours=args.hours,
            workers=args.workers,
        )
        print(f"enqueued task_id={tid} type={args.task_type}")
        sys.exit(0)
    if cmd == "status":
        if STATUS_FILE.exists():
            print(STATUS_FILE.read_text(encoding="utf-8"))
        queue = _load_queue()
        print(f"\nqueue: {len(queue)} total")
        for s, n in sorted({s.get("status"): 0 for s in queue.values()}.items()):
            pass  # placeholder -- compute below
        by_status = {}
        for s in queue.values():
            by_status[s.get("status")] = by_status.get(s.get("status"), 0) + 1
        for k, v in sorted(by_status.items()):
            print(f"  {k}: {v}")
        sys.exit(0)

    sys.exit(main())
