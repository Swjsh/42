"""Tests for autoresearch.state — load/save/touch/history."""

from __future__ import annotations

import datetime as dt
import json

import pytest

from autoresearch import config, state as state_mod


@pytest.fixture
def isolated_state(tmp_path, monkeypatch):
    """Redirect ROOT_STATE_DIR to a temp folder so tests don't touch real state."""
    monkeypatch.setattr(state_mod, "ROOT_STATE_DIR", tmp_path)
    monkeypatch.setattr(state_mod, "STATE_DIR", tmp_path)
    monkeypatch.setattr(state_mod, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(state_mod, "HISTORY_FILE", tmp_path / "history.jsonl")
    yield tmp_path


# Standard windows reused throughout tests.
TRAIN_S, TRAIN_E = dt.date(2025, 1, 1), dt.date(2026, 2, 13)
VAL_S, VAL_E = dt.date(2026, 2, 14), dt.date(2026, 5, 7)


def test_fresh_state_uses_baseline_params(isolated_state):
    s = state_mod.fresh_state(TRAIN_S, TRAIN_E, VAL_S, VAL_E)
    assert s.current_params == dict(config.BASELINE_PARAMS)
    assert s.iteration == 0
    assert s.session_id is not None
    assert s.training_window == {"start": str(TRAIN_S), "end": str(TRAIN_E)}
    assert s.validate_window == {"start": str(VAL_S), "end": str(VAL_E)}
    assert s.mode is None


def test_fresh_state_with_mode_uses_starting_params(isolated_state):
    s = state_mod.fresh_state(
        TRAIN_S, TRAIN_E, VAL_S, VAL_E,
        mode="strict", starting_params=dict(config.STRICT_PARAMS),
    )
    assert s.mode == "strict"
    assert s.current_params["min_triggers_bear"] == config.STRICT_PARAMS["min_triggers_bear"]
    assert s.current_params["premium_stop_pct_bear"] == config.STRICT_PARAMS["premium_stop_pct_bear"]


def test_save_load_roundtrip(isolated_state):
    s = state_mod.fresh_state(TRAIN_S, TRAIN_E, VAL_S, VAL_E)
    s.iteration = 7
    s.modifications_kept = 3
    s.touch_param("f9_vol_mult")
    state_mod.save_state(s)

    loaded = state_mod.load_state()
    assert loaded is not None
    assert loaded.iteration == 7
    assert loaded.modifications_kept == 3
    assert loaded.last_param_modified == "f9_vol_mult"


def test_per_mode_state_files_isolated(isolated_state):
    s_strict = state_mod.fresh_state(
        TRAIN_S, TRAIN_E, VAL_S, VAL_E,
        mode="strict", starting_params=dict(config.STRICT_PARAMS),
    )
    s_strict.iteration = 5
    state_mod.save_state(s_strict)

    s_aggr = state_mod.fresh_state(
        TRAIN_S, TRAIN_E, VAL_S, VAL_E,
        mode="aggressive", starting_params=dict(config.AGGRESSIVE_PARAMS),
    )
    s_aggr.iteration = 12
    state_mod.save_state(s_aggr)

    loaded_strict = state_mod.load_state(mode="strict")
    loaded_aggr = state_mod.load_state(mode="aggressive")
    assert loaded_strict.iteration == 5
    assert loaded_aggr.iteration == 12
    assert loaded_strict.current_params != loaded_aggr.current_params


def test_load_returns_none_when_no_state_file(isolated_state):
    assert state_mod.load_state() is None
    assert state_mod.load_state(mode="strict") is None


def test_touch_param_maintains_cooldown_ring(isolated_state):
    s = state_mod.fresh_state(TRAIN_S, TRAIN_E, VAL_S, VAL_E)
    for p in ["f9_vol_mult", "premium_stop_pct", "min_triggers", "strike_offset"]:
        s.touch_param(p)
    assert len(s.recently_modified) == config.PARAM_COOLDOWN_ITERATIONS
    assert s.recently_modified[0] == "strike_offset"


def test_append_history_writes_jsonl(isolated_state):
    state_mod.append_history({"iteration": 1, "decision": {"keep": True}})
    state_mod.append_history({"iteration": 2, "decision": {"keep": False}})
    lines = (isolated_state / "history.jsonl").read_text().strip().split("\n")
    assert len(lines) == 2
    rec1 = json.loads(lines[0])
    assert rec1["iteration"] == 1
    assert rec1["decision"]["keep"] is True
    assert "at" in rec1


def test_append_history_per_mode(isolated_state):
    state_mod.append_history({"iteration": 1, "mode": "strict"}, mode="strict")
    state_mod.append_history({"iteration": 1, "mode": "aggressive"}, mode="aggressive")
    strict_lines = (isolated_state / "strict" / "history.jsonl").read_text().strip().split("\n")
    aggr_lines = (isolated_state / "aggressive" / "history.jsonl").read_text().strip().split("\n")
    assert len(strict_lines) == 1
    assert len(aggr_lines) == 1


def test_save_state_is_atomic_via_tmp_rename(isolated_state):
    s = state_mod.fresh_state(TRAIN_S, TRAIN_E, VAL_S, VAL_E)
    state_mod.save_state(s)
    assert (isolated_state / "state.json").exists()
    assert not (isolated_state / "state.json.tmp").exists()


def test_update_validate_baseline_persists(isolated_state):
    from autoresearch.metrics import TradeMetrics
    s = state_mod.fresh_state(TRAIN_S, TRAIN_E, VAL_S, VAL_E)
    val_m = TradeMetrics(
        n_trades=10, n_winners=6, n_losers=4, win_rate=0.6,
        total_pnl=500, expectancy=50, avg_winner=125, avg_loser=-75,
        wl_ratio=1.67, max_drawdown=-100, sharpe_daily=1.5, n_days_traded=8,
    )
    state_mod.update_validate_baseline(s, val_m)
    state_mod.save_state(s)
    loaded = state_mod.load_state()
    assert loaded.validate_baseline_metrics["sharpe_daily"] == 1.5
