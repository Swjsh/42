"""Guard for firm_brief.render_theta_clock_lines -- the small additive section that surfaces
the THETA COCKPIT (J directive 2026-08-01, verbatim: "we can't just be getting in options
trades and have Theta kick our ass without us knowing") on the one-page firm brief. Mirrors
test_firm_brief_futures_shadow_section.py's import convention and the fail-open contract
every firm_brief.py section shares: a missing/never-fired source degrades ONLY this section's
text, never the rest of the brief.
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


def test_never_fired_renders_placeholder():
    lines = fb.render_theta_clock_lines({})
    assert len(lines) == 1
    assert "no reading yet" in lines[0]
    assert "Gamma_ThetaClock" in lines[0]


def test_error_snapshot_renders_failed_not_silent():
    # real shape from theta_clock.run_once()'s load_creds-failure early return: ts_et is
    # always set (constructed before the creds attempt) alongside "error".
    lines = fb.render_theta_clock_lines({"ts_et": "2026-08-03T09:31:00",
                                          "error": "load_creds failed: FileNotFoundError: x"})
    assert "FAILED" in lines[0]


def test_flat_day_renders_zero_positions():
    snap = {"ts_et": "2026-08-03T10:15:00", "n_positions": 0,
            "accounts_checked": ["safe-2", "bold-2", "safe-3", "risky-1", "risky-3"],
            "accounts_failed": []}
    line = fb.render_theta_clock_lines(snap)[0]
    assert "0 open SPY option position(s)" in line
    assert "5 account(s) checked" in line
    assert "0 theta-stall alert(s) today" in line
    assert "never auto-exits" in line


def test_account_failures_are_visible_not_swallowed():
    snap = {"ts_et": "2026-08-03T10:15:00", "n_positions": 1,
            "accounts_checked": ["safe-2"], "accounts_failed": [{"arm": "risky-1", "reason": "x"}]}
    line = fb.render_theta_clock_lines(snap)[0]
    assert "1 account read failure(s)" in line


def test_alerts_today_counted_from_position_state_not_snapshot():
    """The snapshot only reflects the LAST tick's n_alerts (almost always 0 -- alerts are
    rare, one-time events) -- the daily total must come from position-state.json's latched
    `alerted` flags, scoped to positions first seen TODAY."""
    snap = {"ts_et": "2026-08-03T15:50:00", "n_positions": 1,
            "accounts_checked": ["safe-2"], "accounts_failed": []}
    pstate = {"positions": {
        "safe-2::SPY260803C00747000": {"alerted": True, "first_seen_et": "2026-08-03T09:31:00"},
        "safe-2::SPY260731C00740000": {"alerted": True, "first_seen_et": "2026-07-31T09:31:00"},  # stale, different day
        "risky-1::SPY260803P00744000": {"alerted": False, "first_seen_et": "2026-08-03T10:00:00"},
    }}
    line = fb.render_theta_clock_lines(snap, pstate)[0]
    assert "1 theta-stall alert(s) today" in line  # only the same-day alerted one counts


def test_build_brief_includes_theta_clock_section():
    """Integration: the real build_brief() must include the Theta Cockpit section header
    regardless of whatever automation/state/theta-clock.json currently holds -- load_json is
    fail-open, so a missing file degrades to the placeholder line, never a crash or a dropped
    section."""
    brief = fb.build_brief({}, {}, [], _et(2026, 8, 1, 9, 30))
    assert "## Theta Cockpit (in-trade Greeks visibility)" in brief
    assert "theta-clock.json" in brief  # sources footer mentions the new input
