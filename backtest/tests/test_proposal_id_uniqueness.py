"""Guard: conductor-proposals.jsonl must not have two ACTIVE rows share a proposal_id.

Foot-gun (FIX-CD-2026-06-28-002-ID-COLLISION, PIPELINE-AUDIT-2026-07-01 finding #7):
`cd-2026-06-28-002` was reused on TWO different active proposals (a BOLD-FLEET
per-arm params change targeting accounts.json, AND the L192 CLAUDE.md doc-fold).
The approve bus resolves an id inconsistently across code paths in the SAME actuator:

  - autonomy_actuator.sync_companion_approvals -> `by_id = {r["proposal_id"]: r ...}`
    (a dict comprehension) -> the LAST duplicate row wins.
  - apply_approved / revert -> `next((r for r ... if r["proposal_id"] == pid))`
    -> the FIRST duplicate row wins.

So a single J `ship cd-2026-06-28-002` could flip one row to approved while a later
apply/revert acts on the OTHER row -- an order/arm-adjacent surface. This test pins
that ACTIVE (still-actionable) proposal_ids are unique so the ambiguity cannot return.

Terminal rows (applied/shelved/reverted/killed/...) are IGNORED on purpose: a
promote_keeper re-emission that already `applied` once is harmless -- only rows a
`ship`/apply could still act on must be unique.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
PROPOSALS = _REPO / "automation" / "state" / "conductor-proposals.jsonl"

# Statuses a `ship`/apply/revert could still act on -> must be unambiguous.
ACTIVE_STATUSES = frozenset({"pending", "approved", "needs_structured_apply"})


def _load_rows(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            # A torn/partial line is a separate hygiene concern; this guard is about
            # id uniqueness, so skip unparseable rows rather than fail open on them.
            continue
    return rows


def find_active_id_collisions(rows: list[dict]) -> dict[str, int]:
    """Return {proposal_id: count} for ids that appear on >1 ACTIVE row."""
    counts: dict[str, int] = {}
    for r in rows:
        pid = r.get("proposal_id")
        status = str(r.get("status", "")).lower()
        if not pid or status not in ACTIVE_STATUSES:
            continue
        counts[pid] = counts.get(pid, 0) + 1
    return {pid: n for pid, n in counts.items() if n > 1}


def test_live_proposals_have_no_active_id_collision():
    """The real bus file: no id is shared by two still-actionable rows."""
    rows = _load_rows(PROPOSALS)
    assert rows, f"expected proposals at {PROPOSALS}"
    collisions = find_active_id_collisions(rows)
    assert not collisions, (
        "conductor-proposals.jsonl has ACTIVE proposal_id collisions "
        f"(a `ship <id>` would be ambiguous): {collisions}. "
        "Re-id all-but-one of each colliding set (keep the id referenced by "
        "STATUS/guards; re-id the orphan)."
    )


def test_bite_detects_a_synthetic_active_collision():
    """Non-vacuous: two active rows sharing an id ARE detected."""
    rows = [
        {"proposal_id": "dup-1", "status": "pending"},
        {"proposal_id": "dup-1", "status": "approved"},
        {"proposal_id": "unique-1", "status": "pending"},
    ]
    collisions = find_active_id_collisions(rows)
    assert collisions == {"dup-1": 2}


def test_terminal_duplicate_is_allowed():
    """A re-emitted id where all-but-one row is terminal is NOT a collision."""
    rows = [
        {"proposal_id": "pk-x", "status": "applied"},   # terminal, ignored
        {"proposal_id": "pk-x", "status": "killed"},    # terminal, ignored
        {"proposal_id": "pk-x", "status": "pending"},   # the one live row
    ]
    assert find_active_id_collisions(rows) == {}


def test_the_fixed_28_002_pair_is_now_split():
    """Regression pin for tonight's fix: the cd-2026-06-28-002 pair is split.

    The doc-fold keeps -002; the BOLD-FLEET row is now -003. Both may be active,
    but they no longer SHARE an id.
    """
    rows = _load_rows(PROPOSALS)
    ids = [r.get("proposal_id") for r in rows]
    # -002 must map to exactly one active row (the doc-fold).
    active_002 = [
        r for r in rows
        if r.get("proposal_id") == "cd-2026-06-28-002"
        and str(r.get("status", "")).lower() in ACTIVE_STATUSES
    ]
    assert len(active_002) == 1, (
        f"expected exactly one ACTIVE cd-2026-06-28-002 (the doc-fold), "
        f"found {len(active_002)}"
    )
    # The BOLD-FLEET row must now carry -003.
    assert "cd-2026-06-28-003" in ids, "BOLD-FLEET row was not re-id'd to cd-2026-06-28-003"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
