"""crew_events.py -- ticker-able crew work log for the HQ world (GOAL-GAMMA-STATION-
2026-09-13 company-roster re-point, 2026-09-14 CREW-RIG build).

WHY THIS EXISTS: J's verdict (2026-09-14) -- "'quiet since 09:05' for Chef -- okay, why?
Same for Coach. Why are they on here if they're not doing anything?" -- Chef's scorer
pass and Coach's sectors pass already run every Station fire (station_loop.py's
run_once(), every 30 min 24/7), but nothing narrates that work anywhere a human (or the
HQ face) can see it happening. This module is the ONE shared, append-only writer for
that narration, so any producer (station_loop.py's scorer/sectors passes today;
trade_autopsy.py's nightly re-score, or a future producer, tomorrow) emits through the
same capped, atomic-write path instead of re-deriving its own jsonl-append-and-trim
logic.

Row shape (caller's responsibility -- this module does not validate it, same contract
as station_board.append_jsonl): {ts_et, who, kind, line, ref, to (optional)}.

Contract: append() NEVER raises -- a broken ticker must never take down its caller. The
Station loop is EXPLICITLY required to survive a crew-events failure (fail-open hard
rule in the build brief); other future callers get the same guarantee for free by using
this module instead of hand-rolling the write.

Cap: DEFAULT_CAP rows, oldest dropped first (atomic tmp+os.replace rewrite only on the
capping path -- the common sub-cap case is a plain append, identical to every other
*.jsonl append in this codebase: station_board.append_jsonl, the loop ledger).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
DEFAULT_PATH = REPO / "automation" / "state" / "station" / "crew-events.jsonl"
DEFAULT_CAP = 500


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def read_rows(path: Optional[Path] = None) -> list:
    """Fail-open JSONL read: one dict per non-blank line; a malformed line is skipped
    rather than aborting the whole read. Missing/unreadable file -> [] (same contract
    as station_board.read_jsonl)."""
    path = path or DEFAULT_PATH
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError:
        return []
    rows: list = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def last_row(*, kind: Optional[str] = None, who: Optional[str] = None,
            ref: Optional[str] = None, path: Optional[Path] = None) -> Optional[dict]:
    """The most recent row matching every given filter, or None if the file is empty/
    missing or nothing matches. Used by producers that need 'what did I last say about
    X' to decide whether this fire is news (e.g. station_loop.py's sectors-heartbeat
    and task-health-delta checks)."""
    rows = read_rows(path)
    for row in reversed(rows):
        if kind is not None and row.get("kind") != kind:
            continue
        if who is not None and row.get("who") != who:
            continue
        if ref is not None and row.get("ref") != ref:
            continue
        return row
    return None


def append(row: dict, *, path: Optional[Path] = None, cap: int = DEFAULT_CAP) -> bool:
    """Appends one row, then caps the file at `cap` rows (oldest dropped first, atomic
    tmp+os.replace rewrite). NEVER raises -- returns True on success, False on any
    failure. This module owns no logger of its own (stays a leaf dependency any
    producer can import without pulling in station_loop.py's logging path); a caller
    that wants a log line on failure checks the return value itself."""
    path = path or DEFAULT_PATH
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        rows = read_rows(path)
        if len(rows) > cap:
            trimmed = rows[-cap:]
            text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in trimmed)
            _atomic_write_text(path, text)
        return True
    except Exception:  # noqa: BLE001 -- a ticker must never crash its caller
        return False
