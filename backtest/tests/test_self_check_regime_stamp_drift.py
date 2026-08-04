"""Guard for self_check.check_regime_stamp_daily -- the Gamma_RegimeStamp (08:22 ET) ->
Gamma_Premarket (08:30 ET) handoff DAILY drift detector.

Motivation: this exact gap ("regime-stamp drift detection... to avoid stale bias") was
self-flagged by Gamma's own audit organ TWICE in a row -- 2026-08-02 and independently
re-flagged 2026-08-03 (analysis/self-audit/new-gaps-flagged.md) -- before this fire graduated
it to code. Until this guard, the ONLY verification of the regime-stamp.json <-> today-bias.
json#regime_context handoff was monday_verify.py's WS6 check, which runs ONCE A WEEK (Monday
only) -- a Tue-Fri silent drift (e.g. Gamma_Premarket's LLM step failing to re-lift the 08:22
ET stamp) had zero daily detector. check_regime_stamp_daily reuses the exact dates_match logic
monday_verify.py's WS6 check already proved correct, generalized to run every weekday.

Mirrors test_self_check_trendline_draw_freshness.py's import convention and structure -- same
DEGRADED-not-BROKEN classification (regime_context is explicitly non-load-bearing, "never a
live entry input" per regime_stamp.py's own docstring).
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
    missing_stamp = tmp_path / "regime-stamp.json"
    missing_bias = tmp_path / "today-bias.json"
    now = dt.datetime(2026, 8, 1, 12, 0)  # Saturday
    assert sc.check_regime_stamp_daily(now, stamp_path=missing_stamp, bias_path=missing_bias) == []


def test_before_slack_window_never_flags(tmp_path):
    missing_stamp = tmp_path / "regime-stamp.json"
    missing_bias = tmp_path / "today-bias.json"
    now = dt.datetime(2026, 8, 3, 8, 45)  # Monday, before 09:00 ET slack expiry
    assert sc.check_regime_stamp_daily(now, stamp_path=missing_stamp, bias_path=missing_bias) == []


# ---- missing artifacts past the slack window on a weekday ----

def test_missing_stamp_flags_after_slack_window(tmp_path):
    missing_stamp = tmp_path / "regime-stamp.json"
    bias = tmp_path / "today-bias.json"
    bias.write_text(json.dumps({"date": "2026-08-03"}), encoding="utf-8")
    now = dt.datetime(2026, 8, 3, 9, 5)  # Monday, past 09:00 ET
    problems = sc.check_regime_stamp_daily(now, stamp_path=missing_stamp, bias_path=bias)
    assert len(problems) == 1
    assert "REGIME-STAMP DEGRADED" in problems[0]
    assert "regime-stamp.json" in problems[0]
    assert not sc._problem_is_broken(problems[0]), "non-load-bearing visibility -- must be DEGRADED, never BROKEN"


def test_missing_bias_flags_after_slack_window(tmp_path):
    stamp = tmp_path / "regime-stamp.json"
    stamp.write_text(json.dumps({"date": "2026-08-03"}), encoding="utf-8")
    missing_bias = tmp_path / "today-bias.json"
    now = dt.datetime(2026, 8, 3, 9, 5)
    problems = sc.check_regime_stamp_daily(now, stamp_path=stamp, bias_path=missing_bias)
    assert len(problems) == 1
    assert "REGIME-STAMP DEGRADED" in problems[0]
    assert "today-bias.json" in problems[0]


# ---- present but no regime_context key (Premarket didn't re-lift the stamp) ----

def test_bias_without_regime_context_flags_drift(tmp_path):
    stamp = tmp_path / "regime-stamp.json"
    stamp.write_text(json.dumps({"date": "2026-08-03"}), encoding="utf-8")
    bias = tmp_path / "today-bias.json"
    bias.write_text(json.dumps({"date": "2026-08-03"}), encoding="utf-8")
    now = dt.datetime(2026, 8, 3, 9, 5)
    problems = sc.check_regime_stamp_daily(now, stamp_path=stamp, bias_path=bias)
    assert len(problems) == 1
    assert "REGIME-STAMP DRIFT" in problems[0]
    assert "no regime_context" in problems[0]
    assert not sc._problem_is_broken(problems[0])


# ---- stale dates (yesterday's stamp/bias still sitting there) ----

def test_stale_prior_day_dates_flag_drift(tmp_path):
    stamp = tmp_path / "regime-stamp.json"
    stamp.write_text(json.dumps({"date": "2026-07-31"}), encoding="utf-8")
    bias = tmp_path / "today-bias.json"
    bias.write_text(json.dumps({
        "date": "2026-08-03",
        "regime_context": {"stamp_date": "2026-07-31", "one_liner": "stale"},
    }), encoding="utf-8")
    now = dt.datetime(2026, 8, 3, 9, 5)
    problems = sc.check_regime_stamp_daily(now, stamp_path=stamp, bias_path=bias)
    assert len(problems) == 1
    assert "REGIME-STAMP DRIFT" in problems[0]
    assert "2026-07-31" in problems[0]
    assert not sc._problem_is_broken(problems[0])


# ---- today's dates match end to end -- no problem ----

def test_dates_match_produces_no_problem(tmp_path):
    stamp = tmp_path / "regime-stamp.json"
    stamp.write_text(json.dumps({"date": "2026-08-03", "one_liner": "fresh"}), encoding="utf-8")
    bias = tmp_path / "today-bias.json"
    bias.write_text(json.dumps({
        "date": "2026-08-03",
        "regime_context": {"stamp_date": "2026-08-03", "one_liner": "fresh"},
    }), encoding="utf-8")
    now = dt.datetime(2026, 8, 3, 9, 5)
    assert sc.check_regime_stamp_daily(now, stamp_path=stamp, bias_path=bias) == []


# ---- corrupt files -- fail-open, never crash ----

def test_corrupt_stamp_treated_as_missing(tmp_path):
    stamp = tmp_path / "regime-stamp.json"
    stamp.write_text("{not valid json", encoding="utf-8")
    bias = tmp_path / "today-bias.json"
    bias.write_text(json.dumps({"date": "2026-08-03"}), encoding="utf-8")
    now = dt.datetime(2026, 8, 3, 9, 5)
    problems = sc.check_regime_stamp_daily(now, stamp_path=stamp, bias_path=bias)
    assert len(problems) == 1
    assert "REGIME-STAMP DEGRADED" in problems[0]


# ---- wiring: run() must call the check and feed it into problems ----

def test_run_source_wires_regime_stamp_daily_check():
    import inspect
    src = inspect.getsource(sc.run)
    assert "check_regime_stamp_daily(now)" in src
    assert "problems.extend(check_regime_stamp_daily(now))" in src
