"""Guards for setup/ollama/nothink_proxy.py -- the per-fire local-brain request normalizer.

GAMMA-STATION Slice 0 (2026-09-13): Claude Code resolves its own model aliases ('sonnet' ->
'claude-sonnet-5', Agent(model:'haiku') -> 'claude-haiku-4-5') and ignores ANTHROPIC_MODEL for subagent
spawns, so a local-brain fire that fans out sends Anthropic ids to Ollama. The proxy must map any
'claude-<tier>*' id onto brain-mode.json's local model for that tier, fail open when the map is
unreadable, and log the rewrite. These tests pin that contract without a server or a network call.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PROXY = REPO / "setup" / "ollama" / "nothink_proxy.py"


@pytest.fixture(scope="module")
def proxy():
    # The module parses sys.argv[1] as a port at import time; pytest's argv would break it.
    saved = sys.argv
    sys.argv = [saved[0]]
    try:
        spec = importlib.util.spec_from_file_location("nothink_proxy_under_test", PROXY)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
    finally:
        sys.argv = saved
    return mod


MAP = {"sonnet": "gamma-planner-fast", "opus": "gamma-planner-fast", "haiku": "qwen3:14b"}


@pytest.mark.parametrize(
    "requested, expected",
    [
        ("claude-sonnet-5", "gamma-planner-fast"),
        ("claude-sonnet-4-5-20250929", "gamma-planner-fast"),
        ("claude-opus-4-8", "gamma-planner-fast"),
        ("claude-haiku-4-5", "qwen3:14b"),
        ("claude-haiku-4-5-20251001", "qwen3:14b"),
    ],
)
def test_rewrite_maps_claude_tiers_by_prefix(proxy, requested, expected):
    payload = {"model": requested}
    token = proxy.rewrite_model(payload, MAP)
    assert payload["model"] == expected
    assert token == f"{requested}->{expected}"


def test_rewrite_passes_local_ids_through(proxy):
    payload = {"model": "gamma-planner-fast"}
    assert proxy.rewrite_model(payload, MAP) == "gamma-planner-fast"
    assert payload["model"] == "gamma-planner-fast"


def test_rewrite_fails_open_on_empty_map(proxy):
    payload = {"model": "claude-sonnet-5"}
    assert proxy.rewrite_model(payload, {}) == "claude-sonnet-5"
    assert payload["model"] == "claude-sonnet-5"


def test_normalize_rewrites_model_and_keeps_existing_contract(proxy, monkeypatch):
    monkeypatch.setattr(proxy, "_model_map", lambda: MAP)
    payload = {
        "model": "claude-haiku-4-5",
        "system": "sys",
        "thinking": {"type": "enabled", "budget_tokens": 1024},
        "metadata": {"user_id": "x"},
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": "hi", "cache_control": {"type": "ephemeral"}}]},
            {"role": "system", "content": "mid-conversation system"},
        ],
    }
    out, summary = proxy.normalize(payload)
    assert out["model"] == "qwen3:14b"
    assert summary["model"] == "claude-haiku-4-5->qwen3:14b"
    assert out["thinking"] == {"type": "disabled"}
    assert "metadata" not in out and "metadata" in summary["dropped"]
    assert [m["role"] for m in out["messages"]] == ["user"]
    assert "cache_control" not in out["messages"][0]["content"][0]
    assert out["system"].endswith("mid-conversation system")


def test_model_map_reads_brain_mode_json(proxy):
    path = Path(proxy.BRAIN_MODE_PATH)
    if not path.exists():
        pytest.skip("brain-mode.json absent on this box")
    live = json.loads(path.read_text(encoding="utf-8-sig")).get("map") or {}
    assert proxy._model_map() == live
    assert {"sonnet", "haiku"} <= set(live), "brain-mode.json map must name the sonnet and haiku tiers"
