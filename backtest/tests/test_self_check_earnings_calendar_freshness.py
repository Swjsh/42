"""Guard for self_check.check_earnings_calendar_freshness -- the weekly-1 earnings-
blackout feed VISIBILITY + FAIL-CLOSED instrument (2026-08-18, WEEKLY-OPTIONS-PROGRAM.md
"trusted earnings calendar" workstream).

Mirrors test_self_check_macro_calendar_freshness.py's shape/conventions exactly (same
producer-freshness pattern, same RED/BROKEN severity rationale): missing file, stale
file, unparseable timestamp, and a fresh file are each pinned; the threshold-read-from-
params.json behavior and its fail-open default are pinned separately; and a source-level
wiring guard confirms run() actually calls the check (never invokes run() itself -- that
needs live state/network, not appropriate from a unit test).

Uses importlib.util.spec_from_file_location (not a plain `import self_check`) to match
test_self_check_macro_calendar_freshness.py's own convention, so this survives running as
a lone file without setup/scripts pre-imported."""
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


PARAMS_48H = {"entry": {"earnings_feed_stale_hours_fail_closed": 48}}


def _write(p: Path, obj) -> Path:
    p.write_text(json.dumps(obj), encoding="utf-8")
    return p


# ---- missing / malformed feed -> always RED, never silently "probably fine" ----

def test_missing_feed_file_flags_broken_red(tmp_path):
    params = _write(tmp_path / "params.json", PARAMS_48H)
    missing = tmp_path / "does-not-exist.json"
    now = dt.datetime(2026, 8, 18, 21, 0, 0)
    problems = sc.check_earnings_calendar_freshness(now, path=missing, params_path=params)
    assert len(problems) == 1
    assert "EARNINGS-CALENDAR MISSING/UNREADABLE" in problems[0]
    assert sc._problem_is_broken(problems[0])


def test_corrupt_feed_json_flags_broken_red_not_crash(tmp_path):
    params = _write(tmp_path / "params.json", PARAMS_48H)
    p = tmp_path / "earnings-blackout.json"
    p.write_text("{not valid json", encoding="utf-8")
    now = dt.datetime(2026, 8, 18, 21, 0, 0)
    problems = sc.check_earnings_calendar_freshness(now, path=p, params_path=params)
    assert len(problems) == 1
    assert sc._problem_is_broken(problems[0])


def test_unparseable_generated_at_flags_stale_red(tmp_path):
    params = _write(tmp_path / "params.json", PARAMS_48H)
    p = _write(tmp_path / "earnings-blackout.json", {"generated_at_et": "not-a-date", "symbols": {}})
    now = dt.datetime(2026, 8, 18, 21, 0, 0)
    problems = sc.check_earnings_calendar_freshness(now, path=p, params_path=params)
    assert len(problems) == 1
    assert "no parseable generated_at_et" in problems[0]
    assert sc._problem_is_broken(problems[0])


def test_missing_generated_at_field_flags_stale_red(tmp_path):
    params = _write(tmp_path / "params.json", PARAMS_48H)
    p = _write(tmp_path / "earnings-blackout.json", {"symbols": {}})
    now = dt.datetime(2026, 8, 18, 21, 0, 0)
    problems = sc.check_earnings_calendar_freshness(now, path=p, params_path=params)
    assert len(problems) == 1
    assert sc._problem_is_broken(problems[0])


# ---- fresh feed -> silent ----

def test_fresh_feed_produces_no_problem(tmp_path):
    params = _write(tmp_path / "params.json", PARAMS_48H)
    p = _write(tmp_path / "earnings-blackout.json",
               {"generated_at_et": "2026-08-18T20:00:00", "symbols": {}})
    now = dt.datetime(2026, 8, 18, 21, 0, 0)  # 1h old, well under the 48h threshold
    assert sc.check_earnings_calendar_freshness(now, path=p, params_path=params) == []


# ---- staleness threshold: read LIVE from params.json, never hand-copied ----
# (this is the RED-PROOF target -- see the session report for the deliberate-break /
# restore evidence this test's assertion was run through)

def test_stale_feed_beyond_threshold_flags_broken_red(tmp_path):
    params = _write(tmp_path / "params.json", PARAMS_48H)
    p = _write(tmp_path / "earnings-blackout.json",
               {"generated_at_et": "2026-08-16T20:00:00", "symbols": {}})  # 49h before `now`
    now = dt.datetime(2026, 8, 18, 21, 0, 0)
    problems = sc.check_earnings_calendar_freshness(now, path=p, params_path=params)
    assert len(problems) == 1
    assert "EARNINGS-CALENDAR STALE" in problems[0]
    assert "49.0h" in problems[0]
    assert "threshold 48h" in problems[0]
    assert sc._problem_is_broken(problems[0])


def test_feed_just_under_threshold_is_not_flagged(tmp_path):
    params = _write(tmp_path / "params.json", PARAMS_48H)
    p = _write(tmp_path / "earnings-blackout.json",
               {"generated_at_et": "2026-08-16T21:30:00", "symbols": {}})  # 47.5h before `now`
    now = dt.datetime(2026, 8, 18, 21, 0, 0)
    assert sc.check_earnings_calendar_freshness(now, path=p, params_path=params) == []


def test_threshold_is_read_live_from_params_not_hand_copied(tmp_path):
    """A tighter params.json threshold (6h) must flag a feed the default 48h would have
    passed -- proves the check reads entry.earnings_feed_stale_hours_fail_closed live,
    rather than using a hardcoded 48h constant."""
    tight_params = _write(tmp_path / "params.json", {"entry": {"earnings_feed_stale_hours_fail_closed": 6}})
    p = _write(tmp_path / "earnings-blackout.json",
               {"generated_at_et": "2026-08-18T12:00:00", "symbols": {}})  # 9h before `now`
    now = dt.datetime(2026, 8, 18, 21, 0, 0)
    problems = sc.check_earnings_calendar_freshness(now, path=p, params_path=tight_params)
    assert len(problems) == 1
    assert "threshold 6h" in problems[0]


def test_unreadable_params_falls_back_to_last_known_good_default(tmp_path):
    """A missing/unreadable params.json must degrade to the documented 48h fallback --
    never silence the alarm and never fabricate a stricter one."""
    missing_params = tmp_path / "does-not-exist-params.json"
    p = _write(tmp_path / "earnings-blackout.json",
               {"generated_at_et": "2026-08-16T20:00:00", "symbols": {}})  # 49h before `now`
    now = dt.datetime(2026, 8, 18, 21, 0, 0)
    problems = sc.check_earnings_calendar_freshness(now, path=p, params_path=missing_params)
    assert len(problems) == 1
    assert "threshold 48h" in problems[0]  # fell back to _EARNINGS_FEED_STALE_HOURS_DEFAULT


# ---- wiring: run() must call the check and feed it into problems ----

def test_run_source_wires_earnings_calendar_freshness_check():
    """Source-level wiring guard (mirrors test_self_check_macro_calendar_freshness.py's
    own test_run_source_wires_macro_calendar_freshness_check) -- deliberately does NOT
    invoke run() itself (live network I/O + real state-file writes, not appropriate from
    a unit test)."""
    import inspect
    src = inspect.getsource(sc.run)
    assert "check_earnings_calendar_freshness(now)" in src, \
        "run() must call the weekly-1 earnings-calendar freshness check"
    assert "problems.extend(check_earnings_calendar_freshness(now))" in src, \
        "a stale/missing earnings feed must feed into the overall verdict"
