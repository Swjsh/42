"""Guard for TASK-SCORER-STATUS-VOCAB-GAP (queue.md, LOW hygiene, closed 2026-09-03).

WHAT WAS WRONG
--------------
``task_scorer.py``'s old ``READY_STATUSES = {"pending", "in_progress"}`` was a
narrow allowlist. Live-grepped ``automation/overnight/queue.md`` this fire
(``grep -oE 'status:[a-zA-Z0-9_-]+' | sort | uniq -c``) turned up 20+ distinct
status tokens in real use — filed, partial, diagnosed, todo, proposed,
research-done, wiring-done-arm-is-j-gated, slice1-done-...-remainder-open,
blocker-B-closed-blocker-A-open, layer1-shipped-layer2-3-open, etc — every one
of which silently read ``ready:false`` under the old allowlist even though
most represent genuinely actionable open work (the item's own text says so:
"...-remainder-open", "...-open" suffixes name real remaining scope).

THE FIX
-------
Inverted the rule: READY = anything NOT terminal. Terminal = a status whose
lowercased text starts with done/closed/killed/parked/superseded/archived
(``TERMINAL_STATUS_RE``). Two deliberate carve-outs preserved from the
pre-fix behavior (both pinned elsewhere too — see test_task_scorer.py and
test_task_scorer_multiline_status.py):
  1. Exact "done" plus the Rule-9 human-reply gates (blocked/awaiting-j-*)
     stay FULLY excluded (never shown even under --all) — that was the
     original ``EXCLUDED_STATUSES`` behavior and this fix must not change it.
  2. "queued" (the HARVESTED-FROM-GYM auto-harvest self-exclusion marker)
     stays not-ready-but-visible — it is a deliberate curation gate, not a
     vocabulary gap; widening it to "ready" would flood --top with raw,
     unreviewed gym-detector rows.

This file exercises the REAL vocabulary tokens found live in queue.md, not a
synthetic subset, so a future regex tweak that silently narrows the terminal
set (or widens it to swallow a real open-work marker) breaks a test that
names the actual queue token.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCORER = REPO / "setup" / "scripts" / "task_scorer.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("task_scorer_vocab", SCORER)
    assert spec and spec.loader, f"cannot load scorer at {SCORER}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


TS = _load_module()

# Real (id, status) pairs live-grepped from automation/overnight/queue.md on
# 2026-09-03 — one representative per distinct vocab family found. Each is
# built into its own minimal single-item queue so items never interact via
# dependency resolution or section scoping.
LIVE_VOCAB_READY = [
    ("V-PENDING", "pending"),
    ("V-IN-PROGRESS", "in_progress"),
    ("V-FILED", "filed"),
    ("V-PARTIAL", "partial"),
    ("V-DIAGNOSED", "diagnosed"),
    ("V-TODO", "todo"),
    ("V-PROPOSED", "proposed"),
    ("V-RESEARCH-DONE", "research-done"),  # "-done" suffix, not a "done" prefix
    ("V-WIRING-DONE-GATED", "wiring-done-arm-is-j-gated"),
    ("V-SLICE1-REMAINDER-OPEN", "slice1-done-setup_dispatch-validator-seam-drift-proofed-remainder-open"),
    ("V-BLOCKER-B-CLOSED-A-OPEN", "blocker-B-closed-blocker-A-open"),
    ("V-LAYER1-SHIPPED-OPEN", "layer1-shipped-layer2-3-open"),
    ("V-RANK3-SHIPPED-OPEN", "rank3-shipped-ranks1-4-open"),
    ("V-INFRA-SHIPPED-ACCRUING", "infra-shipped-data-accruing"),
    ("V-ARMED-FORWARD-WATCH", "armed-forward-watch"),
    ("V-F23-REMAINDER-ONLY", "F23-remainder-only"),
    ("V-FROZEN-PREREG-FORWARD", "frozen_prereg_forward"),
    ("V-BUILT-AWAITING", "built-awaiting-09-29"),
    ("V-BUILT-NOT-DRILLED", "built-not-drilled"),
    ("V-PENDING-NEEDS-J", "pending-needs-J"),
    ("V-PENDING-DOWNGRADED", "pending-downgraded"),
]

# Real terminal statuses that must stay NOT ready (visible under --all).
LIVE_VOCAB_TERMINAL_VISIBLE = [
    ("V-CLOSED", "CLOSED"),
    ("V-CLOSED-NO-SHIP", "CLOSED-NO-SHIP"),
    ("V-CLOSED-PARTIAL", "CLOSED_PARTIAL"),
    ("V-CLOSED-NEGATIVE", "closed-negative"),
]

# Fully-excluded statuses — never shown even under --all.
LIVE_VOCAB_FULLY_EXCLUDED = [
    ("V-AWAITING-J-RATIFICATION", "awaiting-j-ratification"),
    ("V-AWAITING-J-ACTION", "awaiting-j-action"),
]

# The deliberate harvest carve-out: visible under --all, but never ready.
LIVE_VOCAB_NOT_READY_VISIBLE = [
    ("V-QUEUED", "queued"),
]


def _single_item_queue(item_id: str, status: str) -> str:
    return (
        "## Active backlog\n\n"
        f"- [ ] {item_id} (LOW) :: a live-vocab test item :: depends:none :: status:{status}\n"
    )


def test_live_vocab_statuses_are_ready():
    for item_id, status in LIVE_VOCAB_READY:
        queue = _single_item_queue(item_id, status)
        ready_ids = [t.id for t in TS.rank(queue, include_blocked=False)]
        assert item_id in ready_ids, f"{item_id} (status:{status}) should be ready"


def test_live_vocab_terminal_statuses_not_ready_but_visible():
    for item_id, status in LIVE_VOCAB_TERMINAL_VISIBLE:
        queue = _single_item_queue(item_id, status)
        ready_ids = [t.id for t in TS.rank(queue, include_blocked=False)]
        assert item_id not in ready_ids, f"{item_id} (status:{status}) should NOT be ready"
        all_by_id = {t.id: t for t in TS.rank(queue, include_blocked=True)}
        assert item_id in all_by_id, f"{item_id} (status:{status}) should be visible under --all"
        assert all_by_id[item_id].ready is False


def test_live_vocab_fully_excluded_statuses_never_surfaced():
    for item_id, status in LIVE_VOCAB_FULLY_EXCLUDED:
        queue = _single_item_queue(item_id, status)
        all_ids = [t.id for t in TS.parse_queue(queue)]
        assert item_id not in all_ids, f"{item_id} (status:{status}) should be fully excluded"


def test_live_vocab_harvest_queued_not_ready_but_visible():
    for item_id, status in LIVE_VOCAB_NOT_READY_VISIBLE:
        queue = _single_item_queue(item_id, status)
        ready_ids = [t.id for t in TS.rank(queue, include_blocked=False)]
        assert item_id not in ready_ids, f"{item_id} (status:{status}) should NOT be ready"
        all_by_id = {t.id: t for t in TS.rank(queue, include_blocked=True)}
        assert item_id in all_by_id
        assert all_by_id[item_id].ready is False
