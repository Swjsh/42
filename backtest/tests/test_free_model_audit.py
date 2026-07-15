"""Guards for free_model_audit.py -- the reusable free-model grading harness (J 2026-07-11:
"audit it every other day until we're confident in it... put it into a reusable harness
framework we can benchmark and score"). Pure-logic tests only: confidence-bar math, cadence
self-gating, dedupe, registry shape. No network, no real decisions.jsonl I/O (the adapter's
own parsing tests live in test_free_model_audit_heartbeat_veto.py)."""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "free_model_audit", REPO / "setup" / "scripts" / "free_model_audit.py")
fma = importlib.util.module_from_spec(_SPEC)
sys.modules["free_model_audit"] = fma
_SPEC.loader.exec_module(fma)


# ---------- registry ----------

def test_registry_has_heartbeat_veto_wired():
    assert "heartbeat_veto" in fma.AUDIT_SUBJECTS
    assert fma.AUDIT_SUBJECTS["heartbeat_veto"].wired is True


def test_registry_has_twin_review_wired():
    """AUDIT-HARNESS-B2: twin_review is the second wired subject (agreement-with-a-second-
    deterministic-source grading, not counterfactual replay -- see
    free_model_audit_twin_review.py's module docstring)."""
    assert "twin_review" in fma.AUDIT_SUBJECTS
    assert fma.AUDIT_SUBJECTS["twin_review"].wired is True


def test_registry_has_prospector_wired():
    """AUDIT-HARNESS-B3: prospector is wired -- deterministic cross-check against
    ideas-ledger.jsonl kill rows + analysis/recommendations/ artifacts (see that adapter's
    own module docstring; adapter-level parsing/grading tests live in
    test_free_model_audit_prospector.py)."""
    assert "prospector" in fma.AUDIT_SUBJECTS
    assert fma.AUDIT_SUBJECTS["prospector"].wired is True


def test_registry_has_swarm_consult_wired():
    """AUDIT-HARNESS-B3: swarm_consult is wired -- blind Sonnet re-judgment + agreement scoring
    (see that adapter's own module docstring; adapter-level parsing/grading tests live in
    test_free_model_audit_swarm_consult.py)."""
    assert "swarm_consult" in fma.AUDIT_SUBJECTS
    assert fma.AUDIT_SUBJECTS["swarm_consult"].wired is True


def test_registry_has_exactly_four_wired_subjects():
    """Every registered subject as of AUDIT-HARNESS-B3 (2026-07-15) is wired -- no remaining
    TODO stubs. If a future subject is added unwired, this guard must be relaxed deliberately,
    not silently pass."""
    assert set(fma.AUDIT_SUBJECTS) == {"heartbeat_veto", "twin_review", "prospector",
                                       "swarm_consult"}
    for name, adapter in fma.AUDIT_SUBJECTS.items():
        assert adapter.wired is True, f"{name} unexpectedly unwired"


def test_grading_methods_are_the_four_canonical_tags():
    assert fma.GRADING_METHODS == {"counterfactual", "llm_judgment", "deterministic_cross_check",
                                   "ungraded_insufficient_data"}


# ---------- confidence-bar math (pure) ----------

def test_confidence_bar_needs_minimum_evidence():
    """5/5 = 100% correct but under the 15-evidence floor -> NOT confident."""
    state = fma.default_bar_state()
    state = fma.update_confidence_state(state, run_evidence_n=5, run_correct_n=5,
                                        run_date="2026-07-11")
    assert state["confident"] is False
    assert state["evidence_n"] == 5


def test_confidence_bar_crosses_after_enough_evidence_and_streak():
    state = fma.default_bar_state()
    # 3 consecutive runs, each contributing evidence, cumulative rate stays >=85%, n>=15
    state = fma.update_confidence_state(state, run_evidence_n=6, run_correct_n=6, run_date="2026-07-11")
    assert state["confident"] is False  # n=6 < 15
    state = fma.update_confidence_state(state, run_evidence_n=6, run_correct_n=6, run_date="2026-07-13")
    assert state["confident"] is False  # n=12 < 15, streak not yet building (still short of floor)
    state = fma.update_confidence_state(state, run_evidence_n=6, run_correct_n=5, run_date="2026-07-15")
    # n=18 >=15, correct=17/18=94.4% >= 85% -> bar passes THIS run -> streak=1, not yet 3
    assert state["evidence_n"] == 18
    assert state["confident"] is False
    assert state["consecutive_runs_above_bar"] == 1
    state = fma.update_confidence_state(state, run_evidence_n=3, run_correct_n=3, run_date="2026-07-17")
    assert state["consecutive_runs_above_bar"] == 2
    assert state["confident"] is False
    state = fma.update_confidence_state(state, run_evidence_n=3, run_correct_n=3, run_date="2026-07-19")
    assert state["consecutive_runs_above_bar"] == 3
    assert state["confident"] is True
    assert state["cadence_days"] == fma.CADENCE_RELAXED_DAYS
    assert state["confident_since"] == "2026-07-19"


def test_confidence_streak_resets_on_a_bad_run():
    state = fma.default_bar_state()
    state["evidence_n"], state["correct_n"] = 20, 19          # 95% cumulative, well above bar
    state["consecutive_runs_above_bar"] = 2                    # one run away from confident
    # A bad run (0/10 correct) drags the cumulative rate down below 85% -> streak resets to 0
    state = fma.update_confidence_state(state, run_evidence_n=10, run_correct_n=0, run_date="2026-07-11")
    assert state["evidence_n"] == 30
    assert state["correct_n"] == 19
    assert round(fma.cumulative_rate(state), 3) < 0.85
    assert state["consecutive_runs_above_bar"] == 0
    assert state["confident"] is False


def test_confidence_state_drops_after_previously_confident_then_bad_run():
    """A subject that WAS confident (cadence relaxed to weekly) must fall back to the
    default cadence the moment it stops being confident -- never stays lenient on stale trust."""
    state = fma.default_bar_state()
    state.update({"evidence_n": 20, "correct_n": 19, "consecutive_runs_above_bar": 3,
                 "confident": True, "cadence_days": fma.CADENCE_RELAXED_DAYS,
                 "confident_since": "2026-07-01"})
    state = fma.update_confidence_state(state, run_evidence_n=10, run_correct_n=0, run_date="2026-07-11")
    assert state["confident"] is False
    assert state["cadence_days"] == fma.CADENCE_DEFAULT_DAYS
    assert state["confident_since"] is None


def test_empty_run_leaves_cumulative_and_streak_unchanged():
    """A run where every collected item was ungraded (evidence_n=0) must not silently zero
    the streak -- it is neither for nor against confidence, just inconclusive this run."""
    state = fma.default_bar_state()
    state.update({"evidence_n": 16, "correct_n": 15, "consecutive_runs_above_bar": 1})
    new = fma.update_confidence_state(state, run_evidence_n=0, run_correct_n=0, run_date="2026-07-11")
    assert new["evidence_n"] == 16
    assert new["consecutive_runs_above_bar"] == 1
    assert new["last_run_date"] == "2026-07-11"  # last_run_date still advances (it DID run)


# ---------- cadence self-gate (pure) ----------

def test_should_run_first_time_no_last_run_date():
    run, reason = fma.should_run(fma.default_bar_state(), date(2026, 7, 11))
    assert run is True
    assert "first run" in reason


def test_should_run_force_always_true():
    state = {"last_run_date": "2026-07-11", "cadence_days": 2}
    run, reason = fma.should_run(state, date(2026, 7, 11), force=True)
    assert run is True
    assert "forced" in reason


def test_should_run_respects_every_other_day_cadence():
    state = {"last_run_date": "2026-07-10", "cadence_days": 2}
    run, reason = fma.should_run(state, date(2026, 7, 11))  # only 1 day elapsed
    assert run is False
    assert "SKIPPED" in reason and "not due" in reason
    run2, _ = fma.should_run(state, date(2026, 7, 12))  # 2 days elapsed -> due
    assert run2 is True


def test_should_run_respects_relaxed_weekly_cadence():
    state = {"last_run_date": "2026-07-05", "cadence_days": 7}
    run, _ = fma.should_run(state, date(2026, 7, 10))  # 5 days -- still not due weekly
    assert run is False
    run2, _ = fma.should_run(state, date(2026, 7, 12))  # 7 days -- due
    assert run2 is True


def test_should_run_never_returns_silent_reason():
    """Every branch must produce a non-empty, human-readable reason -- OP-25/C7 (silent
    success is failure): a scheduled fire that skips must still SAY so."""
    for state in (fma.default_bar_state(), {"last_run_date": "bad-date", "cadence_days": 2},
                 {"last_run_date": "2026-07-11", "cadence_days": 2}):
        run, reason = fma.should_run(state, date(2026, 7, 11))
        assert isinstance(reason, str) and len(reason) > 0


# ---------- dedupe / history ledger ----------

def test_already_graded_ids_reads_only_matching_subject_item_rows(tmp_path):
    hist = tmp_path / "history.jsonl"
    rows = [
        {"kind": "item", "subject": "heartbeat_veto", "item_id": "extra:safe:t1"},
        {"kind": "item", "subject": "heartbeat_veto", "item_id": "extra:safe:t2"},
        {"kind": "item", "subject": "OTHER_SUBJECT", "item_id": "extra:safe:t1"},  # different subject
        {"kind": "run_summary", "subject": "heartbeat_veto"},  # not an item row
        "not even json",
    ]
    with hist.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write((json.dumps(r) if not isinstance(r, str) else r) + "\n")
    ids = fma.already_graded_ids("heartbeat_veto", history_path=hist)
    assert ids == {"extra:safe:t1", "extra:safe:t2"}


def test_already_graded_ids_missing_file_returns_empty(tmp_path):
    assert fma.already_graded_ids("heartbeat_veto", history_path=tmp_path / "nope.jsonl") == set()


# ---------- scorecard renderer smoke test ----------

def test_render_scorecard_smoke():
    graded = [
        {"item_id": "extra:safe:t1", "decision": "veto", "grading_method": "counterfactual",
         "correct": True, "n_lanes_answered": 2, "evidence_summary": "replay pnl=$-12.00"},
        {"item_id": "extra:safe:t2", "decision": "veto", "grading_method": "counterfactual",
         "correct": False, "n_lanes_answered": 1, "evidence_summary": "replay pnl=$40.00"},
        {"item_id": "core:bold:t3", "decision": "go", "grading_method": "llm_judgment",
         "correct": None, "n_lanes_answered": 2, "evidence_summary": "ungraded"},
    ]
    state = fma.update_confidence_state(fma.default_bar_state(), run_evidence_n=2, run_correct_n=1,
                                        run_date="2026-07-11")
    md = fma.render_scorecard("heartbeat_veto", "2026-07-11", graded,
                              {"n_collected": 3, "n_already_graded": 0}, state)
    assert "heartbeat_veto" in md
    assert "TRUE vetoes" in md and "FALSE vetoes" in md
    assert "extra:safe:t1" in md and "extra:safe:t2" in md
    assert "Verdict" in md
