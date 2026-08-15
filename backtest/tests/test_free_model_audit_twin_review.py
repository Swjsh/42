"""Guards for free_model_audit_twin_review.py -- the twin_review AUDIT_SUBJECTS adapter
(AUDIT-HARNESS-B2).

REAL_SIDECAR_2026_07_11 below is copied VERBATIM from the actual
automation/state/crypto-twin/reviews/2026-07-11.json on disk (confirmed via direct Read before
this adapter was built, per the task's own instruction not to trust the description alone) --
this is real production output from twin_review.py's first live LLM call, not invented.
collect_items parsing tests run against a copy of this real file. Grading-dispatch tests use
small synthetic sidecars + an INJECTED sentinel_path (or a monkeypatched twin_sentinel.evaluate)
so no test ever depends on the live twin-sentinel.json file's mutable current state.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _load(name: str, relpath: str):
    spec = importlib.util.spec_from_file_location(name, REPO / relpath)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


fma = _load("free_model_audit", "setup/scripts/free_model_audit.py")

# DO NOT _load() this one (fixed 2026-08-15) -- same defect as the swarm_consult guard.
# free_model_audit imports it ITSELF while building AUDIT_SUBJECTS
# (free_model_audit.py:205), and the adapter's `grade` closes over THAT instance. Re-executing
# the file here made a SECOND module object, so the monkeypatches below patched a copy the
# adapter never calls and `grade` ran the REAL LLM path -- a test that believed it was mocked
# firing a live `claude` subprocess. Bind to the sys.modules entry so there is ONE instance.
tr = sys.modules["free_model_audit_twin_review"]


# ---------- REAL fixture (verbatim from automation/state/crypto-twin/reviews/2026-07-11.json) ----------

REAL_SIDECAR_2026_07_11 = {
    "date": "2026-07-11",
    "model_used": "nvidia/nemotron-3-super-120b-a12b:free",
    "assessment": "HEALTHY",
    "confidence": 0.95,
    "flags_raised": ["LOW_PATH_COVERAGE"],
    "summary": (
        "No tick errors and zero incidents today. Action distribution: 116 HOLD, 25 "
        "BLOCKED_NO_ACCOUNT, 12 SKIP_NO_SHORT_CRYPTO, 1 ENTERED (forced‑entry test flag), "
        "4 MANAGED. Hourly rollups show similar patterns with no errors. Path coverage is 0/9 "
        "branches green, indicating limited exercise of decision logic. Human should review "
        "test scenarios to increase branch coverage, confirm that BLOCKED_NO_ACCOUNT and "
        "SKIP_NO_SHORT_CRYPTO are expected, and ensure any forced‑entry test flags are "
        "disabled for normal operation."
    ),
}


def _write_sidecar(reviews_dir: Path, date_str: str, payload: dict) -> Path:
    reviews_dir.mkdir(parents=True, exist_ok=True)
    p = reviews_dir / f"{date_str}.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


# ---------- collect_items: parsing on the REAL sidecar ----------

def test_collect_items_reads_real_sidecar(tmp_path):
    _write_sidecar(tmp_path, "2026-07-11", REAL_SIDECAR_2026_07_11)
    items = tr.collect_items(None, date(2026, 7, 11), reviews_dir=tmp_path)
    assert len(items) == 1
    it = items[0]
    assert it.subject == "twin_review"
    assert it.item_id == "review:2026-07-11"
    assert it.account == "crypto-twin"
    assert it.timestamp_et == "2026-07-11T00:00:00"
    assert it.context["date"] == "2026-07-11"
    assert it.free_model_output == REAL_SIDECAR_2026_07_11
    assert it.free_model_output["assessment"] == "HEALTHY"
    assert it.free_model_output["model_used"] == "nvidia/nemotron-3-super-120b-a12b:free"


def test_collect_items_date_window_filters(tmp_path):
    _write_sidecar(tmp_path, "2026-07-09", {**REAL_SIDECAR_2026_07_11, "date": "2026-07-09"})
    _write_sidecar(tmp_path, "2026-07-11", REAL_SIDECAR_2026_07_11)
    only_11 = tr.collect_items(date(2026, 7, 11), date(2026, 7, 11), reviews_dir=tmp_path)
    assert len(only_11) == 1 and only_11[0].context["date"] == "2026-07-11"
    both = tr.collect_items(date(2026, 7, 9), date(2026, 7, 11), reviews_dir=tmp_path)
    assert len(both) == 2
    only_09 = tr.collect_items(None, date(2026, 7, 9), reviews_dir=tmp_path)
    assert len(only_09) == 1 and only_09[0].context["date"] == "2026-07-09"


def test_collect_items_skips_non_dated_filenames(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "README.json").write_text("{}", encoding="utf-8")
    _write_sidecar(tmp_path, "2026-07-11", REAL_SIDECAR_2026_07_11)
    items = tr.collect_items(None, date(2026, 7, 11), reviews_dir=tmp_path)
    assert len(items) == 1
    assert items[0].context["date"] == "2026-07-11"


def test_collect_items_skips_malformed_json(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "2026-07-10.json").write_text("{not valid json", encoding="utf-8")
    _write_sidecar(tmp_path, "2026-07-11", REAL_SIDECAR_2026_07_11)
    items = tr.collect_items(None, date(2026, 7, 11), reviews_dir=tmp_path)
    assert len(items) == 1
    assert items[0].context["date"] == "2026-07-11"


def test_collect_items_missing_dir_returns_empty(tmp_path):
    assert tr.collect_items(None, date(2026, 7, 11), reviews_dir=tmp_path / "nope") == []


# ---------- _sentinel_verdict_for_date: recorded-snapshot path ----------

def test_sentinel_verdict_uses_recorded_snapshot_when_dated_same_day(tmp_path):
    snap_path = tmp_path / "twin-sentinel.json"
    snap_path.write_text(json.dumps({
        "verdict": "GREEN", "reasons": [],
        "facts": {"incidents_today": 0},
        "checked_at_utc": "2026-07-11T14:30:00.203972+00:00",
    }), encoding="utf-8")
    truth = tr._sentinel_verdict_for_date("2026-07-11", sentinel_path=snap_path)
    assert truth is not None
    assert truth["verdict"] == "GREEN"
    assert truth["source"] == "recorded_snapshot"
    assert truth["incidents_today"] == 0
    assert "caveat" not in truth


def test_sentinel_verdict_recorded_snapshot_carries_real_reasons(tmp_path):
    snap_path = tmp_path / "twin-sentinel.json"
    snap_path.write_text(json.dumps({
        "verdict": "RED", "reasons": ["TICK_GAP: last tick 25.0 min ago (threshold 20 min)"],
        "facts": {"incidents_today": 1},
        "checked_at_utc": "2026-07-12T02:00:00+00:00",
    }), encoding="utf-8")
    truth = tr._sentinel_verdict_for_date("2026-07-12", sentinel_path=snap_path)
    assert truth["verdict"] == "RED"
    assert truth["reasons"] == ["TICK_GAP: last tick 25.0 min ago (threshold 20 min)"]
    assert truth["source"] == "recorded_snapshot"


# ---------- _sentinel_verdict_for_date: reconstruction fallback (snapshot dated a DIFFERENT day) ----------

def test_sentinel_verdict_reconstructs_via_evaluate_when_snapshot_is_a_different_day(tmp_path, monkeypatch):
    snap_path = tmp_path / "twin-sentinel.json"
    # Snapshot on disk is dated 2026-07-12 -- querying 2026-07-11 must NOT reuse it.
    snap_path.write_text(json.dumps({
        "verdict": "GREEN", "reasons": [], "facts": {},
        "checked_at_utc": "2026-07-12T00:05:00+00:00",
    }), encoding="utf-8")

    captured = {}

    def _fake_evaluate(*, now_utc, now_et, prior_sentinel):
        captured["now_utc"] = now_utc
        captured["prior_sentinel"] = prior_sentinel
        return {"verdict": "YELLOW", "reasons": ["LOW_UPTIME: 5/20 ticks today (25.0%)"],
               "facts": {"incidents_today": 0}}

    monkeypatch.setattr(tr.ts, "evaluate", _fake_evaluate)
    truth = tr._sentinel_verdict_for_date("2026-07-11", sentinel_path=snap_path)
    assert truth["verdict"] == "YELLOW"
    assert truth["source"] == "reconstructed_evaluate_call"
    assert "caveat" in truth and "twin-health.json" in truth["caveat"]
    assert captured["now_utc"] == datetime(2026, 7, 11, 23, 59, 59, tzinfo=timezone.utc)
    assert captured["prior_sentinel"] is None


def test_sentinel_verdict_reconstructs_when_no_snapshot_file_at_all(tmp_path, monkeypatch):
    monkeypatch.setattr(tr.ts, "evaluate",
                        lambda **kw: {"verdict": "RED", "reasons": ["BREAKER_TRIPPED: x"],
                                     "facts": {"incidents_today": 3}})
    truth = tr._sentinel_verdict_for_date("2026-07-01", sentinel_path=tmp_path / "nope.json")
    assert truth["verdict"] == "RED"
    assert truth["source"] == "reconstructed_evaluate_call"


def test_sentinel_verdict_none_when_evaluate_raises(tmp_path, monkeypatch):
    def _boom(**kw):
        raise RuntimeError("decisions.jsonl unreadable")
    monkeypatch.setattr(tr.ts, "evaluate", _boom)
    assert tr._sentinel_verdict_for_date("2026-07-01", sentinel_path=tmp_path / "nope.json") is None


def test_sentinel_verdict_none_on_unparseable_date(tmp_path):
    assert tr._sentinel_verdict_for_date("not-a-date", sentinel_path=tmp_path / "nope.json") is None


# ---------- grade_item dispatch ----------

def _mk_item(date_str="2026-07-11", assessment="HEALTHY", confidence=0.9, flags=None):
    return fma.AuditItem(
        subject="twin_review", item_id=f"review:{date_str}",
        timestamp_et=f"{date_str}T00:00:00", account="crypto-twin",
        context={"date": date_str, "sidecar_path": f"reviews/{date_str}.json"},
        free_model_output={"date": date_str, "model_used": "nvidia/nemotron-3-super-120b-a12b:free",
                           "assessment": assessment, "confidence": confidence,
                           "flags_raised": flags or [], "summary": "x"})


def test_grade_correct_when_green_maps_to_healthy(monkeypatch):
    it = _mk_item(assessment="HEALTHY")
    monkeypatch.setattr(tr, "_sentinel_verdict_for_date",
                        lambda d, **kw: {"verdict": "GREEN", "reasons": [], "incidents_today": 0,
                                        "source": "recorded_snapshot", "checked_at_utc": "x"})
    result = tr.grade_item(it, {})
    assert result["grading_method"] == "deterministic_cross_check"
    assert result["decision"] == "HEALTHY"
    assert result["correct"] is True
    assert "sentinel_verdict=GREEN" in result["evidence_summary"]
    assert result["detail"]["llm_assessment"] == "HEALTHY"


def test_grade_correct_when_red_maps_to_concerning(monkeypatch):
    it = _mk_item(assessment="CONCERNING")
    monkeypatch.setattr(tr, "_sentinel_verdict_for_date",
                        lambda d, **kw: {"verdict": "RED", "reasons": ["BREAKER_TRIPPED: x"],
                                        "incidents_today": 4, "source": "recorded_snapshot",
                                        "checked_at_utc": "x"})
    result = tr.grade_item(it, {})
    assert result["correct"] is True


def test_grade_wrong_when_llm_says_healthy_but_sentinel_is_red(monkeypatch):
    """The costly error class for this subject: the free model calls it HEALTHY while the
    deterministic judge says RED (a real incident going unnoticed by the LLM reviewer)."""
    it = _mk_item(assessment="HEALTHY")
    monkeypatch.setattr(tr, "_sentinel_verdict_for_date",
                        lambda d, **kw: {"verdict": "RED", "reasons": ["INCIDENT_SPIKE: 5 incidents"],
                                        "incidents_today": 5, "source": "recorded_snapshot",
                                        "checked_at_utc": "x"})
    result = tr.grade_item(it, {})
    assert result["grading_method"] == "deterministic_cross_check"
    assert result["correct"] is False


def test_grade_wrong_when_yellow_maps_to_degraded_mismatch(monkeypatch):
    it = _mk_item(assessment="CONCERNING")  # LLM over-calls a YELLOW as CONCERNING
    monkeypatch.setattr(tr, "_sentinel_verdict_for_date",
                        lambda d, **kw: {"verdict": "YELLOW", "reasons": ["LOW_UPTIME: x"],
                                        "incidents_today": 0, "source": "recorded_snapshot",
                                        "checked_at_utc": "x"})
    result = tr.grade_item(it, {})
    assert result["correct"] is False


def test_grade_includes_caveat_in_evidence_when_reconstructed(monkeypatch):
    it = _mk_item(assessment="HEALTHY")
    monkeypatch.setattr(tr, "_sentinel_verdict_for_date",
                        lambda d, **kw: {"verdict": "GREEN", "reasons": [], "incidents_today": 0,
                                        "source": "reconstructed_evaluate_call",
                                        "caveat": "breaker/account reflect CURRENT state",
                                        "checked_at_utc": "x"})
    result = tr.grade_item(it, {})
    assert result["correct"] is True
    assert "CAVEAT" in result["evidence_summary"]


def test_grade_ungraded_when_assessment_missing_or_invalid():
    it = _mk_item(assessment="SOMETHING_ELSE")
    result = tr.grade_item(it, {})
    assert result["grading_method"] == "ungraded_insufficient_data"
    assert result["correct"] is None
    assert "assessment field missing/invalid" in result["evidence_summary"]


def test_grade_never_fabricates_when_no_ground_truth_available(monkeypatch):
    it = _mk_item(assessment="HEALTHY")
    monkeypatch.setattr(tr, "_sentinel_verdict_for_date", lambda d, **kw: None)
    result = tr.grade_item(it, {})
    assert result["grading_method"] == "ungraded_insufficient_data"
    assert result["correct"] is None


def test_grade_ungraded_when_verdict_unrecognized(monkeypatch):
    it = _mk_item(assessment="HEALTHY")
    monkeypatch.setattr(tr, "_sentinel_verdict_for_date",
                        lambda d, **kw: {"verdict": "UNKNOWN_VERDICT", "reasons": [],
                                        "incidents_today": 0, "source": "recorded_snapshot",
                                        "checked_at_utc": "x"})
    result = tr.grade_item(it, {})
    assert result["grading_method"] == "ungraded_insufficient_data"
    assert result["correct"] is None


# ---------- registry integration (via the real free_model_audit.py, not a synthetic double) ----------

def test_wired_in_real_registry_and_end_to_end_against_the_real_sidecar(tmp_path, monkeypatch):
    """Full loop through the REAL registry entry (not a hand-built AuditItem), proving the
    adapter functions correctly imports match what free_model_audit.py actually calls."""
    assert "twin_review" in fma.AUDIT_SUBJECTS
    adapter = fma.AUDIT_SUBJECTS["twin_review"]
    assert adapter.wired is True

    reviews_dir = tmp_path / "reviews"
    _write_sidecar(reviews_dir, "2026-07-11", REAL_SIDECAR_2026_07_11)
    items = list(adapter.collect(None, date(2026, 7, 11), reviews_dir=reviews_dir))
    assert len(items) == 1

    monkeypatch.setattr(tr, "_sentinel_verdict_for_date",
                        lambda d, **kw: {"verdict": "GREEN", "reasons": [], "incidents_today": 0,
                                        "source": "recorded_snapshot", "checked_at_utc": "x"})
    result = adapter.grade(items[0], {"allow_llm_fallback": True})
    assert result["grading_method"] in fma.GRADING_METHODS
    assert result["grading_method"] == "deterministic_cross_check"
    assert result["correct"] is True  # real sidecar says HEALTHY, GREEN maps to HEALTHY
