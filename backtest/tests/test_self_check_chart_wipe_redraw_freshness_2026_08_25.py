"""Guard for self_check.check_chart_wipe_redraw_freshness -- the premarket Step 5 ('chart wipe +
redraw of J's price levels') VISIBILITY instrument (L5, 2026-08-25).

Motivation: Step 5c (trendline draw) already had a self_check freshness instrument
(check_trendline_draw_freshness) after two silent budget-skips in 2026-07. Step 5 -- the sibling
chart wipe + redraw of price *levels*, stamped into key-levels.json's `chart_drawing_summary.as_of`
-- had NO coverage at all. Its stamp sat at 2026-06-29T08:39:00-04:00 (~2 MONTHS stale) with zero
alarm anywhere (self_check/STATUS.md/Discord) until this guard was built. NOTE: a separate
investigation into premarket's spot price ("Spot 767.00") was REFUTED -- that number was accurate
to $0.28 of the first non-stale live tick; the apparent gap came from comparing against engine-
flagged stale/prior-session rows. This guard does NOT touch spot-price freshness; it covers only
the chart_drawing_summary.as_of gap, which DID survive as real.

Mirrors test_self_check_trendline_draw_freshness.py's structure/import convention. This check is
DEGRADED (never BROKEN) since Step 5 is explicitly non-load-bearing visibility for J's manual
chart-reading -- the deterministic engine reads key-levels.json's `levels` array directly, never
chart_drawing_summary.
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
    now = dt.datetime(2026, 8, 22, 12, 0)  # Saturday
    assert sc.check_chart_wipe_redraw_freshness(now, path=missing) == []


def test_before_slack_window_never_flags(tmp_path):
    missing = tmp_path / "does-not-exist.json"
    now = dt.datetime(2026, 8, 24, 8, 45)  # Monday, before 09:00 ET slack expiry
    assert sc.check_chart_wipe_redraw_freshness(now, path=missing) == []


# ---- missing/never-marked file or field: past slack window on a weekday ----

def test_missing_file_flags_after_slack_window(tmp_path):
    missing = tmp_path / "does-not-exist.json"
    now = dt.datetime(2026, 8, 24, 9, 5)  # Monday, past 09:00 ET
    problems = sc.check_chart_wipe_redraw_freshness(now, path=missing)
    assert len(problems) == 1
    assert "CHART-DRAWING never marked" in problems[0]
    assert not sc._problem_is_broken(problems[0]), "non-load-bearing visibility -- must be DEGRADED, never BROKEN"


def test_file_with_no_chart_drawing_summary_key_flags(tmp_path):
    p = tmp_path / "key-levels.json"
    p.write_text(json.dumps({"levels": []}), encoding="utf-8")
    now = dt.datetime(2026, 8, 24, 9, 5)
    problems = sc.check_chart_wipe_redraw_freshness(now, path=p)
    assert len(problems) == 1
    assert "never marked" in problems[0]


def test_summary_with_no_as_of_key_flags(tmp_path):
    p = tmp_path / "key-levels.json"
    p.write_text(json.dumps({"levels": [], "chart_drawing_summary": {"drawn_count": 0}}), encoding="utf-8")
    now = dt.datetime(2026, 8, 24, 9, 5)
    problems = sc.check_chart_wipe_redraw_freshness(now, path=p)
    assert len(problems) == 1
    assert "never marked" in problems[0]


# ---- stale (as_of exists but not for today) ----

def test_stale_prior_day_flags(tmp_path):
    p = tmp_path / "key-levels.json"
    p.write_text(json.dumps({"levels": [], "chart_drawing_summary": {
        "drawn_count": 0, "as_of": "2026-06-29T08:39:00-04:00",
    }}), encoding="utf-8")
    now = dt.datetime(2026, 8, 24, 9, 5)  # Monday -- June's stamp is stale
    problems = sc.check_chart_wipe_redraw_freshness(now, path=p)
    assert len(problems) == 1
    assert "CHART-DRAWING STALE" in problems[0]
    assert "2026-06-29" in problems[0]
    assert not sc._problem_is_broken(problems[0])


def test_yesterday_flags_stale_too_beyond_one_trading_day(tmp_path):
    """Even one trading day stale (yesterday, not weekend-adjacent) must still flag -- this
    is the 'beyond one trading day' staleness the job spec calls out, not just multi-month rot."""
    p = tmp_path / "key-levels.json"
    p.write_text(json.dumps({"levels": [], "chart_drawing_summary": {
        "drawn_count": 2, "as_of": "2026-08-21T08:39:00-04:00",  # Friday
    }}), encoding="utf-8")
    now = dt.datetime(2026, 8, 24, 9, 5)  # Monday
    problems = sc.check_chart_wipe_redraw_freshness(now, path=p)
    assert len(problems) == 1
    assert "CHART-DRAWING STALE" in problems[0]


# ---- today's stamp -- no problem ----

def test_today_stamp_produces_no_problem(tmp_path):
    p = tmp_path / "key-levels.json"
    p.write_text(json.dumps({"levels": [], "chart_drawing_summary": {
        "drawn_count": 1, "as_of": "2026-08-24T08:39:00-04:00",
    }}), encoding="utf-8")
    now = dt.datetime(2026, 8, 24, 9, 5)
    assert sc.check_chart_wipe_redraw_freshness(now, path=p) == []


# ---- corrupt file -- fail-open into "never marked", never crash ----

def test_corrupt_file_treated_as_never_marked(tmp_path):
    p = tmp_path / "key-levels.json"
    p.write_text("{not valid json", encoding="utf-8")
    now = dt.datetime(2026, 8, 24, 9, 5)
    problems = sc.check_chart_wipe_redraw_freshness(now, path=p)
    assert len(problems) == 1
    assert "never marked" in problems[0]


# ---- the exact real-repo regression this guard exists for ----

def test_real_repo_key_levels_is_stale_today():
    """Verify against the REAL on-disk artifact (automation/state/key-levels.json), not a
    fixture -- a check that cannot fire on a genuinely stale file is not a check. As of this
    guard's authoring, chart_drawing_summary.as_of == 2026-06-29T08:39:00-04:00, so ANY
    present-day weekday morning must flag it."""
    now = dt.datetime(2026, 8, 25, 9, 30)  # Tuesday, market closed after-hours build window
    problems = sc.check_chart_wipe_redraw_freshness(now)  # default path -> real key-levels.json
    assert len(problems) == 1
    assert "CHART-DRAWING STALE" in problems[0]
    assert "2026-06-29" in problems[0]
    assert not sc._problem_is_broken(problems[0])


# ---- the substring trap named in the job spec: "REDRAW" (upper-case) contains "RED" ----

def test_problem_messages_never_contain_bareword_broken_triggers():
    """_problem_is_broken() escalates DEGRADED -> BROKEN on bare substrings including "RED"
    (case-sensitive). The word "redraw" upper-cased ("REDRAW") contains "RED" as a contiguous
    substring and would silently misclassify this visibility-only gap as BROKEN, wrongly
    outranking real trading-critical work in the conductor's triage. Assert every message this
    check can produce is safe against the FULL _problem_is_broken trigger set."""
    scenarios = []

    missing = Path("__definitely_does_not_exist__.json")
    now = dt.datetime(2026, 8, 24, 9, 5)
    scenarios.append(sc.check_chart_wipe_redraw_freshness(now, path=missing))

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        stale = Path(td) / "key-levels.json"
        stale.write_text(json.dumps({"chart_drawing_summary": {
            "as_of": "2026-06-29T08:39:00-04:00"}}), encoding="utf-8")
        scenarios.append(sc.check_chart_wipe_redraw_freshness(now, path=stale))

    scenarios.append(sc.check_chart_wipe_redraw_freshness(now))  # real repo state

    seen_any = False
    for problems in scenarios:
        for p in problems:
            seen_any = True
            assert not sc._problem_is_broken(p), f"message escalated to BROKEN: {p!r}"
            assert "REDRAW" not in p, f"upper-case REDRAW substring-traps RED into BROKEN: {p!r}"
    assert seen_any, "test setup produced no problems to check -- guard would be vacuous"


# ---- wiring: run() must call the check and feed it into problems ----

def test_run_source_wires_chart_wipe_redraw_freshness_check():
    import inspect
    src = inspect.getsource(sc.run)
    assert "check_chart_wipe_redraw_freshness(now)" in src
    assert "problems.extend(check_chart_wipe_redraw_freshness(now))" in src
