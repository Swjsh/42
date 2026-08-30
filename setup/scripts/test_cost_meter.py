"""Tests for gamma_cost_meter.py -- the LIVE COST METER.

Covers exactly what the delivery brief called out as load-bearing:
  * an empty ledger (file exists, readable, zero rows) reads as a verified zero
  * malformed rows (bad JSON, non-dict, bad cost_usd) are skipped, never fatal
  * the unknown-not-zero rule: a MISSING/unreadable source forces usd=None,
    known=False -- it must never come back looking like a verified $0
  * day / trailing-7-day windowing (trailing_et_dates, partial vs full
    aggregation, the companion feed's prune-boundary coverage rule)

Run: backtest/.venv/Scripts/python.exe -m pytest setup/scripts/test_cost_meter.py -q
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

# Direct import (script lives in setup/scripts, not a package) -- same pattern
# as the other setup/scripts/test_*.py files in this repo (see test_cockpit_context.py).
_spec = importlib.util.spec_from_file_location(
    "gamma_cost_meter",
    Path(__file__).parent / "gamma_cost_meter.py",
)
cm = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(cm)  # type: ignore[union-attr]


# --------------------------------------------------------------- _fig helper

def test_fig_unknown_forces_usd_and_known_false_even_if_a_value_was_passed():
    """The core honesty invariant: coverage="unknown" must WIN over any usd
    value a caller passes in -- a bug that "forgets" to null it out cannot
    silently produce a fake number."""
    f = cm._fig(123.45, "unknown", "some method")
    assert f["usd"] is None
    assert f["known"] is False
    assert f["coverage"] == "unknown"


def test_fig_full_reports_the_value_and_known_true():
    f = cm._fig(12.5, "full", "some method")
    assert f["usd"] == 12.5
    assert f["known"] is True
    assert f["coverage"] == "full"


def test_fig_partial_reports_value_but_known_false():
    f = cm._fig(3.0, "partial", "sum", note="2/7 days known")
    assert f["usd"] == 3.0
    assert f["known"] is False
    assert f["coverage"] == "partial"
    assert "2/7" in f["note"]


def test_fig_zero_is_a_real_value_not_treated_as_missing():
    """0.0 must still round-trip when coverage is full -- a verified zero is a
    real, displayable number, not something the None-collapsing logic eats."""
    f = cm._fig(0.0, "full", "method")
    assert f["usd"] == 0.0
    assert f["known"] is True


def test_fig_rejects_bad_coverage_value():
    with pytest.raises(ValueError):
        cm._fig(1.0, "sort-of", "method")


# ------------------------------------------------------------- date windowing

def test_trailing_et_dates_is_seven_days_newest_first():
    dates = cm.trailing_et_dates("2026-08-29", 7)
    assert dates == [
        "2026-08-29", "2026-08-28", "2026-08-27", "2026-08-26",
        "2026-08-25", "2026-08-24", "2026-08-23",
    ]


def test_trailing_et_dates_crosses_month_boundary():
    dates = cm.trailing_et_dates("2026-09-02", 5)
    assert dates == ["2026-09-02", "2026-09-01", "2026-08-31", "2026-08-30", "2026-08-29"]


def test_trailing_et_dates_respects_n():
    assert cm.trailing_et_dates("2026-08-29", 1) == ["2026-08-29"]
    assert len(cm.trailing_et_dates("2026-08-29", 3)) == 3


# --------------------------------------------------------- conductor_by_day

DATES7 = cm.trailing_et_dates("2026-08-29", 7)


def _write_conductor_outcomes(tmp_path: Path, lines: list) -> Path:
    p = tmp_path / "conductor-outcomes.jsonl"
    p.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return p


def test_conductor_missing_file_is_unknown_not_zero():
    missing = Path("/definitely/does/not/exist/conductor-outcomes.jsonl")
    per_day, err = cm.conductor_by_day(DATES7, path=missing)
    assert per_day is None
    assert err is not None
    assert "not found" in err


def test_conductor_empty_ledger_is_a_verified_zero(tmp_path):
    """File exists, readable, zero rows -- this IS measured knowledge (the
    ledger was actually read), so it must come back as a real 0.0, not None."""
    p = _write_conductor_outcomes(tmp_path, [])
    per_day, err = cm.conductor_by_day(DATES7, path=p)
    assert err is None
    for d in DATES7:
        assert per_day[d]["raw_usd"] == 0.0
        assert per_day[d]["fires"] == 0
        # corrected_usd is still computable (0 * correction == 0) -- a real
        # zero, not a None standing in for "we don't know".
        assert per_day[d]["corrected_usd"] == 0.0


def test_conductor_malformed_rows_are_skipped_not_fatal(tmp_path):
    day = DATES7[0]
    lines = [
        "not even json {{{",
        json.dumps("a bare string, not a dict"),
        json.dumps({"fired_at": "%sT16:00:00+00:00" % day, "cost_usd": "not-a-number"}),
        json.dumps({"fired_at": "%sT16:00:00+00:00" % day, "cost_usd": 2.5}),
        "",  # blank line
    ]
    p = _write_conductor_outcomes(tmp_path, lines)
    per_day, err = cm.conductor_by_day(DATES7, path=p)
    assert err is None
    # only the one well-formed $2.50 row should have landed
    assert per_day[day]["raw_usd"] == 2.5
    assert per_day[day]["fires"] == 1


def test_conductor_correction_factor_is_applied_and_imported_not_hardcoded():
    """The correction constant must come FROM conductor_budget.py, the real
    governor -- this pins that the import actually happened."""
    assert cm._CONDUCTOR_CORRECTION is not None
    assert cm._CONDUCTOR_CORRECTION > 1.0
    if cm._cbud is not None:
        assert cm._CONDUCTOR_CORRECTION == cm._cbud.SELF_REPORT_CORRECTION


def test_conductor_correction_applied_to_the_sum(tmp_path):
    day = DATES7[0]
    p = _write_conductor_outcomes(tmp_path, [
        json.dumps({"fired_at": "%sT16:00:00+00:00" % day, "cost_usd": 10.0}),
    ])
    per_day, err = cm.conductor_by_day(DATES7, path=p, correction=2.0)
    assert err is None
    assert per_day[day]["raw_usd"] == 10.0
    assert per_day[day]["corrected_usd"] == 20.0


def test_conductor_by_day_none_correction_arg_means_use_the_real_constant(tmp_path):
    """None is the 'not overridden' sentinel for the `correction` kwarg (same
    convention path/None already uses) -- passing it falls through to the
    real, imported SELF_REPORT_CORRECTION, not to 'no correction'."""
    day = DATES7[0]
    p = _write_conductor_outcomes(tmp_path, [
        json.dumps({"fired_at": "%sT16:00:00+00:00" % day, "cost_usd": 10.0}),
    ])
    per_day, err = cm.conductor_by_day(DATES7, path=p, correction=None)
    assert err is None
    assert per_day[day]["raw_usd"] == 10.0
    assert per_day[day]["corrected_usd"] == pytest.approx(10.0 * cm._CONDUCTOR_CORRECTION)


def test_day_report_conductor_unknown_when_correction_constant_unavailable(monkeypatch, tmp_path):
    """Simulates the real 'conductor_budget.py import failed' path at the
    _day_report level: with the module-level correction constant unset, the
    conductor figure must degrade to unknown (never fall back to an
    uncorrected self-report, which is known to under-count)."""
    monkeypatch.setattr(cm, "_CONDUCTOR_CORRECTION", None)
    day = DATES7[0]
    cmg = {day: {"claude_usd": 5.0, "minimax_usd": 0.0, "groq_usd": 0.0, "claude_sessions": 1}}
    cond = {day: {"raw_usd": 3.0, "fires": 1, "corrected_usd": None}}
    comp = {day: {"known": True, "card_fire": {"usd": 0.0, "asks": 0},
                  "chat": {"usd": 0.0, "asks": 0}, "companion_other": {"usd": 0.0, "asks": 0}}}
    rec = cm._day_report(day, cmg, cond, comp)
    assert rec["by_origin"]["conductor"]["usd"] is None
    assert rec["by_origin"]["conductor"]["known"] is False


# --------------------------------------------------------- companion feed / origin

def _feed_file(tmp_path: Path, ask_id: str, ts: str, cost, extra_lines=None) -> None:
    p = tmp_path / ("%s.jsonl" % ask_id)
    lines = list(extra_lines or [])
    rec = {"t": ts, "step": "result", "ok": True, "subtype": "success"}
    if cost is not None:
        rec["cost"] = cost
    lines.append(json.dumps(rec))
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_companion_feed_scan_missing_dir_is_unknown(tmp_path):
    records, err = cm.companion_feed_scan(feed_dir=tmp_path / "nope")
    assert records is None
    assert err is not None


def test_companion_feed_scan_empty_dir_is_a_verified_empty_list(tmp_path):
    records, err = cm.companion_feed_scan(feed_dir=tmp_path)
    assert err is None
    assert records == []


def test_companion_feed_scan_skips_malformed_files_and_missing_result_step(tmp_path):
    (tmp_path / "ask-bad.jsonl").write_text("not json at all\n{{{\n", encoding="utf-8")
    (tmp_path / "ask-noresult.jsonl").write_text(
        json.dumps({"t": "2026-08-29T16:00:00.000Z", "step": "delta", "text": "hi"}) + "\n",
        encoding="utf-8")
    (tmp_path / "ask-good.jsonl").write_text(
        json.dumps({"t": "2026-08-29T16:00:00.000Z", "step": "result", "cost": 1.5}) + "\n",
        encoding="utf-8")
    records, err = cm.companion_feed_scan(feed_dir=tmp_path)
    assert err is None
    ids = {r["id"]: r for r in records}
    assert "ask-bad" not in ids           # malformed file contributes nothing, doesn't crash
    assert "ask-noresult" not in ids      # no result frame -> not a record at all
    assert ids["ask-good"]["cost_usd"] == 1.5


def test_companion_feed_scan_dates_by_et_not_utc(tmp_path):
    """A UTC stamp just after midnight (e.g. 02:00 UTC) is still the PREVIOUS
    ET calendar day -- the feed must bucket consistently with conductor/claude
    figures, which both go through the same ET conversion."""
    (tmp_path / "ask-latenight.jsonl").write_text(
        json.dumps({"t": "2026-08-29T02:00:00.000Z", "step": "result", "cost": 1.0}) + "\n",
        encoding="utf-8")
    records, err = cm.companion_feed_scan(feed_dir=tmp_path)
    assert err is None
    assert records[0]["date"] == "2026-08-28"  # EDT = UTC-4 -> previous ET day


def test_companion_origin_index_missing_file(tmp_path):
    idx, err = cm.companion_origin_index(results_path=tmp_path / "nope.jsonl")
    assert idx is None
    assert err is not None


def test_companion_origin_index_skips_rows_missing_id_or_origin(tmp_path):
    p = tmp_path / "results.jsonl"
    p.write_text("\n".join([
        "garbage {{{",
        json.dumps({"id": "a", "origin": "card"}),
        json.dumps({"id": "b"}),                 # no origin -> skipped
        json.dumps({"origin": "chat"}),           # no id -> skipped
        json.dumps({"id": "c", "origin": "chat"}),
    ]) + "\n", encoding="utf-8")
    idx, err = cm.companion_origin_index(results_path=p)
    assert err is None
    assert idx == {"a": "card", "c": "chat"}


def test_companion_by_day_splits_card_chat_and_unattributed(tmp_path):
    feed_dir = tmp_path / "feed"
    feed_dir.mkdir()
    day = DATES7[0]
    ts = "%sT16:00:00.000Z" % day  # noon ET, unambiguous day
    _feed_file(feed_dir, "ask-card", ts, 1.0)
    _feed_file(feed_dir, "ask-chat", ts, 2.0)
    _feed_file(feed_dir, "ask-nomatch", ts, 3.0)

    results_path = tmp_path / "results.jsonl"
    results_path.write_text("\n".join([
        json.dumps({"id": "ask-card", "origin": "card"}),
        json.dumps({"id": "ask-chat", "origin": "chat"}),
        # ask-nomatch deliberately has no row here
    ]) + "\n", encoding="utf-8")

    per_day, err, coverage = cm.companion_by_day(
        DATES7, feed_dir=feed_dir, results_path=results_path, prune_keep=50)
    assert err is None
    rec = per_day[day]
    assert rec["known"] is True
    assert rec["card_fire"]["usd"] == 1.0
    assert rec["chat"]["usd"] == 2.0
    assert rec["companion_other"]["usd"] == 3.0
    assert coverage["origin_index_available"] is True


def test_companion_by_day_under_prune_cap_is_full_coverage_even_for_zero_days(tmp_path):
    """Fewer files than the prune cap -> nothing has ever been pruned -> every
    requested date is a verified (possibly zero) figure, not unknown."""
    feed_dir = tmp_path / "feed"
    feed_dir.mkdir()
    # Only one ask, for the newest date -- older dates in the window have zero
    # records but must still read as KNOWN (full history is present).
    ts = "%sT16:00:00.000Z" % DATES7[0]
    _feed_file(feed_dir, "ask-1", ts, 5.0)
    per_day, err, coverage = cm.companion_by_day(DATES7, feed_dir=feed_dir, prune_keep=50)
    assert err is None
    assert coverage["at_prune_cap"] is False
    for d in DATES7:
        assert per_day[d]["known"] is True


def test_companion_by_day_at_prune_cap_marks_days_before_oldest_retained_unknown(tmp_path):
    feed_dir = tmp_path / "feed"
    feed_dir.mkdir()
    newest_day = DATES7[0]
    older_day = DATES7[5]
    # Fill the dir to the (tiny, test-scale) prune cap entirely with newest-day asks,
    # so the oldest retained date is newest_day itself -- anything older is unknown.
    for i in range(3):
        _feed_file(feed_dir, "ask-new-%d" % i, "%sT16:00:00.000Z" % newest_day, 1.0)
    per_day, err, coverage = cm.companion_by_day(DATES7, feed_dir=feed_dir, prune_keep=3)
    assert err is None
    assert coverage["at_prune_cap"] is True
    assert per_day[newest_day]["known"] is True
    assert per_day[older_day]["known"] is False  # zero records, but UNKNOWN not zero


def test_companion_by_day_missing_origin_index_falls_back_to_unattributed(tmp_path):
    """When the results ledger can't be read at all, every priced ask still
    lands in companion_other (priced, just not split) -- the join degrades
    gracefully rather than losing the cost entirely."""
    feed_dir = tmp_path / "feed"
    feed_dir.mkdir()
    ts = "%sT16:00:00.000Z" % DATES7[0]
    _feed_file(feed_dir, "ask-1", ts, 7.0)
    per_day, err, coverage = cm.companion_by_day(
        DATES7, feed_dir=feed_dir, results_path=tmp_path / "nope.jsonl", prune_keep=50)
    assert err is None
    assert coverage["origin_index_available"] is False
    assert per_day[DATES7[0]]["companion_other"]["usd"] == 7.0
    assert per_day[DATES7[0]]["card_fire"]["usd"] == 0.0
    assert per_day[DATES7[0]]["chat"]["usd"] == 0.0


# ------------------------------------------------------------------- _agg

def test_agg_all_unknown_reports_none_not_zero():
    days = {
        "d1": {"x": cm._fig(None, "unknown", "m")},
        "d2": {"x": cm._fig(None, "unknown", "m")},
    }
    f = cm._agg(days, lambda r: r["x"], "sum")
    assert f["usd"] is None
    assert f["known"] is False
    assert f["coverage"] == "unknown"


def test_agg_all_known_reports_full_sum():
    days = {
        "d1": {"x": cm._fig(1.0, "full", "m")},
        "d2": {"x": cm._fig(2.5, "full", "m")},
    }
    f = cm._agg(days, lambda r: r["x"], "sum")
    assert f["usd"] == 3.5
    assert f["known"] is True
    assert f["coverage"] == "full"


def test_agg_mixed_known_and_unknown_is_partial_with_visible_sum():
    days = {
        "d1": {"x": cm._fig(1.0, "full", "m")},
        "d2": {"x": cm._fig(None, "unknown", "m")},
        "d3": {"x": cm._fig(4.0, "full", "m")},
    }
    f = cm._agg(days, lambda r: r["x"], "sum")
    assert f["usd"] == 5.0          # partial sum still shown -- useful, not hidden
    assert f["known"] is False      # but never claimed as the full window
    assert f["coverage"] == "partial"
    assert "2/3" in f["note"]


# ------------------------------------------------------- claude/minimax/groq scan

def test_claude_minimax_groq_missing_project_dir_is_unknown(monkeypatch, tmp_path):
    monkeypatch.setattr(cm._spend, "CC_PROJECT_DIR", tmp_path / "does-not-exist")
    out, err = cm.claude_minimax_groq_by_day(DATES7)
    assert out == {}
    assert err is not None


# ------------------------------------------------------------------- residual

def test_residual_unknown_when_claude_total_unknown():
    claude_fig = cm._fig(None, "unknown", "m")
    zero = cm._fig(0.0, "full", "m")
    r = cm._residual_fig(claude_fig, zero, zero, zero, zero)
    assert r["usd"] is None
    assert r["known"] is False


def test_residual_unknown_when_an_origin_unknown_even_if_claude_known():
    claude_fig = cm._fig(100.0, "full", "m")
    known_zero = cm._fig(0.0, "full", "m")
    unknown = cm._fig(None, "unknown", "m")
    r = cm._residual_fig(claude_fig, known_zero, known_zero, known_zero, unknown)
    assert r["usd"] is None
    assert r["known"] is False
    assert "unknown" in r["note"]


def test_residual_full_when_everything_known():
    claude_fig = cm._fig(100.0, "full", "m")
    ten = cm._fig(10.0, "full", "m")
    r = cm._residual_fig(claude_fig, ten, ten, ten, ten)
    assert r["known"] is True
    assert r["usd"] == pytest.approx(60.0)


def test_residual_negative_is_flagged_not_hidden():
    claude_fig = cm._fig(10.0, "full", "m")
    big = cm._fig(50.0, "full", "m")
    zero = cm._fig(0.0, "full", "m")
    r = cm._residual_fig(claude_fig, big, zero, zero, zero)
    assert r["known"] is True
    assert r["usd"] < 0
    assert "negative" in r["note"]


# --------------------------------------------------------------- build_report

def test_build_report_shape_and_today_key(monkeypatch, tmp_path):
    """End-to-end smoke test against an entirely fake state dir -- every
    source missing -- verifying the report still builds, every figure reads
    unknown (never a fabricated zero), and 'today' matches the anchor date."""
    monkeypatch.setattr(cm, "CONDUCTOR_OUTCOMES", tmp_path / "no-conductor.jsonl")
    monkeypatch.setattr(cm, "COMPANION_FEED_DIR", tmp_path / "no-feed")
    monkeypatch.setattr(cm, "COMPANION_RESULTS", tmp_path / "no-results.jsonl")
    monkeypatch.setattr(cm._spend, "CC_PROJECT_DIR", tmp_path / "no-cc")

    report = cm.build_report(anchor_date="2026-08-29")
    assert report["as_of_et_date"] == "2026-08-29"
    assert report["window_days"] == 7
    assert report["today"]["date_et"] == "2026-08-29"
    assert set(report["days"].keys()) == set(DATES7)
    assert report["today"]["claude_code"]["usd"] is None
    assert report["today"]["claude_code"]["known"] is False
    assert report["today"]["by_origin"]["conductor"]["usd"] is None
    assert len(report["data_quality_flags"]) >= 2  # claude scan + conductor ledger missing


def test_build_report_defaults_anchor_to_et_today(monkeypatch, tmp_path):
    monkeypatch.setattr(cm, "CONDUCTOR_OUTCOMES", tmp_path / "no-conductor.jsonl")
    monkeypatch.setattr(cm, "COMPANION_FEED_DIR", tmp_path / "no-feed")
    monkeypatch.setattr(cm._spend, "CC_PROJECT_DIR", tmp_path / "no-cc")
    report = cm.build_report()
    assert report["as_of_et_date"] == cm._et.et_today_str()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
