"""Usage tracker + cap — prevent claude --print spam.

Every script that invokes `claude --print` calls record_invocation() FIRST.
If today's count >= DAILY_CAP, the call is REFUSED and a "rate-limited" reply
is queued to outbox instead.

Per CLAUDE.md OP 3 (cost-effectiveness gate): hard $-cap discipline.
Per CLAUDE.md OP 18: self-audit, no spam.

Tracker file: automation/state/usage-tracker.jsonl  (append-only invocation log)
Snapshot:     automation/state/usage-snapshot.json  (today's counts + caps)

Hard caps:
    DAILY_CAP = 50 invocations/day from all scripts combined
    HOURLY_CAP = 15 invocations/hour
    PER_MIN_CAP = 1 invocation/minute (burst protection)

Estimated cost per claude --print: ~$0.05-0.15 (Sonnet, 2-5K tokens).
At DAILY_CAP=50 → max ~$7.50/day from autonomous scripts.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
STATE_DIR = ROOT / "automation" / "state"
LOG = STATE_DIR / "usage-tracker.jsonl"
SNAP = STATE_DIR / "usage-snapshot.json"

DAILY_CAP = 50
HOURLY_CAP = 15
PER_MIN_CAP = 1
EST_COST_PER_INVOCATION = 0.10  # midpoint estimate $0.05-0.15


def _read_log() -> list[dict]:
    if not LOG.exists():
        return []
    rows = []
    for line in LOG.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return rows


def check_and_record(source: str, reason: str = "") -> tuple[bool, str]:
    """Returns (allowed, reason). If allowed, the invocation is logged.

    Call this BEFORE invoking claude --print. If allowed=False, queue a
    rate-limited reply to Discord instead of invoking.
    """
    now = dt.datetime.now()
    today = now.date()
    rows = _read_log()

    today_count = sum(1 for r in rows if r.get("date") == today.isoformat())
    last_hour_count = sum(
        1 for r in rows
        if (now - dt.datetime.fromisoformat(r["timestamp"])).total_seconds() <= 3600
    )
    last_min_count = sum(
        1 for r in rows
        if (now - dt.datetime.fromisoformat(r["timestamp"])).total_seconds() <= 60
    )

    # Check caps
    if today_count >= DAILY_CAP:
        return False, f"daily cap {DAILY_CAP} reached ({today_count} today, est ${today_count * EST_COST_PER_INVOCATION:.2f})"
    if last_hour_count >= HOURLY_CAP:
        return False, f"hourly cap {HOURLY_CAP} reached ({last_hour_count} in last hour)"
    if last_min_count >= PER_MIN_CAP:
        return False, f"per-min cap {PER_MIN_CAP} reached (burst suppression)"

    # Record
    row = {
        "timestamp": now.isoformat(),
        "date": today.isoformat(),
        "source": source,
        "reason": reason,
    }
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")

    # Update snapshot
    snap = {
        "updated_at": now.isoformat(),
        "today_count": today_count + 1,
        "today_est_cost_usd": round((today_count + 1) * EST_COST_PER_INVOCATION, 2),
        "last_hour_count": last_hour_count + 1,
        "last_min_count": last_min_count + 1,
        "caps": {"daily": DAILY_CAP, "hourly": HOURLY_CAP, "per_min": PER_MIN_CAP},
        "by_source_today": {},
    }
    today_rows = [r for r in rows + [row] if r.get("date") == today.isoformat()]
    for r in today_rows:
        s = r.get("source", "unknown")
        snap["by_source_today"][s] = snap["by_source_today"].get(s, 0) + 1
    SNAP.write_text(json.dumps(snap, indent=2), encoding="utf-8")

    return True, "ok"


def get_snapshot() -> dict:
    if not SNAP.exists():
        return {"today_count": 0, "today_est_cost_usd": 0.0, "caps": {"daily": DAILY_CAP, "hourly": HOURLY_CAP, "per_min": PER_MIN_CAP}}
    try:
        return json.loads(SNAP.read_text(encoding="utf-8"))
    except Exception:
        return {}


if __name__ == "__main__":
    # CLI: print snapshot
    snap = get_snapshot()
    print(json.dumps(snap, indent=2))
