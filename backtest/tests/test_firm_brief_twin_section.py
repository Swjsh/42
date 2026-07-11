"""Guard for firm_brief.render_twin_lines -- the small additive section that surfaces
the Crypto Twin (24/7 mechanism-validation training ground, J requirement 2026-07-10)
on the one-page firm brief. Mirrors test_firm_brief_prospector_section.py's import
convention and the fail-open contract every firm_brief.py section shares: a
missing/never-fired source degrades ONLY this section's text, never the rest of the
brief. Pure -- no network, no real file I/O beyond the read-only integration check at
the bottom.
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


def test_never_ticked_renders_placeholder():
    lines = fb.render_twin_lines({})
    assert len(lines) == 1
    assert "no tick yet" in lines[0]
    assert "Gamma_CryptoTwin" in lines[0]


def test_happy_path_blocked_no_account():
    data = {
        "last_tick_et": "2026-07-10T21:35:00", "ticks_today": 42, "last_action": "HOLD",
        "breaker_tripped": False, "account_status": "BLOCKED_NO_ACCOUNT", "n_orders_lifetime": 0,
        "last_error": None,
    }
    line = fb.render_twin_lines(data)[0]
    assert line.startswith("- TWIN:")
    assert "2026-07-10T21:35:00" in line
    assert "42 today" in line
    assert "last_action=HOLD" in line
    assert "breaker=OK" in line
    assert "account=BLOCKED_NO_ACCOUNT" in line
    assert "orders=0 lifetime" in line
    assert "LAST ERROR" not in line


def test_happy_path_live_account_with_orders():
    data = {
        "last_tick_et": "2026-07-10T22:00:00", "ticks_today": 5, "last_action": "ENTERED",
        "breaker_tripped": False, "account_status": "LIVE", "n_orders_lifetime": 3,
        "last_error": None,
    }
    line = fb.render_twin_lines(data)[0]
    assert "account=LIVE" in line
    assert "orders=3 lifetime" in line


def test_breaker_tripped_renders_tripped_not_ok():
    data = {"last_tick_et": "t", "ticks_today": 1, "last_action": "HOLD",
           "breaker_tripped": True, "account_status": "LIVE", "n_orders_lifetime": 0}
    line = fb.render_twin_lines(data)[0]
    assert "breaker=TRIPPED" in line


def test_breaker_unknown_renders_question_mark():
    data = {"last_tick_et": "t", "ticks_today": 1, "last_action": "HOLD",
           "breaker_tripped": None, "account_status": "LIVE", "n_orders_lifetime": 0}
    line = fb.render_twin_lines(data)[0]
    assert "breaker=?" in line


def test_last_error_surfaces_loudly():
    data = {
        "last_tick_et": "2026-07-10T22:05:00", "ticks_today": 6, "last_action": "TICK_ERROR",
        "breaker_tripped": False, "account_status": "LIVE", "n_orders_lifetime": 0,
        "last_error": "ConnectionError: simulated network outage",
    }
    line = fb.render_twin_lines(data)[0]
    assert "LAST ERROR" in line
    assert "ConnectionError" in line


def test_last_error_is_truncated_when_very_long():
    data = {"last_tick_et": "t", "ticks_today": 1, "last_action": "TICK_ERROR",
           "breaker_tripped": False, "account_status": "LIVE", "n_orders_lifetime": 0,
           "last_error": "x" * 500}
    line = fb.render_twin_lines(data)[0]
    assert len(line) < 500 + 200  # bounded, not a raw 500-char dump


def test_missing_action_status_renders_placeholder_not_crash():
    data = {"last_tick_et": "t", "ticks_today": 0, "breaker_tripped": None,
           "account_status": "?", "n_orders_lifetime": 0}
    line = fb.render_twin_lines(data)[0]
    assert "last_action=?" in line


def test_build_brief_includes_twin_section():
    """Integration: the real build_brief() (called the same way Gamma_FirmBrief's
    main() calls it) must include the Crypto Twin section header regardless of
    whatever automation/state/twin-health.json currently holds -- load_json is
    fail-open, so a missing file degrades to the placeholder line, never a crash or
    a dropped section."""
    brief = fb.build_brief({}, {}, [], _et(2026, 7, 10, 22, 0))
    assert "## Crypto Twin (24/7 mechanism validation)" in brief
    assert "twin-health.json" in brief  # sources footer mentions the new input


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
