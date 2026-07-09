"""Guard for firm_brief.render_prospector_lines -- the small additive section
that surfaces Gamma_Prospector (the exogenous-idea organ, J 2026-07-09) on the
one-page firm brief. Mirrors test_firm_brief_autopsy_staleness.py's import
convention and the fail-open contract every firm_brief.py section shares: a
missing/errored/never-run source degrades ONLY this section's text, never the
rest of the brief. Pure -- no network, no real file I/O beyond the read-only
integration check at the bottom."""
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


def test_never_scanned_renders_placeholder():
    lines = fb.render_prospector_lines({})
    assert len(lines) == 1
    assert "no scan yet" in lines[0]
    assert "Gamma_Prospector" in lines[0]


def test_error_case_renders_failed_message():
    lines = fb.render_prospector_lines({"date": "2026-07-09", "error": "network exploded badly"})
    assert "FAILED" in lines[0]
    assert "network exploded badly" in lines[0]


def test_happy_path_with_promotion():
    data = {"date": "2026-07-09", "beat": "options_structure_metrics", "scan_ok": True,
           "n_new_ideas": 2, "n_total_ideas": 14, "promoted_idea": "gex_flip_from_banked_cboe"}
    lines = fb.render_prospector_lines(data)
    line = lines[0]
    assert "2026-07-09" in line and "options_structure_metrics" in line
    assert "2 new idea" in line and "14 total" in line
    assert "gex_flip_from_banked_cboe" in line and "_chef-inbox" in line
    assert "no free lane" not in line


def test_happy_path_without_promotion_omits_promotion_clause():
    data = {"date": "2026-07-09", "beat": "cross_asset_signals", "scan_ok": True,
           "n_new_ideas": 0, "n_total_ideas": 12, "promoted_idea": None}
    lines = fb.render_prospector_lines(data)
    assert "promoted" not in lines[0]


def test_scan_not_ok_appends_lane_note():
    data = {"date": "2026-07-09", "beat": "futures_positioning", "scan_ok": False,
           "n_new_ideas": 0, "n_total_ideas": 12, "promoted_idea": None}
    lines = fb.render_prospector_lines(data)
    assert "no free lane up" in lines[0]


def test_build_brief_includes_prospector_section():
    """Integration: the real build_brief() (called the same way Gamma_FirmBrief's
    main() calls it) must include the Prospector section header regardless of
    whatever automation/state/prospector-last.json currently holds -- load_json
    is fail-open, so a missing file degrades to the placeholder line, never a
    crash or a dropped section."""
    brief = fb.build_brief({}, {}, [], _et(2026, 7, 9, 21, 0))
    assert "## Prospector (exogenous ideas)" in brief
    assert "prospector-last.json" in brief  # sources footer mentions the new input
