"""Guard for self_check.check_macro_calendar_freshness / _calendar_staleness -- the
macro/event calendar VISIBILITY instrument (2026-07-15).

Motivation: Gamma_MacroCalendar (07:45 ET weekdays, setup/scripts/macro_calendar.py) missed
its 2026-07-15 fire -- root cause: an overnight Windows-Update reboot chain (3x
TrustedInstaller "Operating System: Upgrade (Planned)" restarts, System event log 109/1074,
ending 23:32:56 MT on 07-14) left no interactive logon session (LogonType=Interactive, this
repo's universal task-registration convention) through the 05:45 MT/07:45 ET trigger window.
Corroborated by Gamma_ScoutPremarket (03:30 MT) ALSO showing NumberOfMissedRuns=1 with
LastRunTime stuck at 07-14, while every task from 06:00 MT onward (LaunchTV, Premarket,
HeartbeatCore) fired normally -- a clean ~05:45-06:00 MT boundary. This is UNRELATED to the
older, already-fixed (2026-07-09) weekly-review-producer staleness referenced in STATUS.md's
2026-07-06/07-08 entries (frozen last_refresh=2026-06-14, 22-24 days stale then, closed by
building macro_calendar.py + registering Gamma_MacroCalendar) -- the new producer's own
refresh_log shows clean consecutive weekday fires 07-10/07-13/07-14 before this ONE isolated
~28-32h miss.

context_bundle_producer.py already computes this exact staleness (calendar_stale) but that
flag is LOGGED ONLY (bundle note: "not consumed by score/gates") with no STATUS.md/Discord
surface -- so a miss could recur silently. This pins:

  1. self_check._calendar_staleness is a PURE, dependency-free duplicate of
     context_bundle_producer._calendar_staleness (duplicated, not imported, because
     context_bundle_producer.py pulls in pandas at module level for unrelated trend-alignment
     work, while self_check.py runs under the SYSTEM pythonw.exe -- Gamma_SelfCheck's install
     script -- which has NO pandas; verified 2026-07-15: `pythonw.exe -c "import pandas"` ->
     ModuleNotFoundError). test_matches_context_bundle_producer_calendar_staleness below
     cross-checks the two copies for behavioral parity so they can never silently drift.
  2. A stale calendar renders BROKEN/RED (not DEGRADED like most staleness checks in this
     file) -- a stale no-trade-window gate is a real trading-relevant risk, not cosmetic.
  3. A fresh calendar renders no problem at all.
  4. Missing/malformed news.json is ALWAYS treated as stale -- never silently "probably fine".
  5. run() actually wires the check into problems (source-level guard, no live I/O).

Mirrors test_self_check_pdt_status.py's import convention (spec_from_file_location, so this
survives running as a lone file without setup/scripts pre-imported)."""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
MOD_PATH = REPO / "setup" / "scripts" / "self_check.py"

_spec = importlib.util.spec_from_file_location("self_check", MOD_PATH)
sc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sc)


# ---- _calendar_staleness: mirrors the exact 3 cases from
#      test_context_bundle_producer.py so both copies are pinned to the same behavior ----

def test_fresh_before_todays_fire_uses_yesterdays_fire_as_anchor():
    # Wednesday 01:00 ET -- today's 07:45 fire hasn't happened yet; anchor = Tuesday 07:45.
    now_et = dt.datetime(2026, 7, 15, 1, 0)  # Wednesday
    fresh_news = {"freshness_stamp": "2026-07-14T07:45:01"}  # Tuesday's fire
    stale, reason = sc._calendar_staleness(fresh_news, now_et=now_et)
    assert stale is False
    assert reason is None


def test_stale_when_stamp_predates_expected_fire():
    now_et = dt.datetime(2026, 7, 15, 9, 0)  # Wednesday, well past today's 07:45 fire
    old_news = {"freshness_stamp": "2026-07-13T07:45:01"}  # 2 days stale
    stale, reason = sc._calendar_staleness(old_news, now_et=now_et)
    assert stale is True
    assert "predates" in reason


def test_missing_news_is_always_stale():
    stale, reason = sc._calendar_staleness(None, now_et=dt.datetime(2026, 7, 15, 1, 0))
    assert stale is True
    assert "missing" in reason


# ---- the exact 2026-07-15 scar, reproduced ----

def test_the_2026_07_15_scar_reproduced():
    """Real numbers from the incident: news.json's freshness_stamp stuck at Tuesday
    2026-07-14T07:45:01 (the last successful fire), evaluated Wednesday 2026-07-15 at 16:00 ET
    -- the exact context_bundle_producer reading captured live that day (~32.3h stale)."""
    now_et = dt.datetime(2026, 7, 15, 16, 0, 1)
    news = {"freshness_stamp": "2026-07-14T07:45:01.518286"}
    stale, reason = sc._calendar_staleness(news, now_et=now_et)
    assert stale is True
    assert "2026-07-14T07:45:01.518286" in reason
    assert "2026-07-15T07:45:00" in reason


# ---- weekend anchoring (not exercised by the original 3 context_bundle_producer cases) ----

def test_saturday_anchors_to_fridays_fire():
    now_et = dt.datetime(2026, 7, 18, 10, 0)  # Saturday
    fresh_news = {"freshness_stamp": "2026-07-17T07:45:01"}  # Friday's fire
    stale, reason = sc._calendar_staleness(fresh_news, now_et=now_et)
    assert stale is False


def test_sunday_anchors_to_fridays_fire():
    now_et = dt.datetime(2026, 7, 19, 10, 0)  # Sunday
    fresh_news = {"freshness_stamp": "2026-07-17T07:45:01"}  # Friday's fire
    stale, reason = sc._calendar_staleness(fresh_news, now_et=now_et)
    assert stale is False


def test_monday_before_fire_anchors_to_prior_fridays_fire():
    now_et = dt.datetime(2026, 7, 20, 6, 0)  # Monday, before today's 07:45 fire
    fresh_news = {"freshness_stamp": "2026-07-17T07:45:01"}  # Friday's fire
    stale, reason = sc._calendar_staleness(fresh_news, now_et=now_et)
    assert stale is False


# ---- honest-stale, never silently "probably fine" ----

def test_no_freshness_stamp_field_is_stale():
    stale, reason = sc._calendar_staleness({"some_other_key": 1}, now_et=dt.datetime(2026, 7, 15, 9, 0))
    assert stale is True
    assert "no freshness_stamp" in reason


def test_unparseable_stamp_is_stale():
    stale, reason = sc._calendar_staleness({"freshness_stamp": "not-a-date"}, now_et=dt.datetime(2026, 7, 15, 9, 0))
    assert stale is True
    assert "unparseable" in reason


# ---- check_macro_calendar_freshness: the problems-list wrapper ----

def test_check_fresh_calendar_produces_no_problem(tmp_path):
    p = tmp_path / "news.json"
    p.write_text(json.dumps({"freshness_stamp": "2026-07-15T07:45:01"}), encoding="utf-8")
    now = dt.datetime(2026, 7, 15, 9, 0)
    problems = sc.check_macro_calendar_freshness(now, news_path=p)
    assert problems == []


def test_check_stale_calendar_flags_broken_red(tmp_path):
    p = tmp_path / "news.json"
    p.write_text(json.dumps({"freshness_stamp": "2026-07-14T07:45:01.518286"}), encoding="utf-8")
    now = dt.datetime(2026, 7, 15, 19, 10, 38)
    problems = sc.check_macro_calendar_freshness(now, news_path=p)
    assert len(problems) == 1
    assert "MACRO-CALENDAR STALE" in problems[0]
    assert "Gamma_MacroCalendar" in problems[0]
    assert sc._problem_is_broken(problems[0]), \
        "a stale no-trade-window gate is a real trading risk -- must render BROKEN/RED, unlike most staleness checks in this file"


def test_check_missing_news_json_flags_broken_red(tmp_path):
    missing = tmp_path / "does-not-exist.json"
    now = dt.datetime(2026, 7, 15, 9, 0)
    problems = sc.check_macro_calendar_freshness(now, news_path=missing)
    assert len(problems) == 1
    assert "missing or malformed" in problems[0]
    assert sc._problem_is_broken(problems[0])


def test_check_corrupt_news_json_flags_stale_not_crash(tmp_path):
    p = tmp_path / "news.json"
    p.write_text("{not valid json", encoding="utf-8")
    now = dt.datetime(2026, 7, 15, 9, 0)
    problems = sc.check_macro_calendar_freshness(now, news_path=p)
    assert len(problems) == 1
    assert sc._problem_is_broken(problems[0])


# ---- parity: self_check's duplicate must never silently drift from the original ----

def test_matches_context_bundle_producer_calendar_staleness():
    """The load-bearing drift guard promised by self_check.py's module comment: if either
    copy of the anchor logic changes without the other, this REDs. Runs under backtest/.venv
    (which has pandas), unlike self_check.py's own production runtime (system pythonw, no
    pandas) -- see that module's comment for why the duplication exists at all."""
    backtest_scripts = str(REPO / "setup" / "scripts")
    if backtest_scripts not in sys.path:
        sys.path.insert(0, backtest_scripts)
    import context_bundle_producer as cbp  # noqa: PLC0415

    cases = [
        (None, dt.datetime(2026, 7, 15, 1, 0)),
        ({"freshness_stamp": "2026-07-14T07:45:01"}, dt.datetime(2026, 7, 15, 1, 0)),
        ({"freshness_stamp": "2026-07-13T07:45:01"}, dt.datetime(2026, 7, 15, 9, 0)),
        ({"freshness_stamp": "2026-07-15T07:45:01"}, dt.datetime(2026, 7, 15, 9, 0)),
        ({"freshness_stamp": "2026-07-17T07:45:01"}, dt.datetime(2026, 7, 18, 10, 0)),  # Saturday
        ({"freshness_stamp": "2026-07-17T07:45:01"}, dt.datetime(2026, 7, 19, 10, 0)),  # Sunday
        ({"freshness_stamp": "2026-07-17T07:45:01"}, dt.datetime(2026, 7, 20, 6, 0)),   # Monday pre-fire
        ({"as_of": "2026-07-14T07:45:01.518286"}, dt.datetime(2026, 7, 15, 16, 0, 1)),
        ({"some_other_key": 1}, dt.datetime(2026, 7, 15, 9, 0)),
        ({"freshness_stamp": "garbage"}, dt.datetime(2026, 7, 15, 9, 0)),
    ]
    for news, now_et in cases:
        ours = sc._calendar_staleness(news, now_et=now_et)
        theirs = cbp._calendar_staleness(news, now_et=now_et)
        assert ours == theirs, f"DRIFT for news={news!r} now_et={now_et!r}: self_check={ours!r} vs context_bundle_producer={theirs!r}"


# ---- wiring: run() must call the check and feed it into problems ----

def test_run_source_wires_macro_calendar_freshness_check():
    """Source-level wiring guard (mirrors test_self_check_pdt_status.py's
    test_run_source_wires_check_pdt_status_and_persists_summary pattern) -- deliberately does
    NOT invoke run() itself (live network I/O + real state-file writes, not appropriate from a
    unit test)."""
    import inspect
    src = inspect.getsource(sc.run)
    assert "check_macro_calendar_freshness(now)" in src, \
        "run() must call the macro-calendar freshness check"
    assert "problems.extend(check_macro_calendar_freshness(now))" in src, \
        "a stale calendar must feed into the overall verdict"
