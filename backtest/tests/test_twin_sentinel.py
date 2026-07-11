"""Guard: setup/scripts/twin_sentinel.py -- the deterministic RED/YELLOW/GREEN judge
for the CRYPTO TWIN (markdown/planning/TWIN-PROGRAM.md).

Locks in: each RED/YELLOW rule fires on its own fixture (the stale-tick bite: a
decisions.jsonl whose last row is older than the 20-min threshold MUST verdict RED);
fail-open behavior on every missing/malformed input (never raises, never crashes);
escalation de-dupe is PER EPISODE (one queue.md row + one Discord ping per continuous
RED run, re-arms after a GREEN/YELLOW recovery); the queue.md "## Twin escalations"
section is created exactly once and new rows always land INSIDE that section even
when another section gets appended below it later; the nightly review hook fires
only after 23:30 UTC and only once per UTC day; main()/_main_safe() never raise.
"""
from __future__ import annotations

import json
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in ("setup/scripts", ""):
    p = str(REPO / _p) if _p else str(REPO)
    if p not in sys.path:
        sys.path.insert(0, p)

import twin_sentinel as tsm  # noqa: E402


def _write_jsonl(path: Path, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def _write_full_uptime_history(path: Path, now_utc: datetime, *, cadence_minutes: int = None) -> None:
    """Writes one decisions.jsonl row every CADENCE_MINUTES from UTC midnight up
    through the tick just before now_utc -- 100% uptime, last tick always fresh.
    Isolates whichever OTHER rule a test targets from the LOW_UPTIME rule (which
    would otherwise false-fire on a sparse single-row fixture once >=1h has elapsed
    in the UTC day -- LOW_UPTIME_MIN_EXPECTED=12 ticks)."""
    cadence_minutes = cadence_minutes or tsm.CADENCE_MINUTES
    today_str = now_utc.strftime("%Y-%m-%d")
    midnight = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    rows = []
    t = midnight
    while t < now_utc:
        rows.append({"ts_utc": t.isoformat(), "session_date_utc": today_str, "action": "HOLD"})
        t += timedelta(minutes=cadence_minutes)
    _write_jsonl(path, rows)


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


UTC = timezone.utc


# ============================================================================
# Fail-open readers
# ============================================================================
def test_read_jsonl_missing_file_is_empty_list(tmp_path):
    assert tsm._read_jsonl(tmp_path / "nope.jsonl") == []


def test_read_jsonl_skips_malformed_lines(tmp_path):
    p = tmp_path / "d.jsonl"
    p.write_text('{"a": 1}\nnot json\n{"a": 2}\n', encoding="utf-8")
    rows = tsm._read_jsonl(p)
    assert len(rows) == 2


def test_read_json_missing_file_is_none(tmp_path):
    assert tsm._read_json(tmp_path / "nope.json") is None


def test_read_json_malformed_is_none(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not valid", encoding="utf-8")
    assert tsm._read_json(p) is None


def test_read_json_non_dict_is_none(tmp_path):
    p = tmp_path / "list.json"
    p.write_text("[1, 2, 3]", encoding="utf-8")
    assert tsm._read_json(p) is None


# ============================================================================
# evaluate_tick_freshness -- freshness + UTC-day uptime
# ============================================================================
def test_tick_freshness_no_rows_is_none_age():
    facts = tsm.evaluate_tick_freshness([], datetime(2026, 7, 11, 1, 0, tzinfo=UTC))
    assert facts["tick_age_minutes"] is None
    assert facts["last_tick_utc"] is None
    assert facts["ticks_today_utc"] == 0


def test_tick_freshness_computes_age_minutes():
    rows = [{"ts_utc": "2026-07-11T00:35:00+00:00", "session_date_utc": "2026-07-11"}]
    facts = tsm.evaluate_tick_freshness(rows, datetime(2026, 7, 11, 1, 0, tzinfo=UTC))
    assert facts["tick_age_minutes"] == pytest.approx(25.0, abs=0.01)


def test_tick_freshness_uses_last_row_even_if_unsorted_search_from_end():
    """Rows are on-disk append order (oldest first) -- the freshness scan walks
    BACKWARD from the end and must pick the LAST (most recent) row, not the first."""
    rows = [
        {"ts_utc": "2026-07-11T00:00:00+00:00"},
        {"ts_utc": "2026-07-11T00:50:00+00:00"},
    ]
    facts = tsm.evaluate_tick_freshness(rows, datetime(2026, 7, 11, 1, 0, tzinfo=UTC))
    assert facts["tick_age_minutes"] == pytest.approx(10.0, abs=0.01)


def test_tick_freshness_skips_trailing_rows_with_unparseable_timestamp():
    rows = [
        {"ts_utc": "2026-07-11T00:50:00+00:00"},
        {"ts_utc": "not-a-timestamp"},
    ]
    facts = tsm.evaluate_tick_freshness(rows, datetime(2026, 7, 11, 1, 0, tzinfo=UTC))
    assert facts["tick_age_minutes"] == pytest.approx(10.0, abs=0.01)


def test_tick_freshness_counts_today_via_session_date_utc():
    rows = [
        {"ts_utc": "2026-07-10T23:55:00+00:00", "session_date_utc": "2026-07-10"},
        {"ts_utc": "2026-07-11T00:05:00+00:00", "session_date_utc": "2026-07-11"},
        {"ts_utc": "2026-07-11T00:10:00+00:00", "session_date_utc": "2026-07-11"},
    ]
    facts = tsm.evaluate_tick_freshness(rows, datetime(2026, 7, 11, 0, 20, tzinfo=UTC))
    assert facts["ticks_today_utc"] == 2
    assert facts["expected_ticks_utc"] == 4  # 20 minutes / 5-min cadence
    assert facts["uptime_pct"] == 50.0


def test_tick_freshness_falls_back_to_ts_utc_date_when_session_date_missing():
    rows = [{"ts_utc": "2026-07-11T00:05:00+00:00"}]
    facts = tsm.evaluate_tick_freshness(rows, datetime(2026, 7, 11, 0, 10, tzinfo=UTC))
    assert facts["ticks_today_utc"] == 1


def test_tick_freshness_uptime_none_at_utc_midnight_zero_expected():
    facts = tsm.evaluate_tick_freshness([], datetime(2026, 7, 11, 0, 0, tzinfo=UTC))
    assert facts["expected_ticks_utc"] == 0
    assert facts["uptime_pct"] is None  # avoid divide-by-zero, not a fake 0% or 100%


# ============================================================================
# count_incidents_today -- schema-tolerant
# ============================================================================
def test_count_incidents_today_matches_by_date_substring():
    rows = [
        {"ts_utc": "2026-07-11T01:00:00+00:00", "kind": "x"},
        {"occurred_at": "2026-07-10T23:00:00+00:00", "kind": "y"},  # yesterday
        {"ts_utc": "2026-07-11T02:00:00+00:00", "kind": "z"},
    ]
    today_n, undated = tsm.count_incidents_today(rows, "2026-07-11")
    assert today_n == 2
    assert undated == 0


def test_count_incidents_today_excludes_undated_rows():
    rows = [{"kind": "mystery", "note": "no timestamp field at all"}]
    today_n, undated = tsm.count_incidents_today(rows, "2026-07-11")
    assert today_n == 0
    assert undated == 1


def test_count_incidents_today_empty_list():
    assert tsm.count_incidents_today([], "2026-07-11") == (0, 0)


# ============================================================================
# parse_path_coverage -- CONFIRMED schema (2026-07-11 B1c ship, verified against the
# real producer: crypto_twin_scenarios.py + crypto_twin_health.summarize_path_coverage)
# ============================================================================
def _real_branch(tier: str, status: str) -> dict:
    return {"tier": tier, "status": status, "count_today": 0,
            "last_exercised_utc": None, "last_result": None}


def test_parse_path_coverage_none_when_absent():
    assert tsm.parse_path_coverage(None, "2026-07-11") is None


def test_parse_path_coverage_real_branches_shape():
    """The ACTUAL on-disk shape (automation/state/crypto-twin/path-coverage.json,
    confirmed live 2026-07-11): branches is a dict of dicts, each with a 'status' key."""
    data = {
        "date_utc": "2026-07-11",
        "branches": {
            "ENTRY_TP1_TRAIL": _real_branch("LIVE", "GREEN"),
            "ENTRY_STRUCTURE_STOP": _real_branch("LIVE", "PENDING"),
            "ENTRY_CAT_CAP": _real_branch("LIVE", "IN_PROGRESS"),
            "ENTRY_TP1_TRAIL_BEAR": _real_branch("SIM", "NOT_YET_COVERED"),
        },
    }
    cov = tsm.parse_path_coverage(data, "2026-07-11")
    assert cov["total"] == 4
    assert cov["green"] == 1
    assert cov["incidents"] == 0
    assert cov["date_utc"] == "2026-07-11"


def test_parse_path_coverage_status_match_is_case_sensitive():
    """The real producer's status vocabulary is a closed uppercase enum (GREEN/
    INCIDENT/PENDING/IN_PROGRESS/NOT_YET_COVERED) -- a lowercase 'green' must NOT
    count (this module no longer guesses a case-insensitive match)."""
    data = {"branches": {"a": _real_branch("LIVE", "green"), "b": _real_branch("LIVE", "GREEN")}}
    cov = tsm.parse_path_coverage(data, "2026-07-11")
    assert cov["green"] == 1


def test_parse_path_coverage_counts_incidents_from_branch_status():
    data = {"branches": {
        "a": _real_branch("LIVE", "INCIDENT"),
        "b": _real_branch("LIVE", "INCIDENT"),
        "c": _real_branch("LIVE", "GREEN"),
    }}
    cov = tsm.parse_path_coverage(data, "2026-07-11")
    assert cov["incidents"] == 2
    assert cov["green"] == 1


def test_parse_path_coverage_summary_ints_fallback_shape():
    """Defensive fallback only -- NOT the real producer's shape, kept in case a future
    producer ever emits pre-aggregated counts instead of a branches map."""
    data = {"date_utc": "2026-07-11", "total_branches": 10, "green_branches": 3}
    cov = tsm.parse_path_coverage(data, "2026-07-11")
    assert cov["total"] == 10
    assert cov["green"] == 3
    assert cov["incidents"] is None  # fallback shape carries no incident signal


def test_parse_path_coverage_stale_date_is_none():
    """A coverage file dated to a PRIOR UTC day must never accuse TODAY of lagging."""
    data = {"date_utc": "2026-07-10", "total_branches": 10, "green_branches": 1}
    assert tsm.parse_path_coverage(data, "2026-07-11") is None


def test_parse_path_coverage_unrecognized_shape_is_none():
    assert tsm.parse_path_coverage({"unexpected": "shape"}, "2026-07-11") is None


# ============================================================================
# read_health_facts
# ============================================================================
def test_read_health_facts_missing_file(tmp_path):
    facts = tsm.read_health_facts(tmp_path / "nope.json")
    assert facts["health_readable"] is False
    assert facts["account_status"] is None
    assert facts["breaker_tripped"] is None


def test_read_health_facts_reads_real_fields(tmp_path):
    p = tmp_path / "twin-health.json"
    _write_json(p, {"account_status": "LIVE", "breaker_tripped": False,
                    "last_action": "HOLD", "last_error": None})
    facts = tsm.read_health_facts(p)
    assert facts["health_readable"] is True
    assert facts["account_status"] == "LIVE"
    assert facts["breaker_tripped"] is False


# ============================================================================
# evaluate() -- each RED/YELLOW rule, fixture-driven, non-vacuous bites
# ============================================================================
def _isolated_paths(tmp_path):
    return dict(
        decisions_path=tmp_path / "decisions.jsonl",
        health_path=tmp_path / "twin-health.json",
        incidents_path=tmp_path / "incidents.jsonl",
        coverage_path=tmp_path / "path-coverage.json",
    )


def test_evaluate_green_baseline(tmp_path):
    """Everything clean -> GREEN, no reasons. The floor every other test diffs against."""
    paths = _isolated_paths(tmp_path)
    now = datetime(2026, 7, 11, 0, 10, tzinfo=UTC)  # early UTC day -> uptime check not yet active
    _write_jsonl(paths["decisions_path"], [
        {"ts_utc": "2026-07-11T00:08:00+00:00", "session_date_utc": "2026-07-11", "action": "HOLD"},
    ])
    _write_json(paths["health_path"], {"account_status": "LIVE", "breaker_tripped": False})
    result = tsm.evaluate(now_utc=now, now_et=now, **paths)
    assert result["verdict"] == "GREEN"
    assert result["reasons"] == []


def test_evaluate_stale_tick_is_red(tmp_path):
    """THE BITE: last tick 25 min ago (> 20-min threshold) MUST verdict RED with a
    TICK_GAP reason -- this is the exact case the task spec calls out by name."""
    paths = _isolated_paths(tmp_path)
    now = datetime(2026, 7, 11, 1, 0, tzinfo=UTC)
    _write_jsonl(paths["decisions_path"], [
        {"ts_utc": "2026-07-11T00:35:00+00:00", "session_date_utc": "2026-07-11", "action": "HOLD"},
    ])
    result = tsm.evaluate(now_utc=now, now_et=now, **paths)
    assert result["verdict"] == "RED"
    assert any(r.startswith("TICK_GAP:") for r in result["reasons"])
    assert result["facts"]["tick_age_minutes"] == pytest.approx(25.0, abs=0.01)


def test_evaluate_no_ticks_ever_is_red_tick_gap(tmp_path):
    """A COMPLETELY missing decisions.jsonl is itself a genuine freshness problem --
    must NOT be silently skipped as 'fail-open, no data' (OP-25/C7)."""
    paths = _isolated_paths(tmp_path)
    now = datetime(2026, 7, 11, 1, 0, tzinfo=UTC)
    result = tsm.evaluate(now_utc=now, now_et=now, **paths)
    assert result["verdict"] == "RED"
    assert any(r.startswith("TICK_GAP:") for r in result["reasons"])


def test_evaluate_low_uptime_is_yellow(tmp_path):
    paths = _isolated_paths(tmp_path)
    now = datetime(2026, 7, 11, 1, 0, tzinfo=UTC)  # 60 min elapsed -> 12 expected ticks
    rows = [
        {"ts_utc": f"2026-07-11T00:{m:02d}:00+00:00", "session_date_utc": "2026-07-11", "action": "HOLD"}
        for m in (0, 55)  # only 2 of the 12 expected ticks -- also keeps the LAST tick fresh
    ]
    _write_jsonl(paths["decisions_path"], rows)
    result = tsm.evaluate(now_utc=now, now_et=now, **paths)
    assert result["verdict"] == "YELLOW"
    assert any(r.startswith("LOW_UPTIME:") for r in result["reasons"])
    assert not any(r.startswith("TICK_GAP:") for r in result["reasons"])  # last tick IS fresh


def test_evaluate_low_uptime_not_flagged_before_min_expected_sample(tmp_path):
    """Early in the UTC day (< 1h elapsed, < LOW_UPTIME_MIN_EXPECTED ticks possible)
    a thin tick count must NOT false-flag -- avoids midnight-UTC noise."""
    paths = _isolated_paths(tmp_path)
    now = datetime(2026, 7, 11, 0, 10, tzinfo=UTC)  # only 2 ticks possible so far
    _write_jsonl(paths["decisions_path"], [
        {"ts_utc": "2026-07-11T00:08:00+00:00", "session_date_utc": "2026-07-11", "action": "HOLD"},
    ])
    result = tsm.evaluate(now_utc=now, now_et=now, **paths)
    assert not any(r.startswith("LOW_UPTIME:") for r in result["reasons"])


def test_evaluate_incident_spike_is_red(tmp_path):
    paths = _isolated_paths(tmp_path)
    now = datetime(2026, 7, 11, 1, 0, tzinfo=UTC)
    _write_jsonl(paths["decisions_path"], [
        {"ts_utc": "2026-07-11T00:58:00+00:00", "session_date_utc": "2026-07-11", "action": "HOLD"},
    ])
    _write_jsonl(paths["incidents_path"], [
        {"ts_utc": "2026-07-11T00:10:00+00:00"},
        {"ts_utc": "2026-07-11T00:20:00+00:00"},
        {"ts_utc": "2026-07-11T00:30:00+00:00"},
    ])
    result = tsm.evaluate(now_utc=now, now_et=now, **paths)
    assert result["verdict"] == "RED"
    assert any(r.startswith("INCIDENT_SPIKE:") for r in result["reasons"])


def test_evaluate_two_incidents_does_not_spike(tmp_path):
    paths = _isolated_paths(tmp_path)
    now = datetime(2026, 7, 11, 1, 0, tzinfo=UTC)
    _write_jsonl(paths["decisions_path"], [
        {"ts_utc": "2026-07-11T00:58:00+00:00", "session_date_utc": "2026-07-11", "action": "HOLD"},
    ])
    _write_jsonl(paths["incidents_path"], [
        {"ts_utc": "2026-07-11T00:10:00+00:00"},
        {"ts_utc": "2026-07-11T00:20:00+00:00"},
    ])
    result = tsm.evaluate(now_utc=now, now_et=now, **paths)
    assert not any(r.startswith("INCIDENT_SPIKE:") for r in result["reasons"])


def test_evaluate_incident_spike_from_coverage_branch_status(tmp_path):
    """SECOND incident signal (confirmed live 2026-07-11, B1c): path-coverage.json's
    own per-branch status=='INCIDENT' count must ALSO be able to trip INCIDENT_SPIKE,
    even with an entirely EMPTY/absent incidents.jsonl -- this is real, live data the
    sentinel must not be blind to just because it isn't shaped like a jsonl event log."""
    paths = _isolated_paths(tmp_path)
    now = datetime(2026, 7, 11, 1, 0, tzinfo=UTC)
    _write_jsonl(paths["decisions_path"], [
        {"ts_utc": "2026-07-11T00:58:00+00:00", "session_date_utc": "2026-07-11", "action": "HOLD"},
    ])
    _write_json(paths["coverage_path"], {"date_utc": "2026-07-11", "branches": {
        "ENTRY_TP1_TRAIL": _real_branch("LIVE", "INCIDENT"),
        "ENTRY_STRUCTURE_STOP": _real_branch("LIVE", "INCIDENT"),
        "ENTRY_CAT_CAP": _real_branch("LIVE", "INCIDENT"),
        "ORGANIC_SIGNAL": _real_branch("LIVE", "GREEN"),
    }})
    result = tsm.evaluate(now_utc=now, now_et=now, **paths)
    assert result["verdict"] == "RED"
    assert any(r.startswith("INCIDENT_SPIKE:") for r in result["reasons"])
    assert result["facts"]["incidents_from_jsonl"] == 0
    assert result["facts"]["incidents_from_coverage"] == 3
    assert result["facts"]["incidents_today"] == 3


def test_evaluate_incident_spike_takes_the_worse_of_both_sources(tmp_path):
    """max(), not sum(): 2 from incidents.jsonl + 2 from coverage-branch-status must
    read as 2 (the worse single source), not 4 (double-counted as if additive)."""
    paths = _isolated_paths(tmp_path)
    now = datetime(2026, 7, 11, 1, 0, tzinfo=UTC)
    _write_jsonl(paths["decisions_path"], [
        {"ts_utc": "2026-07-11T00:58:00+00:00", "session_date_utc": "2026-07-11", "action": "HOLD"},
    ])
    _write_jsonl(paths["incidents_path"], [
        {"ts_utc": "2026-07-11T00:10:00+00:00"},
        {"ts_utc": "2026-07-11T00:20:00+00:00"},
    ])
    _write_json(paths["coverage_path"], {"date_utc": "2026-07-11", "branches": {
        "a": _real_branch("LIVE", "INCIDENT"),
        "b": _real_branch("LIVE", "INCIDENT"),
        "c": _real_branch("LIVE", "GREEN"),
    }})
    result = tsm.evaluate(now_utc=now, now_et=now, **paths)
    assert result["facts"]["incidents_today"] == 2
    assert not any(r.startswith("INCIDENT_SPIKE:") for r in result["reasons"])


def test_evaluate_coverage_lag_is_yellow_after_18_utc(tmp_path):
    paths = _isolated_paths(tmp_path)
    now = datetime(2026, 7, 11, 18, 5, tzinfo=UTC)
    _write_jsonl(paths["decisions_path"], [
        {"ts_utc": "2026-07-11T18:03:00+00:00", "session_date_utc": "2026-07-11", "action": "HOLD"},
    ])
    _write_json(paths["coverage_path"], {"date_utc": "2026-07-11", "total_branches": 10, "green_branches": 3})
    result = tsm.evaluate(now_utc=now, now_et=now, **paths)
    assert result["verdict"] == "YELLOW"
    assert any(r.startswith("COVERAGE_LAG:") for r in result["reasons"])


def test_evaluate_coverage_lag_is_yellow_with_real_branches_shape(tmp_path):
    """End-to-end through the CONFIRMED real schema (branches dict-of-dicts), not just
    the defensive summary-ints fallback -- this is what the real Gamma_TwinSentinel
    fire actually reads against automation/state/crypto-twin/path-coverage.json."""
    paths = _isolated_paths(tmp_path)
    now = datetime(2026, 7, 11, 18, 5, tzinfo=UTC)
    _write_jsonl(paths["decisions_path"], [
        {"ts_utc": "2026-07-11T18:03:00+00:00", "session_date_utc": "2026-07-11", "action": "HOLD"},
    ])
    _write_json(paths["coverage_path"], {"date_utc": "2026-07-11", "branches": {
        "ENTRY_TP1_TRAIL": _real_branch("LIVE", "GREEN"),
        "ENTRY_STRUCTURE_STOP": _real_branch("LIVE", "PENDING"),
        "ENTRY_CAT_CAP": _real_branch("LIVE", "PENDING"),
        "ENTRY_MAX_HOLD": _real_branch("LIVE", "PENDING"),
        "RESTART_OPEN_POSITION": _real_branch("LIVE", "PENDING"),
        "ORGANIC_SIGNAL": _real_branch("LIVE", "PENDING"),
        "ENTRY_TP1_TRAIL_BEAR": _real_branch("SIM", "NOT_YET_COVERED"),
        "ENTRY_STRUCTURE_STOP_BEAR": _real_branch("SIM", "NOT_YET_COVERED"),
        "ENTRY_CAT_CAP_BEAR": _real_branch("SIM", "NOT_YET_COVERED"),
    }})
    result = tsm.evaluate(now_utc=now, now_et=now, **paths)
    assert result["facts"]["coverage"]["total"] == 9
    assert result["facts"]["coverage"]["green"] == 1
    assert result["verdict"] == "YELLOW"
    assert any(r.startswith("COVERAGE_LAG:") for r in result["reasons"])


def test_evaluate_coverage_lag_not_flagged_before_18_utc(tmp_path):
    paths = _isolated_paths(tmp_path)
    now = datetime(2026, 7, 11, 12, 0, tzinfo=UTC)
    _write_jsonl(paths["decisions_path"], [
        {"ts_utc": "2026-07-11T11:58:00+00:00", "session_date_utc": "2026-07-11", "action": "HOLD"},
    ])
    _write_json(paths["coverage_path"], {"date_utc": "2026-07-11", "total_branches": 10, "green_branches": 1})
    result = tsm.evaluate(now_utc=now, now_et=now, **paths)
    assert not any(r.startswith("COVERAGE_LAG:") for r in result["reasons"])


def test_evaluate_coverage_over_half_green_not_flagged(tmp_path):
    paths = _isolated_paths(tmp_path)
    now = datetime(2026, 7, 11, 19, 0, tzinfo=UTC)
    _write_jsonl(paths["decisions_path"], [
        {"ts_utc": "2026-07-11T18:58:00+00:00", "session_date_utc": "2026-07-11", "action": "HOLD"},
    ])
    _write_json(paths["coverage_path"], {"date_utc": "2026-07-11", "total_branches": 10, "green_branches": 7})
    result = tsm.evaluate(now_utc=now, now_et=now, **paths)
    assert not any(r.startswith("COVERAGE_LAG:") for r in result["reasons"])


def test_evaluate_missing_coverage_file_never_flags_after_18_utc(tmp_path):
    """Fail-open: B1 may not have shipped path-coverage.json yet -- absence must
    never itself be treated as '0% coverage'. Uses a full healthy tick history (not
    just one fresh row) since 20:00 UTC is well past LOW_UPTIME_MIN_EXPECTED --
    isolates the coverage-absence behavior from the (separately-tested) uptime rule."""
    paths = _isolated_paths(tmp_path)
    now = datetime(2026, 7, 11, 20, 0, tzinfo=UTC)
    _write_full_uptime_history(paths["decisions_path"], now)
    result = tsm.evaluate(now_utc=now, now_et=now, **paths)
    assert result["verdict"] == "GREEN"
    assert any("coverage check skipped" in n for n in result["notes"])


def test_evaluate_breaker_tripped_is_red(tmp_path):
    paths = _isolated_paths(tmp_path)
    now = datetime(2026, 7, 11, 1, 0, tzinfo=UTC)
    _write_jsonl(paths["decisions_path"], [
        {"ts_utc": "2026-07-11T00:58:00+00:00", "session_date_utc": "2026-07-11", "action": "HOLD"},
    ])
    _write_json(paths["health_path"], {"account_status": "LIVE", "breaker_tripped": True})
    result = tsm.evaluate(now_utc=now, now_et=now, **paths)
    assert result["verdict"] == "RED"
    assert any(r.startswith("BREAKER_TRIPPED:") for r in result["reasons"])


def test_evaluate_missing_health_file_never_manufactures_red(tmp_path):
    paths = _isolated_paths(tmp_path)
    now = datetime(2026, 7, 11, 0, 10, tzinfo=UTC)  # early UTC day -> uptime check not yet active
    _write_jsonl(paths["decisions_path"], [
        {"ts_utc": "2026-07-11T00:08:00+00:00", "session_date_utc": "2026-07-11", "action": "HOLD"},
    ])
    result = tsm.evaluate(now_utc=now, now_et=now, **paths)
    assert result["verdict"] == "GREEN"
    assert any("twin-health.json unreadable" in n for n in result["notes"])


def test_evaluate_account_regression_live_to_blocked_is_red(tmp_path):
    paths = _isolated_paths(tmp_path)
    now = datetime(2026, 7, 11, 1, 0, tzinfo=UTC)
    _write_jsonl(paths["decisions_path"], [
        {"ts_utc": "2026-07-11T00:58:00+00:00", "session_date_utc": "2026-07-11", "action": "HOLD"},
    ])
    _write_json(paths["health_path"], {"account_status": "BLOCKED_NO_ACCOUNT", "breaker_tripped": False})
    prior = {"verdict": "GREEN", "facts": {"account_status": "LIVE"}}
    result = tsm.evaluate(now_utc=now, now_et=now, prior_sentinel=prior, **paths)
    assert result["verdict"] == "RED"
    assert any(r.startswith("ACCOUNT_REGRESSION:") for r in result["reasons"])


def test_evaluate_account_status_stable_live_not_flagged(tmp_path):
    paths = _isolated_paths(tmp_path)
    now = datetime(2026, 7, 11, 1, 0, tzinfo=UTC)
    _write_jsonl(paths["decisions_path"], [
        {"ts_utc": "2026-07-11T00:58:00+00:00", "session_date_utc": "2026-07-11", "action": "HOLD"},
    ])
    _write_json(paths["health_path"], {"account_status": "LIVE", "breaker_tripped": False})
    prior = {"verdict": "GREEN", "facts": {"account_status": "LIVE"}}
    result = tsm.evaluate(now_utc=now, now_et=now, prior_sentinel=prior, **paths)
    assert not any(r.startswith("ACCOUNT_REGRESSION:") for r in result["reasons"])


def test_evaluate_no_prior_sentinel_never_flags_regression(tmp_path):
    """First-ever run (no prior state) can't have 'regressed FROM LIVE' -- must not
    false-positive just because current status happens not to be LIVE."""
    paths = _isolated_paths(tmp_path)
    now = datetime(2026, 7, 11, 1, 0, tzinfo=UTC)
    _write_jsonl(paths["decisions_path"], [
        {"ts_utc": "2026-07-11T00:58:00+00:00", "session_date_utc": "2026-07-11", "action": "HOLD"},
    ])
    _write_json(paths["health_path"], {"account_status": "BLOCKED_NO_ACCOUNT", "breaker_tripped": False})
    result = tsm.evaluate(now_utc=now, now_et=now, prior_sentinel=None, **paths)
    assert not any(r.startswith("ACCOUNT_REGRESSION:") for r in result["reasons"])


def test_evaluate_red_wins_over_yellow(tmp_path):
    paths = _isolated_paths(tmp_path)
    now = datetime(2026, 7, 11, 1, 0, tzinfo=UTC)
    rows = [
        {"ts_utc": f"2026-07-11T00:{m:02d}:00+00:00", "session_date_utc": "2026-07-11", "action": "HOLD"}
        for m in (0, 55)  # thin -> LOW_UPTIME yellow, but last tick still fresh
    ]
    _write_jsonl(paths["decisions_path"], rows)
    _write_json(paths["health_path"], {"account_status": "LIVE", "breaker_tripped": True})  # RED
    result = tsm.evaluate(now_utc=now, now_et=now, **paths)
    assert result["verdict"] == "RED"
    codes = {r.split(":", 1)[0] for r in result["reasons"]}
    assert "BREAKER_TRIPPED" in codes and "LOW_UPTIME" in codes


def test_evaluate_never_writes_any_file(tmp_path):
    """The deterministic core is PURE -- no side effects, ever."""
    paths = _isolated_paths(tmp_path)
    now = datetime(2026, 7, 11, 1, 0, tzinfo=UTC)
    tsm.evaluate(now_utc=now, now_et=now, **paths)
    assert list(tmp_path.iterdir()) == []


# ============================================================================
# _append_queue_row -- section created once, rows land INSIDE the section
# ============================================================================
def test_append_queue_row_creates_section_once(tmp_path):
    qp = tmp_path / "queue.md"
    tsm._append_queue_row(["TICK_GAP: x"], today_et="2026-07-11", queue_path=qp)
    text = qp.read_text(encoding="utf-8")
    assert text.count(tsm.TWIN_ESCALATIONS_HEADER) == 1
    assert "TWIN-ESCALATION" in text
    assert "dispatch a Sonnet investigation" in text
    assert "status:pending" in text


def test_append_queue_row_second_call_does_not_duplicate_header(tmp_path):
    qp = tmp_path / "queue.md"
    tsm._append_queue_row(["TICK_GAP: x"], today_et="2026-07-11", queue_path=qp)
    tsm._append_queue_row(["INCIDENT_SPIKE: y"], today_et="2026-07-11", queue_path=qp)
    text = qp.read_text(encoding="utf-8")
    assert text.count(tsm.TWIN_ESCALATIONS_HEADER) == 1
    assert text.count("TWIN-ESCALATION") == 2


def test_append_queue_row_lands_inside_section_not_after_a_later_section(tmp_path):
    """A row appended AFTER some OTHER section got tacked onto the file must still
    land inside '## Twin escalations', never get swallowed into the later section."""
    qp = tmp_path / "queue.md"
    qp.write_text("## Some earlier section\n\n- [ ] EARLIER-ITEM :: x :: status:pending\n",
                  encoding="utf-8")
    tsm._append_queue_row(["TICK_GAP: x"], today_et="2026-07-11", queue_path=qp)
    # Now simulate an unrelated process appending a NEW section below ours.
    with qp.open("a", encoding="utf-8") as f:
        f.write("\n## A totally unrelated later section\n\n- [ ] OTHER :: y :: status:pending\n")

    tsm._append_queue_row(["BREAKER_TRIPPED: z"], today_et="2026-07-11", queue_path=qp)
    text = qp.read_text(encoding="utf-8")
    lines = text.splitlines()
    esc_idx = next(i for i, ln in enumerate(lines) if ln.strip() == tsm.TWIN_ESCALATIONS_HEADER)
    later_idx = next(i for i, ln in enumerate(lines) if "unrelated later section" in ln)
    tick_gap_idx = next(i for i, ln in enumerate(lines) if "TICK_GAP" in ln)
    breaker_idx = next(i for i, ln in enumerate(lines) if "BREAKER_TRIPPED" in ln)
    assert esc_idx < tick_gap_idx < later_idx
    assert esc_idx < breaker_idx < later_idx, "second escalation row must land BEFORE the later section, not after"


# ============================================================================
# run_sentinel() -- escalation de-dupe end to end (the real bite)
# ============================================================================
def _run_paths(tmp_path):
    return dict(
        sentinel_path=tmp_path / "twin-sentinel.json",
        queue_path=tmp_path / "queue.md",
        outbox_path=tmp_path / "discord-outbox.jsonl",
        cfg_path=tmp_path / "no-discord-config.json",
        decisions_path=tmp_path / "decisions.jsonl",
        health_path=tmp_path / "twin-health.json",
        incidents_path=tmp_path / "incidents.jsonl",
        coverage_path=tmp_path / "path-coverage.json",
        run_review=False,
    )


def _n_lines(p: Path) -> int:
    if not p.exists():
        return 0
    return len([ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()])


def test_run_sentinel_escalates_once_then_dedupes_then_rearms_on_new_episode(tmp_path):
    paths = _run_paths(tmp_path)

    # Fire 1: stale from the start -> RED, new episode -> exactly one queue row + one ping.
    now1 = datetime(2026, 7, 11, 1, 0, tzinfo=UTC)
    r1 = tsm.run_sentinel(now_utc=now1, now_et=now1, **paths)
    assert r1["verdict"] == "RED"
    assert r1["escalation"]["queue_row_written_this_episode"] is True
    assert r1["escalation"]["ping_sent_this_episode"] is True
    queue_rows_1 = paths["queue_path"].read_text(encoding="utf-8").count("TWIN-ESCALATION")
    assert queue_rows_1 == 1
    assert _n_lines(paths["outbox_path"]) == 1

    # Fire 2: still stale (same episode) -> RED again, but NO new queue row / ping.
    now2 = datetime(2026, 7, 11, 1, 15, tzinfo=UTC)
    r2 = tsm.run_sentinel(now_utc=now2, now_et=now2, **paths)
    assert r2["verdict"] == "RED"
    assert paths["queue_path"].read_text(encoding="utf-8").count("TWIN-ESCALATION") == 1
    assert _n_lines(paths["outbox_path"]) == 1

    # Fire 3: fresh tick lands -> GREEN, episode ends, flags reset. Full healthy
    # history (not just one row) since 80 min have elapsed -> LOW_UPTIME would
    # otherwise false-fire on a single-row fixture and mask what this step tests.
    now3 = datetime(2026, 7, 11, 1, 20, tzinfo=UTC)
    _write_full_uptime_history(paths["decisions_path"], now3)
    r3 = tsm.run_sentinel(now_utc=now3, now_et=now3, **paths)
    assert r3["verdict"] == "GREEN"
    assert r3["escalation"]["episode_active"] is False
    assert r3["escalation"]["ping_sent_this_episode"] is False

    # Fire 4: goes stale again (30 min after the fresh tick) -> a NEW episode -> re-arms,
    # exactly ONE additional queue row and ONE additional ping (total 2, not 1).
    now4 = datetime(2026, 7, 11, 1, 50, tzinfo=UTC)
    r4 = tsm.run_sentinel(now_utc=now4, now_et=now4, **paths)
    assert r4["verdict"] == "RED"
    assert paths["queue_path"].read_text(encoding="utf-8").count("TWIN-ESCALATION") == 2
    assert _n_lines(paths["outbox_path"]) == 2


def test_run_sentinel_green_never_touches_queue_or_outbox(tmp_path):
    paths = _run_paths(tmp_path)
    now = datetime(2026, 7, 11, 0, 10, tzinfo=UTC)
    _write_jsonl(paths["decisions_path"], [
        {"ts_utc": "2026-07-11T00:08:00+00:00", "session_date_utc": "2026-07-11", "action": "HOLD"},
    ])
    result = tsm.run_sentinel(now_utc=now, now_et=now, **paths)
    assert result["verdict"] == "GREEN"
    assert not paths["queue_path"].exists()
    assert not paths["outbox_path"].exists()


def test_run_sentinel_writes_sentinel_json_with_expected_top_level_keys(tmp_path):
    paths = _run_paths(tmp_path)
    now = datetime(2026, 7, 11, 0, 10, tzinfo=UTC)
    _write_jsonl(paths["decisions_path"], [
        {"ts_utc": "2026-07-11T00:08:00+00:00", "session_date_utc": "2026-07-11", "action": "HOLD"},
    ])
    tsm.run_sentinel(now_utc=now, now_et=now, **paths)
    on_disk = json.loads(paths["sentinel_path"].read_text(encoding="utf-8"))
    for key in ("verdict", "reasons", "checked_at_et", "facts", "escalation"):
        assert key in on_disk


def test_run_sentinel_persists_account_status_for_next_runs_regression_check(tmp_path):
    """End-to-end proof that run_sentinel's OWN state file is what makes
    ACCOUNT_REGRESSION detectable across fires (twin-health.json has no history)."""
    paths = _run_paths(tmp_path)
    now1 = datetime(2026, 7, 11, 0, 10, tzinfo=UTC)
    _write_jsonl(paths["decisions_path"], [
        {"ts_utc": "2026-07-11T00:08:00+00:00", "session_date_utc": "2026-07-11", "action": "HOLD"},
    ])
    _write_json(paths["health_path"], {"account_status": "LIVE", "breaker_tripped": False})
    r1 = tsm.run_sentinel(now_utc=now1, now_et=now1, **paths)
    assert r1["verdict"] == "GREEN"

    now2 = datetime(2026, 7, 11, 0, 15, tzinfo=UTC)
    _write_jsonl(paths["decisions_path"], [
        {"ts_utc": "2026-07-11T00:08:00+00:00", "session_date_utc": "2026-07-11", "action": "HOLD"},
        {"ts_utc": "2026-07-11T00:14:00+00:00", "session_date_utc": "2026-07-11", "action": "HOLD"},
    ])
    _write_json(paths["health_path"], {"account_status": "BLOCKED_NO_ACCOUNT", "breaker_tripped": False})
    r2 = tsm.run_sentinel(now_utc=now2, now_et=now2, **paths)
    assert r2["verdict"] == "RED"
    assert any(r.startswith("ACCOUNT_REGRESSION:") for r in r2["reasons"])


# ============================================================================
# Nightly review hook -- fires once after 23:30 UTC, never before, never twice
# ============================================================================
def _fake_review_module(monkeypatch, calls: dict):
    fake = types.ModuleType("twin_review")

    def _fake_run_review(*, now_utc=None, now_et=None):
        calls["n"] = calls.get("n", 0) + 1
        return {"mode": "LLM", "summary_line": "all quiet", "report_path": "x.md"}

    fake.run_review = _fake_run_review
    monkeypatch.setitem(sys.modules, "twin_review", fake)
    return fake


def test_review_not_triggered_before_2330_utc(tmp_path, monkeypatch):
    calls = {}
    _fake_review_module(monkeypatch, calls)
    paths = _run_paths(tmp_path)
    paths["run_review"] = True
    now = datetime(2026, 7, 11, 20, 0, tzinfo=UTC)
    _write_jsonl(paths["decisions_path"], [
        {"ts_utc": "2026-07-11T19:58:00+00:00", "session_date_utc": "2026-07-11", "action": "HOLD"},
    ])
    result = tsm.run_sentinel(now_utc=now, now_et=now, **paths)
    assert result["review_ran_this_fire"] is False
    assert calls.get("n", 0) == 0


def test_review_triggered_after_2330_utc(tmp_path, monkeypatch):
    calls = {}
    _fake_review_module(monkeypatch, calls)
    paths = _run_paths(tmp_path)
    paths["run_review"] = True
    now = datetime(2026, 7, 11, 23, 30, tzinfo=UTC)
    _write_jsonl(paths["decisions_path"], [
        {"ts_utc": "2026-07-11T23:28:00+00:00", "session_date_utc": "2026-07-11", "action": "HOLD"},
    ])
    result = tsm.run_sentinel(now_utc=now, now_et=now, **paths)
    assert result["review_ran_this_fire"] is True
    assert calls.get("n", 0) == 1
    assert result["last_review_note"]["date_utc"] == "2026-07-11"


def test_review_runs_only_once_per_utc_day(tmp_path, monkeypatch):
    calls = {}
    _fake_review_module(monkeypatch, calls)
    paths = _run_paths(tmp_path)
    paths["run_review"] = True
    _write_jsonl(paths["decisions_path"], [
        {"ts_utc": "2026-07-11T23:28:00+00:00", "session_date_utc": "2026-07-11", "action": "HOLD"},
    ])

    now1 = datetime(2026, 7, 11, 23, 30, tzinfo=UTC)
    tsm.run_sentinel(now_utc=now1, now_et=now1, **paths)
    assert calls.get("n", 0) == 1

    # A second fire 15 min later, same UTC day, past the trigger hour -- must NOT re-run.
    now2 = datetime(2026, 7, 11, 23, 45, tzinfo=UTC)
    result2 = tsm.run_sentinel(now_utc=now2, now_et=now2, **paths)
    assert result2["review_ran_this_fire"] is False
    assert calls.get("n", 0) == 1


def test_review_failure_is_caught_and_noted_never_breaks_sentinel(tmp_path, monkeypatch):
    fake = types.ModuleType("twin_review")

    def _boom(*, now_utc=None, now_et=None):
        raise RuntimeError("simulated LLM client crash")

    fake.run_review = _boom
    monkeypatch.setitem(sys.modules, "twin_review", fake)

    paths = _run_paths(tmp_path)
    paths["run_review"] = True
    now = datetime(2026, 7, 11, 23, 31, tzinfo=UTC)
    _write_full_uptime_history(paths["decisions_path"], now)
    result = tsm.run_sentinel(now_utc=now, now_et=now, **paths)
    assert result["review_ran_this_fire"] is False
    assert any("nightly review FAILED" in n for n in result["notes"])
    # sentinel's own verdict machinery must be unaffected by the review crash
    assert result["verdict"] == "GREEN"


# ============================================================================
# _load_user_mention / _send_discord_ping -- reused shared pattern
# ============================================================================
def test_load_user_mention_reads_config(tmp_path):
    cfg = tmp_path / ".discord-config.json"
    cfg.write_text('{"user_id": "12345"}', encoding="utf-8")
    assert tsm._load_user_mention(cfg) == "<@12345> "


def test_load_user_mention_fails_open_on_missing_config(tmp_path):
    assert tsm._load_user_mention(tmp_path / "missing.json") == ""


def test_send_discord_ping_writes_expected_schema(tmp_path):
    outbox = tmp_path / "discord-outbox.jsonl"
    tsm._send_discord_ping("hello", outbox_path=outbox, cfg_path=tmp_path / "missing.json")
    row = json.loads(outbox.read_text(encoding="utf-8").strip())
    assert row["content"] == "hello"
    assert row["source"] == "twin_sentinel"
    assert "queued_at" in row


# ============================================================================
# main() / _main_safe() -- orchestration contract, never touches real state
# ============================================================================
def test_main_calls_run_sentinel_and_prints_verdict(monkeypatch, capsys):
    fake_result = {
        "verdict": "GREEN", "reasons": [], "notes": [], "checked_at_et": "2026-07-11T00:00:00",
        "escalation": {"episode_active": False, "queue_row_written_this_episode": False,
                       "ping_sent_this_episode": False},
        "review_ran_this_fire": False, "last_review_note": None,
    }
    monkeypatch.setattr(tsm, "run_sentinel", lambda **kw: fake_result)
    assert tsm.main() == 0
    out = capsys.readouterr().out
    assert '"verdict": "GREEN"' in out


def test_main_always_returns_0_even_on_red(monkeypatch):
    fake_result = {
        "verdict": "RED", "reasons": ["TICK_GAP: x"], "notes": [], "checked_at_et": "t",
        "escalation": {"episode_active": True, "queue_row_written_this_episode": True,
                       "ping_sent_this_episode": True},
        "review_ran_this_fire": False, "last_review_note": None,
    }
    monkeypatch.setattr(tsm, "run_sentinel", lambda **kw: fake_result)
    assert tsm.main() == 0


def test_main_safe_never_raises(monkeypatch):
    def _boom(**kw):
        raise RuntimeError("simulated crash")
    monkeypatch.setattr(tsm, "run_sentinel", _boom)
    assert tsm._main_safe() == 0


def test_main_safe_propagates_is_provable_via_main_raising(monkeypatch):
    """Non-vacuous: proves main() really CAN raise (the guard isn't trivially a no-op)."""
    def _boom(**kw):
        raise RuntimeError("simulated crash")
    monkeypatch.setattr(tsm, "run_sentinel", _boom)
    with pytest.raises(RuntimeError):
        tsm.main()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
