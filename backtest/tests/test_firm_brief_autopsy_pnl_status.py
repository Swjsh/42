"""Guard for firm_brief.render_autopsy_lines -- THE 2026-07-14 honesty fix.

Monday 2026-07-13: risky-3's real -$25 closed position sat in the broker-truth ledger, but
OPRA option bars were unavailable for it (indexing lag), so trade_autopsy.py's `rows` came
back empty. The OLD firm_brief line read `net_pnl` straight off trade-autopsy-last.json and
printed "0 engine positions, net +$0.00" -- textually identical to a genuinely flat day, even
though the .md itself already said INCOMPLETE (nobody reads the .md from a one-line brief).
These tests pin the fix: an unverified day must NEVER render a dollar figure as if it were
the day's true P&L, must say P&L_UNVERIFIED/NO_BARS instead, and legacy last.json files
written before the `pnl_status` key existed must still render correctly (inferred from the
same n_no_bars/n_positions_found fields that schema already had).

Mirrors test_firm_brief_prospector_section.py's import convention and fail-open contract."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "firm_brief", REPO / "setup" / "scripts" / "firm_brief.py")
fb = importlib.util.module_from_spec(_SPEC)
sys.modules["firm_brief"] = fb
_SPEC.loader.exec_module(fb)


def test_never_ran_renders_placeholder():
    lines = fb.render_autopsy_lines({})
    assert len(lines) == 1
    assert "no autopsy yet" in lines[0]
    assert "Gamma_TradeAutopsy" in lines[0]


def test_error_case_renders_failed_message():
    lines = fb.render_autopsy_lines({"date": "2026-07-09", "error": "traceback exploded"})
    assert "FAILED" in lines[0]
    assert "traceback exploded" in lines[0]


def test_flat_day_shows_zero_confidently():
    """A REAL flat day (0 positions found at all) is allowed to say net +$0.00 -- this is
    known-true, not a cover for missing data."""
    data = {"date": "2026-07-09", "pnl_status": "flat", "n_positions": 0,
           "n_positions_found": 0, "n_no_bars": 0, "net_pnl": 0.0,
           "n_stopped_then_paid": 0, "new_hypotheses": [], "md": "analysis/autopsies/2026-07-09.md"}
    lines = fb.render_autopsy_lines(data)
    line = lines[0]
    assert "+$0.00" in line
    assert "P&L_UNVERIFIED" not in line
    assert "0 engine positions" in line


def test_verified_day_shows_the_real_number():
    data = {"date": "2026-07-09", "pnl_status": "verified", "n_positions": 10,
           "n_positions_found": 10, "n_no_bars": 0, "net_pnl": -381.0,
           "n_stopped_then_paid": 10, "new_hypotheses": ["H-2026-07-09-stop-noise"],
           "md": "analysis/autopsies/2026-07-09.md"}
    lines = fb.render_autopsy_lines(data)
    line = lines[0]
    assert "-$381.00" in line
    assert "10 engine positions" in line
    assert "10 stopped-then-paid" in line
    assert "H-2026-07-09-stop-noise" in line
    assert "P&L_UNVERIFIED" not in line


def test_unverified_no_bars_never_shows_a_dollar_figure_as_the_days_pnl():
    """THE pinned regression: Monday 07-13's exact shape (1 position found, 1 unreplayable,
    net_pnl is None). Must say P&L_UNVERIFIED/NO_BARS, must name the counts, must NEVER
    print $0.00 or any other bare dollar figure as the day's net."""
    data = {"date": "2026-07-13", "pnl_status": "unverified_no_bars", "n_positions": 0,
           "n_positions_found": 1, "n_no_bars": 1, "net_pnl": None,
           "net_pnl_known_partial": None, "n_stopped_then_paid": 0, "new_hypotheses": [],
           "md": "analysis/autopsies/2026-07-13.md"}
    lines = fb.render_autopsy_lines(data)
    line = lines[0]
    assert "P&L_UNVERIFIED/NO_BARS" in line
    assert "$0.00" not in line
    assert "1 closed engine position" in line
    assert "bars unavailable for 1" in line
    assert "NOT a flat day" in line
    assert "2026-07-13" in line


def test_unverified_no_bars_surfaces_the_known_partial_when_present():
    """Mixed day: 3 found, 1 unreplayable, 2 DID verify at a known net -- the partial sum
    must be visible (never buried), but still never phrased as the day's total."""
    data = {"date": "2026-07-14", "pnl_status": "unverified_no_bars", "n_positions": 2,
           "n_positions_found": 3, "n_no_bars": 1, "net_pnl": None,
           "net_pnl_known_partial": 45.5, "n_stopped_then_paid": 0, "new_hypotheses": [],
           "md": "analysis/autopsies/2026-07-14.md"}
    lines = fb.render_autopsy_lines(data)
    line = lines[0]
    assert "P&L_UNVERIFIED/NO_BARS" in line
    assert "+$45.50" in line
    assert "2 replayed" in line
    assert "3 closed engine position" in line
    assert "bars unavailable for 1" in line


def test_legacy_file_without_pnl_status_key_infers_unverified():
    """A last.json written by the PRE-2026-07-14 code has no `pnl_status` key at all (the
    exact file trade_autopsy.py wrote for 2026-07-13 before this fix). Must still be
    recognized as unverified via n_no_bars/n_positions_found -- never silently fall
    through to the flat-day happy path."""
    data = {"date": "2026-07-13", "n_positions": 0, "n_positions_found": 1, "n_no_bars": 1,
           "net_pnl": 0.0, "n_stopped_then_paid": 0, "new_hypotheses": [],
           "md": "analysis/autopsies/2026-07-13.md"}
    lines = fb.render_autopsy_lines(data)
    line = lines[0]
    assert "P&L_UNVERIFIED/NO_BARS" in line
    assert "$0.00" not in line


def test_legacy_file_without_pnl_status_key_infers_flat():
    data = {"date": "2026-07-09", "n_positions": 0, "n_positions_found": 0, "n_no_bars": 0,
           "net_pnl": 0.0, "n_stopped_then_paid": 0, "new_hypotheses": [],
           "md": "analysis/autopsies/2026-07-09.md"}
    lines = fb.render_autopsy_lines(data)
    assert "P&L_UNVERIFIED" not in lines[0]
    assert "+$0.00" in lines[0]


def test_legacy_file_without_pnl_status_key_infers_verified():
    data = {"date": "2026-07-08", "n_positions": 14, "n_positions_found": 14, "n_no_bars": 0,
           "net_pnl": -382.0, "n_stopped_then_paid": 8, "new_hypotheses": [],
           "md": "analysis/autopsies/2026-07-08.md"}
    lines = fb.render_autopsy_lines(data)
    assert "P&L_UNVERIFIED" not in lines[0]
    assert "-$382.00" in lines[0]


def test_build_brief_never_crashes_on_the_pinned_monday_shape():
    """Integration: build_brief() (called the same way Gamma_FirmBrief's main() calls it)
    must render the unverified line inline, without crashing, for the exact real shape
    Monday 07-13 produced."""
    import datetime as dt
    autopsy_snapshot = {"date": "2026-07-13", "n_positions": 0, "n_positions_found": 1,
                        "n_no_bars": 1, "pnl_status": "unverified_no_bars", "net_pnl": None,
                        "net_pnl_known_partial": None, "n_stopped_then_paid": 0,
                        "new_hypotheses": [], "md": "analysis/autopsies/2026-07-13.md"}
    orig_load_json = fb.load_json
    try:
        fb.load_json = lambda path: (autopsy_snapshot if str(path).endswith(
            "trade-autopsy-last.json") else orig_load_json(path))
        brief = fb.build_brief({}, {}, [], dt.datetime(2026, 7, 14, 8, 35))
    finally:
        fb.load_json = orig_load_json
    assert "## Gamma's read (trade autopsy)" in brief
    assert "P&L_UNVERIFIED/NO_BARS" in brief
