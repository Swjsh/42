#!/usr/bin/env python3
"""STATUS.md retention / consolidation tool (graduates L181 to a reusable guard).

Problem (L181, re-violated 2026-06-24): `automation/overnight/STATUS.md` is the
conductor's durable cross-fire memory, appended every fire. With no retention cap
it grows past the Read tool's token cap (~25K tokens) so a fire can no longer read
it whole -> it trusts a stale breadcrumb over current STATUS and re-does solved work
(the exact L181 foot-gun). The 2026-06-22 consolidation was a MANUAL one-off; it
regrew to 226KB / 58 entries by 2026-06-24. This module makes consolidation a
repeatable, tested, idempotent operation instead of a bespoke manual effort.

Behaviour:
  * Split STATUS.md on `## [` entry boundaries (entries are newest-first at the top).
  * KEEP the newest entries while cumulative bytes <= --max-keep-bytes (default 45000,
    safely under the ~25K-token Read cap), always keeping at least --min-keep entries.
  * ROLL the older tail (verbatim, nothing deleted) to the monthly archive
    `automation/overnight/STATUS-archive-YYYY-MM.md`, newest roll inserted at the top
    (cold tail, newest-first within each roll) with a dated roll-off comment.
  * Idempotent: if the file already fits the budget, it is a no-op (exit 0).
  * Fail-open (L181/OP-25): any error / missing file -> exit 0 noop, never raises into
    a caller. This is operational state hygiene; it must never block J or a fire.

Rail-4 clear: touches ONLY operational state (STATUS.md + its archive). Zero
trading-logic / params / orders / doctrine change.

CLI:
  python setup/scripts/status_retention.py                 # apply consolidation
  python setup/scripts/status_retention.py --check         # report only, exit 2 if over budget
  python setup/scripts/status_retention.py --max-keep-bytes 60000 --min-keep 10
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STATUS_PATH = os.path.join(REPO_ROOT, "automation", "overnight", "STATUS.md")

ENTRY_SPLIT = re.compile(r"(?=^## \[)", re.M)
DEFAULT_MAX_KEEP_BYTES = 45_000
DEFAULT_MIN_KEEP = 8


def split_entries(text: str):
    """Return (preamble, [entries]) splitting on `## [` headers (newest-first order).

    The preamble is any text before the first entry (usually empty for STATUS.md).
    Each entry string includes its trailing content up to the next `## [`.
    """
    parts = ENTRY_SPLIT.split(text)
    if not parts:
        return "", []
    # If the file starts with an entry, parts[0] is "" -> preamble empty.
    if parts[0].lstrip().startswith("## ["):
        return "", parts
    return parts[0], parts[1:]


def plan_consolidation(text: str, max_keep_bytes: int, min_keep: int):
    """Decide which entries to keep vs roll off. Pure function (testable).

    Returns dict: kept_text, rolled_entries (list, newest-first), n_kept, n_rolled.
    """
    preamble, entries = split_entries(text)
    n = len(entries)
    if n == 0:
        return {"kept_text": text, "rolled_entries": [], "n_kept": 0, "n_rolled": 0}

    cum = len(preamble.encode("utf-8"))
    keep_count = 0
    for i, e in enumerate(entries):
        cum += len(e.encode("utf-8"))
        keep_count = i + 1
        # Always keep at least min_keep; stop once over budget beyond that.
        if keep_count >= min_keep and cum > max_keep_bytes:
            break

    keep_count = min(keep_count, n)
    kept = entries[:keep_count]
    rolled = entries[keep_count:]
    kept_text = preamble + "".join(kept)
    return {
        "kept_text": kept_text,
        "rolled_entries": rolled,
        "n_kept": len(kept),
        "n_rolled": len(rolled),
    }


def _archive_path(status_path: str, today: dt.date) -> str:
    return os.path.join(os.path.dirname(status_path), f"STATUS-archive-{today:%Y-%m}.md")


def _archive_header(today: dt.date) -> str:
    return (
        f"# STATUS archive — {today:%Y-%m} (rolled off from STATUS.md by "
        "status_retention.py, L181)\n\n"
        "> Verbatim older STATUS.md entries, newest-first within each roll. "
        "STATUS.md keeps the newest entries that fit the Read cap; this file is the "
        "cold tail. Nothing deleted.\n\n"
    )


def _insert_roll(existing: str, roll_block: str, today: dt.date) -> str:
    """Insert a new roll at the TOP of the archive body (after the header preamble)."""
    if not existing.strip():
        return _archive_header(today) + roll_block
    marker = existing.find("<!-- rolled off")
    if marker == -1:
        # No prior roll marker; append a header if missing, then the roll.
        if existing.startswith("# STATUS archive"):
            return existing.rstrip() + "\n\n" + roll_block
        return _archive_header(today) + roll_block + existing
    head = existing[:marker]
    tail = existing[marker:]
    return head + roll_block + tail


def apply_consolidation(status_path: str, max_keep_bytes: int, min_keep: int,
                        today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    with open(status_path, "r", encoding="utf-8") as fh:
        text = fh.read()

    plan = plan_consolidation(text, max_keep_bytes, min_keep)
    if plan["n_rolled"] == 0:
        return {"changed": False, "n_kept": plan["n_kept"], "n_rolled": 0,
                "new_bytes": len(text.encode("utf-8"))}

    rolled = plan["rolled_entries"]
    rolled_lines = sum(e.count("\n") for e in rolled)
    roll_block = (
        f"\n<!-- rolled off {today:%Y-%m-%d} by status_retention.py "
        f"(L181 consolidation): {len(rolled)} entries / {rolled_lines} lines -->\n\n"
        + "".join(rolled).rstrip() + "\n\n"
    )

    archive_path = _archive_path(status_path, today)
    existing = ""
    if os.path.exists(archive_path):
        with open(archive_path, "r", encoding="utf-8") as fh:
            existing = fh.read()
    new_archive = _insert_roll(existing, roll_block, today)

    # Atomic writes (temp + replace) so a crash can't corrupt the live state file.
    _atomic_write(archive_path, new_archive)
    _atomic_write(status_path, plan["kept_text"])

    return {"changed": True, "n_kept": plan["n_kept"], "n_rolled": plan["n_rolled"],
            "new_bytes": len(plan["kept_text"].encode("utf-8")),
            "archive_path": archive_path}


def _atomic_write(path: str, content: str) -> None:
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Consolidate STATUS.md (L181 retention guard).")
    ap.add_argument("--status-path", default=STATUS_PATH)
    ap.add_argument("--max-keep-bytes", type=int, default=DEFAULT_MAX_KEEP_BYTES)
    ap.add_argument("--min-keep", type=int, default=DEFAULT_MIN_KEEP)
    ap.add_argument("--check", action="store_true",
                    help="report only; exit 2 if over budget, 0 if fits")
    args = ap.parse_args(argv)

    try:
        if not os.path.exists(args.status_path):
            print(f"status_retention: {args.status_path} missing -> noop")
            return 0
        size = os.path.getsize(args.status_path)
        if args.check:
            over = size > args.max_keep_bytes
            print(f"status_retention --check: {size} bytes "
                  f"({'OVER' if over else 'within'} budget {args.max_keep_bytes})")
            return 2 if over else 0
        res = apply_consolidation(args.status_path, args.max_keep_bytes, args.min_keep)
        if res["changed"]:
            print(f"status_retention: kept {res['n_kept']} entries "
                  f"({res['new_bytes']} bytes), rolled {res['n_rolled']} to "
                  f"{os.path.basename(res['archive_path'])}")
        else:
            print(f"status_retention: within budget ({res['new_bytes']} bytes, "
                  f"{res['n_kept']} entries) -> noop")
        return 0
    except Exception as exc:  # fail-open (L181/OP-25): never raise into a caller
        print(f"status_retention: FAIL-OPEN noop ({type(exc).__name__}: {exc})",
              file=sys.stderr)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
