"""Tests for autoresearch.decider — keep/revert decision logic."""

from __future__ import annotations

import pytest

from autoresearch.decider import decide
from autoresearch.metrics import TradeMetrics


def _metrics(**kwargs) -> TradeMetrics:
    """Build a TradeMetrics with safe defaults overridable via kwargs."""
    defaults = dict(
        n_trades=30, n_winners=15, n_losers=15, win_rate=0.50,
        total_pnl=1500.0, expectancy=50.0, avg_winner=200.0, avg_loser=-100.0,
        wl_ratio=2.0, max_drawdown=-300.0, sharpe_daily=1.0, n_days_traded=20,
    )
    defaults.update(kwargs)
    return TradeMetrics(**defaults)


def test_keep_when_sharpe_improves_and_thresholds_pass():
    baseline = _metrics(sharpe_daily=0.8).to_dict()
    candidate = _metrics(sharpe_daily=1.2)
    d = decide(candidate, baseline)
    assert d.keep is True
    assert d.delta_sharpe == pytest.approx(0.4)


def test_revert_when_sharpe_degrades():
    baseline = _metrics(sharpe_daily=1.0).to_dict()
    candidate = _metrics(sharpe_daily=0.5)
    d = decide(candidate, baseline)
    assert d.keep is False
    assert "did not improve" in d.reason


def test_revert_when_min_trades_violated():
    baseline = _metrics(sharpe_daily=0.5).to_dict()
    # higher Sharpe but only 5 trades -> min_trades hard gate
    candidate = _metrics(sharpe_daily=2.0, n_trades=5)
    d = decide(candidate, baseline)
    assert d.keep is False
    assert any("n_trades" in f for f in d.threshold_failures)


def test_revert_when_win_rate_below_floor():
    baseline = _metrics(win_rate=0.5).to_dict()
    # Below KEEP_THRESHOLDS.min_win_rate=0.10 -> blocked
    candidate = _metrics(sharpe_daily=2.0, win_rate=0.05, n_winners=2, n_losers=28)
    d = decide(candidate, baseline)
    assert d.keep is False
    assert any("win_rate" in f for f in d.threshold_failures)


def test_revert_when_expectancy_negative():
    baseline = _metrics().to_dict()
    # Below KEEP_THRESHOLDS.min_expectancy=-10.0 -> blocked
    candidate = _metrics(sharpe_daily=2.0, expectancy=-50.0, total_pnl=-1500.0)
    d = decide(candidate, baseline)
    assert d.keep is False
    assert any("expectancy" in f for f in d.threshold_failures)


def test_revert_when_drawdown_regresses_significantly():
    baseline = _metrics(max_drawdown=-200.0).to_dict()
    # 1.5x regression limit -> -300 is the floor; -500 should fail
    candidate = _metrics(sharpe_daily=2.0, max_drawdown=-500.0)
    d = decide(candidate, baseline)
    assert d.keep is False
    assert any("max_dd" in f for f in d.threshold_failures)


def test_keep_when_drawdown_improves():
    baseline = _metrics(max_drawdown=-500.0).to_dict()
    candidate = _metrics(sharpe_daily=1.5, max_drawdown=-200.0)
    d = decide(candidate, baseline)
    assert d.keep is True


def test_decide_with_no_baseline_keeps_if_above_zero_sharpe():
    candidate = _metrics(sharpe_daily=1.0)
    d = decide(candidate, baseline=None)
    assert d.keep is True
