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
import json
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


# ============================================================================
# B2c EXTENSION -- path-coverage scoreboard + last gauntlet result
# ============================================================================

_HEALTHY_DATA = {
    "last_tick_et": "2026-07-11T22:00:00", "ticks_today": 42, "last_action": "HOLD",
    "breaker_tripped": False, "account_status": "LIVE", "n_orders_lifetime": 3,
    "last_error": None,
}


def test_single_arg_call_is_byte_for_byte_unaffected_by_the_extension():
    """Regression-proof: every pre-existing call site (coverage_data/gauntlet_data
    omitted) must render EXACTLY the old text -- no stray suffix, no crash."""
    line = fb.render_twin_lines(_HEALTHY_DATA)[0]
    assert line == ("- TWIN: last tick 2026-07-11T22:00:00 (42 today), last_action=HOLD, "
                    "breaker=OK, account=LIVE, orders=3 lifetime.")
    assert "coverage:" not in line
    assert "gauntlet:" not in line


def test_coverage_extends_the_same_line_not_a_new_bullet():
    lines = fb.render_twin_lines(_HEALTHY_DATA, {"paths": {"tp1_trail": {"status": "green"}}})
    assert len(lines) == 1                      # still ONE line -- extended, not appended-as-new
    assert lines[0].startswith("- TWIN:")
    assert "coverage:" in lines[0]


def test_coverage_renders_green_fraction_and_incident_count():
    coverage = {"paths": {
        "tp1_trail": {"status": "green", "last_incident": None},
        "structure_stop": {"status": "green", "last_incident": None},
        "catastrophe_cap": {"status": "green", "last_incident": None},
        "max_hold": {"status": "green", "last_incident": None},
        "restart_open_position": {"status": "green", "last_incident": None},
        "entry": {"status": "red", "last_incident": "wrong stage observed"},
    }}
    line = fb.render_twin_lines(_HEALTHY_DATA, coverage)[0]
    assert "coverage: 5/6 branches green today, 1 incident(s)" in line


def test_coverage_missing_data_renders_honest_no_data_yet():
    """A NEVER-WIRED scenario scheduler must render an honest placeholder, never a
    fabricated 0/0 or a silently dropped clause (OP-33: unknown is never green)."""
    line = fb.render_twin_lines(_HEALTHY_DATA, {})[0]
    assert "coverage: no path-coverage data yet" in line
    assert "gauntlet:" not in line   # no gauntlet_data passed either -> clause omitted


def test_coverage_with_gauntlet_result_appends_pass_and_time():
    coverage = {"paths": {"tp1_trail": {"status": "green"}}}
    gauntlet = {"overall": "PASS", "ts_et": "2026-07-11T20:41:07"}
    line = fb.render_twin_lines(_HEALTHY_DATA, coverage, gauntlet)[0]
    assert "gauntlet: PASS 20:41" in line


def test_coverage_with_gauntlet_fail_surfaces_fail_not_silently_pass():
    coverage = {"paths": {"structure_stop": {"status": "red", "last_incident": "timeout"}}}
    gauntlet = {"overall": "FAIL", "ts_et": "2026-07-11T20:41:07"}
    line = fb.render_twin_lines(_HEALTHY_DATA, coverage, gauntlet)[0]
    assert "gauntlet: FAIL 20:41" in line


def test_coverage_present_but_no_gauntlet_data_omits_gauntlet_clause():
    line = fb.render_twin_lines(_HEALTHY_DATA, {"paths": {"tp1_trail": {"status": "green"}}}, None)[0]
    assert "coverage:" in line
    assert "gauntlet:" not in line


def test_coverage_suffix_placed_before_last_error_which_still_appears_last():
    data = dict(_HEALTHY_DATA, last_error="ConnectionError: simulated")
    line = fb.render_twin_lines(data, {"paths": {"tp1_trail": {"status": "green"}}})[0]
    assert line.index("coverage:") < line.index("LAST ERROR")


def test_build_brief_wires_coverage_and_gauntlet_into_footer(tmp_path, monkeypatch):
    """Integration: build_brief() actually loads path-coverage.json + gauntlet-
    last.json (not just twin-health.json) and threads them through to the
    rendered TWIN line + sources footer."""
    twin_dir = tmp_path / "crypto-twin"
    twin_dir.mkdir(parents=True)
    (tmp_path / "twin-health.json").write_text(json.dumps(_HEALTHY_DATA), encoding="utf-8")
    (twin_dir / "path-coverage.json").write_text(
        json.dumps({"paths": {"tp1_trail": {"status": "green"}, "structure_stop": {"status": "green"}}}),
        encoding="utf-8")
    (twin_dir / "gauntlet-last.json").write_text(
        json.dumps({"overall": "PASS", "ts_et": "2026-07-11T20:41:07"}), encoding="utf-8")
    monkeypatch.setattr(fb, "STATE", tmp_path)

    brief = fb.build_brief({}, {}, [], _et(2026, 7, 11, 22, 0))
    assert "coverage: 2/2 branches green today, 0 incident(s)" in brief
    assert "gauntlet: PASS 20:41" in brief
    assert "crypto-twin/path-coverage.json" in brief
    assert "crypto-twin/gauntlet-last.json" in brief


def test_build_brief_missing_coverage_files_degrades_gracefully(tmp_path, monkeypatch):
    """Neither path-coverage.json nor gauntlet-last.json exist yet (B1 hasn't
    shipped the scenario scheduler) -- build_brief() must still render cleanly,
    never crash, never fabricate a green scoreboard."""
    monkeypatch.setattr(fb, "STATE", tmp_path)   # empty dir -- every twin source missing
    brief = fb.build_brief({}, {}, [], _et(2026, 7, 11, 22, 0))
    assert "## Crypto Twin (24/7 mechanism validation)" in brief
    assert "no tick yet" in brief   # twin-health.json also missing in this isolated STATE


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
