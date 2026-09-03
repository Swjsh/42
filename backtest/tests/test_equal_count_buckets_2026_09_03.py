"""Guard tests for backtest/lib/canonical_battery.py::equal_count_buckets
(GATE-DESIGN-FIXED-CALENDAR-WINDOWS-STARVE-LOW-FIRE-RATE-KNOBS fold, 2026-09-03).

Pure unit tests on synthetic fixtures -- no live core-decisions.jsonl / OPRA cache
dependency, so these stay green regardless of what today's ledger looks like.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))

from lib import canonical_battery as cb  # noqa: E402


def test_evenly_divisible_gives_equal_sizes():
    boundaries = cb.equal_count_buckets(list(range(8)), n_buckets=4)
    assert boundaries == [(0, 2), (2, 4), (4, 6), (6, 8)]


def test_remainder_distributed_to_last_buckets():
    # n=35 matches the worked example's total changed-trade count (R_tp100_f50:
    # 4 + 13 + 4 + 14 = 35 across the 4 calendar sub-windows).
    boundaries = cb.equal_count_buckets(list(range(35)), n_buckets=4)
    sizes = [end - start for start, end in boundaries]
    assert sizes == [8, 9, 9, 9]
    assert sum(sizes) == 35


def test_all_buckets_clear_g4_floor_where_calendar_windows_could_not():
    """The worked example (analysis/recommendations/tp1-r50-readjudication-2026-08-23.json):
    R_tp100_f50 has n_changed=35 total, but under FIXED CALENDAR windows two of four
    (2025H1, 2026Q1) sit at n_changed=4 -- below G4's >=5-changed floor -- PERMANENTLY,
    capping qualifying windows at 2 of 4 regardless of forward extension. Equal-count
    bucketing over the same total clears the floor in all four buckets."""
    boundaries = cb.equal_count_buckets(list(range(35)), n_buckets=4)
    sizes = [end - start for start, end in boundaries]
    assert all(size >= 5 for size in sizes)


def test_boundaries_cover_full_range_no_gap_no_overlap():
    deltas = list(range(17))
    boundaries = cb.equal_count_buckets(deltas, n_buckets=4)
    assert boundaries[0][0] == 0
    assert boundaries[-1][1] == len(deltas)
    for (_s0, e0), (s1, _e1) in zip(boundaries, boundaries[1:]):
        assert e0 == s1


def test_single_bucket_is_the_whole_range():
    boundaries = cb.equal_count_buckets(list(range(10)), n_buckets=1)
    assert boundaries == [(0, 10)]


def test_empty_input_gives_empty_buckets():
    boundaries = cb.equal_count_buckets([], n_buckets=4)
    assert boundaries == [(0, 0), (0, 0), (0, 0), (0, 0)]


def test_invalid_n_buckets_raises():
    with pytest.raises(ValueError):
        cb.equal_count_buckets([1.0, 2.0, 3.0], n_buckets=0)
