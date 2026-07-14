"""Guard for firm_brief.render_futures_shadow_lines -- the small additive section that
surfaces the FUTURES-MIRROR-SHADOW 7th-arm forward-evidence lane (2026-07-14 J directive
"make sure you trade futures today too") on the one-page firm brief. Mirrors
test_firm_brief_prospector_section.py's import convention and the fail-open contract every
firm_brief.py section shares: a missing/never-fired source degrades ONLY this section's text,
never the rest of the brief.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "firm_brief", REPO / "setup" / "scripts" / "firm_brief.py")
fb = importlib.util.module_from_spec(_SPEC)
sys.modules["firm_brief"] = fb
_SPEC.loader.exec_module(fb)


def _et(y, m, d, hh, mm):
    return dt.datetime(y, m, d, hh, mm)


def test_never_computed_renders_placeholder():
    lines = fb.render_futures_shadow_lines({})
    assert len(lines) == 1
    assert "no shadow-progress.json yet" in lines[0]
    assert "Gamma_FuturesMirror" in lines[0]


def test_below_arming_bar_shows_progress_fraction():
    data = {"n_round_trips": 3, "total_pnl_usd": -45.5, "updated_et": "2026-07-14T10:00:00",
           "arming_bar": {"round_trips_needed": 20, "armable": False}}
    line = fb.render_futures_shadow_lines(data)[0]
    assert "3/20 round trips toward the arming bar" in line
    assert "-$45.50" in line
    assert "2026-07-14T10:00:00" in line


def test_at_or_above_bar_shows_expectancy_and_null_verdict():
    data = {"n_round_trips": 20, "total_pnl_usd": 120.0, "updated_et": "2026-07-14T16:05:00",
           "arming_bar": {"round_trips_needed": 20, "expectancy_positive": True,
                          "beats_null": True, "armable": True}}
    line = fb.render_futures_shadow_lines(data)[0]
    assert "20/20 round trips" in line
    assert "expectancy positive" in line
    assert "beats buy-hold null" in line
    assert "armable=True" in line
    assert "+$120.00" in line


def test_null_not_yet_evaluated_at_the_bar_renders_honestly():
    """n has hit 20 but the null itself couldn't be evaluated (e.g. every deadline fell
    outside the 7d yfinance window) -- must render as unevaluated, never silently claim a
    beat or a loss."""
    data = {"n_round_trips": 20, "total_pnl_usd": 50.0, "updated_et": "2026-07-14T16:05:00",
           "arming_bar": {"round_trips_needed": 20, "expectancy_positive": True,
                          "beats_null": None, "armable": False}}
    line = fb.render_futures_shadow_lines(data)[0]
    assert "null unevaluated vs buy-hold null" in line
    assert "armable=False" in line


def test_negative_expectancy_renders_negative():
    data = {"n_round_trips": 22, "total_pnl_usd": -30.0, "updated_et": "2026-07-14T16:05:00",
           "arming_bar": {"round_trips_needed": 20, "expectancy_positive": False,
                          "beats_null": False, "armable": False}}
    line = fb.render_futures_shadow_lines(data)[0]
    assert "expectancy negative" in line
    assert "does NOT beat buy-hold null" in line


def test_build_brief_includes_futures_shadow_section():
    """Integration: the real build_brief() must include the Futures Shadow section header
    regardless of whatever automation/state/futures/shadow-progress.json currently holds --
    load_json is fail-open, so a missing file degrades to the placeholder line, never a crash
    or a dropped section."""
    brief = fb.build_brief({}, {}, [], _et(2026, 7, 14, 9, 30))
    assert "## Futures Shadow (MES mirror, 7th-arm forward evidence)" in brief
    assert "futures/shadow-progress.json" in brief  # sources footer mentions the new input
