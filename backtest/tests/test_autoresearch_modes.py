"""Tests for STRICT/BALANCED/AGGRESSIVE mode definitions and proposer behaviour."""

from __future__ import annotations

import pytest

from autoresearch import config
from autoresearch.config import (
    AGGRESSIVE_PARAMS,
    BALANCED_PARAMS,
    BASELINE_PARAMS,
    MODES,
    SEARCH_SPACE,
    STRICT_PARAMS,
)


def test_modes_dict_has_three_entries():
    assert set(MODES.keys()) == {"strict", "balanced", "aggressive"}


def test_balanced_matches_baseline():
    assert BALANCED_PARAMS == BASELINE_PARAMS


def test_strict_is_more_restrictive_than_balanced():
    # min_triggers_bear/bull higher -> stricter
    assert STRICT_PARAMS["min_triggers_bear"] >= BALANCED_PARAMS["min_triggers_bear"]
    assert STRICT_PARAMS["min_triggers_bull"] >= BALANCED_PARAMS["min_triggers_bull"]
    # premium_stop tighter (closer to 0) -> stricter
    assert STRICT_PARAMS["premium_stop_pct_bear"] > BALANCED_PARAMS["premium_stop_pct_bear"]
    assert STRICT_PARAMS["premium_stop_pct_bull"] > BALANCED_PARAMS["premium_stop_pct_bull"]
    # ribbon_spread higher -> stricter
    assert STRICT_PARAMS["ribbon_spread_min_cents"] >= BALANCED_PARAMS["ribbon_spread_min_cents"]


def test_aggressive_is_looser_than_balanced():
    assert AGGRESSIVE_PARAMS["min_triggers_bear"] <= BALANCED_PARAMS["min_triggers_bear"]
    # wider stop -> looser
    assert AGGRESSIVE_PARAMS["premium_stop_pct_bear"] <= BALANCED_PARAMS["premium_stop_pct_bear"]
    assert AGGRESSIVE_PARAMS["premium_stop_pct_bull"] <= BALANCED_PARAMS["premium_stop_pct_bull"]
    assert AGGRESSIVE_PARAMS["ribbon_spread_min_cents"] <= BALANCED_PARAMS["ribbon_spread_min_cents"]


def test_all_mode_param_keys_match_baseline_keys():
    """Every mode must specify exactly the same keys as BASELINE_PARAMS."""
    for mode_name, params in MODES.items():
        assert set(params.keys()) == set(BASELINE_PARAMS.keys()), (
            f"mode {mode_name} keys differ from BASELINE_PARAMS"
        )


def test_all_mode_values_are_in_search_space():
    """Sanity check: starting points must be inside SEARCH_SPACE so the proposer
    can navigate from them. Time gates are nullable; everything else must match."""
    for mode_name, params in MODES.items():
        for k, v in params.items():
            space = SEARCH_SPACE.get(k)
            if space is None:
                continue
            assert v in space, (
                f"mode {mode_name}.{k}={v!r} not in SEARCH_SPACE[{k!r}]={space}"
            )


def test_train_validate_window_constants_are_sensible():
    import datetime as dt
    train_end = dt.date.fromisoformat(config.DEFAULT_TRAIN_END)
    val_start = dt.date.fromisoformat(config.DEFAULT_VALIDATE_START)
    train_start = dt.date.fromisoformat(config.DEFAULT_TRAIN_START)
    val_end = dt.date.fromisoformat(config.DEFAULT_VALIDATE_END)
    # validate starts AFTER train ends (no overlap)
    assert val_start > train_end
    # train is much larger than validate (typical 80/20 or so)
    train_days = (train_end - train_start).days
    val_days = (val_end - val_start).days
    assert train_days > val_days
    # validate is at least a month
    assert val_days >= 30


def test_max_validation_regression_is_reasonable():
    assert 0.0 < config.MAX_VALIDATION_REGRESSION < 1.0
