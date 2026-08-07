"""Guard for self_check.check_scout_premarket_fresh -- the Gamma_ScoutPremarket (05:30 ET) ->
scout_output.json DAILY freshness detector.

Motivation: self-flagged by Gamma's own audit organ 2026-08-06 (analysis/self-audit/
new-gaps-flagged.md): "The Scout premarket macro/news scanner repeatedly fails due to a low
USD budget, leaving scout_output.json stale and biasing downstream regime/bias decisions."
Live-verified 2026-08-07: Gamma_ScoutPremarket is an LLM-agent-driven task (not a deterministic
script) that reports Windows Task Scheduler LastTaskResult=0 every weekday, but its OWN
append-only fire log (scout-log.jsonl) shows only 9 entries across 2026-05-20..2026-08-07 with
a full silent month (2026-06-19..2026-07-21) -- exit-code success is not evidence the agent
actually regenerated the artifact that day (C7). Until this guard, nothing verified the
CONSUMED ARTIFACT (scout_output.json) itself.

Mirrors test_self_check_regime_stamp_drift.py's import convention and structure -- same
DEGRADED-not-BROKEN classification (scout_addendum_to_swarm is explicitly an addendum feed
into Premarket's bias write, not a live-entry gate)."""
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
    missing = tmp_path / "scout_output.json"
    now = dt.datetime(2026, 8, 1, 12, 0)  # Saturday
    assert sc.check_scout_premarket_fresh(now, scout_path=missing) == []


def test_before_slack_window_never_flags(tmp_path):
    missing = tmp_path / "scout_output.json"
    now = dt.datetime(2026, 8, 3, 7, 45)  # Monday, before 08:00 ET slack expiry
    assert sc.check_scout_premarket_fresh(now, scout_path=missing) == []


# ---- missing artifact past the slack window on a weekday ----

def test_missing_output_flags_after_slack_window(tmp_path):
    missing = tmp_path / "scout_output.json"
    now = dt.datetime(2026, 8, 3, 8, 5)  # Monday, past 08:00 ET
    problems = sc.check_scout_premarket_fresh(now, scout_path=missing)
    assert len(problems) == 1
    assert "SCOUT DEGRADED" in problems[0]
    assert not sc._problem_is_broken(problems[0]), "addendum-only -- must be DEGRADED, never BROKEN"


# ---- stale prior-day artifact still sitting there ----

def test_stale_prior_day_flags(tmp_path):
    out = tmp_path / "scout_output.json"
    out.write_text(json.dumps({
        "generated_at": "2026-07-31T09:30:04Z",
        "for_session_date": "2026-07-31",
        "status": "ok",
    }), encoding="utf-8")
    now = dt.datetime(2026, 8, 3, 8, 5)
    problems = sc.check_scout_premarket_fresh(now, scout_path=out)
    assert len(problems) == 1
    assert "SCOUT STALE" in problems[0]
    assert "2026-07-31" in problems[0]
    assert not sc._problem_is_broken(problems[0])


# ---- fresh today (generated_at date match) -- no problem ----

def test_fresh_generated_at_produces_no_problem(tmp_path):
    out = tmp_path / "scout_output.json"
    out.write_text(json.dumps({
        "generated_at": "2026-08-03T09:30:04Z",
        "for_session_date": "2026-08-03",
        "status": "ok",
    }), encoding="utf-8")
    now = dt.datetime(2026, 8, 3, 8, 5)
    assert sc.check_scout_premarket_fresh(now, scout_path=out) == []


# ---- fresh today via for_session_date only (e.g. a late-Saturday scan for next Tuesday) ----

def test_fresh_session_date_only_produces_no_problem(tmp_path):
    out = tmp_path / "scout_output.json"
    out.write_text(json.dumps({
        "generated_at": "2026-08-01T19:20:00Z",
        "for_session_date": "2026-08-03",
        "status": "ok",
    }), encoding="utf-8")
    now = dt.datetime(2026, 8, 3, 8, 5)
    assert sc.check_scout_premarket_fresh(now, scout_path=out) == []


# ---- corrupt file -- fail-open, never crash ----

def test_corrupt_output_treated_as_missing(tmp_path):
    out = tmp_path / "scout_output.json"
    out.write_text("{not valid json", encoding="utf-8")
    now = dt.datetime(2026, 8, 3, 8, 5)
    problems = sc.check_scout_premarket_fresh(now, scout_path=out)
    assert len(problems) == 1
    assert "SCOUT DEGRADED" in problems[0]


# ---- wiring: run() must call the check and feed it into problems ----

def test_run_source_wires_scout_premarket_fresh_check():
    import inspect
    src = inspect.getsource(sc.run)
    assert "check_scout_premarket_fresh(now)" in src
    assert "problems.extend(check_scout_premarket_fresh(now))" in src
