"""Guard: grinder.jsonl rotation must actually truncate, and archives must be pruned.

Scar (2026-08-29 audit): run-crypto-daily.ps1 rotated with

    Get-Content $grinderPath -Tail 100 | Set-Content $grinderPath -Encoding utf8

which reads and writes THE SAME FILE in one pipeline. Set-Content cannot open the file
while Get-Content holds it -- reproduced live:

    Set-Content : The process cannot access the file '...' because it is being used by
    another process.

The error was swallowed and the script logged "rotated -> ... (kept last 100 lines)"
regardless (C7: silent success is failure). So grinder.jsonl never shrank and the daily
Copy-Item wrote a fresh ~1.5 GB near-duplicate every single day. Measured at audit time:
67 archives / 58.69 GB, every one byte-verified as an exact PREFIX of the next, with C:
down to 7.5 GB free -- about 4.6 days from a full system volume.

These tests are static (the script is PowerShell, not importable), which is the right
shape here: the failure was a specific TEXTUAL pattern, so the guard bans that pattern.
"""
import re
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "setup" / "scripts" / "run-crypto-daily.ps1"


@pytest.fixture(scope="module")
def body() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_script_exists(body):
    assert body.strip(), "run-crypto-daily.ps1 is missing or empty"


def test_no_self_referential_getcontent_setcontent_pipeline(body):
    """The exact bug: Get-Content <X> ... | Set-Content <same X>."""
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("#"):
            continue
        m = re.search(r"Get-Content\s+(\$\w+).*\|\s*Set-Content\s+(\$\w+)", s)
        assert not (m and m.group(1) == m.group(2)), (
            f"self-referential Get-Content|Set-Content pipeline on {m.group(1)}: {s!r} -- "
            "stage to a temp file and Move-Item over the original instead"
        )


def test_rotation_stages_through_temp_then_moves(body):
    assert ".rotate.tmp" in body, "rotation must stage to a temp file"
    assert re.search(r"Move-Item\s+\$tmp\s+\$grinderPath\s+-Force", body), \
        "rotation must atomically Move-Item the temp file over grinder.jsonl"


def test_rotation_verifies_it_actually_shrank(body):
    """Never log success without checking the file got smaller."""
    assert "ROTATION FAILED" in body, \
        "rotation must detect and log a no-op truncate instead of claiming success"
    assert re.search(r"\$newSize\s+-ge\s+\$size", body), \
        "rotation must compare post-truncate size against pre-truncate size"


def test_dated_archives_are_pruned(body):
    """ledger_archive.py prunes date-named DIRECTORIES; these are date-named FILES, so
    they were never covered by any retention policy."""
    assert re.search(r'Filter\s+"grinder-archive-\*\.jsonl"', body), \
        "must enumerate dated grinder archives for pruning"
    assert "AddDays(-14)" in body, "must prune archives past a bounded retention window"
    assert re.search(r"Remove-Item\s+\$_\.FullName", body), "must actually delete stale archives"
