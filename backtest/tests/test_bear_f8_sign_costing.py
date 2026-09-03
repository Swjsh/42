"""Tests for bear_f8_sign_costing.py -- BEAR-F8-VIX-FLOOR-COSTING-REPLAY sign-only costing.

Covers: no walker/option-pricing import surface, clustering, the walk-forward outcome rule
(favourable/adverse/flat + same-bar tie-break), and the session-clustered bootstrap helpers.
Does NOT re-derive the live report's numbers (that would just re-run the tool) -- these are
unit-level checks on synthetic fixtures.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backtest" / "tools"))
sys.path.insert(0, str(ROOT / "backtest"))
sys.path.insert(0, str(ROOT))

import bear_f8_sign_costing as mod  # noqa: E402


def test_no_walker_or_option_pricing_import():
    """The whole point of the SIGN-ONLY scope: this module must never IMPORT a walker or an
    option-pricing module. Only checks actual import statements -- the module's own docstring
    names the walker in prose (explaining why it's excluded), which is fine and expected."""
    src = Path(mod.__file__).read_text(encoding="utf-8")
    import_lines = [ln for ln in src.splitlines() if ln.strip().startswith(("import ", "from "))]
    banned = ("exit_manager_walk", "simulate_trade_real", "option_pricing_real",
              "walk_exit_manager", "cap_admission")
    for ln in import_lines:
        for token in banned:
            assert token not in ln, f"forbidden walker/option-pricing import: {ln!r}"


def test_cluster_events_folds_within_gap_and_splits_beyond():
    rows = [
        {"ts_et": "2026-08-05T09:46:00", "spy": 765.8},
        {"ts_et": "2026-08-05T09:50:00", "spy": 765.7},   # 4 min later -> same cluster
        {"ts_et": "2026-08-05T10:10:00", "spy": 765.5},   # 20 min later -> new cluster
    ]
    events = mod.cluster_events(rows, gap_minutes=15)
    assert len(events) == 2
    assert events[0]["ts_et"] == "2026-08-05T09:46:00"
    assert events[1]["ts_et"] == "2026-08-05T10:10:00"


def test_build_population_r_sole_blocker_only_and_pools_accounts():
    rows = [
        # sole-blocker-8, safe -- should count
        {"ts_et": "2026-08-05T09:46:00", "account": "safe", "armed": True, "verdict": "HOLD",
         "bear_blockers": [8], "spy": 765.8, "vix": 15.2},
        # sole-blocker-8, bold, same moment -- pools into the SAME episode as the safe tick above
        {"ts_et": "2026-08-05T09:46:02", "account": "bold", "armed": True, "verdict": "HOLD",
         "bear_blockers": [8], "spy": 765.8, "vix": 15.2},
        # multi-blocker cascade row -- must be excluded (C15)
        {"ts_et": "2026-08-05T09:46:05", "account": "safe", "armed": True, "verdict": "HOLD",
         "bear_blockers": [5, 8], "spy": 765.8, "vix": 15.2},
        # not armed -- excluded
        {"ts_et": "2026-08-05T09:47:00", "account": "safe", "armed": False, "verdict": "HOLD",
         "bear_blockers": [8], "spy": 765.8, "vix": 15.2},
        # outside window -- excluded
        {"ts_et": "2026-07-01T09:46:00", "account": "safe", "armed": True, "verdict": "HOLD",
         "bear_blockers": [8], "spy": 765.8, "vix": 15.2},
    ]
    pop_r = mod.build_population_r(rows)
    assert len(pop_r) == 1
    assert pop_r[0]["ts_et"] == "2026-08-05T09:46:00"
    assert pop_r[0]["entry_price"] == 765.8


def _mk_bars(rows):
    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["ts"])
    return df


def test_walk_outcome_favourable_when_price_falls_first():
    bars = _mk_bars([
        {"ts": "2026-08-05T09:45:00", "open": 766.0, "high": 766.1, "low": 765.9, "close": 766.0},
        {"ts": "2026-08-05T09:50:00", "open": 766.0, "high": 766.2, "low": 765.0, "close": 765.1},  # touches fav
    ])
    outcome = mod.walk_outcome(bars, dt.datetime(2026, 8, 5, 9, 45), 766.0,
                                median_hold=10, fav_price=765.2, adv_price=767.0)
    assert outcome == "FAVOURABLE"


def test_walk_outcome_adverse_when_price_rises_first():
    bars = _mk_bars([
        {"ts": "2026-08-05T09:45:00", "open": 766.0, "high": 766.1, "low": 765.9, "close": 766.0},
        {"ts": "2026-08-05T09:50:00", "open": 766.0, "high": 767.5, "low": 765.9, "close": 767.4},  # touches adv
    ])
    outcome = mod.walk_outcome(bars, dt.datetime(2026, 8, 5, 9, 45), 766.0,
                                median_hold=10, fav_price=765.2, adv_price=767.0)
    assert outcome == "ADVERSE"


def test_walk_outcome_same_bar_tiebreak_is_adverse():
    """Pre-registered rule: a single bar touching BOTH thresholds resolves ADVERSE, since 5-min
    bars can't show which came first intrabar and the tie-break must not favour Population R."""
    bars = _mk_bars([
        {"ts": "2026-08-05T09:45:00", "open": 766.0, "high": 767.5, "low": 765.0, "close": 766.0},
    ])
    outcome = mod.walk_outcome(bars, dt.datetime(2026, 8, 5, 9, 45), 766.0,
                                median_hold=10, fav_price=765.2, adv_price=767.0)
    assert outcome == "ADVERSE"


def test_walk_outcome_flat_when_neither_touched():
    bars = _mk_bars([
        {"ts": "2026-08-05T09:45:00", "open": 766.0, "high": 766.1, "low": 765.9, "close": 766.0},
    ])
    outcome = mod.walk_outcome(bars, dt.datetime(2026, 8, 5, 9, 45), 766.0,
                                median_hold=10, fav_price=765.2, adv_price=767.0)
    assert outcome == "FLAT"


def test_session_clustered_bootstrap_ci_deterministic_with_seed():
    entries = [
        {"ts_et": "2026-08-05T09:45:00", "outcome": "FAVOURABLE"},
        {"ts_et": "2026-08-05T10:00:00", "outcome": "ADVERSE"},
        {"ts_et": "2026-08-06T09:45:00", "outcome": "FAVOURABLE"},
        {"ts_et": "2026-08-06T10:00:00", "outcome": "FAVOURABLE"},
    ]
    p1, lo1, hi1 = mod.session_clustered_bootstrap_ci(entries, "outcome", "FAVOURABLE", seed=1337, n_boot=200)
    p2, lo2, hi2 = mod.session_clustered_bootstrap_ci(entries, "outcome", "FAVOURABLE", seed=1337, n_boot=200)
    assert p1 == pytest.approx(0.75)
    assert (lo1, hi1) == (lo2, hi2)   # same seed -> reproducible CI
    assert 0.0 <= lo1 <= p1 <= hi1 <= 1.0


def test_session_clustered_bootstrap_ci_empty_is_nan_safe():
    p, lo, hi = mod.session_clustered_bootstrap_ci([], "outcome", "FAVOURABLE")
    assert p != p  # nan


def test_join_enter_bear_within_tolerance_only():
    idx = {
        "safe": [
            {"ts_et": "2026-08-05T11:49:03", "spy": 771.93, "vix": 18.0, "verdict": "ENTER_BEAR"},
        ],
        "bold": [],
    }
    within = mod.join_enter_bear("safe", dt.datetime(2026, 8, 5, 11, 49, 7), idx)
    assert within is not None and within["spy"] == 771.93

    too_far = mod.join_enter_bear("safe", dt.datetime(2026, 8, 5, 11, 55, 0), idx)
    assert too_far is None

    before_entry = mod.join_enter_bear("safe", dt.datetime(2026, 8, 5, 11, 48, 0), idx)
    assert before_entry is None  # ENTER row must be AT-OR-BEFORE the trade's own entry ts
