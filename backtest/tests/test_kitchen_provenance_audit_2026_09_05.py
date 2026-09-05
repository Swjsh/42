"""Guard: kitchen_provenance_audit correctly classifies OK / MISSING / NO-ARTIFACT files,
and kitchen_reviewer refuses to auto-promote a PROVENANCE-MISSING candidate.

Scar: _lesson-inbox/2026-09-05-kitchen-nemotron-fabricated-analysis-numbers.md -- three
independent Sonnet adjudication workers found chef-nemo `_analysis/*.md` verdicts citing
runner outputs (JSONs, tests) that were never produced. These tests RED if that path
ever reopens (a fabricated-but-well-formed citation silently clearing promotion).
"""
from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]


def _load_module(mod_name: str, rel_path: str):
    spec = importlib.util.spec_from_file_location(mod_name, _REPO / rel_path)
    m = importlib.util.module_from_spec(spec)
    # Register before exec: the module uses @dataclass, and dataclass's internal
    # _is_type() check looks the module up via sys.modules[cls.__module__] -- it must
    # already be registered or dataclass() raises AttributeError on a None lookup.
    sys.modules[mod_name] = m
    try:
        spec.loader.exec_module(m)
    finally:
        sys.modules.pop(mod_name, None)
    return m


kpa = _load_module("kitchen_provenance_audit_under_test", "setup/scripts/kitchen_provenance_audit.py")


# --------------------------------------------------------------------------------------------
# classify_file: OK / MISSING / NO-ARTIFACT-CITED / NOT-A-VERDICT
# --------------------------------------------------------------------------------------------

def test_provenance_ok_when_cited_artifact_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(kpa, "REPO", tmp_path)
    real = tmp_path / "analysis" / "recommendations" / "real_edge.json"
    real.parent.mkdir(parents=True)
    real.write_text(json.dumps({"edge_capture": 900}), encoding="utf-8")
    cand = tmp_path / "candidate-ok.md"
    cand.write_text(
        "Confidence 8/10. OOS expectancy +$0.42/trade. "
        "See analysis/recommendations/real_edge.json for the scorecard.\n",
        encoding="utf-8",
    )
    result = kpa.classify_file(cand)
    assert result.status == "PROVENANCE-OK", result
    assert result.missing == []
    assert "analysis/recommendations/real_edge.json" in result.cited


def test_provenance_missing_when_cited_artifact_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(kpa, "REPO", tmp_path)
    cand = tmp_path / "candidate-fabricated.md"
    cand.write_text(
        "Confidence 10/10. OOS expectancy +$0.42/trade. "
        "See analysis/recommendations/qqq_label_vol_strat_oos.json for the scorecard; "
        "must pass test_qqq_label_vol_strat.py.\n",
        encoding="utf-8",
    )
    result = kpa.classify_file(cand)
    assert result.status == "PROVENANCE-MISSING", result
    assert "analysis/recommendations/qqq_label_vol_strat_oos.json" in result.missing
    assert "test_qqq_label_vol_strat.py" in result.missing


def test_no_artifact_cited_when_numeric_but_no_citation(tmp_path, monkeypatch):
    monkeypatch.setattr(kpa, "REPO", tmp_path)
    cand = tmp_path / "candidate-no-cite.md"
    cand.write_text(
        "Confidence 9/10. Expectancy +$500 per trade, Sharpe=1.2. No artifact referenced.\n",
        encoding="utf-8",
    )
    result = kpa.classify_file(cand)
    assert result.status == "NO-ARTIFACT-CITED", result
    assert result.cited == []


def test_not_a_verdict_when_no_numeric_content(tmp_path, monkeypatch):
    monkeypatch.setattr(kpa, "REPO", tmp_path)
    cand = tmp_path / "candidate-idea-stub.md"
    cand.write_text("Brainstorm: maybe VWAP continuation has an edge on high-vol days.\n",
                    encoding="utf-8")
    result = kpa.classify_file(cand)
    assert result.status == "NOT-A-VERDICT", result


def test_run_audit_totals_and_rate(tmp_path, monkeypatch):
    monkeypatch.setattr(kpa, "REPO", tmp_path)
    ok = tmp_path / "ok.md"
    ok.write_text("Confidence 8/10 -- see analysis/recommendations/run.json", encoding="utf-8")
    (tmp_path / "analysis" / "recommendations").mkdir(parents=True)
    (tmp_path / "analysis" / "recommendations" / "run.json").write_text("{}", encoding="utf-8")
    missing = tmp_path / "missing.md"
    missing.write_text("Confidence 9/10 -- see analysis/recommendations/ghost.json", encoding="utf-8")
    no_artifact = tmp_path / "no-artifact.md"
    no_artifact.write_text("Confidence 7/10, no citation", encoding="utf-8")
    report = kpa.run_audit([ok, missing, no_artifact])
    assert report["totals"]["PROVENANCE-OK"] == 1
    assert report["totals"]["PROVENANCE-MISSING"] == 1
    assert report["totals"]["NO-ARTIFACT-CITED"] == 1
    # fabricated_artifact_rate = MISSING / scored(=3) = 1/3
    assert abs(report["fabricated_artifact_rate"] - (1 / 3)) < 1e-3


# --------------------------------------------------------------------------------------------
# kitchen_reviewer: PROVENANCE-MISSING must never auto-promote
# --------------------------------------------------------------------------------------------

def _load_kitchen_reviewer():
    fakes = {}
    for name in ("run_minimax", "kitchen_daemon"):
        if name not in sys.modules:
            mod = types.ModuleType(name)
            if name == "run_minimax":
                mod.call_minimax = lambda *a, **k: {"ok": False, "error": "stub"}
            else:
                mod.enqueue_task = lambda *a, **k: "stub-task-id"
                mod.MODEL_LADDER = []
            sys.modules[name] = mod
            fakes[name] = mod
    spec = importlib.util.spec_from_file_location(
        "kitchen_reviewer_provenance_under_test", _REPO / "setup" / "scripts" / "kitchen_reviewer.py")
    m = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(m)
    finally:
        for name in fakes:
            sys.modules.pop(name, None)
    return m


kr = _load_kitchen_reviewer()

# Hits all six _OP20_CHECKS keyword groups so only the provenance gate is under test.
_OP20_TEXT = """\
account size $2000 equity, qty=3 contracts
sample bias: in-sample n=40, overfit check done
out-of-sample walk-forward validation window
real fills via OPRA simulator_real
failure mode: max drawdown -$300 on the worst day
concentration: top-5 days 38% of P&L
"""


def _mk_repo(tmp_path, monkeypatch):
    cands = tmp_path / "strategy" / "candidates"
    cands.mkdir(parents=True)
    (tmp_path / "analysis" / "recommendations").mkdir(parents=True)
    monkeypatch.setattr(kr, "REPO", tmp_path)
    monkeypatch.setattr(kr, "CANDIDATES_DIR", cands)
    monkeypatch.setattr(kr, "REVIEW_LOG", cands / "_review-log.jsonl")
    return tmp_path, cands


def test_reviewer_refuses_provenance_missing_file(tmp_path, monkeypatch):
    """The RED-proofed assertion: a candidate that cites a scorecard JSON + test file that
    do not exist must be capped to VALIDATE, never PROMOTE, and never reach the leaderboard --
    even though its edge_capture-style numbers otherwise read as strong evidence."""
    repo, cands = _mk_repo(tmp_path, monkeypatch)
    cand = cands / "fabricated-chef-nemo.md"
    cand.write_text(
        _OP20_TEXT
        + "\nOOS expectancy +$0.42/trade (n=128); see "
          "analysis/recommendations/qqq_label_vol_strat_oos.json and "
          "test_qqq_label_vol_strat.py for the full run.\n",
        encoding="utf-8",
    )
    verdict, cap_reason = kr._cap_promote_if_unevidenced("PROMOTE", cand.name)
    assert verdict == "VALIDATE", verdict
    assert "PROVENANCE-MISSING" in cap_reason, cap_reason

    # And the full auto-promote path (as main() would call it) must not touch the leaderboard.
    result = kr._auto_promote_candidate(cand.name, "looks amazing per Nemotron")
    assert result.startswith("pending"), result
    lb = cands / "_LEADERBOARD.md"
    assert (not lb.exists()) or ("fabricated-chef-nemo" not in lb.read_text(encoding="utf-8"))


def test_reviewer_allows_provenance_ok_file_through_to_op16_gate(tmp_path, monkeypatch):
    """A candidate whose cited artifact DOES exist should not be capped by the provenance
    gate at all -- it still has to clear the separate OP-16 numeric-edge_capture floor,
    proving the two gates are independent (provenance-clean but weak-edge still fails on
    OP-16, not silently promoted just because provenance passed)."""
    repo, cands = _mk_repo(tmp_path, monkeypatch)
    scorecard = repo / "analysis" / "recommendations" / "real-edge-chef-nemo.json"
    scorecard.write_text(json.dumps({"edge_capture": 100.0}), encoding="utf-8")
    cand = cands / "real-edge-chef-nemo.md"
    cand.write_text(
        _OP20_TEXT + "\nsee analysis/recommendations/real-edge-chef-nemo.json\n",
        encoding="utf-8",
    )
    verdict, cap_reason = kr._cap_promote_if_unevidenced("PROMOTE", cand.name)
    # Not capped for provenance (artifact exists) -- capped instead for weak OP-16 edge.
    assert verdict == "VALIDATE"
    assert "PROVENANCE-MISSING" not in cap_reason
