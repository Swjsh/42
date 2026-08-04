"""Guard: pml_scan._find_spy_csv anchors to the documented 2025-01-01 analysis
window (filename date), never "biggest file wins" by byte size.

Root cause: sorting every spy_5m_*.csv candidate by stat().st_size silently
picked whichever backfill produced the biggest file. Once the 2024-01-18 OPRA
extension landed (2026-07-31), it out-sized the correct in-window master
(3,670,647 vs 2,525,198 bytes on disk as of this fix) and would have been
silently ingested -- roughly a year of extra SPY bars outside the "full
16-month" window this scan's own docstring documents, corrupting every
day-count / WR% stat with no error and no crash. Fixed by filtering to the
EXPLICIT `spy_5m_2025-01-01_*.csv` prefix and picking the newest by parsed
end-date -- mirrors the pre-existing
tools/expand_opra_cache.py#resolve_spy_master() convention (same bug class,
same fix, ratified during the OPRA-BACKFILL-2026-07-31 work).
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"


def _pml_scan():
    sys.path.insert(0, str(BACKTEST / "autoresearch"))
    sys.path.insert(0, str(BACKTEST))
    sys.path.insert(0, str(REPO))
    return importlib.import_module("pml_scan")


def _touch(path: Path, size_bytes: int) -> None:
    """Create a file of an exact byte size; content doesn't matter for this guard."""
    path.write_bytes(b"x" * size_bytes)


def test_picks_in_window_file_not_biggest_file(tmp_path: Path) -> None:
    """RED-proof: a bigger, OUT-OF-WINDOW file must lose to the smaller
    in-window file. Mirrors the live shape found on disk at fix time, at a
    tiny scale."""
    pml_scan = _pml_scan()
    out_of_window_bigger = tmp_path / "spy_5m_2024-01-18_2026-07-22.csv"
    in_window_smaller = tmp_path / "spy_5m_2025-01-01_2026-07-22.csv"
    _touch(out_of_window_bigger, 10_000)
    _touch(in_window_smaller, 100)

    picked = pml_scan._find_spy_csv(data_dir=tmp_path)
    assert picked == in_window_smaller, (
        f"expected the in-window 2025-01-01 master, got {picked.name}"
    )

    # RED-proof: the OLD "biggest file wins" logic, run on this SAME fixture,
    # must pick the wrong (bigger, out-of-range) file -- proving this isn't a
    # test that would have passed either way.
    old_logic_pick = sorted(
        tmp_path.glob("spy_5m_*.csv"), key=lambda p: p.stat().st_size, reverse=True
    )[0]
    assert old_logic_pick == out_of_window_bigger, (
        "fixture didn't reproduce the footgun shape -- old logic should pick "
        "the bigger, out-of-window file here"
    )


def test_picks_newest_end_date_among_in_window_candidates(tmp_path: Path) -> None:
    """Rolling-append behavior must survive the fix: among multiple in-window
    (2025-01-01-start) candidates, pick the freshest end date, even when an
    OLDER candidate is the bigger file."""
    pml_scan = _pml_scan()
    older_bigger = tmp_path / "spy_5m_2025-01-01_2026-06-16.csv"
    newer_smaller = tmp_path / "spy_5m_2025-01-01_2026-07-22.csv"
    _touch(older_bigger, 50_000)
    _touch(newer_smaller, 100)

    picked = pml_scan._find_spy_csv(data_dir=tmp_path)
    assert picked == newer_smaller


def test_skips_merged_suffix_variant(tmp_path: Path) -> None:
    """A `_merged` suffix variant's tail isn't a plain ISO end-date and must
    be skipped, even though it is by far the biggest file present."""
    pml_scan = _pml_scan()
    merged = tmp_path / "spy_5m_2025-01-01_2026-05-19_merged.csv"
    plain = tmp_path / "spy_5m_2025-01-01_2026-05-15.csv"
    _touch(merged, 999_999)
    _touch(plain, 100)

    picked = pml_scan._find_spy_csv(data_dir=tmp_path)
    assert picked == plain


def test_raises_when_no_in_window_candidate(tmp_path: Path) -> None:
    """No spy_5m_2025-01-01_*.csv present -> fail LOUD (FileNotFoundError),
    never silently fall back to an out-of-window file."""
    pml_scan = _pml_scan()
    (tmp_path / "spy_5m_2024-01-18_2026-07-22.csv").write_bytes(b"x" * 100)
    with pytest.raises(FileNotFoundError):
        pml_scan._find_spy_csv(data_dir=tmp_path)
