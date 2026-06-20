"""Task 0.1 — Daily key-levels snapshot archiver.

Writes TWO destinations from automation/state/key-levels.json (+ today-bias.json):
  1. analysis/level-quality/snapshots/{YYYY-MM-DD}/  — level-quality gym input.
  2. journal/key-levels-archive/key-levels-{YYYY-MM-DD}.json — the historical
     real-★★★-levels archive that pattern_backtest._load_named_levels_from_keyjson
     and validate_level_family.py read. This is the data that unblocks honest
     level-keyed validation (floor_hold / close_ceiling / BEARISH_REJECTION on
     REAL levels instead of synthetic ★★ PDH/PDL proxies).

Why this is an independent task and not just the run-daily-review.ps1 archiver:
  run-daily-review.ps1 archives key-levels.json inline, BUT it early-exits on
  holidays (Test-HolidayFromAlpaca) and on a rate-limit-retry failure — so on
  those days the archive silently misses a day. This standalone $0 capture is the
  safety-net so the archive accumulates toward the N>=20-30 days needed to re-run
  the level validations (see markdown/planning/FUTURE-IMPROVEMENTS.md).

Idempotent: if a destination already has the snapshot for that date, logs
SKIP_EXISTS and leaves the existing file untouched.

Paths anchored to __file__ (L60).  No production writes (OP-22 safe).
Does NOT modify key-levels.json or params*.json. Never places orders.
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STATE_DIR = REPO / "automation" / "state"
SNAPSHOTS_DIR = REPO / "analysis" / "level-quality" / "snapshots"
# The flat archive that backtests/validators read by date.
JOURNAL_ARCHIVE_DIR = REPO / "journal" / "key-levels-archive"

SOURCES = [
    STATE_DIR / "key-levels.json",
    STATE_DIR / "today-bias.json",
]


def _session_date(key_levels_path: Path) -> str:
    """Extract `for_session` date from key-levels.json or fall back to today."""
    try:
        data = json.loads(key_levels_path.read_text(encoding="utf-8"))
        val = data.get("for_session") or data.get("as_of", "")
        if val:
            # for_session is YYYY-MM-DD; as_of may be ISO-8601 with time
            return str(val)[:10]
    except Exception:
        pass
    return date.today().isoformat()


def main() -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    key_levels = STATE_DIR / "key-levels.json"
    if not key_levels.exists():
        print(f"[{ts}] ERROR key-levels.json not found at {key_levels}")
        sys.exit(1)

    session_date = _session_date(key_levels)
    snap_dir = SNAPSHOTS_DIR / session_date
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    if snap_dir.exists():
        # Check if both files already snapshotted
        existing = [f.name for f in snap_dir.iterdir()]
        if "key-levels.json" in existing:
            print(f"[{ts}] SKIP_EXISTS snapshot for {session_date} already present at {snap_dir}")
            return

    snap_dir.mkdir(parents=True, exist_ok=True)

    copied = []
    skipped = []
    for src in SOURCES:
        dst = snap_dir / src.name
        if not src.exists():
            skipped.append(str(src.name))
            continue
        shutil.copy2(src, dst)
        copied.append(str(src.name))

    print(f"[{ts}] ARCHIVED session={session_date} -> {snap_dir}")
    if copied:
        print(f"[{ts}]   copied: {', '.join(copied)}")
    if skipped:
        print(f"[{ts}]   skipped (not found): {', '.join(skipped)}")

    # Destination 2: flat per-date archive that pattern_backtest.py +
    # validate_level_family.py read. This is the real-level data store.
    JOURNAL_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    flat_dst = JOURNAL_ARCHIVE_DIR / f"key-levels-{session_date}.json"
    if flat_dst.exists():
        print(f"[{ts}] SKIP_EXISTS journal archive for {session_date} already present at {flat_dst}")
    else:
        shutil.copy2(key_levels, flat_dst)
        print(f"[{ts}] ARCHIVED journal -> {flat_dst}")


if __name__ == "__main__":
    main()
