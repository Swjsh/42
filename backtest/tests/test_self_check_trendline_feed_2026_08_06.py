"""D9 guard -- the trendline-feed liveness alarm (2026-08-06).

THE INCIDENT: automation/state/trendlines.json sat stale for 47 DAYS (2026-05-14 ->
2026-08-06) with zero alarms. Mechanism (two causes, both named): (1) the producer's ONLY
invocation was premarket.md step 2 -- an LLM instruction -- and run-premarket.ps1's
deliverable gate checks only today-bias.json, so a silently-skipped step still reported
success (C7); (2) when it DID run, a lexicographic latest-CSV pick fitted stale data
(fixed + guarded separately, commit 47c79f0b). Revival = a DETERMINISTIC premarket step
(run-premarket.ps1 TRENDLINES step) + THIS self_check alarm so a future death surfaces
within a day instead of 47. Consumption stays SHADOW (zero code consumers by design).

Run:  backtest/.venv/Scripts/python.exe -m pytest -q backtest/tests/test_self_check_trendline_feed_2026_08_06.py
"""
from __future__ import annotations

import datetime as dt
import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = ROOT / "setup" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

WEDNESDAY = dt.datetime(2026, 8, 5, 12, 0)   # mid-week, mid-day: tightest slack (1.5d)
MONDAY = dt.datetime(2026, 8, 3, 9, 0)


@pytest.fixture()
def sc():
    return importlib.import_module("self_check")


def _write(tmp_path, name, payload) -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_47_day_stale_feed_alarms(sc, tmp_path):
    """THE D9 PIN: the exact incident state (as_of 2026-05-14, checked 2026-08-05) must
    produce a DEGRADED line -- pre-fix there was NO check at all and 47 days passed silent."""
    feed = _write(tmp_path, "trendlines.json", {"as_of": "2026-05-14T08:31:00-04:00"})
    live = _write(tmp_path, "trendlines-live.json", {"generated_at": "2026-08-05T11:55:00"})
    problems = sc.check_trendline_feed_freshness(WEDNESDAY, feed_path=feed, live_path=live)
    assert len(problems) == 1 and "TRENDLINE-FEED DEGRADED" in problems[0]
    assert "47-day-silence class" in problems[0] or "producer died" in problems[0]


def test_fresh_surfaces_are_quiet(sc, tmp_path):
    feed = _write(tmp_path, "trendlines.json", {"as_of": "2026-08-05T08:31:00-04:00"})
    live = _write(tmp_path, "trendlines-live.json", {"generated_at": "2026-08-05T11:55:00"})
    assert sc.check_trendline_feed_freshness(WEDNESDAY, feed_path=feed, live_path=live) == []


def test_missing_file_is_a_death_not_a_pass(sc, tmp_path):
    """Fail-open must not mean fail-SILENT: a missing artifact IS the death this alarms on."""
    live = _write(tmp_path, "trendlines-live.json", {"generated_at": "2026-08-05T11:55:00"})
    problems = sc.check_trendline_feed_freshness(
        WEDNESDAY, feed_path=tmp_path / "absent.json", live_path=live)
    assert len(problems) == 1 and "missing/unreadable" in problems[0]


def test_dead_live_organ_alarms_independently(sc, tmp_path):
    feed = _write(tmp_path, "trendlines.json", {"as_of": "2026-08-05T08:31:00-04:00"})
    live = _write(tmp_path, "trendlines-live.json", {"generated_at": "2026-07-30T11:55:00"})
    problems = sc.check_trendline_feed_freshness(WEDNESDAY, feed_path=feed, live_path=live)
    assert len(problems) == 1 and "TRENDLINE-LIVE DEGRADED" in problems[0]


def test_monday_morning_friday_file_is_not_a_false_alarm(sc, tmp_path):
    """Weekend slack: a Friday-dated file on Monday 09:00 must NOT alarm."""
    feed = _write(tmp_path, "trendlines.json", {"as_of": "2026-07-31T08:31:00-04:00"})
    live = _write(tmp_path, "trendlines-live.json", {"generated_at": "2026-07-31T15:55:00"})
    assert sc.check_trendline_feed_freshness(MONDAY, feed_path=feed, live_path=live) == []


def test_check_is_registered_in_main(sc):
    """The alarm must actually be wired into the daily fire, not just importable."""
    src = (_SCRIPTS / "self_check.py").read_text(encoding="utf-8")
    assert "check_trendline_feed_freshness(now)" in src, (
        "check_trendline_feed_freshness exists but is not registered in self_check main() "
        "-- the D9 liveness alarm would never fire")


def test_premarket_runs_the_deterministic_producer():
    """The revival half: run-premarket.ps1 must invoke compute_trendlines.py
    deterministically (the LLM-prompt-only invocation was cause #1 of the 47-day death)."""
    ps1 = (_SCRIPTS / "run-premarket.ps1").read_text(encoding="utf-8")
    assert "compute_trendlines.py" in ps1, (
        "run-premarket.ps1 no longer runs compute_trendlines.py -- trendlines.json is back "
        "to LLM-compliance-only production (the exact 47-day-death mechanism, D9)")
