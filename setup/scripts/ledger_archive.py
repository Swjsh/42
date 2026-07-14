"""ledger_archive.py -- daily LOCAL archival of decision ledgers + trade logs.

WHY THIS EXISTS (2026-07-14): a `git stash drop` in the shared checkout destroyed
~3 weeks of uncommitted decision-ledger history (recovered by luck, not process).
The ledgers (core-decisions.jsonl, per-arm fleet decisions.jsonl, trades*.csv) are
being gitignored+untracked by the orchestrating session tonight so they stop
polluting `git status` -- which also means git no longer protects them at all.
This script is the belt-and-suspenders daily LOCAL archive: a plain dated copy
that survives an accidental `rm`/`git clean`/overwrite of the live file.

Pure stdlib. No LLM, no MCP, no network, no git operations. Every fire:
  1. Copies each SOURCES file (if present) into
     automation/archive/ledgers/<ET-date>/<flattened-name> via shutil.copy2
     (always overwrites -- idempotent by construction, running twice is harmless).
  2. Prunes archive dirs older than RETENTION_DAYS, judged by DIRECTORY NAME date
     (never mtime -- a touched-but-stale dir must still get pruned on schedule).
  3. Always exits 0 (fail-open, OP-25/C7 -- never crash the scheduled task; every
     outcome prints a one-line note so a silent miss is never mistaken for success).

Scheduled via Gamma_LedgerArchive, daily 16:12 ET (install-ledger-archive.ps1).
ET comes from this repo's canonical clock (setup/scripts/et_clock.py) -- NEVER
local time / bash TZ (this box is Mountain, ET = local + 2h; see
project_tz_systemic_fix / feedback_bash_tz_broken_use_powershell_clock).
"""
from __future__ import annotations

import shutil
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = Path(__file__).resolve().parent

# et_clock.py lives alongside this script -- import it directly (repo convention;
# see test_broker_canary.py / test_engine_liveness_guards.py for the same pattern).
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
from et_clock import et_now, et_today_str  # noqa: E402

ARCHIVE_ROOT = REPO_ROOT / "automation" / "archive" / "ledgers"
RETENTION_DAYS = 30

# Repo-relative (POSIX-style) source paths. Missing files are SKIPPED with a
# logged note, never a crash -- a fleet arm or account can be legitimately absent.
SOURCES: List[str] = [
    "automation/state/core-decisions.jsonl",
    "automation/state/fleet/risky-1/decisions.jsonl",
    "automation/state/fleet/risky-3/decisions.jsonl",
    "automation/state/fleet/safe-3/decisions.jsonl",
    "journal/trades.csv",
    "journal/trades-aggressive.csv",
]


def _flatten_name(rel_path: str) -> str:
    """Turn a repo-relative path into a single flat filename for the archive dir."""
    return rel_path.replace("/", "__").replace("\\", "__")


def archive_today(*, repo_root: Path, archive_root: Path, sources: List[str], today: str) -> List[str]:
    """Copy each `sources` file (relative to `repo_root`) into `archive_root/today/`.

    Always uses shutil.copy2 (overwrite) -- idempotent by construction, per spec:
    "if today's dir already has a file with same size or newer mtime, overwrite is
    fine". Returns one summary line per source (COPY / SKIP / ERROR) -- never raises.
    """
    dest_dir = archive_root / today
    dest_dir.mkdir(parents=True, exist_ok=True)

    lines: List[str] = []
    for rel in sources:
        src = repo_root / rel
        if not src.exists():
            lines.append(f"SKIP  {rel} (source not found)")
            continue
        dest = dest_dir / _flatten_name(rel)
        try:
            shutil.copy2(src, dest)
            lines.append(f"COPY  {rel} -> {today}/{dest.name} ({dest.stat().st_size} bytes)")
        except OSError as exc:
            lines.append(f"ERROR {rel} ({exc})")
    return lines


def prune_old_dirs(*, archive_root: Path, cutoff_date: date) -> List[str]:
    """Delete archive dirs older than `cutoff_date`, judged by DIRECTORY NAME date.

    Never touches non-date-named children (defense against an unrelated file
    someday landing under archive_root). Fail-open: a single dir's removal
    failure is skipped, not fatal to the rest of the prune pass.
    """
    if not archive_root.exists():
        return []

    lines: List[str] = []
    for child in sorted(archive_root.iterdir()):
        if not child.is_dir():
            continue
        try:
            dir_date = datetime.strptime(child.name, "%Y-%m-%d").date()
        except ValueError:
            continue  # not a date-named dir -- leave it alone
        if dir_date < cutoff_date:
            try:
                shutil.rmtree(child)
                lines.append(f"PRUNE {child.name}")
            except OSError as exc:
                lines.append(f"ERROR prune {child.name} ({exc})")
    return lines


def main() -> int:
    """Always returns 0. Any unexpected exception is caught and logged, never raised."""
    try:
        today_str = et_today_str()
        now_et: Optional[datetime] = et_now()
        cutoff = now_et.date() - timedelta(days=RETENTION_DAYS)

        copy_lines = archive_today(
            repo_root=REPO_ROOT, archive_root=ARCHIVE_ROOT, sources=SOURCES, today=today_str
        )
        prune_lines = prune_old_dirs(archive_root=ARCHIVE_ROOT, cutoff_date=cutoff)

        for line in copy_lines:
            print(line)
        summary = f"pruned {len(prune_lines)} dir(s) older than {RETENTION_DAYS}d"
        if prune_lines:
            summary += ": " + ", ".join(prune_lines)
        print(summary)
    except Exception as exc:  # noqa: BLE001 -- fail-open per OP-25/C7, never crash the task
        print(f"ERROR ledger_archive.main() failed: {exc!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
