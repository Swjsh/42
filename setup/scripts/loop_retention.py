"""loop_retention.py — append-only retention cap for the autonomous-driver loop.

WHY THIS EXISTS (gamma-drive anti-memory-leak guard)
----------------------------------------------------
``status_retention.py`` caps ``STATUS.md`` (the prose breadcrumb file). But the
driver loop (gamma-drive / conductor) ALSO grows pure-append JSONL logs that have
no cap — chiefly ``conductor-outcomes.jsonl`` (one row per fire; 1000+ rows after
a few months of nightly fires). Left unbounded, a consumer that reads the whole
file (the wrapper's convergence check, any metric folder) slows down and, in the
worst case, blows a context budget — the exact append-only-producer-past-its-read-
contract foot-gun that took STATUS.md down (L181) and watcher-observations.jsonl
to 5.1 MB (the 06-22 RED).

This is the JSONL sibling of ``status_retention.py``: keep the newest N rows in
place, roll the older tail VERBATIM into a monthly archive next to the file
(nothing deleted, fully recoverable), atomic-write, idempotent (no-op under the
cap), and **fail-open** — a retention hiccup must NEVER crash or block the loop
that calls it (OP-25 / rail 2).

Deliberately NOT capped here (status-aware, owned elsewhere — naive row-capping
would drop live state):
  * ``conductor-proposals.jsonl`` — a dropped row = a lost pending J approval.
    The AutoApply actuator prunes terminal (applied/shelved) rows.
  * ``discord-outbox.jsonl`` — a dropped row = an unsent ping. The Discord bridge
    drains it; it only grows if the bridge is dead (a separate alarm).

STDLIB ONLY (runs under any scheduled-task interpreter). Anchored to repo root via
__file__ so cwd never matters.

CLI:
    python setup/scripts/loop_retention.py            # cap the default set
    python setup/scripts/loop_retention.py --check    # exit 2 if any file is over cap (no write)
    python setup/scripts/loop_retention.py --file PATH --max-rows N   # cap one file
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

# --- Path anchoring (cwd-independent) ---------------------------------------
# setup/scripts/loop_retention.py -> parents[2] == repo root.
REPO = Path(__file__).resolve().parents[2]
STATE_DIR = REPO / "automation" / "state"


class Target(NamedTuple):
    """One append-only JSONL file and the number of newest rows to keep."""

    path: Path
    max_rows: int


# The default set: the loop's own unbounded pure-log appends. Conservative caps —
# large enough to keep ample cross-fire history, small enough to read instantly.
DEFAULT_TARGETS: tuple[Target, ...] = (
    Target(STATE_DIR / "conductor-outcomes.jsonl", 500),
)


def _archive_path(path: Path) -> Path:
    """Monthly archive sibling, e.g. conductor-outcomes-archive-202606.jsonl."""
    month = datetime.now(timezone.utc).strftime("%Y%m")
    return path.with_name(f"{path.stem}-archive-{month}{path.suffix}")


def _atomic_write_lines(path: Path, lines: list[str]) -> None:
    """Write ``lines`` to ``path`` atomically (temp file + os.replace)."""
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("".join(lines))
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def is_over_cap(target: Target) -> bool:
    """True if the file exists and holds more than ``max_rows`` non-empty rows."""
    if not target.path.exists():
        return False
    try:
        with target.path.open("r", encoding="utf-8") as fh:
            non_empty = sum(1 for ln in fh if ln.strip())
        return non_empty > target.max_rows
    except Exception:
        return False


def cap_file(target: Target) -> int:
    """Keep the newest ``max_rows`` rows of ``target``; roll the older tail VERBATIM
    into the monthly archive. Returns the number of rows archived (0 = no-op).

    Fail-open: any exception returns 0 without raising — the caller's loop must
    never crash because retention hiccuped.
    """
    try:
        if not target.path.exists():
            return 0
        with target.path.open("r", encoding="utf-8") as fh:
            raw = fh.readlines()
        # Preserve rows verbatim; count only non-empty for the cap decision so a
        # trailing newline can't trip the threshold.
        non_empty_idx = [i for i, ln in enumerate(raw) if ln.strip()]
        if len(non_empty_idx) <= target.max_rows:
            return 0

        keep_from = non_empty_idx[-target.max_rows]
        older = raw[:keep_from]
        newest = raw[keep_from:]
        if not older:
            return 0

        # Roll the older tail into the monthly archive (append, newest-appended,
        # nothing lost: kept ∪ archived == original).
        archive = _archive_path(target.path)
        with archive.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write("".join(older))

        _atomic_write_lines(target.path, newest)
        return sum(1 for ln in older if ln.strip())
    except Exception:
        return 0


def run(targets: tuple[Target, ...] = DEFAULT_TARGETS) -> dict[str, int]:
    """Cap every target. Returns {filename: rows_archived}. Never raises."""
    return {t.path.name: cap_file(t) for t in targets}


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cap append-only driver-loop JSONL logs.")
    parser.add_argument("--file", help="Cap a single file instead of the default set.")
    parser.add_argument("--max-rows", type=int, default=500, help="Rows to keep (with --file).")
    parser.add_argument("--check", action="store_true", help="Exit 2 if any target is over cap; no write.")
    args = parser.parse_args(argv)

    targets: tuple[Target, ...]
    if args.file:
        targets = (Target(Path(args.file), args.max_rows),)
    else:
        targets = DEFAULT_TARGETS

    if args.check:
        over = [t.path.name for t in targets if is_over_cap(t)]
        if over:
            print("OVER CAP: " + ", ".join(over))
            return 2
        print("within cap -> noop")
        return 0

    result = run(targets)
    rolled = {k: v for k, v in result.items() if v}
    if rolled:
        print("rolled: " + ", ".join(f"{k}={v}" for k, v in rolled.items()))
    else:
        print("within cap -> noop")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
