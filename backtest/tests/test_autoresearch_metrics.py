"""Tests for autoresearch.metrics — Sharpe, expectancy, drawdown."""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass

import pytest

from autoresearch.metrics import compute_metrics, daily_pnl_series, _sharpe


@dataclass
class _FakeFill:
    """Minimal stub matching the TradeFill interface used by metrics.compute_metrics."""

    entry_time_et: dt.datetime
    dollar_pnl: float


def _trade(date: str, pnl: float, hour: int = 10) -> _FakeFill:
    return _FakeFill(dt.datetime.fromisoformat(date).replace(hour=hour), pnl)


def test_compute_metrics_empty_returns_zeros():
    m = compute_metrics([])
    assert m.n_trades == 0
    assert m.total_pnl == 0
    assert m.sharpe_daily == 0
    assert m.win_rate == 0


def test_compute_metrics_basic_winners_and_losers():
    trades = [
        _trade("2026-01-05", 100),
        _trade("2026-01-06", -50),
        _trade("2026-01-07", 200),
        _trade("2026-01-08", -30),
    ]
    m = compute_metrics(trades)
    assert m.n_trades == 4
    assert m.n_winners == 2
    assert m.n_losers == 2
    assert m.win_rate == 0.5
    assert m.total_pnl == 220
    assert m.expectancy == 55
    assert m.avg_winner == 150
    assert m.avg_loser == -40
    assert m.wl_ratio == pytest.approx(3.75)


def test_max_drawdown_sequential():
    # +100, -200 (peak 100, trough -100, dd -200), +50, +200
    trades = [
        _trade("2026-01-05", 100),
        _trade("2026-01-06", -200),
        _trade("2026-01-07", 50),
        _trade("2026-01-08", 200),
    ]
    m = compute_metrics(trades)
    # Peak = +100 (after day 1), trough = -100 (after day 2). DD = -100 - 100 = -200.
    assert m.max_drawdown == -200


def test_daily_pnl_groups_by_date():
    trades = [
        _trade("2026-01-05", 100, hour=10),
        _trade("2026-01-05", 50, hour=14),
        _trade("2026-01-06", -75),
    ]
    daily = daily_pnl_series(trades)
    assert daily[dt.date(2026, 1, 5)] == 150
    assert daily[dt.date(2026, 1, 6)] == -75


def test_sharpe_zero_when_constant():
    # Zero variance -> Sharpe defined as 0 (avoid div by zero)
    assert _sharpe([10, 10, 10]) == 0.0


def test_sharpe_positive_when_consistently_winning():
    s = _sharpe([100, 110, 90, 105, 95])
    assert s > 0
    assert math.isfinite(s)


def test_wl_ratio_infinite_with_no_losers():
    trades = [_trade("2026-01-05", 100), _trade("2026-01-06", 50)]
    m = compute_metrics(trades)
    assert math.isinf(m.wl_ratio)
    # to_dict converts inf -> None for JSON safety
    assert m.to_dict()["wl_ratio"] is None
