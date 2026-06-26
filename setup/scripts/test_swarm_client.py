"""Offline tests for swarm_client pure-logic core (no network, no openai SDK).

Run either way:
    python setup/scripts/test_swarm_client.py      # standalone runner
    pytest setup/scripts/test_swarm_client.py       # if pytest present
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import swarm_client as sc  # noqa: E402

# A synthetic roster so privacy tests don't depend on production config.
SYNTH = {
    "local_floor": {"provider": "ollama", "model": "qwen3:14b"},
    "providers": {
        "groq": {"base_url": "https://g", "trains_on_input": False},
        "gemini": {"base_url": "https://gem", "trains_on_input": True},
        "ollama": {"base_url": "http://localhost:11434/v1", "trains_on_input": False},
    },
    "roles": {
        "secret_role": {"privacy": "sensitive", "lanes": [
            {"provider": "gemini", "model": "flash"},   # trains -> must be dropped
            {"provider": "groq", "model": "llama"},
            {"provider": "ollama", "model": "qwen3:14b"}]},
        "public_role": {"privacy": "public_ok", "lanes": [
            {"provider": "gemini", "model": "flash"},   # trains -> kept (public ok)
            {"provider": "ollama", "model": "qwen3:14b"}]},
    },
}


def test_privacy_filter_drops_training_lane():
    lanes = sc.resolve_lanes("secret_role", SYNTH)
    providers = [ln["provider"] for ln in lanes]
    assert "gemini" not in providers, providers
    assert providers == ["groq", "ollama"], providers


def test_public_role_keeps_training_lane():
    lanes = sc.resolve_lanes("public_role", SYNTH)
    assert lanes[0]["provider"] == "gemini", lanes


def test_sensitive_never_empty_falls_to_floor():
    roster = {
        "local_floor": {"provider": "ollama", "model": "qwen3:14b"},
        "providers": {"gemini": {"trains_on_input": True},
                      "ollama": {"trains_on_input": False}},
        "roles": {"r": {"privacy": "sensitive",
                        "lanes": [{"provider": "gemini", "model": "flash"}]}},
    }
    lanes = sc.resolve_lanes("r", roster)
    assert lanes and lanes[-1]["provider"] == "ollama", lanes


def test_real_roster_roles_end_in_local_floor():
    roster = sc.load_roster()
    for role in roster["roles"]:
        # chef is exempt: cook prompts (~31K tokens) exceed the local model's default
        # ctx, so chef ends in a big-ctx cloud lane. Its never-dark guarantee lives at
        # the kitchen-daemon level (the original OpenRouter ladder is the final fallback).
        # TODO: give Ollama a 32K-ctx qwen3 variant so chef can end in local too.
        if role == "chef":
            continue
        lanes = sc.resolve_lanes(role, roster)
        assert lanes[-1]["provider"] == "ollama", (role, lanes)


def test_coordinator_lane_order():
    roster = sc.load_roster()
    lanes = sc.resolve_lanes("coordinator", roster)
    provs = [ln["provider"] for ln in lanes]
    assert provs == ["groq", "openrouter", "ollama"], provs


def test_cooldown_excludes_lane():
    roster = sc.load_roster()
    lanes = sc.resolve_lanes("coordinator", roster)
    first = lanes[0]
    sc._cool_lane(first, seconds=60)
    try:
        eff = sc.effective_lanes("coordinator", roster)
        assert sc._lane_key(first) not in [sc._lane_key(x) for x in eff], eff
    finally:
        with sc._LANE_LOCK:
            sc._LANE_COOLDOWN_UNTIL.clear()


def test_extract_json_strips_fence_and_think():
    raw = "<think>let me think...</think>\n```json\n{\"a\": 1, \"b\": \"x\"}\n```"
    assert sc.extract_json(raw) == {"a": 1, "b": "x"}


def test_extract_json_widest_span():
    raw = "here you go: {\"k\": [1,2,3]} thanks!"
    assert sc.extract_json(raw) == {"k": [1, 2, 3]}


def test_validate_json_required_and_types():
    schema = {"type": "object", "required": ["a"],
              "properties": {"a": {"type": "string"}, "n": {"type": "number"}}}
    ok, errs = sc.validate_json({"a": "hi", "n": 3}, schema)
    assert ok, errs
    ok2, errs2 = sc.validate_json({"n": 3}, schema)
    assert not ok2 and any("missing" in e for e in errs2), errs2


def _run_all() -> int:
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
