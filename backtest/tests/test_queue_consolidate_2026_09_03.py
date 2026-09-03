"""setup/scripts/queue_consolidate.py -- deterministic queue.md retention-cap consolidation.

Replaces the hand pass done 2026-08-19, 2026-08-29, and twice on 2026-09-02 (folded into
QUEUE-MD-RETENTION-CAP in automation/overnight/queue.md). Everything here operates on
tmp_path fixtures built to mimic queue.md's real shape -- NEVER on the live queue.md or a
live queue-archive-*.md.

Covers: terminal-status selection ([x] + status: OR head CLOSED/DONE/SHIPPED/RESOLVED+date),
[~]/[ ] never selected, depends: blocking with a printed reason, byte-for-byte CRLF
preservation on untouched lines, verbatim archive content, restore-on-failure, and the
pointer line being updated in place rather than duplicated across runs.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import queue_consolidate as qc  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture builder -- mimics queue.md's real shape: UTF-8 BOM, CRLF everywhere.
# ---------------------------------------------------------------------------

def make_queue_bytes(active_backlog_lines: list[str], preamble: list[str] | None = None) -> bytes:
    preamble = preamble if preamble is not None else ["# OVERNIGHT TASK QUEUE", ""]
    body = preamble + ["## Active backlog"] + active_backlog_lines
    text = "\r\n".join(body) + "\r\n"
    return b"\xef\xbb\xbf" + text.encode("utf-8")


ITEM_DONE = "- [x] ITEM-DONE (LOW) :: some resolved work :: depends:none :: status:done"
ITEM_CLOSED_DUP = (
    "- [x] ITEM-CLOSED-DUP (LOW) :: dup work :: depends:none :: status:closed-duplicate"
)
ITEM_HEAD_CLOSED_DATE = (
    "- [x] ITEM-HEAD-CLOSED (LOW, CLOSED 2026-09-01 by audit) :: desc :: depends:none "
    ":: status:in_progress"
)
ITEM_X_BUT_PENDING = "- [x] ITEM-X-PENDING (LOW) :: checked but not terminal :: depends:none :: status:pending"
ITEM_OPEN = "- [ ] ITEM-OPEN (LOW) :: still working :: depends:none :: status:pending"
ITEM_DEFERRED = "- [~] ITEM-DEFERRED (LOW) :: deferred :: depends:none :: status:closed"
HEADING_SECTION = "### Some Section (filed 2026-08-01)"
# Regression fixture for a real false positive caught on the live queue.md dry-run
# (2026-09-03): a lowercase "fail-closed" hyphenated compound inside a description,
# alongside an unrelated date, must NOT match the CLOSED-marker head rule -- only an
# exact-case, all-caps CLOSED/DONE/SHIPPED/RESOLVED marker should.
ITEM_LOWERCASE_CLOSED_COMPOUND = (
    "- [x] ITEM-GUARD-INVERT (LOW) :: RED-proofed 2026-09-01 (inverted the fail-closed "
    "guard) :: depends:none :: status:built-not-drilled"
)


@pytest.fixture()
def queue_path(tmp_path):
    return tmp_path / "queue.md"


@pytest.fixture()
def archive_dir(tmp_path):
    d = tmp_path / "archive"
    d.mkdir()
    return d


def write_fixture(queue_path: Path, lines: list[str]) -> bytes:
    data = make_queue_bytes(lines)
    queue_path.write_bytes(data)
    return data


# ---------------------------------------------------------------------------
# Selection logic
# ---------------------------------------------------------------------------

def test_terminal_status_selected(queue_path, archive_dir):
    original = write_fixture(queue_path, [ITEM_DONE, ITEM_CLOSED_DUP, ITEM_X_BUT_PENDING])
    rc = qc.run(queue_path, archive_dir, apply=True, min_headroom=20_000)
    assert rc == 0
    new_bytes = queue_path.read_bytes()
    assert b"ITEM-DONE" not in new_bytes
    assert b"ITEM-CLOSED-DUP" not in new_bytes
    # not terminal, not archived -- must remain
    assert b"ITEM-X-PENDING" in new_bytes


def test_head_closed_with_date_selected_even_if_status_not_terminal(queue_path, archive_dir):
    write_fixture(queue_path, [ITEM_HEAD_CLOSED_DATE])
    rc = qc.run(queue_path, archive_dir, apply=True, min_headroom=20_000)
    assert rc == 0
    new_bytes = queue_path.read_bytes()
    assert b"ITEM-HEAD-CLOSED" not in new_bytes
    archives = list(archive_dir.glob("queue-archive-*.md"))
    assert len(archives) == 1
    assert "ITEM-HEAD-CLOSED" in archives[0].read_text(encoding="utf-8")


def test_open_and_deferred_checkboxes_never_selected(queue_path, archive_dir):
    original = write_fixture(queue_path, [ITEM_OPEN, ITEM_DEFERRED, ITEM_DONE])
    rc = qc.run(queue_path, archive_dir, apply=True, min_headroom=20_000)
    assert rc == 0
    new_bytes = queue_path.read_bytes()
    # [ ] and [~] survive even though ITEM-DEFERRED's status:closed would otherwise qualify
    assert b"ITEM-OPEN" in new_bytes
    assert b"ITEM-DEFERRED" in new_bytes
    assert b"ITEM-DONE" not in new_bytes


def test_lowercase_closed_inside_hyphenated_compound_is_not_a_marker(queue_path, archive_dir):
    write_fixture(queue_path, [ITEM_LOWERCASE_CLOSED_COMPOUND])
    rc = qc.run(queue_path, archive_dir, apply=True, min_headroom=20_000)
    assert rc == 0
    # status:built-not-drilled is not terminal, and "fail-closed" (lowercase, inside a
    # hyphenated compound) must not be read as a CLOSED marker just because a date is
    # elsewhere in the head line.
    assert b"ITEM-GUARD-INVERT" in queue_path.read_bytes()
    assert not list(archive_dir.glob("queue-archive-*.md"))


def test_headings_never_selected(queue_path, archive_dir):
    write_fixture(queue_path, [HEADING_SECTION, ITEM_DONE])
    rc = qc.run(queue_path, archive_dir, apply=True, min_headroom=20_000)
    assert rc == 0
    new_bytes = queue_path.read_bytes()
    assert b"Some Section" in new_bytes


# ---------------------------------------------------------------------------
# depends: blocking
# ---------------------------------------------------------------------------

def test_depends_reference_blocks_archival_and_prints_reason(queue_path, archive_dir, capsys):
    lines = [
        ITEM_DONE.replace("ITEM-DONE", "ITEM-G"),
        "- [ ] ITEM-H (LOW) :: needs G first :: depends:ITEM-G :: status:pending",
    ]
    write_fixture(queue_path, lines)
    rc = qc.run(queue_path, archive_dir, apply=True, min_headroom=20_000)
    assert rc == 0
    new_bytes = queue_path.read_bytes()
    # ITEM-G must NOT have been archived -- ITEM-H still depends on it
    assert b"ITEM-G" in new_bytes
    assert not list(archive_dir.glob("queue-archive-*.md"))
    out = capsys.readouterr().out
    assert "ITEM-G" in out and "depends" in out.lower()
    assert "ITEM-H" in out


def test_depends_does_not_block_unrelated_candidates(queue_path, archive_dir):
    lines = [
        ITEM_DONE.replace("ITEM-DONE", "ITEM-G"),
        ITEM_DONE.replace("ITEM-DONE", "ITEM-Z"),
        "- [ ] ITEM-H (LOW) :: needs G first :: depends:ITEM-G :: status:pending",
    ]
    write_fixture(queue_path, lines)
    rc = qc.run(queue_path, archive_dir, apply=True, min_headroom=20_000)
    assert rc == 0
    new_bytes = queue_path.read_bytes()
    assert b"ITEM-G" in new_bytes  # blocked
    assert b"ITEM-Z" not in new_bytes  # unrelated candidate still archives


# ---------------------------------------------------------------------------
# CRLF byte-for-byte preservation
# ---------------------------------------------------------------------------

def test_untouched_lines_keep_crlf_and_bom(queue_path, archive_dir):
    lines = [ITEM_OPEN, ITEM_DONE]
    original = write_fixture(queue_path, lines)
    assert original.startswith(b"\xef\xbb\xbf")
    rc = qc.run(queue_path, archive_dir, apply=True, min_headroom=20_000)
    assert rc == 0
    new_bytes = queue_path.read_bytes()
    assert new_bytes.startswith(b"\xef\xbb\xbf")
    # The untouched ITEM-OPEN line must appear byte-for-byte (with its original \r\n) in the
    # new file -- find it and check the line and its terminator survived unchanged.
    needle = ITEM_OPEN.encode("utf-8") + b"\r\n"
    assert needle in new_bytes
    # No bare (non-CRLF) newlines were introduced anywhere in queue.md.
    body = new_bytes[3:]  # strip BOM
    assert body.count(b"\n") == body.count(b"\r\n")


def test_dry_run_writes_nothing(queue_path, archive_dir):
    original = write_fixture(queue_path, [ITEM_DONE])
    rc = qc.run(queue_path, archive_dir, apply=False, min_headroom=20_000)
    assert rc == 0
    assert queue_path.read_bytes() == original
    assert not list(archive_dir.glob("queue-archive-*.md"))


# ---------------------------------------------------------------------------
# Archive content verbatim
# ---------------------------------------------------------------------------

def test_archive_contains_verbatim_lf_normalised_text(queue_path, archive_dir):
    write_fixture(queue_path, [ITEM_DONE])
    rc = qc.run(queue_path, archive_dir, apply=True, min_headroom=20_000)
    assert rc == 0
    archives = list(archive_dir.glob("queue-archive-*.md"))
    assert len(archives) == 1
    archived_text = archives[0].read_text(encoding="utf-8")
    assert ITEM_DONE in archived_text
    assert "\r\n" not in archives[0].read_bytes().decode("utf-8")


def test_second_run_appends_tranche_not_overwrite(queue_path, archive_dir):
    write_fixture(queue_path, [ITEM_DONE])
    rc = qc.run(queue_path, archive_dir, apply=True, min_headroom=20_000)
    assert rc == 0
    archive_file = list(archive_dir.glob("queue-archive-*.md"))[0]
    first_text = archive_file.read_text(encoding="utf-8")
    assert "ITEM-DONE" in first_text

    # Add a second, independent done item and re-run against the SAME date's archive file.
    lines = [ITEM_DONE.replace("ITEM-DONE", "ITEM-SECOND")]
    write_fixture(queue_path, lines)
    rc2 = qc.run(queue_path, archive_dir, apply=True, min_headroom=20_000)
    assert rc2 == 0

    second_text = archive_file.read_text(encoding="utf-8")
    assert "ITEM-DONE" in second_text  # first tranche preserved
    assert "ITEM-SECOND" in second_text  # new tranche appended
    assert "## Tranche 2" in second_text
    assert second_text.count("## Tranche 2") == 1


# ---------------------------------------------------------------------------
# Pointer line: inserted once, updated (not duplicated) on subsequent runs
# ---------------------------------------------------------------------------

def test_pointer_line_inserted_once_and_updated_on_rerun(queue_path, archive_dir):
    write_fixture(queue_path, [ITEM_DONE])
    qc.run(queue_path, archive_dir, apply=True, min_headroom=20_000)
    text1 = queue_path.read_bytes().decode("utf-8")
    pointer_lines_1 = [l for l in text1.splitlines() if l.startswith("> ") and "moved verbatim to" in l]
    assert len(pointer_lines_1) == 1

    # Re-run with a fresh candidate -- pointer must be UPDATED, not duplicated.
    lines = [ITEM_DONE.replace("ITEM-DONE", "ITEM-THIRD")]
    write_fixture(queue_path, lines)
    # manually re-insert the pointer as it would look post-first-run, since write_fixture
    # above replaced the whole file; simulate a realistic second pass by re-running the
    # apply against the freshly seeded file's own heading (no pre-existing pointer this
    # time -- covered separately below for the true "already has a pointer" case).
    qc.run(queue_path, archive_dir, apply=True, min_headroom=20_000)
    text2 = queue_path.read_bytes().decode("utf-8")
    pointer_lines_2 = [l for l in text2.splitlines() if l.startswith("> ") and "moved verbatim to" in l]
    assert len(pointer_lines_2) == 1


def test_pointer_line_updated_in_place_when_already_present(queue_path, archive_dir):
    # First pass creates the pointer.
    write_fixture(queue_path, [ITEM_DONE])
    qc.run(queue_path, archive_dir, apply=True, min_headroom=20_000)
    after_first = queue_path.read_bytes()

    # Second pass on the SAME (already-pointered) file, adding one more archivable item
    # directly after the heading block by re-writing with the surviving content plus a new one.
    decoded, had_bom = qc.decode_bytes(after_first)
    lines = decoded.splitlines(keepends=True)
    heading_idx = next(i for i, l in enumerate(lines) if qc._content(l) == "## Active backlog")
    # Insert a brand-new archivable item right after the (already updated) heading block.
    new_item_line = ITEM_DONE.replace("ITEM-DONE", "ITEM-FOURTH") + "\r\n"
    lines.insert(heading_idx + 2, new_item_line)  # heading + pointer already occupy [0],[1]
    queue_path.write_bytes(qc.encode_bytes("".join(lines), had_bom))

    qc.run(queue_path, archive_dir, apply=True, min_headroom=20_000)
    final_text = queue_path.read_bytes().decode("utf-8")
    pointer_lines = [l for l in final_text.splitlines() if l.startswith("> ") and "moved verbatim to" in l]
    assert len(pointer_lines) == 1
    assert "ITEM-FOURTH" not in final_text  # it got archived
    assert "1 `[x]` done item" in pointer_lines[0]  # reflects the LATEST run, not cumulative


# ---------------------------------------------------------------------------
# Restore-on-failure
# ---------------------------------------------------------------------------

def test_restore_on_self_verify_failure(queue_path, archive_dir, monkeypatch):
    original = write_fixture(queue_path, [ITEM_DONE])

    def _boom(*args, **kwargs):
        raise qc.ConsolidationError("forced failure for restore-path test")

    monkeypatch.setattr(qc, "self_verify", _boom)

    with pytest.raises(qc.ConsolidationError):
        qc.run(queue_path, archive_dir, apply=True, min_headroom=20_000)

    assert queue_path.read_bytes() == original
    assert not list(archive_dir.glob("queue-archive-*.md"))


def test_restore_on_failure_preserves_pre_existing_archive(queue_path, archive_dir, monkeypatch):
    # First, a clean successful run creates the archive file.
    write_fixture(queue_path, [ITEM_DONE])
    qc.run(queue_path, archive_dir, apply=True, min_headroom=20_000)
    archive_file = list(archive_dir.glob("queue-archive-*.md"))[0]
    archive_before = archive_file.read_bytes()

    # Second run: seed a new candidate, force a failure, and confirm BOTH files roll back --
    # queue.md to its pre-second-run state and the archive to its pre-second-run content.
    lines = [ITEM_DONE.replace("ITEM-DONE", "ITEM-FIFTH")]
    queue_before_second = write_fixture(queue_path, lines)

    def _boom(*args, **kwargs):
        raise qc.ConsolidationError("forced failure for restore-path test (existing archive)")

    monkeypatch.setattr(qc, "self_verify", _boom)

    with pytest.raises(qc.ConsolidationError):
        qc.run(queue_path, archive_dir, apply=True, min_headroom=20_000)

    assert queue_path.read_bytes() == queue_before_second
    assert archive_file.read_bytes() == archive_before


# ---------------------------------------------------------------------------
# --min-headroom loud warning
# ---------------------------------------------------------------------------

def test_min_headroom_warns_when_still_close_to_cap(queue_path, archive_dir, capsys, monkeypatch):
    # Shrink the cap so the tiny fixture file is deliberately "close" to it.
    write_fixture(queue_path, [ITEM_DONE, ITEM_OPEN])
    size_before = queue_path.stat().st_size
    monkeypatch.setattr(qc, "CAP_BYTES", size_before + 50)
    rc = qc.run(queue_path, archive_dir, apply=True, min_headroom=1000)
    assert rc == 0
    out = capsys.readouterr().out
    assert "LOUD" in out


def test_no_candidates_is_a_clean_noop(queue_path, archive_dir, capsys):
    original = write_fixture(queue_path, [ITEM_OPEN, ITEM_DEFERRED])
    rc = qc.run(queue_path, archive_dir, apply=True, min_headroom=20_000)
    assert rc == 0
    assert queue_path.read_bytes() == original
    assert not list(archive_dir.glob("queue-archive-*.md"))
