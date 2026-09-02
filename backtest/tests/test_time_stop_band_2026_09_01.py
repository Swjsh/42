"""Tests for setup/scripts/measure_time_stop_band.py band-classification helpers (B6).

MEASUREMENT-ONLY module -- these tests cover the pure classification helpers with synthetic
rows (in_band / in_strict_band / still_open_at / classify_moneyness / spy_close_at), not the
live network fetch. RED-PROOF: test_in_band_excludes_before_1520 is asserted to FAIL when the
lower bound is loosened to 15:00 (mechanism check, not just a passing-test check).
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import measure_time_stop_band as mod  # noqa: E402


def test_in_band_boundaries():
    assert mod.in_band("2026-08-15T15:20:00") is True
    assert mod.in_band("2026-08-15T15:40:00") is True
    assert mod.in_band("2026-08-15T15:19:59") is False
    assert mod.in_band("2026-08-15T15:40:01") is False


def test_in_strict_band_excludes_15_20_to_15_25():
    assert mod.in_strict_band("2026-08-15T15:22:00") is False
    assert mod.in_strict_band("2026-08-15T15:25:00") is True
    assert mod.in_strict_band("2026-08-15T15:39:59") is True


def test_in_band_excludes_before_1520():
    """RED-PROOF mechanism: in_band must NOT count a 15:10 exit as in the [15:20,15:40]
    band. Broken deliberately below by widening the lower bound to 15:00, which must make
    the assertion FAIL -- proving the test actually discriminates on the boundary rather
    than passing regardless."""
    assert mod.in_band("2026-08-15T15:10:00") is False

    # Break the mechanism: widen the band and confirm the SAME check now fails.
    broken = mod.in_band("2026-08-15T15:10:00", lo=dt.time(15, 0))
    assert broken is True, "sanity: widening the lower bound to 15:00 must flip this to True"
    # (confirms the helper's `lo` parameter is load-bearing -- not a no-op)


def test_still_open_at():
    assert mod.still_open_at("2026-08-15T14:00:00", "2026-08-15T15:35:00", dt.time(15, 30)) is True
    assert mod.still_open_at("2026-08-15T14:00:00", "2026-08-15T15:25:00", dt.time(15, 30)) is False
    assert mod.still_open_at("2026-08-15T15:31:00", "2026-08-15T15:45:00", dt.time(15, 30)) is False


def test_classify_moneyness_call():
    assert mod.classify_moneyness("C", strike=700.0, spot=705.0) == "ITM"
    assert mod.classify_moneyness("C", strike=700.0, spot=695.0) == "OTM"
    assert mod.classify_moneyness("C", strike=700.0, spot=700.30) == "NEAR_ATM"
    assert mod.classify_moneyness("C", strike=700.0, spot=699.60) == "NEAR_ATM"


def test_classify_moneyness_put():
    assert mod.classify_moneyness("P", strike=700.0, spot=695.0) == "ITM"
    assert mod.classify_moneyness("P", strike=700.0, spot=705.0) == "OTM"
    assert mod.classify_moneyness("P", strike=700.0, spot=700.40) == "NEAR_ATM"


def test_classify_moneyness_rejects_bad_right():
    import pytest
    with pytest.raises(ValueError):
        mod.classify_moneyness("X", strike=700.0, spot=700.0)


def test_gross_winner_dollars_only_sums_positive():
    rows = [{"pnl_dollars": 10.0}, {"pnl_dollars": -5.0}, {"pnl_dollars": 20.0}, {"pnl_dollars": 0.0}]
    assert mod.gross_winner_dollars(rows) == 30.0


def test_spy_close_at_picks_latest_bar_not_after_target():
    bars = [
        (dt.datetime(2026, 8, 15, 15, 20), 700.0),
        (dt.datetime(2026, 8, 15, 15, 25), 701.0),
        (dt.datetime(2026, 8, 15, 15, 30), 702.0),
        (dt.datetime(2026, 8, 15, 15, 35), 703.0),
    ]
    assert mod.spy_close_at(bars, "2026-08-15", dt.time(15, 30)) == 702.0
    assert mod.spy_close_at(bars, "2026-08-15", dt.time(15, 33)) == 702.0
    assert mod.spy_close_at(bars, "2026-08-15", dt.time(15, 19)) is None
    assert mod.spy_close_at(bars, "2026-08-16", dt.time(15, 30)) is None


def test_apply_pass_criterion_ship_kill_needsmore():
    measurement_ship = {"band_census": {"band_15_20_to_15_40": {"share_of_gross_winner_dollars_post_2026_08_11": 0.02}}}
    measurement_kill = {"band_census": {"band_15_20_to_15_40": {"share_of_gross_winner_dollars_post_2026_08_11": 0.15}}}
    measurement_needsmore = {"band_census": {"band_15_20_to_15_40": {"share_of_gross_winner_dollars_post_2026_08_11": 0.07}}}
    measurement_empty = {"band_census": {"band_15_20_to_15_40": {"share_of_gross_winner_dollars_post_2026_08_11": None}}}

    assert mod.apply_pass_criterion(measurement_ship)["verdict"] == "SHIP"
    assert mod.apply_pass_criterion(measurement_kill)["verdict"] == "KILL"
    assert mod.apply_pass_criterion(measurement_needsmore)["verdict"] == "NEEDS-MORE"
    assert mod.apply_pass_criterion(measurement_empty)["verdict"] == "NEEDS-MORE"
