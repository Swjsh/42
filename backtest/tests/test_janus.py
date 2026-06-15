"""Tests for janus.detector — two-window regime detection."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import pytest

from janus import detector as det
from janus.detector import (
    HISTORICAL_REGIME,
    MIXED,
    NOVEL_REGIME,
    RegimeSignal,
    _annualised_sharpe,
    detect,
    load_regime,
    save_regime,
    trades_to_daily_pnl,
)


def _series(start: str, values: list[float]) -> dict[dt.date, float]:
    """Build a daily_pnl dict starting at `start` with one entry per business day."""
    d = dt.date.fromisoformat(start)
    out: dict[dt.date, float] = {}
    for v in values:
        # Skip weekends crudely
        while d.weekday() >= 5:
            d += dt.timedelta(days=1)
        out[d] = v
        d += dt.timedelta(days=1)
    return out


def test_annualised_sharpe_zero_when_constant():
    assert _annualised_sharpe([10, 10, 10, 10]) == 0.0


def test_annualised_sharpe_positive_when_trending_up():
    s = _annualised_sharpe([100, 110, 90, 105, 95])
    assert s > 0


def test_detect_with_no_data_returns_mixed():
    sig = detect({})
    assert sig.regime == MIXED
    assert sig.n_recent == 0


def test_detect_recognises_novel_regime_when_recent_collapses():
    # Baseline: positive trending (+10..+90 alternating, mean ~+50)
    # Recent: negative trending (-100..-10 alternating, mean ~-55)
    # Both have nonzero variance, so Sharpe is well-defined for both.
    baseline = [40, 50, 60, 70, 50, 30, 60, 40, 50, 60] * 6  # 60 days, mean=51, nonzero var
    recent = [-100, -50, -150, -80, -120, -60, -90, -110, -70, -130]  # 10 days, mean=-96
    series = _series("2025-01-02", baseline + recent)
    sig = detect(series, recent_window_days=10, baseline_window_days=60,
                 divergence_threshold=0.5)
    assert sig.regime == NOVEL_REGIME
    assert sig.delta_sharpe < -0.5
    assert sig.recent_sharpe < sig.baseline_sharpe


def test_detect_recognises_historical_regime_when_recent_excels():
    # Baseline: weak/noisy (mean ~0 with mild variance)
    baseline = [-5, 5, -3, 7, 2, -4, 6, -2, 4, -6] * 6  # 60 days
    recent = [80, 90, 70, 100, 85, 75, 95, 90, 80, 95]  # 10 days, strongly positive
    series = _series("2025-01-02", baseline + recent)
    sig = detect(series, recent_window_days=10, baseline_window_days=60,
                 divergence_threshold=0.5)
    assert sig.regime == HISTORICAL_REGIME
    assert sig.recent_sharpe > sig.baseline_sharpe


def test_detect_returns_mixed_within_deadband():
    # Recent and baseline have nearly identical statistics — Sharpe deltas
    # should fall well within a generous deadband.
    pattern = [25, -15, 30, -20, 35, -10, 20, -25, 15, -5]  # mean 5, std ~22
    baseline = pattern * 6   # 60 days
    recent = list(pattern)   # 10 days, same pattern
    series = _series("2025-01-02", baseline + recent)
    sig = detect(series, recent_window_days=10, baseline_window_days=60,
                 divergence_threshold=5.0)  # very generous deadband
    assert sig.regime == MIXED, f"expected MIXED, got {sig.regime} with delta={sig.delta_sharpe:.3f}"


def test_recent_baseline_windows_do_not_overlap():
    # 30 dates, recent=5, baseline=20 -> baseline = days 5-25, recent = days 25-30
    series = _series("2025-01-02", [10.0] * 30)
    sig = detect(series, recent_window_days=5, baseline_window_days=20)
    assert sig.n_recent == 5
    assert sig.n_baseline == 20


def test_baseline_window_clipped_to_available_data():
    # only 15 days of data, baseline_window_days=60 but recent=5
    series = _series("2025-01-02", [10.0] * 15)
    sig = detect(series, recent_window_days=5, baseline_window_days=60)
    assert sig.n_recent == 5
    assert sig.n_baseline == 10  # 15 - 5 recent


def test_threshold_adjustments_tighter_for_novel():
    baseline = [40, 50, 60, 70, 50, 30, 60, 40, 50, 60] * 6
    recent = [-100, -50, -150, -80, -120, -60, -90, -110, -70, -130]
    series = _series("2025-01-02", baseline + recent)
    sig = detect(series, recent_window_days=10, baseline_window_days=60,
                 divergence_threshold=0.5)
    assert sig.regime == NOVEL_REGIME
    adj = sig.threshold_adjustments
    assert adj["min_triggers_bear_floor"] >= 2
    assert adj["size_modifier"] <= 0.5


def test_threshold_adjustments_default_for_mixed():
    series = _series("2025-01-02", [10.0] * 70)  # constant -> Sharpe 0 -> MIXED
    sig = detect(series, divergence_threshold=0.5)
    assert sig.regime == MIXED
    adj = sig.threshold_adjustments
    assert adj["min_triggers_bear_floor"] == 1


def test_save_load_roundtrip(tmp_path):
    sig = RegimeSignal(
        regime=NOVEL_REGIME, recent_sharpe=-1.5, baseline_sharpe=2.0,
        delta_sharpe=-3.5, n_recent=10, n_baseline=60,
        recent_total_pnl=-500.0, baseline_total_pnl=3000.0,
        detected_at="2026-05-08T12:00:00",
        threshold_adjustments={"min_triggers_bear_floor": 2},
        notes="test",
    )
    path = tmp_path / "regime.json"
    save_regime(sig, path)
    loaded = load_regime(path)
    assert loaded.regime == NOVEL_REGIME
    assert loaded.delta_sharpe == -3.5
    assert loaded.threshold_adjustments["min_triggers_bear_floor"] == 2


def test_load_returns_none_when_missing(tmp_path):
    assert load_regime(tmp_path / "missing.json") is None


def test_invalid_window_raises():
    with pytest.raises(ValueError):
        detect({}, recent_window_days=0)
    with pytest.raises(ValueError):
        detect({}, recent_window_days=10, baseline_window_days=5)


@dataclass
class _FakeFill:
    entry_time_et: dt.datetime
    dollar_pnl: float


def test_trades_to_daily_pnl_aggregates():
    trades = [
        _FakeFill(dt.datetime(2026, 1, 5, 10, 0), 100),
        _FakeFill(dt.datetime(2026, 1, 5, 14, 0), 50),
        _FakeFill(dt.datetime(2026, 1, 6, 11, 0), -75),
    ]
    daily = trades_to_daily_pnl(trades)
    assert daily[dt.date(2026, 1, 5)] == 150
    assert daily[dt.date(2026, 1, 6)] == -75


def test_ref_date_clips_to_history():
    series = _series("2025-01-02", [10.0] * 50)
    # Pick a ref date that's 20 days into the series
    ref = sorted(series.keys())[20]
    sig = detect(series, recent_window_days=5, baseline_window_days=10, ref_date=ref)
    # n_recent <= 5, n_baseline <= 10, all dates <= ref
    assert sig.n_recent == 5
    assert sig.n_baseline == 10
