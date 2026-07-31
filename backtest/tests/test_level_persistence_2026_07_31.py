"""Guard tests for the level-persistence matching logic (LEVEL-PERSISTENCE-2026-07-31).

Guards the cohort-classification contract frozen in the prereg of
backtest/tools/level_persistence_2026_07_31.py:

  - zone_match is inclusive at the tolerance boundary and symmetric.
  - count_zone_touches counts RTH 5m bars whose [low, high] INTERSECTS the zone
    (not just bars whose close is inside), and ignores non-RTH bars.
  - classify_level: no prior sets -> UNKNOWN; no match -> FRESH; match with < 2
    touches -> PERSISTENT; match with >= 2 touches -> TOUCH_VALIDATED; touches are
    only counted on MATCHED prior days.
  - strip_round_numbers drops exact-integer psychological levels only.

RED-proof: each assertion fails under the plausible regression it targets
(exclusive boundary, close-inside-zone touch test, touches counted on unmatched
days, round-strip dropping non-integers). Verified RED by sabotage-run at build
time (see analysis/deep-research/LEVEL-PERSISTENCE-2026-07-31.md).
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO.parent
for _p in (str(ROOT), str(REPO), str(REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from level_persistence_2026_07_31 import (  # noqa: E402
    classify_level,
    count_zone_touches,
    match_against_set,
    strip_round_numbers,
    zone_match,
)


def _bars(rows):
    """rows: list of (time_str, low, high)."""
    return pd.DataFrame({
        "time": [dt.time.fromisoformat(t) for t, _, _ in rows],
        "low": [lo for _, lo, _ in rows],
        "high": [hi for _, _, hi in rows],
    })


# ---------------- zone_match ----------------

def test_zone_match_inclusive_boundary_and_symmetric():
    assert zone_match(740.00, 740.40, 0.40)          # exactly at tol -> MATCH (inclusive)
    assert zone_match(740.40, 740.00, 0.40)          # symmetric
    assert not zone_match(740.00, 740.41, 0.40)      # just beyond -> no match
    assert zone_match(740.00, 740.00, 0.0)           # zero tol, identical -> match


def test_match_against_set():
    s = [700.0, 740.15, 755.9]
    assert match_against_set(740.00, s, 0.40)        # matches 740.15
    assert not match_against_set(748.00, s, 0.40)
    assert not match_against_set(740.00, [], 0.40)


# ---------------- count_zone_touches ----------------

def test_touches_range_intersection_not_close():
    # Zone 739.60..740.40 (price 740.00, tol 0.40).
    bars = _bars([
        ("09:30:00", 740.10, 740.90),   # low inside zone -> touch
        ("09:35:00", 738.00, 739.70),   # high pokes into zone -> touch
        ("09:40:00", 738.00, 739.20),   # entirely below -> no touch
        ("09:45:00", 739.00, 741.00),   # spans the whole zone -> touch
        ("08:55:00", 739.90, 740.10),   # PREMARKET (non-RTH) -> ignored
        ("15:55:00", 740.00, 740.05),   # RTH last bar, inside -> touch
    ])
    assert count_zone_touches(bars, 740.00, 0.40) == 4


def test_touches_empty_and_no_rth():
    assert count_zone_touches(_bars([]), 740.0, 0.40) == 0
    only_pm = _bars([("07:00:00", 739.9, 740.1)])
    assert count_zone_touches(only_pm, 740.0, 0.40) == 0


# ---------------- classify_level ----------------

def test_classify_unknown_when_no_prior_days():
    assert classify_level(740.0, [], [], 0.40) == ("UNKNOWN", 0, 0)


def test_classify_fresh_when_no_prior_match():
    sets_ = [[730.0, 735.0], [750.0]]
    bars_ = [_bars([("10:00:00", 739.8, 740.2)]),   # tape touched it, but level NOT in set
             _bars([])]
    # Touches on unmatched days must NOT rescue a FRESH level.
    assert classify_level(740.0, sets_, bars_, 0.40) == ("FRESH", 0, 0)


def test_classify_persistent_single_touch():
    sets_ = [[740.15]]
    bars_ = [_bars([("10:00:00", 739.9, 740.1),      # 1 touch
                    ("10:05:00", 738.0, 739.0)])]    # no touch
    assert classify_level(740.0, sets_, bars_, 0.40) == ("PERSISTENT", 1, 1)


def test_classify_touch_validated_two_touches():
    sets_ = [[740.15], [739.9]]
    bars_ = [_bars([("10:00:00", 739.9, 740.1)]),
             _bars([("11:00:00", 739.5, 740.7)])]
    cohort, nmatch, touches = classify_level(740.0, sets_, bars_, 0.40)
    assert cohort == "TOUCH_VALIDATED"
    assert nmatch == 2
    assert touches == 2


def test_classify_touches_only_on_matched_days():
    # Day 0 matches (0 touches on its tape); day 1 does NOT match but its tape
    # touches the zone twice -- those must not count.
    sets_ = [[740.15], [700.0]]
    bars_ = [_bars([("10:00:00", 741.0, 742.0)]),                        # matched, no touch
             _bars([("10:00:00", 739.9, 740.1), ("10:05:00", 739.8, 740.2)])]  # unmatched
    assert classify_level(740.0, sets_, bars_, 0.40) == ("PERSISTENT", 1, 0)


# ---------------- strip_round_numbers ----------------

def test_strip_round_numbers():
    assert strip_round_numbers([740.0, 740.15, 741.0, 739.99]) == [740.15, 739.99]
    assert strip_round_numbers([]) == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
