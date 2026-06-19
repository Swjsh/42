"""Smoke test for the watchers added 2026-05-13.

Per OP 21 these all start WATCH-ONLY. The smoke test only verifies:
  1. Each watcher module imports cleanly
  2. The detect_*_setup() entry point is callable
  3. Calling with `None` / empty inputs returns `None` (no crash)
  4. `WatcherSignal` schema is exported and instantiable

Actual bar-processing correctness is the heartbeat's responsibility
during live observation + the watcher_grader's responsibility during
backfill replay.

NOTE 2026-06-18: SNIPER was retired (watcher-fleet de-sprawl) — its smoke
cases were removed here when sniper_watcher.py was deleted. The standalone
lib/sniper_detector.py stays in tree (offline diag) but no longer has a
watcher wrapper. VWAP / ODF / v14_enhanced remain.
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


def test_surviving_new_detects_exported_from_package():
    """The surviving new detect functions are importable from `lib.watchers`.

    SNIPER was retired 2026-06-18 (sniper_watcher.py deleted), so it is no longer
    in this list — the registry reconciliation test (test_watcher_registry.py) now
    owns the "every watcher is wired" invariant.
    """
    from lib.watchers import (
        detect_vwap_setup,
        detect_opening_drive_fade_setup,
        detect_v14_enhanced_setup,
    )

    assert callable(detect_vwap_setup)
    assert callable(detect_opening_drive_fade_setup)
    assert callable(detect_v14_enhanced_setup)
