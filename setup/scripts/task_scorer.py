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
import sys
from pathlib import Path
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Paths — anchored to the repo root via __file__, never hardcoded absolute.
# This file lives at  <repo>/setup/scripts/task_scorer.py  → repo root is 2 up.
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
QUEUE = REPO_ROOT / "automation" / "overnight" / "queue.md"
# Confirm-before-capital recency state (produced by the weekly recency_check).
# A promote-keeper item is only ACTIONABLE when a contender can clear this gate;
# when it is explicitly RED the promote cannot ship, so it must NOT be surfaced
# as the top ready task (that just wastes a fire re-verifying the wall).
RECENCY_STATE = REPO_ROOT / "automation" / "state" / "recency-confirmation.json"

# Items whose readiness is externally gated by the recency state (substring,
# case-insensitive). PROMOTE-KEEPER ranks HIGH on every fire but is unshippable
# while recency is RED — the actuator + contender_oos_check both block it.
RECENCY_GATED_ID_MARKER = "PROMOTE-KEEPER"

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
# Trading-path marker — order/fill/entry/exit/placement/arm/stop/position-monitor
# work is the FUNCTION of the rig and is NEVER expense-penalized. (2026-07-01
# pipeline audit: EXPENSIVE_RE halved J's own HIGH trading items — RIBBON-LAG,
# POSITION-MONITOR-1MIN — for ~7 days while doc-folds outranked them.)
TRADING_PATH_RE = re.compile(
    r"\b(?:order|fill|entr|exit|placement|arm|stop|position[\s-]*monitor)",
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


def _extract_field_last(block_text: str, key: str) -> str:
    """Like ``_extract_field`` but scans an entire (possibly multi-line) item
    BLOCK for ``::``-delimited ``key:<value>`` chunks and returns the LAST
    match, not just whatever is on the checkbox's own line.

    WHY: queue.md items are append-only (OP-22) — a closing verdict such as
    ``status:CLOSED-LANE-B-NO-CELL-SHIPS`` routinely lands several physical
    lines below the ``- [ ]`` checkbox line, inside later continuation prose
    (e.g. ``... point here. depends:none :: status:CLOSED-...`` on line 44 of
    a 33-line item whose checkbox line 14 ends bare at ``::`` with nothing
    after it). Reading only the checkbox line's own ``rest`` therefore sees
    status ``""`` — which this module's own ready-rule treats as READY — on
    an item that is provably closed. Confirmed live 2026-07-22: this exact
    bug is why ``PULLBACK-HOLD-BULL-TRIGGER`` (status:CLOSED-LANE-B-NO-CELL-
    SHIPS) still ranked ``ready:true`` at the top of ``--top`` days after
    closure. Scanning the WHOLE block and taking the LAST match (the most
    recently appended, hence most current, disposition) fixes this without
    touching single-line items (where "last" == "only" == the original
    behavior). Never raises; missing key returns "".
    """
    # Bound each ``::``-chunk to its OWN LINE, not the whole block: splitting
    # ``block_text`` by ``::`` globally lets a field with no LATER ``::`` on
    # its own line (e.g. a bare ``status:pending`` immediately followed by
    # unrelated multi-paragraph blockquote prose with no ``::`` at all) bleed
    # everything after it into the "value" — silently corrupting a clean
    # "pending" into "pending\n\n> **NOT PICKABLE...(paragraphs)...". Per-line
    # splitting keeps every field's value correctly terminated at end-of-line.
    found = ""
    for raw_line in block_text.splitlines():
        for chunk in raw_line.split("::"):
            chunk = chunk.strip()
            if chunk.lower().startswith(key + ":"):
                found = chunk[len(key) + 1 :].strip()
    return found


def _recency_explicitly_red(path: Path | None = None) -> bool:
    """True ONLY when the confirm-before-capital headline is readable and
    EXPLICITLY RED (``headline.edges_confirmed_on_recent is False``).

    Missing / garbled / confirmed (``True``) → returns False (do NOT suppress).
    This is deliberately the *conservative* direction for ATTENTION-routing: we
    only down-rank a promote when we POSITIVELY know it is recency-blocked, never
    hiding work on uncertainty. (The capital gates in autonomy_actuator /
    contender_oos_check fail CLOSED — that is the right direction for *shipping*;
    this scorer only routes attention, so it fails OPEN toward surfacing.)

    Reads the SAME field as ``autonomy_actuator._recency_gate_clears`` — the
    field contract is pinned by ``test_task_scorer_recency.py``'s parity test so
    the two readers can never drift apart (C14). Never raises.
    """
    p = path or RECENCY_STATE
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        headline = data.get("headline") if isinstance(data, dict) else None
        return (
            isinstance(headline, dict)
            and headline.get("edges_confirmed_on_recent") is False
        )
    except Exception:
        return False


# Statuses that mean a DEPENDENCY item is still genuinely OPEN (blocks its
# dependents). Anything else — done, done-with-annotation, or unknown compound
# vocab like 'wiring-done-arm-is-j-gated' — is treated as satisfied. (2026-07-01
# pipeline audit: G4's unrecognized status string permanently blocked G14, the
# v15.3 PRIMARY exit wiring. A dep only blocks when its item is provably open.)
OPEN_DEP_STATUSES = {
    "",
    "pending",
    "in_progress",
    "blocked",
    "awaiting-j-ratification",
    "awaiting-j-action",
}


def _dep_tokens(depends: str) -> list[str]:
    """Split a ``depends:<...>`` value into dependency ids, ignoring annotations.

    Parenthesized text is prose, NOT a dependency: ``none (was X; decoupled
    2026-06-27)`` == none. (2026-07-01 audit: this parse bug hid J's HIGH items
    — RIBBON-LAG, POSITION-MONITOR-1MIN — from the ready list for ~7 days.)
    Comma-separated multi-deps are supported; per-chunk only the leading token
    counts. Never raises.
    """
    cleaned = re.sub(r"\([^)]*\)", " ", depends)
    toks: list[str] = []
    for chunk in cleaned.split(","):
        parts = chunk.strip().split()
        lead = parts[0] if parts else ""
        if lead and lead.lower() != "none":
            toks.append(lead)
    return toks


def _open_item_ids(lines: list[str]) -> set[str]:
    """Ids of items in the given (active-section) lines that are genuinely OPEN.

    Open = an unchecked ``- [ ]`` item whose status is in OPEN_DEP_STATUSES.
    ``- [x]`` / ``- [~]`` / status:done / unknown-status items are NOT open, so
    dependencies naming them are satisfied.

    Reads status from the item's WHOLE block (see ``_extract_field_last``),
    not just its checkbox line — the same append-only-prose fix as
    ``parse_queue``'s status read, applied here so a closed-but-unchecked
    dependency (e.g. ``status:CLOSED-...`` several lines below the checkbox)
    correctly stops blocking its dependents instead of appearing perpetually
    open.
    """
    ids: set[str] = set()
    for block in _item_blocks(lines):
        line = block[0]
        m = ITEM_RE.match(line.strip())
        if not m or m.group("check").lower() == "x":
            continue
        status = _extract_field_last("\n".join(block), "status").lower()
        if status in OPEN_DEP_STATUSES:
            ids.add(m.group("id"))
    return ids


def _is_blocked_by_deps(depends: str, open_ids: set[str] | None = None) -> bool:
    """True when a depends:<...> value names a dependency that is still OPEN.

    ``depends:none`` / ``depends:`` (empty) / missing / ``none (annotation)``
    == not blocked. When ``open_ids`` is provided (the parsed queue's open item
    ids), a named dependency blocks ONLY if it is an open item — a dep whose
    item is done/absent/unknown-status is satisfied. Without ``open_ids`` any
    named dependency blocks (legacy conservative behavior).
    """
    deps = _dep_tokens(depends)
    if not deps:
        return False
    if open_ids is None:
        return True
    return any(d in open_ids for d in deps)


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
    # TRADING-PATH EXEMPTION (2026-07-01 audit): order/fill/entry/exit/placement/
    # arm/stop/position-monitor items are the rig's FUNCTION — never divided.
    if EXPENSIVE_RE.search(description):
        if TRADING_PATH_RE.search(description):
            reasons.append("expensive-exempt(trading-path)")
        else:
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


def _item_blocks(lines: list[str]) -> list[list[str]]:
    """Group active-section lines into per-item blocks.

    A block starts at a ``- [ ]``/``- [x]`` checkbox line and absorbs every
    following line up to (not including) the next checkbox line or the next
    ``###``/``##`` header — i.e. all of that item's continuation/append-only
    prose. Lines before the first checkbox (headers, blockquote preamble) are
    dropped (they never belonged to any item). Never raises.
    """
    blocks: list[list[str]] = []
    current: list[str] | None = None
    for line in lines:
        is_new_item = ITEM_RE.match(line.strip()) is not None
        is_header = bool(SUBHEADER_RE.match(line)) or (
            bool(TOP_LEVEL_RE.match(line)) and not SUBHEADER_RE.match(line)
        )
        if is_new_item:
            if current is not None:
                blocks.append(current)
            current = [line]
            continue
        if is_header:
            if current is not None:
                blocks.append(current)
            current = None
            continue
        if current is not None:
            current.append(line)
    if current is not None:
        blocks.append(current)
    return blocks


def parse_queue(text: str) -> list[Task]:
    """Parse the Active-backlog section of a queue.md string into scored Tasks.

    Robust by construction: any line that does not match the item shape, or that
    blows up mid-parse, is skipped — this function NEVER raises on bad input.
    """
    tasks: list[Task] = []
    active = _active_lines(text)
    # First pass: which item ids are genuinely OPEN (for dependency resolution).
    open_ids = _open_item_ids(active)
    for block in _item_blocks(active):
        line = block[0]
        block_text = "\n".join(block)
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

            # status: scan the WHOLE block (last match wins — see
            # _extract_field_last docstring) so a closing verdict appended
            # several lines below the checkbox line is not silently missed.
            # depends: checkbox-line-only, unchanged (status is the confirmed,
            # demonstrated bug; widening depends parsing is a separate,
            # out-of-scope risk — see TASK-SCORER-STATUS-VOCAB-GAP).
            status = _extract_field_last(block_text, "status").lower()
            depends = _extract_field(rest, "depends")

            # Exclusions: bad status, or a still-open dependency = not ready.
            has_deps = _is_blocked_by_deps(depends, open_ids)
            status_ok = status in READY_STATUSES or status == ""
            if status in EXCLUDED_STATUSES:
                # Excluded entirely — never surfaced even with --all.
                continue

            ready = bool(status_ok) and not has_deps

            # Confirm-before-capital: a recency-gated item (PROMOTE-KEEPER) is
            # only ACTIONABLE when a contender can actually clear the recency
            # gate. When recency is explicitly RED the promote cannot ship, so
            # surfacing it as the top READY item just wastes a fire re-verifying
            # the wall — down-rank it to not-ready (still visible under --all).
            recency_blocked = (
                ready
                and RECENCY_GATED_ID_MARKER in task_id.upper()
                and _recency_explicitly_red()
            )
            if recency_blocked:
                ready = False

            score, reason = score_item(
                priority=priority,
                description=description,
                paren=paren,
                ready=ready,
                has_deps=has_deps,
            )
            if recency_blocked:
                reason += (
                    "; blocked: confirm-before-capital recency RED "
                    "(no shippable contender)"
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


def staleness_advisory(ranked: list) -> str | None:
    """OP-25 nudge, graduated 2026-07-18 after a 3rd same-day recurrence.

    Three HIGH-priority items that ``task_scorer --top`` ranked #1 this session
    (RANGE-SCALP-REGIME-STRATEGY, the POSITION-MONITOR-1MIN cluster,
    RIBBON-LAG-PRICE-STRUCTURE-TRIGGER) turned out to be CLOSED_ALREADY_ANSWERED /
    CLOSED_SUPERSEDED by research or infra that had shipped AFTER the item was
    filed — nobody re-checked before spending a fire re-designing or re-running
    already-finished work. ``task_scorer`` ranks readiness (depends satisfied,
    not in_progress) but has no notion of "is the described gap still real", so
    a stale HIGH item can sit at rank #1 for weeks, actively misdirecting the
    conductor. This is a lightweight advisory, not a smart staleness detector
    (that needs semantic judgment this module deliberately doesn't have) — it
    exists to make the discipline habitual rather than to auto-resolve it.
    See ``strategy/candidates/_lesson-inbox/2026-07-18-stale-queue-item-outranked-real-work.md``.
    """
    if not ranked:
        return None
    top = ranked[0]
    if top.priority not in ("HIGH", "CRITICAL"):
        return None
    return (
        f"[task_scorer] advisory: '{top.id}' is {top.priority}-ranked #1 — before "
        "executing, trace it against CURRENT reality (analysis/recommendations/, "
        "strategy/candidates/, already-shipped infra/detectors) to confirm the "
        "described gap still reproduces. 3 same-day HIGH items were closed "
        "CLOSED_ALREADY_ANSWERED/CLOSED_SUPERSEDED on 2026-07-18 alone because "
        "nobody re-checked first. See "
        "_lesson-inbox/2026-07-18-stale-queue-item-outranked-real-work.md."
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
        advisory = staleness_advisory(ranked)
        if advisory:
            print(advisory, file=sys.stderr)  # stderr only — --top's stdout contract is id-only
        print(ranked[0].id if ranked else "")
        return 0

    ranked = rank(text, include_blocked=args.all)
    advisory = staleness_advisory(rank(text, include_blocked=False))
    if advisory:
        print(advisory, file=sys.stderr)
    print(_to_json(ranked))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
