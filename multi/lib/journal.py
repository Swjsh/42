"""multi/lib/journal.py -- append-only trade journaling for the multi-symbol lane (arm multi-1).

WHY THIS FILE EXISTS AND CANNOT REUSE journal/trades.csv
==========================================================
`journal/trades.csv` (the SPY 0DTE book) has one row per trade with `date`, `time_entry`,
`time_exit` columns -- a schema that assumes entry and exit happen on the SAME calendar day,
because a 0DTE position is always flat by 15:50 ET. This lane's whole point is multi-day holds
(`automation/state/multi/params.json` -> `exits.days_to_live: 3`, `entry.min_dte_at_entry: 3`)
-- a Monday entry can exit Thursday. A same-day schema literally cannot represent that: there is
no single `date` field a Mon->Thu trade belongs to.

THE FIX: entry and exit are TWO SEPARATE APPENDS, linked by `trade_id`, written to a dedicated
`journal/trades-multi.csv`. This is not a stylistic choice -- it is forced by the problem: at
entry time the exit is, by construction, unknown for up to 3 sessions. `append_entry()` writes
what is known the moment a fill happens; `append_exit()` writes what is known once it closes,
looks up its own ENTRY row by `trade_id` to compute holding period + P&L, and denormalizes the
entry facts forward onto the EXIT row so a reader never has to join two rows to see one trade.

ENCODING: journal/trades.csv carries a UTF-8 BOM (verified: its first three bytes are
EF BB BF, i.e. it was written with `encoding="utf-8-sig"` or an equivalent BOM-emitting path)
-- a naive `open(path, encoding="utf-8")` reader sees a stray "﻿" glued onto the first
header cell (`"﻿date"` != `"date"`), which silently breaks any code that does
`row["date"]`. This module writes and reads with plain `encoding="utf-8"` (no BOM) everywhere,
by construction, so it never reproduces that bug.

ATOMICITY: every append acquires an exclusive sidecar lock file (`<path>.lock`, created via
O_CREAT|O_EXCL so only one writer can hold it) before opening the CSV, and fsyncs after every
write. A writer that crashes while holding the lock leaves a stale lock file rather than a
corrupt CSV (the CSV itself is never truncated or rewritten, only appended to) -- the next
writer detects the lock is older than `_LOCK_STALE_SEC` and takes it over rather than
deadlocking forever, mirroring this repo's existing lock-based-takeover fix for the entry-claim
race (commit da8fb973, 2026-08-19) rather than the older, riskier rename-dance pattern.

SEPARATION: this module never imports anything from the SPY engine, `multi/core.py`, or the
sibling exit-management modules (`multi/lib/exits.py`, `multi/lib/position_state.py`) currently
under construction alongside it. It is a pure read/write boundary over one CSV file, callable
by anything (a fill handler, a backfill script, a human) that has the facts of a trade.
"""

from __future__ import annotations

import csv
import datetime as dt
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

JOURNAL_PATH = REPO_ROOT / "journal" / "trades-multi.csv"

# Column order is the file's public contract -- append-only, never reorder existing columns.
FIELDNAMES: tuple[str, ...] = (
    "trade_id", "row_type", "arm", "symbol", "contract", "side",
    "entry_date", "entry_time_et", "entry_premium", "qty",
    "exit_date", "exit_time_et", "exit_premium", "exit_reason",
    "holding_period_sessions", "pnl_dollars", "pnl_pct",
    "feed", "spread_pct_at_entry",
)

_LOCK_STALE_SEC = 30.0  # a lock older than this belonged to a writer that crashed; take it over.
_LOCK_POLL_SEC = 0.02
_LOCK_TIMEOUT_SEC = 5.0

_SIDE_MAP = {"C": "C", "CALL": "C", "CALLS": "C", "P": "P", "PUT": "P", "PUTS": "P"}


class JournalError(RuntimeError):
    """Raised loudly on anything that would corrupt or fabricate journal data: a malformed
    entry, an exit with no matching entry, a double-exit, or an unreadable file. This module
    never silently drops a bad row or guesses a missing fact."""


# --- date / session-count helpers -------------------------------------------------------

def parse_date(value: Any) -> dt.date:
    """Accepts a `date`, a `datetime` (takes its date), or an ISO 'YYYY-MM-DD' string."""
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    s = str(value).strip()
    if not s:
        raise JournalError(f"cannot parse an empty date value ({value!r})")
    try:
        return dt.date.fromisoformat(s[:10])
    except ValueError as e:
        raise JournalError(f"cannot parse date {value!r}: {e}") from e


def trading_sessions_held(entry_date: dt.date, exit_date: dt.date) -> int:
    """Weekday (Mon-Fri) sessions elapsed strictly AFTER `entry_date`, through `exit_date`.

    This is a SESSION count, not a calendar-day count -- the distinction is the whole reason
    this function exists. A Friday entry exited the following Monday is naive-calendar 3 days
    apart ((exit - entry).days == 3) but only ONE trading session elapses (Saturday and Sunday
    are not sessions). Same-day entry/exit -> 0 (the position never survived a session
    boundary). US market holidays are NOT excluded (no holiday calendar dependency here) --
    only weekends -- so a hold that spans a holiday is counted one session high; this is a
    disclosed simplification, not silently assumed correct.
    """
    if exit_date < entry_date:
        raise JournalError(
            f"exit_date {exit_date} precedes entry_date {entry_date} -- refusing to compute "
            f"a negative holding period"
        )
    sessions = 0
    d = entry_date
    one_day = dt.timedelta(days=1)
    while d < exit_date:
        d = d + one_day
        if d.weekday() < 5:  # Mon=0 .. Fri=4
            sessions += 1
    return sessions


def _normalize_side(side: Any) -> str:
    key = str(side).strip().upper()
    if key not in _SIDE_MAP:
        raise JournalError(f"side must be one of C/CALL/P/PUT (got {side!r})")
    return _SIDE_MAP[key]


def _fmt_num(v: Optional[float]) -> str:
    return "" if v is None else repr(float(v)) if isinstance(v, float) else str(v)


def _require_positive_int(name: str, v: Any) -> int:
    try:
        f = float(v)
    except (TypeError, ValueError) as e:
        raise JournalError(f"{name} must be numeric (got {v!r})") from e
    if f != int(f) or int(f) <= 0:
        raise JournalError(f"{name} must be a positive whole number (got {v!r})")
    return int(f)


def _require_positive_float(name: str, v: Any) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError) as e:
        raise JournalError(f"{name} must be numeric (got {v!r})") from e
    if f != f or f <= 0:  # NaN check + non-positive
        raise JournalError(f"{name} must be > 0 (got {v!r})")
    return f


# --- lock-based atomic append -------------------------------------------------------------

def _acquire_lock(lock_path: Path) -> None:
    deadline = time.monotonic() + _LOCK_TIMEOUT_SEC
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode("ascii"))
            os.close(fd)
            return
        except FileExistsError:
            try:
                age = time.time() - lock_path.stat().st_mtime
            except OSError:
                age = 0.0
            if age > _LOCK_STALE_SEC:
                # The prior holder crashed mid-write and never released it. Taking over a
                # stale lock (rather than deadlocking the lane's journaling forever) mirrors
                # the repo's existing lock-based-takeover fix for the entry-claim race.
                try:
                    lock_path.unlink()
                except OSError:
                    pass
                continue
            if time.monotonic() > deadline:
                raise JournalError(
                    f"could not acquire journal lock {lock_path} within "
                    f"{_LOCK_TIMEOUT_SEC}s -- another writer is active and not stale yet"
                )
            time.sleep(_LOCK_POLL_SEC)


def _release_lock(lock_path: Path) -> None:
    try:
        lock_path.unlink()
    except OSError:
        pass


def _atomic_append_row(path: Path, row: dict) -> None:
    """Append exactly one CSV row, writing the header first iff the file is new/empty.

    Locked (see module docstring) and fsync'd so a crash mid-write never interleaves bytes
    from two writers, and the durable state on disk after any completed call is exactly the
    prior content plus one well-formed row.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    _acquire_lock(lock_path)
    try:
        is_new = (not path.exists()) or path.stat().st_size == 0
        with path.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(FIELDNAMES))
            if is_new:
                writer.writeheader()
            writer.writerow(row)
            fh.flush()
            os.fsync(fh.fileno())
    finally:
        _release_lock(lock_path)


def _read_rows(path: Path) -> list[dict]:
    """Plain UTF-8 read, tolerant of a crash-truncated trailing partial row (csv.DictReader
    simply yields fewer/shorter fields for it; callers that need a specific row type filter
    it out naturally since a truncated row will be missing `row_type` or `trade_id`)."""
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# --- public write API ------------------------------------------------------------------

def append_entry(
    *,
    trade_id: str,
    symbol: str,
    contract: str,
    side: str,
    entry_date: Any,
    entry_time_et: str,
    entry_premium: float,
    qty: int,
    arm: str = "multi-1",
    feed: str = "indicative",
    spread_pct_at_entry: Optional[float] = None,
    path: Path = JOURNAL_PATH,
) -> dict:
    """Append the ENTRY half of a trade. The exit is unknown at this point by construction --
    this row alone never carries P&L or holding period."""
    if not trade_id or not str(trade_id).strip():
        raise JournalError("trade_id is required and cannot be blank")
    if not symbol or not str(symbol).strip():
        raise JournalError("symbol is required and cannot be blank")
    if not contract or not str(contract).strip():
        raise JournalError("contract is required and cannot be blank")

    existing = _read_rows(path)
    if any(r.get("trade_id") == str(trade_id) and r.get("row_type") == "ENTRY" for r in existing):
        raise JournalError(f"trade_id={trade_id!r} already has an ENTRY row -- refusing duplicate")

    qty_i = _require_positive_int("qty", qty)
    prem_f = _require_positive_float("entry_premium", entry_premium)
    ed = parse_date(entry_date)

    row = {f: "" for f in FIELDNAMES}
    row.update(
        trade_id=str(trade_id), row_type="ENTRY", arm=arm, symbol=str(symbol).upper(),
        contract=str(contract), side=_normalize_side(side),
        entry_date=ed.isoformat(), entry_time_et=str(entry_time_et),
        entry_premium=_fmt_num(prem_f), qty=str(qty_i),
        feed=feed,
        spread_pct_at_entry=_fmt_num(spread_pct_at_entry) if spread_pct_at_entry is not None else "",
    )
    _atomic_append_row(path, row)
    return row


def append_exit(
    *,
    trade_id: str,
    exit_date: Any,
    exit_time_et: str,
    exit_premium: float,
    exit_reason: str,
    path: Path = JOURNAL_PATH,
) -> dict:
    """Append the EXIT half, looked up against its own ENTRY row by `trade_id`.

    Computes `holding_period_sessions` (trading-session count, see `trading_sessions_held`)
    and `pnl_dollars`/`pnl_pct`. This lane is long-premium-only (calls AND puts are both LONG
    positions -- params.json `entry.structure == "long_premium_only"`), so the P&L formula is
    identical for both sides: profit = (exit_premium - entry_premium) * qty * 100. There is no
    short-premium path in this lane, so `side` never flips the sign of this formula.

    Fails loudly (never fabricates or guesses) if: no ENTRY row exists for `trade_id`, the
    trade already has an EXIT row (double-exit), or `exit_date` precedes the recorded
    `entry_date`.
    """
    if not trade_id or not str(trade_id).strip():
        raise JournalError("trade_id is required and cannot be blank")

    rows = _read_rows(path)
    entry_row: Optional[dict] = None
    for r in rows:
        if r.get("trade_id") != str(trade_id):
            continue
        if r.get("row_type") == "ENTRY":
            entry_row = r
        elif r.get("row_type") == "EXIT":
            raise JournalError(
                f"trade_id={trade_id!r} already has an EXIT row -- refusing to double-book P&L"
            )
    if entry_row is None:
        raise JournalError(
            f"no ENTRY row found for trade_id={trade_id!r} -- refusing to fabricate an exit "
            f"for a trade this journal never recorded opening"
        )

    entry_date = parse_date(entry_row["entry_date"])
    exit_date_p = parse_date(exit_date)
    sessions = trading_sessions_held(entry_date, exit_date_p)

    entry_premium = _require_positive_float("entry_premium (from ENTRY row)", entry_row["entry_premium"])
    qty = _require_positive_int("qty (from ENTRY row)", entry_row["qty"])
    exit_premium_f = _require_positive_float("exit_premium", exit_premium)

    pnl_dollars = round((exit_premium_f - entry_premium) * qty * 100.0, 2)
    pnl_pct = round((exit_premium_f - entry_premium) / entry_premium * 100.0, 4)

    row = {f: entry_row.get(f, "") for f in FIELDNAMES}
    row.update(
        row_type="EXIT",
        exit_date=exit_date_p.isoformat(), exit_time_et=str(exit_time_et),
        exit_premium=_fmt_num(exit_premium_f), exit_reason=str(exit_reason),
        holding_period_sessions=str(sessions),
        pnl_dollars=_fmt_num(pnl_dollars), pnl_pct=_fmt_num(pnl_pct),
    )
    _atomic_append_row(path, row)
    return row


# --- public read API ---------------------------------------------------------------------

def all_rows(path: Path = JOURNAL_PATH) -> list[dict]:
    return _read_rows(path)


def open_trades(path: Path = JOURNAL_PATH) -> list[dict]:
    """ENTRY rows with no matching EXIT row yet -- this lane's own open-position book. Honest
    on an empty/missing file: returns `[]` rather than raising (no positions is a valid, common
    state, distinct from a read failure -- `_read_rows` already fails loudly on a genuinely
    corrupt file via csv's own errors propagating)."""
    rows = _read_rows(path)
    entries: dict[str, dict] = {}
    exited: set[str] = set()
    for r in rows:
        tid = r.get("trade_id")
        if not tid:
            continue
        if r.get("row_type") == "ENTRY":
            entries[tid] = r
        elif r.get("row_type") == "EXIT":
            exited.add(tid)
    return [r for tid, r in entries.items() if tid not in exited]


def closed_trades(path: Path = JOURNAL_PATH) -> list[dict]:
    """EXIT rows only -- each one is a complete, denormalized closed trade."""
    return [r for r in _read_rows(path) if r.get("row_type") == "EXIT"]
