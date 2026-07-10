"""Kitchen queue GC -- archive stale, starved, still-pending tasks.

Implements the KITCHEN-SPEC "Prune" step (6) as a repeatable, dry-run-first
tool: for pending tasks matching the filters it emits `requeue` events whose
reason carries the "archived" prefix. kitchen_daemon._load_queue (2026-07-09
prune-protocol fix) collapses those to status=archived, which removes the
tasks from daemon selection AND from kitchen_seeder's MAX_PENDING_BACKLOG
count -- the two places where a permanently-starved backlog does damage.

Default filters mirror the spec's prune clause: status=pending, priority=low,
older than 48h, any source. DRY-RUN by default; nothing is written without
--apply. After --apply the tool re-loads the queue and verifies every target
actually collapsed to archived, and prints before/after pending counts.

NOTE: a live kitchen_daemon only honors archive events if its running code
includes the 2026-07-09 fix -- events appended under an older daemon are
inert (the old collapse treats them as plain requeues of already-pending
tasks) until the daemon restarts on the fixed code. Safe either way.

Usage:
  python kitchen_queue_gc.py                                   # dry-run, spec defaults
  python kitchen_queue_gc.py --source seeder --older-than-hours 336 --apply
  python kitchen_queue_gc.py --queue-file <path> --apply       # act on a specific file
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import kitchen_daemon as kd  # noqa: E402

DEFAULT_OLDER_THAN_HOURS = 48.0  # KITCHEN-SPEC prune clause: "> 48h"
DEFAULT_PRIORITY = "low"


def _age_hours(state: dict, now_utc: datetime) -> Optional[float]:
    created = kd._parse_event_ts(state.get("created_at"))
    if created is None:
        return None
    return (now_utc - created).total_seconds() / 3600.0


def find_stale_tasks(
    queue: dict[str, dict],
    *,
    older_than_hours: float,
    priority: str,
    sources: tuple[str, ...] = (),
    now_utc: Optional[datetime] = None,
) -> list[dict]:
    """Return pending tasks matching priority + age (+ optional source) filters,
    oldest first. Tasks with an unparseable created_at are never selected --
    archival must be provably justified by age."""
    now_utc = now_utc or datetime.now(timezone.utc)
    stale: list[dict] = []
    for state in queue.values():
        if state.get("status") != "pending":
            continue
        if state.get("priority") != priority:
            continue
        if sources and state.get("source") not in sources:
            continue
        age_h = _age_hours(state, now_utc)
        if age_h is None or age_h <= older_than_hours:
            continue
        stale.append({**state, "age_hours": age_h})
    stale.sort(key=lambda s: s.get("created_at") or "")
    return stale


def _pending_counts(queue: dict[str, dict]) -> tuple[int, int]:
    """(pending_total, llm_pending) -- llm_pending is what kitchen_seeder's
    MAX_PENDING_BACKLOG skip-gate counts (pending, non-grinder)."""
    pending = [s for s in queue.values() if s.get("status") == "pending"]
    llm = [s for s in pending if s.get("task_type", "llm_cook") != "grinder_sweep"]
    return len(pending), len(llm)


def gc_queue(
    queue_file: Path,
    *,
    older_than_hours: float = DEFAULT_OLDER_THAN_HOURS,
    priority: str = DEFAULT_PRIORITY,
    sources: tuple[str, ...] = (),
    apply: bool = False,
    note: str = "",
) -> dict:
    """Run one GC pass. Returns a report dict; writes events only when apply=True."""
    queue = kd._load_queue(queue_file)
    pending_before, llm_before = _pending_counts(queue)
    now_utc = datetime.now(timezone.utc)
    targets = find_stale_tasks(
        queue, older_than_hours=older_than_hours, priority=priority,
        sources=sources, now_utc=now_utc,
    )

    report = {
        "queue_file": str(queue_file),
        "apply": apply,
        "filters": {
            "older_than_hours": older_than_hours,
            "priority": priority,
            "sources": list(sources) or "any",
        },
        "pending_before": pending_before,
        "llm_pending_before": llm_before,
        "targets": [
            {
                "task_id": t["task_id"],
                "source": t.get("source"),
                "created_at": t.get("created_at"),
                "age_days": round(t["age_hours"] / 24.0, 1),
                "task": (t.get("task") or "")[:90],
            }
            for t in targets
        ],
    }
    if not apply:
        return report

    stamp = now_utc.date().isoformat()
    for t in targets:
        reason = (
            f"archived: queue-gc stale {priority}-priority src={t.get('source')} "
            f"age={t['age_hours'] / 24.0:.1f}d > {older_than_hours:.0f}h ({stamp})"
        )
        if note:
            reason += f" -- {note}"
        kd._append_event(
            {"event": "requeue", "task_id": t["task_id"], "reason": reason},
            queue_file=queue_file,
        )

    # Verify: re-load and confirm every target collapsed to archived.
    after = kd._load_queue(queue_file)
    not_archived = [
        t["task_id"] for t in targets
        if after.get(t["task_id"], {}).get("status") != "archived"
    ]
    pending_after, llm_after = _pending_counts(after)
    report.update({
        "archived": len(targets) - len(not_archived),
        "verify_failed_task_ids": not_archived,
        "pending_after": pending_after,
        "llm_pending_after": llm_after,
    })
    return report


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--older-than-hours", type=float, default=DEFAULT_OLDER_THAN_HOURS)
    p.add_argument("--priority", default=DEFAULT_PRIORITY,
                   choices=list(kd.PRIORITY_ORDER.keys()))
    p.add_argument("--source", action="append", default=[],
                   help="restrict to this source (repeatable); default: any source")
    p.add_argument("--queue-file", default=str(kd.QUEUE_FILE),
                   help=f"queue JSONL to act on (default: {kd.QUEUE_FILE})")
    p.add_argument("--apply", action="store_true",
                   help="actually append archive events (default: dry-run)")
    p.add_argument("--note", default="", help="extra context appended to each reason")
    args = p.parse_args(argv)

    report = gc_queue(
        Path(args.queue_file),
        older_than_hours=args.older_than_hours,
        priority=args.priority,
        sources=tuple(args.source),
        apply=args.apply,
        note=args.note,
    )

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"[{mode}] queue={report['queue_file']}")
    print(f"  filters: {json.dumps(report['filters'])}")
    print(f"  pending before: total={report['pending_before']} "
          f"llm={report['llm_pending_before']}")
    print(f"  matched {len(report['targets'])} stale task(s):")
    for t in report["targets"]:
        print(f"    {t['task_id'][:8]} src={t['source']:<18} "
              f"{(t['created_at'] or '?')[:19]} age={t['age_days']:5.1f}d  {t['task'][:60]}")
    if args.apply:
        print(f"  archived: {report['archived']}/{len(report['targets'])} "
              f"(verified via _load_queue re-read)")
        print(f"  pending after: total={report['pending_after']} "
              f"llm={report['llm_pending_after']}")
        if report["verify_failed_task_ids"]:
            print(f"  VERIFY FAILED for: {report['verify_failed_task_ids']}")
            return 1
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    sys.exit(main())
