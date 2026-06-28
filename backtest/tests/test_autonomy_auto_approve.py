"""Guard: the autonomy actuator's OP-11/OP-25 auto-approver must approve ONLY the
safe class and NEVER a raw params/heartbeat/risk change without eval evidence.

This RED-on-regression test is the graduated guardrail for the auto-approve wire
(J: 'wiring autonomous improvement is in our OPs -- don't ask'). If someone widens
the bar so an unvalidated trading-params change auto-approves, this fails loud.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "autonomy_actuator", REPO / "setup" / "scripts" / "autonomy_actuator.py"
)
act = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(act)


def _write(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _redirect(tmp_path, monkeypatch):
    prop = tmp_path / "proposals.jsonl"
    monkeypatch.setattr(act, "PROPOSALS", prop)
    monkeypatch.setattr(act, "CHANGELOG", tmp_path / "changelog.jsonl")
    return prop


def test_bar_approves_only_safe_class(tmp_path, monkeypatch):
    prop = _redirect(tmp_path, monkeypatch)
    _write(prop, [
        # 1) OP-25 doc-index fold touching only CLAUDE.md -> APPROVE
        {"proposal_id": "doc-ok", "status": "pending", "kind": "doc-index",
         "apply_ops": [{"file": "CLAUDE.md", "find": "L1,2", "replace": "L1,2,9"}]},
        # 2) raw params change, no eval evidence -> STAY PENDING
        {"proposal_id": "params-raw", "status": "pending", "kind": "params",
         "apply_ops": [{"file": "automation/state/params.json", "find": "a", "replace": "b"}]},
        # 3) doc-index MISLABEL that actually edits params.json -> STAY PENDING
        {"proposal_id": "doc-mislabeled", "status": "pending", "kind": "doc-index",
         "apply_ops": [{"file": "automation/state/params.json", "find": "a", "replace": "b"}]},
        # 4) trading edge that cleared the OP-11 eval bar (+scorecard) -> APPROVE
        {"proposal_id": "edge-cleared", "status": "pending", "kind": "params",
         "eval_bar_cleared": True, "scorecard": "analysis/recommendations/x.json",
         "apply_ops": [{"file": "automation/state/params.json", "find": "a", "replace": "b"}]},
        # 5) doc-index but PROSE-only (no apply_ops) -> STAY PENDING
        {"proposal_id": "doc-prose", "status": "pending", "kind": "doc-index", "apply": "do it"},
        # 6) eval flag set but NO scorecard -> STAY PENDING (evidence required)
        {"proposal_id": "edge-noscore", "status": "pending", "kind": "heartbeat",
         "eval_bar_cleared": True,
         "apply_ops": [{"file": "automation/prompts/heartbeat.md", "find": "a", "replace": "b"}]},
    ])
    n = act.auto_approve_pending()
    status = {r["proposal_id"]: r["status"] for r in act._read_proposals()}
    assert status["doc-ok"] == "approved"
    assert status["edge-cleared"] == "approved"
    assert status["params-raw"] == "pending"
    assert status["doc-mislabeled"] == "pending"
    assert status["doc-prose"] == "pending"
    assert status["edge-noscore"] == "pending"
    assert n == 2


def test_idempotent(tmp_path, monkeypatch):
    prop = _redirect(tmp_path, monkeypatch)
    _write(prop, [{"proposal_id": "d", "status": "pending", "kind": "doc-index",
                   "apply_ops": [{"file": "CLAUDE.md", "find": "L1", "replace": "L1,9"}]}])
    assert act.auto_approve_pending() == 1
    assert act.auto_approve_pending() == 0  # already approved -> never re-approves
    assert act._read_proposals()[0]["approved_via"] == "auto:op25_docindex"


def test_drain_already_applied(tmp_path, monkeypatch):
    """A chained fold whose edit already landed (find absent, replace present) is
    closed as a no-op; a genuinely-stale one (replace also absent) is left alone."""
    prop = _redirect(tmp_path, monkeypatch)
    monkeypatch.setattr(act, "REPO", tmp_path)
    (tmp_path / "doc.md").write_text("hello ALREADY-THERE world", encoding="utf-8")
    _write(prop, [
        {"proposal_id": "stuck", "status": "needs_structured_apply", "kind": "doc-index",
         "apply_ops": [{"file": "doc.md", "find": "MISSING-FIND", "replace": "ALREADY-THERE"}]},
        {"proposal_id": "genuine-stale", "status": "needs_structured_apply", "kind": "doc-index",
         "apply_ops": [{"file": "doc.md", "find": "MISSING-FIND", "replace": "ALSO-MISSING"}]},
    ])
    n = act.drain_already_applied()
    status = {r["proposal_id"]: r["status"] for r in act._read_proposals()}
    assert status["stuck"] == "applied"
    assert status["genuine-stale"] == "needs_structured_apply"
    assert n == 1
