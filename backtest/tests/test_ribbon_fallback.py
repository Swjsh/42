"""Tests for backtest/lib/ribbon_fallback.py — the Alpaca-OHLCV->Saty-ribbon fallback
compute core (Layer-1a of OPEN-BLINDNESS-TV-HANG).

The load-bearing test is `test_parity_with_compute_ema_snapshot`: it pins the fallback's
EMA math to be byte-identical to the canonical reference implementation
(automation/scripts/compute_ema_snapshot.py), so the engine's TV-down fallback can never
silently make a DIFFERENT ribbon decision than the live TV indicator (C11 / L180 same-
opportunity-set trap). If anyone edits either EMA, this test fails loud.
"""

from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path

import pytest

from backtest.lib import ribbon_fallback as rf

_REPO = Path(__file__).resolve().parents[2]
_CONFIG = _REPO / "backtest" / "lib" / "ribbon_config.json"


def _load_reference_ema():
    """Import automation/scripts/compute_ema_snapshot.py directly (the canonical producer)
    and return its pandas-based ema() function."""
    path = _REPO / "automation" / "scripts" / "compute_ema_snapshot.py"
    spec = importlib.util.spec_from_file_location("compute_ema_snapshot_ref", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod.ema


def _synthetic_closes(n: int = 250) -> list[float]:
    """Deterministic non-trivial close walk (no RNG — reproducible)."""
    out = []
    price = 700.0
    for i in range(n):
        price += math.sin(i / 7.0) * 0.8 + (0.05 if i % 3 == 0 else -0.03)
        out.append(round(price, 2))
    return out


# --- spec / drift guards ---------------------------------------------------

def test_periods_loaded_from_config_and_match_fingerprint():
    periods = rf.load_periods()
    assert periods == {"fast_ema": 13, "pivot_ema": 20, "slow_ema": 48, "sma_50": 50}
    # Canary: the on-disk fingerprinted config still holds these exact values.
    cfg = json.loads(_CONFIG.read_text(encoding="utf-8"))
    assert cfg["periods"]["fast_ema"] == 13
    assert cfg["periods"]["pivot_ema"] == 20
    assert cfg["periods"]["slow_ema"] == 48


# --- the C11/L180 same-decision parity guard -------------------------------

def test_parity_with_compute_ema_snapshot():
    """ribbon_fallback.tv_ema must equal the reference compute_ema_snapshot.ema's LAST
    value to floating precision, for every canonical period. This is what guarantees the
    TV-down fallback makes the SAME ribbon decision the live TV read would have made."""
    pd = pytest.importorskip("pandas")
    closes = _synthetic_closes(250)
    ref_ema = _load_reference_ema()
    series = pd.Series(closes, dtype="float64")
    for period in (13, 20, 48, 51):
        ref_last = float(ref_ema(series, period).iloc[-1])
        ours = rf.tv_ema(closes, period)
        assert ours is not None
        assert abs(ours - ref_last) < 1e-9, f"period={period}: {ours} vs {ref_last}"


# --- stack classification --------------------------------------------------

def test_classify_stack_bull_bear_mixed_unknown():
    assert rf.classify_stack(10.0, 9.0, 8.0) == "BULL"
    assert rf.classify_stack(8.0, 9.0, 10.0) == "BEAR"
    assert rf.classify_stack(9.0, 10.0, 8.0) == "MIXED"  # not monotonic
    assert rf.classify_stack(9.0, 9.0, 9.0) == "MIXED"   # flat / equal => not strict
    assert rf.classify_stack(None, 9.0, 8.0) == "UNKNOWN"


def test_spread_cents_is_ribbon_width():
    r = rf.compute_ribbon(_synthetic_closes(250))
    assert r.spread_cents is not None
    assert r.ema_fast is not None and r.ema_slow is not None
    expected = round(abs(r.ema_fast - r.ema_slow) * 100, 1)
    assert r.spread_cents == expected


# --- fail-closed on short input --------------------------------------------

def test_insufficient_bars_fail_closed_no_raise():
    # Fewer bars than the slow period => slow EMA cannot seed => UNKNOWN, no exception.
    r = rf.compute_ribbon([700.0, 700.5, 701.0])  # 3 bars < 48
    assert r.stack == "UNKNOWN"
    assert r.ema_slow is None
    assert r.spread_cents is None
    assert r.is_usable() is False
    assert r.price == 701.0  # price still available from the last bar
    assert r.bars_used == 3


def test_empty_input_does_not_raise():
    r = rf.compute_ribbon([])
    assert r.stack == "UNKNOWN"
    assert r.price is None
    assert r.is_usable() is False


# --- full read + monotonic stacks ------------------------------------------

def test_compute_ribbon_clean_bull_stack():
    # Strictly rising series => fast EMA above pivot above slow => BULL.
    closes = [700.0 + i * 0.5 for i in range(120)]
    r = rf.compute_ribbon(closes, source="test")
    assert r.stack == "BULL"
    assert r.is_usable() is True
    assert r.price == closes[-1]
    assert r.ema_fast > r.ema_pivot > r.ema_slow
    assert r.source == "test"


def test_compute_ribbon_clean_bear_stack():
    closes = [760.0 - i * 0.5 for i in range(120)]
    r = rf.compute_ribbon(closes)
    assert r.stack == "BEAR"
    assert r.ema_fast < r.ema_pivot < r.ema_slow


# --- bar extraction --------------------------------------------------------

def test_closes_from_bars_key_spellings():
    bars = [{"c": 1.0}, {"close": 2.0}, {"Close": 3.0}]
    assert rf.closes_from_bars(bars) == [1.0, 2.0, 3.0]


def test_closes_from_bars_malformed_raises():
    with pytest.raises(KeyError):
        rf.closes_from_bars([{"open": 1.0, "high": 2.0}])


def test_frozen_dataclass_is_immutable():
    r = rf.compute_ribbon(_synthetic_closes(120))
    with pytest.raises(Exception):
        r.stack = "BULL"  # type: ignore[misc]
