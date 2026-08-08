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
# STRATEGY-IDEATION mode (J directive 2026-07-09: "the kitchen should have an
# organ that is free agents introducing strats for us to cook up and backtest").
#
# Part-1 audit (2026-07-09) found the pre-existing meta-task brainstorm lane
# (below) had gone SILENT for 17 days -- last source=seeder create event was
# 2026-06-22T14:23:43. Root cause: SEEDER_SYSTEM_PROMPT's own PRIORITY GUIDANCE
# marks "speculative exploration / brainstorm" tasks priority=low, and
# kitchen_daemon._pick_next_task always runs highest-priority-then-oldest first
# -- a continuous stream of medium/high tasks from reviewer/grinder-auto/
# analyst-eod-auto starves every low-priority task forever. This new organ is
# a DELIBERATELY separate lane: hardcoded priority=high (never model-chosen)
# and an INDEPENDENT small backlog cap that never shares the starved queue
# segment, so it cannot inherit that failure mode.
# ────────────────────────────────────────────────────────────────────────────

IDEATION_EVERY_N_FIRES = 3       # every 3rd hourly fire -> STRATEGY-IDEATION mode
                                  # instead of the meta-task brainstorm (persisted counter)
IDEATION_TARGET_CANDIDATES = 5   # ask the model for up to this many structured candidates
IDEATION_MAX_PENDING = 8         # independent cap -- see note above
IDEATION_SOURCE = "seeder-ideation"
SEEDER_STATE_FILE = STATE_DIR / "kitchen-seeder-state.json"
MAX_KILLED_SLUGS = 80
MAX_REGISTRY_NAMES = 80

REQUIRED_CANDIDATE_FIELDS = (
    "name", "thesis_1line", "entry_rule", "exit_shape_suggestion",
    "regime_hint", "novelty_claim",
)

# Primitives the engine actually computes today. An entry_rule that references
# NONE of these is almost certainly unimplementable (a hallucinated indicator
# or an external feed the engine has no access to) -- see
# _entry_rule_has_known_primitive.
KNOWN_PRIMITIVES = (
    "level", "vwap", "ribbon", "structure", "gap", "compression", "trendline",
    "wick", "volume", "bos", "choch", "ema", "sma", "rsi", "atr", "orb",
    "opening range", "premarket", "vix", "candle", "reject", "reclaim", "break",
    "higher high", "higher low", "lower high", "lower low", "hh", "hl", "lh", "ll",
)


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
    # EXTENDED 2026-07-09 for the STRATEGY-IDEATION lane (never weaken existing
    # patterns -- only add). A free model inventing "exit_shape_suggestion" or
    # "regime_hint" text has more creative surface to accidentally (or
    # adversarially) phrase a live-arming / order-placing instruction than the
    # terse meta-task lane did.
    r"gamma_core_armed",
    r"\blive\s*[:=]\s*true\b",
    r"\barm(ing)?\b.*\blive\b",
    r"\bexecute\b.*\b(order|trade)\b",
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
# STRATEGY-IDEATION: registry / killed-list / exogenous-ideas context gathering
# ────────────────────────────────────────────────────────────────────────────


_PLAYBOOK_HEADING_RE = re.compile(
    r"^###\s+(?:Setup name|CANDIDATE|RETIRED)\b(.*)$", re.MULTILINE
)
_SHOUTY_TOKEN_RE = re.compile(r"[A-Z][A-Z0-9_]{3,}")
_LEADERBOARD_NAME_RE = re.compile(r"\[([A-Z][A-Z0-9_ ]{2,60}?)\]\(")
_LEADERBOARD_BARE_NAME_RE = re.compile(r"^\|\s*[^|]*\|\s*([A-Z][A-Z0-9_]{3,})\s*\|")

# Broad on purpose: this is a soft "don't re-pitch" context block, not a hard
# safety gate, so false positives (a PROMISING candidate that happens to
# mention "fail" in prose) are harmless -- a missed KILL is not.
_KILL_KEYWORDS = (
    "reject", "kill", "dead", "fail", "do-not-promote", "anti-edge",
    "artifact-invalidated",
)
# Explicitly named in the J directive / task spec -- always surfaced even if
# they'd otherwise fall outside the recency cap.
_ALWAYS_INCLUDE_KILL_PATTERNS = (
    "ribbon-rejection", "ribbon_rejection", "futures-swing", "futures_swing",
    "orb15", "orb-15",
)


def _gather_registry_names(max_n: int = MAX_REGISTRY_NAMES) -> list[str]:
    """Known strategy/setup names: playbook.md CONFIRMED+CANDIDATE+RETIRED
    setups, plus every named candidate on the leaderboard. Used so the
    ideation model doesn't re-propose something that already exists in code.

    References the bare `REPO` global at call time (not a precomputed
    derived constant) so tests can `monkeypatch.setattr(module, "REPO", ...)`.
    """
    names: list[str] = []

    playbook_text = _read_safe(REPO / "markdown" / "0dte" / "playbook.md", 60_000)
    for m in _PLAYBOOK_HEADING_RE.finditer(playbook_text):
        tm = _SHOUTY_TOKEN_RE.search(m.group(1))
        if tm:
            names.append(tm.group(0))

    board_text = _read_safe(REPO / "strategy" / "candidates" / "_LEADERBOARD.md", 60_000)
    for m in _LEADERBOARD_NAME_RE.finditer(board_text):
        names.append(m.group(1).strip())
    for line in board_text.splitlines():
        m = _LEADERBOARD_BARE_NAME_RE.match(line)
        if m:
            names.append(m.group(1))

    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        key = n.upper()
        if key in seen:
            continue
        seen.add(key)
        out.append(n)
        if len(out) >= max_n:
            break
    return out


def _gather_killed_slugs(max_n: int = MAX_KILLED_SLUGS) -> list[str]:
    """Grep analysis/recommendations/*.json for reject/kill/dead/fail verdicts
    (raw-text keyword scan -- robust to the many different JSON shapes verdicts
    are stored in, including nested per-setup dicts). Most-recent-first, with
    the families the J directive explicitly named always force-included.
    """
    recs_dir = REPO / "analysis" / "recommendations"
    if not recs_dir.exists():
        return []
    hits: list[Path] = []
    try:
        for p in recs_dir.glob("*.json"):
            try:
                raw = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            low = raw.lower()
            if any(kw in low for kw in _KILL_KEYWORDS):
                hits.append(p)
    except OSError:
        return []
    hits.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    slugs = [p.stem for p in hits]

    head = slugs[:max_n]
    forced = [s for s in slugs if any(pat in s.lower() for pat in _ALWAYS_INCLUDE_KILL_PATTERNS)]
    for s in forced:
        if s not in head:
            head.append(s)
    return head


def _gather_ideas_ledger(max_n: int = 10) -> str:
    """Read analysis/prospector/ideas-ledger.jsonl if present -- the exogenous
    (outside-the-kitchen) ideation organ's output. Absent today; this wires the
    outside->kitchen flow for whenever that organ starts writing to it.
    """
    ledger_path = REPO / "analysis" / "prospector" / "ideas-ledger.jsonl"
    if not ledger_path.exists():
        return (
            "(not present -- no exogenous ideas yet; this block will populate once "
            "an outside ideation organ starts writing analysis/prospector/ideas-ledger.jsonl)"
        )
    try:
        rows: list[str] = []
        with open(ledger_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(line)
        tail = rows[-max_n:]
        out: list[str] = []
        for line in tail:
            try:
                d = json.loads(line)
                out.append(f"  - {json.dumps(d, separators=(',', ':'))[:300]}")
            except json.JSONDecodeError:
                out.append(f"  - {line[:300]}")
        return "\n".join(out) if out else "(file present but empty)"
    except OSError as exc:
        return f"[read error: {exc}]"


# ────────────────────────────────────────────────────────────────────────────
# STRATEGY-IDEATION: prompt + parsing + filters
# ────────────────────────────────────────────────────────────────────────────


IDEATION_SYSTEM_PROMPT = """You are the Kitchen STRATEGY-IDEATION organ for Project Gamma
0DTE SPY trading R&D -- a free-tier autonomous model whose SOLE job right now is to INVENT
novel, tradeable strategy CANDIDATES, not to propose tasks about strategies.

You are NOT writing a full DRAFT candidate doc yet (Chef does that downstream, from your
proposal). You are proposing the RAW IDEA in structured form so it can be routed to a
Stage-1 backtest.

OUTPUT FORMAT (strict): respond with ONLY a JSON array. No preamble, no markdown, no
explanation. Each element is an object with EXACTLY these fields (all required, all strings):
  {
    "name": "<SHORT_SHOUTY_SETUP_NAME, e.g. OPENING_RANGE_IMBALANCE_LONG>",
    "thesis_1line": "<one sentence: why this edge should exist>",
    "entry_rule": "<OBJECTIVE, mechanical rule referencing primitives the engine actually
                    computes today: named levels, VWAP, the ribbon (EMA stack), market
                    structure (HH/HL/LH/LL, BOS/CHoCH), opening range, gaps, volatility
                    compression, candle wicks/bodies, volume, RSI/ATR, VIX. Do NOT invent
                    data sources the engine cannot see (no sentiment, no news feed, no
                    order-book/dark-pool data, no options-flow) unless the inputs below
                    explicitly say that primitive exists.>",
    "exit_shape_suggestion": "<stop + target shape, e.g. 'chart-stop at structure
                    invalidation, TP1 at 1.5R, runner trail 15% off HWM' -- reference
                    existing exit primitives (chart-stop, premium-stop %, chandelier
                    trail, TP1/runner split) where possible>",
    "regime_hint": "<when this should and should NOT fire -- VIX band, time-of-day,
                    trend vs chop, etc.>",
    "novelty_claim": "<1-2 sentences: why this is NOT already covered by the KNOWN
                    REGISTRY NAMES or KILLED LIST provided below -- name the closest
                    existing setup and say what's structurally different>"
  }

HARD RULES:
1. NEVER re-propose (even lightly reworded) anything in the KNOWN REGISTRY NAMES block
   below -- those setups already exist in code.
2. NEVER re-propose (even lightly reworded) anything in the KILLED LIST block below --
   those were tested and DIED. A cosmetic rename of a killed idea is still the killed idea.
3. NEVER propose changes to automation/prompts/heartbeat*.md, automation/state/params*.json,
   CLAUDE.md, or placing any live/paper order directly -- you propose RESEARCH candidates only.
4. Be CONCRETE and OBJECTIVE in entry_rule -- a human or another model must be able to code
   it from your sentence alone, with no further clarification.
5. Diversify across DIFFERENT primitive families across your N candidates -- don't propose
   N variations of the same idea.
6. If you genuinely cannot think of anything novel, it is FINE to propose fewer than N
   (down to 1) rather than pad with disguised re-pitches of the registry/killed list.

Quality > volume. One genuinely novel, objectively-codeable candidate beats five vague ones.
"""


def _build_ideation_prompt(n_candidates: int) -> str:
    registry_names = _gather_registry_names()
    killed_slugs = _gather_killed_slugs()
    ideas_block = _gather_ideas_ledger()

    sections = (
        "### KNOWN REGISTRY NAMES (already exist in code -- do NOT re-propose)\n```\n"
        + ("\n".join(registry_names) if registry_names else "(none found)") + "\n```\n\n"
        "### KILLED LIST (tested and DIED -- do NOT re-propose, even reworded)\n```\n"
        + ("\n".join(killed_slugs) if killed_slugs else "(none found)") + "\n```\n\n"
        "### EXOGENOUS IDEAS LEDGER (analysis/prospector/ideas-ledger.jsonl -- outside-sourced\n"
        "raw leads, if any; you may build on these but must still pass the novelty + primitive\n"
        "rules)\n```\n" + ideas_block + "\n```\n"
    )
    return (
        f"# Propose up to {n_candidates} NOVEL strategy candidates (STRATEGY-IDEATION mode)\n\n"
        f"{sections}\n"
        f"Propose up to {n_candidates} candidates (fewer is fine, see HARD RULE 6) as a JSON "
        "array per the system prompt's OUTPUT FORMAT. JSON ARRAY only."
    )


def _parse_strategy_candidate(item) -> Optional[dict]:
    """Validate one structured candidate dict from the ideation model.

    Returns a normalized dict (stripped strings) if every REQUIRED_CANDIDATE_FIELDS
    is present as a non-empty string, else None (malformed -- caller drops it).
    """
    if not isinstance(item, dict):
        return None
    out: dict = {}
    for field in REQUIRED_CANDIDATE_FIELDS:
        val = item.get(field)
        if not isinstance(val, str) or not val.strip():
            return None
        out[field] = val.strip()
    return out


def _entry_rule_has_known_primitive(entry_rule: str) -> bool:
    low = entry_rule.lower()
    return any(kw in low for kw in KNOWN_PRIMITIVES)


NAME_REPITCH_THRESHOLD = 0.5  # looser than DEDUP_SIMILARITY_THRESHOLD -- names are
                               # short (3-5 tokens), so even half overlapping is a
                               # real signal, not noise.


def _is_registry_repitch(candidate: dict, known_names: list[str]) -> bool:
    """Novelty check vs the registry + killed list.

    Checks the candidate's NAME on its own against each known name first: an
    exact (or near-exact) name repitch is the dangerous case, and diluting it
    with the full (freshly-written) thesis sentence via _is_duplicate lets a
    single original-sounding sentence mask an exact-name repitch (caught by
    the guard tests below -- 'V14E_BEAR_ONLY_GATE' plus a two-clause thesis
    dropped straight name-repitch Jaccard from 1.0 to 0.667, under the 0.7
    dedup threshold). Falls back to the existing _is_duplicate Jaccard on
    name+thesis for a looser "conceptually the same idea" catch.
    """
    name_tokens = _tokenize(candidate["name"])
    for known in known_names:
        if _jaccard(name_tokens, _tokenize(known)) >= NAME_REPITCH_THRESHOLD:
            return True
    probe = f"{candidate['name']} {candidate['thesis_1line']}"
    return _is_duplicate(probe, known_names)


def _candidate_to_task_desc(candidate: dict) -> str:
    """Pack a structured candidate into the imperative task string the daemon's
    llm_cook lane executes (the only lane that can currently turn free text into
    a written DRAFT candidate -- see Part-1 audit: GRINDER_REGISTRY only runs
    parameter sweeps of strategies that are ALREADY hand-coded, there is no
    generic "backtest an arbitrary new detector" harness today). Explicitly
    routes to a Stage-1 backtest as the next step per chef conventions.
    """
    return (
        f"STRATEGY-IDEATION PROPOSAL '{candidate['name']}' (free-agent ideation organ, "
        f"NOVEL-STRATEGY-CANDIDATE lane, J directive 2026-07-09). "
        f"Thesis: {candidate['thesis_1line']} "
        f"Entry rule: {candidate['entry_rule']} "
        f"Exit shape: {candidate['exit_shape_suggestion']} "
        f"Regime hint: {candidate['regime_hint']} "
        f"Novelty claim (why not already in the registry): {candidate['novelty_claim']} "
        f"Write this up as a DRAFT CANDIDATE per the CANDIDATE TEMPLATE (type=new_trigger). "
        f"Do NOT fabricate OP-16/backtest numbers -- honestly state 'unknown -- requires "
        f"Stage-1 backtest' for every anchor-day cell per the system prompt's own instruction. "
        f"Set Pre-merge gate to: needs a Stage-1 backtest via the autoresearch grinder harness "
        f"before any further ratification."
    )


def run_ideation_cycle(n_candidates: int = IDEATION_TARGET_CANDIDATES, *, force: bool = False) -> dict:
    """Run one STRATEGY-IDEATION cycle end-to-end: call the free model, validate
    + filter the structured candidates it returns, enqueue the survivors as
    high-priority llm_cook tasks under source=IDEATION_SOURCE.

    Used by both the scheduled Nth-fire path (main()) and manual verification
    (`python kitchen_seeder.py --ideate-now`, which passes force=True to bypass
    the independent backlog cap for a one-off check).

    Returns a result dict (ok, proposed candidates, enqueued task ids, per-filter
    counts, model/cost) suitable for logging and for the caller to print/verify.
    """
    queue = _load_queue()
    pending = [s for s in queue.values() if s.get("status") == "pending"]
    ideation_pending = [s for s in pending if s.get("source") == IDEATION_SOURCE]
    if not force and len(ideation_pending) >= IDEATION_MAX_PENDING:
        _log(f"IDEATION_SKIP: {len(ideation_pending)} ideation tasks already pending "
             f">= independent cap {IDEATION_MAX_PENDING}")
        return {"ok": True, "skipped": True, "reason": "backlog_cap", "enqueued_task_ids": []}

    prompt = _build_ideation_prompt(n_candidates)

    # FREE POOL FIRST (same pattern as the meta-task lane above): lazy-imported
    # so a missing/stubbed swarm_client never breaks module import.
    result = None
    try:
        import swarm_client as _swarm  # noqa: E402
        result = _swarm.call_role("chef", prompt, system=IDEATION_SYSTEM_PROMPT,
                                  max_tokens=8000, temperature=0.8,
                                  timeout=120, remote_timeout=90,
                                  task_id="kitchen.seeder.ideation")
        if result.get("ok") and (result.get("content") or "").strip():
            _log(f"IDEATION via pool lane={result.get('lane')}")
    except Exception as exc:  # noqa: BLE001
        _log(f"IDEATION swarm path failed: {type(exc).__name__}: {exc}; trying ladder")
        result = None
    if not (result and result.get("ok") and (result.get("content") or "").strip()):
        for tier_idx, model in enumerate(MODEL_LADDER):
            _log(f"IDEATION ladder attempt tier={tier_idx} model={model}")
            result = call_minimax(prompt, system=IDEATION_SYSTEM_PROMPT, model=model,
                                  max_tokens=8000, temperature=0.8, timeout=240,
                                  task_id=f"kitchen.seeder.ideation.tier{tier_idx}")
            if result.get("ok") and (result.get("content") or "").strip():
                result["ladder_used"] = tier_idx
                break
            _log(f"  tier {tier_idx} failed: {result.get('error', 'unknown')}")

    if not result or not result.get("ok") or not (result.get("content") or "").strip():
        err = result.get("error") if result else "no_result"
        _log(f"IDEATION all paths failed; error={err}")
        return {"ok": False, "enqueued_task_ids": [], "error": err}

    content = result.get("content", "")
    raw_candidates = _extract_json_array(content)
    if not raw_candidates:
        _log("IDEATION could not extract JSON array from response; raw saved")
        raw_path = STATE_DIR / "logs" / f"seeder-ideation-bad-response-{_et_now().strftime('%Y%m%dT%H%M%S')}.txt"
        try:
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_text(content, encoding="utf-8")
        except OSError:
            pass
        return {"ok": False, "enqueued_task_ids": [], "error": "no_json_array",
                "raw_saved": str(raw_path)}

    registry_names = _gather_registry_names()
    killed_slugs = _gather_killed_slugs()
    known_names = registry_names + killed_slugs
    existing_descs = [s.get("task", "") for s in list(queue.values())[-DEDUP_WINDOW_RECENT:]]

    proposed: list[dict] = []
    enqueued_ids: list[str] = []
    counts = {"malformed": 0, "no_primitive": 0, "repitch": 0, "forbidden": 0, "dup": 0}

    for raw in raw_candidates:
        candidate = _parse_strategy_candidate(raw)
        if candidate is None:
            counts["malformed"] += 1
            _log(f"  IDEATION_SKIP_MALFORMED: {str(raw)[:150]}")
            continue
        proposed.append(candidate)

        if not _entry_rule_has_known_primitive(candidate["entry_rule"]):
            counts["no_primitive"] += 1
            _log(f"  IDEATION_SKIP_NO_PRIMITIVE: {candidate['name']}")
            continue
        if _is_registry_repitch(candidate, known_names):
            counts["repitch"] += 1
            _log(f"  IDEATION_SKIP_REPITCH: {candidate['name']}")
            continue

        task_desc = _candidate_to_task_desc(candidate)
        if _is_forbidden(task_desc):
            counts["forbidden"] += 1
            _log(f"  IDEATION_SKIP_FORBIDDEN: {candidate['name']}")
            continue
        if _is_duplicate(task_desc, existing_descs):
            counts["dup"] += 1
            _log(f"  IDEATION_SKIP_DUPLICATE: {candidate['name']}")
            continue

        tid = enqueue_task(task_desc, priority="high", source=IDEATION_SOURCE)
        _log(f"  IDEATION_ENQ id={tid[:8]} name={candidate['name']}")
        existing_descs.append(task_desc)
        enqueued_ids.append(tid)

    _log(f"IDEATION DONE proposed={len(proposed)} enqueued={len(enqueued_ids)} "
         f"malformed={counts['malformed']} no_primitive={counts['no_primitive']} "
         f"repitch={counts['repitch']} forbidden={counts['forbidden']} dup={counts['dup']} "
         f"model={result.get('model') or result.get('lane')} cost=${result.get('cost_usd', 0.0):.4f}")

    return {
        "ok": True,
        "proposed": proposed,
        "enqueued_task_ids": enqueued_ids,
        "counts": {**counts, "proposed": len(proposed), "enqueued": len(enqueued_ids)},
        "model": result.get("model") or result.get("lane"),
        "cost_usd": result.get("cost_usd", 0.0),
    }


def _load_seeder_state() -> dict:
    try:
        if SEEDER_STATE_FILE.exists():
            return json.loads(SEEDER_STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _log(f"WARN seeder-state read failed: {exc}")
    return {"fire_count": 0, "last_ideation_at": None, "last_ideation_result": None}


def _save_seeder_state(state: dict) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = SEEDER_STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
        tmp.replace(SEEDER_STATE_FILE)
    except OSError as exc:
        _log(f"WARN seeder-state write failed: {exc}")


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

    # Step 1.5: STRATEGY-IDEATION -- every Nth fire, INSTEAD of the meta-task
    # brainstorm (Step 2). Persisted counter survives across fires/restarts.
    seeder_state = _load_seeder_state()
    seeder_state["fire_count"] = int(seeder_state.get("fire_count", 0)) + 1
    do_ideation = (seeder_state["fire_count"] % IDEATION_EVERY_N_FIRES == 0)
    _save_seeder_state(seeder_state)  # persist the counter even before the cycle runs

    if do_ideation:
        _log(f"IDEATION fire (fire_count={seeder_state['fire_count']}, "
             f"every {IDEATION_EVERY_N_FIRES})")
        ideation_result = run_ideation_cycle()
        seeder_state["last_ideation_at"] = _et_now().isoformat()
        seeder_state["last_ideation_result"] = ideation_result.get(
            "counts", {"skipped": ideation_result.get("skipped", False),
                       "reason": ideation_result.get("reason", ideation_result.get("error"))})
        _save_seeder_state(seeder_state)
        return 0 if ideation_result.get("ok") else 1

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
                                  max_tokens=8000, temperature=0.7,
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
                                  max_tokens=8000, temperature=0.7, timeout=240,
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
    import argparse

    _p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    _p.add_argument(
        "--ideate-now", action="store_true",
        help=(
            "Force one STRATEGY-IDEATION cycle immediately (bypasses the Nth-fire "
            "counter AND the independent pending-backlog cap) and exit. For manual "
            "verification -- does not touch the persisted fire_count counter or run "
            "the grinder-seed / meta-task steps."
        ),
    )
    _args = _p.parse_args()

    if _args.ideate_now:
        _res = run_ideation_cycle(force=True)
        print(json.dumps(_res, indent=2, default=str))
        sys.exit(0 if _res.get("ok") else 1)

    sys.exit(main())
