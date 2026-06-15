"""Tests for the train/validate split decider."""

from __future__ import annotations

import pytest

from autoresearch.decider import decide_with_validation
from autoresearch.metrics import TradeMetrics


def _m(**kwargs) -> TradeMetrics:
    defaults = dict(
        n_trades=30, n_winners=15, n_losers=15, win_rate=0.50,
        total_pnl=1500.0, expectancy=50.0, avg_winner=200.0, avg_loser=-100.0,
        wl_ratio=2.0, max_drawdown=-300.0, sharpe_daily=1.0, n_days_traded=20,
    )
    defaults.update(kwargs)
    return TradeMetrics(**defaults)


def test_keep_when_train_improves_and_validate_holds():
    train_base = _m(sharpe_daily=1.0).to_dict()
    val_base = _m(sharpe_daily=0.8).to_dict()
    train_cand = _m(sharpe_daily=1.5)
    val_cand = _m(sharpe_daily=0.85)
    d = decide_with_validation(train_cand, train_base, val_cand, val_base)
    assert d.keep is True


def test_revert_when_train_does_not_improve():
    train_base = _m(sharpe_daily=2.0).to_dict()
    val_base = _m(sharpe_daily=1.0).to_dict()
    train_cand = _m(sharpe_daily=1.0)
    val_cand = _m(sharpe_daily=1.5)  # validate improves but train regresses
    d = decide_with_validation(train_cand, train_base, val_cand, val_base)
    assert d.keep is False
    assert "did not improve" in d.reason


def test_revert_when_validate_regresses_too_far():
    # train improves but validate drops 50% — overfitting signal
    train_base = _m(sharpe_daily=1.0).to_dict()
    val_base = _m(sharpe_daily=1.0).to_dict()
    train_cand = _m(sharpe_daily=2.5)
    val_cand = _m(sharpe_daily=0.4)  # 60% drop, exceeds 20% MAX_VALIDATION_REGRESSION
    d = decide_with_validation(train_cand, train_base, val_cand, val_base)
    assert d.keep is False
    assert "validate sharpe regressed" in d.reason
    assert any("validate" in f for f in d.threshold_failures)


def test_keep_when_validate_within_acceptable_regression():
    # train improves big, validate drops small (under 20%)
    train_base = _m(sharpe_daily=1.0).to_dict()
    val_base = _m(sharpe_daily=1.0).to_dict()
    train_cand = _m(sharpe_daily=2.0)
    val_cand = _m(sharpe_daily=0.85)  # 15% drop, within 20% deadband
    d = decide_with_validation(train_cand, train_base, val_cand, val_base)
    assert d.keep is True


def test_revert_when_train_hard_gate_fails():
    # train sharpe up but win rate collapses below the 10% floor
    train_base = _m(sharpe_daily=1.0).to_dict()
    val_base = _m(sharpe_daily=1.0).to_dict()
    train_cand = _m(sharpe_daily=2.0, win_rate=0.05, n_winners=2, n_losers=28)
    val_cand = _m(sharpe_daily=1.0)
    d = decide_with_validation(train_cand, train_base, val_cand, val_base)
    assert d.keep is False


def test_revert_when_validate_negative_and_baseline_was_negative_but_worse():
    # both validate sharpes are negative; candidate is MORE negative
    train_base = _m(sharpe_daily=1.0).to_dict()
    val_base = _m(sharpe_daily=-0.5).to_dict()
    train_cand = _m(sharpe_daily=2.0)
    val_cand = _m(sharpe_daily=-1.5)
    d = decide_with_validation(train_cand, train_base, val_cand, val_base)
    assert d.keep is False
    assert "validate" in d.reason


def test_keep_when_validate_negative_baseline_and_candidate_improves():
    # both validate sharpes are negative; candidate is LESS negative
    train_base = _m(sharpe_daily=1.0).to_dict()
    val_base = _m(sharpe_daily=-1.0).to_dict()
    train_cand = _m(sharpe_daily=2.0)
    val_cand = _m(sharpe_daily=-0.5)  # improvement
    d = decide_with_validation(train_cand, train_base, val_cand, val_base)
    assert d.keep is True
