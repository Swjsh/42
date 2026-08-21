"""Guard: blocker names must be DIRECTION-AWARE — bear and bull reuse indices.

THE DEFECT THIS PINS (shipped and caught the same day, 2026-08-20)
  `evaluate_bearish_setup` and `evaluate_bullish_setup` in backtest/lib/filters.py
  both append integer blocker indices, and THE SAME INDEX MEANS DIFFERENT THINGS:

      index 9   bull = "VIX < 22 hard cap"    bear = breakdown-bar volume confirmation
      index 10  bull = buyer pressure          bear = not enough triggers
      index 11  bull = triggers / level-tied   bear = liquidity sweep at the level

  The first BLOCKER_NAMES map was transcribed from the BULL function and applied
  to every tick regardless of side. That mislabelled every bear tick on the
  cockpit, and put a wrong claim into that day's EOD audit ("filter 9 · VIX >= 22
  blocked 61% of the day" — it was actually the volume/breakdown check).

  Filter 6 was inverted in both directions too: it requires ribbon spread >= 30c,
  so it blocks when the ribbon is too NARROW, not when something is "too wide".
  And it reads the SATY RIBBON spread, not an option bid-ask spread — misreading
  that produced a bogus "112c median spread" finding before it was traced.

WHY A TEST AND NOT JUST A FIX
  This class of error is invisible: the page renders a confident, plausible,
  wrong sentence. Nothing crashes. The only defence is asserting the names
  against the actual source of truth — filters.py itself.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import gamma_cockpit_data as cd                 # noqa: E402

FILTERS = (REPO / "backtest" / "lib" / "filters.py").read_text(encoding="utf-8")


def _fn_body(name: str) -> str:
    i = FILTERS.index("def %s(" % name)
    return FILTERS[i:i + 40000]


def _indices_in(name: str) -> set:
    return {int(m.group(1)) for m in re.finditer(r"blockers\.append\((\d+)\)", _fn_body(name))}


def test_the_two_functions_really_do_reuse_indices():
    """If this ever stops being true, the whole direction-aware apparatus is moot."""
    bear, bull = _indices_in("evaluate_bearish_setup"), _indices_in("evaluate_bullish_setup")
    assert bear & bull, "expected overlapping blocker indices between bear and bull"


def test_separate_tables_exist_and_differ():
    assert cd.BEAR_BLOCKER_NAMES is not cd.BULL_BLOCKER_NAMES
    differing = [k for k in set(cd.BEAR_BLOCKER_NAMES) & set(cd.BULL_BLOCKER_NAMES)
                 if cd.BEAR_BLOCKER_NAMES[k] != cd.BULL_BLOCKER_NAMES[k]]
    assert differing, "bear and bull tables are identical — the bug is back"
    assert {9, 10} <= set(differing), differing


def test_every_named_index_actually_exists_in_its_function():
    """A name for an index the function never emits is fiction."""
    bear, bull = _indices_in("evaluate_bearish_setup"), _indices_in("evaluate_bullish_setup")
    assert set(cd.BEAR_BLOCKER_NAMES) <= bear, set(cd.BEAR_BLOCKER_NAMES) - bear
    assert set(cd.BULL_BLOCKER_NAMES) <= bull, set(cd.BULL_BLOCKER_NAMES) - bull


def test_bear_nine_is_the_volume_check_not_a_vix_cap():
    n = cd.blocker_name(9, "bear").lower()
    assert "breakdown" in n or "volume" in n, n
    assert "vix" not in n, "bear filter 9 is NOT a VIX gate: %r" % n


def test_bull_nine_is_the_vix_hard_cap():
    assert "vix" in cd.blocker_name(9, "bull").lower()


def test_bear_ten_is_trigger_count_not_pressure():
    assert "trigger" in cd.blocker_name(10, "bear").lower()
    assert "pressure" in cd.blocker_name(10, "bull").lower()


def test_filter_six_reads_as_TOO_NARROW_in_both_directions():
    """It requires spread >= 30c, so it blocks on compression, not on width."""
    for side in ("bear", "bull"):
        n = cd.blocker_name(6, side).lower()
        assert "narrow" in n, "%s filter 6 still reads as 'too wide': %r" % (side, n)
    # and the source really is a >= comparison against a minimum
    assert "spread_cents < RIBBON_SPREAD_MIN_CENTS" in _fn_body("evaluate_bearish_setup")


def test_bear_eight_states_the_real_condition():
    """VIX > 17.30 AND RISING. The bull phrasing ('not low, not falling') was wrong
    for bear and hid why a 15.5-16.1 VIX day could never open the normal path."""
    n = cd.blocker_name(8, "bear")
    assert "17.3" in n and "rising" in n.lower(), n


def test_unknown_index_degrades_to_itself():
    assert cd.blocker_name(99, "bear") == "99"
    assert cd.blocker_name(None, "bull") == "None"


def test_ticks_carry_the_side_they_were_named_with():
    er = cd.engine_room()
    spy = [e for e in er["engines"] if e["id"] == "spy-core"][0]
    for t in spy["ticks"]:
        assert t.get("blocker_side") in ("bear", "bull"), t
        for b in t.get("blockers", []):
            assert not b.isdigit(), "bare index leaked: %r" % b
