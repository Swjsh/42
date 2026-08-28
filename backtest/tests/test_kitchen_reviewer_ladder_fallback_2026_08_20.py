"""Guard: kitchen_reviewer falls back to the MODEL_LADDER when the pool
result is ok=True but the content doesn't parse as the required JSON object
(and falls through remaining ladder tiers on the same shape too).

Scar (2026-08-20, self-check DEGRADED -> STATUS RED flag, "RUN-PS1-HIDDEN
MASKED EXIT"): `run-kitchen-reviewer.ps1` exited 1 on 3/9 fires in one day.
Root cause: the primary free model (nvidia/nemotron, a reasoning model) would
sometimes burn its whole max_tokens budget on chain-of-thought prose before
ever emitting the required JSON object, returning `ok=True` with truncated/
unparseable content. The old gate treated ok+non-empty as "usable" and never
tried the 3-tier ladder that exists specifically to cover this. These tests
RED if that gate ever reopens (i.e. if a garbled-but-nonempty response is
ever accepted without a JSON-parseability check).
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_MOD_PATH = _REPO / "setup" / "scripts" / "kitchen_reviewer.py"

_REASONING_PROSE = (
    "We are given 12 cook outputs to review. Let's think step by step "
    "about each one before producing any output... " * 50
)  # no '{' at all -- simulates a truncated reasoning response with zero JSON

_VALID_JSON = (
    '{"decisions": [{"output_path": "x.md", "verdict": "VALIDATE", '
    '"rationale": "ok", "followup_task": ""}], "digest": "test digest"}'
)


def _load_kitchen_reviewer(model_ladder):
    """Load kitchen_reviewer with heavy siblings stubbed (no real LLM/daemon).

    FIXED 2026-08-28 (full-suite RED, test-order pollution): the stubbing used to be
    conditional on `name not in sys.modules`, which silently did nothing whenever some
    OTHER test file (test_kitchen_grader_crashloop_guards.py does `importlib.import_module
    ("kitchen_daemon")` -- entirely normal, correct behavior on ITS part) had already
    cached the REAL module first. kitchen_reviewer.py is loaded here as a fresh, isolated
    module object (spec_from_file_location under a unique name), but its own `import
    kitchen_daemon` during exec_module() still resolves through the ONE shared
    sys.modules cache -- so whichever module got there first wins, real or fake,
    regardless of which one THIS test intends. Reproduced in isolation:
    `pytest test_kitchen_grader_crashloop_guards.py
    test_kitchen_reviewer_ladder_fallback_2026_08_20.py` -> tier-0 fired the REAL
    kitchen_daemon.MODEL_LADDER's live model id instead of this test's
    ["ladder-tier-0", "ladder-tier-1"], and the fake call_minimax raised
    "unexpected model nvidia/nemotron-3-super-120b-a12b:free".

    Fix: ALWAYS install the fake for the duration of this load (never conditional on
    prior state), saving whatever sys.modules[name] held before -- real module, a
    DIFFERENT test's fake, or nothing -- and restoring exactly that in `finally`. This
    is isolation, not a one-shot claim on an empty slot; it holds no matter what any
    other test file already did to sys.modules."""
    prior: dict[str, object] = {}
    _MISSING = object()
    for name in ("run_minimax", "kitchen_daemon"):
        prior[name] = sys.modules.get(name, _MISSING)
        mod = types.ModuleType(name)
        if name == "run_minimax":
            mod.call_minimax = lambda *a, **k: {"ok": False, "error": "unset-stub"}
        else:
            mod.enqueue_task = lambda *a, **k: "stub-task-id"
            mod.MODEL_LADDER = model_ladder
        sys.modules[name] = mod
    spec = importlib.util.spec_from_file_location(
        "kitchen_reviewer_ladder_fallback_under_test", _MOD_PATH
    )
    m = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(m)
    finally:
        for name, was in prior.items():
            if was is _MISSING:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = was
    return m


def _mk_repo(tmp_path, monkeypatch, kr):
    cands = tmp_path / "strategy" / "candidates"
    cands.mkdir(parents=True)
    (tmp_path / "analysis" / "kitchen-review").mkdir(parents=True)
    cand = cands / "2026-08-20-chef-nemo-fake.md"
    cand.write_text("some cook output body\n", encoding="utf-8")
    monkeypatch.setattr(kr, "REPO", tmp_path)
    monkeypatch.setattr(kr, "CANDIDATES_DIR", cands)
    monkeypatch.setattr(kr, "REVIEW_DIR", tmp_path / "analysis" / "kitchen-review")
    monkeypatch.setattr(kr, "REVIEW_LOG", cands / "_review-log.jsonl")
    monkeypatch.setattr(kr, "STATE_DIR", tmp_path / "automation" / "state")
    (tmp_path / "automation" / "state" / "logs").mkdir(parents=True)
    return cands


def test_unparseable_pool_result_falls_through_to_ladder(tmp_path, monkeypatch):
    """Pool returns ok=True with reasoning prose (no JSON) -> ladder tier 0
    also unparseable -> tier 1 returns valid JSON -> main() succeeds (exit 0),
    proving the fallback chain is exercised end-to-end, not short-circuited."""
    kr = _load_kitchen_reviewer(model_ladder=["ladder-tier-0", "ladder-tier-1"])
    _mk_repo(tmp_path, monkeypatch, kr)

    fake_swarm = types.ModuleType("swarm_client")
    fake_swarm.call_role = lambda *a, **k: {
        "ok": True, "content": _REASONING_PROSE, "lane": "openrouter::nemotron",
    }
    monkeypatch.setitem(sys.modules, "swarm_client", fake_swarm)

    calls = []

    def fake_call_minimax(*a, model=None, **k):
        calls.append(model)
        if model == "ladder-tier-0":
            return {"ok": True, "content": _REASONING_PROSE}  # unparseable again
        if model == "ladder-tier-1":
            return {"ok": True, "content": _VALID_JSON}
        raise AssertionError(f"unexpected model {model}")

    monkeypatch.setattr(kr, "call_minimax", fake_call_minimax)

    rc = kr.main()

    assert rc == 0, "main() should succeed once the ladder produces parseable JSON"
    assert calls == ["ladder-tier-0", "ladder-tier-1"], (
        "expected BOTH ladder tiers to be attempted in order after the "
        f"pool's unparseable response; got {calls}"
    )


def test_all_paths_unparseable_saves_raw_and_exits_1(tmp_path, monkeypatch):
    """Pool + every ladder tier all return ok=True but unparseable -> main()
    exits 1 (not a crash) and a raw debug dump is written for post-mortem."""
    kr = _load_kitchen_reviewer(model_ladder=["ladder-tier-0"])
    cands = _mk_repo(tmp_path, monkeypatch, kr)

    fake_swarm = types.ModuleType("swarm_client")
    fake_swarm.call_role = lambda *a, **k: {
        "ok": True, "content": _REASONING_PROSE, "lane": "openrouter::nemotron",
    }
    monkeypatch.setitem(sys.modules, "swarm_client", fake_swarm)
    monkeypatch.setattr(
        kr, "call_minimax",
        lambda *a, **k: {"ok": True, "content": _REASONING_PROSE},
    )

    rc = kr.main()

    assert rc == 1
    dumps = list((tmp_path / "automation" / "state" / "logs").glob("reviewer-bad-response-*.txt"))
    assert dumps, "expected a raw-response debug dump when every path is unparseable"


def test_pool_result_that_parses_cleanly_skips_ladder_entirely(tmp_path, monkeypatch):
    """Sanity: the happy path (pool returns valid JSON) never touches the
    ladder at all -- this fix must not add cost/latency to the common case."""
    kr = _load_kitchen_reviewer(model_ladder=["ladder-tier-0"])
    _mk_repo(tmp_path, monkeypatch, kr)

    fake_swarm = types.ModuleType("swarm_client")
    fake_swarm.call_role = lambda *a, **k: {
        "ok": True, "content": _VALID_JSON, "lane": "openrouter::nemotron",
    }
    monkeypatch.setitem(sys.modules, "swarm_client", fake_swarm)

    def fail_if_called(*a, **k):
        raise AssertionError("ladder must not be attempted when the pool result parses")

    monkeypatch.setattr(kr, "call_minimax", fail_if_called)

    rc = kr.main()

    assert rc == 0
