"""Guard: setup/scripts/swarm_client.py call_role_json lane failover on INVALID JSON.

Locks in the 2026-07-11 fix: a lane that answers with transport-ok but non-schema-
valid content (reasoning-prose drift — the live nemotron-3-super failure mode that
starved twin_review's critic calls while the local floor passed the same prompt
first-try) is a FAILED lane for JSON mode and falls through to the next lane.
Previously call_role's "ok + non-empty wins" accepted the prose as final and the
repair-retry re-entered call_role at lane 0, so the roster never reached the
schema-compliant cerebras/local-floor lanes (C7: audit outputs, not exit codes).

Also locks in: the ONE-repair-total budget (pinned to the lane it repairs; spent on
parseable-but-schema-invalid output, forfeited on no-JSON-at-all except on the final
lane), the worst-case call bound of len(lanes)+1 (hot-path latency guard — the
heartbeat_core 2-model entry veto calls this every ENTER candidate), the additive
envelope fields json_attempts / json_lanes_rejected, and — regression guard — that
plain call_role keeps its original any-non-empty-text-wins semantics for the seven
prose consumers (kitchen, narrative, manager dispatch).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in ("setup/scripts", ""):
    p = str(REPO / _p) if _p else str(REPO)
    if p not in sys.path:
        sys.path.insert(0, p)

import swarm_client as sc  # noqa: E402

SCHEMA = {"type": "object", "required": ["go"],
          "properties": {"go": {"type": "boolean"}, "reason": {"type": "string"}}}

L1 = {"provider": "openrouter", "model": "nvidia/nemotron-3-super-120b-a12b:free"}
L2 = {"provider": "cerebras", "model": "zai-glm-4.7"}
L3 = {"provider": "ollama", "model": "qwen3:14b"}

PROSE = "Okay, let me think about this entry. The ribbon is BEAR and VIX is calm, so go true."


def _key(lane: dict) -> str:
    return f"{lane['provider']}::{lane['model']}"


class LaneScript:
    """Fake _call_lane: pops scripted responses per lane key, records every call.

    A script item that is a str = transport-ok content; a dict is merged into the
    envelope (e.g. {"ok": False, "error": "429"}). An exhausted lane transport-fails.
    """

    def __init__(self, script: dict):
        self.script = {k: list(v) for k, v in script.items()}
        self.calls: list[tuple[str, str]] = []  # (lane_key, task_id)

    def __call__(self, lane, prompt, *, system, max_tokens, temperature,
                 timeout, task_id, roster, remote_timeout=45.0):
        key = _key(lane)
        self.calls.append((key, task_id))
        seq = self.script.get(key) or []
        item = seq.pop(0) if seq else {"ok": False, "error": "script_exhausted"}
        if isinstance(item, str):
            return {"ok": True, "lane": key, "content": item, "error": None}
        return {"ok": False, "lane": key, "content": "", "error": None, **item}


def _wire(monkeypatch, lanes: list, script: dict) -> LaneScript:
    fake = LaneScript(script)
    monkeypatch.setattr(sc, "load_roster", lambda force=False: {})
    monkeypatch.setattr(sc, "effective_lanes", lambda role, roster=None: list(lanes))
    monkeypatch.setattr(sc, "_call_lane", fake)
    return fake


def _repairs(fake: LaneScript) -> list[tuple[str, str]]:
    return [c for c in fake.calls if c[1].endswith(".repair")]


# ============================================================================
# The bug being fixed: prose-drifting primary must fall through, not win
# ============================================================================
def test_prose_primary_falls_through_to_next_lane(monkeypatch):
    fake = _wire(monkeypatch, [L1, L2, L3], {
        _key(L1): [PROSE],
        _key(L2): ['{"go": true, "reason": "clean tape"}'],
    })
    env, parsed = sc.call_role_json("critic", "sanity-check", SCHEMA, task_id="t")
    assert parsed == {"go": True, "reason": "clean tape"}
    assert env["lane"] == _key(L2)
    assert env["json_lanes_rejected"] == [_key(L1)]
    assert env["json_attempts"] == 2
    # No-JSON-at-all on a non-final lane must NOT burn the repair budget on a re-roll.
    assert _repairs(fake) == []
    assert [c[0] for c in fake.calls] == [_key(L1), _key(L2)]


def test_all_lanes_prose_returns_none_with_full_reject_list(monkeypatch):
    fake = _wire(monkeypatch, [L1, L2, L3], {
        _key(L1): [PROSE], _key(L2): [PROSE], _key(L3): [PROSE, PROSE],
    })
    env, parsed = sc.call_role_json("critic", "p", SCHEMA)
    assert parsed is None
    assert env["json_lanes_rejected"] == [_key(L1), _key(L2), _key(L3)]
    # Final lane gets the last-chance repair even for no-JSON output.
    assert _repairs(fake) == [(_key(L3), "swarm.json.critic.repair")]
    # Worst case bound: len(lanes) + 1 total model calls.
    assert env["json_attempts"] == len(fake.calls) == 4


# ============================================================================
# Repair budget: one total, pinned to the lane that earned it
# ============================================================================
def test_schema_invalid_gets_same_lane_repair(monkeypatch):
    fake = _wire(monkeypatch, [L1, L2], {
        _key(L1): ['{"g0": 1}', '{"go": false, "reason": "chop"}'],
    })
    env, parsed = sc.call_role_json("critic", "p", SCHEMA)
    assert parsed == {"go": False, "reason": "chop"}
    assert env["lane"] == _key(L1)
    assert fake.calls == [(_key(L1), "swarm.json.critic"),
                          (_key(L1), "swarm.json.critic.repair")]
    assert env["json_lanes_rejected"] == []


def test_repair_budget_is_one_total_across_lanes(monkeypatch):
    fake = _wire(monkeypatch, [L1, L2, L3], {
        _key(L1): ['{"wrong": 1}', '{"still": "wrong"}'],   # invalid + failed repair
        _key(L2): ['{"also": "wrong"}'],                    # invalid, budget gone
        _key(L3): ['{"go": true}'],
    })
    env, parsed = sc.call_role_json("critic", "p", SCHEMA)
    assert parsed == {"go": True}
    assert env["lane"] == _key(L3)
    assert len(_repairs(fake)) == 1
    assert env["json_lanes_rejected"] == [_key(L1), _key(L2)]


def test_single_lane_no_json_gets_last_chance_repair(monkeypatch):
    fake = _wire(monkeypatch, [L3], {_key(L3): [PROSE, '{"go": true}']})
    env, parsed = sc.call_role_json("critic", "p", SCHEMA)
    assert parsed == {"go": True}
    assert _repairs(fake) == [(_key(L3), "swarm.json.critic.repair")]


# ============================================================================
# Pre-existing semantics that must survive
# ============================================================================
def test_transport_failure_still_falls_through_and_is_not_a_json_reject(monkeypatch):
    _wire(monkeypatch, [L1, L2], {
        _key(L1): [{"ok": False, "error": "429 rate limited"}],
        _key(L2): ['{"go": true}'],
    })
    env, parsed = sc.call_role_json("critic", "p", SCHEMA)
    assert parsed == {"go": True}
    assert env["json_lanes_rejected"] == []


def test_empty_content_lane_falls_through_without_repair(monkeypatch):
    fake = _wire(monkeypatch, [L1, L2], {
        _key(L1): ["   "],
        _key(L2): ['{"go": false}'],
    })
    env, parsed = sc.call_role_json("critic", "p", SCHEMA)
    assert parsed == {"go": False}
    assert _repairs(fake) == []


def test_total_failure_envelope_keeps_consumer_contract(monkeypatch):
    """heartbeat_core records env.get('lane') on no_valid_json — envelope must stay
    a dict with lane/ok even when every lane transport-fails."""
    _wire(monkeypatch, [L1, L2, L3], {})  # every lane transport-fails
    env, parsed = sc.call_role_json("critic", "p", SCHEMA)
    assert parsed is None
    assert env["ok"] is False
    assert env["lane"] == _key(L3)
    assert env["json_attempts"] == 3


def test_call_role_prose_semantics_unchanged(monkeypatch):
    """The seven prose consumers keep first-non-empty-wins — prose is a VALID win
    for call_role; only call_role_json demands schema-valid JSON."""
    fake = _wire(monkeypatch, [L1, L2], {_key(L1): [PROSE]})
    env = sc.call_role("critic", "p")
    assert env["ok"] is True
    assert env["lane"] == _key(L1)
    assert env["content"] == PROSE
    assert len(fake.calls) == 1
