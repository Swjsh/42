"""Guard for setup/scripts/loop_retention.py — the driver-loop JSONL retention cap.

Pins the contract gamma-drive depends on: newest-N kept in place, older tail rolled
VERBATIM to a monthly archive (nothing lost), idempotent under cap, fail-open.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

# Load the script by path (it lives under setup/scripts, not an importable package).
_MOD_PATH = Path(__file__).resolve().parents[2] / "setup" / "scripts" / "loop_retention.py"
_spec = importlib.util.spec_from_file_location("loop_retention", _MOD_PATH)
assert _spec and _spec.loader
loop_retention = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(loop_retention)

Target = loop_retention.Target


def _rows(n: int) -> list[str]:
    return [f'{{"task_id":"t{i}","items_drained":1}}\n' for i in range(n)]


def test_under_cap_is_noop(tmp_path: Path) -> None:
    f = tmp_path / "outcomes.jsonl"
    original = _rows(10)
    f.write_text("".join(original), encoding="utf-8")
    archived = loop_retention.cap_file(Target(f, max_rows=500))
    assert archived == 0
    assert f.read_text(encoding="utf-8") == "".join(original)
    # No archive created when under cap.
    assert not list(tmp_path.glob("outcomes-archive-*.jsonl"))


def test_over_cap_keeps_newest_and_archives_rest_verbatim(tmp_path: Path) -> None:
    f = tmp_path / "outcomes.jsonl"
    original = _rows(120)
    f.write_text("".join(original), encoding="utf-8")

    archived = loop_retention.cap_file(Target(f, max_rows=50))
    assert archived == 70

    kept = f.read_text(encoding="utf-8")
    archive_files = list(tmp_path.glob("outcomes-archive-*.jsonl"))
    assert len(archive_files) == 1
    rolled = archive_files[0].read_text(encoding="utf-8")

    # Newest 50 kept in place; oldest 70 rolled.
    assert kept == "".join(original[-50:])
    assert rolled == "".join(original[:70])
    # Nothing lost: kept ∪ archived == original, in order.
    assert rolled + kept == "".join(original)


def test_idempotent_second_run_noop(tmp_path: Path) -> None:
    f = tmp_path / "outcomes.jsonl"
    f.write_text("".join(_rows(120)), encoding="utf-8")
    loop_retention.cap_file(Target(f, max_rows=50))
    first = f.read_text(encoding="utf-8")
    again = loop_retention.cap_file(Target(f, max_rows=50))
    assert again == 0
    assert f.read_text(encoding="utf-8") == first


def test_fail_open_on_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "nope.jsonl"
    assert loop_retention.cap_file(Target(missing, max_rows=50)) == 0


def test_check_mode_detects_over_cap(tmp_path: Path) -> None:
    f = tmp_path / "outcomes.jsonl"
    f.write_text("".join(_rows(120)), encoding="utf-8")
    assert loop_retention.is_over_cap(Target(f, max_rows=50)) is True
    assert loop_retention.is_over_cap(Target(f, max_rows=500)) is False


def test_blank_lines_do_not_trip_cap(tmp_path: Path) -> None:
    f = tmp_path / "outcomes.jsonl"
    rows = _rows(40) + ["\n", "\n"]  # 40 real rows + trailing blanks
    f.write_text("".join(rows), encoding="utf-8")
    # 40 non-empty <= 50 cap -> noop even though 42 physical lines.
    assert loop_retention.cap_file(Target(f, max_rows=50)) == 0
