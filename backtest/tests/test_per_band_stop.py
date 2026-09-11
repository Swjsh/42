"""Unit tests + red-proof for per_band_stop.py (T-W4, exit-B's machinery -- SHADOW ONLY).

Guard: resolve_stop_pct must correctly bucket entry premiums by band, and must fail LOUD
(ValueError) on a malformed band_table rather than silently mis-resolving. Red-proof
(manually verified this session, not left in the repo): swapping the loop's `<` for `<=`
on the ceiling comparison moves the boundary-value tests (0.20, 0.50 exactly) to the WRONG
band -- test_boundary_values_are_exclusive_of_ceiling catches that class of off-by-one.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_FLEET = _ROOT / "automation" / "state" / "fleet"
if str(_FLEET) not in sys.path:
    sys.path.insert(0, str(_FLEET))

from per_band_stop import StopBand, resolve_stop_pct, EXIT_B_BAND_TABLE  # noqa: E402


def test_exit_b_band_table_shape():
    """The pre-registered exit-B table: <0.20 -> -25%, 0.20-0.50 -> -35%, >=0.50 -> -50%."""
    assert resolve_stop_pct(0.05, EXIT_B_BAND_TABLE) == -0.25
    assert resolve_stop_pct(0.19, EXIT_B_BAND_TABLE) == -0.25
    assert resolve_stop_pct(0.25, EXIT_B_BAND_TABLE) == -0.35
    assert resolve_stop_pct(0.49, EXIT_B_BAND_TABLE) == -0.35
    assert resolve_stop_pct(0.50, EXIT_B_BAND_TABLE) == -0.50
    assert resolve_stop_pct(5.00, EXIT_B_BAND_TABLE) == -0.50


def test_boundary_values_are_exclusive_of_ceiling():
    """entry_premium == ceiling belongs to the NEXT band, not the current one (< not <=)."""
    table = (StopBand(0.20, -0.25), StopBand(None, -0.50))
    assert resolve_stop_pct(0.199999, table) == -0.25
    assert resolve_stop_pct(0.20, table) == -0.50      # exactly at the ceiling -> next band
    assert resolve_stop_pct(0.200001, table) == -0.50


def test_zero_and_negative_premium_fall_into_lowest_band():
    table = (StopBand(0.20, -0.25), StopBand(None, -0.50))
    assert resolve_stop_pct(0.0, table) == -0.25


def test_single_band_table_always_returns_its_stop():
    table = (StopBand(None, -0.42),)
    assert resolve_stop_pct(0.01, table) == -0.42
    assert resolve_stop_pct(999.0, table) == -0.42


def test_empty_table_raises():
    with pytest.raises(ValueError, match="not be empty"):
        resolve_stop_pct(0.30, ())


def test_non_last_band_with_none_ceiling_raises():
    """A None ceiling ANYWHERE but the last position is a malformed table -- fail loud, not
    silently swallow the remaining bands."""
    table = (StopBand(None, -0.25), StopBand(0.50, -0.35), StopBand(None, -0.50))
    with pytest.raises(ValueError, match="only the LAST band"):
        resolve_stop_pct(0.10, table)


def test_last_band_without_none_ceiling_raises():
    """The catch-all band is mandatory -- a table whose last entry has a finite ceiling
    would silently drop any premium above it (fail loud instead)."""
    table = (StopBand(0.20, -0.25), StopBand(0.50, -0.35))
    with pytest.raises(ValueError, match="catch-all"):
        resolve_stop_pct(1.00, table)
