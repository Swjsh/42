"""twin_ledger_io.py -- shared read path for the crypto twin's decisions.jsonl ledger,
across the rotation boundary (twin_ledger_rotate.py).

WHY THIS EXISTS (2026-09-15, OP-22 retention cap): automation/state/crypto-twin/
decisions.jsonl grew unbounded (147.6 MB / 58,873 rows at ~3.6 MB/day, ~1 tick/min
24/7) because every reader either full-scanned the live file or opened it directly.
twin_ledger_rotate.py moves COMPLETED UTC days into gzip archives at
automation/state/crypto-twin/archive/decisions-YYYY-MM-DD.jsonl.gz, leaving only the
still-open day(s) in the live file. Every reader that used to open decisions.jsonl
directly for anything beyond "today" or "the last few hours" MUST route through this
module instead, or it will silently see an INCOMPLETE ledger after the first rotation
(no crash -- just missing history, which is worse: OP-25/C7 "silent success is
failure").

CONTRACT
========
* `iter_rows(since_utc=None)` yields every decision row (dict) in chronological file
  order: archives oldest-first (filtered to those that could contain a row on/after
  `since_utc`, by filename date), then the live file. Malformed lines are skipped
  (mirrors every existing reader's `except json.JSONDecodeError: continue`).
* `since_utc=None` means ALL TIME -- a reader that needs full history (e.g.
  crypto_twin_pnl.reconstruct_trips, which reconstructs every organic trip ever) gets
  it exactly as before rotation, just reassembled from archive + live instead of one
  file.
* `since_utc="YYYY-MM-DD"` (a UTC calendar-day string) skips any archive whose date is
  strictly before that day -- this is what cuts crypto_twin_health.py's ~1/min 147 MB
  full scan down to "today's rows" or "the last soak hour".
* ROTATION SAFETY: this module never mutates anything. It only reads. The live file is
  always read in full (it holds at most ~1 day + whatever hasn't rotated yet), so a
  reader combining archives (bounded, gzip, read once) with the live file (small,
  always current) never sees a torn write -- the writer (crypto_twin_core.log_decision)
  opens the file in "a" append-per-row mode, so a read mid-append sees a clean prefix
  of complete lines at worst (the trailing partial line, if any, fails json.loads and
  is skipped exactly like every other malformed-line guard in this codebase).

Day partitioning uses the row's own `session_date_utc` field (already stamped by
crypto_twin_core._decision_row on every row) FIRST, falling back to the date portion of
`ts_utc` only when `session_date_utc` is absent -- same precedence
crypto_twin_health.evaluate_tick_freshness's ticks-today loop already uses, chosen
deliberately over `ts_utc` alone because of the TWIN-TS-UTC-DRIFT bug (twin_sentinel.py
_row_effective_utc's docstring): some HOLD_BAD_BARS rows carry a frozen-wrong ts_utc
while session_date_utc (stamped from the levels object, a different code path) has not
been observed to drift the same way.
"""
from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Iterator, Optional

REPO = Path(__file__).resolve().parents[2]
TWIN_DIR = REPO / "automation" / "state" / "crypto-twin"
LIVE_PATH = TWIN_DIR / "decisions.jsonl"
ARCHIVE_DIR = TWIN_DIR / "archive"
ARCHIVE_PREFIX = "decisions-"
ARCHIVE_SUFFIX = ".jsonl.gz"


def row_date_utc(row: dict) -> Optional[str]:
    """The row's UTC calendar day (YYYY-MM-DD), or None if neither field is usable."""
    d = row.get("session_date_utc")
    if isinstance(d, str) and len(d) == 10:
        return d
    ts = row.get("ts_utc")
    if isinstance(ts, str) and len(ts) >= 10:
        return ts[:10]
    return None


def archive_path_for(date_str: str, *, archive_dir: Path = ARCHIVE_DIR) -> Path:
    return archive_dir / f"{ARCHIVE_PREFIX}{date_str}{ARCHIVE_SUFFIX}"


def list_archives(*, archive_dir: Path = ARCHIVE_DIR) -> list[Path]:
    """Every rotated archive file, sorted oldest-first by the date in its filename."""
    if not archive_dir.is_dir():
        return []
    hits = []
    for p in archive_dir.glob(f"{ARCHIVE_PREFIX}*{ARCHIVE_SUFFIX}"):
        date_str = p.name[len(ARCHIVE_PREFIX):-len(ARCHIVE_SUFFIX)]
        if len(date_str) == 10:
            hits.append((date_str, p))
    hits.sort(key=lambda t: t[0])
    return [p for _, p in hits]


def _parse_lines(lines) -> Iterator[dict]:
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(row, dict):
            yield row


def _iter_archive_rows(path: Path) -> Iterator[dict]:
    try:
        with gzip.open(path, "rt", encoding="utf-8", errors="replace") as fh:
            yield from _parse_lines(fh)
    except OSError:
        return


def _iter_live_rows(path: Path) -> Iterator[dict]:
    if not path.exists():
        return
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            yield from _parse_lines(fh)
    except OSError:
        return


def iter_rows(since_utc: Optional[str] = None, *, live_path: Path = LIVE_PATH,
             archive_dir: Path = ARCHIVE_DIR) -> Iterator[dict]:
    """Every decision row on/after `since_utc` (a "YYYY-MM-DD" UTC date string), or ALL
    rows when `since_utc` is None. Archives oldest-first, then the live file, so
    callers that care about order get chronological order (the writer only appends, and
    rotation preserves per-day ordering)."""
    for archive in list_archives(archive_dir=archive_dir):
        date_str = archive.name[len(ARCHIVE_PREFIX):-len(ARCHIVE_SUFFIX)]
        if since_utc is not None and date_str < since_utc:
            continue
        for row in _iter_archive_rows(archive):
            if since_utc is None:
                yield row
            else:
                d = row_date_utc(row)
                if d is None or d >= since_utc:
                    yield row
    for row in _iter_live_rows(live_path):
        if since_utc is None:
            yield row
        else:
            d = row_date_utc(row)
            if d is None or d >= since_utc:
                yield row


def read_rows(since_utc: Optional[str] = None, *, live_path: Path = LIVE_PATH,
              archive_dir: Path = ARCHIVE_DIR) -> list[dict]:
    return list(iter_rows(since_utc, live_path=live_path, archive_dir=archive_dir))


def count_rows(since_utc: Optional[str] = None, *, live_path: Path = LIVE_PATH,
               archive_dir: Path = ARCHIVE_DIR) -> int:
    return sum(1 for _ in iter_rows(since_utc, live_path=live_path, archive_dir=archive_dir))


def read_last_row(*, live_path: Path = LIVE_PATH) -> Optional[dict]:
    """The most recent row. Always reachable from the LIVE file alone -- rotation never
    touches today's rows, so the newest row is always still in decisions.jsonl."""
    last: Optional[dict] = None
    for row in _iter_live_rows(live_path):
        last = row
    return last
