#!/usr/bin/env python3
"""ROI-rank the conductor's overnight backlog so it picks the max-value next task.

WHY THIS EXISTS (Phase 3 of the autonomy plan)
-----------------------------------------------
The conductor today walks ``automation/overnight/queue.md`` Tier-by-Tier and
picks the next ``- [ ]`` item by its FIXED tier label. That means a LOW
"doc-index fold" sitting in Tier 1 can get picked before a HIGH engine-benefit
item in Tier 2 — priority by position, not by value-per-cost (ROI).

This module is the missing ranker: parse the *Active backlog* only, score each
ready item by ROI (value from priority + path-to-money / quick-win signals,
divided by a cost proxy), and hand back a sorted list so the conductor can take
the single highest-ROI ready item.

It is READ-ONLY and STDLIB-ONLY (no pandas / no pip deps) so it can run inside
any scheduled-task interpreter without the backtest venv. It NEVER raises on a
malformed queue — a bad line is skipped, a missing file yields ``[]``.

CLI
---
    python setup/scripts/task_scorer.py            # ranked JSON array (ready only)
    python setup/scripts/task_scorer.py --top      # just the best ready item's id
    python setup/scripts/task_scorer.py --all       # include blocked (ready=false)

Each JSON row: {"id", "score", "priority", "ready", "reason"}.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Paths — anchored to the repo root via __file__, never hardcoded absolute.
# This file lives at  <repo>/setup/scripts/task_scorer.py  → repo root is 2 up.
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
QUEUE = REPO_ROOT / "automation" / "overnight" / "queue.md"

# ---------------------------------------------------------------------------
# Section parsing markers.
#  - Active items live ONLY under "## Active backlog".
#  - We stop at the NEXT top-level "## " heading (e.g. "## Archived", "## Completed").
#  - "### Tier N" are sub-headers WITHIN the active section — they do NOT stop us.
# ---------------------------------------------------------------------------
ACTIVE_HEADING = "## Active backlog"
TOP_LEVEL_RE = re.compile(r"^##\s+\S")          # a "## " heading (not "### ")
SUBHEADER_RE = re.compile(r"^###\s+")            # a "### " sub-header

# A backlog line looks like:
#   - [ ] <id> (<PRIORITY...>) :: <description> :: depends:<...> :: status:<...>
# Only the leading "- [ ] " / "- [x] " marker + id + parens are guaranteed; the
# trailing "::"-delimited fields are best-effort (some Tier-4 lines omit depends).
ITEM_RE = re.compile(
    r"^- \[(?P<check>[ xX])\]\s+"      # checkbox: space = open, x = done
    r"(?P<id>\S+)\s+"                  # task id (first whitespace-delimited token)
    r"\((?P<paren>[^)]*)\)"            # priority parens, e.g. "(LOW, doc-index)"
    r"\s*::\s*(?P<rest>.*)$"           # everything after the first " :: "
)

# Leading priority token inside the parens: HIGH / MED / LOW (case-insensitive).
PRIORITY_RE = re.compile(r"\b(HIGH|MED|LOW)\b", re.IGNORECASE)

# Statuses that mean "not pickable" even on an unchecked line.
EXCLUDED_STATUSES = {"done", "blocked", "awaiting-j-ratification"}
# Statuses we actively allow (anything else unchecked is treated conservatively
# as not-ready so we never pick something in an unexpected state).
READY_STATUSES = {"pending", "in_progress"}

# Priority → base value.
PRIORITY_BASE = {"HIGH": 3.0, "MED": 2.0, "LOW": 1.0}

# Value signals.
ENGINE_BENEFIT_RE = re.compile(
    r"engine|edge|param|strike|stop|exit|sizing|validator|fill|risk|money|p&l|backtest|signal",
    re.IGNORECASE,
)
QUICK_WIN_RE = re.compile(
    r"verify|quick|one-token|one-line|fold|typo|rename|cleanup|prune|index",
    re.IGNORECASE,
)
# Cost proxy: expensive = anything that smells like design/research work.
EXPENSIVE_RE = re.compile(
    r"spec|design|research|redesign|investigate",
    re.IGNORECASE,
)
# Pure-bookkeeping marker in the priority parens (de-prioritize busywork).
DOC_INDEX_RE = re.compile(r"doc-index", re.IGNORECASE)

ENGINE_BENEFIT_BONUS = 2.0
QUICK_WIN_BONUS = 1.5
READY_BONUS = 1.0
DOC_INDEX_PENALTY = 1.0
EXPENSIVE_DIVISOR = 1.5
MIN_SCORE = 0.5  # the doc-index penalty can never push a score below this floor


class Task(NamedTuple):
    """One scored backlog item (immutable — no in-place mutation)."""

    id: str
    score: float
    priority: str
    ready: bool
    reason: str


def _extract_field(rest: str, key: str) -> str:
    """Pull the value of a ``key:<value>`` field from the ':: '-delimited rest.

    Returns "" when the field is absent. Best-effort + never raises.
    """
    for chunk in rest.split("::"):
        chunk = chunk.strip()
        if chunk.lower().startswith(key + ":"):
            return chunk[len(key) + 1 :].strip()
    return ""


def _is_blocked_by_deps(depends: str) -> bool:
    """True when a depends:<...> value names a real (non-trivial) dependency.

    ``depends:none`` / ``depends:`` (empty) / missing == not blocked.
    Anything else is a real dependency → blocked.
    """
    d = depends.strip().lower()
    return d not in ("", "none")


def score_item(
    priority: str,
    description: str,
    paren: str,
    ready: bool,
    has_deps: bool,
) -> tuple[float, str]:
    """Compute the ROI score + a human-readable reason string.

    value  = priority base + engine-benefit + quick-win + ready-now - doc-index
    cost   = expensive ? 1.5 : 1.0
    score  = max(MIN_SCORE_when_penalized, value / cost)

    The penalty floor (MIN_SCORE) only applies to the doc-index de-prioritization
    so real LOW engine work is never crushed below 0.5.
    """
    base = PRIORITY_BASE.get(priority, 1.0)
    reasons = [f"base={base:g}({priority or '?'})"]
    value = base

    if ENGINE_BENEFIT_RE.search(description):
        value += ENGINE_BENEFIT_BONUS
        reasons.append(f"+{ENGINE_BENEFIT_BONUS:g} engine-benefit")

    if QUICK_WIN_RE.search(description):
        value += QUICK_WIN_BONUS
        reasons.append(f"+{QUICK_WIN_BONUS:g} quick-win")

    # Ready-now bonus: deps satisfied (depends:none/empty) AND pickable state.
    if ready and not has_deps:
        value += READY_BONUS
        reasons.append(f"+{READY_BONUS:g} ready-now")

    # Doc-index / pure-bookkeeping de-prioritization (floored, never below 0.5).
    penalized = False
    if DOC_INDEX_RE.search(paren):
        value -= DOC_INDEX_PENALTY
        penalized = True
        reasons.append(f"-{DOC_INDEX_PENALTY:g} doc-index")

    # Cost proxy divisor for expensive design/research work → ROI = value/cost.
    if EXPENSIVE_RE.search(description):
        value /= EXPENSIVE_DIVISOR
        reasons.append(f"/{EXPENSIVE_DIVISOR:g} expensive(cost)")

    if penalized and value < MIN_SCORE:
        value = MIN_SCORE
        reasons.append(f"floored to {MIN_SCORE:g}")

    return round(value, 4), "; ".join(reasons)


def _active_lines(text: str) -> list[str]:
    """Return only the lines inside the '## Active backlog' section.

    Starts after the Active-backlog heading; stops at the next top-level '## '
    heading. '### Tier N' sub-headers are kept (they are inside the section).
    """
    lines = text.splitlines()
    out: list[str] = []
    in_section = False
    for line in lines:
        if not in_section:
            if line.strip() == ACTIVE_HEADING:
                in_section = True
            continue
        # Inside the section: a "## " (but not "### ") heading ends it.
        if TOP_LEVEL_RE.match(line) and not SUBHEADER_RE.match(line):
            break
        out.append(line)
    return out


def parse_queue(text: str) -> list[Task]:
    """Parse the Active-backlog section of a queue.md string into scored Tasks.

    Robust by construction: any line that does not match the item shape, or that
    blows up mid-parse, is skipped — this function NEVER raises on bad input.
    """
    tasks: list[Task] = []
    for line in _active_lines(text):
        try:
            m = ITEM_RE.match(line.strip())
            if not m:
                continue  # not a backlog item (header, prose, blockquote, blank)

            # Skip completed items (- [x]).
            if m.group("check").lower() == "x":
                continue

            task_id = m.group("id")
            paren = m.group("paren")
            rest = m.group("rest")

            # Priority = leading HIGH/MED/LOW token in the parens.
            pm = PRIORITY_RE.search(paren)
            priority = pm.group(1).upper() if pm else "LOW"

            # Description = the text up to the first '::' delimited meta-field.
            # (rest already excludes the id+paren; its first chunk is the desc.)
            description = rest.split("::", 1)[0].strip()

            status = _extract_field(rest, "status").lower()
            depends = _extract_field(rest, "depends")

            # Exclusions: bad status, or a real dependency = not ready.
            has_deps = _is_blocked_by_deps(depends)
            status_ok = status in READY_STATUSES or status == ""
            if status in EXCLUDED_STATUSES:
                # Excluded entirely — never surfaced even with --all.
                continue

            ready = bool(status_ok) and not has_deps

            score, reason = score_item(
                priority=priority,
                description=description,
                paren=paren,
                ready=ready,
                has_deps=has_deps,
            )
            tasks.append(
                Task(
                    id=task_id,
                    score=score,
                    priority=priority,
                    ready=ready,
                    reason=reason,
                )
            )
        except Exception:
            # Malformed line — skip it, never crash the ranker.
            continue
    return tasks


def rank(text: str, include_blocked: bool = False) -> list[Task]:
    """Parse + sort tasks by descending score (ties broken by id for stability)."""
    tasks = parse_queue(text)
    if not include_blocked:
        tasks = [t for t in tasks if t.ready]
    return sorted(tasks, key=lambda t: (-t.score, t.id))


def load_queue_text(path: Path = QUEUE) -> str | None:
    """Read the queue file; return None when it is missing (→ caller prints []).

    Never raises on a missing/unreadable file.
    """
    try:
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return None


def _to_json(tasks: list[Task]) -> str:
    return json.dumps(
        [
            {
                "id": t.id,
                "score": t.score,
                "priority": t.priority,
                "ready": t.ready,
                "reason": t.reason,
            }
            for t in tasks
        ],
        indent=2,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="ROI-rank the conductor's overnight backlog (queue.md)."
    )
    parser.add_argument(
        "--top",
        action="store_true",
        help="print only the single highest-ROI ready item id (empty if none).",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="include not-ready (dependency-blocked) items with ready=false.",
    )
    args = parser.parse_args(argv)

    text = load_queue_text()
    if text is None:
        # Missing queue: --top prints empty string, otherwise an empty array.
        print("" if args.top else "[]")
        return 0

    if args.top:
        # --top is always over READY items only (you can't pick a blocked task).
        ranked = rank(text, include_blocked=False)
        print(ranked[0].id if ranked else "")
        return 0

    ranked = rank(text, include_blocked=args.all)
    print(_to_json(ranked))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
