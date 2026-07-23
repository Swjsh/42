"""Guard for backtest/tools/engulfing_at_structure_detector.py -- the causal
ENGULFING-AT-STRUCTURE-TRIGGER detector (queue.md, built 2026-07-23 after the prior
swing-shelf attempt was proven not to fire on either live exhibit).

Two anchor fixtures below are REAL cached bars (backtest/data/spy_5m_2026-05-19_
2026-07-23.csv), transcribed verbatim -- not synthetic -- so a fixture drift from the
real tape is caught the moment someone "fixes" a rounding difference without checking
the source. Both anchors are RED-proofed (see test docstrings for the exact mutation
that was applied and reverted while authoring this file).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest" / "tools"))

import engulfing_at_structure_detector as det  # noqa: E402


def _arrays(bars: list[tuple[float, float, float, float]]):
    """bars: list of (open, high, low, close) tuples, oldest first -> 4 numpy arrays."""
    a = np.array(bars, dtype=float)
    return a[:, 0], a[:, 1], a[:, 2], a[:, 3]  # opens, highs, lows, closes


# =====================================================================================
# Real-tape fixtures (verbatim from the cached CSV -- see module docstring)
# =====================================================================================

# 2026-07-23, 09:55..10:45 ET, 5m bars. Index 9 = 10:40 (J's bearish exhibit).
BEARISH_EXHIBIT_BARS = [
    (740.950, 741.280, 739.30, 739.575),  # 09:55
    (739.580, 740.630, 739.58, 740.345),  # 10:00
    (740.360, 740.930, 738.87, 739.360),  # 10:05
    (739.345, 740.540, 739.21, 739.660),  # 10:10
    (739.650, 740.360, 739.41, 739.510),  # 10:15
    (739.520, 740.435, 739.17, 739.440),  # 10:20
    (739.400, 739.910, 738.99, 739.800),  # 10:25
    (739.740, 740.040, 738.66, 738.970),  # 10:30
    (738.980, 740.510, 738.59, 740.380),  # 10:35  <- shelf touch (high)
    (740.380, 740.640, 738.67, 738.870),  # 10:40  <- bearish engulfing / reaction
    (738.860, 739.470, 738.67, 738.830),  # 10:45
]
BEARISH_T = 9

# 2026-07-21, 10:30..11:10 ET, 5m bars. Index 7 = 11:05 (J's bullish exhibit).
BULLISH_EXHIBIT_BARS = [
    (746.8500, 747.2500, 746.58, 746.8000),  # 10:30
    (746.7950, 747.0200, 746.09, 746.3000),  # 10:35
    (746.3000, 746.6350, 745.77, 746.6000),  # 10:40  <- farther shelf touch (nbar=3+ path)
    (746.6100, 747.2600, 746.45, 746.9100),  # 10:45
    (746.9100, 746.9600, 746.50, 746.6900),  # 10:50
    (746.6800, 746.7900, 746.26, 746.7400),  # 10:55
    (746.7700, 746.8900, 745.83, 746.0010),  # 11:00  <- nearest shelf touch (nbar=1 path)
    (746.0000, 747.0700, 745.85, 746.9800),  # 11:05  <- bullish engulfing / reaction
    (746.9800, 747.5200, 746.94, 747.2098),  # 11:10
]
BULLISH_T = 7


# =====================================================================================
# Both anchors fire on the frozen grid's "both_anchors_fire" cells (prereg's own
# result_table: band>=0.15 + nbar=1 for bearish; every cell reaches bullish at nbar=1,
# and band>=0.15 also reaches it at nbar>=2 via the farther touch).
# =====================================================================================

def test_bearish_anchor_fires_at_shipped_cell():
    opens, highs, lows, closes = _arrays(BEARISH_EXHIBIT_BARS)
    cell = det.Cell(zone_band=0.15, body_floor=0.50, min_bars_apart=1)
    hit = det.detect_bar(opens, highs, lows, closes, BEARISH_T, cell)
    assert hit is not None
    assert hit["bias"] == "bearish"
    assert hit["shelf_bar_offset"] == 1  # 10:35, exactly 1 bar before 10:40
    assert hit["touch_spread"] == pytest.approx(0.13, abs=0.005)


def test_bearish_anchor_MISSES_at_tight_band_disclosed_in_prereg():
    """The prereg's own falsification table discloses this: band=0.08 is 1-2 cents
    short of the real $0.13 spread. This is the EXACT reason the grid's zone_band axis
    must include 0.15, not a bug -- pinned here so a future "helpful" widening of 0.08
    doesn't silently change what this test proves."""
    opens, highs, lows, closes = _arrays(BEARISH_EXHIBIT_BARS)
    cell = det.Cell(zone_band=0.08, body_floor=0.50, min_bars_apart=1)
    hit = det.detect_bar(opens, highs, lows, closes, BEARISH_T, cell)
    assert hit is None


def test_bearish_anchor_MISSES_when_min_bars_apart_excludes_the_only_touch():
    """10:35 is the ONLY qualifying shelf touch within lookback for this exhibit --
    min_bars_apart=2 structurally excludes it (not a band issue)."""
    opens, highs, lows, closes = _arrays(BEARISH_EXHIBIT_BARS)
    cell = det.Cell(zone_band=0.25, body_floor=0.50, min_bars_apart=2)
    hit = det.detect_bar(opens, highs, lows, closes, BEARISH_T, cell)
    assert hit is None


def test_bullish_anchor_fires_via_nearest_touch_at_nbar1():
    opens, highs, lows, closes = _arrays(BULLISH_EXHIBIT_BARS)
    cell = det.Cell(zone_band=0.08, body_floor=0.50, min_bars_apart=1)
    hit = det.detect_bar(opens, highs, lows, closes, BULLISH_T, cell)
    assert hit is not None
    assert hit["bias"] == "bullish"
    assert hit["shelf_bar_offset"] == 1  # 11:00, immediately preceding
    assert hit["touch_spread"] == pytest.approx(0.02, abs=0.005)


def test_bullish_anchor_fires_via_farther_touch_at_nbar3():
    """Same bar, DIFFERENT (farther) qualifying touch once nbar=3 excludes 11:00 --
    proves the shelf search is genuinely re-scoped by min_bars_apart, not returning a
    cached/hardcoded touch. 10:40 sits 5 bars before 11:05 (11:00/10:55/10:50/10:45/10:40
    -- nbar=3 only excludes the nearer 11:00 touch, it does not force the offset to
    equal 3 itself; the nearest bar that BOTH clears min_bars_apart>=3 AND independently
    passes is_rolling_extreme happens to be 10:40, 5 bars back -- 10:50/10:45 fail the
    local-extreme check, see BULLISH_EXHIBIT_BARS)."""
    opens, highs, lows, closes = _arrays(BULLISH_EXHIBIT_BARS)
    cell = det.Cell(zone_band=0.15, body_floor=0.50, min_bars_apart=3)
    hit = det.detect_bar(opens, highs, lows, closes, BULLISH_T, cell)
    assert hit is not None
    assert hit["bias"] == "bullish"
    assert hit["shelf_bar_offset"] == 5  # 10:40
    assert hit["touch_spread"] == pytest.approx(0.08, abs=0.005)


def test_both_anchors_fire_together_on_the_declared_shipped_cell():
    """The exact cell the prereg names as clearing BOTH anchors: band=0.15, nbar=1
    (body_floor doesn't matter here -- both exhibits clear 0.65 comfortably)."""
    cell = det.Cell(zone_band=0.15, body_floor=0.65, min_bars_apart=1)
    bo, bh, bl, bc = _arrays(BEARISH_EXHIBIT_BARS)
    uo, uh, ul, uc = _arrays(BULLISH_EXHIBIT_BARS)
    bear_hit = det.detect_bar(bo, bh, bl, bc, BEARISH_T, cell)
    bull_hit = det.detect_bar(uo, uh, ul, uc, BULLISH_T, cell)
    assert bear_hit is not None and bear_hit["bias"] == "bearish"
    assert bull_hit is not None and bull_hit["bias"] == "bullish"


# =====================================================================================
# Why the prior (swing-pivot) attempt failed, and why this one doesn't: the reaction
# bar itself must NOT be required to independently be a rolling extreme.
# =====================================================================================

def test_reaction_bar_need_not_itself_be_the_freshest_extreme():
    """11:05's own low (745.85) sits 2c ABOVE 11:00's low (745.83) -- 11:05 is NOT the
    freshest local low. A detector that required the reaction bar to independently pass
    is_rolling_extreme would reject this exhibit entirely; find_shelf_touch does not
    impose that requirement on bar t (only on the candidate shelf bar i)."""
    _, _, lows, _ = _arrays(BULLISH_EXHIBIT_BARS)
    assert not det.is_rolling_extreme(lows, BULLISH_T, kind="low", side_window=2), (
        "fixture invariant broken: 11:05 must NOT be a fresh rolling low for this test "
        "to actually exercise the code path it claims to")
    shelf = det.find_shelf_touch(lows, lows, BULLISH_T, kind="low", zone_band=0.08,
                                  min_bars_apart=1)
    assert shelf is not None


# =====================================================================================
# C6 causality -- mutating bars strictly AFTER t must never change the result at t.
# =====================================================================================

def test_causal_c6_find_shelf_touch_ignores_future_bars():
    lows = np.array([100.0, 99.9, 99.95, 99.80, 99.82], dtype=float)
    highs = lows + 1.0
    t = 4
    cell_result = det.find_shelf_touch(lows, highs, t, kind="low", zone_band=0.10,
                                        min_bars_apart=1)
    mutated_lows = lows.copy()
    mutated_lows[t + 1:] = 1.0  # no bars exist after t here, so extend the array instead
    lows_extended = np.append(lows, [0.01, 500.0, -999.0])
    highs_extended = np.append(highs, [0.01, 500.0, -999.0])
    mutated_result = det.find_shelf_touch(lows_extended, highs_extended, t, kind="low",
                                           zone_band=0.10, min_bars_apart=1)
    assert cell_result == mutated_result


def test_causal_c6_detect_bar_ignores_future_bars():
    opens, highs, lows, closes = _arrays(BULLISH_EXHIBIT_BARS)
    cell = det.Cell(zone_band=0.15, body_floor=0.50, min_bars_apart=1)
    before = det.detect_bar(opens, highs, lows, closes, BULLISH_T, cell)

    future_bars = BULLISH_EXHIBIT_BARS + [
        (500.0, 999.0, 0.01, 0.02),   # wild future bar
        (0.02, 0.03, 0.01, 0.02),
    ]
    fo, fh, fl, fc = _arrays(future_bars)
    after = det.detect_bar(fo, fh, fl, fc, BULLISH_T, cell)
    assert before == after


def test_causal_c6_is_rolling_extreme_ignores_future_bars():
    values = np.array([5.0, 4.0, 4.5, 4.2, 100.0, -50.0], dtype=float)
    i = 2
    before = det.is_rolling_extreme(values, i, kind="low", side_window=2)
    truncated = values[:i + 1]
    after = det.is_rolling_extreme(truncated, i, kind="low", side_window=2)
    assert before == after


# =====================================================================================
# Zone band is a BAND, not a penny-exact match -- and IS bounded (not infinitely wide).
# =====================================================================================

def test_zone_band_admits_a_near_but_not_identical_touch():
    lows = np.array([100.00, 100.50, 100.60, 100.04], dtype=float)  # touch=100.00 vs t=100.04
    highs = lows + 1.0
    shelf = det.find_shelf_touch(lows, highs, 3, kind="low", zone_band=0.05, min_bars_apart=1)
    assert shelf is not None
    assert shelf["touch_spread"] == pytest.approx(0.04, abs=1e-9)


def test_zone_band_rejects_a_touch_outside_the_band():
    lows = np.array([100.00, 100.50, 100.60, 100.20], dtype=float)  # touch=100.00 vs t=100.20
    highs = lows + 1.0
    shelf = det.find_shelf_touch(lows, highs, 3, kind="low", zone_band=0.05, min_bars_apart=1)
    assert shelf is None


# =====================================================================================
# body_floor gate
# =====================================================================================

def test_body_floor_rejects_an_indecisive_engulfing_candle():
    # bar0 (prev): RED, small body 99.95..100.10 (open=100.10, close=99.95).
    # bar1 (t): GREEN, body 99.90..100.15 fully engulfs bar0's body (valid bullish
    # engulfing geometry) but sits inside a WIDE range (99.00..101.00, via wicks) so
    # body_pct = 0.25 / 2.00 = 0.125 -- well under a 0.50 floor. Confirmed this fixture
    # actually exercises the engulfing-geometry path (not just failing on direction)
    # via a deliberate mutation-and-revert of the body_floor gate itself while authoring
    # this test: disabling the gate (`if False: return None`) made this test go GREEN
    # incorrectly with an earlier, geometry-invalid fixture -- that fixture was replaced
    # with this one, which correctly goes RED when the gate is disabled.
    opens = np.array([100.10, 99.90])
    closes = np.array([99.95, 100.15])
    highs = np.array([100.20, 101.00])
    lows = np.array([99.90, 99.00])
    assert det.is_engulfing(opens, closes, 1, direction="bullish"), (
        "fixture invariant broken: bar1 must genuinely engulf bar0 for this test to "
        "exercise the body_floor gate rather than the engulfing-geometry gate")
    cell = det.Cell(zone_band=100.0, body_floor=0.50, min_bars_apart=1)
    hit = det.detect_bar(opens, highs, lows, closes, 1, cell)
    assert hit is None, "wide-range/small-body candle must not pass the body_floor gate"


def test_body_floor_accepts_a_decisive_candle_at_a_low_floor():
    opens, highs, lows, closes = _arrays(BEARISH_EXHIBIT_BARS)
    cell = det.Cell(zone_band=0.15, body_floor=0.10, min_bars_apart=1)
    hit = det.detect_bar(opens, highs, lows, closes, BEARISH_T, cell)
    assert hit is not None


# =====================================================================================
# Engulfing geometry + direction matching
# =====================================================================================

def test_is_engulfing_requires_body_containment():
    opens = np.array([100.0, 100.5])
    closes = np.array([99.0, 101.0])  # bar0 red 99..100, bar1 green 100.5..101 -- does NOT engulf
    assert not det.is_engulfing(opens, closes, 1, direction="bullish")


def test_is_engulfing_bullish_true_case():
    opens = np.array([100.0, 99.0])
    closes = np.array([99.0, 100.5])  # bar0 red (100->99), bar1 green engulfing (99->100.5)
    assert det.is_engulfing(opens, closes, 1, direction="bullish")
    assert not det.is_engulfing(opens, closes, 1, direction="bearish")


def test_bearish_engulfing_never_matches_a_low_shelf():
    """A bearish-direction engulfing bar only ever searches a HIGH shelf; confirms
    detect_bar doesn't accidentally cross-wire kind="low" into a bearish result."""
    opens, highs, lows, closes = _arrays(BEARISH_EXHIBIT_BARS)
    cell = det.Cell(zone_band=0.15, body_floor=0.50, min_bars_apart=1)
    hit = det.detect_bar(opens, highs, lows, closes, BEARISH_T, cell)
    assert hit is not None and hit["bias"] == "bearish"
    # the shelf_price recorded must come from the HIGHS array, not lows
    assert hit["shelf_price"] == pytest.approx(highs[BEARISH_T - 1], abs=1e-6)


# =====================================================================================
# Grid construction -- catches silent drift from the frozen pre-reg's own axes/n_cells.
# =====================================================================================

def test_build_grid_matches_frozen_prereg_shape():
    axes = {
        "zone_band_dollars": (0.08, 0.15, 0.25),
        "body_floor_pct": (0.50, 0.65),
        "min_bars_apart": (1, 3),
    }
    grid = det.build_grid(axes)
    assert len(grid) == 12
    ids = {c.cell_id() for c in grid}
    assert len(ids) == 12, "cell_id must be unique per cell (no silent collisions)"
    assert "band0.15|body0.50|nbar1" in ids


def test_detect_cell_day_wraps_gidxs_correctly():
    opens, highs, lows, closes = _arrays(BULLISH_EXHIBIT_BARS)
    gidxs = np.arange(1000, 1000 + len(opens))
    cell = det.Cell(zone_band=0.15, body_floor=0.50, min_bars_apart=1)
    hits = det.detect_cell_day(opens, highs, lows, closes, gidxs, cell)
    assert any(h["local_i"] == BULLISH_T and h["gidx"] == 1000 + BULLISH_T for h in hits)
