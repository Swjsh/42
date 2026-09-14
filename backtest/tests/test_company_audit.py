"""Guard: setup/scripts/company_audit.py + automation/state/station/company-roster.json
(GOAL-GAMMA-STATION-2026-09-13 item 22, "test that all agents work, have goals, are
smart, and work autonomously as a real company").

Covers, in order: the committed roster's shape (7 personas, required keys, objective
quoted verbatim from its own role_file, every `tasks[]` name present in the
SCHEDULED-TASKS.md registry); the core per-axis logic run HERMETICALLY on a tmp_path
fixture tree (no PowerShell, no network) -- a persona pointed at nothing yields
FAIL-with-evidence on every axis and never raises, a fully-backed synthetic persona
yields PASS on all four; the documented JSON shape via one real `--no-llm` CLI run
against the actual repo (no network, but does enumerate the real Task Scheduler --
this is the same command `python setup/scripts/company_audit.py --no-llm` runs by hand,
so it doubles as a repeatability check); and two small regression locks for bugs found
live while building this: the weekend/night last-trading-day guard (a run at 00:2x ET on
a fresh Monday must grade FRIDAY's evidence, not an empty Monday) and the per-TASK (not
blended per-persona) cadence lookup Coach's four heterogeneous tasks need.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in ("setup/scripts", ""):
    p = str(REPO / _p) if _p else str(REPO)
    if p not in sys.path:
        sys.path.insert(0, p)

import company_audit as ca  # noqa: E402

ROSTER_PATH = REPO / "automation" / "state" / "station" / "company-roster.json"
REGISTRY_PATH = REPO / "automation" / "state" / "SCHEDULED-TASKS.md"

REQUIRED_PERSONA_KEYS = {
    "name", "role_file", "objective", "kpi", "cadence", "tasks", "dedicated_task",
    "deliverable", "goal_ref", "ground_truth", "quiz",
}


def _real_roster() -> dict:
    return json.loads(ROSTER_PATH.read_text(encoding="utf-8"))


# ============================================================================
# Roster schema (the committed config, not a fixture)
# ============================================================================

def test_roster_has_seven_personas_with_required_keys():
    personas = _real_roster()["personas"]
    assert len(personas) == 7
    assert len({p["name"] for p in personas}) == 7, "duplicate persona name"
    for p in personas:
        missing = REQUIRED_PERSONA_KEYS - set(p.keys())
        assert not missing, f"{p.get('name')!r} missing roster keys: {missing}"
        assert p["objective"].strip(), f"{p['name']}: empty objective"
        assert p["kpi"].strip(), f"{p['name']}: empty kpi"
        assert isinstance(p["tasks"], list)
        assert p["deliverable"].get("path"), f"{p['name']}: deliverable.path missing"
        assert p["ground_truth"]["kind"] in ca.GROUND_TRUTH_CHECKS, (
            f"{p['name']}: ground_truth.kind={p['ground_truth'].get('kind')!r} has no registered check")
        quiz = p["quiz"]
        assert quiz["prompt"].strip() and quiz["checks"], f"{p['name']}: quiz is incomplete"
        for check in quiz["checks"]:
            assert check["type"] in ("regex", "substring") and check["value"]


def test_roster_objectives_are_literal_substrings_of_their_role_files():
    """The has_goal axis enforces this at runtime (check_has_goal); pinned again here so
    a hand-edit to the roster that drifts from its source .md fails CI, not just a live
    run three weeks later."""
    for p in _real_roster()["personas"]:
        role_text = (REPO / p["role_file"]).read_text(encoding="utf-8")
        assert p["objective"] in role_text, (
            f"{p['name']}'s roster `objective` is not a verbatim substring of {p['role_file']}")


def test_roster_goal_refs_point_at_real_goal_files_or_none():
    for p in _real_roster()["personas"]:
        ref = p["goal_ref"]
        if ref == "none":
            continue
        assert (REPO / "automation" / "state" / "goals" / f"{ref}.md").exists(), (
            f"{p['name']}: goal_ref={ref!r} names a file that does not exist")


def test_roster_task_names_exist_in_scheduled_tasks_registry():
    registry_text = REGISTRY_PATH.read_text(encoding="utf-8")
    for p in _real_roster()["personas"]:
        for task_name in p["tasks"]:
            needle = f"`{task_name}`"
            assert needle in registry_text, (
                f"{p['name']}'s task {task_name!r} does not appear as {needle} anywhere "
                f"in {REGISTRY_PATH.name}")


# ============================================================================
# Core per-axis logic -- hermetic: no PowerShell, no network, tmp_path only
# ============================================================================

def _write_role_file(tmp_path: Path, rel: str, objective: str) -> None:
    f = tmp_path / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(f"# Role\n\n## Your job in one sentence\n\n{objective}\n", encoding="utf-8")


def _far_deadline() -> float:
    return time.monotonic() + 5


def test_persona_pointed_at_nothing_fails_every_axis_with_evidence(monkeypatch, tmp_path):
    monkeypatch.setattr(ca, "REPO", tmp_path)
    _write_role_file(tmp_path, ".claude/agents/ghost.md", "Ghost's one-sentence objective.")

    persona = {
        "name": "Ghost",
        "role_file": ".claude/agents/ghost.md",
        "objective": "Ghost's one-sentence objective.",
        "kpi": "some measurable line",
        "cadence": "06:00 ET daily",
        "tasks": ["Gamma_DoesNotExist"],
        "dedicated_task": True,
        "deliverable": {"path": "nowhere/nothing.json", "glob": None},
        "goal_ref": "none",
        "ground_truth": {
            "kind": "coach_drift_within_cadence",
            "drift_path": "nowhere/drift.json", "log_path": "nowhere/log.jsonl",
            "within_hours": 30, "log_within_days": 3,
        },
        "quiz": {"id": "x", "prompt": "irrelevant", "checks": [{"type": "substring", "value": "x"}]},
    }
    now = datetime.now(timezone.utc)
    result = ca.run_persona_audit(persona, {}, None, now, "2026-09-11", False, "test", "none", _far_deadline())

    assert result["verdict"] == "FAIL"
    for axis in ("works", "has_goal", "is_smart", "autonomous"):
        check = result["checks"][axis]
        assert check["evidence"], f"{axis}: evidence must never be empty, even on FAIL"
    assert result["checks"]["works"]["verdict"] == "FAIL"
    assert "Gamma_DoesNotExist" in result["checks"]["works"]["evidence"]
    assert result["checks"]["is_smart"]["verdict"] == "FAIL"
    assert "missing" in result["checks"]["is_smart"]["evidence"].lower()
    assert result["checks"]["autonomous"]["verdict"] == "FAIL"


def test_missing_role_file_and_goal_ref_fail_has_goal_distinctly(tmp_path, monkeypatch):
    monkeypatch.setattr(ca, "REPO", tmp_path)
    persona = {"name": "NoFile", "role_file": ".claude/agents/nofile.md",
               "objective": "anything", "kpi": "k", "goal_ref": "none"}
    result = ca.check_has_goal(persona)
    assert result["verdict"] == "FAIL"
    assert "missing role_file" in result["evidence"]


def test_synthetic_complete_persona_passes_every_axis(monkeypatch, tmp_path):
    monkeypatch.setattr(ca, "REPO", tmp_path)
    _write_role_file(tmp_path, ".claude/agents/model.md", "Be a model employee in one sentence.")

    now = datetime.now(timezone.utc)
    drift_path = tmp_path / "crypto" / "data" / "scorecards" / "drift_report.json"
    drift_path.parent.mkdir(parents=True, exist_ok=True)
    drift_path.write_text(json.dumps({"overall_health": "GREEN"}), encoding="utf-8")
    log_path = drift_path.parent / "model-log.jsonl"
    log_path.write_text(json.dumps({"ts": now.isoformat()}) + "\n", encoding="utf-8")

    task_name = "Gamma_ModelTask"
    tasks_by_name = {task_name: {
        "name": task_name, "state": "Ready",
        "last_run": now.isoformat().replace("+00:00", "Z"),
        "last_result": 0, "triggers": [],
    }}
    persona = {
        "name": "Model",
        "role_file": ".claude/agents/model.md",
        "objective": "Be a model employee in one sentence.",
        "kpi": "some measurable line",
        "cadence": "every 30 min, 24/7",
        "tasks": [task_name],
        "dedicated_task": True,
        "deliverable": {"path": "crypto/data/scorecards/drift_report.json", "glob": None},
        "goal_ref": "none",
        "ground_truth": {
            "kind": "coach_drift_within_cadence",
            "drift_path": "crypto/data/scorecards/drift_report.json",
            "log_path": "crypto/data/scorecards/model-log.jsonl",
            "within_hours": 30, "log_within_days": 3,
        },
        "quiz": {"id": "x", "prompt": "irrelevant", "checks": [{"type": "substring", "value": "x"}]},
    }
    result = ca.run_persona_audit(persona, tasks_by_name, None, now, "2026-09-11",
                                   False, "no-llm test", "none", _far_deadline())

    assert result["verdict"] == "PASS", result
    for axis in ("works", "has_goal", "is_smart", "autonomous"):
        assert result["checks"][axis]["verdict"] == "PASS", (axis, result["checks"][axis])
    assert result["quiz"]["verdict"] == "SKIPPED"  # allowed=False -- never silently ran a real LLM call


# ============================================================================
# 2026-09-14 company-roster re-point (C4): the two new ground_truth kinds,
# chef_verdict_rows and coach_sectors_fresh, on synthetic tmp_path trees --
# PASS/WARN/FAIL for each, hermetically (no PowerShell, no network).
# ============================================================================

def _chef_gt(**overrides) -> dict:
    gt = {"kind": "chef_verdict_rows",
          "verdicts_path": "analysis/recommendations/station-verdicts.jsonl",
          "board_path": "automation/state/station/ideas-board.json", "max_age_min": 60}
    gt.update(overrides)
    return gt


def test_chef_verdict_rows_fails_when_verdicts_file_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(ca, "REPO", tmp_path)
    result = ca._gt_chef_verdict_rows(_chef_gt(), datetime.now(timezone.utc), "2026-09-11")
    assert result["verdict"] == "FAIL"
    assert "missing" in result["evidence"].lower()


def test_chef_verdict_rows_fails_when_verdicts_file_has_zero_rows(monkeypatch, tmp_path):
    monkeypatch.setattr(ca, "REPO", tmp_path)
    p = tmp_path / "analysis" / "recommendations" / "station-verdicts.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("", encoding="utf-8")
    result = ca._gt_chef_verdict_rows(_chef_gt(), datetime.now(timezone.utc), "2026-09-11")
    assert result["verdict"] == "FAIL"
    assert "0 parseable rows" in result["evidence"]


def test_chef_verdict_rows_passes_when_fresh_and_every_testing_card_covered(monkeypatch, tmp_path):
    monkeypatch.setattr(ca, "REPO", tmp_path)
    now = datetime.now(timezone.utc)
    fresh_ts = ca.et_now(now_utc=now).strftime("%Y-%m-%d %H:%M:%S ET")
    vp = tmp_path / "analysis" / "recommendations" / "station-verdicts.jsonl"
    vp.parent.mkdir(parents=True, exist_ok=True)
    vp.write_text(json.dumps({"ts_et": fresh_ts, "card_id": "c1",
                              "spec": {"type": "size_cap", "params": {"cap": 3}},
                              "result": {"verdict": "pending", "n_pre": 5, "n_post": 0}}) + "\n",
                 encoding="utf-8")
    bp = tmp_path / "automation" / "state" / "station" / "ideas-board.json"
    bp.parent.mkdir(parents=True, exist_ok=True)
    bp.write_text(json.dumps([{"id": "c1", "status": "testing", "title": "x"},
                              {"id": "c2", "status": "proposed", "title": "y"}]), encoding="utf-8")

    result = ca._gt_chef_verdict_rows(_chef_gt(), now, "2026-09-11")
    assert result["verdict"] == "PASS", result
    assert "0 without a verdict row" in result["evidence"]


def test_chef_verdict_rows_warns_when_a_testing_card_has_no_verdict_row(monkeypatch, tmp_path):
    monkeypatch.setattr(ca, "REPO", tmp_path)
    now = datetime.now(timezone.utc)
    fresh_ts = ca.et_now(now_utc=now).strftime("%Y-%m-%d %H:%M:%S ET")
    vp = tmp_path / "analysis" / "recommendations" / "station-verdicts.jsonl"
    vp.parent.mkdir(parents=True, exist_ok=True)
    vp.write_text(json.dumps({"ts_et": fresh_ts, "card_id": "c1", "spec": {}, "result": {}}) + "\n",
                 encoding="utf-8")
    bp = tmp_path / "automation" / "state" / "station" / "ideas-board.json"
    bp.parent.mkdir(parents=True, exist_ok=True)
    # c2 is 'testing' but never appears in the verdicts ledger -- must be flagged.
    bp.write_text(json.dumps([{"id": "c1", "status": "testing"}, {"id": "c2", "status": "testing"}]),
                 encoding="utf-8")

    result = ca._gt_chef_verdict_rows(_chef_gt(), now, "2026-09-11")
    assert result["verdict"] == "WARN"
    assert "1 testing card(s) have no verdict row" in result["evidence"]


def test_chef_verdict_rows_warns_when_stale(monkeypatch, tmp_path):
    monkeypatch.setattr(ca, "REPO", tmp_path)
    now = datetime.now(timezone.utc)
    stale_ts = ca.et_now(now_utc=now - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S ET")
    vp = tmp_path / "analysis" / "recommendations" / "station-verdicts.jsonl"
    vp.parent.mkdir(parents=True, exist_ok=True)
    vp.write_text(json.dumps({"ts_et": stale_ts, "card_id": "c1", "spec": {}, "result": {}}) + "\n",
                 encoding="utf-8")
    bp = tmp_path / "automation" / "state" / "station" / "ideas-board.json"
    bp.parent.mkdir(parents=True, exist_ok=True)
    bp.write_text(json.dumps([]), encoding="utf-8")

    result = ca._gt_chef_verdict_rows(_chef_gt(), now, "2026-09-11")
    assert result["verdict"] == "WARN"
    assert "stale" in result["evidence"]


def _coach_gt(**overrides) -> dict:
    gt = {"kind": "coach_sectors_fresh", "path": "automation/state/station/sectors.json", "max_age_min": 60}
    gt.update(overrides)
    return gt


def test_coach_sectors_fresh_fails_when_file_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(ca, "REPO", tmp_path)
    result = ca._gt_coach_sectors_fresh(_coach_gt(), datetime.now(timezone.utc), "2026-09-11")
    assert result["verdict"] == "FAIL"
    assert "missing" in result["evidence"].lower()


def test_coach_sectors_fresh_fails_when_file_unparseable(monkeypatch, tmp_path):
    monkeypatch.setattr(ca, "REPO", tmp_path)
    p = tmp_path / "automation" / "state" / "station" / "sectors.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("not json", encoding="utf-8")
    result = ca._gt_coach_sectors_fresh(_coach_gt(), datetime.now(timezone.utc), "2026-09-11")
    assert result["verdict"] == "FAIL"


def test_coach_sectors_fresh_passes_when_fresh_and_carries_summary_line(monkeypatch, tmp_path):
    monkeypatch.setattr(ca, "REPO", tmp_path)
    now = datetime.now(timezone.utc)
    fresh_ts = ca.et_now(now_utc=now).strftime("%Y-%m-%d %H:%M:%S ET")
    p = tmp_path / "automation" / "state" / "station" / "sectors.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"ts_et": fresh_ts, "rows": [],
                             "summary_line": "8 lanes -- 6 GREEN . 0 RED . 1 frozen",
                             "task_health": {}}), encoding="utf-8")

    result = ca._gt_coach_sectors_fresh(_coach_gt(), now, "2026-09-11")
    assert result["verdict"] == "PASS", result
    assert "8 lanes -- 6 GREEN . 0 RED . 1 frozen" in result["evidence"], (
        "evidence must carry the file's own summary_line")


def test_coach_sectors_fresh_warns_when_stale(monkeypatch, tmp_path):
    monkeypatch.setattr(ca, "REPO", tmp_path)
    now = datetime.now(timezone.utc)
    stale_ts = ca.et_now(now_utc=now - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S ET")
    p = tmp_path / "automation" / "state" / "station" / "sectors.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"ts_et": stale_ts, "rows": [], "summary_line": "x", "task_health": {}}),
                encoding="utf-8")

    result = ca._gt_coach_sectors_fresh(_coach_gt(), now, "2026-09-11")
    assert result["verdict"] == "WARN"
    assert "stale" in result["evidence"]


def test_coach_sectors_fresh_warns_when_ts_et_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(ca, "REPO", tmp_path)
    p = tmp_path / "automation" / "state" / "station" / "sectors.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"rows": [], "summary_line": "x", "task_health": {}}), encoding="utf-8")

    result = ca._gt_coach_sectors_fresh(_coach_gt(), datetime.now(timezone.utc), "2026-09-11")
    assert result["verdict"] == "WARN"
    assert "ts_et" in result["evidence"]


def test_chef_and_coach_kinds_registered_in_ground_truth_checks():
    assert "chef_verdict_rows" in ca.GROUND_TRUTH_CHECKS
    assert "coach_sectors_fresh" in ca.GROUND_TRUTH_CHECKS
    assert ca.GROUND_TRUTH_CHECKS["chef_verdict_rows"] is ca._gt_chef_verdict_rows
    assert ca.GROUND_TRUTH_CHECKS["coach_sectors_fresh"] is ca._gt_coach_sectors_fresh


# ============================================================================
# The documented JSON shape -- one real --no-llm CLI run against the real repo
# (no network; does enumerate the real Task Scheduler, same as a human's fire)
# ============================================================================

def test_no_llm_cli_run_produces_the_documented_json_shape():
    rc = ca.main(["--no-llm"])
    assert rc == 0

    out_path = REPO / "automation" / "state" / "station" / "company-audit.json"
    out = json.loads(out_path.read_text(encoding="utf-8"))

    for key in ("ts_et", "last_trading_day", "llm_used", "llm_model", "llm_skip_reason",
                "runtime_s", "personas", "summary"):
        assert key in out, f"missing top-level key {key!r}"
    assert out["llm_used"] is False
    assert out["llm_model"] is None

    assert len(out["personas"]) == 7
    assert set(out["summary"].keys()) == {"pass", "warn", "fail", "total"}
    assert out["summary"]["total"] == 7
    assert out["summary"]["pass"] + out["summary"]["warn"] + out["summary"]["fail"] == 7

    for p in out["personas"]:
        assert p["verdict"] in ("PASS", "WARN", "FAIL")
        assert p["quiz"]["verdict"] == "SKIPPED"  # --no-llm: no quiz was ever asked
        for axis in ("works", "has_goal", "is_smart", "autonomous"):
            check = p["checks"][axis]
            assert check["verdict"] in ("PASS", "WARN", "FAIL")
            assert isinstance(check["evidence"], str) and check["evidence"]


# ============================================================================
# Regression locks for two live bugs caught while building this
# ============================================================================

def test_last_trading_day_grades_friday_not_an_empty_monday_night():
    """LIVE BUG (caught building this): the first cut anchored to `now`'s own ET date,
    so a run at 00:24 ET on a brand-new Monday resolved to Monday itself (a weekday) and
    graded every persona against a day nobody had worked yet. Today only counts once its
    session is plausibly over (16:00 ET)."""
    monday_0024_et = datetime(2026, 9, 14, 4, 24, tzinfo=timezone.utc)  # 00:24 EDT
    assert ca._last_trading_day(monday_0024_et) == "2026-09-11"

    monday_1700_et = datetime(2026, 9, 14, 21, 0, tzinfo=timezone.utc)  # 17:00 EDT
    assert ca._last_trading_day(monday_1700_et) == "2026-09-14"

    sunday_noon_et = datetime(2026, 9, 13, 16, 0, tzinfo=timezone.utc)  # 12:00 EDT
    assert ca._last_trading_day(sunday_noon_et) == "2026-09-11"


def test_cadence_window_is_per_task_not_the_blended_persona_sentence():
    """LIVE BUG: Coach's roster `cadence` is one sentence covering FOUR tasks with
    different real cadences ('06:00 ET daily' AND 'every 30 min' AND 'every 5 min' AND
    '17:30 ET daily'). Regexing that one string picked the tightest match (every 30 min)
    and applied it to all four, false-FAILing the two once-a-day tasks all night.
    _task_cadence_text must resolve each task's OWN cadence independently."""
    daily_text = ca._task_cadence_text("Gamma_CryptoDaily", "irrelevant blended sentence")
    thirty_min_text = ca._task_cadence_text("Gamma_CryptoRegression", "irrelevant blended sentence")
    assert "every" not in daily_text.lower()
    assert "every 30 min" in thirty_min_text

    now_et = datetime(2026, 9, 14, 2, 0)  # naive ET, well outside a weekend gap
    daily_window = ca._cadence_window(daily_text, now_et)
    thirty_min_window = ca._cadence_window(thirty_min_text, now_et)
    assert daily_window > timedelta(hours=10)
    assert thirty_min_window < timedelta(hours=2)


def test_heartbeat_core_relaxes_outside_rth_but_stays_tight_inside_it():
    """LIVE BUG: Pilot's Gamma_HeartbeatCore ('every 1 min, 09:30-15:55 ET weekdays') is
    silent by design outside market hours; a flat 'every 1 min -> 3 min window' read it
    as stale every single evening. Outside the RTH range it must relax to the daily
    window; inside the range it must stay tight."""
    cadence = ca._TASK_CADENCE["Gamma_HeartbeatCore"]
    midnight_et = datetime(2026, 9, 15, 0, 30)  # naive ET, Tuesday, market closed
    midday_et = datetime(2026, 9, 15, 11, 0)    # naive ET, Tuesday, inside 09:30-15:55

    assert ca._cadence_window(cadence, midnight_et) >= timedelta(hours=10)
    assert ca._cadence_window(cadence, midday_et) <= timedelta(minutes=15)


@pytest.mark.parametrize("checks,answer,expected", [
    ([{"type": "substring", "value": "hello"}], "well hello there", True),
    ([{"type": "substring", "value": "hello"}], "goodbye", False),
    ([{"type": "regex", "value": r"ANSWER:\s*7\b"}], "math... ANSWER: 7", True),
    ([{"type": "regex", "value": r"ANSWER:\s*7\b"}], "ANSWER: 8", False),
    ([{"type": "substring", "value": "a"}, {"type": "substring", "value": "b"}], "a and b", True),
    ([{"type": "substring", "value": "a"}, {"type": "substring", "value": "b"}], "only a", False),
])
def test_quiz_check_passes_requires_every_check(checks, answer, expected):
    assert ca._quiz_check_passes(answer, checks) is expected


def test_worse_orders_fail_over_warn_over_pass_and_skipped_is_neutral():
    assert ca._worse("PASS", "WARN") == "WARN"
    assert ca._worse("WARN", "FAIL") == "FAIL"
    assert ca._worse("PASS", "SKIPPED") == "PASS"
    assert ca._worse("FAIL", "SKIPPED") == "FAIL"
