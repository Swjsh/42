"""TDD tests for the PULLBACK-HOLD bull trigger (Lane-A vocabulary build,
queue item PULLBACK-HOLD-BULL-TRIGGER, filed 2026-07-22 Fable review).

Mechanism under test: `detect_pullback_hold_bullish` (backtest/lib/filters.py) —
price dips INTO a level's zone band, HOLDS there (no close below the zone floor)
for >= min_hold_bars, then the current bar closes above the highest close seen
during the hold window. SHADOW-LOGGED ONLY (see test_pullback_hold_shadow_only.py
for the zero-behavior-change wiring proof) — Lane-B validation (frozen pre-reg →
real-fills replay → 4-condition gate + BH-FDR) is a SEPARATE, not-yet-run fire.

Real-tape fixture: the 2026-07-22 10:40-10:55 ET SPY 5m bars (backtest/data/
spy_5m_2026-05-19_2026-07-22.csv), the exact exhibit the queue item cites — a
pullback low at 746.78 (queue text: "746.80") sitting 22c inside the zone band of
a known level_memory level at 746.54 (queue text: "26c above"; both consistent
with a $0.30 zone, not a penny-exact touch — levels-are-zones, J 2026-07-17).
`detect_level_reclaim` does not fire until price is back at ~748+ (session top,
per the queue's own note); this detector confirms multiple bars earlier, at the
shelf itself.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


def _make_bar(o: float, h: float, l: float, c: float, v: float = 300_000) -> pd.Series:
    return pd.Series({"open": o, "high": h, "low": l, "close": c, "volume": v})


# ----- real-tape fixture: 2026-07-22 10:40-10:55 ET, level 746.54 -----------------

def _real_2026_07_22_window() -> pd.DataFrame:
    """Bars 08-11 of the queue item's own exhibit (10:00-10:55 ET), read verbatim
    from the cached SIP 5m CSV (rows re-indexed 0..11 for this fixture)."""
    rows = [
        (748.770, 748.970, 748.5200, 748.9700),  # 0  10:00
        (748.970, 749.380, 748.5100, 748.5401),  # 1  10:05
        (748.540, 748.775, 748.1101, 748.2400),  # 2  10:10
        (748.260, 748.320, 747.7700, 748.1400),  # 3  10:15
        (748.125, 748.430, 747.3800, 747.6000),  # 4  10:20
        (747.630, 747.810, 747.0900, 747.3000),  # 5  10:25
        (747.290, 747.790, 747.1700, 747.2400),  # 6  10:30
        (747.260, 747.450, 747.0508, 747.3100),  # 7  10:35
        (747.300, 747.450, 746.7600, 746.7800),  # 8  10:40  <- pullback low, 0.22 inside zone
        (746.790, 747.470, 746.6800, 747.3700),  # 9  10:45  <- hold bar (tighter touch, 0.14)
        (747.380, 747.650, 747.0900, 747.4200),  # 10 10:50  <- reclaim bar (breaks hold high)
        (747.390, 747.977, 747.1500, 747.9350),  # 11 10:55
    ]
    return pd.DataFrame(
        [{"open": o, "high": h, "low": l, "close": c, "volume": 300_000} for o, h, l, c in rows]
    )


def test_pullback_hold_fires_on_real_2026_07_22_exhibit_at_1050():
    """THE defining test: fires at the 10:50 bar (idx 10), 2 bars after the pullback
    low, returning the defended level 746.54 — bars earlier than level_reclaim
    (which per the queue item doesn't fire until ~748+, the session top)."""
    from lib.filters import detect_pullback_hold_bullish

    prior_bars = _real_2026_07_22_window()
    bar_idx = 10
    bar = prior_bars.iloc[bar_idx]
    result = detect_pullback_hold_bullish(bar, prior_bars, bar_idx, levels_active=[746.54])

    assert result == 746.54, (
        f"PULLBACK-HOLD must fire at 10:50 on the real 2026-07-22 exhibit, "
        f"defending level 746.54. Got {result}."
    )


def test_pullback_hold_does_not_fire_on_the_pullback_low_bar_itself():
    """Negative: the 10:40 bar (idx 8, the low itself) cannot fire — no hold has
    happened yet (C6 no-look-ahead: nothing forward of the low bar is visible to it)."""
    from lib.filters import detect_pullback_hold_bullish

    prior_bars = _real_2026_07_22_window()
    bar_idx = 8
    bar = prior_bars.iloc[bar_idx]
    assert detect_pullback_hold_bullish(bar, prior_bars, bar_idx, levels_active=[746.54]) is None


def test_pullback_hold_does_not_fire_one_bar_after_the_low_insufficient_hold():
    """Negative: the 10:45 bar (idx 9) is only 1 bar after the 10:40 low — with
    min_hold_bars=2 default, that's not enough separation yet (no distinct
    low-then-2-holds-then-reclaim shape exists at this bar)."""
    from lib.filters import detect_pullback_hold_bullish

    prior_bars = _real_2026_07_22_window()
    bar_idx = 9
    bar = prior_bars.iloc[bar_idx]
    assert detect_pullback_hold_bullish(bar, prior_bars, bar_idx, levels_active=[746.54]) is None


def test_pullback_hold_fires_again_at_1055_picking_the_tighter_touch():
    """The 10:55 bar (idx 11) also confirms — and picks idx 9 (dist 0.14, tighter)
    as the pullback low rather than idx 8 (dist 0.22), proving the 'tightest touch
    in the approach window' tie-break behaves as documented."""
    from lib.filters import detect_pullback_hold_bullish

    prior_bars = _real_2026_07_22_window()
    bar_idx = 11
    bar = prior_bars.iloc[bar_idx]
    result = detect_pullback_hold_bullish(bar, prior_bars, bar_idx, levels_active=[746.54])
    assert result == 746.54


# ----- synthetic edge-case coverage (each branch of the detector) ----------------

def _synthetic_shelf(low_close: float = 99.85, hold_close_1: float = 99.90,
                      hold_close_2: float = 99.95) -> pd.DataFrame:
    """Bars 0-2: drift down toward the level. Bar 3: pullback low touches the zone
    (level=100.00, zone=[99.70, 100.30]). Bars 4-5: hold. Bar 6: candidate reclaim."""
    rows = [
        _make_bar(101.00, 101.10, 100.80, 100.90),
        _make_bar(100.90, 100.95, 100.50, 100.60),
        _make_bar(100.60, 100.65, 100.20, 100.25),
        _make_bar(100.25, 100.30, 99.80, low_close),      # idx 3: pullback low, low=99.80 (dist 0.20)
        _make_bar(low_close, hold_close_1 + 0.05, low_close - 0.05, hold_close_1),  # idx 4: hold
        _make_bar(hold_close_1, hold_close_2 + 0.05, hold_close_1 - 0.05, hold_close_2),  # idx 5: hold
        _make_bar(hold_close_2, 100.20, hold_close_2 - 0.02, 100.10),  # idx 6: candidate reclaim
    ]
    return pd.DataFrame(rows)


def test_pullback_hold_fires_on_clean_synthetic_shelf():
    from lib.filters import detect_pullback_hold_bullish

    prior_bars = _synthetic_shelf()
    bar_idx = 6
    bar = prior_bars.iloc[bar_idx]
    result = detect_pullback_hold_bullish(bar, prior_bars, bar_idx, levels_active=[100.00])
    assert result == 100.00


def test_pullback_hold_does_not_fire_when_no_level_touched():
    """Negative: no level anywhere near the pullback low."""
    from lib.filters import detect_pullback_hold_bullish

    prior_bars = _synthetic_shelf()
    bar_idx = 6
    bar = prior_bars.iloc[bar_idx]
    assert detect_pullback_hold_bullish(bar, prior_bars, bar_idx, levels_active=[50.00]) is None


def test_pullback_hold_does_not_fire_when_zone_floor_broken_during_hold():
    """Negative: one of the hold bars closes BELOW the zone floor (99.70) —
    the shelf was broken, not defended. Pattern invalidated even though the
    current bar closes above the (now-irrelevant) prior closes."""
    from lib.filters import detect_pullback_hold_bullish

    rows = [
        _make_bar(101.00, 101.10, 100.80, 100.90),
        _make_bar(100.90, 100.95, 100.50, 100.60),
        _make_bar(100.60, 100.65, 100.20, 100.25),
        _make_bar(100.25, 100.30, 99.80, 99.85),        # idx 3: pullback low (dist 0.20)
        _make_bar(99.85, 99.90, 99.50, 99.60),           # idx 4: CLOSES BELOW FLOOR (99.60 < 99.70)
        _make_bar(99.60, 100.05, 99.55, 100.00),          # idx 5: hold
        _make_bar(100.00, 100.20, 99.95, 100.10),         # idx 6: would-be reclaim
    ]
    prior_bars = pd.DataFrame(rows)
    bar_idx = 6
    bar = prior_bars.iloc[bar_idx]
    assert detect_pullback_hold_bullish(bar, prior_bars, bar_idx, levels_active=[100.00]) is None


def test_pullback_hold_does_not_fire_when_current_bar_has_not_broken_hold_high():
    """Negative: current bar re-enters/holds the zone but does NOT close above the
    highest close of the hold window — no reclaim of the minor structure yet."""
    from lib.filters import detect_pullback_hold_bullish

    prior_bars = _synthetic_shelf(low_close=99.85, hold_close_1=99.95, hold_close_2=100.05)
    # Overwrite bar 6 (the "reclaim" bar) to close BELOW the hold-window high (100.05)
    prior_bars.loc[6] = _make_bar(100.05, 100.10, 100.00, 100.02)
    bar_idx = 6
    bar = prior_bars.iloc[bar_idx]
    assert detect_pullback_hold_bullish(bar, prior_bars, bar_idx, levels_active=[100.00]) is None


def test_pullback_hold_does_not_fire_when_current_bar_closes_below_zone_floor():
    """Negative: current bar itself closes below the zone floor — obviously not
    a reclaim regardless of the hold window's own closes."""
    from lib.filters import detect_pullback_hold_bullish

    prior_bars = _synthetic_shelf()
    prior_bars.loc[6] = _make_bar(99.90, 99.95, 99.50, 99.60)  # close 99.60 < floor 99.70
    bar_idx = 6
    bar = prior_bars.iloc[bar_idx]
    assert detect_pullback_hold_bullish(bar, prior_bars, bar_idx, levels_active=[100.00]) is None


def test_pullback_hold_returns_none_with_empty_levels():
    from lib.filters import detect_pullback_hold_bullish

    prior_bars = _synthetic_shelf()
    bar_idx = 6
    bar = prior_bars.iloc[bar_idx]
    assert detect_pullback_hold_bullish(bar, prior_bars, bar_idx, levels_active=[]) is None


def test_pullback_hold_returns_none_when_bar_idx_too_early():
    """bar_idx < min_hold_bars can never have a valid hold window — guard clause."""
    from lib.filters import detect_pullback_hold_bullish

    prior_bars = _synthetic_shelf()
    bar = prior_bars.iloc[1]
    assert detect_pullback_hold_bullish(bar, prior_bars, 1, levels_active=[100.00]) is None


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
