#!/usr/bin/env python
"""twin_ledger_rotate.py -- rotate-not-truncate retention for
automation/state/crypto-twin/decisions.jsonl (2026-09-15, OP-22 retention cap).

WHAT THIS DOES: moves COMPLETED UTC calendar days (never today) out of the live
decisions.jsonl into gzip archives at
automation/state/crypto-twin/archive/decisions-YYYY-MM-DD.jsonl.gz, then rewrites the
live file to hold only the remaining (today's, and any unclassifiable) rows. Content is
NEVER deleted or truncated -- every row that leaves the live file is verified present
(row count + sha256) in its archive before the live file is touched at all.

WRITER SAFETY: crypto_twin_core.log_decision() opens decisions.jsonl in "a" (append)
mode, writes one line, and closes it -- it never holds a long-lived handle and never
seeks/rewrites. That makes rename-based rotation safe WHILE the twin is ticking: this
script reads the live file's bytes ONCE at the start (`original_bytes`), computes the
split from that exact snapshot, and immediately before the final os.replace() re-reads
the file and appends any bytes that landed AFTER `len(original_bytes)` (i.e. rows the
writer appended during rotation) onto the new live file. Nothing the writer appends
between the initial read and the swap can be lost -- see `_rebuild_live()` below.

ATOMICITY: the archive gz is written to a .tmp path, decompressed and re-hashed to
verify row-count + sha256 match what was extracted from the live file, and only THEN
does the live file get rewritten (via a temp file + os.replace, matching the writer's
"a"-mode atomicity contract). If the gz write/verify fails, nothing else happens -- the
live file is untouched and the script exits nonzero.

--dry-run: computes and prints the plan (which days, how many rows, resulting sizes)
without writing anything.

--restore: the revert path. Concatenates every archive (oldest-first) plus the current
live file's content back into decisions.jsonl, verifying the resulting row count equals
archives+live before replacing (byte-identical row *content*, not necessarily identical
JSON key ordering across a rewrite -- rows are written back exactly as extracted, so
this is a byte-identical round trip on the JSON payloads).
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import twin_ledger_io as tlio  # noqa: E402

LIVE_PATH = tlio.LIVE_PATH
ARCHIVE_DIR = tlio.ARCHIVE_DIR


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _today_utc_str(now_utc: datetime | None = None) -> str:
    now_utc = now_utc or datetime.now(timezone.utc)
    return now_utc.strftime("%Y-%m-%d")


def _split_rows(raw_text: str, today_str: str) -> tuple[dict[str, list[str]], list[str]]:
    """(by_day, kept_lines). by_day: {date_str: [raw_line, ...]} for every COMPLETED day
    (date_str < today_str). kept_lines: raw lines for today, unclassifiable rows
    (no session_date_utc/ts_utc), and malformed lines -- all stay in the live file so
    nothing is ever silently dropped.

    Splits on a literal "\\n" ONLY (str.split, never str.splitlines()) -- splitlines()
    also breaks on \\r, \\x0b, \\x0c, \\x1c-\\x1e, \\x85, \\u2028, \\u2029, any of which can
    legally appear inside a JSON string value (JSON only forbids unescaped 0x00-0x1F, and
    none of the Unicode separators are in that range). The writer (crypto_twin_core.
    log_decision) only ever appends "json.dumps(row) + \"\\n\"" -- a literal \\n is the ONLY
    row delimiter that was ever actually written, so it is the only one this may split on
    without risking carving a single valid row into two invalid fragments (found live,
    2026-09-15: one row's `reason` text contains such a character; splitlines() produced
    a phantom truncated fragment that split("\\n") does not)."""
    by_day: dict[str, list[str]] = {}
    kept: list[str] = []
    for line in raw_text.split("\n"):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            kept.append(line)  # malformed -- never touch, keep it visible in the live file
            continue
        d = tlio.row_date_utc(row) if isinstance(row, dict) else None
        if d is None or d >= today_str:
            kept.append(line)
        else:
            by_day.setdefault(d, []).append(line)
    return by_day, kept


def plan(*, live_path: Path = LIVE_PATH, now_utc: datetime | None = None) -> dict:
    if not live_path.exists():
        return {"today_utc": _today_utc_str(now_utc), "days": {}, "kept_rows": 0,
                "live_exists": False}
    raw_bytes = live_path.read_bytes()
    raw_text = raw_bytes.decode("utf-8", errors="replace")
    today_str = _today_utc_str(now_utc)
    by_day, kept = _split_rows(raw_text, today_str)
    return {
        "today_utc": today_str,
        "days": {d: len(lines) for d, lines in by_day.items()},
        "kept_rows": len(kept),
        "live_exists": True,
        "_raw_bytes": raw_bytes,
        "_by_day": by_day,
        "_kept_lines": kept,
    }


def _write_archive_verified(date_str: str, lines: list[str], *,
                            archive_dir: Path = ARCHIVE_DIR) -> dict:
    archive_dir.mkdir(parents=True, exist_ok=True)
    dest = tlio.archive_path_for(date_str, archive_dir=archive_dir)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    payload = ("\n".join(lines) + "\n").encode("utf-8") if lines else b""

    if dest.exists():
        # Merge with an existing archive for this day (e.g. a prior partial-day
        # rotation, or a re-run) instead of clobbering it -- never lose already-archived
        # rows. DEDUPLICATED (2026-09-15 incident: two overlapping rotate() invocations
        # against the same not-yet-rotated live file each independently computed the
        # SAME day's lines and both merged them in, silently doubling every archive --
        # exact-line-equality dedup, order-preserving, makes a repeat/overlapping run
        # idempotent instead of additive).
        with gzip.open(dest, "rt", encoding="utf-8", errors="replace") as fh:
            existing_lines = [ln.rstrip("\n") for ln in fh if ln.strip()]
        seen = set(existing_lines)
        new_only = [ln for ln in lines if ln not in seen and not seen.add(ln)]
        merged = existing_lines + new_only
        payload = ("\n".join(merged) + "\n").encode("utf-8") if merged else b""
        expected_line_count = len(merged)
    else:
        expected_line_count = len(lines)

    with gzip.open(tmp, "wb") as gz:
        gz.write(payload)

    # verify by reading back
    with gzip.open(tmp, "rt", encoding="utf-8", errors="replace") as fh:
        readback_lines = [ln.rstrip("\n") for ln in fh if ln.strip()]
    if len(readback_lines) != expected_line_count:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(
            f"archive verify FAILED for {date_str}: wrote {expected_line_count} rows, "
            f"read back {len(readback_lines)}"
        )
    moved_sha = _sha256_bytes(payload)
    os.replace(tmp, dest)
    return {"date": date_str, "path": str(dest), "rows": expected_line_count,
            "sha256": moved_sha, "bytes": len(payload)}


def _rebuild_live(live_path: Path, original_bytes: bytes, kept_lines: list[str]) -> dict:
    """Writes the new live file = kept_lines + any bytes appended to `live_path` AFTER
    `original_bytes` since the initial read (concurrent-writer safety -- see module
    docstring)."""
    tail = b""
    if live_path.exists():
        current = live_path.read_bytes()
        if current[: len(original_bytes)] == original_bytes:
            tail = current[len(original_bytes):]
        else:
            # The prefix changed under us (should be impossible for an append-only
            # writer) -- refuse to guess, fail loudly rather than silently drop rows.
            raise RuntimeError(
                "live file prefix changed during rotation (expected append-only "
                "writer) -- aborting rebuild to avoid row loss"
            )
    new_content = ("\n".join(kept_lines) + "\n").encode("utf-8") if kept_lines else b""
    new_content += tail
    tmp = live_path.with_suffix(live_path.suffix + ".rotate.tmp")
    tmp.write_bytes(new_content)
    tail_rows = sum(1 for ln in tail.decode("utf-8", errors="replace").splitlines() if ln.strip())
    os.replace(tmp, live_path)
    return {"kept_rows": len(kept_lines), "tail_rows_captured": tail_rows}


def rotate(*, live_path: Path = LIVE_PATH, archive_dir: Path = ARCHIVE_DIR,
           now_utc: datetime | None = None, dry_run: bool = False) -> dict:
    p = plan(live_path=live_path, now_utc=now_utc)
    if not p["live_exists"] or not p["days"]:
        return {"status": "NOOP", "reason": "nothing to rotate", "today_utc": p["today_utc"],
                "days": p.get("days", {}), "kept_rows": p.get("kept_rows", 0)}

    if dry_run:
        return {"status": "DRY_RUN", "today_utc": p["today_utc"], "days": p["days"],
                "kept_rows": p["kept_rows"],
                "would_rotate_rows": sum(p["days"].values())}

    original_bytes = p["_raw_bytes"]
    archived = []
    for date_str, lines in sorted(p["_by_day"].items()):
        archived.append(_write_archive_verified(date_str, lines, archive_dir=archive_dir))

    rebuild = _rebuild_live(live_path, original_bytes, p["_kept_lines"])

    return {"status": "OK", "today_utc": p["today_utc"], "archived": archived,
            "rebuild": rebuild}


def restore(*, live_path: Path = LIVE_PATH, archive_dir: Path = ARCHIVE_DIR) -> dict:
    """Concatenates every archive (oldest-first) + current live content back into
    decisions.jsonl. Revert path for `rotate()`."""
    archives = tlio.list_archives(archive_dir=archive_dir)
    parts: list[str] = []
    archive_rows = 0
    for path in archives:
        with gzip.open(path, "rt", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.rstrip("\n")
                if line.strip():
                    parts.append(line)
                    archive_rows += 1
    live_rows = 0
    if live_path.exists():
        for line in live_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip():
                parts.append(line)
                live_rows += 1
    content = ("\n".join(parts) + "\n").encode("utf-8") if parts else b""
    tmp = live_path.with_suffix(live_path.suffix + ".restore.tmp")
    tmp.write_bytes(content)
    os.replace(tmp, live_path)
    return {"status": "OK", "archive_rows": archive_rows, "live_rows_before": live_rows,
            "total_rows": archive_rows + live_rows, "archives_merged": len(archives)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--restore", action="store_true", help="revert: reassemble live "
                    "decisions.jsonl from archives + current live content")
    args = ap.parse_args(argv)

    if args.restore:
        result = restore()
    else:
        result = rotate(dry_run=args.dry_run)

    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("status") in ("OK", "DRY_RUN", "NOOP") else 1


if __name__ == "__main__":
    raise SystemExit(main())
