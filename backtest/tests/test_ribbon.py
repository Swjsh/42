"""Validate ribbon computation against live values from TradingView MCP.

The acid test: compute Fast/Pivot/Slow EMAs on the 120-bar fixture and verify the
final values match the live indicator output within 5 cents.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.ribbon import ema, compute_ribbon, ribbon_at, load_periods, RibbonState  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
TOLERANCE_CENTS = 5  # 0.05 dollars — same tolerance the fingerprinter used


def _load_fingerprint_fixture():
    bars = pd.read_csv(REPO / "fixtures" / "recent_120bars.csv")
    live = json.loads((REPO / "fixtures" / "live_ribbon_snapshot.json").read_text())
    return bars["close"], live["live_ribbon_values"]


def test_ema_smoke():
    """EMA of a constant series should equal the constant after warmup."""
    s = pd.Series([100.0] * 50)
    result = ema(s, 13)
    assert np.isnan(result[:12]).all()
    assert np.allclose(result[12:], 100.0)


def test_ema_known_value():
    """EMA on a simple ramp should produce a known closed-form output."""
    # Linear ramp 1..50; EMA(13) at end ≈ a SMA-seeded value that approaches 38.07.
    s = pd.Series(np.arange(1, 51, dtype=float))
    result = ema(s, 13)
    # The first 13 values: SMA of 1..13 = 7. Then EMA recursion.
    assert result[12] == pytest.approx(7.0)
    # By bar 50, with strong upward ramp, EMA(13) should track recent values.
    # Mean of last 13 (38..50) = 44; EMA tracks around there with bias to most recent.
    assert 42.0 < result[-1] < 49.0


def test_ribbon_matches_live_fingerprint():
    """The whole point: our EMAs must reproduce the live Saty Pivot Ribbon values."""
    closes, live_values = _load_fingerprint_fixture()
    ribbon_df = compute_ribbon(closes)

    last = ribbon_df.iloc[-1]
    assert abs(last["fast"] - live_values["Fast EMA"]) * 100 <= TOLERANCE_CENTS, \
        f"Fast EMA mismatch: computed {last['fast']:.4f} vs live {live_values['Fast EMA']}"
    assert abs(last["pivot"] - live_values["Pivot EMA"]) * 100 <= TOLERANCE_CENTS, \
        f"Pivot EMA mismatch: computed {last['pivot']:.4f} vs live {live_values['Pivot EMA']}"
    assert abs(last["slow"] - live_values["Slow EMA"]) * 100 <= TOLERANCE_CENTS, \
        f"Slow EMA mismatch: computed {last['slow']:.4f} vs live {live_values['Slow EMA']}"


def test_stack_classification():
    """Strictly ordered Fast > Pivot > Slow = BULL; reverse = BEAR; interleaved = MIXED."""
    closes, _ = _load_fingerprint_fixture()
    ribbon_df = compute_ribbon(closes)

    # Verify stack values are one of the expected enum
    valid_stacks = {"BULL", "BEAR", "MIXED", "WARMUP"}
    assert set(ribbon_df["stack"].unique()) <= valid_stacks

    # Count warmup bars — should equal slow_ema_period - 1 (longest EMA needs warmup)
    periods = load_periods()
    expected_warmup = periods["slow_ema"] - 1
    actual_warmup = (ribbon_df["stack"] == "WARMUP").sum()
    assert actual_warmup == expected_warmup, \
        f"Warmup count mismatch: expected {expected_warmup}, got {actual_warmup}"


def test_spread_cents():
    """Spread should equal (max - min) of the 3 EMAs in cents."""
    closes, live_values = _load_fingerprint_fixture()
    ribbon_df = compute_ribbon(closes)
    last = ribbon_df.iloc[-1]

    # From live: max=733.09 (Slow), min=733.00 (Fast). Spread = 0.09 = 9 cents.
    expected_spread = (
        max(live_values["Fast EMA"], live_values["Pivot EMA"], live_values["Slow EMA"])
        - min(live_values["Fast EMA"], live_values["Pivot EMA"], live_values["Slow EMA"])
    ) * 100
    assert abs(last["spread_cents"] - expected_spread) <= TOLERANCE_CENTS


def test_ribbon_at_warmup_returns_none():
    """Bars within the warmup window should return None when queried."""
    closes, _ = _load_fingerprint_fixture()
    ribbon_df = compute_ribbon(closes)
    state = ribbon_at(ribbon_df, ribbon_df.index[0])
    assert state is None


def test_ribbon_at_post_warmup_returns_state():
    """Bars after warmup should return a populated RibbonState."""
    closes, _ = _load_fingerprint_fixture()
    ribbon_df = compute_ribbon(closes)
    state = ribbon_at(ribbon_df, ribbon_df.index[-1])
    assert isinstance(state, RibbonState)
    assert state.stack in {"BULL", "BEAR", "MIXED"}
    assert state.spread_cents >= 0
