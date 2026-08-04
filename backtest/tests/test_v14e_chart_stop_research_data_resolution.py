"""Guard: v14e_chart_stop_research._find_spy_csv anchors to the documented
2025-01-01 analysis window (filename date), never "biggest file wins" by byte
size ("prefer the largest file (most historical coverage)" was the literal
old comment).

Root cause: same bug class as pml_scan.py -- sorting every spy_5m_*.csv
candidate by stat().st_size silently picked whichever backfill produced the
biggest file. Once the 2024-01-18 OPRA extension landed (2026-07-31), it
out-sized the correct in-window master (3,670,647 vs 2,525,198 bytes on disk
as of this fix) and would have been silently ingested into every
ribbon-warmup / simulate_trade_real replay this script runs. Fixed by
filtering to the EXPLICIT `spy_5m_2025-01-01_*.csv` prefix and picking the
newest by parsed end-date -- mirrors
tools/expand_opra_cache.py#resolve_spy_master() and pml_scan.py's identical
fix.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"


def _v14e():
    sys.path.insert(0, str(BACKTEST / "autoresearch"))
    sys.path.insert(0, str(BACKTEST))
    sys.path.insert(0, str(REPO))
    return importlib.import_module("v14e_chart_stop_research")


def _touch(path: Path, size_bytes: int) -> None:
    """Create a file of an exact byte size; content doesn't matter for this guard."""
    path.write_bytes(b"x" * size_bytes)


def test_picks_in_window_file_not_biggest_file(tmp_path: Path) -> None:
    """RED-proof: a bigger, OUT-OF-WINDOW file must lose to the smaller
    in-window file. Mirrors the live shape found on disk at fix time, at a
    tiny scale."""
    v14e = _v14e()
    out_of_window_bigger = tmp_path / "spy_5m_2024-01-18_2026-07-22.csv"
    in_window_smaller = tmp_path / "spy_5m_2025-01-01_2026-07-22.csv"
    _touch(out_of_window_bigger, 10_000)
    _touch(in_window_smaller, 100)

    picked = v14e._find_spy_csv(data_dir=tmp_path)
    assert picked == in_window_smaller, (
        f"expected the in-window 2025-01-01 master, got "
        f"{picked.name if picked else None}"
    )

    # RED-proof: the OLD "prefer the largest file" logic, run on this SAME
    # fixture, must pick the wrong (bigger, out-of-range) file.
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
    v14e = _v14e()
    older_bigger = tmp_path / "spy_5m_2025-01-01_2026-06-16.csv"
    newer_smaller = tmp_path / "spy_5m_2025-01-01_2026-07-22.csv"
    _touch(older_bigger, 50_000)
    _touch(newer_smaller, 100)

    picked = v14e._find_spy_csv(data_dir=tmp_path)
    assert picked == newer_smaller


def test_skips_merged_suffix_variant(tmp_path: Path) -> None:
    """A `_merged` suffix variant's tail isn't a plain ISO end-date and must
    be skipped, even though it is by far the biggest file present."""
    v14e = _v14e()
    merged = tmp_path / "spy_5m_2025-01-01_2026-05-19_merged.csv"
    plain = tmp_path / "spy_5m_2025-01-01_2026-05-15.csv"
    _touch(merged, 999_999)
    _touch(plain, 100)

    picked = v14e._find_spy_csv(data_dir=tmp_path)
    assert picked == plain


def test_returns_none_when_no_in_window_candidate(tmp_path: Path) -> None:
    """No spy_5m_2025-01-01_*.csv present -> None (caller logs + exits 1),
    never a silent fallback to an out-of-window file."""
    v14e = _v14e()
    (tmp_path / "spy_5m_2024-01-18_2026-07-22.csv").write_bytes(b"x" * 100)
    assert v14e._find_spy_csv(data_dir=tmp_path) is None
