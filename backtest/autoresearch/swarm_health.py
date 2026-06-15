"""swarm-health — pre-session swarm output freshness + status check.

Reads automation/swarm/state/swarm_output.json, checks the `status` field,
checks the `generated_at` timestamp for staleness (> 4 hours = STALE), and
emits one of:

    SWARM_OK        status == "complete" AND generated_at within 4 hours
    SWARM_STALE     status == "complete" but generated_at > 4 hours ago
    SWARM_DEGRADED  status present but neither "complete" nor "failed"
    SWARM_FAILED    status == "failed" OR file missing entirely

On any non-OK verdict, appends a flag to automation/overnight/STATUS.md
under the ## Known broken section so J wakes up to a signal, not silence.

USAGE:
    python -m autoresearch.swarm_health
    python -m autoresearch.swarm_health --swarm-output /path/to/swarm_output.json
    python -m autoresearch.swarm_health --stale-hours 6
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_SWARM_OUTPUT = ROOT / "automation" / "swarm" / "state" / "swarm_output.json"
STATUS_MD = ROOT / "automation" / "overnight" / "STATUS.md"

DEFAULT_STALE_HOURS = 4


def _parse_timestamp(ts: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp string to a timezone-aware datetime.

    Handles both Z suffix and +00:00 style offsets. Returns None on failure.
    """
    if not ts:
        return None
    try:
        # Replace Z with +00:00 for fromisoformat compatibility on Python < 3.11
        normalized = ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _append_status_flag(verdict: str, status: str, detail: str) -> None:
    """Append a one-liner to STATUS.md Known broken section if non-OK."""
    if not STATUS_MD.exists():
        return
    try:
        now_et_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        line = (
            f"\n- [{verdict}] {now_et_str} "
            f"swarm.status={status!r} — {detail} "
            f"(premarket may have run without swarm context)\n"
        )
        content = STATUS_MD.read_text(encoding="utf-8")
        # Insert after ## Known broken header if present, otherwise append
        marker = "## Known broken"
        if marker in content:
            insert_pos = content.index(marker) + len(marker)
            content = content[:insert_pos] + line + content[insert_pos:]
        else:
            content = content.rstrip() + f"\n\n## Known broken\n{line}"
        STATUS_MD.write_text(content, encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        # Never crash the caller because of a STATUS.md write failure
        print(f"[swarm-health] WARNING: could not write STATUS.md: {exc}", file=sys.stderr)


def run(
    swarm_output_path: Optional[str] = None,
    stale_hours: int = DEFAULT_STALE_HOURS,
    write_status: bool = True,
) -> dict:
    """Check swarm output health.

    Returns a dict with fields:
        verdict       SWARM_OK | SWARM_STALE | SWARM_DEGRADED | SWARM_FAILED
        detail        Human-readable explanation
        status        Raw status field from swarm_output.json (or None)
        fired_at      Raw generated_at field (or None)
        age_hours     Age of the file in hours (None if unparseable)
        checked_at    ISO timestamp of this check (UTC)
    """
    path = Path(swarm_output_path) if swarm_output_path else DEFAULT_SWARM_OUTPUT
    now_utc = datetime.now(timezone.utc)
    checked_at = now_utc.isoformat()

    # --- File missing ---
    if not path.exists():
        result = {
            "verdict": "SWARM_FAILED",
            "detail": f"swarm_output.json not found at {path}",
            "status": None,
            "fired_at": None,
            "age_hours": None,
            "checked_at": checked_at,
        }
        if write_status:
            _append_status_flag("SWARM_FAILED", "missing", result["detail"])
        return result

    # --- Parse JSON ---
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        result = {
            "verdict": "SWARM_FAILED",
            "detail": f"swarm_output.json unreadable: {exc}",
            "status": None,
            "fired_at": None,
            "age_hours": None,
            "checked_at": checked_at,
        }
        if write_status:
            _append_status_flag("SWARM_FAILED", "unreadable", result["detail"])
        return result

    # --- Extract fields ---
    status: Optional[str] = raw.get("status")
    # The file uses "generated_at" in the observed schema; support "fired_at" alias too
    ts_str: Optional[str] = raw.get("generated_at") or raw.get("fired_at")
    fired_at_parsed = _parse_timestamp(ts_str)

    # --- Compute age ---
    age_hours: Optional[float] = None
    if fired_at_parsed is not None:
        age_hours = (now_utc - fired_at_parsed).total_seconds() / 3600.0

    # --- Verdict logic ---
    if status == "complete":
        if age_hours is not None and age_hours > stale_hours:
            verdict = "SWARM_STALE"
            detail = (
                f"status=complete but generated_at {ts_str!r} is "
                f"{age_hours:.1f}h ago (threshold {stale_hours}h)"
            )
        else:
            verdict = "SWARM_OK"
            age_str = f"{age_hours:.1f}h" if age_hours is not None else "unknown age"
            detail = f"status=complete, generated_at {ts_str!r} ({age_str} ago)"
    elif status == "failed":
        failure_reason = raw.get("failure_reason", "unknown")
        verdict = "SWARM_FAILED"
        detail = f"status=failed, failure_reason={failure_reason!r}"
    elif status is None:
        verdict = "SWARM_FAILED"
        detail = "status field missing from swarm_output.json"
    else:
        verdict = "SWARM_DEGRADED"
        detail = f"status={status!r} (expected 'complete')"

    result = {
        "verdict": verdict,
        "detail": detail,
        "status": status,
        "fired_at": ts_str,
        "age_hours": round(age_hours, 2) if age_hours is not None else None,
        "checked_at": checked_at,
    }

    if verdict != "SWARM_OK" and write_status:
        _append_status_flag(verdict, str(status), detail)

    return result


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--swarm-output",
        default=None,
        metavar="PATH",
        help=f"Path to swarm_output.json (default: {DEFAULT_SWARM_OUTPUT})",
    )
    p.add_argument(
        "--stale-hours",
        type=float,
        default=DEFAULT_STALE_HOURS,
        metavar="N",
        help=f"Hours before a 'complete' output is considered stale (default: {DEFAULT_STALE_HOURS})",
    )
    p.add_argument(
        "--no-status-write",
        action="store_true",
        help="Skip appending to STATUS.md (dry-run mode)",
    )
    args = p.parse_args(argv)

    result = run(
        swarm_output_path=args.swarm_output,
        stale_hours=int(args.stale_hours),
        write_status=not args.no_status_write,
    )
    print(json.dumps(result, indent=2))
    verdict_line = f"[swarm-health] {result['verdict']}: {result['detail']}"
    print(verdict_line, file=sys.stderr)
    return 0 if result["verdict"] == "SWARM_OK" else 1


if __name__ == "__main__":
    sys.exit(main())
