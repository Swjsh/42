"""Guard for self_check.check_trendline_draw_freshness -- the premarket Step 5c ('draw the live
engine's trendlines on J's chart') VISIBILITY instrument (TRENDLINE-FIXES-2026-07-17 item 1).

Motivation: two budget-skips of Step 5c happened in two days (2026-07-16/17) and both went ONLY
to journal '## Setups skipped' -- no STATUS.md/Discord surface, nothing self_check/engine-health
ever saw, so J found out only by noticing his chart was bare. trendline_draw_state.mark_run()
(automation/prompts/premarket.md Step 5c, .claude/skills/trendline-draw/SKILL.md Step 6) now
stamps every outcome (success/skipped) into trendline-draw-state.json's `last_run`; this pins the
self_check reader of that stamp.

Mirrors test_self_check_macro_calendar_freshness.py's import convention and structure, but this
check is DEGRADED (never BROKEN) since Step 5c is explicitly non-load-bearing visibility, unlike
the macro calendar's trading-relevant no-trade-window gate.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MOD_PATH = REPO / "setup" / "scripts" / "self_check.py"

_spec = importlib.util.spec_from_file_location("self_check", MOD_PATH)
sc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sc)


# ---- weekend / before-slack-window: never flags (nothing should have run yet) ----

def test_weekend_never_flags(tmp_path):
    missing = tmp_path / "does-not-exist.json"
    now = dt.datetime(2026, 7, 18, 12, 0)  # Saturday
    assert sc.check_trendline_draw_freshness(now, path=missing) == []


def test_before_slack_window_never_flags(tmp_path):
    missing = tmp_path / "does-not-exist.json"
    now = dt.datetime(2026, 7, 20, 8, 45)  # Monday, before 09:00 ET slack expiry
    assert sc.check_trendline_draw_freshness(now, path=missing) == []


# ---- missing/never-marked state: past slack window on a weekday ----

def test_missing_state_file_flags_after_slack_window(tmp_path):
    missing = tmp_path / "does-not-exist.json"
    now = dt.datetime(2026, 7, 20, 9, 5)  # Monday, past 09:00 ET
    problems = sc.check_trendline_draw_freshness(now, path=missing)
    assert len(problems) == 1
    assert "TRENDLINE-DRAW never marked" in problems[0]
    assert not sc._problem_is_broken(problems[0]), "non-load-bearing visibility -- must be DEGRADED, never BROKEN"


def test_state_with_no_last_run_key_flags(tmp_path):
    p = tmp_path / "trendline-draw-state.json"
    p.write_text(json.dumps({"drawn": []}), encoding="utf-8")
    now = dt.datetime(2026, 7, 20, 9, 5)
    problems = sc.check_trendline_draw_freshness(now, path=p)
    assert len(problems) == 1
    assert "never marked" in problems[0]


# ---- stale (last_run exists but not for today) ----

def test_stale_prior_day_flags(tmp_path):
    p = tmp_path / "trendline-draw-state.json"
    p.write_text(json.dumps({"drawn": [], "last_run": {
        "status": "success", "reason": "", "date_et": "2026-07-17", "ts_et": "2026-07-17T08:35:00",
    }}), encoding="utf-8")
    now = dt.datetime(2026, 7, 20, 9, 5)  # Monday -- Friday's run is stale
    problems = sc.check_trendline_draw_freshness(now, path=p)
    assert len(problems) == 1
    assert "TRENDLINE-DRAW STALE" in problems[0]
    assert "2026-07-17" in problems[0]
    assert not sc._problem_is_broken(problems[0])


# ---- today's run marked skipped ----

def test_today_skipped_flags_with_reason(tmp_path):
    p = tmp_path / "trendline-draw-state.json"
    p.write_text(json.dumps({"drawn": [], "last_run": {
        "status": "skipped", "reason": "context budget", "date_et": "2026-07-20", "ts_et": "2026-07-20T08:40:00",
    }}), encoding="utf-8")
    now = dt.datetime(2026, 7, 20, 9, 5)
    problems = sc.check_trendline_draw_freshness(now, path=p)
    assert len(problems) == 1
    assert "TRENDLINE-DRAW SKIPPED" in problems[0]
    assert "context budget" in problems[0]
    assert not sc._problem_is_broken(problems[0])


# ---- today's run marked success -- no problem ----

def test_today_success_produces_no_problem(tmp_path):
    p = tmp_path / "trendline-draw-state.json"
    p.write_text(json.dumps({"drawn": [{"entity_id": "e1"}], "last_run": {
        "status": "success", "reason": "", "date_et": "2026-07-20", "ts_et": "2026-07-20T08:35:00",
    }}), encoding="utf-8")
    now = dt.datetime(2026, 7, 20, 9, 5)
    assert sc.check_trendline_draw_freshness(now, path=p) == []


# ---- corrupt state -- fail-open into "never marked", never crash ----

def test_corrupt_state_file_treated_as_never_marked(tmp_path):
    p = tmp_path / "trendline-draw-state.json"
    p.write_text("{not valid json", encoding="utf-8")
    now = dt.datetime(2026, 7, 20, 9, 5)
    problems = sc.check_trendline_draw_freshness(now, path=p)
    assert len(problems) == 1
    assert "never marked" in problems[0]


# ---- wiring: run() must call the check and feed it into problems ----

def test_run_source_wires_trendline_draw_freshness_check():
    import inspect
    src = inspect.getsource(sc.run)
    assert "check_trendline_draw_freshness(now)" in src
    assert "problems.extend(check_trendline_draw_freshness(now))" in src
