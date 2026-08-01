"""Guard for firm_brief.render_core_recency_lines -- the CORE-STRATEGY RECENCY brief
line (WS11, 2026-08-01; J's standing rule 2026-07-31: "day 372 ago is not gonna work
like day 162 ago" -- and the core strategy itself was the one armed thing with no
recency clock on any surface J reads).

Pin the properties that make the line trustworthy rather than merely present:
  1. The headline ALWAYS carries per-direction verdict AND n ("bear RED n=15, bull
     UNDERPOWERED n=2") -- an n-free verdict is exactly the oversell OP-33 bans.
  2. UNDERPOWERED renders as UNDERPOWERED -- never dressed up as GREEN/RED.
  3. A RED direction renders loudly (the word RED survives into the line).
  4. Fails OPEN on missing/error/never-ran input, same shape as every other section.
  5. A stale run (run_date older than the most recent expected nightly) says STALE
     rather than quietly quoting old numbers (OP-33b: registered != firing).
  6. build_brief() actually includes the section (wiring, not just the renderer).

Mirrors test_firm_brief_winner_autopsy_section.py's import convention."""
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

_OK = {
    "run_date": "2026-08-01",
    "window": {"start": "2026-06-26", "end": "2026-07-31", "n_trading_days": 25},
    "confirm_n_floor": 10,
    "headline": "core strategy recency: bear RED n=15, bull UNDERPOWERED n=2 "
                "(floor 10, 25d to 2026-07-31)",
    "verdicts": {
        "bear": {"verdict": "RED", "n": 15, "exp_per_trade": -40.6,
                 "headline": "bear RED n=15"},
        "bull": {"verdict": "UNDERPOWERED", "n": 2, "exp_per_trade": -147.5,
                 "headline": "bull UNDERPOWERED n=2"},
    },
    "strata": {"replay_supplement_safe_shape": {
        "recent": {"bear": {"n": 12, "exp_per_trade": -8.0},
                   "bull": {"n": 4, "exp_per_trade": 15.0}}}},
}

_NOW = dt.datetime(2026, 8, 1, 21, 0)


def test_ok_line_carries_verdict_and_n_per_direction():
    lines = fb.render_core_recency_lines(_OK, _NOW)
    joined = "\n".join(lines)
    assert "bear RED n=15" in joined
    assert "bull UNDERPOWERED n=2" in joined
    assert "core-strategy-recency.json" in joined  # pointer to the full detail


def test_underpowered_is_never_dressed_as_a_verdict():
    data = dict(_OK)
    lines = fb.render_core_recency_lines(data, _NOW)
    joined = "\n".join(lines)
    # the bull cell must not read GREEN/RED anywhere on this line
    assert "bull UNDERPOWERED" in joined
    assert "bull GREEN" not in joined and "bull RED" not in joined


def test_red_direction_renders_the_word_red():
    lines = fb.render_core_recency_lines(_OK, _NOW)
    assert any("RED" in ln for ln in lines)


def test_replay_supplement_is_labelled_when_present():
    lines = fb.render_core_recency_lines(_OK, _NOW)
    joined = "\n".join(lines)
    assert "replay" in joined.lower()          # supplement quoted...
    assert "n=15" in joined and "n=2" in joined  # ...but broker n stays the headline


def test_never_ran_renders_placeholder():
    lines = fb.render_core_recency_lines({}, _NOW)
    assert len(lines) == 1
    assert "no core-strategy recency run yet" in lines[0]


def test_stale_run_says_stale():
    """A run_date more than 2 calendar days old (nightly cadence + weekend grace) must
    surface STALE -- old numbers quoted as fresh is the C7 silent-wrong class."""
    old = dict(_OK, run_date="2026-07-25")
    lines = fb.render_core_recency_lines(old, dt.datetime(2026, 8, 1, 21, 0))
    assert any("STALE" in ln for ln in lines)


def test_fresh_run_has_no_stale_flag():
    lines = fb.render_core_recency_lines(_OK, _NOW)
    assert not any("STALE" in ln for ln in lines)


def test_build_brief_includes_the_section(monkeypatch, tmp_path):
    """Wiring guard: build_brief must render the section header even with every source
    missing (fail-open) -- proves the section is actually reachable from the brief."""
    monkeypatch.setattr(fb, "STATE", tmp_path)  # no state files exist -> all sections degrade
    text = fb.build_brief({}, {}, [], _NOW)
    assert "## Core strategy recency" in text
    assert "no core-strategy recency run yet" in text
