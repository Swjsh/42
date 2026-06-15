"""Smoke test for the 4 new watchers added 2026-05-13.

Per OP 21 these all start WATCH-ONLY. The smoke test only verifies:
  1. Each watcher module imports cleanly
  2. The detect_*_setup() entry point is callable
  3. Calling with `None` / empty inputs returns `None` (no crash)
  4. `WatcherSignal` schema is exported and instantiable

Actual bar-processing correctness is the heartbeat's responsibility
during live observation + the watcher_grader's responsibility during
backfill replay.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


def test_watcher_signal_dataclass_importable():
    """WatcherSignal schema is exported and instantiable."""
    from lib.watchers import WatcherSignal

    sig = WatcherSignal(
        watcher_name="x",
        setup_name="X",
        direction="long",
        entry_price=1.0,
        stop_price=0.9,
        tp1_price=1.1,
        runner_price=1.2,
        confidence="medium",
        reason="smoke",
    )
    assert sig.watcher_name == "x"
    assert sig.metadata == {}
    assert sig.triggers_fired == []


def test_sniper_watcher_imports_and_returns_none_on_empty():
    """sniper_watcher: import + None-input safety."""
    from lib.watchers.sniper_watcher import detect_sniper_setup

    # Empty DataFrame -> None
    empty = pd.DataFrame(columns=["timestamp_et", "open", "high", "low", "close", "volume"])
    assert detect_sniper_setup(bar=None, bar_idx=0, spy_bars=empty) is None
    # Bar with no timestamp_et -> None
    bar_no_ts = pd.Series({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 0})
    assert detect_sniper_setup(bar=bar_no_ts, bar_idx=0, spy_bars=empty) is None


def test_vwap_watcher_imports_and_returns_none_on_empty():
    """vwap_watcher: import + None-input safety."""
    from lib.watchers.vwap_watcher import detect_vwap_setup

    empty = pd.DataFrame(columns=["timestamp_et", "open", "high", "low", "close", "volume"])
    assert detect_vwap_setup(bar=None, bar_idx=0, spy_bars=empty, ribbon_state=None) is None
    bar_no_ts = pd.Series({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 0})
    assert detect_vwap_setup(bar=bar_no_ts, bar_idx=0, spy_bars=empty, ribbon_state=None) is None


def test_opening_drive_fade_watcher_imports_and_returns_none_on_empty():
    """opening_drive_fade_watcher: import + None-input safety + state reset hooks."""
    from lib.watchers.opening_drive_fade_watcher import (
        detect_opening_drive_fade_setup,
        reset_state,
        reset_all_state,
    )

    empty = pd.DataFrame(columns=["timestamp_et", "open", "high", "low", "close", "volume"])
    assert detect_opening_drive_fade_setup(bar=None, bar_idx=0, spy_bars=empty) is None
    bar_no_ts = pd.Series({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 0})
    assert detect_opening_drive_fade_setup(bar=bar_no_ts, bar_idx=0, spy_bars=empty) is None

    # State-reset helpers don't crash
    reset_state("2026-05-13")
    reset_all_state()


def test_v14_enhanced_watcher_imports_and_returns_none_on_empty():
    """v14_enhanced_watcher: import + None-input safety."""
    from lib.watchers.v14_enhanced_watcher import detect_v14_enhanced_setup

    assert detect_v14_enhanced_setup(None) is None


def test_all_four_exported_from_package():
    """All 4 new detect functions are importable from `lib.watchers`."""
    from lib.watchers import (
        detect_sniper_setup,
        detect_vwap_setup,
        detect_opening_drive_fade_setup,
        detect_v14_enhanced_setup,
    )

    assert callable(detect_sniper_setup)
    assert callable(detect_vwap_setup)
    assert callable(detect_opening_drive_fade_setup)
    assert callable(detect_v14_enhanced_setup)


def test_default_knob_constants_match_sniper_v1_winner_combo():
    """Sniper watcher defaults must equal sniper-v1.json#winner_combo."""
    import json
    from lib.watchers import sniper_watcher

    scorecard_path = REPO.parent / "analysis" / "recommendations" / "sniper-v1.json"
    if not scorecard_path.exists():
        # Don't fail if the scorecard hasn't been generated yet; smoke only.
        return
    sc = json.loads(scorecard_path.read_text())
    wc = sc["winner_combo"]
    assert sniper_watcher.DEFAULT_VOL_MULT == wc["vol_mult"]
    assert sniper_watcher.DEFAULT_BODY_MIN_CENTS == wc["body_min_cents"]
    assert sniper_watcher.DEFAULT_MIN_STARS == wc["min_stars"]
    assert sniper_watcher.DEFAULT_PROXIMITY_DOLLARS == wc["proximity_dollars"]
    assert sniper_watcher.DEFAULT_STRIKE_OFFSET == wc["strike_offset"]
    assert sniper_watcher.DEFAULT_PREMIUM_STOP_PCT == wc["premium_stop_pct"]
    assert sniper_watcher.DEFAULT_TP1_PREMIUM_PCT == wc["tp1_premium_pct"]
    assert sniper_watcher.DEFAULT_RUNNER_TARGET_PCT == wc["runner_target_pct"]
    assert sniper_watcher.DEFAULT_TP1_QTY_FRACTION == wc["tp1_qty_fraction"]
    assert sniper_watcher.DEFAULT_QTY == wc["qty"]
    assert sniper_watcher.DEFAULT_PROFIT_LOCK_THRESHOLD_PCT == wc["profit_lock_threshold_pct"]
    assert sniper_watcher.DEFAULT_PROFIT_LOCK_STOP_OFFSET_PCT == wc["profit_lock_stop_offset_pct"]
