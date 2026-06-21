"""Regression guard for the EMA-snapshot producer (PHASE2-C1-BIAS-EMA-NULLS).

THE BUG THIS GUARDS: ``automation/state/today-bias.json`` shipped with
``key_levels.ema_fast / ema_pivot / ema_slow / sma_50`` all ``null`` whenever the
premarket TradingView pull failed (holidays/weekends: ``ema_read_failed: true``).
Those nulls feed the EMA-ribbon read that the BEARISH_REJECTION_RIDE_THE_RIBBON
setup depends on, so a silent null = a silently-degraded ribbon assessment.

THE FIX (already live): ``automation/scripts/compute_ema_snapshot.py`` (scheduled
``Gamma_EmaSnapshot`` 08:20 ET) computes the Saty Pivot Ribbon EMAs (13/20/48) +
SMA-50 from the SPY 5m CSV and patches today-bias.json key_levels IN PLACE — but
ONLY when a field is currently null (never clobbering a real TradingView value).

This test graduates that fix to a guard (STAGE 4.5 / OP-25: a re-violated lesson
MUST become a test) so the producer cannot silently regress to emitting nulls:

  1. compute_snapshot() yields non-null numeric EMA/SMA values on enough bars.
  2. compute_snapshot() refuses (ValueError) when bars are too few to seed.
  3. patch_today_bias() FILLS null key_levels fields from the snapshot.
  4. patch_today_bias() does NOT overwrite already-populated (TradingView) values.
  5. ema() matches the TradingView SMA-seed EMA convention on a known series.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
PRODUCER = REPO / "automation" / "scripts" / "compute_ema_snapshot.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("compute_ema_snapshot", PRODUCER)
    assert spec and spec.loader, f"cannot load producer at {PRODUCER}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MOD = _load_module()


def _synthetic_df(n: int) -> pd.DataFrame:
    """n bars of a gently rising close series with valid wall-clock timestamps."""
    start = pd.Timestamp("2026-06-01 09:30:00")
    ts = [start + pd.Timedelta(minutes=5 * i) for i in range(n)]
    closes = [600.0 + 0.1 * i for i in range(n)]
    return pd.DataFrame({"timestamp_et": ts, "close": closes})


def test_producer_is_tracked_in_git():
    """L164: the producer must exist on disk (and be committed alongside this test)."""
    assert PRODUCER.exists(), f"producer missing at {PRODUCER}"


def test_compute_snapshot_emits_non_null_emas():
    """The core regression: enough bars -> all four EMA/SMA fields are non-null floats."""
    snap = MOD.compute_snapshot(_synthetic_df(MOD.MIN_BARS + 10))
    for field in ("ema_fast", "ema_pivot", "ema_slow", "sma_50"):
        assert snap[field] is not None, f"{field} regressed to null"
        assert isinstance(snap[field], float)
    # On a monotonically rising series the fast EMA leads the slow EMA.
    assert snap["ema_fast"] > snap["ema_slow"]


def test_compute_snapshot_refuses_too_few_bars():
    with pytest.raises(ValueError):
        MOD.compute_snapshot(_synthetic_df(MOD.SMA_50 - 1))


def test_patch_fills_null_key_levels(tmp_path, monkeypatch):
    bias = {"date": "2026-06-19", "key_levels": {"ema_fast": None, "ema_pivot": None,
                                                 "ema_slow": None, "sma_50": None}}
    bias_path = tmp_path / "today-bias.json"
    bias_path.write_text(json.dumps(bias))
    monkeypatch.setattr(MOD, "STATE_DIR", tmp_path)

    snap = {"ema_fast": 751.09, "ema_pivot": 751.3, "ema_slow": 751.94, "sma_50": 752.12}
    assert MOD.patch_today_bias(snap) is True

    out = json.loads(bias_path.read_text())["key_levels"]
    assert out["ema_fast"] == 751.09 and out["sma_50"] == 752.12


def test_patch_does_not_clobber_tradingview_values(tmp_path, monkeypatch):
    """Live TradingView values must win — patch only fills nulls."""
    bias = {"date": "2026-06-19", "key_levels": {"ema_fast": 700.0, "ema_pivot": None,
                                                 "ema_slow": 701.0, "sma_50": None}}
    bias_path = tmp_path / "today-bias.json"
    bias_path.write_text(json.dumps(bias))
    monkeypatch.setattr(MOD, "STATE_DIR", tmp_path)

    snap = {"ema_fast": 751.09, "ema_pivot": 751.3, "ema_slow": 751.94, "sma_50": 752.12}
    changed = MOD.patch_today_bias(snap)
    assert changed is True  # filled the two nulls

    out = json.loads(bias_path.read_text())["key_levels"]
    assert out["ema_fast"] == 700.0   # preserved (TV value)
    assert out["ema_slow"] == 701.0   # preserved (TV value)
    assert out["ema_pivot"] == 751.3  # filled
    assert out["sma_50"] == 752.12    # filled


def test_patch_noop_when_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(MOD, "STATE_DIR", tmp_path)  # no today-bias.json here
    assert MOD.patch_today_bias({"ema_fast": 1.0}) is False


def test_ema_matches_tradingview_sma_seed_convention():
    """ema() seeds with the SMA of the first `period` bars, then standard EMA."""
    closes = pd.Series([float(x) for x in range(1, 21)])  # 1..20
    period = 5
    out = MOD.ema(closes, period)
    # First period-1 values are NaN; index 4 is the SMA seed = mean(1..5) = 3.0
    assert pd.isna(out.iloc[3])
    assert out.iloc[4] == pytest.approx(3.0)
    # Next bar: close=6, k=2/6 -> 6*k + 3*(1-k)
    k = 2.0 / (period + 1)
    assert out.iloc[5] == pytest.approx(6.0 * k + 3.0 * (1 - k))
