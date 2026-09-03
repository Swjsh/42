#!/usr/bin/env python3
"""Weekly Review done-marker (queue.md WEEKLY-REVIEW-RETRY-DONE-MARKER, LOW).

Gamma_WeeklyReview's script (run-weekly-review.ps1) fires an Invoke-Claude LLM
review (~$8/run, 12-min cap). Every other evening producer got a PT15M/PT30M
self-heal retry window on 2026-09-03 (dceb125e) so a silently-skipped fire gets
recovered -- WeeklyReview was left out because a retry within that window would
call the $8 LLM a second time for the same week with no way to know it already
ran. This module is the missing done-marker so the .ps1 wrapper can skip the
LLM call when the current ISO week is already marked done.

Marker file (default): automation/state/weekly-review-done.json
    {"week_iso": "2026-W36", "generated_et": "2026-09-06T18:03:11-04:00",
     "artifact_path": "analysis/..."}

Contract (enforced by the CALLER, not this module):
  - `check` runs at the START of the wrapper, before Invoke-Claude. If the
    marker's week_iso equals the CURRENT ISO week (ET), the review already
    ran this week -- skip the LLM call. Exit code 0 = SKIP (already done),
    exit code 1 = RUN (stale or missing marker). This is an intentional
    inversion of the usual 0-is-success convention: the caller branches on
    $LASTEXITCODE to decide whether to call Invoke-Claude at all.
  - `write` runs ONLY after Invoke-Claude reports success. A FAILED run must
    NEVER call `write` -- the caller is responsible for gating that call on
    the LLM exit code so a failed run leaves the marker stale/missing and the
    retry window can recover it. This module does not know or care whether
    the LLM call succeeded; it just records that `write` was invoked.

Usage:
  python weekly_review_marker.py check [--marker PATH] [--now ISO8601]
  python weekly_review_marker.py write --artifact PATH [--marker PATH] [--now ISO8601]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover -- py<3.9 not used in this repo's venvs
    ZoneInfo = None  # type: ignore

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MARKER = REPO_ROOT / "automation" / "state" / "weekly-review-done.json"
ET_ZONE = ZoneInfo("America/New_York") if ZoneInfo else timezone.utc


def now_et(now_override: str | None = None) -> datetime:
    """Current ET time, or a caller-supplied override (tests / --now) parsed
    as ISO-8601. Naive overrides are assumed already ET."""
    if now_override:
        dt = datetime.fromisoformat(now_override)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ET_ZONE)
        return dt.astimezone(ET_ZONE)
    return datetime.now(timezone.utc).astimezone(ET_ZONE)


def iso_week_string(dt: datetime) -> str:
    """ISO-8601 week label, e.g. '2026-W36'. Uses isocalendar() so week
    boundaries follow the ISO standard (Mon-Sun, week 1 = first week with a
    Thursday in January) rather than a naive day-of-year divide."""
    year, week, _ = dt.isocalendar()
    return f"{year}-W{week:02d}"


def read_marker(marker_path: Path) -> dict | None:
    if not marker_path.exists():
        return None
    try:
        data = json.loads(marker_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def is_current_week_done(marker_path: Path, now: datetime) -> bool:
    marker = read_marker(marker_path)
    if not marker:
        return False
    return marker.get("week_iso") == iso_week_string(now)


def write_marker(marker_path: Path, now: datetime, artifact_path: str) -> dict:
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "week_iso": iso_week_string(now),
        "generated_et": now.isoformat(),
        "artifact_path": artifact_path,
    }
    marker_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check", help="exit 0 if current ISO week already done, else 1")
    p_check.add_argument("--marker", default=str(DEFAULT_MARKER))
    p_check.add_argument("--now", default=None, help="ISO-8601 override, for tests")

    p_write = sub.add_parser("write", help="record the current ISO week as done")
    p_write.add_argument("--marker", default=str(DEFAULT_MARKER))
    p_write.add_argument("--now", default=None, help="ISO-8601 override, for tests")
    p_write.add_argument("--artifact", default="", help="path to the generated review artifact")

    args = parser.parse_args(argv)
    now = now_et(args.now)
    marker_path = Path(args.marker)

    if args.command == "check":
        week = iso_week_string(now)
        if is_current_week_done(marker_path, now):
            print(f"SKIP already-done {week}")
            return 0
        print(f"RUN {week}")
        return 1

    if args.command == "write":
        payload = write_marker(marker_path, now, args.artifact)
        print(f"WROTE {payload['week_iso']} -> {marker_path}")
        return 0

    return 2  # unreachable -- argparse `required=True` rejects unknown commands


if __name__ == "__main__":
    sys.exit(main())
