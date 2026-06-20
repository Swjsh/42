"""Lessons module — L## candidate detection (separate from winner forensics).

Scans:
  - rule_breaks_today ledger
  - journal_md for "lesson:" / "TODO" markers
  - ingest_warnings for system-level issues
  - cross-references existing LESSONS-LEARNED.md to dedupe

Output: candidate L## entries (NOT auto-written — queued for J ratification per OP 24).
"""
from __future__ import annotations

import re
from pathlib import Path

from ..schema import CategoryScore
from ..ingest import IngestedData

REPO = Path(__file__).resolve().parent.parent.parent.parent.parent
LESSONS_FILE = REPO / "markdown" / "doctrine" / "LESSONS-LEARNED.md"


def _existing_lesson_titles() -> set[str]:
    """Get lowercased lesson title fragments from LESSONS-LEARNED.md for dedupe."""
    if not LESSONS_FILE.exists():
        return set()
    try:
        text = LESSONS_FILE.read_text(encoding="utf-8-sig")
        # Match lines like "## L01: title" or "## L23: title"
        titles = set()
        for m in re.finditer(r"##\s*L(\d+):\s*(.+?)$", text, re.MULTILINE):
            num = int(m.group(1))
            title = m.group(2).strip().lower()
            # Strip date suffix like "(2026-05-14)"
            title = re.sub(r"\(\d{4}-\d{2}-\d{2}\)\s*$", "", title).strip()
            titles.add(title)
        return titles
    except Exception:
        return set()


def _next_l_number() -> int:
    """Find the highest L## in LESSONS-LEARNED.md and return next."""
    if not LESSONS_FILE.exists():
        return 1
    try:
        text = LESSONS_FILE.read_text(encoding="utf-8-sig")
        nums = [int(m.group(1)) for m in re.finditer(r"##\s*L(\d+):", text)]
        return max(nums) + 1 if nums else 1
    except Exception:
        return 1


def analyze_lessons(data: IngestedData, trades) -> CategoryScore:
    """Detect candidate lessons. Score = quality of incident logging.

    Scoring:
      - Base 50 (neutral)
      - +30 if rule_breaks_today is empty (clean session)
      - +20 if no system incidents (TV CDP / Discord / pin chain)
      - Lower if many new lesson candidates emerged today (signals stress)
    """
    candidates = []
    existing_titles = _existing_lesson_titles()
    next_l = _next_l_number()

    # Source 1: rule breaks
    for rb in data.rule_breaks_today:
        if not isinstance(rb, dict):
            continue
        title = f"rule break: {rb.get('rule_id', 'unknown')} — {rb.get('reason', '')[:80]}"
        dup = any(t for t in existing_titles
                  if title.lower().startswith(t[:30]) or t.startswith(title.lower()[:30]))
        if not dup:
            candidates.append({
                "candidate_l_num": next_l,
                "title": title.strip(),
                "source": "rule_breaks.jsonl",
                "detail": rb,
                "duplicate_of_existing": False,
            })
            next_l += 1

    # Source 2: ingest warnings
    for w in data.ingest_warnings:
        if not w or not isinstance(w, str):
            continue
        title = f"ingest warning: {w[:120]}"
        dup = any(t for t in existing_titles if w[:30].lower() in t)
        if not dup:
            candidates.append({
                "candidate_l_num": next_l,
                "title": title,
                "source": "ingest_warnings",
                "detail": w,
                "duplicate_of_existing": False,
            })
            next_l += 1

    # Source 3: journal markdown TODO / lesson markers
    md = data.journal_md or ""
    for m in re.finditer(r"(?im)^(?:- \[ \]|TODO|LESSON):?\s+(.+?)$", md):
        line = m.group(1).strip()[:120]
        if not line:
            continue
        # Filter obvious non-lesson TODOs (UI tweaks, etc.)
        if any(kw in line.lower() for kw in ["test", "verify", "ship", "queue"]):
            continue
        dup = any(t for t in existing_titles if line[:30].lower() in t)
        if not dup:
            candidates.append({
                "candidate_l_num": next_l,
                "title": f"journal candidate: {line}",
                "source": "journal_md",
                "detail": line,
                "duplicate_of_existing": False,
            })
            next_l += 1

    # Score
    base = 50
    if not data.rule_breaks_today:
        base += 30
    if not any(("tv cdp" in str(w).lower() or "discord" in str(w).lower())
               for w in data.ingest_warnings):
        base += 20

    # Penalize if many novel candidates (signals a stressful session)
    if len(candidates) >= 5:
        base = max(40, base - 15)
    elif len(candidates) >= 3:
        base = max(50, base - 8)

    actions = []
    if candidates:
        actions.append({
            "type": "queue_lesson_candidate",
            "priority": "MED",
            "details": {
                "count": len(candidates),
                "candidates": candidates,
                "destination": "analysis/recommendations/lessons-candidates.jsonl",
                "note": "OP 24 — auto-write to LESSONS-LEARNED.md is BANNED. Candidates queued for J ratification.",
            },
        })

    narrative = (
        f"Lesson candidates detected: {len(candidates)} "
        f"(rule_breaks={len(data.rule_breaks_today)}, "
        f"ingest_warnings={len(data.ingest_warnings)}, "
        f"journal_markers={sum(1 for c in candidates if c['source']=='journal_md')}). "
        f"All candidates queued — NEVER auto-written to LESSONS-LEARNED.md. "
        f"Score {base}/100."
    )

    return CategoryScore(
        score=float(base),
        evidence={
            "phase": "2.4",
            "candidate_count": len(candidates),
            "lesson_candidates": candidates,
            "next_l_number": next_l,
            "existing_lesson_count": len(existing_titles),
        },
        narrative=narrative,
        actions=actions,
    )
