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

EMA-STALENESS FIX (2026-06-28):
  6. _csv_end_date() parses the end-date from spy_5m filenames correctly.
  7. load_latest_spy() selects the CSV with the newest end-date, NOT the largest
     file size (the root-cause of the 10-day-stale EMA injection).
  8. _spot_deviation_ok() rejects a snapshot whose last_close deviates >3% from
     the live sight-beacon spot (catches wrong-CSV selection at patch time).
  9. patch_today_bias() refuses to patch when the spot-deviation guard fires.
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


# ---------------------------------------------------------------------------
# EMA-STALENESS FIX GUARDS (2026-06-28)
# Root cause: load_latest_spy sorted by st_size, picking a large old file
# (spy_5m_2025-01-01_2026-06-18.csv) over the smaller but newer file
# (spy_5m_2026-05-19_2026-06-26.csv) -> 10-day-stale EMA values in today-bias.
# ---------------------------------------------------------------------------

def test_csv_end_date_parses_standard_filename():
    """_csv_end_date() extracts the end-date from a standard spy_5m filename."""
    import datetime as dt
    p = Path("spy_5m_2025-01-01_2026-06-26.csv")
    assert MOD._csv_end_date(p) == dt.date(2026, 6, 26)


def test_csv_end_date_parses_merged_filename():
    """_csv_end_date() works on filenames with _merged suffix."""
    import datetime as dt
    p = Path("spy_5m_2025-01-01_2026-05-19_merged.csv")
    assert MOD._csv_end_date(p) == dt.date(2026, 5, 19)


def test_csv_end_date_returns_min_for_unparseable():
    """_csv_end_date() returns date.min for filenames that don't match the pattern."""
    import datetime as dt
    assert MOD._csv_end_date(Path("random_file.csv")) == dt.date.min


def test_load_latest_spy_selects_by_end_date_not_size(tmp_path, monkeypatch):
    """Regression: load_latest_spy must pick the CSV with the newest end-date.

    Scenario mirrors the 2026-06-28 incident: a large old file
    (end=2026-06-18) and a smaller newer file (end=2026-06-26).
    The function must pick the newer file regardless of size.
    """
    import datetime as dt

    # Build the newer (smaller) CSV — 2 days of 5-min bars
    newer_rows = MOD.MIN_BARS + 5
    start = pd.Timestamp("2026-06-25 09:30:00")
    ts_new = [start + pd.Timedelta(minutes=5 * i) for i in range(newer_rows)]
    closes_new = [730.0 + 0.01 * i for i in range(newer_rows)]
    df_new = pd.DataFrame({"timestamp_et": [str(t) for t in ts_new], "close": closes_new})
    newer_csv = tmp_path / "spy_5m_2026-06-25_2026-06-26.csv"
    df_new.to_csv(newer_csv, index=False)

    # Build the older (larger) CSV — many more rows so it wins by size
    older_rows = MOD.MIN_BARS + 100
    start_old = pd.Timestamp("2025-01-01 09:30:00")
    ts_old = [start_old + pd.Timedelta(minutes=5 * i) for i in range(older_rows)]
    closes_old = [720.0 + 0.01 * i for i in range(older_rows)]
    df_old = pd.DataFrame({"timestamp_et": [str(t) for t in ts_old], "close": closes_old})
    older_csv = tmp_path / "spy_5m_2025-01-01_2026-06-18.csv"
    df_old.to_csv(older_csv, index=False)

    # Verify older file is actually larger (confirms the scenario)
    assert older_csv.stat().st_size > newer_csv.stat().st_size, \
        "test setup broken: old file should be larger"

    monkeypatch.setattr(MOD, "DATA_DIR", tmp_path)
    df = MOD.load_latest_spy()
    assert df is not None

    # The last bar's close should come from the NEWER file (closes_new[-1] ~ 730.5)
    last_close = float(df.iloc[-1]["close"])
    assert last_close == pytest.approx(closes_new[-1], abs=0.01), (
        f"load_latest_spy picked the wrong CSV: last_close={last_close} "
        f"(expected ~{closes_new[-1]} from 2026-06-26, not ~{closes_old[-1]} from 2026-06-18)"
    )


def test_spot_deviation_ok_passes_within_threshold(tmp_path):
    """_spot_deviation_ok() returns True when deviation is within 3%."""
    beacon = {"spy": 730.0, "ok": True}
    bp = tmp_path / "sight-beacon.json"
    bp.write_text(json.dumps(beacon))
    # 1% deviation — should pass
    snap = {"last_close": 737.3}
    assert MOD._spot_deviation_ok(snap, bp) is True


def test_spot_deviation_ok_fails_beyond_threshold(tmp_path):
    """_spot_deviation_ok() returns False when deviation exceeds 3%."""
    beacon = {"spy": 730.0, "ok": True}
    bp = tmp_path / "sight-beacon.json"
    bp.write_text(json.dumps(beacon))
    # 4% deviation — should fail
    snap = {"last_close": 759.2}
    assert MOD._spot_deviation_ok(snap, bp) is False


def test_spot_deviation_ok_failopen_missing_beacon(tmp_path):
    """_spot_deviation_ok() fails-open (returns True) when beacon file is absent."""
    bp = tmp_path / "no-beacon.json"  # does not exist
    snap = {"last_close": 999.0}
    assert MOD._spot_deviation_ok(snap, bp) is True


def test_spot_deviation_ok_failopen_missing_spot(tmp_path):
    """_spot_deviation_ok() fails-open when beacon has no 'spy' field."""
    beacon = {"ok": True}  # no 'spy' key
    bp = tmp_path / "sight-beacon.json"
    bp.write_text(json.dumps(beacon))
    snap = {"last_close": 999.0}
    assert MOD._spot_deviation_ok(snap, bp) is True


def test_patch_rejected_when_spot_deviates(tmp_path, monkeypatch):
    """patch_today_bias() must NOT patch when spot-deviation guard fires.

    Regression guard: a stale CSV producing a last_close 4% from the live spot
    should never contaminate today-bias with stale EMA values.
    """
    bias = {"date": "2026-06-28", "key_levels": {"ema_fast": None, "ema_pivot": None,
                                                  "ema_slow": None, "sma_50": None}}
    bias_path = tmp_path / "today-bias.json"
    bias_path.write_text(json.dumps(bias))

    # Beacon spot = 730; snapshot last_close = 759 (4% deviation — should block)
    beacon = {"spy": 730.0, "ok": True}
    beacon_path = tmp_path / "sight-beacon.json"
    beacon_path.write_text(json.dumps(beacon))

    monkeypatch.setattr(MOD, "STATE_DIR", tmp_path)
    snap = {"last_close": 759.2, "ema_fast": 758.0, "ema_pivot": 758.5,
            "ema_slow": 759.0, "sma_50": 759.5}
    result = MOD.patch_today_bias(snap, beacon_path=beacon_path)
    assert result is False, "patch should have been blocked by spot-deviation guard"

    # today-bias must remain untouched
    out = json.loads(bias_path.read_text())["key_levels"]
    assert out["ema_fast"] is None, "stale EMA must not have been written to today-bias"


def test_patch_proceeds_when_spot_within_threshold(tmp_path, monkeypatch):
    """patch_today_bias() patches normally when spot-deviation is within 3%."""
    bias = {"date": "2026-06-28", "key_levels": {"ema_fast": None, "ema_pivot": None,
                                                  "ema_slow": None, "sma_50": None}}
    bias_path = tmp_path / "today-bias.json"
    bias_path.write_text(json.dumps(bias))

    # Beacon spot = 730; last_close = 737 (< 1% deviation — should pass)
    beacon = {"spy": 730.0, "ok": True}
    beacon_path = tmp_path / "sight-beacon.json"
    beacon_path.write_text(json.dumps(beacon))

    monkeypatch.setattr(MOD, "STATE_DIR", tmp_path)
    snap = {"last_close": 737.3, "ema_fast": 731.9, "ema_pivot": 732.2,
            "ema_slow": 732.8, "sma_50": 733.3}
    result = MOD.patch_today_bias(snap, beacon_path=beacon_path)
    assert result is True

    out = json.loads(bias_path.read_text())["key_levels"]
    assert out["ema_fast"] == 731.9
