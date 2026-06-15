"""Pytest fixtures for pressure tests.

Provides reusable loaders for SPY/VIX bars at specific dates and a clean module
fixture that lets each test inject its own params.json overrides.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

# Make backtest/ importable from any pressure_test file.
REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from autoresearch import runner  # noqa: E402
from lib import filters as filters_mod  # noqa: E402


@pytest.fixture(scope="session")
def spy_vix_bars() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load full SPY/VIX 5m dataset once per pytest session.

    Pressure tests slice this dataframe at the date+time of the loss.
    Loading once at session scope amortises CSV-parse cost.
    """
    start = dt.date(2025, 1, 1)
    end = dt.date.today()
    return runner.load_data(start, end)


@pytest.fixture
def bars_at_window(spy_vix_bars):
    """Factory fixture: returns a function that slices to a (start_dt, end_dt) window.

    Usage in test:
        def test_X(bars_at_window):
            spy, vix = bars_at_window("2026-04-15 10:30", "2026-04-15 12:00")
            ...
    """
    spy_full, vix_full = spy_vix_bars

    def _slice(start_iso: str, end_iso: str) -> tuple[pd.DataFrame, pd.DataFrame]:
        start = pd.to_datetime(start_iso).tz_localize("US/Eastern")
        end = pd.to_datetime(end_iso).tz_localize("US/Eastern")
        spy = spy_full[(spy_full["timestamp_et"] >= start) & (spy_full["timestamp_et"] <= end)].copy()
        vix = vix_full[(vix_full["timestamp_et"] >= start) & (vix_full["timestamp_et"] <= end)].copy()
        return spy, vix

    return _slice


@pytest.fixture
def production_v14_params() -> dict[str, Any]:
    """The current production param set. Pressure tests run against THIS first
    (RED — confirm the loss reproduces) then run again with the candidate
    filter active (GREEN — confirm the filter blocks it).
    """
    import json
    params_path = REPO.parent / "automation" / "state" / "params.json"
    return json.loads(params_path.read_text(encoding="utf-8"))


@pytest.fixture
def fresh_filters_module():
    """Reset module-level constants in lib.filters to defaults before each test.

    Prevents test ordering from contaminating subsequent tests. Pairs with
    runner._patched_filter_constants which sets per-test overrides.
    """
    # Snapshot defaults (these are the module-level constants in filters.py).
    snapshot = {
        attr: getattr(filters_mod, attr)
        for attr in dir(filters_mod)
        if attr.isupper() and not attr.startswith("_")
    }
    yield filters_mod
    # Restore.
    for k, v in snapshot.items():
        setattr(filters_mod, k, v)


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "pressure: mark a test as a pressure test")
    config.addinivalue_line("markers", "r_id(id): tag with R-NNNN fingerprint id")
    config.addinivalue_line("markers", "slow: mark a test as slow (full validate-window run)")
