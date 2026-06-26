"""Graduated guard for L171 — tight-stop truncation manufactures fake edge.

Pins the cross-check that disqualifies a "candidate" whose only positive grid
cell sits at a tight premium stop while the SAME signal on the SAME strike at
chart-stop-only (-0.99) is negative. The IBS new-hunt is the reproducer:
strike_offset=-1 / stop=-8% -> +$5.3/trade, but the same strike at chart-stop-only
-> -$19.6/trade (sign inverts == truncation artifact, not edge).

See: backtest/lib/truncation_guard.py, markdown/doctrine/LESSONS-LEARNED.md L171,
CLAUDE.md C2 (L51/L55/L64), C4, C3/L58.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

BACKTEST = Path(__file__).resolve().parents[1]   # backtest/
ROOT = BACKTEST.parent                            # repo root (42/)
sys.path.insert(0, str(BACKTEST))

from lib.truncation_guard import (  # noqa: E402
    CHART_STOP_ONLY_PCT,
    TIGHT_STOP_THRESHOLD,
    TruncationVerdict,
    cross_check_grid,
    is_truncation_artifact,
)

IBS_JSON = ROOT / "analysis" / "recommendations" / "newhunt-ibs-mean-reversion.json"


def _cell(strike: int, stop: float, avg: float) -> dict:
    """Minimal grid cell in the IBS/real-fills layout."""
    return {"strike_offset": strike, "premium_stop_pct": stop, "overall": {"avg_pnl": avg}}


# ── is_truncation_artifact: the core boolean ──────────────────────────────────

def test_artifact_when_tight_stop_positive_but_chart_stop_negative():
    # IBS shape: +$5.3 at the tight stop, -$19.6 at chart-stop-only.
    assert is_truncation_artifact(
        best_per_trade=5.3,
        chart_stop_only_per_trade=-19.6,
        best_premium_stop_pct=-0.08,
    ) is True


def test_not_artifact_when_chart_stop_also_positive():
    # Sign HOLDS across the stop axis -> a genuine edge, not truncation.
    assert is_truncation_artifact(
        best_per_trade=5.3,
        chart_stop_only_per_trade=4.0,
        best_premium_stop_pct=-0.08,
    ) is False


def test_not_artifact_when_best_cell_is_chart_stop_only():
    # If the chosen cell IS the loose stop, it cannot be a tight-stop artifact
    # (-0.99 is not > -0.30).
    assert is_truncation_artifact(
        best_per_trade=5.3,
        chart_stop_only_per_trade=5.3,
        best_premium_stop_pct=-0.99,
    ) is False


def test_not_artifact_when_best_cell_negative():
    assert is_truncation_artifact(
        best_per_trade=-4.0,
        chart_stop_only_per_trade=-19.6,
        best_premium_stop_pct=-0.08,
    ) is False


def test_none_per_trade_treated_as_zero():
    # Matches the reference `(avg or 0) > 0` guard: None -> not positive -> no artifact.
    assert is_truncation_artifact(
        best_per_trade=None,
        chart_stop_only_per_trade=-19.6,
        best_premium_stop_pct=-0.08,
    ) is False


def test_fails_open_when_chart_stop_only_missing():
    # No reference cell -> cannot disprove -> NOT flagged (outer gate still governs).
    assert is_truncation_artifact(
        best_per_trade=5.3,
        chart_stop_only_per_trade=None,
        best_premium_stop_pct=-0.08,
    ) is False


def test_threshold_boundary_is_exclusive():
    # Reference uses strict `best_ps > -0.30`: exactly -0.30 is NOT tight.
    assert is_truncation_artifact(
        best_per_trade=5.3, chart_stop_only_per_trade=-19.6, best_premium_stop_pct=TIGHT_STOP_THRESHOLD,
    ) is False
    # Just tighter than the threshold IS tight.
    assert is_truncation_artifact(
        best_per_trade=5.3, chart_stop_only_per_trade=-19.6, best_premium_stop_pct=-0.20,
    ) is True


# ── cross_check_grid: grid lookup + verdict ───────────────────────────────────

def test_cross_check_grid_flags_ibs_shaped_grid():
    grid = [
        _cell(-1, -0.08, 5.3),
        _cell(-1, -0.20, -10.4),
        _cell(-1, -0.50, -19.0),
        _cell(-1, -0.99, -19.6),
        _cell(0, -0.08, 2.3),
        _cell(0, -0.99, -16.9),
    ]
    best = _cell(-1, -0.08, 5.3)
    v = cross_check_grid(grid, best)
    assert isinstance(v, TruncationVerdict)
    assert v.is_artifact is True
    assert v.passes is False
    assert v.chart_stop_only_per_trade == -19.6
    assert v.best_strike_offset == -1
    assert "TRUNCATION ARTIFACT" in v.reason


def test_cross_check_grid_passes_a_genuine_edge():
    # Same signal stays positive even at chart-stop-only -> real edge.
    grid = [_cell(-1, -0.08, 5.3), _cell(-1, -0.99, 3.0)]
    v = cross_check_grid(grid, _cell(-1, -0.08, 5.3))
    assert v.is_artifact is False
    assert v.passes is True
    assert v.chart_stop_only_per_trade == 3.0


def test_cross_check_grid_fails_open_without_loose_cell():
    grid = [_cell(-1, -0.08, 5.3)]   # no -0.99 cell at this strike
    v = cross_check_grid(grid, _cell(-1, -0.08, 5.3))
    assert v.is_artifact is False
    assert v.chart_stop_only_per_trade is None
    assert "NOT disproved" in v.reason


def test_cross_check_grid_uses_same_strike_only():
    # A negative chart-stop-only at a DIFFERENT strike must not trigger the flag.
    grid = [_cell(-1, -0.08, 5.3), _cell(0, -0.99, -16.9)]   # no (-1, -0.99)
    v = cross_check_grid(grid, _cell(-1, -0.08, 5.3))
    assert v.is_artifact is False           # fails open: no same-strike loose cell
    assert v.chart_stop_only_per_trade is None


# ── Integration: reproduce the committed IBS verdict from the real grid ────────

@pytest.mark.skipif(not IBS_JSON.exists(), reason="IBS recommendation JSON not present")
def test_matches_committed_ibs_recommendation():
    data = json.loads(IBS_JSON.read_text(encoding="utf-8"))
    grid = data["grid"]
    # Reconstruct the chosen cell (best_config: strike_offset=-1, premium_stop_pct=-0.08).
    best = next(
        c for c in grid
        if c["strike_offset"] == -1 and c["premium_stop_pct"] == -0.08
    )
    v = cross_check_grid(grid, best)
    # The helper must reproduce exactly what the IBS script self-verified + committed.
    assert v.is_artifact is True
    assert v.chart_stop_only_per_trade == -19.6
    assert data["self_verify"]["is_truncation_artifact"] is True
    assert data["self_verify"]["same_strike_chart_stop_only_per_trade"] == v.chart_stop_only_per_trade
    assert data["clears_bar"] is False


def test_defaults_are_the_reference_values():
    assert CHART_STOP_ONLY_PCT == -0.99
    assert TIGHT_STOP_THRESHOLD == -0.30
