"""Guard: kitchen_daemon priority-aging (starvation fix) + prune-protocol
archival (2026-07-09).

The pre-existing meta-task brainstorm lane in kitchen_seeder went silent for
17 days (last source=seeder create 2026-06-22) because:
  1. SEEDER_SYSTEM_PROMPT marks brainstorm tasks priority=low, and
     _pick_next_task ran strict highest-priority-then-oldest -- continuous
     medium/high inflow from reviewer/grinder-auto/analyst-eod-auto starved
     every low task FOREVER (~20 tasks pending 37-49 days).
  2. The permanently-stuck tasks kept kitchen_seeder's MAX_PENDING_BACKLOG
     skip-gate tripped, so no fresh meta-tasks were even generated.
  3. The KITCHEN-SPEC prune protocol ("requeue event with reason=archived")
     was a dead letter: _load_queue forced status=pending on EVERY requeue,
     so 13 archive events emitted by earlier sessions silently RESURRECTED
     their targets instead of clearing them.

These tests pin the fixes: aging in _effective_priority/_pick_next_task,
archived/closed collapse in _load_queue, and the kitchen_queue_gc tool.
Loader pattern copied from test_kitchen_seeder_ideation.py.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO / "setup" / "scripts"


def _load_modules():
    """Load kitchen_daemon + kitchen_queue_gc with heavy siblings stubbed
    (no LLM, no network)."""
    fakes = {}
    for name in ("chef_nemotron", "swarm_client"):
        if name not in sys.modules:
            mod = types.ModuleType(name)
            if name == "chef_nemotron":
                mod.CHEF_SYSTEM_PROMPT = "stub"
                mod.MODEL_LADDER = []
                mod._call_with_ladder = lambda *a, **k: {"ok": False, "error": "stub"}
                mod._write_candidate = lambda *a, **k: Path(".")
                mod._slugify = lambda s: "stub"
                mod._gather_common_inputs = lambda: ""
            else:
                mod.call_role = lambda *a, **k: {"ok": False, "error": "stub"}
            sys.modules[name] = mod
            fakes[name] = mod
    inserted_kd = "kitchen_daemon" not in sys.modules
    try:
        spec_kd = importlib.util.spec_from_file_location(
            "kitchen_daemon", _SCRIPTS / "kitchen_daemon.py")
        kd_mod = importlib.util.module_from_spec(spec_kd)
        spec_kd.loader.exec_module(kd_mod)
        if inserted_kd:
            # kitchen_queue_gc does `import kitchen_daemon` -- bind it to the
            # stub-loaded instance, never the real import (real chef_nemotron).
            sys.modules["kitchen_daemon"] = kd_mod
        spec_gc = importlib.util.spec_from_file_location(
            "kitchen_queue_gc_under_test", _SCRIPTS / "kitchen_queue_gc.py")
        gc_mod = importlib.util.module_from_spec(spec_gc)
        spec_gc.loader.exec_module(gc_mod)
    finally:
        for name in fakes:
            sys.modules.pop(name, None)
        if inserted_kd:
            sys.modules.pop("kitchen_daemon", None)
    return kd_mod, gc_mod


kd, qgc = _load_modules()

_NOW = datetime(2026, 7, 9, 12, 0, 0, tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _pending(tid: str, priority: str, age_hours: float, *,
             now: datetime = _NOW, task_type: str = "llm_cook",
             source: str = "seeder") -> dict:
    return {
        "task_id": tid,
        "task": f"task {tid}",
        "priority": priority,
        "status": "pending",
        "created_at": _iso(now - timedelta(hours=age_hours)),
        "source": source,
        "task_type": task_type,
        "retry_count": 0,
    }


def _write_queue(path: Path, events: list[dict]) -> None:
    path.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")


# ── 1. _effective_priority tier math ────────────────────────────────────────


def test_effective_priority_tier_math():
    ep = kd._effective_priority
    assert ep(_pending("a", "low", 1), _NOW) == 3        # fresh low unchanged
    assert ep(_pending("b", "low", 25), _NOW) == 2       # +1 tier after 24h
    assert ep(_pending("c", "low", 49), _NOW) == 1       # +2 tiers after 48h
    assert ep(_pending("d", "low", 500), _NOW) == 1      # capped at ceiling=high
    assert ep(_pending("e", "medium", 25), _NOW) == 1
    assert ep(_pending("f", "medium", 500), _NOW) == 1   # never reaches critical
    assert ep(_pending("g", "high", 500), _NOW) == 1     # high stays high
    assert ep(_pending("h", "critical", 500), _NOW) == 0


def test_effective_priority_bad_timestamps_get_no_promotion():
    ep = kd._effective_priority
    garbage = _pending("a", "low", 1)
    garbage["created_at"] = "not-a-timestamp"
    assert ep(garbage, _NOW) == 3
    missing = _pending("b", "low", 1)
    missing["created_at"] = None
    assert ep(missing, _NOW) == 3
    future = _pending("c", "low", 1)
    future["created_at"] = _iso(_NOW + timedelta(days=2))  # clock skew
    assert ep(future, _NOW) == 3


def test_parse_event_ts_handles_naive_and_aware():
    aware = kd._parse_event_ts("2026-07-01T10:00:00+00:00")
    naive = kd._parse_event_ts("2026-07-01T10:00:00")  # old events are naive
    assert aware == naive
    assert kd._parse_event_ts("garbage") is None
    assert kd._parse_event_ts(None) is None


# ── 2. _pick_next_task ordering under aging ─────────────────────────────────


def _now_pending(tid: str, priority: str, age_hours: float, **kw) -> dict:
    """Pending state aged relative to REAL now (_pick_next_task uses real now)."""
    return _pending(tid, priority, age_hours, now=datetime.now(timezone.utc), **kw)


def test_fresh_low_still_yields_to_fresh_medium_and_high():
    queue = {
        "low": _now_pending("low", "low", 0.5),
        "med": _now_pending("med", "medium", 0.3),
        "high": _now_pending("high", "high", 0.1),
    }
    assert kd._pick_next_task(queue)["task_id"] == "high"
    del queue["high"]
    assert kd._pick_next_task(queue)["task_id"] == "med"


def test_starved_low_eventually_beats_continuous_fresh_high_inflow():
    """THE regression: a 5-day-old low task must win against a queue that
    always contains fresh high tasks (the exact condition that starved the
    seeder meta-task lane for 17 days)."""
    queue = {"old-low": _now_pending("old-low", "low", 5 * 24)}
    for i in range(6):
        queue[f"high-{i}"] = _now_pending(f"high-{i}", "high", 0.1 + i * 0.01)
    assert kd._pick_next_task(queue)["task_id"] == "old-low"


def test_aged_low_never_preempts_critical():
    queue = {
        "old-low": _now_pending("old-low", "low", 30 * 24),
        "crit": _now_pending("crit", "critical", 0.1),
    }
    assert kd._pick_next_task(queue)["task_id"] == "crit"


def test_grinder_suppressed_by_raw_high_llm_backlog():
    """LIVELOCK FIX unchanged: 3+ raw-high LLM tasks pending -> grinder is
    excluded from selection even when aging has promoted it to the ceiling."""
    queue = {f"h-{i}": _now_pending(f"h-{i}", "high", 0.1) for i in range(3)}
    queue["grinder"] = _now_pending(
        "grinder", "medium", 20 * 24, task_type="grinder_sweep")
    assert kd._pick_next_task(queue)["task_id"].startswith("h-")


def test_deferral_predicate_stays_raw_so_aged_lows_dont_suppress_grinder():
    """Discriminating case: 3 aged lows (EFFECTIVE high, raw low) + an even
    older grinder. If the deferral predicate wrongly counted effective
    priority, the grinder would be suppressed and an aged low would win.
    Instead the grinder -- itself aged to the ceiling tier and oldest overall
    -- is picked: grinders age too (starvation-freedom applies to every task
    type), and only RAW high/critical LLM backlog defers them."""
    queue = {
        f"aged-{i}": _now_pending(f"aged-{i}", "low", 10 * 24) for i in range(3)
    }
    queue["grinder"] = _now_pending(
        "grinder", "medium", 20 * 24, task_type="grinder_sweep")
    assert kd._pick_next_task(queue)["task_id"] == "grinder"


# ── 3. _load_queue prune-protocol collapse ──────────────────────────────────


def test_requeue_reason_archived_collapses_to_archived(tmp_path):
    qf = tmp_path / "q.jsonl"
    _write_queue(qf, [
        {"event": "create", "task_id": "t1", "task": "stale brainstorm",
         "priority": "low", "source": "seeder", "ts": "2026-05-22T01:00:00+00:00"},
        {"event": "requeue", "task_id": "t1",
         "reason": "archived: queue-gc stale low-priority", "ts": "2026-07-09T01:00:00+00:00"},
    ])
    queue = kd._load_queue(qf)
    assert queue["t1"]["status"] == "archived"
    assert queue["t1"]["archived_reason"].startswith("archived:")
    assert kd._pick_next_task(queue) is None  # never selected


def test_requeue_reason_archived_is_prefix_and_case_insensitive(tmp_path):
    qf = tmp_path / "q.jsonl"
    _write_queue(qf, [
        {"event": "create", "task_id": "t1", "task": "x", "priority": "low",
         "ts": "2026-05-22T01:00:00+00:00"},
        # real historical shape from the live queue: "archived-invalid: ..."
        {"event": "requeue", "task_id": "t1",
         "reason": "Archived-invalid: watcher already exists and FAILED",
         "ts": "2026-07-09T01:00:00+00:00"},
    ])
    assert kd._load_queue(qf)["t1"]["status"] == "archived"


def test_requeue_normal_reasons_still_return_to_pending(tmp_path):
    """Reaper (stale_claim), grinder deferral (deferred:) and failure-cleanup
    (cleanup: + reset_retries) requeues must keep their existing semantics."""
    qf = tmp_path / "q.jsonl"
    _write_queue(qf, [
        {"event": "create", "task_id": "t1", "task": "x", "priority": "medium",
         "ts": "2026-07-01T01:00:00+00:00"},
        {"event": "fail", "task_id": "t1", "error": "boom",
         "ts": "2026-07-01T02:00:00+00:00"},
        {"event": "requeue", "task_id": "t1",
         "reason": "cleanup: transient infra failure — retry allowed",
         "reset_retries": True, "ts": "2026-07-01T03:00:00+00:00"},
        {"event": "create", "task_id": "t2", "task": "y", "priority": "medium",
         "ts": "2026-07-01T01:00:00+00:00"},
        {"event": "requeue", "task_id": "t2",
         "reason": "stale_claim age=1900s exceeds 1800s", "ts": "2026-07-01T02:00:00+00:00"},
        {"event": "create", "task_id": "t3", "task": "z", "priority": "medium",
         "ts": "2026-07-01T01:00:00+00:00"},
        {"event": "requeue", "task_id": "t3",
         "reason": "deferred: 4 high-priority LLM tasks ahead", "ts": "2026-07-01T02:00:00+00:00"},
    ])
    queue = kd._load_queue(qf)
    assert queue["t1"]["status"] == "pending"
    assert queue["t1"]["retry_count"] == 0  # reset_retries honored
    assert queue["t2"]["status"] == "pending"
    assert queue["t3"]["status"] == "pending"


def test_close_event_collapses_to_closed(tmp_path):
    qf = tmp_path / "q.jsonl"
    _write_queue(qf, [
        {"event": "create", "task_id": "t1", "task": "x", "priority": "medium",
         "ts": "2026-07-01T01:00:00+00:00"},
        {"event": "close", "task_id": "t1", "reason": "purge: known garbage",
         "ts": "2026-07-01T02:00:00+00:00"},
    ])
    queue = kd._load_queue(qf)
    assert queue["t1"]["status"] == "closed"
    assert queue["t1"]["closed_reason"].startswith("purge:")
    assert kd._pick_next_task(queue) is None


def test_archived_task_revivable_by_later_plain_requeue(tmp_path):
    qf = tmp_path / "q.jsonl"
    _write_queue(qf, [
        {"event": "create", "task_id": "t1", "task": "x", "priority": "low",
         "ts": "2026-05-22T01:00:00+00:00"},
        {"event": "requeue", "task_id": "t1", "reason": "archived: gc",
         "ts": "2026-07-09T01:00:00+00:00"},
        {"event": "requeue", "task_id": "t1", "reason": "manual revive",
         "ts": "2026-07-09T02:00:00+00:00"},
    ])
    assert kd._load_queue(qf)["t1"]["status"] == "pending"


# ── 4. kitchen_queue_gc end-to-end ──────────────────────────────────────────


def _gc_fixture_queue(tmp_path: Path) -> Path:
    now = datetime.now(timezone.utc)
    qf = tmp_path / "cook-queue.jsonl"
    _write_queue(qf, [
        {"event": "create", "task_id": "old-low-seeder", "task": "stale brainstorm",
         "priority": "low", "source": "seeder",
         "ts": _iso(now - timedelta(days=30))},
        {"event": "create", "task_id": "fresh-low-seeder", "task": "new brainstorm",
         "priority": "low", "source": "seeder",
         "ts": _iso(now - timedelta(hours=1))},
        {"event": "create", "task_id": "old-med-reviewer", "task": "review followup",
         "priority": "medium", "source": "reviewer",
         "ts": _iso(now - timedelta(days=30))},
        {"event": "create", "task_id": "old-low-other", "task": "other lane",
         "priority": "low", "source": "gamma-autonomous",
         "ts": _iso(now - timedelta(days=30))},
    ])
    return qf


def test_gc_dry_run_selects_stale_lows_and_writes_nothing(tmp_path):
    qf = _gc_fixture_queue(tmp_path)
    before = qf.read_bytes()
    report = qgc.gc_queue(qf, older_than_hours=48, priority="low",
                          sources=("seeder",), apply=False)
    assert [t["task_id"] for t in report["targets"]] == ["old-low-seeder"]
    assert qf.read_bytes() == before  # dry-run must not touch the file
    assert "archived" not in report  # apply-only fields absent


def test_gc_apply_archives_only_matching_tasks_and_verifies(tmp_path):
    qf = _gc_fixture_queue(tmp_path)
    report = qgc.gc_queue(qf, older_than_hours=48, priority="low",
                          sources=("seeder",), apply=True)
    assert report["archived"] == 1
    assert report["verify_failed_task_ids"] == []
    assert report["pending_before"] == 4
    assert report["pending_after"] == 3
    assert report["llm_pending_before"] == 4
    assert report["llm_pending_after"] == 3

    queue = kd._load_queue(qf)
    assert queue["old-low-seeder"]["status"] == "archived"
    assert queue["fresh-low-seeder"]["status"] == "pending"   # too young
    assert queue["old-med-reviewer"]["status"] == "pending"   # wrong priority
    assert queue["old-low-other"]["status"] == "pending"      # wrong source


def test_gc_apply_without_source_filter_catches_all_stale_lows(tmp_path):
    qf = _gc_fixture_queue(tmp_path)
    report = qgc.gc_queue(qf, older_than_hours=48, priority="low", apply=True)
    assert report["archived"] == 2  # old-low-seeder + old-low-other
    queue = kd._load_queue(qf)
    assert queue["old-low-seeder"]["status"] == "archived"
    assert queue["old-low-other"]["status"] == "archived"
    assert queue["old-med-reviewer"]["status"] == "pending"


def test_gc_never_archives_unparseable_created_at(tmp_path):
    qf = tmp_path / "q.jsonl"
    _write_queue(qf, [
        {"event": "create", "task_id": "no-ts", "task": "x", "priority": "low",
         "source": "seeder", "ts": "garbage"},
    ])
    report = qgc.gc_queue(qf, older_than_hours=48, priority="low", apply=True)
    assert report["targets"] == []
    assert kd._load_queue(qf)["no-ts"]["status"] == "pending"
