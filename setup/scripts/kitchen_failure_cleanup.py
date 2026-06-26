"""
kitchen_failure_cleanup.py
--------------------------
One-shot cleanup of the 62 failed_permanent kitchen tasks.

Disposition:
  PURGE (9)      - archived-2026-05-24 tasks: known garbage, emit a 'purge' close event
  RETRY (49)     - APIConnectionError (transient outage) + unregistered grinders (now
                   in registry): reset retry count by emitting a 'requeue' event with
                   reset_retries=True so daemon picks them back up
  QUARANTINE (2) - overnight_grinder timeouts: emit a 'quarantine' event, leave
                   failed_permanent but document for manual review

Run: python setup/scripts/kitchen_failure_cleanup.py [--dry-run]
"""
import json
import sys
import collections
from datetime import datetime, timezone
from pathlib import Path

QUEUE = Path(__file__).parent.parent.parent / "automation" / "state" / "cook-queue.jsonl"
DRY_RUN = "--dry-run" in sys.argv


def _now():
    return datetime.now(timezone.utc).isoformat()


def load_failed_tasks(path: Path):
    tasks = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ev = rec.get("event") or rec.get("status") or "NONE"
            tid = rec.get("task_id", "")
            if ev == "create":
                tasks[tid] = {"task": rec.get("task", ""), "fail_count": 0, "events": []}
            elif tid in tasks:
                tasks[tid]["events"].append({"ev": ev, "error": rec.get("error", "")})
                if ev == "fail":
                    tasks[tid]["fail_count"] += 1
    return tasks


def classify(tasks):
    purge, retry, quarantine = [], [], []
    for tid, info in tasks.items():
        evs = [e["ev"] for e in info["events"]]
        if "complete" in evs or info["fail_count"] == 0:
            continue
        last_err = ""
        for e in reversed(info["events"]):
            if e["ev"] == "fail":
                last_err = e.get("error", "")
                break
        el = last_err.lower()
        if "archived-" in el:
            purge.append((tid, info["task"], last_err))
        elif "apiconnectionerror" in el or "connection error" in el or "unknown grinder" in el:
            retry.append((tid, info["task"], last_err))
        elif "timeout" in el:
            quarantine.append((tid, info["task"], last_err))
    return purge, retry, quarantine


def emit_events(path: Path, events: list[dict]):
    if DRY_RUN:
        print(f"[DRY-RUN] Would append {len(events)} events to {path.name}")
        for e in events:
            print(f"  {e['event']} | {e['task_id'][:8]} | {e.get('reason','')[:60]}")
        return
    with open(path, "a", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")


def main():
    print("Loading queue …")
    tasks = load_failed_tasks(QUEUE)
    purge, retry, quarantine = classify(tasks)
    print(f"PURGE: {len(purge)} | RETRY: {len(retry)} | QUARANTINE: {len(quarantine)}")

    ts = _now()
    new_events = []

    for tid, task, reason in purge:
        new_events.append({
            "event": "close",
            "task_id": tid,
            "reason": f"purge: {reason[:80]}",
            "ts": ts,
        })

    for tid, task, reason in retry:
        new_events.append({
            "event": "requeue",
            "task_id": tid,
            "reason": "cleanup: transient infra failure or grinder now registered — retry allowed",
            "reset_retries": True,
            "ts": ts,
        })

    for tid, task, reason in quarantine:
        new_events.append({
            "event": "close",
            "task_id": tid,
            "reason": f"quarantine: timeout on overnight_grinder — check venv interpreter (L27). task={task[:60]}",
            "ts": ts,
        })

    emit_events(QUEUE, new_events)

    if not DRY_RUN:
        print(f"\nDone. Appended {len(new_events)} events.")
        print(f"  Purged   : {len(purge)}")
        print(f"  Retried  : {len(retry)}")
        print(f"  Quarantine: {len(quarantine)}")
        print("\nDaemon will pick up retried tasks on its next poll cycle.")
    else:
        print(f"\nDry-run complete — no changes written.")


if __name__ == "__main__":
    main()
