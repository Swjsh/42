"""Kitchen seeder -- autonomous cook-task generator.

Fires hourly. Reads the project state (leaderboard, lessons-learned, recent
journal, mistakes.md, _chef-inbox/) and asks Nemotron itself to brainstorm 5-10
new cook tasks. Appends them to cook-queue.jsonl via kitchen_daemon.enqueue_task().

PER CLAUDE.md OP-30 + J directive 2026-05-21 "I need 24/7 free model cooking
... pure autonomy ... Claude is the driver."

GUARDS:
  * If pending queue already has >= MAX_PENDING_BACKLOG tasks, skip seeding
    (don't flood; let daemon catch up).
  * Deduplicate against recent task descriptions (last 50) -- skip near-duplicates.
  * Never seeds a task that mentions modifying heartbeat.md / params*.json /
    placing orders -- those are Rule 9 forbidden surfaces.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional


REPO = Path(__file__).resolve().parents[2]
STATE_DIR = REPO / "automation" / "state"

sys.path.insert(0, str(REPO / "setup" / "scripts"))
from run_minimax import call_minimax  # noqa: E402
from kitchen_daemon import (  # noqa: E402
    enqueue_task,
    _load_queue,
    MODEL_LADDER,
    GRINDER_REGISTRY,
    GRINDER_COOLDOWN_H,
    _grinder_last_run_hours_ago,
)


_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

MAX_PENDING_BACKLOG = 25       # if pending >= this, skip (don't flood)
TARGET_NEW_TASKS_PER_FIRE = 5  # ask the model for this many
DEDUP_WINDOW_RECENT = 80       # check this many recent tasks for dedup
DEDUP_SIMILARITY_THRESHOLD = 0.7  # ratio (Jaccard on token set) above which we skip


# ────────────────────────────────────────────────────────────────────────────
# DST-aware ET
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


if sys.platform == "win32" and os.path.basename(sys.executable).lower() == "pythonw.exe":
    _log_dir = STATE_DIR / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _today = _et_now().strftime("%Y-%m-%d")
    sys.stdout = open(_log_dir / f"kitchen-seeder-{_today}.stdout.log", "a", buffering=1, encoding="utf-8")
    sys.stderr = open(_log_dir / f"kitchen-seeder-{_today}.stderr.log", "a", buffering=1, encoding="utf-8")


def _log(msg: str) -> None:
    ts = _et_now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts} ET] {msg}", flush=True)


# ────────────────────────────────────────────────────────────────────────────
# Input gathering
# ────────────────────────────────────────────────────────────────────────────


def _read_safe(path: Path, max_bytes: int = 40_000) -> str:
    try:
        if not path.exists():
            return ""
        data = path.read_text(encoding="utf-8", errors="replace")
        if len(data) > max_bytes:
            return data[:max_bytes] + f"\n\n[... truncated {len(data) - max_bytes:,} bytes ...]"
        return data
    except OSError as exc:
        return f"[read error: {exc}]"


def _block(label: str, content: str) -> str:
    if not content:
        return f"### {label}\n(empty / not present)\n"
    return f"### {label}\n```\n{content}\n```\n"


def _recent_chef_outputs(n: int = 10) -> str:
    """One-line per recent chef output for inspiration / dedup signal."""
    cands_dir = REPO / "strategy" / "candidates"
    rows: list[str] = []
    if not cands_dir.exists():
        return ""
    files = sorted(
        [p for p in cands_dir.iterdir()
         if p.is_file() and p.suffix == ".md" and "chef-nemo" in p.name],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:n]
    for p in files:
        try:
            first_heading = ""
            with open(p, encoding="utf-8") as f:
                for line in f:
                    if line.startswith("# CANDIDATE:") or line.startswith("# ANALYSIS:"):
                        first_heading = line.strip()
                        break
            rows.append(f"  - {p.name}: {first_heading}")
        except OSError:
            continue
    return "\n".join(rows) if rows else "(none yet)"


def _today_journal_path() -> Path:
    return REPO / "journal" / f"{_et_now().strftime('%Y-%m-%d')}.md"


def _gather_extra_seeder_context() -> str:
    """Return compact context blocks for decisions.jsonl, inbox depths, and open recs.

    Each block is capped at ~20 lines so the prompt stays lean.
    Returns an empty string on any error.
    """
    parts: list[str] = []

    # 1. Last 30 entries from automation/state/decisions.jsonl
    decisions_path = STATE_DIR / "decisions.jsonl"
    if decisions_path.exists():
        try:
            raw_lines: list[str] = []
            with open(decisions_path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        raw_lines.append(line)
            last_lines = raw_lines[-30:]
            rows: list[str] = []
            for line in last_lines:
                try:
                    ev = json.loads(line)
                    ts = ev.get("timestamp", "")[:16]
                    setup = ev.get("setup_name", ev.get("setup", "?"))
                    action = ev.get("action", "?")
                    conf = ev.get("confidence_score", ev.get("confidence", "?"))
                    rows.append(f"  {ts} | {setup} | {action} | conf={conf}")
                except (json.JSONDecodeError, AttributeError):
                    rows.append(f"  {line[:100]}")
            if rows:
                block = "### Recent Pilot decisions (last 30 ticks from decisions.jsonl)\n"
                block += "\n".join(rows) + "\n"
                parts.append(block)
        except OSError:
            pass

    # 2. Inbox depth — count files in each author inbox
    inbox_dirs = {
        "_chef-inbox": REPO / "strategy" / "candidates" / "_chef-inbox",
        "_validator-inbox": REPO / "strategy" / "candidates" / "_validator-inbox",
        "_skill-inbox": REPO / "strategy" / "candidates" / "_skill-inbox",
        "_lesson-inbox": REPO / "strategy" / "candidates" / "_lesson-inbox",
    }
    inbox_notes: list[str] = []
    for inbox_name, inbox_path in inbox_dirs.items():
        if inbox_path.exists():
            try:
                n = sum(
                    1 for p in inbox_path.iterdir()
                    if p.is_file() and p.suffix == ".md" and not p.name.startswith("README")
                )
                if n > 5:
                    inbox_notes.append(
                        f"  Note: {inbox_name} inbox has {n} items pending author persona work."
                    )
            except OSError:
                pass
    if inbox_notes:
        parts.append("### Inbox depth (author persona backlogs)\n" + "\n".join(inbox_notes) + "\n")

    # 3. Open recommendations — list any analysis/recommendations/*.json files
    recs_dir = REPO / "analysis" / "recommendations"
    if recs_dir.exists():
        try:
            rec_files = sorted(
                p.name for p in recs_dir.iterdir()
                if p.is_file() and p.suffix == ".json"
            )
            if rec_files:
                listing = "\n".join(f"  - {n}" for n in rec_files[:20])
                parts.append(
                    "### Open recommendations awaiting validation\n"
                    f"{listing}\n"
                )
        except OSError:
            pass

    return "\n".join(parts) if parts else ""


SEEDER_SYSTEM_PROMPT = """You are the Kitchen Seeder for Project Gamma 0DTE SPY trading R&D.

Your single job: read the inputs and produce a JSON ARRAY of N concrete cook tasks
that Chef will work on. Each task is a self-contained imperative description that
Chef can act on without further clarification.

OUTPUT FORMAT (strict): respond with ONLY a JSON array. No preamble, no markdown,
no explanation. Each element is an object with these fields exactly:
  {
    "task": "<imperative task description, 1-3 sentences, concrete>",
    "priority": "<critical|high|medium|low>",
    "rationale": "<one sentence: why this is worth cooking>"
  }

Good task examples:
  * "Re-rank leaderboard candidates #3 (V14E_BEAR_ONLY_GATE) and #5 (ORB_DIRECTION_FILTER) by walk-forward stability across 2026 Q1 quarterly windows; identify which is more regime-robust."
  * "Mine markdown/doctrine/LESSONS-LEARNED.md L40-L55 for the top 3 foot-guns that have NOT been encoded as gym validators yet; propose validator specs."
  * "Explore: is there an edge in entering BEARISH_REJECTION 2 bars later (post-confirmation) vs immediate? Quantify trade count and avg P&L impact across J's 7 anchor days."
  * "Brainstorm a NEW SETUP class inspired by J's 5/15 manual trades that the current playbook does not cover."

Bad task examples (do NOT produce these):
  * "Make Chef faster" -- too vague
  * "Update heartbeat.md with new rule" -- Rule 9 forbidden surface
  * "Place a paper trade" -- forbidden surface
  * "Tell J what we found" -- ineffective autonomous output

PRIORITY GUIDANCE:
  * critical -- a known production foot-gun the engine is repeatedly hitting (rare)
  * high    -- a NEW lesson / mistake / anchor-day finding that hasn't been addressed
  * medium  -- standard refinement of existing leaderboard candidate
  * low     -- speculative exploration / brainstorm

Avoid duplicates of recent chef outputs (listed in the inputs). Diversify across:
  filter relaxation, exit logic, new triggers, watcher promotion gates, OOS validation,
  real-fills verification, regime stratification, anchor-day analysis.

Generate exactly N tasks. JSON ARRAY only.
"""


def _build_seeder_prompt(n_tasks: int) -> str:
    sections = [
        _block("strategy/candidates/_LEADERBOARD.md",
               _read_safe(REPO / "strategy" / "candidates" / "_LEADERBOARD.md", 35_000)),
        _block("markdown/doctrine/LESSONS-LEARNED.md (tail 25K bytes)",
               _read_safe_tail(REPO / "markdown" / "doctrine" / "LESSONS-LEARNED.md", 25_000)),
        _block("journal/mistakes.md (tail 12K bytes)",
               _read_safe_tail(REPO / "journal" / "mistakes.md", 12_000)),
        _block(f"journal/{_et_now().strftime('%Y-%m-%d')}.md (today)",
               _read_safe(_today_journal_path(), 25_000)),
        _block("markdown/0dte/playbook.md",
               _read_safe(REPO / "markdown" / "0dte" / "playbook.md", 15_000)),
        _block("Recent chef outputs (for dedup signal):",
               _recent_chef_outputs(15)),
    ]

    # Append extra live-signal context (decisions ticks, inbox depth, open recs)
    extra = _gather_extra_seeder_context()
    if extra:
        sections.append("## Live signal context\n\n" + extra + "\n")

    body = (
        f"# Seed {n_tasks} cook tasks\n\n"
        "## Inputs (inlined)\n\n"
        f"{''.join(sections)}\n\n"
        f"Generate EXACTLY {n_tasks} cook tasks as a JSON array per the system prompt's "
        "OUTPUT FORMAT. JSON ARRAY only."
    )
    return body


def _read_safe_tail(path: Path, max_bytes: int) -> str:
    """Read the LAST max_bytes of a file (useful for append-only logs)."""
    try:
        if not path.exists():
            return ""
        data = path.read_text(encoding="utf-8", errors="replace")
        if len(data) <= max_bytes:
            return data
        return "[... earlier content truncated ...]\n\n" + data[-max_bytes:]
    except OSError as exc:
        return f"[read error: {exc}]"


# ────────────────────────────────────────────────────────────────────────────
# Dedup
# ────────────────────────────────────────────────────────────────────────────


_TOKEN_RE = re.compile(r"[a-zA-Z0-9]+")


def _tokenize(s: str) -> set[str]:
    return {w.lower() for w in _TOKEN_RE.findall(s) if len(w) >= 3}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _is_duplicate(new_desc: str, existing_descs: list[str]) -> bool:
    new_tokens = _tokenize(new_desc)
    for ex in existing_descs:
        if _jaccard(new_tokens, _tokenize(ex)) >= DEDUP_SIMILARITY_THRESHOLD:
            return True
    return False


FORBIDDEN_PATTERNS = [
    r"\bheartbeat\.md\b",
    r"\bparams.*\.json\b",
    r"\bclaude\.md\b",
    r"place.*(order|trade)",
    r"modif(y|ies).*production",
    r"deploy.*(live|prod)",
]


def _is_forbidden(task: str) -> bool:
    lower = task.lower()
    for pat in FORBIDDEN_PATTERNS:
        if re.search(pat, lower):
            return True
    return False


# ────────────────────────────────────────────────────────────────────────────
# Output extraction
# ────────────────────────────────────────────────────────────────────────────


def _extract_json_array(content: str) -> Optional[list]:
    """Try to extract a JSON array from the response. Handles markdown fences."""
    if not content:
        return None
    # Strip code fences
    s = content.strip()
    if s.startswith("```"):
        nl = s.find("\n")
        if nl > 0:
            s = s[nl + 1:]
        if s.rstrip().endswith("```"):
            s = s.rsplit("```", 1)[0]
    s = s.strip()
    # Try direct parse first
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, list) else None
    except json.JSONDecodeError:
        pass
    # Slice to first [ and last ]
    first = s.find("[")
    last = s.rfind("]")
    if first >= 0 and last > first:
        try:
            obj = json.loads(s[first:last + 1])
            return obj if isinstance(obj, list) else None
        except json.JSONDecodeError:
            pass
    return None


# ────────────────────────────────────────────────────────────────────────────
# Grinder sweep seeding
# ────────────────────────────────────────────────────────────────────────────


def _seed_grinder_tasks(queue: dict, pending: list) -> int:
    """Enqueue grinder_sweep tasks for any grinder that hasn't run recently.

    Rules:
    - Skip if a grinder_sweep task for that script is already pending in the queue.
    - Skip if progress.json shows it ran within GRINDER_COOLDOWN_H hours.
    - Enqueue at priority=medium so LLM high/critical tasks are processed first.
    """
    # Map: script_name -> is there a pending grinder task for it?
    pending_grinder_names: set[str] = {
        s.get("script_name", "")
        for s in pending
        if s.get("task_type") == "grinder_sweep"
    }

    # Also detect recently completed grinder tasks in the queue event log
    recently_completed_grinder_names: set[str] = set()
    now_utc = datetime.now(timezone.utc)
    for state in queue.values():
        if state.get("status") != "completed":
            continue
        if state.get("task_type") != "grinder_sweep":
            continue
        completed_at = state.get("completed_at", "")
        if not completed_at:
            continue
        try:
            comp_dt = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
            if comp_dt.tzinfo is None:
                comp_dt = comp_dt.replace(tzinfo=timezone.utc)
            hours_ago = (now_utc - comp_dt.astimezone(timezone.utc)).total_seconds() / 3600
            sname = state.get("script_name", "")
            per_grinder_cd = GRINDER_REGISTRY.get(sname, {}).get("cooldown_h", GRINDER_COOLDOWN_H)
            if hours_ago < per_grinder_cd:
                recently_completed_grinder_names.add(sname)
        except (ValueError, AttributeError):
            continue

    enqueued = 0
    for script_name, info in GRINDER_REGISTRY.items():
        per_cd_h = info.get("cooldown_h", GRINDER_COOLDOWN_H)

        # Skip if already queued
        if script_name in pending_grinder_names:
            _log(f"  GRINDER_SKIP {script_name}: already pending in queue")
            continue

        # Skip if recently completed (queue log)
        if script_name in recently_completed_grinder_names:
            _log(f"  GRINDER_SKIP {script_name}: completed in queue within {per_cd_h:.0f}h")
            continue

        # Skip if progress.json on disk shows recent run
        hours_ago = _grinder_last_run_hours_ago(script_name)
        if hours_ago is not None and hours_ago < per_cd_h:
            _log(f"  GRINDER_SKIP {script_name}: progress.json shows ran {hours_ago:.1f}h ago")
            continue

        # Enqueue grinder sweep
        task_desc = (
            f"Run {script_name} parameter sweep: {info['description']}. "
            f"Find keepers with improved edge_capture and wide_pnl. "
            f"Floors protected: 4/29 + 5/04 wins must not regress."
        )
        tid = enqueue_task(
            task_desc,
            priority="medium",
            source="seeder-grinder",
            task_type="grinder_sweep",
            script_name=script_name,
            hours=info.get("default_hours", 2.0),
            workers=4,
        )
        _log(f"  GRINDER_ENQ {script_name} hours={info.get('default_hours', 2.0)} task_id={tid[:8]}")
        enqueued += 1

    return enqueued


# ────────────────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────────────────


def main() -> int:
    queue = _load_queue()
    pending = [s for s in queue.values() if s.get("status") == "pending"]
    _log(f"queue: {len(queue)} total, {len(pending)} pending")

    # Step 1: Seed grinder_sweep tasks (pure-Python, $0, independent of LLM backlog cap)
    grinder_added = _seed_grinder_tasks(queue, pending)
    if grinder_added:
        _log(f"grinder seeding: +{grinder_added} grinder_sweep tasks enqueued")
        # Reload so the LLM dedup check sees the new entries
        queue = _load_queue()
        pending = [s for s in queue.values() if s.get("status") == "pending"]

    # Step 2: Seed LLM cook tasks — respect backlog cap (grinder tasks count toward it)
    llm_pending = [s for s in pending if s.get("task_type", "llm_cook") != "grinder_sweep"]
    if len(llm_pending) >= MAX_PENDING_BACKLOG:
        _log(f"LLM backlog at {len(llm_pending)} >= cap {MAX_PENDING_BACKLOG}; skipping LLM seed")
        return 0

    prompt = _build_seeder_prompt(TARGET_NEW_TASKS_PER_FIRE)
    # FREE POOL FIRST: route seeding through the lane pool (chef role = Groq-70B
    # primary, big-ctx + no-train, never the throttled OpenRouter-only ladder).
    # Removes the ~32% OpenRouter-429 failure + the paid MiniMax tier. Falls back
    # to the original ladder only if the pool returns nothing usable.
    result = None
    try:
        import swarm_client as _swarm  # noqa: E402
        result = _swarm.call_role("chef", prompt, system=SEEDER_SYSTEM_PROMPT,
                                  max_tokens=4000, temperature=0.7,
                                  timeout=120, remote_timeout=90, task_id="kitchen.seeder")
        if result.get("ok") and (result.get("content") or "").strip():
            _log(f"seeder via pool lane={result.get('lane')}")
    except Exception as exc:  # noqa: BLE001
        _log(f"swarm seeder path failed: {type(exc).__name__}: {exc}; trying ladder")
        result = None
    if not (result and result.get("ok") and (result.get("content") or "").strip()):
        for tier_idx, model in enumerate(MODEL_LADDER):
            _log(f"ladder attempt tier={tier_idx} model={model}")
            result = call_minimax(prompt, system=SEEDER_SYSTEM_PROMPT, model=model,
                                  max_tokens=4000, temperature=0.7, timeout=240,
                                  task_id=f"kitchen.seeder.tier{tier_idx}")
            if result.get("ok") and (result.get("content") or "").strip():
                result["ladder_used"] = tier_idx
                break
            _log(f"  tier {tier_idx} failed: {result.get('error', 'unknown')}")

    if not result or not result.get("ok"):
        _log(f"all paths failed; aborting this seed fire. error={result.get('error') if result else 'none'}")
        return 1

    content = result.get("content", "")
    tasks = _extract_json_array(content)
    if not tasks:
        _log("could not extract JSON array from response; raw saved")
        raw_path = STATE_DIR / "logs" / f"seeder-bad-response-{_et_now().strftime('%Y%m%dT%H%M%S')}.txt"
        try:
            raw_path.write_text(content, encoding="utf-8")
            _log(f"raw -> {raw_path}")
        except OSError:
            pass
        return 1

    existing_descs = [s.get("task", "") for s in list(queue.values())[-DEDUP_WINDOW_RECENT:]]
    enqueued = 0
    skipped_dup = 0
    skipped_forbidden = 0

    for item in tasks:
        if not isinstance(item, dict):
            continue
        task_desc = (item.get("task") or "").strip()
        if not task_desc:
            continue
        priority = (item.get("priority") or "medium").lower()
        if priority not in ("critical", "high", "medium", "low"):
            priority = "medium"

        if _is_forbidden(task_desc):
            _log(f"  SKIP_FORBIDDEN: {task_desc[:100]}")
            skipped_forbidden += 1
            continue
        if _is_duplicate(task_desc, existing_descs):
            _log(f"  SKIP_DUPLICATE: {task_desc[:100]}")
            skipped_dup += 1
            continue

        tid = enqueue_task(task_desc, priority=priority, source="seeder")
        _log(f"  ENQ tier={result.get('ladder_used')} prio={priority} id={tid[:8]} desc={task_desc[:100]}")
        existing_descs.append(task_desc)
        enqueued += 1

    _log(f"DONE enqueued={enqueued} dup_skipped={skipped_dup} forbidden_skipped={skipped_forbidden} cost=${result.get('cost_usd', 0.0):.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
