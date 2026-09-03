"""Guard for self_check.check_trendline_draw_freshness -- the daily trendline chart-drawing
VISIBILITY instrument (RE-POINTED 2026-09-03, TRENDLINE-DRAW-HEADLESS).

ORIGINAL MOTIVATION (2026-07-19). Premarket Step 5c (LLM-driven) drew the live engine's
trendlines on J's chart once daily; two budget-skips in two days (2026-07-16/17) went ONLY
to journal '## Setups skipped' with no self_check/STATUS.md/Discord trace, so J found out
only by noticing his chart was bare. `trendline_draw_state.mark_run()` stamped
`trendline-draw-state.json#last_run` on both the success and skip path; this check watched it.

WHY IT WAS RE-POINTED (2026-09-03, same shape as CHART-DRAWING's 2026-09-02 re-point --
test_self_check_chart_wipe_redraw_freshness_2026_08_25.py). Step 5c had skipped AGAIN with
reason='budget conservation' -- an LLM choosing not to run a $0 deterministic job -- while
`trendline_chart_draw.py` (built 2026-08-09) sat unused, citing a headless-CDP constraint
`Gamma_ChartAutoDraw` (2026-08-06) had already disproved. `setup/scripts/
trendline_headless_draw.py` is the fix: a pure-Python, $0, no-LLM producer (registered as
`Gamma_TrendlineHeadlessDraw`) that stamps a NEW file, `trendline-headless-draw.json`. This
check now reads THAT file and never touches the old `trendline-draw-state.json` -- which
keeps its own meaning ("the LLM skill ran today") for anyone still invoking it by hand.

THE SUBTLE PART (identical reasoning to CHART-DRAWING). trendline_headless_draw.py calls
write_state() on every path, including its fail-open `SKIPPED_TV_DOWN`/`SKIPPED_NO_DATA`
routes, so a bare "as_of is today" test would read GREEN on a TradingView-down morning while
the chart still carries yesterday's lines. The `status` field is the load-bearing half. A
SOFT skip (TV down -- the expected off-hours case) still flags, but with a distinct,
non-alarming message from a genuine ERROR -- doctrine says fail-open is a pass on the
mechanism, but the visibility instrument still owes J a trace either way.

Posture is unchanged: DEGRADED, never BROKEN (see _problem_is_broken) -- trendline drawing is
additive visibility only, never load-bearing for a trading decision.
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

MON_AFTER_SLACK = dt.datetime(2026, 9, 7, 9, 5)   # Monday, past the 09:00 ET slack expiry
TODAY = "2026-09-07"


def _state(tmp_path, name="trendline-headless-draw.json", **fields):
    p = tmp_path / name
    p.write_text(json.dumps(fields), encoding="utf-8")
    return p


# ---- the re-point itself -------------------------------------------------------------

def test_the_check_reads_the_live_producer_not_the_retired_one(tmp_path, monkeypatch):
    """The whole 2026-09-03 fix. If this regresses, the check goes back to watching the OLD
    LLM-path stamp, which nothing new writes to, and silently drifts stale forever even
    though the new headless producer is running fine every morning.

    BEHAVIOURAL, not textual (same lesson CHART-DRAWING's own re-point test learned: a
    mutation swapping the default path to the old file must be CAUGHT, not just missed by a
    string assertion that doesn't happen to mention either filename)."""
    live = _state(tmp_path, as_of=f"{TODAY}T08:40:00-04:00", status="OK")
    retired = tmp_path / "trendline-draw-state.json"
    retired.write_text(json.dumps(
        {"drawn": [], "last_run": {"status": "skipped", "reason": "budget conservation",
                                    "date_et": "2026-08-27", "ts_et": "2026-08-27T08:31:00"}}),
        encoding="utf-8")

    monkeypatch.setattr(sc, "TRENDLINE_DRAW_STATE", live)
    assert sc.check_trendline_draw_freshness(MON_AFTER_SLACK) == [], (
        "the check flagged despite a fresh, successful trendline-headless-draw stamp -- it "
        "is reading some other file, almost certainly the RETIRED LLM-path "
        "trendline-draw-state.json that nothing new writes to"
    )


# ---- weekend / before-slack-window: never flags (nothing should have run yet) ----

def test_weekend_never_flags(tmp_path):
    now = dt.datetime(2026, 9, 6, 12, 0)  # Sunday
    assert sc.check_trendline_draw_freshness(now, path=tmp_path / "nope.json") == []


def test_before_slack_window_never_flags(tmp_path):
    now = dt.datetime(2026, 9, 8, 8, 45)  # Tuesday, before 09:00 ET slack expiry
    assert sc.check_trendline_draw_freshness(now, path=tmp_path / "nope.json") == []


# ---- missing/never-marked stamp: past slack window on a weekday ----

def test_missing_state_file_flags_after_slack_window(tmp_path):
    problems = sc.check_trendline_draw_freshness(MON_AFTER_SLACK, path=tmp_path / "nope.json")
    assert len(problems) == 1
    assert "TRENDLINE-DRAW never marked" in problems[0]
    assert not sc._problem_is_broken(problems[0]), "non-load-bearing visibility -- must be DEGRADED, never BROKEN"


def test_state_with_no_as_of_key_flags(tmp_path):
    p = _state(tmp_path, status="OK")  # no as_of at all
    problems = sc.check_trendline_draw_freshness(MON_AFTER_SLACK, path=p)
    assert len(problems) == 1
    assert "never marked" in problems[0]


def test_corrupt_state_file_treated_as_never_marked(tmp_path):
    p = tmp_path / "trendline-headless-draw.json"
    p.write_text("{not valid json", encoding="utf-8")
    problems = sc.check_trendline_draw_freshness(MON_AFTER_SLACK, path=p)
    assert len(problems) == 1
    assert "never marked" in problems[0]


# ---- stale (as_of exists but not for today) ----

def test_stale_prior_day_flags_even_with_status_ok(tmp_path):
    p = _state(tmp_path, as_of="2026-09-04T08:40:00-04:00", status="OK")
    problems = sc.check_trendline_draw_freshness(MON_AFTER_SLACK, path=p)
    assert len(problems) == 1
    assert "TRENDLINE-DRAW STALE" in problems[0]
    assert "2026-09-04" in problems[0]
    assert not sc._problem_is_broken(problems[0])


# ---- today's stamp, status != OK: the load-bearing half ----

def test_fresh_stamp_but_tv_down_still_flags_softly(tmp_path):
    """THE SUBTLE PART: today's date alone is not enough -- a TV-down run still writes
    as_of=today via its own fail-open path, so status is what actually decides GREEN vs not."""
    p = _state(tmp_path, as_of=f"{TODAY}T08:40:00-04:00", status="SKIPPED_TV_DOWN",
               reason="CDP not reachable on 127.0.0.1:9222")
    problems = sc.check_trendline_draw_freshness(MON_AFTER_SLACK, path=p)
    assert len(problems) == 1
    assert "TRENDLINE-DRAW skipped" in problems[0]
    assert "CDP not reachable" in problems[0]
    assert not sc._problem_is_broken(problems[0]), "expected fail-open path must stay report-only, never BROKEN"


def test_soft_skip_message_is_distinct_from_a_genuine_error():
    """doctrine says the fail-open TV-down path must not be escalated to the same severity
    as an actual bug -- pin that the two statuses produce visibly different wording, not just
    both-non-BROKEN by coincidence."""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        tmp_path = Path(td)
        soft = _state(tmp_path, name="soft.json", as_of=f"{TODAY}T08:40:00-04:00", status="SKIPPED_TV_DOWN")
        hard = _state(tmp_path, name="hard.json", as_of=f"{TODAY}T08:40:00-04:00", status="ERROR", reason="boom")
        soft_problems = sc.check_trendline_draw_freshness(MON_AFTER_SLACK, path=soft)
        hard_problems = sc.check_trendline_draw_freshness(MON_AFTER_SLACK, path=hard)
        assert "skipped" in soft_problems[0].lower()
        assert "DID NOT DRAW" in hard_problems[0]
        assert not sc._problem_is_broken(soft_problems[0])
        assert not sc._problem_is_broken(hard_problems[0])


def test_no_data_status_is_also_a_soft_skip(tmp_path):
    p = _state(tmp_path, as_of=f"{TODAY}T08:40:00-04:00", status="SKIPPED_NO_DATA", reason="only 3 bars fetched")
    problems = sc.check_trendline_draw_freshness(MON_AFTER_SLACK, path=p)
    assert len(problems) == 1
    assert "TRENDLINE-DRAW skipped" in problems[0]


def test_dry_run_status_flags_as_did_not_draw(tmp_path):
    """DRY_RUN is neither OK nor a fail-open skip -- it means the producer deliberately did
    not touch the chart. Must still be caught (not silently GREEN) since DRY_RUN is never the
    scheduled task's real invocation."""
    p = _state(tmp_path, as_of=f"{TODAY}T08:40:00-04:00", status="DRY_RUN")
    problems = sc.check_trendline_draw_freshness(MON_AFTER_SLACK, path=p)
    assert len(problems) == 1
    assert "DID NOT DRAW" in problems[0]


# ---- today's run, status OK: no problem ----

def test_today_ok_produces_no_problem(tmp_path):
    p = _state(tmp_path, as_of=f"{TODAY}T08:40:00-04:00", status="OK", n_drawn=2)
    assert sc.check_trendline_draw_freshness(MON_AFTER_SLACK, path=p) == []


# ---- 'run it by hand' advice must point at the new deterministic script, not the old skill ----

def test_advice_points_at_the_new_script_not_the_old_skill_by_hand():
    import inspect
    src = inspect.getsource(sc.check_trendline_draw_freshness)
    assert "trendline_headless_draw.py" in src
    assert "run the trendline-draw skill by hand" not in src, (
        "must not advise running the retired LLM skill by hand")


# ---- wiring: run() must call the check and feed it into problems ----

def test_run_source_wires_trendline_draw_freshness_check():
    import inspect
    src = inspect.getsource(sc.run)
    assert "check_trendline_draw_freshness(now)" in src
    assert "problems.extend(check_trendline_draw_freshness(now))" in src
