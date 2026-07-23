"""snapshot_key_levels.py -- dated point-in-time snapshots of the LIVE level feed.

WHY THIS EXISTS (2026-07-23): the full-engine historical replay
(analysis/recommendations/engine-fullhist-replay-2026-07-23.md) proved that live's
level feed (automation/state/key-levels.json = curated + level_memory merge +
intraday refresh) is NEVER historically snapshotted -- `refresh_levels_intraday.py`
and `level_memory_producer.py` overwrite the same file in place every fire, so no
backtest can ever reconstruct what the engine actually SAW at entry time on a past
day. Trade-level fidelity of every historical engine replay is therefore
compromised, permanently, for every day before this script started running. The
past is unrecoverable -- the fix is FORWARD-ONLY: from today on, take dated
snapshots so future replays have a real point-in-time level feed to test against.

Pure stdlib. No LLM, no MCP, no network, no broker, no trading-path writes. Every
fire:
  1. Copies automation/state/key-levels.json (if present) into
     automation/state/key-levels-history/<ET-date>/<HHMM>.json.
  2. Copies automation/state/key-levels-memory.json (the G11 level_memory merge
     input, if present) into
     automation/state/key-levels-history/<ET-date>/<HHMM>-memory.json.
  3. SKIP-IF-UNCHANGED: before writing, hashes the source and compares it against
     the day's LATEST existing snapshot of the same kind (by content hash, not
     mtime/size) -- if identical, no new file is written (avoids 4x/day churn on a
     quiet session where nothing moved between fires).
  4. Fail-open (C7 / OP-25): a missing source file is a logged SKIP line, never a
     crash. Any unexpected exception anywhere is caught in main() and logged --
     this script always exits 0, never breaks the scheduled-task chain.

Fire cadence is owned by Windows Task Scheduler (Gamma_KeyLevelsSnapshot, 4x/day
weekdays: 08:35/09:30/12:00/15:50 ET -- premarket-final, open, midday drift, EOD),
NOT by this script -- one invocation = one idempotent snapshot attempt.

RETENTION: files are small JSON (~20-25KB each), no pruning is implemented yet.
Per OP-22 ("every append-only producer has a retention cap"), CONSOLIDATION
(prune/archive/compress) triggers once the history directory holds roughly 1 year
of daily dirs -- not before. Revisit then; do not add pruning speculatively now.

ET comes from this repo's canonical clock (setup/scripts/et_clock.py) -- NEVER
local time / bash TZ (this box is Mountain, ET = local + 2h; see
project_tz_systemic_fix / feedback_bash_tz_broken_use_powershell_clock).
"""
from __future__ import annotations

import hashlib
import re
import shutil
import sys
from pathlib import Path
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = Path(__file__).resolve().parent

# et_clock.py lives alongside this script -- import it directly (repo convention;
# see ledger_archive.py / test_broker_canary.py for the same pattern).
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
from et_clock import et_now, et_today_str  # noqa: E402

SOURCE_MAIN = REPO_ROOT / "automation" / "state" / "key-levels.json"
SOURCE_MEMORY = REPO_ROOT / "automation" / "state" / "key-levels-memory.json"
HISTORY_ROOT = REPO_ROOT / "automation" / "state" / "key-levels-history"

# Filename shapes within a day's snapshot dir: main = "HHMM.json", memory =
# "HHMM-memory.json". Kept as strict patterns so "latest snapshot of this kind"
# never accidentally matches the other kind's files.
_MAIN_PATTERN = re.compile(r"^\d{4}\.json$")
_MEMORY_PATTERN = re.compile(r"^\d{4}-memory\.json$")


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _latest_snapshot(day_dir: Path, pattern: re.Pattern) -> Optional[Path]:
    """The most recent (highest HHMM) existing snapshot of one kind in `day_dir`,
    or None if the dir doesn't exist or has no matching file yet."""
    if not day_dir.exists():
        return None
    matches = [p for p in day_dir.iterdir() if p.is_file() and pattern.match(p.name)]
    if not matches:
        return None
    return sorted(matches, key=lambda p: p.name)[-1]


def snapshot_one(*, source: Path, day_dir: Path, hhmm: str, pattern: re.Pattern, suffix: str) -> str:
    """Snapshot one source file into `day_dir/<hhmm><suffix>.json`, skipping the
    write if it would be byte-identical to the day's latest same-kind snapshot.

    Never raises for a missing/unreadable source -- returns a SKIP/ERROR line.
    """
    if not source.exists():
        return f"SKIP {source.name} (source not found)"

    try:
        content_hash = _file_hash(source)
    except OSError as exc:
        return f"ERROR {source.name} (read failed: {exc})"

    latest = _latest_snapshot(day_dir, pattern)
    if latest is not None:
        try:
            if _file_hash(latest) == content_hash:
                return f"SKIP-UNCHANGED {source.name} (matches {latest.name})"
        except OSError:
            pass  # unreadable prior snapshot -- fall through and write a fresh one

    day_dir.mkdir(parents=True, exist_ok=True)
    dest = day_dir / f"{hhmm}{suffix}.json"
    try:
        shutil.copy2(source, dest)
        try:
            rel = dest.relative_to(REPO_ROOT)
        except ValueError:
            rel = dest
        return f"WROTE {source.name} -> {rel} ({dest.stat().st_size} bytes)"
    except OSError as exc:
        return f"ERROR {source.name} (write failed: {exc})"


def main() -> int:
    """Always returns 0. Any unexpected exception is caught and logged, never raised."""
    try:
        today_str = et_today_str()
        hhmm = et_now().strftime("%H%M")
        day_dir = HISTORY_ROOT / today_str

        lines: List[str] = [
            snapshot_one(source=SOURCE_MAIN, day_dir=day_dir, hhmm=hhmm, pattern=_MAIN_PATTERN, suffix=""),
            snapshot_one(
                source=SOURCE_MEMORY, day_dir=day_dir, hhmm=hhmm, pattern=_MEMORY_PATTERN, suffix="-memory"
            ),
        ]
        for line in lines:
            print(line)
    except Exception as exc:  # noqa: BLE001 -- fail-open per OP-25/C7, never crash the task
        print(f"ERROR snapshot_key_levels.main() failed: {exc!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
