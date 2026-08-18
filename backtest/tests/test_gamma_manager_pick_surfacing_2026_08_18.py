"""Guard: gamma_manager's pick phase must never fail SILENTLY again.

THE INCIDENT (2026-08-17 16:16 ET -> 2026-08-18 00:46, caught by the readiness sweep):
every Manager pick failed for 8+ hours and the log said `error: null` on every row.
Mechanism, reproduced live before fixing: qwen3:14b -- fed a context that had grown rich
with the day's STATUS entries -- emitted VALID JSON in its own shape ({"task":...,
"details":{...}}), which is missing PICK_SCHEMA's required "prompt" key. swarm_client's
schema validator correctly rejected it, returned pick=None, and left env["error"]=None
because TRANSPORT succeeded. gamma_manager then logged env["error"] verbatim: null.

Transport-ok + schema-invalid is a FAILURE WITH A CAUSE, not "no error" (C7). Two fixes:
  1. run_cycle synthesizes a diagnostic (attempts, rejected lanes, content head) when the
     envelope carries no error -- the next drift is one glance to diagnose.
  2. The pick prompt now puts the CONTEXT FIRST and the output contract LAST (small local
     models anchor on the last thing read; instruction-first had the model mirroring the
     context's own JSON back). Live result after the reorder: first schema-valid pick in
     8.5 hours.

Pure: fake swarm_client, no ollama, no network.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

spec = importlib.util.spec_from_file_location("gamma_manager", REPO / "setup" / "scripts" / "gamma_manager.py")
gm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gm)


class _RejectingSC:
    """The exact 2026-08-17 envelope shape: transport ok, schema rejected, no error."""
    @staticmethod
    def call_role_json(role, prompt, schema, **kw):
        env = {"lane": "ollama::qwen3:14b", "error": None, "ok": True,
               "json_attempts": 3, "json_lanes_rejected": ["ollama::qwen3:14b"],
               "content": '{"task":"x","details":{}}'}
        return env, None


def _quiet(monkeypatch, logged):
    monkeypatch.setattr(gm, "_log", lambda e: logged.append(e))
    monkeypatch.setattr(gm, "gather_context", lambda: "CTX")


def test_schema_rejection_is_surfaced_not_null(monkeypatch):
    logged = []
    _quiet(monkeypatch, logged)
    monkeypatch.setattr(gm, "sc", _RejectingSC)
    r = gm.run_cycle(allow_heavy=False)
    assert r["ok"] is False and r["stage"] == "pick"
    assert r["error"], "a schema rejection must carry a diagnostic, never None"
    for needle in ("schema_invalid", "3 attempt(s)", "content_head"):
        assert needle in r["error"]
    assert logged and logged[0]["error"] == r["error"]


def test_envelope_error_still_wins_when_present(monkeypatch):
    logged = []
    _quiet(monkeypatch, logged)

    class _ErrSC:
        @staticmethod
        def call_role_json(*a, **k):
            return {"lane": "x", "error": "connection refused", "content": ""}, None
    monkeypatch.setattr(gm, "sc", _ErrSC)
    r = gm.run_cycle(allow_heavy=False)
    assert r["error"] == "connection refused", "a real transport error must not be rewritten"


def test_prompt_puts_context_first_and_contract_last(monkeypatch):
    """The anchoring fix. If the contract drifts back above the context, qwen mirrors the
    context JSON again -- pin the ORDER, not just the presence."""
    seen = {}

    class _CaptureSC:
        @staticmethod
        def call_role_json(role, prompt, schema, **kw):
            seen["prompt"] = prompt
            return {"lane": "x", "error": None, "json_attempts": 1,
                    "json_lanes_rejected": [], "content": ""}, None
    logged = []
    _quiet(monkeypatch, logged)
    monkeypatch.setattr(gm, "sc", _CaptureSC)
    gm.run_cycle(allow_heavy=False)
    p = seen["prompt"]
    assert "CTX" in p
    assert "EXACTLY these keys" in p
    assert p.index("CTX") < p.index("EXACTLY these keys"), \
        "context must precede the output contract (small models anchor on the tail)"
    assert '"prompt"' in p and "strategist|coder|critic|validator|forager|chef" in p
    assert "Example shape" in p


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
