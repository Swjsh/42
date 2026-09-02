"""Guard for the prereg_hygiene results-file detection fix (2026-09-02).

THE BUG THIS CLOSES: prereg_hygiene.py flags a prereg only on stale-status-text +
age>14d + orphan. It never checked whether a companion result file already exists on
disk. Confirmed live 2026-09-02: 6 real preregs (recency-qty-clamp, ladder-vwap,
pdt-blocked-counterfactual, expected-move-gate, morning-gate, entry-structure-forward)
sat with a stale FROZEN/PENDING status while a completed verdict already existed in a
sibling *-results.json -- and one (PDT counterfactual) was RE-RUN FROM SCRATCH the
same night by an earlier fire before the duplication was caught, burning real
compute on an answer that already existed on disk.

Pins:
  - a prereg matched to an existing result (by rule_id, by a result's `registration`
    field naming the prereg, or by the observed filename heuristic) is NEVER flagged
    as "FROZEN/NOT RUN", even when its own status/age/orphan would otherwise qualify
  - self-match is excluded: a prereg carrying its own rule_id with no separate result
    file must not be reported as "has a matching result" (the bug caught while
    building this fix -- first pass wrongly self-matched 18 files)
  - `entries[].has_results_file` / `result_file` are populated for every prereg
  - `stale_status_but_has_results` surfaces exactly the reconciliation candidates --
    stale-status text but a real result exists -- so a future adjudication pass
    doesn't have to re-discover this by hand or re-run the study
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_PH_PATH = _REPO / "setup" / "scripts" / "prereg_hygiene.py"
_spec = importlib.util.spec_from_file_location("prereg_hygiene_results_under_test", _PH_PATH)
prereg_hygiene = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(prereg_hygiene)


def _write(path: Path, obj) -> None:
    path.write_text(json.dumps(obj), encoding="utf-8")


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    recs = tmp_path / "analysis" / "recommendations"
    recs.mkdir(parents=True)
    setup_dir = tmp_path / "setup"
    setup_dir.mkdir()
    backtest_dir = tmp_path / "backtest"
    backtest_dir.mkdir()
    automation_dir = tmp_path / "automation" / "overnight"
    automation_dir.mkdir(parents=True)
    status_md = automation_dir / "STATUS.md"
    status_md.write_text("# status\n", encoding="utf-8")

    monkeypatch.setattr(prereg_hygiene, "REPO", tmp_path)
    monkeypatch.setattr(prereg_hygiene, "RECS_DIR", recs)
    monkeypatch.setattr(prereg_hygiene, "OUT_FILE", recs / "prereg-hygiene.json")
    monkeypatch.setattr(prereg_hygiene, "STATUS_MD", status_md)
    monkeypatch.setattr(prereg_hygiene, "SEARCH_DIRS", ["setup", "backtest", "automation"])
    monkeypatch.setattr(prereg_hygiene, "EXCLUDE_PATHS", {status_md.resolve()})
    monkeypatch.setattr(prereg_hygiene, "_referenced_stems", lambda stems: None)
    return {"recs": recs}


def test_rule_id_match_suppresses_the_flag(sandbox):
    """A prereg that would otherwise flag (stale status + old + orphan) must NOT flag
    once a sibling result file carrying the SAME rule_id exists -- the recency-qty-clamp
    shape found live."""
    recs = sandbox["recs"]
    prereg = recs / "prereg-widget-clamp-2026-08-01.json"
    _write(prereg, {
        "status": "FROZEN_BEFORE_RUNNER", "frozen_at_et": "2026-08-01T00:00:00",
        "rule_id": "WIDGET-CLAMP-2026-08-01",
    })
    _write(recs / "widget-clamp-2026-08-01-results.json", {
        "rule_id": "WIDGET-CLAMP-2026-08-01", "verdict": "FAIL -- clamp stays",
    })
    report = prereg_hygiene.scan()
    assert report["n_flagged"] == 0
    entry = next(e for e in report["entries"] if e["file"] == prereg.name)
    assert entry["has_results_file"] is True
    assert entry["result_file"] == "widget-clamp-2026-08-01-results.json"


def test_registration_field_match_suppresses_the_flag(sandbox):
    """A result file that names its source prereg via `registration` (the older
    convention -- expected-move-gate / morning-gate shape) must also suppress the flag,
    even with no shared rule_id."""
    recs = sandbox["recs"]
    prereg = recs / "prereg-gate-2026-08-01.json"
    _write(prereg, {"status": "FROZEN_PENDING_RUN", "frozen_at_et": "2026-08-01T00:00:00"})
    _write(recs / "gate-result.json", {
        "registration": "analysis/recommendations/prereg-gate-2026-08-01.json",
        "verdict": "PASS",
    })
    report = prereg_hygiene.scan()
    assert report["n_flagged"] == 0
    entry = next(e for e in report["entries"] if e["file"] == prereg.name)
    assert entry["has_results_file"] is True
    assert entry["result_file"] == "gate-result.json"


def test_filename_heuristic_match_suppresses_the_flag(sandbox):
    """No rule_id, no registration field -- falls back to the observed filename
    convention (strip leading 'prereg-', append '-results.json')."""
    recs = sandbox["recs"]
    prereg = recs / "prereg-ladder-vwap-2026-08-01.json"
    _write(prereg, {"status": "FROZEN_BEFORE_RUNNER", "frozen_at_et": "2026-08-01T00:00:00"})
    _write(recs / "ladder-vwap-2026-08-01-results.json", {"verdict": "NO-SHIP"})
    report = prereg_hygiene.scan()
    assert report["n_flagged"] == 0
    entry = next(e for e in report["entries"] if e["file"] == prereg.name)
    assert entry["has_results_file"] is True


def test_no_result_file_still_flags_normally(sandbox):
    """RED-PROOF the fix does not neuter the original flag: with no matching result at
    all, a genuinely stale/orphan/old prereg must still flag exactly as before."""
    recs = sandbox["recs"]
    prereg = recs / "prereg-truly-unrun-2026-08-01.json"
    _write(prereg, {"status": "FROZEN -- NOT RUN", "frozen_at_et": "2026-08-01T00:00:00"})
    report = prereg_hygiene.scan()
    assert report["n_flagged"] == 1
    assert report["flagged"][0]["file"] == prereg.name
    entry = next(e for e in report["entries"] if e["file"] == prereg.name)
    assert entry["has_results_file"] is False
    assert entry["result_file"] is None


def test_self_match_excluded_rule_id(sandbox):
    """RED-PROOF the self-match bug caught while building this fix: a prereg carrying
    its own rule_id, with no OTHER file sharing that rule_id, must not be reported as
    'has a matching result' (it would otherwise match itself and silently suppress a
    real flag)."""
    recs = sandbox["recs"]
    prereg = recs / "prereg-self-only-2026-08-01.json"
    _write(prereg, {
        "status": "FROZEN -- NOT RUN", "frozen_at_et": "2026-08-01T00:00:00",
        "rule_id": "SELF-ONLY-2026-08-01",
    })
    report = prereg_hygiene.scan()
    entry = next(e for e in report["entries"] if e["file"] == prereg.name)
    assert entry["has_results_file"] is False, "must not match its own rule_id to itself"
    assert report["n_flagged"] == 1, "a genuinely unmatched stale/orphan/old prereg must still flag"


def test_self_match_excluded_registration(sandbox):
    """RED-PROOF: a prereg file that (unusually) carries a `registration` field
    pointing at ITSELF must not be treated as its own result."""
    recs = sandbox["recs"]
    prereg = recs / "prereg-self-reg-2026-08-01.json"
    _write(prereg, {
        "status": "FROZEN -- NOT RUN", "frozen_at_et": "2026-08-01T00:00:00",
        "registration": "analysis/recommendations/prereg-self-reg-2026-08-01.json",
    })
    report = prereg_hygiene.scan()
    entry = next(e for e in report["entries"] if e["file"] == prereg.name)
    assert entry["has_results_file"] is False
    assert report["n_flagged"] == 1


def test_stale_status_but_has_results_surfaces_reconciliation_candidates(sandbox):
    """The new report key exists precisely to hand a future adjudication pass the
    exact list of preregs whose status text lies (says never-run) while a real
    result sits on disk -- so nobody has to re-derive this by hand, or re-run the
    study, the way the PDT counterfactual was accidentally re-run 2026-09-02."""
    recs = sandbox["recs"]
    prereg = recs / "prereg-widget-2026-08-01.json"
    _write(prereg, {
        "status": "FROZEN_BEFORE_RUNNER", "frozen_at_et": "2026-08-01T00:00:00",
        "rule_id": "WIDGET-2026-08-01",
    })
    _write(recs / "widget-2026-08-01-results.json", {
        "rule_id": "WIDGET-2026-08-01", "verdict": "FAIL",
    })
    report = prereg_hygiene.scan()
    candidates = {c["file"] for c in report["stale_status_but_has_results"]}
    assert prereg.name in candidates
    row = next(c for c in report["stale_status_but_has_results"] if c["file"] == prereg.name)
    assert row["result_file"] == "widget-2026-08-01-results.json"
