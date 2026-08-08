"""Guard: setup/scripts/autonomy_report.py -- honest today/this-week autonomy scorecard.

Locks in: SHIP-event definition (items_drained>0 OR lessons_shipped>0); no-op reason
attribution priority (budget checked before error before nothing_ready); ET-calendar-date
bucketing for today/week from a UTC fired_at; the trailing-7-day week window is INCLUSIVE
of the as-of day; spend-by-hour is keyed by ET hour, not raw UTC hour; the verdict line is
never blank even on a fully-starved day or an entirely empty ledger; missing/garbled source
files degrade fail-open (empty lists / None sections) rather than crashing; --dry-run performs
zero disk writes; a real run writes valid JSON with every documented top-level key.

Every state-file read goes through a module-level Path constant (OUTCOMES_PATH, METRIC_PATH,
BUDGET_CONFIG_PATH, OUTPUT_PATH) so tests monkeypatch those onto a tmp_path fixture rather
than touching real repo state. "Now" is read through the single seam _current_utc(), which
every fixture-driven test monkeypatches directly -- no test here depends on the real clock.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in ("setup/scripts", ""):
    p = str(REPO / _p) if _p else str(REPO)
    if p not in sys.path:
        sys.path.insert(0, p)

import autonomy_report as ar  # noqa: E402


# ============================================================================
# Fixtures / helpers
# ============================================================================

def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _row(fired_at, task_id="TASK", cost=1.0, drained=0, lessons=0, note=""):
    return {
        "fired_at": fired_at,
        "task_id": task_id,
        "cost_usd": cost,
        "items_drained": drained,
        "lessons_shipped": lessons,
        "note": note,
    }


@pytest.fixture
def state_paths(tmp_path, monkeypatch):
    paths = {
        "outcomes": tmp_path / "conductor-outcomes.jsonl",
        "metric": tmp_path / "autonomy-metric.json",
        "budget_cfg": tmp_path / "conductor-budget.json",
        "output": tmp_path / "autonomy-report.json",
    }
    monkeypatch.setattr(ar, "OUTCOMES_PATH", paths["outcomes"])
    monkeypatch.setattr(ar, "METRIC_PATH", paths["metric"])
    monkeypatch.setattr(ar, "BUDGET_CONFIG_PATH", paths["budget_cfg"])
    monkeypatch.setattr(ar, "OUTPUT_PATH", paths["output"])
    return paths


def _freeze_now(monkeypatch, iso_utc: str):
    fixed = datetime.fromisoformat(iso_utc)
    if fixed.tzinfo is None:
        fixed = fixed.replace(tzinfo=timezone.utc)
    monkeypatch.setattr(ar, "_current_utc", lambda: fixed)


# ============================================================================
# is_ship_event
# ============================================================================

def test_is_ship_event_true_on_items_drained():
    assert ar.is_ship_event({"items_drained": 1, "lessons_shipped": 0}) is True


def test_is_ship_event_true_on_lessons_shipped():
    assert ar.is_ship_event({"items_drained": 0, "lessons_shipped": 1}) is True


def test_is_ship_event_false_when_both_zero():
    assert ar.is_ship_event({"items_drained": 0, "lessons_shipped": 0}) is False


def test_is_ship_event_false_when_keys_missing():
    assert ar.is_ship_event({}) is False


def test_is_ship_event_ignores_nonzero_cost_alone():
    """A fire can spend money without draining/shipping anything -- that's still
    a no-op by this script's explicit definition."""
    assert ar.is_ship_event({"cost_usd": 9.35, "items_drained": 0, "lessons_shipped": 0}) is False


def test_is_ship_event_tolerates_garbled_values():
    assert ar.is_ship_event({"items_drained": "not-a-number", "lessons_shipped": None}) is False


# ============================================================================
# classify_noop_reason -- priority order + real-ledger phrasing
# ============================================================================

def test_classify_budget_from_real_ledger_phrasing():
    row = {"task_id": "QUIET-BUDGET-EXHAUSTED", "note": "nightly budget gate EXHAUSTED"}
    assert ar.classify_noop_reason(row) == "budget_exhausted"


def test_classify_budget_from_task_id_only():
    row = {"task_id": "rail0-budget-exhausted-0530", "note": ""}
    assert ar.classify_noop_reason(row) == "budget_exhausted"


def test_classify_error_when_no_budget_marker():
    row = {"task_id": "SOMETHING", "note": "unhandled exception during fan-out"}
    assert ar.classify_noop_reason(row) == "error"


def test_classify_budget_wins_over_error_marker_in_same_note():
    """A budget-exhausted row whose note also says 'exit code 3' (which mentions
    neither error nor exception, but let's also prove the priority order directly
    with a note containing both an error word and 'budget')."""
    row = {"task_id": "X", "note": "budget gate exit, error code 3, zero work done"}
    assert ar.classify_noop_reason(row) == "budget_exhausted"


def test_classify_nothing_ready():
    row = {"task_id": "X", "note": "queue empty, nothing ready to pick"}
    assert ar.classify_noop_reason(row) == "nothing_ready"


def test_classify_other_fallback():
    row = {"task_id": "X", "note": "some unrelated benign note"}
    assert ar.classify_noop_reason(row) == "other"


def test_classify_case_insensitive():
    row = {"task_id": "X", "note": "BUDGET GATE EXHAUSTED"}
    assert ar.classify_noop_reason(row) == "budget_exhausted"


# ============================================================================
# load_outcomes -- fail-open jsonl reader
# ============================================================================

def test_load_outcomes_missing_file_is_empty(state_paths):
    assert ar.load_outcomes(state_paths["outcomes"]) == []


def test_load_outcomes_skips_malformed_lines_keeps_good_ones(state_paths):
    p = state_paths["outcomes"]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        '{"task_id": "A", "cost_usd": 1}\n'
        "not json at all\n"
        '{"task_id": "B", "cost_usd": 2}\n'
        "\n",
        encoding="utf-8",
    )
    rows = ar.load_outcomes(p)
    assert [r["task_id"] for r in rows] == ["A", "B"]


def test_load_outcomes_skips_non_dict_json_lines(state_paths):
    p = state_paths["outcomes"]
    p.write_text('[1,2,3]\n{"task_id": "ok"}\n', encoding="utf-8")
    rows = ar.load_outcomes(p)
    assert rows == [{"task_id": "ok"}]


# ============================================================================
# load_budget_config -- fail-open + partial override
# ============================================================================

def test_load_budget_config_missing_file_uses_defaults(state_paths):
    cfg = ar.load_budget_config(state_paths["budget_cfg"])
    assert cfg == ar._BUDGET_DEFAULTS


def test_load_budget_config_partial_override(state_paths):
    _write_json(state_paths["budget_cfg"], {"daily_cap_usd": 15.0})
    cfg = ar.load_budget_config(state_paths["budget_cfg"])
    assert cfg["daily_cap_usd"] == 15.0
    assert cfg["max_fires"] == ar._BUDGET_DEFAULTS["max_fires"]


def test_load_budget_config_garbled_file_falls_back_to_defaults(state_paths):
    state_paths["budget_cfg"].parent.mkdir(parents=True, exist_ok=True)
    state_paths["budget_cfg"].write_text("{not valid json", encoding="utf-8")
    assert ar.load_budget_config(state_paths["budget_cfg"]) == ar._BUDGET_DEFAULTS


# ============================================================================
# ET date bucketing -- the DST/offset-correctness seam
# ============================================================================

def test_parse_fired_at_et_converts_utc_to_et_calendar_date():
    # 2026-08-08T04:08:40+00:00 is EDT (UTC-4) -> 2026-08-08 00:08 ET, same day.
    et_dt = ar._parse_fired_at_et("2026-08-08T04:08:40+00:00")
    assert et_dt.strftime("%Y-%m-%d") == "2026-08-08"
    assert et_dt.hour == 0


def test_parse_fired_at_et_late_evening_fire_rolls_to_next_utc_day():
    # 2026-08-08T02:00:00+00:00 UTC is 2026-08-07 22:00 ET (EDT) -- the exact
    # "evening fire's UTC date is already tomorrow" case conductor_budget.py
    # documents. The ET calendar date must be the PRIOR day, not the UTC one.
    et_dt = ar._parse_fired_at_et("2026-08-08T02:00:00+00:00")
    assert et_dt.strftime("%Y-%m-%d") == "2026-08-07"
    assert et_dt.hour == 22


def test_parse_fired_at_et_missing_or_garbled_is_none():
    assert ar._parse_fired_at_et(None) is None
    assert ar._parse_fired_at_et("") is None
    assert ar._parse_fired_at_et("not-a-timestamp") is None
    assert ar._parse_fired_at_et(12345) is None


def test_rows_on_date_filters_by_et_date():
    rows = [
        {"fired_at": "2026-08-08T04:08:40+00:00"},  # ET 08-08
        {"fired_at": "2026-08-08T02:00:00+00:00"},  # ET 08-07
        {"fired_at": "2026-08-07T12:00:00+00:00"},  # ET 08-07
    ]
    assert len(ar.rows_on_date(rows, "2026-08-08")) == 1
    assert len(ar.rows_on_date(rows, "2026-08-07")) == 2


def test_rows_on_date_excludes_unparseable_fired_at():
    rows = [{"fired_at": "garbage"}, {"fired_at": "2026-08-08T04:08:40+00:00"}]
    assert len(ar.rows_on_date(rows, "2026-08-08")) == 1


def test_rows_in_week_is_inclusive_seven_day_window():
    # end_day 2026-08-08 -> window is 2026-08-02..2026-08-08 inclusive (7 days).
    rows = [
        {"fired_at": "2026-08-02T12:00:00+00:00"},  # in window (edge)
        {"fired_at": "2026-08-08T12:00:00+00:00"},  # in window (edge)
        {"fired_at": "2026-08-01T12:00:00+00:00"},  # OUT (8 days back)
    ]
    week_rows = ar.rows_in_week(rows, "2026-08-08")
    assert len(week_rows) == 2


# ============================================================================
# summarize_rows / build_verdict
# ============================================================================

def test_summarize_rows_counts_ship_vs_noop_and_reasons():
    rows = [
        _row("2026-08-08T10:00:00+00:00", "SHIP-1", drained=1),
        _row("2026-08-08T11:00:00+00:00", "SHIP-2", lessons=1),
        _row("2026-08-08T12:00:00+00:00", "BUDGET-GATE-QUIET", note="budget gate exhausted"),
        _row("2026-08-08T13:00:00+00:00", "BUDGET-GATE-QUIET-2", note="budget gate exhausted"),
        _row("2026-08-08T14:00:00+00:00", "ERR-1", note="unhandled exception"),
        _row("2026-08-08T15:00:00+00:00", "IDLE-1", note="queue empty, nothing ready"),
    ]
    summary = ar.summarize_rows(rows)
    assert summary["total_fires"] == 6
    assert summary["ship_fires"] == 2
    assert summary["noop_fires"] == 4
    assert summary["noop_reasons"] == {
        "budget_exhausted": 2, "nothing_ready": 1, "error": 1, "other": 0,
    }
    assert summary["ship_task_ids"] == ["SHIP-1", "SHIP-2"]


def test_summarize_rows_empty_list():
    summary = ar.summarize_rows([])
    assert summary["total_fires"] == 0
    assert summary["ship_fires"] == 0
    assert summary["noop_reasons"] == {"budget_exhausted": 0, "nothing_ready": 0, "error": 0, "other": 0}


def test_build_verdict_matches_spec_example_format():
    summary = {"total_fires": 12, "ship_fires": 4, "noop_reasons": {"budget_exhausted": 6}}
    assert ar.build_verdict(summary, "today") == "Drove 4 of 12 fire slots today; 6 were budget-starved."


def test_build_verdict_no_budget_starved_omits_that_clause():
    summary = {"total_fires": 5, "ship_fires": 5, "noop_reasons": {"budget_exhausted": 0}}
    assert ar.build_verdict(summary, "today") == "Drove 5 of 5 fire slots today."


def test_build_verdict_fully_starved_day_is_honest_not_blank():
    summary = {"total_fires": 6, "ship_fires": 0, "noop_reasons": {"budget_exhausted": 6}}
    out = ar.build_verdict(summary, "today")
    assert out == "Drove 0 of 6 fire slots today; 6 were budget-starved."
    assert out.strip() != ""


def test_build_verdict_zero_fires_is_honest_not_blank():
    summary = {"total_fires": 0, "ship_fires": 0, "noop_reasons": {"budget_exhausted": 0}}
    out = ar.build_verdict(summary, "today")
    assert out == "No conductor fires recorded today -- nothing to report."
    assert out.strip() != ""


def test_build_verdict_singular_slot_wording():
    summary = {"total_fires": 1, "ship_fires": 1, "noop_reasons": {"budget_exhausted": 0}}
    assert ar.build_verdict(summary, "today") == "Drove 1 of 1 fire slot today."


# ============================================================================
# spend_by_hour_et
# ============================================================================

def test_spend_by_hour_et_buckets_by_et_hour_not_utc():
    rows = [
        _row("2026-08-08T04:08:40+00:00", cost=2.3),  # ET 00:08 -> hour 00
        _row("2026-08-08T05:32:02+00:00", cost=9.35),  # ET 01:32 -> hour 01
        _row("2026-08-08T06:07:17+00:00", cost=2.8),  # ET 02:07 -> hour 02
    ]
    shape = ar.spend_by_hour_et(rows)
    assert shape == {"00": 2.3, "01": 9.35, "02": 2.8}


def test_spend_by_hour_et_sums_multiple_fires_same_hour():
    rows = [
        _row("2026-08-08T04:00:00+00:00", cost=1.0),
        _row("2026-08-08T04:30:00+00:00", cost=2.5),
    ]
    assert ar.spend_by_hour_et(rows) == {"00": 3.5}


def test_spend_by_hour_et_missing_cost_counts_as_zero():
    rows = [{"fired_at": "2026-08-08T04:08:40+00:00"}]
    assert ar.spend_by_hour_et(rows) == {"00": 0.0}


def test_spend_by_hour_et_skips_unparseable_timestamps():
    rows = [{"fired_at": "garbage", "cost_usd": 5.0}]
    assert ar.spend_by_hour_et(rows) == {}


def test_spend_by_hour_et_empty_rows_is_empty_dict():
    assert ar.spend_by_hour_et([]) == {}


# ============================================================================
# compute_report -- full integration
# ============================================================================

def test_compute_report_full_fixture_shapes_every_section():
    rows = [
        _row("2026-08-08T14:00:00+00:00", "SHIP-1", cost=3.0, drained=1),
        _row("2026-08-08T16:00:00+00:00", "BUDGET-1", cost=0.0, note="budget gate exhausted"),
        _row("2026-08-08T18:00:00+00:00", "BUDGET-2", cost=0.0, note="budget gate exhausted"),
        _row("2026-08-01T14:00:00+00:00", "OLD", cost=1.0, drained=1),  # outside the 7-day week
    ]
    budget_cfg = {"daily_cap_usd": 30.0, "max_fires": 4, "enabled": True}
    metric_doc = {"trend": "regressing", "net_improvement": 77, "total_cost_usd": 52.89}

    report = ar.compute_report(rows, metric_doc, budget_cfg, "2026-08-08")

    assert report["today"]["date"] == "2026-08-08"
    assert report["today"]["total_fires"] == 3
    assert report["today"]["ship_fires"] == 1
    assert report["today"]["verdict"] == "Drove 1 of 3 fire slots today; 2 were budget-starved."

    assert report["week"]["start_date"] == "2026-08-02"
    assert report["week"]["end_date"] == "2026-08-08"
    assert report["week"]["total_fires"] == 3  # OLD row (08-01) falls outside the window

    assert report["budget_shape"]["daily_cap_usd"] == 30.0
    assert report["budget_shape"]["max_fires_per_day_cap"] == 4
    # slots_used_today counts ALL fires (3 total: 1 ship + 2 no-op), not just ship events --
    # matches conductor_budget.py's own accounting (every fire counts against max_fires).
    assert report["budget_shape"]["slots_used_today"] == 3
    assert report["budget_shape"]["slots_available_today"] == 1  # 4 - 3
    assert "10" in report["budget_shape"]["spend_by_hour_et"]  # 14:00 UTC -> 10:00 ET (EDT)

    assert report["autonomy_metric"] == metric_doc
    assert report["verdict"] == report["today"]["verdict"]


# ============================================================================
# build_budget_shape -- slots_used/slots_available must reflect budget-SLOT
# consumption (every fire, ship or no-op), never a ship count. Guards the
# 2026-08-08 audit finding: the old code keyed slots_used_today off
# ship_fires_today and echoed max_fires verbatim as slots_available_today
# regardless of usage.
# ============================================================================

def test_build_budget_shape_slots_used_counts_every_fire_not_just_ships():
    """Reproduces the exact incident shape the audit quoted: 11 total conductor-family
    fires today, only 3 of them ship events, max_fires=4 -- a day fully exhausted
    2.75x over. slots_used_today must read 11 (matching conductor_budget.py's own
    accounting, which counts every fire against max_fires), never 3."""
    rows_today = [_row(f"2026-08-08T{h:02d}:00:00+00:00", f"T{i}",
                        drained=(1 if i < 3 else 0))
                  for i, h in enumerate(range(11))]
    shape = ar.build_budget_shape(rows_today, {"daily_cap_usd": 30.0, "max_fires": 4},
                                   total_fires_today=11)
    assert shape["slots_used_today"] == 11, (
        "must count ALL fires, not the ship subset -- a reader trusting the field name "
        "must not be told the day still has room when it is 2.75x over max_fires")
    assert shape["slots_available_today"] == 0, "clamped at 0, never negative"


def test_build_budget_shape_slots_available_decreases_as_slots_are_used():
    rows_today = [_row("2026-08-08T14:00:00+00:00", "T1", drained=1)]
    shape = ar.build_budget_shape(rows_today, {"daily_cap_usd": 30.0, "max_fires": 4},
                                   total_fires_today=1)
    assert shape["slots_used_today"] == 1
    assert shape["slots_available_today"] == 3, "3 of 4 nominal slots still open"


def test_build_budget_shape_slots_available_never_negative_when_over_cap():
    shape = ar.build_budget_shape([], {"daily_cap_usd": 30.0, "max_fires": 4},
                                   total_fires_today=7)
    assert shape["slots_available_today"] == 0


def test_compute_report_budget_shape_keys_off_total_fires_end_to_end():
    """End-to-end: compute_report must pass total_fires (not ship_fires) into
    build_budget_shape -- pins the call-site fix, not just the function's own logic."""
    rows = [
        _row("2026-08-08T14:00:00+00:00", "SHIP-1", cost=3.0, drained=1),
        _row("2026-08-08T15:00:00+00:00", "NOOP-1", cost=0.0, note="nothing ready"),
        _row("2026-08-08T16:00:00+00:00", "NOOP-2", cost=0.0, note="nothing ready"),
        _row("2026-08-08T17:00:00+00:00", "NOOP-3", cost=0.0, note="nothing ready"),
    ]
    budget_cfg = {"daily_cap_usd": 30.0, "max_fires": 4}
    report = ar.compute_report(rows, None, budget_cfg, "2026-08-08")
    assert report["today"]["total_fires"] == 4
    assert report["today"]["ship_fires"] == 1
    assert report["budget_shape"]["slots_used_today"] == 4, (
        "must equal total_fires (4), not ship_fires (1)")
    assert report["budget_shape"]["slots_available_today"] == 0


def test_compute_report_empty_ledger_is_honest_not_blank():
    report = ar.compute_report([], None, dict(ar._BUDGET_DEFAULTS), "2026-08-08")
    assert report["today"]["verdict"] == "No conductor fires recorded today -- nothing to report."
    assert report["week"]["verdict"] == "No conductor fires recorded this week -- nothing to report."
    assert report["autonomy_metric"] is None
    assert report["verdict"] != ""


# ============================================================================
# main() -- CLI, dry-run, real-run, fail-open end to end
# ============================================================================

def test_dry_run_writes_nothing(state_paths, monkeypatch):
    _freeze_now(monkeypatch, "2026-08-08T20:00:00+00:00")
    rc = ar.main(["--dry-run"])
    assert rc == 0
    assert not state_paths["output"].exists()


def test_real_run_writes_valid_json_with_all_top_level_keys(state_paths, monkeypatch):
    _freeze_now(monkeypatch, "2026-08-08T20:00:00+00:00")
    _write_jsonl(state_paths["outcomes"], [
        _row("2026-08-08T14:00:00+00:00", "SHIP-1", drained=1),
        _row("2026-08-08T18:00:00+00:00", "BUDGET-1", note="budget gate exhausted"),
    ])
    rc = ar.main([])
    assert rc == 0
    assert state_paths["output"].exists()
    data = json.loads(state_paths["output"].read_text(encoding="utf-8"))
    assert {"computed_at", "today", "week", "budget_shape", "autonomy_metric", "verdict"} <= set(data.keys())
    assert data["verdict"] == "Drove 1 of 2 fire slots today; 1 were budget-starved."


def test_real_run_missing_all_source_files_still_writes_honest_report(state_paths, monkeypatch):
    """The named fully-starved-fixture requirement, at the main()/CLI level: no
    outcomes file, no metric file, no budget config file at all -- report must
    still be written with an honest (non-blank, non-crashing) verdict."""
    _freeze_now(monkeypatch, "2026-08-08T20:00:00+00:00")
    rc = ar.main([])
    assert rc == 0
    data = json.loads(state_paths["output"].read_text(encoding="utf-8"))
    assert data["today"]["verdict"] == "No conductor fires recorded today -- nothing to report."
    assert data["autonomy_metric"] is None
    assert data["budget_shape"]["daily_cap_usd"] == ar._BUDGET_DEFAULTS["daily_cap_usd"]


def test_real_run_fully_starved_day_end_to_end(state_paths, monkeypatch):
    """Every fire today is a budget no-op -- the day-was-fully-starved fixture,
    at full main()-level integration. Verdict must name the starve count, not
    just say something generically quiet."""
    _freeze_now(monkeypatch, "2026-08-08T22:00:00+00:00")
    _write_jsonl(state_paths["outcomes"], [
        _row("2026-08-08T04:08:40+00:00", "QUIET-1", note="rail-0 budget gate EXHAUSTED"),
        _row("2026-08-08T08:01:06+00:00", "QUIET-2", note="rail-0 budget gate EXHAUSTED"),
        _row("2026-08-08T10:00:53+00:00", "QUIET-3", note="rail-0 budget gate EXHAUSTED"),
    ])
    rc = ar.main([])
    assert rc == 0
    data = json.loads(state_paths["output"].read_text(encoding="utf-8"))
    assert data["today"]["ship_fires"] == 0
    assert data["today"]["noop_reasons"]["budget_exhausted"] == 3
    assert data["today"]["verdict"] == "Drove 0 of 3 fire slots today; 3 were budget-starved."
    assert data["verdict"] == data["today"]["verdict"]


def test_write_report_is_atomic_tmp_then_replace(state_paths):
    ar.write_report({"a": 1}, state_paths["output"])
    assert state_paths["output"].exists()
    assert not state_paths["output"].with_suffix(".json.tmp").exists()
    assert json.loads(state_paths["output"].read_text(encoding="utf-8")) == {"a": 1}
