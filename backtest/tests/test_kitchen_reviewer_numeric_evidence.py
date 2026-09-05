"""Guard: kitchen_reviewer PROMOTE requires a NUMERIC edge_capture from a
scorecard JSON on disk — LLM prose numbers must never clear the OP-16 floor.

Scar (2026-07-01 consolidation audit): 7/7 recent auto-promotes to
_LEADERBOARD.md cleared the floor on the literal LLM string
'inferred edge_capture=$25000'. These tests RED if that path ever reopens.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_MOD_PATH = _REPO / "setup" / "scripts" / "kitchen_reviewer.py"


def _load_kitchen_reviewer():
    """Load kitchen_reviewer with its heavy siblings stubbed (no LLM, no daemon)."""
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
    spec = importlib.util.spec_from_file_location("kitchen_reviewer_under_test", _MOD_PATH)
    m = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(m)
    finally:
        for name in fakes:
            sys.modules.pop(name, None)
    return m


kr = _load_kitchen_reviewer()


# Hits all six _OP20_CHECKS keyword groups so only the OP-16 gate is under test.
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


def _seed_run_log(repo, command: str) -> None:
    """R3 (GOAL-KITCHEN-RUNNER-IN-LOOP-2026-09-05): kitchen_reviewer now cross-checks a
    candidate's `provenance:` command against automation/state/kitchen-stage1-run-log.jsonl
    -- the daemon's own record of what it actually executed. Existing fixtures below write
    a `provenance:` line WITHOUT ever having run anything (that's the point of the tests --
    they exercise the OP-16/citation gates in isolation), so they must now also seed a
    matching PROVENANCE-OK run-log row or the NEW run-log gate caps them for a reason those
    tests aren't about. This mirrors what kitchen_stage1_runner.py itself appends."""
    log_path = repo / "automation" / "state" / "kitchen-stage1-run-log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"status": "PROVENANCE-OK", "command": command}) + "\n")


def test_llm_dollar_string_does_not_promote(tmp_path, monkeypatch):
    repo, cands = _mk_repo(tmp_path, monkeypatch)
    cand = cands / "fake-edge-chef-nemo.md"
    cand.write_text(_OP20_TEXT + "\ninferred edge_capture=$25000 -- massive!\n",
                    encoding="utf-8")
    result = kr._auto_promote_candidate(cand.name, "looks amazing")
    assert result.startswith("pending"), result
    assert "op16-fail" in result
    lb = cands / "_LEADERBOARD.md"
    assert (not lb.exists()) or ("fake-edge-chef-nemo" not in lb.read_text(encoding="utf-8"))


def test_numeric_scorecard_on_disk_promotes(tmp_path, monkeypatch):
    repo, cands = _mk_repo(tmp_path, monkeypatch)
    _seed_run_log(repo, "python setup/scripts/runner.py")
    scorecard = repo / "analysis" / "recommendations" / "real-edge-chef-nemo.json"
    scorecard.write_text(json.dumps({"edge_capture": 912.0, "n": 40}), encoding="utf-8")
    cand = cands / "real-edge-chef-nemo.md"
    cand.write_text(
        _OP20_TEXT + "\nsee analysis/recommendations/real-edge-chef-nemo.json\n"
        "\nprovenance: python setup/scripts/runner.py -> "
        "analysis/recommendations/real-edge-chef-nemo.json\n",
        encoding="utf-8",
    )
    result = kr._auto_promote_candidate(cand.name, "validated edge")
    assert result == "promoted", result
    lb_text = (cands / "_LEADERBOARD.md").read_text(encoding="utf-8")
    assert "edge_capture=912" in lb_text


def test_scorecard_below_floor_does_not_promote(tmp_path, monkeypatch):
    repo, cands = _mk_repo(tmp_path, monkeypatch)
    _seed_run_log(repo, "python setup/scripts/runner.py")
    scorecard = repo / "analysis" / "recommendations" / "weak-edge-chef-nemo.json"
    scorecard.write_text(json.dumps({"edge_capture": 100.0}), encoding="utf-8")
    cand = cands / "weak-edge-chef-nemo.md"
    cand.write_text(
        _OP20_TEXT + "\nsee analysis/recommendations/weak-edge-chef-nemo.json\n"
        "\nprovenance: python setup/scripts/runner.py -> "
        "analysis/recommendations/weak-edge-chef-nemo.json\n",
        encoding="utf-8",
    )
    result = kr._auto_promote_candidate(cand.name, "weak")
    assert result.startswith("pending"), result
    assert "edge_capture=100" in result and "< 771" in result


def test_promote_verdict_capped_to_validate_without_scorecard(tmp_path, monkeypatch):
    """No scorecard JSON exists anywhere -- the OP-16 floor check must cap this on its
    own reason ('no numeric scorecard edge_capture'), isolated from the provenance gates
    by citing an EXISTING (non-JSON) artifact + a provenance: line so neither of those
    gates fires first."""
    repo, cands = _mk_repo(tmp_path, monkeypatch)
    _seed_run_log(repo, "python setup/scripts/runner.py")
    context_doc = repo / "analysis" / "recommendations" / "context-note.md"
    context_doc.write_text("background context, no scorecard here", encoding="utf-8")
    cand = cands / "fake-edge-chef-nemo.md"
    cand.write_text(
        _OP20_TEXT + "\ninferred edge_capture=$25000 -- see "
        "analysis/recommendations/context-note.md for background\n"
        "\nprovenance: python setup/scripts/runner.py -> "
        "analysis/recommendations/context-note.md\n",
        encoding="utf-8",
    )
    verdict, cap_reason = kr._cap_promote_if_unevidenced(
        "PROMOTE", "strategy/candidates/fake-edge-chef-nemo.md")
    assert verdict == "VALIDATE"
    assert cap_reason.startswith("capped:")
    assert "no numeric scorecard edge_capture" in cap_reason


def test_evidenced_promote_not_capped(tmp_path, monkeypatch):
    repo, cands = _mk_repo(tmp_path, monkeypatch)
    _seed_run_log(repo, "python setup/scripts/runner.py")
    scorecard = repo / "analysis" / "recommendations" / "real-edge-chef-nemo.json"
    scorecard.write_text(json.dumps({"summary": {"edge_capture": 800}}), encoding="utf-8")
    cand = cands / "real-edge-chef-nemo.md"
    cand.write_text(
        _OP20_TEXT + "\nsee analysis/recommendations/real-edge-chef-nemo.json\n"
        "\nprovenance: python setup/scripts/runner.py -> "
        "analysis/recommendations/real-edge-chef-nemo.json\n",
        encoding="utf-8",
    )
    verdict, cap_reason = kr._cap_promote_if_unevidenced("PROMOTE", cand.name)
    assert verdict == "PROMOTE"
    assert cap_reason == ""
