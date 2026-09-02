"""Guard for self_check.check_chart_wipe_redraw_freshness -- the daily chart wipe + level
redraw VISIBILITY instrument (L5, built 2026-08-25; RE-POINTED 2026-09-02).

ORIGINAL MOTIVATION (2026-08-25). Step 5c (trendline draw) already had a freshness
instrument after two silent budget-skips in 2026-07. Step 5 -- the sibling chart wipe +
redraw of price *levels* -- had none, and its stamp sat ~2 MONTHS stale with zero alarm
anywhere. (A separate investigation into premarket's spot price was REFUTED that session and
this guard never covered it.)

WHY IT WAS RE-POINTED (2026-09-02). The check watched `key-levels.json ->
chart_drawing_summary.as_of`, written by premarket Step 5 -- an LLM step that is RETIRED.
`Gamma_ChartAutoDraw` (registered 2026-08-06, $0, 08:35-16:05 ET every 30m) replaced it with
`setup/scripts/draw_key_levels.py`, which stamps `automation/state/chart-autodraw.json`.
The old field therefore froze at 2026-06-29 and the check cried CHART-DRAWING STALE every 30
minutes for two months against a chart that was being redrawn correctly every day. That
noise is what buried the whole `### BROKEN` surface (queue.md STATUS-BROKEN-BLOCKS-DRAIN).

A check pointed at a retired producer reports on the retired producer, not on the system
(C14). The half of this file that matters most is therefore
`test_the_check_reads_the_live_producer_not_the_retired_one`.

THE SUBTLE PART. draw_key_levels.py calls write_state() on its FAILURE paths too, so a
TradingView-down morning still stamps a fresh `as_of`. A bare "as_of is today" test would
read GREEN while J's chart carried yesterday's levels. The status field is the load-bearing
half -- see test_fresh_stamp_but_tv_down_still_flags.

Posture is unchanged: DEGRADED, never BROKEN. The deterministic engine reads key-levels.json's
`levels` array for entries/exits and never any drawing stamp, so a miss costs eyeball context,
not trading correctness.
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

MON_AFTER_SLACK = dt.datetime(2026, 8, 24, 9, 5)   # Monday, past the 09:00 ET slack expiry
TODAY = "2026-08-24"


def _state(tmp_path, **fields):
    p = tmp_path / "chart-autodraw.json"
    p.write_text(json.dumps(fields), encoding="utf-8")
    return p


# ---- the re-point itself -------------------------------------------------------------

def test_the_check_reads_the_live_producer_not_the_retired_one(tmp_path, monkeypatch):
    """The whole 2026-09-02 fix. If this regresses, the check goes back to watching a field
    nothing has written since 2026-06-29 and resumes crying stale against a healthy chart.

    BEHAVIOURAL, not textual. The first cut of this test asserted
    `CHART_AUTODRAW_STATE.name == "chart-autodraw.json"` plus `"chart_drawing_summary" not in
    <body>`, and a RED-proof mutation that swapped the default path to `STATE /
    "key-levels.json"` sailed straight through it -- neither string appears in that mutant.
    It tested how the regression happened to be SPELLED. So: build both files, point the
    module's default at the live one, and assert which file the answer actually came from.
    """
    live = _state(tmp_path, as_of=f"{TODAY}T08:35:00-04:00", status="OK")
    retired = tmp_path / "key-levels.json"
    retired.write_text(json.dumps(
        {"levels": [], "chart_drawing_summary": {"as_of": "2026-06-29T08:39:00-04:00"}}),
        encoding="utf-8")

    monkeypatch.setattr(sc, "CHART_AUTODRAW_STATE", live)
    monkeypatch.setattr(sc, "STATE", tmp_path)  # so a key-levels.json read resolves HERE
    assert sc.check_chart_wipe_redraw_freshness(MON_AFTER_SLACK) == [], (
        "the check flagged despite a fresh, successful chart-autodraw stamp -- it is reading "
        "some other file, almost certainly the RETIRED premarket Step 5 "
        "chart_drawing_summary stamp that has been frozen at 2026-06-29 for months"
    )


# ---- weekend / before-slack-window: never flags (nothing should have run yet) ----

def test_weekend_never_flags(tmp_path):
    now = dt.datetime(2026, 8, 22, 12, 0)  # Saturday
    assert sc.check_chart_wipe_redraw_freshness(now, path=tmp_path / "nope.json") == []


def test_before_slack_window_never_flags(tmp_path):
    """First ChartAutoDraw fire is 08:35 ET; judging at 08:45 would be a false alarm."""
    now = dt.datetime(2026, 8, 24, 8, 45)
    assert sc.check_chart_wipe_redraw_freshness(now, path=tmp_path / "nope.json") == []


# ---- missing / never-marked ----------------------------------------------------------

def test_missing_file_flags_after_slack_window(tmp_path):
    problems = sc.check_chart_wipe_redraw_freshness(MON_AFTER_SLACK, path=tmp_path / "nope.json")
    assert len(problems) == 1
    assert "CHART-DRAWING never marked" in problems[0]
    assert not sc._problem_is_broken(problems[0]), (
        "non-load-bearing visibility -- must be DEGRADED, never BROKEN"
    )


def test_file_with_no_as_of_flags(tmp_path):
    p = _state(tmp_path, status="OK", drawn=[])
    problems = sc.check_chart_wipe_redraw_freshness(MON_AFTER_SLACK, path=p)
    assert len(problems) == 1 and "never marked" in problems[0]


def test_corrupt_json_flags_rather_than_raising(tmp_path):
    p = tmp_path / "chart-autodraw.json"
    p.write_text("{not json", encoding="utf-8")
    problems = sc.check_chart_wipe_redraw_freshness(MON_AFTER_SLACK, path=p)
    assert len(problems) == 1, "a corrupt state file must flag, never crash self_check"


# ---- stale vs fresh ------------------------------------------------------------------

def test_yesterdays_stamp_flags_stale(tmp_path):
    p = _state(tmp_path, as_of="2026-08-21T16:05:00-04:00", status="OK")
    problems = sc.check_chart_wipe_redraw_freshness(MON_AFTER_SLACK, path=p)
    assert len(problems) == 1
    assert "CHART-DRAWING STALE" in problems[0] and "2026-08-21" in problems[0]
    assert not sc._problem_is_broken(problems[0])


def test_todays_ok_stamp_is_clean(tmp_path):
    p = _state(tmp_path, as_of=f"{TODAY}T08:35:00-04:00", status="OK", dry_run=False)
    assert sc.check_chart_wipe_redraw_freshness(MON_AFTER_SLACK, path=p) == []


# ---- the subtle one: a fresh stamp that did NOT draw ----------------------------------

def test_fresh_stamp_but_tv_down_still_flags(tmp_path):
    """draw_key_levels.py write_state()s on its failure paths, so `as_of` is fresh even when
    TradingView was unreachable and the chart went untouched. Checking only the date would
    report GREEN on exactly the morning J's chart is wrong."""
    p = _state(tmp_path, as_of=f"{TODAY}T08:35:00-04:00", status="SKIPPED_TV_DOWN",
               message="CDP 9222 refused")
    problems = sc.check_chart_wipe_redraw_freshness(MON_AFTER_SLACK, path=p)
    assert len(problems) == 1
    assert "DID NOT DRAW" in problems[0] and "SKIPPED_TV_DOWN" in problems[0]
    assert not sc._problem_is_broken(problems[0])


def test_fresh_stamp_but_dry_run_still_flags(tmp_path):
    p = _state(tmp_path, as_of=f"{TODAY}T08:35:00-04:00", status="DRY_RUN")
    problems = sc.check_chart_wipe_redraw_freshness(MON_AFTER_SLACK, path=p)
    assert len(problems) == 1 and "DID NOT DRAW" in problems[0]


def test_fresh_stamp_but_error_status_still_flags(tmp_path):
    p = _state(tmp_path, as_of=f"{TODAY}T08:35:00-04:00", status="ERROR", message="boom")
    problems = sc.check_chart_wipe_redraw_freshness(MON_AFTER_SLACK, path=p)
    assert len(problems) == 1 and "DID NOT DRAW" in problems[0]


def test_unknown_future_status_flags_rather_than_passing(tmp_path):
    """Fail closed on an unrecognised status: a new status added to draw_key_levels.py must
    be classified deliberately, not silently treated as success."""
    p = _state(tmp_path, as_of=f"{TODAY}T08:35:00-04:00", status="SOMETHING_NEW")
    assert len(sc.check_chart_wipe_redraw_freshness(MON_AFTER_SLACK, path=p)) == 1


# ---- the naming constraint that predates this file ------------------------------------

def test_no_message_contains_the_bare_red_substring(tmp_path):
    """'REDRAW' upper-case would trip _problem_is_broken's bare 'RED' test and outrank real
    trading-critical work in the conductor's triage. Every message must dodge it."""
    cases = [
        sc.check_chart_wipe_redraw_freshness(MON_AFTER_SLACK, path=tmp_path / "nope.json"),
        sc.check_chart_wipe_redraw_freshness(
            MON_AFTER_SLACK, path=_state(tmp_path, as_of="2026-08-21T09:00:00", status="OK")),
        sc.check_chart_wipe_redraw_freshness(
            MON_AFTER_SLACK,
            path=_state(tmp_path, as_of=f"{TODAY}T08:35:00", status="SKIPPED_TV_DOWN")),
    ]
    for problems in cases:
        for msg in problems:
            assert "RED" not in msg, f"message trips the BROKEN classifier: {msg!r}"
            assert not sc._problem_is_broken(msg)
