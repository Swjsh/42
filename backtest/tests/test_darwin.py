"""Tests for darwin.scorecard and darwin.weights."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import pytest

from darwin import scorecard as sc_mod, weights as w_mod
from darwin.scorecard import FilterScorecard, KNOWN_FILTERS
from darwin.weights import (
    FilterWeights,
    INITIAL_WEIGHT,
    WEIGHT_CEILING,
    WEIGHT_FLOOR,
    high_weight_filters,
    low_weight_filters,
    update_from_scorecard,
    weighted_setup_score,
)


@pytest.fixture
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setattr(sc_mod, "STATE_DIR", tmp_path)
    monkeypatch.setattr(sc_mod, "SCORECARD_FILE", tmp_path / "scorecard.json")
    monkeypatch.setattr(w_mod, "STATE_DIR", tmp_path)
    monkeypatch.setattr(w_mod, "WEIGHTS_FILE", tmp_path / "weights.json")
    yield tmp_path


@dataclass
class _FakeFill:
    entry_time_et: dt.datetime
    dollar_pnl: float
    setup: str = "BEARISH_REJECTION_RIDE_THE_RIBBON"


def _trade(date: str, pnl: float, setup: str = "BEARISH_REJECTION_RIDE_THE_RIBBON") -> _FakeFill:
    return _FakeFill(dt.datetime.fromisoformat(date), pnl, setup=setup)


def test_scorecard_initializes_all_known_filters(isolated_state):
    sc = FilterScorecard()
    assert set(sc.stats.keys()) == set(KNOWN_FILTERS)
    for fid in KNOWN_FILTERS:
        assert sc.stats[fid].total_passes == 0


def test_scorecard_save_load_roundtrip(isolated_state):
    sc = FilterScorecard()
    sc.stats["f9_bear_breakdown_bar"].pass_on_winner = 7
    sc.n_trades_seen = 12
    sc.save()
    loaded = FilterScorecard.load_or_new()
    assert loaded.stats["f9_bear_breakdown_bar"].pass_on_winner == 7
    assert loaded.n_trades_seen == 12


def test_scorecard_attributes_winners_and_losers_to_bear_filters(isolated_state):
    sc = FilterScorecard()
    trades = [
        _trade("2026-01-05", 100),    # winner
        _trade("2026-01-06", -50),    # loser
        _trade("2026-01-07", 200),    # winner
    ]
    sc.update_from_backtest(trades, decisions=[])
    bear_filter = sc.stats["f5_bear_ribbon_stack"]
    assert bear_filter.pass_on_winner == 2
    assert bear_filter.pass_on_loser == 1
    assert bear_filter.pass_winrate == pytest.approx(2 / 3)


def test_scorecard_routes_bullish_trades_to_bull_filters(isolated_state):
    sc = FilterScorecard()
    trades = [
        _trade("2026-01-05", 100, setup="BULLISH_RECLAIM_RIDE_THE_RIBBON"),
        _trade("2026-01-06", 100, setup="BULLISH_RECLAIM_RIDE_THE_RIBBON"),
    ]
    sc.update_from_backtest(trades, decisions=[])
    assert sc.stats["f5_bull_ribbon_stack"].pass_on_winner == 2
    assert sc.stats["f5_bear_ribbon_stack"].pass_on_winner == 0


def test_pass_winrate_returns_0_5_when_no_data():
    sc = FilterScorecard()
    assert sc.stats["f9_bear_breakdown_bar"].pass_winrate == 0.5


def test_weights_initialise_to_one(isolated_state):
    fw = FilterWeights()
    for fid in KNOWN_FILTERS:
        assert fw.weights[fid] == INITIAL_WEIGHT


def test_weights_save_load_roundtrip(isolated_state):
    fw = FilterWeights()
    fw.weights["f9_bear_breakdown_bar"] = 1.5
    fw.save()
    loaded = FilterWeights.load_or_new()
    assert loaded.weights["f9_bear_breakdown_bar"] == 1.5


def test_update_promotes_top_quartile_filter(isolated_state):
    sc = FilterScorecard()
    fw = FilterWeights()
    # 8 winners, 1 loser -> winrate 0.89, well above TOP_QUARTILE_WINRATE
    sc.stats["f9_bear_breakdown_bar"].pass_on_winner = 8
    sc.stats["f9_bear_breakdown_bar"].pass_on_loser = 1
    changes = update_from_scorecard(fw, sc)
    assert "f9_bear_breakdown_bar" in changes
    old, new, reason = changes["f9_bear_breakdown_bar"]
    assert new > old
    assert "top quartile" in reason


def test_update_demotes_bottom_quartile_filter(isolated_state):
    sc = FilterScorecard()
    fw = FilterWeights()
    # 1 winner, 8 losers -> winrate 0.11, well below BOTTOM_QUARTILE_WINRATE
    sc.stats["f9_bear_breakdown_bar"].pass_on_winner = 1
    sc.stats["f9_bear_breakdown_bar"].pass_on_loser = 8
    changes = update_from_scorecard(fw, sc)
    assert "f9_bear_breakdown_bar" in changes
    old, new, _ = changes["f9_bear_breakdown_bar"]
    assert new < old


def test_update_skips_filter_with_too_few_passes(isolated_state):
    sc = FilterScorecard()
    fw = FilterWeights()
    sc.stats["f9_bear_breakdown_bar"].pass_on_winner = 2  # below MIN_PASSES_FOR_WEIGHT_CHANGE
    sc.stats["f9_bear_breakdown_bar"].pass_on_loser = 0
    changes = update_from_scorecard(fw, sc)
    assert "f9_bear_breakdown_bar" not in changes


def test_weight_clamps_to_floor_and_ceiling(isolated_state):
    sc = FilterScorecard()
    fw = FilterWeights()
    # Push a filter to its ceiling
    fw.weights["f9_bear_breakdown_bar"] = WEIGHT_CEILING
    sc.stats["f9_bear_breakdown_bar"].pass_on_winner = 100
    sc.stats["f9_bear_breakdown_bar"].pass_on_loser = 1
    update_from_scorecard(fw, sc)
    assert fw.weights["f9_bear_breakdown_bar"] == WEIGHT_CEILING

    # And to the floor
    fw.weights["f5_bear_ribbon_stack"] = WEIGHT_FLOOR
    sc.stats["f5_bear_ribbon_stack"].pass_on_winner = 1
    sc.stats["f5_bear_ribbon_stack"].pass_on_loser = 100
    update_from_scorecard(fw, sc)
    assert fw.weights["f5_bear_ribbon_stack"] == WEIGHT_FLOOR


def test_low_and_high_weight_filters(isolated_state):
    fw = FilterWeights()
    fw.weights["f5_bear_ribbon_stack"] = 0.5
    fw.weights["f9_bear_breakdown_bar"] = 1.5
    fw.weights["f10_bear_htf_triggers"] = 2.0
    low = low_weight_filters(fw, threshold=0.7)
    high = high_weight_filters(fw, threshold=1.3)
    assert "f5_bear_ribbon_stack" in low
    assert "f9_bear_breakdown_bar" in high
    assert high[0] == "f10_bear_htf_triggers"  # sorted by weight desc


def test_weighted_setup_score_sums_correctly(isolated_state):
    fw = FilterWeights()
    fw.weights["f5_bear_ribbon_stack"] = 1.5
    fw.weights["f6_ribbon_spread"] = 0.8
    score = weighted_setup_score(["f5_bear_ribbon_stack", "f6_ribbon_spread"], fw)
    assert score == pytest.approx(2.3)


def test_dry_run_does_not_mutate(isolated_state):
    sc = FilterScorecard()
    fw = FilterWeights()
    sc.stats["f9_bear_breakdown_bar"].pass_on_winner = 8
    sc.stats["f9_bear_breakdown_bar"].pass_on_loser = 1
    original = dict(fw.weights)
    update_from_scorecard(fw, sc, dry_run=True)
    assert fw.weights == original
    assert fw.n_updates == 0
