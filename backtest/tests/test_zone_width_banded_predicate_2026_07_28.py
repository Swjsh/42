"""Guard tests for the ZONE-WIDTH pre-registered banded predicate (2026-07-28).

Pins the frozen properties of backtest/tools/zone_width_fullhist_replay.py's
make_banded_detector BEFORE the full 390-day run is trusted:

  1. band=0 is algebraically identical to production detect_level_rejection
     (grid sweep) -- the control cell IS the production engine.
  2. STRICT-PRESERVING: when the production strict predicate fires, the banded
     detector returns the production result even if the band would pick a HIGHER
     level -- the shared base is never re-leveled.
  3. WICK-DEFERENCE: when production's wick fall-through would fire, the banded
     detector returns None so filters.py:1528-1536's wick-promotion path keeps
     ownership of that bar.
  4. Band cells fire on the two marginal classes (approach_touch at 25c-not-10c;
     pierced_close_in_zone at 10c) and classify the mode correctly.

RED on any regression to the frozen pre-registered semantics.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]          # backtest/
ROOT = REPO.parent
for _p in (str(ROOT), str(REPO), str(REPO / "tools"),
           str(ROOT / "automation" / "state" / "fleet")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import zone_width_fullhist_replay as zw               # noqa: E402
from lib import filters as filters_mod                # noqa: E402


def bar(o: float, h: float, lo: float, c: float) -> pd.Series:
    return pd.Series({
        "open": o, "high": h, "low": lo, "close": c, "volume": 1000.0,
        "timestamp_et": pd.Timestamp("2026-07-28 10:00:00"),
    })


def test_band_zero_equals_production_grid_sweep():
    """Cell 0c == production: sweep highs/closes around a level, exact agreement."""
    fire_log: list = []
    det0 = zw.make_banded_detector(0.0, fire_log)
    level = 100.0
    step = 0.05
    for hi_i in range(-10, 11):          # highs 99.50 .. 100.50
        for cl_i in range(-12, 9):       # closes 99.40 .. 100.40
            h = level + hi_i * step
            c = level + cl_i * step
            if c > h:
                continue
            b = bar(h - 0.10, h, min(c, h) - 0.20, c)
            got = det0(b, [level])
            want = filters_mod.detect_level_rejection(b, [level])
            assert got == want, f"band=0 diverged at high={h} close={c}: {got} != {want}"
    assert fire_log == [], "band=0 must never take the banded fall-through branch"


def test_strict_preserving_never_relevels():
    """Strict fires at 100.0; the 25c band alone would pick 100.5 (higher). The banded
    detector must return the PRODUCTION result (100.0), keeping the shared base intact."""
    fire_log: list = []
    det = zw.make_banded_detector(0.25, fire_log)
    b = bar(100.10, 100.30, 99.70, 99.80)     # strict vs 100.0: high>100, close<100
    # banded-only candidate 100.5: high 100.30 > 100.25 and close 99.80 < 100.75
    got = det(b, [100.0, 100.5])
    assert got == 100.0
    assert fire_log == [], "strict-preserved bars must not be logged as band fires"


def test_wick_deference_returns_none():
    """Production wick fall-through owns this bar (big upper wick, close within +10c of
    level): banded detector must return None so the wick path runs unchanged."""
    fire_log: list = []
    det = zw.make_banded_detector(0.25, fire_log)
    # L=100: O=99.90 H=100.30 Lo=99.85 C=100.05 -> range .45, upper wick .25 >=
    # max(0.15, .5*.45=.225); close 100.05 <= 100.10 tolerance; high >= level.
    b = bar(99.90, 100.30, 99.85, 100.05)
    level = 100.0
    assert filters_mod.detect_level_rejection(b, [level]) is None      # strict silent
    assert filters_mod.detect_wick_rejection_bearish(b, [level]) == level  # wick fires
    assert det(b, [level]) is None, "wick-deference violated"
    assert fire_log == []


def test_approach_touch_fires_25c_not_10c():
    """High 99.80 vs level 100 (20c shy): inside the 25c zone, outside the 10c zone."""
    b = bar(99.75, 99.80, 99.60, 99.70)
    level = 100.0
    assert filters_mod.detect_level_rejection(b, [level]) is None
    log25: list = []
    log10: list = []
    assert zw.make_banded_detector(0.25, log25)(b, [level]) == level
    assert zw.make_banded_detector(0.10, log10)(b, [level]) is None
    assert len(log25) == 1 and log25[0]["mode"] == "approach_touch"
    assert log10 == []


def test_pierced_close_in_zone_fires_10c():
    """Pierced (high 100.20 > level) but closed 8c ABOVE the level; wick too small to
    trigger the production wick path (0.12 < $0.15 floor) -- the 10c band's marginal
    close-side class."""
    b = bar(100.10, 100.20, 99.95, 100.08)
    level = 100.0
    assert filters_mod.detect_level_rejection(b, [level]) is None
    assert filters_mod.detect_wick_rejection_bearish(b, [level]) is None
    log10: list = []
    assert zw.make_banded_detector(0.10, log10)(b, [level]) == level
    assert len(log10) == 1 and log10[0]["mode"] == "pierced_close_in_zone"


def test_band_zero_via_patch_is_inert_multi_level():
    """Multi-level tiebreak delegation: strict path must return production's max-level
    pick untouched."""
    det0 = zw.make_banded_detector(0.0, [])
    b = bar(100.60, 100.80, 100.10, 100.20)   # strict fires vs 100.5 (high>|close<)
    levels = [100.5, 100.3]                    # ...and vs 100.3; production picks max
    assert det0(b, levels) == filters_mod.detect_level_rejection(b, levels) == 100.5


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
