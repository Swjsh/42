"""Tests for twin_ledger_io.py + twin_ledger_rotate.py (OP-22 retention cap for
automation/state/crypto-twin/decisions.jsonl, 2026-09-15). All fixtures use tmp_path --
never the real ledger."""
from __future__ import annotations

import gzip
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in ("setup/scripts",):
    if str(REPO / _p) not in sys.path:
        sys.path.insert(0, str(REPO / _p))

import twin_ledger_io as tlio  # noqa: E402
import twin_ledger_rotate as rot  # noqa: E402


def _row(date_str: str, seq: int, action: str = "HOLD") -> dict:
    return {
        "ts_utc": f"{date_str}T{seq % 24:02d}:00:00+00:00",
        "ts_et": f"{date_str}T{seq % 24:02d}:00:00",
        "session_date_utc": date_str,
        "action": action,
        "seq": seq,
    }


def _write_live(path: Path, rows: list[dict]) -> None:
    # newline="" -- matches the real writer (crypto_twin_core.log_decision's
    # open(p, "a", encoding="utf-8").write(...)): LF-only, no platform newline
    # translation, so fixtures behave like the real 147MB production ledger (confirmed
    # by its custody snapshot: ~2 stray \r\n out of 58,876 lines, not one-per-line).
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8", newline="")


def _mk_multiday(tmp_path: Path, days: list[str], rows_per_day: int = 3):
    live = tmp_path / "decisions.jsonl"
    archive_dir = tmp_path / "archive"
    rows = []
    for d in days:
        for i in range(rows_per_day):
            rows.append(_row(d, i))
    _write_live(live, rows)
    return live, archive_dir, rows


# ─────────────────────────────────────────────────────────────────────────────────────
# twin_ledger_io: identical rows across the live+archive boundary vs a single file
# ─────────────────────────────────────────────────────────────────────────────────────
def test_iter_rows_matches_single_file_before_any_rotation(tmp_path):
    live, archive_dir, rows = _mk_multiday(tmp_path, ["2026-09-10", "2026-09-11", "2026-09-12"])
    got = tlio.read_rows(live_path=live, archive_dir=archive_dir)
    assert got == rows


def test_iter_rows_identical_across_rotation_boundary(tmp_path):
    days = ["2026-09-10", "2026-09-11", "2026-09-12", "2026-09-13"]
    live, archive_dir, rows = _mk_multiday(tmp_path, days)
    now_utc = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)  # "today" = 09-13

    result = rot.rotate(live_path=live, archive_dir=archive_dir, now_utc=now_utc)
    assert result["status"] == "OK"

    got_after = tlio.read_rows(live_path=live, archive_dir=archive_dir)
    assert got_after == rows  # ALL rows still reachable, same order, same content


def test_since_utc_filters_to_lookback_window(tmp_path):
    days = ["2026-09-10", "2026-09-11", "2026-09-12", "2026-09-13"]
    live, archive_dir, rows = _mk_multiday(tmp_path, days)
    now_utc = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
    rot.rotate(live_path=live, archive_dir=archive_dir, now_utc=now_utc)

    got = tlio.read_rows(since_utc="2026-09-12", live_path=live, archive_dir=archive_dir)
    got_days = {r["session_date_utc"] for r in got}
    assert got_days == {"2026-09-12", "2026-09-13"}


def test_read_last_row_always_from_live_file(tmp_path):
    days = ["2026-09-10", "2026-09-11", "2026-09-12", "2026-09-13"]
    live, archive_dir, rows = _mk_multiday(tmp_path, days)
    now_utc = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
    rot.rotate(live_path=live, archive_dir=archive_dir, now_utc=now_utc)

    last = tlio.read_last_row(live_path=live)
    assert last == rows[-1]


# ─────────────────────────────────────────────────────────────────────────────────────
# rotation never touches today's rows
# ─────────────────────────────────────────────────────────────────────────────────────
def test_rotation_never_touches_today(tmp_path):
    days = ["2026-09-12", "2026-09-13"]
    live, archive_dir, rows = _mk_multiday(tmp_path, days)
    now_utc = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)

    rot.rotate(live_path=live, archive_dir=archive_dir, now_utc=now_utc)

    remaining = [json.loads(l) for l in live.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert all(r["session_date_utc"] == "2026-09-13" for r in remaining)
    assert len(remaining) == 3
    assert not (archive_dir / "decisions-2026-09-13.jsonl.gz").exists()
    assert (archive_dir / "decisions-2026-09-12.jsonl.gz").exists()


def test_dry_run_writes_nothing(tmp_path):
    days = ["2026-09-12", "2026-09-13"]
    live, archive_dir, rows = _mk_multiday(tmp_path, days)
    now_utc = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
    before = live.read_bytes()

    result = rot.rotate(live_path=live, archive_dir=archive_dir, now_utc=now_utc, dry_run=True)

    assert result["status"] == "DRY_RUN"
    assert live.read_bytes() == before
    assert not archive_dir.exists()


def test_noop_when_only_today_present(tmp_path):
    live, archive_dir, rows = _mk_multiday(tmp_path, ["2026-09-13"])
    now_utc = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
    result = rot.rotate(live_path=live, archive_dir=archive_dir, now_utc=now_utc)
    assert result["status"] == "NOOP"


def test_overlapping_rotate_calls_do_not_double_archive(tmp_path):
    """2026-09-15 incident: two rotate() invocations against the same not-yet-reduced
    live file (e.g. an accidental double-fire) each independently compute the SAME
    completed day's lines; the merge-with-existing branch in _write_archive_verified
    used to concatenate blindly, silently doubling every archived row. Must be
    idempotent instead."""
    days = ["2026-09-12", "2026-09-13"]
    live, archive_dir, rows = _mk_multiday(tmp_path, days)
    now_utc = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)

    p = rot.plan(live_path=live, now_utc=now_utc)  # snapshot BEFORE either "run"
    # Simulate two overlapping invocations both archiving from the SAME snapshot (the
    # live file itself is deliberately NOT reduced here -- this isolates the archive
    # write path, which is exactly where the 2026-09-15 incident's duplication lived).
    for date_str, lines in sorted(p["_by_day"].items()):
        rot._write_archive_verified(date_str, lines, archive_dir=archive_dir)
    for date_str, lines in sorted(p["_by_day"].items()):
        rot._write_archive_verified(date_str, lines, archive_dir=archive_dir)

    archived_0912 = list(tlio._iter_archive_rows(archive_dir / "decisions-2026-09-12.jsonl.gz"))
    assert len(archived_0912) == 3  # NOT 6 -- deduplicated, not doubled


# ─────────────────────────────────────────────────────────────────────────────────────
# archive verification (row count + sha) actually checked before live file is touched
# ─────────────────────────────────────────────────────────────────────────────────────
def test_archived_gz_row_count_and_sha_match(tmp_path):
    days = ["2026-09-12", "2026-09-13"]
    live, archive_dir, rows = _mk_multiday(tmp_path, days, rows_per_day=5)
    now_utc = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)

    result = rot.rotate(live_path=live, archive_dir=archive_dir, now_utc=now_utc)
    entry = result["archived"][0]
    assert entry["date"] == "2026-09-12"
    assert entry["rows"] == 5

    gz_path = Path(entry["path"])
    with gzip.open(gz_path, "rt", encoding="utf-8") as fh:
        lines = [l for l in fh if l.strip()]
    assert len(lines) == 5
    import hashlib
    payload = ("\n".join(l.rstrip("\n") for l in lines) + "\n").encode("utf-8")
    assert hashlib.sha256(payload).hexdigest() == entry["sha256"]


# ─────────────────────────────────────────────────────────────────────────────────────
# --restore round-trips
# ─────────────────────────────────────────────────────────────────────────────────────
def test_restore_round_trips_row_content(tmp_path):
    days = ["2026-09-10", "2026-09-11", "2026-09-12", "2026-09-13"]
    live, archive_dir, rows = _mk_multiday(tmp_path, days)
    now_utc = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
    rot.rotate(live_path=live, archive_dir=archive_dir, now_utc=now_utc)

    restore_result = rot.restore(live_path=live, archive_dir=archive_dir)
    assert restore_result["status"] == "OK"
    assert restore_result["total_rows"] == len(rows)

    restored_rows = [json.loads(l) for l in live.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert restored_rows == rows


# ─────────────────────────────────────────────────────────────────────────────────────
# concurrent-append safety: a row lands between the gz write and the os.replace swap
# ─────────────────────────────────────────────────────────────────────────────────────
def test_concurrent_append_during_rotation_is_not_lost(tmp_path, monkeypatch):
    days = ["2026-09-12", "2026-09-13"]
    live, archive_dir, rows = _mk_multiday(tmp_path, days)
    now_utc = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)

    new_row = _row("2026-09-13", 99, action="ENTERED")

    real_write_archive = rot._write_archive_verified

    def _write_archive_then_append(date_str, lines, *, archive_dir):
        # Simulate the writer (crypto_twin_core.log_decision, open("a")) appending a
        # fresh row to the LIVE file while this day's archive is being written --
        # exactly the race the module docstring describes.
        with open(live, "a", encoding="utf-8") as f:
            f.write(json.dumps(new_row) + "\n")
        return real_write_archive(date_str, lines, archive_dir=archive_dir)

    monkeypatch.setattr(rot, "_write_archive_verified", _write_archive_then_append)

    result = rot.rotate(live_path=live, archive_dir=archive_dir, now_utc=now_utc)
    assert result["status"] == "OK"
    assert result["rebuild"]["tail_rows_captured"] == 1

    remaining = [json.loads(l) for l in live.read_text(encoding="utf-8").splitlines() if l.strip()]
    # today's 3 original rows + the concurrently-appended row, nothing lost
    assert new_row in remaining
    assert len(remaining) == 4

    # And the row is still visible through the shared reader too.
    all_rows = tlio.read_rows(live_path=live, archive_dir=archive_dir)
    assert new_row in all_rows
    assert len(all_rows) == len(rows) + 1


def test_live_prefix_change_aborts_rebuild(tmp_path):
    """If the live file's prefix is no longer what we read (should be impossible for an
    append-only writer), _rebuild_live refuses to guess rather than risk dropping rows."""
    live = tmp_path / "decisions.jsonl"
    _write_live(live, [_row("2026-09-13", 0)])
    original_bytes = live.read_bytes()
    live.write_text("something completely different\n", encoding="utf-8")

    try:
        rot._rebuild_live(live, original_bytes, ["kept"])
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "prefix changed" in str(e)
