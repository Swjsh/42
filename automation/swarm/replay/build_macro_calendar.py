"""
Filter macro-calendar.json to events relevant to a target date — replay-mode replacement.

The live macro_agent.md reads automation/state/macro-calendar.json and filters by today's date.
For replay, we copy the file but filter events_30d to ONLY events whose date == target_date
OR fall in the same week (for context). This avoids the agent reasoning about future events.

Schema matches the live macro-calendar.json exactly.

Usage:
  python build_macro_calendar.py --date 2026-05-14
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

WORK_DIR = Path(__file__).parent.parent.parent.parent.resolve()
SWARM_DIR = WORK_DIR / "automation" / "swarm"
LIVE_CALENDAR = WORK_DIR / "automation" / "state" / "macro-calendar.json"


def _log(msg: str) -> None:
    print(f"[build_macro_calendar] {msg}", flush=True)


def build_macro_calendar(date_et: str, output_path: Path | None = None) -> dict:
    if not LIVE_CALENDAR.exists():
        raise FileNotFoundError(f"Live macro-calendar missing: {LIVE_CALENDAR}")

    with open(LIVE_CALENDAR, encoding="utf-8") as f:
        live = json.load(f)

    target_dt = datetime.fromisoformat(date_et)
    week_start = (target_dt - timedelta(days=target_dt.weekday())).strftime("%Y-%m-%d")
    week_end = (target_dt + timedelta(days=6 - target_dt.weekday())).strftime("%Y-%m-%d")

    in_window = [e for e in live.get("events_30d", []) if week_start <= e.get("date", "") <= week_end]
    today_events = [e for e in in_window if e.get("date") == date_et]

    out = dict(live)
    out["events_30d"] = in_window
    out["replay_mode"] = True
    out["replay_window"] = {
        "target_date": date_et,
        "week_start": week_start,
        "week_end": week_end,
        "events_total_in_window": len(in_window),
        "events_today": len(today_events),
    }
    out["refresh_log"] = [{
        "fetched_at": datetime.now().isoformat(),
        "source": "replay_filter",
        "events_added": len(in_window),
        "events_removed": len(live.get("events_30d", [])) - len(in_window),
        "note": f"Filtered to week {week_start}..{week_end} for replay of {date_et}",
    }]

    if output_path is None:
        output_path = SWARM_DIR / "state" / "macro-calendar.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    _log(f"wrote {output_path} ({len(in_window)} events in week, {len(today_events)} on target date)")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Filter macro-calendar.json for historical date")
    parser.add_argument("--date", required=True, help="Target date YYYY-MM-DD")
    parser.add_argument("--output", type=Path, default=None,
                        help="Output path (default: automation/swarm/state/macro-calendar.json)")
    args = parser.parse_args()

    try:
        build_macro_calendar(args.date, args.output)
        return 0
    except Exception as exc:
        _log(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
