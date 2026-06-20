"""Feedback writer — auto-queues doctrine candidates, lesson candidates, etc.

ALL writes are APPEND-ONLY to JSONL ledgers under analysis/recommendations/.
NEVER writes to markdown/doctrine/LESSONS-LEARNED.md, markdown/planning/FUTURE-IMPROVEMENTS.md, or
docs/CHANGELOG.md directly (OP 24 — those require J ratification).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent.parent.parent
QUEUE_DIR = REPO / "analysis" / "recommendations"
QUEUE_DIR.mkdir(parents=True, exist_ok=True)

GRINDER_QUEUE = QUEUE_DIR / "queue.jsonl"
LESSONS_CANDIDATES = QUEUE_DIR / "lessons-candidates.jsonl"
FUTURE_IMPROVEMENTS_CANDIDATES = QUEUE_DIR / "future-improvements-candidates.jsonl"


def _fingerprint_hash(d: dict) -> str:
    """Stable hash for dedupe (sorted JSON)."""
    s = json.dumps(d, sort_keys=True, default=str)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _existing_hashes(path: Path) -> set[str]:
    """Read existing JSONL and collect fingerprint hashes for dedupe."""
    if not path.exists():
        return set()
    hashes = set()
    try:
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    h = obj.get("fingerprint_hash")
                    if h:
                        hashes.add(h)
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass
    return hashes


def _append_unique(path: Path, entry: dict, dedupe_keys: list[str]) -> bool:
    """Append entry to JSONL if not duplicate. Returns True if appended."""
    dedupe_payload = {k: entry.get(k) for k in dedupe_keys}
    h = _fingerprint_hash(dedupe_payload)
    entry["fingerprint_hash"] = h

    existing = _existing_hashes(path)
    if h in existing:
        return False

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")
    return True


def queue_doctrine_candidate(candidate: dict) -> bool:
    """Queue a doctrine candidate for the weekend grinder (or evening fire).

    Args:
        candidate: dict with keys like {date, source, setup_name, rationale,
                   fingerprint_for_search, analog_stats, op_20_disclosures}

    Returns:
        True if appended (new), False if duplicate.
    """
    return _append_unique(
        GRINDER_QUEUE, candidate,
        dedupe_keys=["setup_name", "fingerprint_for_search"],
    )


def append_lesson_candidate(candidate: dict) -> bool:
    """Append L## candidate to lessons-candidates.jsonl (J ratifies → manual write).

    Args:
        candidate: dict with {date, candidate_l_num, title, source, detail}
    """
    return _append_unique(
        LESSONS_CANDIDATES, candidate,
        dedupe_keys=["title", "source"],
    )


def append_future_improvement(improvement: dict) -> bool:
    """Append improvement idea to future-improvements-candidates.jsonl."""
    return _append_unique(
        FUTURE_IMPROVEMENTS_CANDIDATES, improvement,
        dedupe_keys=["title"],
    )


def dispatch_actions_from_categories(categories: dict, date_str: str) -> dict:
    """Walk every category's actions list and dispatch to the right feedback writer.

    Returns counts: {grinder_queue: N, lessons: N, future_improvements: N}
    """
    counts = {"grinder_queue": 0, "lessons": 0, "future_improvements": 0,
              "duplicates_skipped": 0, "unhandled": 0}

    for cat_key, cat in categories.items():
        actions = getattr(cat, "actions", None) or (cat.get("actions") if isinstance(cat, dict) else [])
        for a in actions or []:
            atype = a.get("type", "")
            details = a.get("details", {}) or {}
            entry = {
                "date": date_str,
                "source_category": cat_key,
                "priority": a.get("priority", "MED"),
                **details,
            }
            if atype == "queue_for_grinder":
                appended = queue_doctrine_candidate(entry)
                counts["grinder_queue" if appended else "duplicates_skipped"] += 1
            elif atype in ("queue_lesson_candidate", "log_lesson"):
                # Lessons category emits a single action with `candidates: [...]` list
                cand_list = details.get("candidates", [])
                if cand_list:
                    for cand in cand_list:
                        entry2 = {"date": date_str, "source_category": cat_key, **cand}
                        appended = append_lesson_candidate(entry2)
                        counts["lessons" if appended else "duplicates_skipped"] += 1
                else:
                    appended = append_lesson_candidate(entry)
                    counts["lessons" if appended else "duplicates_skipped"] += 1
            elif atype in ("queue_future_improvement", "update_doctrine"):
                appended = append_future_improvement(entry)
                counts["future_improvements" if appended else "duplicates_skipped"] += 1
            elif atype.startswith("alert_") or atype.startswith("log_"):
                # Operational alerts (silent watchers, stale news, pin chain breaks,
                # doctrine wins, etc.) — append to a single alerts ledger
                alerts_path = QUEUE_DIR / "alerts.jsonl"
                entry2 = {**entry, "alert_type": atype}
                appended = _append_unique(alerts_path, entry2,
                                          dedupe_keys=["alert_type", "source_category"])
                counts["alerts"] = counts.get("alerts", 0) + (1 if appended else 0)
            else:
                counts["unhandled"] += 1

    return counts
