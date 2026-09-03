"""Guards for `learning_ledger.py` (filed 2026-09-03) -- the deterministic $0 roll-up of
"what Gamma learned" that the home page renders. See CLAUDE.md for the WHY (Kitchen runs
3,787+ completed tasks, dozens of preregs, hundreds of shadow rows -- nothing rolled it up,
so J experienced Gamma as idle).

PUBLIC CONTRACT under test (gamma_home.py imports this lazily -- must not silently change
shape): DEFAULT_OUT, build(now_et=None) -> dict, write(d, path=None) -> Path,
load(path=None) -> dict | None, and the CLI ([--json] [--out PATH] [--now ISO]).

Every module-level path constant is monkeypatched onto tmp_path fixtures so the real repo
is NEVER read by these tests -- the module is loaded fresh per test via
importlib.util.spec_from_file_location (same pattern as
test_conductor_outcome_zero_enter_grading_2026_09_03.py), so real() reads of CLAUDE.md/
LESSONS-LEARNED.md/etc. cannot leak in.

Run with:
    backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_learning_ledger_2026_09_03.py -q
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

_MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "setup" / "scripts" / "learning_ledger.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("learning_ledger_under_test", _MODULE_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def ll(tmp_path, monkeypatch):
    """Module with EVERY source path constant redirected under tmp_path -- the real repo
    is never touched."""
    mod = _load_module()
    root = tmp_path / "repo"
    (root / "automation" / "state").mkdir(parents=True)
    (root / "strategy" / "candidates" / "_analysis").mkdir(parents=True)
    (root / "analysis" / "recommendations").mkdir(parents=True)
    (root / "analysis" / "entry-quality").mkdir(parents=True)
    (root / "analysis" / "arm-ladder").mkdir(parents=True)
    (root / "analysis" / "prod-shadow").mkdir(parents=True)
    (root / "analysis" / "self-audit").mkdir(parents=True)
    (root / "markdown" / "doctrine").mkdir(parents=True)

    monkeypatch.setattr(mod, "REPO", root)
    monkeypatch.setattr(mod, "COOK_QUEUE_FILE", root / "automation" / "state" / "cook-queue.jsonl")
    monkeypatch.setattr(mod, "KITCHEN_STATUS_FILE",
                         root / "automation" / "state" / "kitchen-status.json")
    monkeypatch.setattr(mod, "CANDIDATES_DIR", root / "strategy" / "candidates")
    monkeypatch.setattr(mod, "ANALYSIS_DIR", root / "strategy" / "candidates" / "_analysis")
    monkeypatch.setattr(mod, "RECOMMENDATIONS_DIR", root / "analysis" / "recommendations")
    monkeypatch.setattr(mod, "ENTRY_QUALITY_SHADOW_FILE",
                         root / "analysis" / "entry-quality" / "shadow-tally.jsonl")
    monkeypatch.setattr(mod, "LADDER_SHADOW_FILE",
                         root / "analysis" / "arm-ladder" / "ladder-rung-shadow-ledger.jsonl")
    monkeypatch.setattr(mod, "PROD_SHADOW_FILE", root / "analysis" / "prod-shadow" / "ledger.jsonl")
    monkeypatch.setattr(mod, "SHADOW_SUMMARY_FILE",
                         root / "analysis" / "entry-quality" / "shadow-summary.json")
    monkeypatch.setattr(mod, "CONDUCTOR_OUTCOMES_FILE",
                         root / "automation" / "state" / "conductor-outcomes.jsonl")
    monkeypatch.setattr(mod, "SELF_AUDIT_GAP_LOG", root / "analysis" / "self-audit" / "gap-log.jsonl")
    monkeypatch.setattr(mod, "STUDY_CURRICULUM_FILE",
                         root / "markdown" / "doctrine" / "STUDY-CURRICULUM.md")
    monkeypatch.setattr(mod, "LESSONS_FILE", root / "markdown" / "doctrine" / "LESSONS-LEARNED.md")
    monkeypatch.setattr(mod, "DEFAULT_OUT", root / "automation" / "state" / "learning-ledger.json")
    mod._root = root  # convenience handle for tests
    return mod


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows) + ("\n" if rows else ""),
                     encoding="utf-8")


# ---------------------------------------------------------------------------
# Windows: ET calendar day math around a fixed --now.
# ---------------------------------------------------------------------------

def test_windows_today_and_7d_around_fixed_now(ll):
    # now = 2026-09-03 18:00 ET (naive -- treated as already-ET per module convention)
    now = datetime(2026, 9, 3, 18, 0, 0)
    _write_jsonl(ll.COOK_QUEUE_FILE, [
        {"event": "complete", "task_id": "a", "ts": "2026-09-03T20:00:00+00:00"},  # today ET
        {"event": "complete", "task_id": "b", "ts": "2026-08-28T20:00:00+00:00"},  # 6 days ago
        {"event": "complete", "task_id": "c", "ts": "2026-08-27T20:00:00+00:00"},  # 7 days ago -> OUT
        {"event": "claim", "task_id": "d", "ts": "2026-09-03T20:00:00+00:00"},     # not "complete"
    ])
    d = ll.build(now_et=now)
    assert d["today_et"] == "2026-09-03"
    assert d["windows"]["today"]["kitchen_tasks_completed"] == 1
    assert d["windows"]["7d"]["kitchen_tasks_completed"] == 2  # a + b, c falls outside


def test_cook_queue_day_boundary_across_utc_et_offset(ll):
    """A UTC timestamp just after midnight UTC can still be the PRIOR ET day (EDT = UTC-4).
    2026-09-03T02:00:00+00:00 is 2026-09-02T22:00:00 ET -- must NOT count as 09-03."""
    now = datetime(2026, 9, 3, 12, 0, 0)
    _write_jsonl(ll.COOK_QUEUE_FILE, [
        {"event": "complete", "task_id": "x", "ts": "2026-09-03T02:00:00+00:00"},  # -> 09-02 ET
        {"event": "complete", "task_id": "y", "ts": "2026-09-03T13:00:00+00:00"},  # -> 09-03 ET
    ])
    d = ll.build(now_et=now)
    assert d["windows"]["today"]["kitchen_tasks_completed"] == 1


# ---------------------------------------------------------------------------
# Missing source -> NO DATA + errors; present-but-empty -> 0.
# ---------------------------------------------------------------------------

def test_missing_source_is_no_data_with_reason(ll):
    now = datetime(2026, 9, 3, 12, 0, 0)
    # COOK_QUEUE_FILE deliberately never written -> does not exist.
    d = ll.build(now_et=now)
    assert d["windows"]["today"]["kitchen_tasks_completed"] == "NO DATA"
    assert d["windows"]["7d"]["kitchen_tasks_completed"] == "NO DATA"
    assert "kitchen_tasks_completed" in d["errors"]
    assert "cook-queue.jsonl" in d["errors"]["kitchen_tasks_completed"]


def test_present_but_empty_source_is_zero_not_no_data(ll):
    now = datetime(2026, 9, 3, 12, 0, 0)
    ll.COOK_QUEUE_FILE.write_text("", encoding="utf-8")  # exists, zero rows
    d = ll.build(now_et=now)
    assert d["windows"]["today"]["kitchen_tasks_completed"] == 0
    assert d["windows"]["7d"]["kitchen_tasks_completed"] == 0
    assert "kitchen_tasks_completed" not in d["errors"]


def test_build_never_raises_when_every_source_is_garbage(tmp_path, monkeypatch):
    """A totally empty tmp_path -- no directories pre-created at all (unlike the shared
    `ll` fixture, which mkdirs several dirs so directory-backed sources legitimately read
    as empty/0). Here every single source, file AND directory, is genuinely absent, so
    build() must degrade every count key to NO DATA without raising."""
    mod = _load_module()
    root = tmp_path / "totally-empty-repo"  # deliberately never created
    monkeypatch.setattr(mod, "REPO", root)
    monkeypatch.setattr(mod, "COOK_QUEUE_FILE", root / "automation" / "state" / "cook-queue.jsonl")
    monkeypatch.setattr(mod, "KITCHEN_STATUS_FILE",
                         root / "automation" / "state" / "kitchen-status.json")
    monkeypatch.setattr(mod, "CANDIDATES_DIR", root / "strategy" / "candidates")
    monkeypatch.setattr(mod, "ANALYSIS_DIR", root / "strategy" / "candidates" / "_analysis")
    monkeypatch.setattr(mod, "RECOMMENDATIONS_DIR", root / "analysis" / "recommendations")
    monkeypatch.setattr(mod, "ENTRY_QUALITY_SHADOW_FILE",
                         root / "analysis" / "entry-quality" / "shadow-tally.jsonl")
    monkeypatch.setattr(mod, "LADDER_SHADOW_FILE",
                         root / "analysis" / "arm-ladder" / "ladder-rung-shadow-ledger.jsonl")
    monkeypatch.setattr(mod, "PROD_SHADOW_FILE", root / "analysis" / "prod-shadow" / "ledger.jsonl")
    monkeypatch.setattr(mod, "CONDUCTOR_OUTCOMES_FILE",
                         root / "automation" / "state" / "conductor-outcomes.jsonl")
    monkeypatch.setattr(mod, "SELF_AUDIT_GAP_LOG", root / "analysis" / "self-audit" / "gap-log.jsonl")
    monkeypatch.setattr(mod, "STUDY_CURRICULUM_FILE",
                         root / "markdown" / "doctrine" / "STUDY-CURRICULUM.md")
    monkeypatch.setattr(mod, "LESSONS_FILE", root / "markdown" / "doctrine" / "LESSONS-LEARNED.md")

    now = datetime(2026, 9, 3, 12, 0, 0)
    d = mod.build(now_et=now)
    for key, val in d["windows"]["today"].items():
        assert val == "NO DATA", f"{key} should be NO DATA when its source is entirely absent"
    for key, val in d["windows"]["7d"].items():
        assert val == "NO DATA"
    assert d["latest_verdicts"] == []
    assert isinstance(d["errors"], dict) and len(d["errors"]) > 0


# ---------------------------------------------------------------------------
# preregs: filed vs adjudicated.
# ---------------------------------------------------------------------------

def test_prereg_filed_vs_adjudicated(ll):
    now = datetime(2026, 9, 3, 12, 0, 0)
    recs = ll.RECOMMENDATIONS_DIR
    # Filed today (by filename date), status not yet terminal -> filed but not adjudicated.
    (recs / "prereg-alpha-2026-09-03.json").write_text(
        json.dumps({"status": "FROZEN -- NOT RUN"}), encoding="utf-8")
    # Filed via filed_at field (filename date is old), status IS terminal.
    (recs / "prereg-beta-2026-07-01.json").write_text(
        json.dumps({"status": "RUN_COMPLETE_KILL", "filed_at": "2026-09-03T10:00:00",
                    "adjudicated_at": "2026-09-03T11:00:00"}),
        encoding="utf-8")
    # Old file, old adjudication -- outside both windows.
    (recs / "prereg-gamma-2026-01-01.json").write_text(
        json.dumps({"status": "SHIP", "adjudicated_at": "2026-01-02T00:00:00"}),
        encoding="utf-8")
    d = ll.build(now_et=now)
    assert d["windows"]["today"]["preregs_filed"] == 2  # alpha (filename) + beta (filed_at)
    assert d["windows"]["today"]["preregs_adjudicated"] == 1  # beta only (adjudicated_at today)
    assert d["windows"]["7d"]["preregs_filed"] == 2
    assert d["windows"]["7d"]["preregs_adjudicated"] == 1


def test_prereg_no_ship_is_not_misread_as_ship(ll):
    now = datetime(2026, 9, 3, 12, 0, 0)
    (ll.RECOMMENDATIONS_DIR / "prereg-delta-2026-09-03.json").write_text(
        json.dumps({"status": "RUN_COMPLETE -- NO-SHIP -- all 4 gates FAIL"}),
        encoding="utf-8")
    d = ll.build(now_et=now)
    kinds = {v["subject"]: v["kind"] for v in d["latest_verdicts"]}
    assert kinds.get("prereg-delta-2026-09-03") == "FAIL"


# ---------------------------------------------------------------------------
# latest_verdicts: sorted newest-first, capped at 12, each carries a source path.
# ---------------------------------------------------------------------------

def test_verdicts_sorted_newest_first_and_capped_at_12(ll):
    now = datetime(2026, 9, 3, 12, 0, 0)
    recs = ll.RECOMMENDATIONS_DIR
    for i in range(15):
        (recs / f"prereg-item{i:02d}-2026-08-01.json").write_text(
            json.dumps({"status": "KILL",
                        "adjudicated_at": f"2026-08-{(i % 28) + 1:02d}T00:00:00"}),
            encoding="utf-8")
    d = ll.build(now_et=now)
    verdicts = d["latest_verdicts"]
    assert len(verdicts) == 12
    dates = [v["at_et"] for v in verdicts]
    assert dates == sorted(dates, reverse=True)
    for v in verdicts:
        assert v["source"].startswith("analysis/recommendations/")
        assert v["kind"] in ll.VERDICT_KINDS


# ---------------------------------------------------------------------------
# git failure -> NO DATA (subprocess.run monkeypatched to fail).
# ---------------------------------------------------------------------------

def test_git_failure_is_no_data(ll, monkeypatch):
    now = datetime(2026, 9, 3, 12, 0, 0)

    def _boom(*args, **kwargs):
        raise FileNotFoundError("git not found")

    monkeypatch.setattr(ll.subprocess, "run", _boom)
    d = ll.build(now_et=now)
    assert d["windows"]["today"]["commits"] == "NO DATA"
    assert d["windows"]["7d"]["commits"] == "NO DATA"
    assert "commits" in d["errors"]


def test_git_nonzero_exit_is_no_data(ll, monkeypatch):
    now = datetime(2026, 9, 3, 12, 0, 0)

    class _Result:
        returncode = 128
        stdout = ""
        stderr = "fatal: not a git repository"

    monkeypatch.setattr(ll.subprocess, "run", lambda *a, **k: _Result())
    d = ll.build(now_et=now)
    assert d["windows"]["today"]["commits"] == "NO DATA"
    assert "commits" in d["errors"]


# ---------------------------------------------------------------------------
# CLI: writes the file and prints a summary line (or --json).
# ---------------------------------------------------------------------------

def test_cli_writes_file_and_prints_summary(ll, monkeypatch, capsys):
    now_iso = "2026-09-03T12:00:00"
    ll.COOK_QUEUE_FILE.write_text("", encoding="utf-8")
    out_path = ll._root / "custom-out.json"
    rc = ll.main(["--out", str(out_path), "--now", now_iso])
    assert rc == 0
    captured = capsys.readouterr()
    assert "learning-ledger" in captured.out
    assert str(out_path) in captured.out or out_path.name in captured.out
    assert out_path.exists()
    on_disk = json.loads(out_path.read_text(encoding="utf-8"))
    assert on_disk["today_et"] == "2026-09-03"


def test_cli_json_flag_prints_full_json(ll, capsys):
    now_iso = "2026-09-03T12:00:00"
    rc = ll.main(["--json", "--now", now_iso])
    assert rc == 0
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["today_et"] == "2026-09-03"
    assert "windows" in parsed and "sources" in parsed and "methods" in parsed


# ---------------------------------------------------------------------------
# write() / load() round-trip.
# ---------------------------------------------------------------------------

def test_write_and_load_round_trip(ll):
    now = datetime(2026, 9, 3, 12, 0, 0)
    d = ll.build(now_et=now)
    path = ll._root / "ledger.json"
    written = ll.write(d, path)
    assert written == path
    assert path.exists()
    loaded = ll.load(path)
    assert loaded == d


def test_load_missing_file_returns_none(ll):
    missing = ll._root / "does-not-exist.json"
    assert ll.load(missing) is None


def test_load_malformed_json_returns_none(ll):
    path = ll._root / "malformed.json"
    path.write_text("{not valid json", encoding="utf-8")
    assert ll.load(path) is None


# ---------------------------------------------------------------------------
# RED-proof: break a counting rule, watch the guard fail, then restore it.
# ---------------------------------------------------------------------------

def test_red_proof_cook_queue_window_boundary():
    """If the ET-day-boundary conversion regresses to naive UTC-as-ET (the historical
    TZ-SYSTEMIC bug class this repo has been bitten by before), this test must fail."""
    mod = _load_module()
    root_dir = _MODULE_PATH.parent  # unused; just proving the module loads standalone
    assert root_dir.exists()

    # Simulate the broken behavior directly: treating an aware UTC ts as if its wall-clock
    # were already ET (i.e. NOT converting) would count 2026-09-03T02:00:00+00:00 as ET
    # 09-03, when it is actually ET 09-02 (EDT = UTC-4). Assert the CORRECT module does NOT
    # produce that (this is the behavior test_cook_queue_day_boundary_across_utc_et_offset
    # already proves positively) -- here we prove the naive-broken version WOULD differ,
    # so the test suite is actually discriminating and not vacuously true.
    ts = "2026-09-03T02:00:00+00:00"
    naive_broken_date = ts[:10]  # "2026-09-03" -- the wrong answer a naive impl would give
    correct_date = mod._to_et_date(ts).isoformat()
    assert correct_date == "2026-09-02"
    assert correct_date != naive_broken_date, (
        "RED-PROOF FAILED: the naive (bug-reproducing) date computation now matches the "
        "module's real output -- the discriminating test above would no longer catch a "
        "regression back to naive-UTC-as-ET."
    )


def test_red_proof_missing_source_must_not_silently_be_zero(ll):
    """If build() regressed to defaulting a missing source to 0 instead of 'NO DATA', this
    test fails -- proving the guard actually discriminates the two cases."""
    now = datetime(2026, 9, 3, 12, 0, 0)
    # COOK_QUEUE_FILE not written -> missing.
    d = ll.build(now_et=now)
    val = d["windows"]["today"]["kitchen_tasks_completed"]
    assert val == "NO DATA", (
        f"RED-PROOF FAILED: missing source produced {val!r} instead of the required "
        "'NO DATA' sentinel -- C7 (silent success is failure) would be violated."
    )
    # Now prove the FIX actually distinguishes from the empty-but-present case (same file,
    # touched empty) -- these two must NOT collapse to the same value.
    ll.COOK_QUEUE_FILE.write_text("", encoding="utf-8")
    d2 = ll.build(now_et=now)
    assert d2["windows"]["today"]["kitchen_tasks_completed"] == 0
    assert d2["windows"]["today"]["kitchen_tasks_completed"] != val


# ---------------------------------------------------------------- prose sources are not status fields (2026-09-03 fix)

def test_kitchen_task_description_with_failed_is_not_a_verdict(tmp_path, monkeypatch):
    """Caught on the first real run: a kitchen task DESCRIPTION reading 'Investigate why 4
    accepted orders failed to fill' was scored as a FAIL verdict with the opaque task hash as
    its subject. Prose sources only yield unambiguous tokens (NO-LIFT / keepers / KILL /
    NULL / NO-SHIP / 'verdict ... pass|fail'), and the subject is the task text."""
    import learning_ledger as ll
    ks = tmp_path / "kitchen-status.json"
    ks.write_text(json.dumps({"recent_completed_top_10": [
        {"task_id": "deadbeef", "task": "Investigate why 4 accepted orders failed to fill",
         "completed_at": "2026-09-03T21:47:57+00:00"},
        {"task_id": "cafef00d", "task": "Interpret grinder output: 5 keepers found. Top wide_pnl=587",
         "completed_at": "2026-09-03T21:40:00+00:00"},
    ]}), encoding="utf-8")
    monkeypatch.setattr(ll, "KITCHEN_STATUS_FILE", ks)
    rows = ll._verdicts_from_kitchen_status()
    assert [r["kind"] for r in rows] == ["KEEPER"], rows
    assert rows[0]["subject"].startswith("Interpret grinder output"), rows[0]
    assert rows[0]["at_et"].endswith("ET") and "17:40" in rows[0]["at_et"], rows[0]["at_et"]
