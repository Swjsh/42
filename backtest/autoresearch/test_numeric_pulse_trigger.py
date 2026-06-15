"""Tests for the event-driven heartbeat trigger embedded in numeric_pulse.py.

These tests verify:
  - cooldown enforcement (no back-to-back fires within 60s)
  - empty alerts -> no fire
  - state file persistence
  - spawn-failure handling
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Ensure project root on path so crypto.lib imports work
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from backtest.autoresearch import numeric_pulse as np  # noqa: E402


@pytest.fixture
def tmp_state(tmp_path, monkeypatch):
    """Redirect TRIGGER_STATE_FILE to a tmp path so tests don't bleed state."""
    state_file = tmp_path / "alert-trigger-state.json"
    monkeypatch.setattr(np, "TRIGGER_STATE_FILE", state_file)
    return state_file


def test_no_alerts_returns_not_fired(tmp_state):
    result = np._trigger_heartbeat_if_alert([])
    assert result["fired"] is False
    assert result["reason"] == "no_alerts"


def test_alert_fires_when_no_prior_state(tmp_state, monkeypatch):
    """First alert with empty state file -> fires + persists state."""
    fake_popen = MagicMock()
    monkeypatch.setattr("subprocess.Popen", fake_popen)
    alerts = [{
        "pattern": "failed_breakdown_wick",
        "bias": "bullish",
        "confidence": 0.75,
        "key_price": 735.0,
        "spy_close": 735.40,
        "level_distance_dollars": 0.20,
        "level_name": "PML",
    }]
    result = np._trigger_heartbeat_if_alert(alerts)
    assert result["fired"] is True
    assert tmp_state.exists()
    state = json.loads(tmp_state.read_text())
    assert "last_fire_utc" in state
    assert state["last_fire_alerts"][0]["pattern"] == "failed_breakdown_wick"


def test_cooldown_blocks_second_fire(tmp_state, monkeypatch):
    """If last fire was <60s ago, refuse to fire."""
    # Seed state file with a recent fire (5 sec ago)
    now = datetime.now(timezone.utc)
    tmp_state.parent.mkdir(parents=True, exist_ok=True)
    tmp_state.write_text(json.dumps({
        "last_fire_utc": (now - timedelta(seconds=5)).isoformat(),
        "last_fire_alerts": [],
    }))
    alerts = [{
        "pattern": "double_bottom", "bias": "bullish", "confidence": 0.70,
        "key_price": 100.0, "spy_close": 100.0,
        "level_distance_dollars": 0.10, "level_name": "L1",
    }]
    fake_popen = MagicMock()
    monkeypatch.setattr("subprocess.Popen", fake_popen)
    result = np._trigger_heartbeat_if_alert(alerts)
    assert result["fired"] is False
    assert result["reason"] == "cooldown"
    assert result["cooldown_remaining_sec"] > 0
    fake_popen.assert_not_called()


def test_cooldown_elapsed_allows_fire(tmp_state, monkeypatch):
    """If last fire was >60s ago, allow new fire."""
    now = datetime.now(timezone.utc)
    tmp_state.write_text(json.dumps({
        "last_fire_utc": (now - timedelta(seconds=120)).isoformat(),
    }))
    fake_popen = MagicMock()
    monkeypatch.setattr("subprocess.Popen", fake_popen)
    alerts = [{
        "pattern": "rejection_at_level_bearish", "bias": "bearish",
        "confidence": 0.80, "key_price": 750.0, "spy_close": 750.0,
        "level_distance_dollars": 0.05, "level_name": "PDH",
    }]
    result = np._trigger_heartbeat_if_alert(alerts)
    assert result["fired"] is True
    state = json.loads(tmp_state.read_text())
    assert state["last_fire_alerts"][0]["pattern"] == "rejection_at_level_bearish"


def test_corrupt_state_file_recovers(tmp_state, monkeypatch):
    """Malformed JSON in state file -> treat as empty + fire."""
    tmp_state.write_text("not valid json {")
    fake_popen = MagicMock()
    monkeypatch.setattr("subprocess.Popen", fake_popen)
    alerts = [{"pattern": "x", "bias": "bullish", "confidence": 0.70,
               "key_price": 0.0, "spy_close": 0.0,
               "level_distance_dollars": 0.0, "level_name": "Z"}]
    result = np._trigger_heartbeat_if_alert(alerts)
    # Should fire because state was treated as empty
    assert result["fired"] is True


def test_spawn_failure_returns_fired_false(tmp_state, monkeypatch):
    """If subprocess.Popen raises, return fired=False with reason."""
    def boom(*a, **kw):
        raise OSError("spawn denied")
    monkeypatch.setattr("subprocess.Popen", boom)
    # Also need to make wrapper files exist for the check to pass
    alerts = [{"pattern": "x", "bias": "bullish", "confidence": 0.7,
               "key_price": 0.0, "spy_close": 0.0,
               "level_distance_dollars": 0.0, "level_name": "Z"}]
    result = np._trigger_heartbeat_if_alert(alerts)
    assert result["fired"] is False
    assert "spawn failed" in result["reason"] or "missing" in result["reason"]


def test_state_includes_fired_for_accounts(tmp_state, monkeypatch):
    """After successful fire, state should record which wrappers were fired."""
    fake_popen = MagicMock()
    monkeypatch.setattr("subprocess.Popen", fake_popen)
    alerts = [{"pattern": "x", "bias": "bullish", "confidence": 0.7,
               "key_price": 0.0, "spy_close": 0.0,
               "level_distance_dollars": 0.0, "level_name": "Z"}]
    np._trigger_heartbeat_if_alert(alerts)
    state = json.loads(tmp_state.read_text())
    assert "fired_for" in state
    # Should be a list (Safe + Bold typically)
    assert isinstance(state["fired_for"], list)
