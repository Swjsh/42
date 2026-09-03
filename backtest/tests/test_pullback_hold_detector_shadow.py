"""Tests for backtest/lib/pullback_hold_detector.py (PULLBACK-HOLD-BULL-TRIGGER, Lane A/B
forward-shadow build, queue item filed 2026-07-22, re-opened 2026-09-03). SHADOW-ONLY module --
these tests exercise the standalone detector directly; they do not touch the frozen
`filters.py` shadow-logged sibling or any live/backtest engine path.

Also covers `setup/scripts/pullback_hold_shadow.py`'s ledger-rewrite idempotency (the
day_throttle_shadow.py precedent: a full deterministic recompute from the same underlying data
must reproduce byte-identical output, not accumulate duplicates on re-run).
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))

from lib.pullback_hold_detector import (  # noqa: E402
    PULLBACK_LOOKBACK_BARS,
    PULLBACK_MIN_HOLD_BARS,
    PULLBACK_ZONE_BAND_DOLLARS_DEFAULT,
    PullbackHoldFire,
    detect_pullback_hold,
    scan_session,
)


def _mk_bars(rows: list[dict]) -> pd.DataFrame:
    """rows: list of {open, high, low, close}, one per 5-min bar starting 09:30 ET."""
    start = dt.datetime(2026, 9, 3, 9, 30)
    out = []
    for i, r in enumerate(rows):
        out.append({
            "timestamp_et": start + dt.timedelta(minutes=5 * i),
            "open": r["open"], "high": r["high"], "low": r["low"], "close": r["close"],
        })
    return pd.DataFrame(out)


def _firing_scenario() -> pd.DataFrame:
    """9 bars (idx 0-8). Approach filler (0-4) away from the level; pullback low at idx 5
    (low=99.75, inside the $100.00 +/- $0.30 band); hold bars 5-7 all with low inside the band,
    highest hold close 100.00; reclaim bar 8 closes 100.50 (> zone ceiling 100.30 and > 100.00).
    K=3 (bars 5,6,7) exactly meets the frozen min_hold_bars."""
    return _mk_bars([
        {"open": 105.0, "high": 105.2, "low": 104.9, "close": 105.0},   # 0
        {"open": 104.5, "high": 104.6, "low": 104.2, "close": 104.3},   # 1
        {"open": 103.0, "high": 103.1, "low": 102.5, "close": 102.6},   # 2
        {"open": 101.0, "high": 101.2, "low": 100.6, "close": 100.7},   # 3
        {"open": 100.3, "high": 100.4, "low": 99.90, "close": 100.00},  # 4
        {"open": 100.00, "high": 100.05, "low": 99.75, "close": 99.90}, # 5 -- pullback low
        {"open": 99.90, "high": 100.00, "low": 99.80, "close": 99.95},  # 6 -- hold
        {"open": 99.95, "high": 100.05, "low": 99.85, "close": 100.00}, # 7 -- hold, highest close
        {"open": 100.00, "high": 100.60, "low": 99.95, "close": 100.50},# 8 -- reclaim
    ])


LEVEL = 100.00


def test_fires_on_valid_pullback_hold():
    bars = _firing_scenario()
    fire = detect_pullback_hold(bars, 8, [LEVEL], htf_stack="BULL")
    assert fire is not None
    assert isinstance(fire, PullbackHoldFire)
    assert fire.level == LEVEL
    assert fire.band == PULLBACK_ZONE_BAND_DOLLARS_DEFAULT
    assert fire.k_bars == 3
    assert fire.trigger_close == 100.50
    assert fire.htf_state == "BULL"


def test_does_not_fire_when_hold_broken():
    """Same geometry, but bar 6's low exits the zone floor (99.60 < 99.70) -- the hold is
    invalidated and no fire should be produced."""
    bars = _firing_scenario()
    bars.loc[6, "low"] = 99.60
    fire = detect_pullback_hold(bars, 8, [LEVEL], htf_stack="BULL")
    assert fire is None


def test_does_not_fire_when_reclaim_close_too_weak():
    """Reclaim bar closes inside the zone (never breaks the ceiling) -- must not fire."""
    bars = _firing_scenario()
    bars.loc[8, "close"] = 100.10  # below zone_hi (100.30)
    fire = detect_pullback_hold(bars, 8, [LEVEL], htf_stack="BULL")
    assert fire is None


def test_k_too_short_no_fire():
    """The firing scenario's hold window is exactly 3 bars. Requiring min_hold_bars=5 (K larger
    than what the geometry actually offers) must refuse to fire -- proves the K constant is
    load-bearing, not decorative."""
    bars = _firing_scenario()
    fire = detect_pullback_hold(bars, 8, [LEVEL], htf_stack="BULL", min_hold_bars=5)
    assert fire is None


def test_htf_bear_vetoes_an_otherwise_valid_fire():
    bars = _firing_scenario()
    fire = detect_pullback_hold(bars, 8, [LEVEL], htf_stack="BEAR")
    assert fire is None


def test_htf_unknown_passes_not_bear():
    """None/UNKNOWN HTF must NOT veto -- only an explicit BEAR stack blocks (task spec: '15-min
    HTF not BEAR', insufficient warmup is not evidence of BEAR)."""
    bars = _firing_scenario()
    fire = detect_pullback_hold(bars, 8, [LEVEL], htf_stack=None)
    assert fire is not None
    fire2 = detect_pullback_hold(bars, 8, [LEVEL], htf_stack="MIXED")
    assert fire2 is not None


def test_level_outside_lookback_window_no_fire():
    """No level within band of any bar's low in the whole approach window -> None."""
    bars = _firing_scenario()
    fire = detect_pullback_hold(bars, 8, [500.0], htf_stack="BULL")
    assert fire is None


def test_per_level_zone_width_overrides_default_band():
    """A key-levels.json-shaped dict level with its own zone_width must be honored over the
    module default -- a tighter width that would exclude the pullback low must refuse to fire."""
    bars = _firing_scenario()
    tight_level = {"price": LEVEL, "zone_width": 0.05}  # 99.75 low is $0.25 away -- outside 0.05
    fire = detect_pullback_hold(bars, 8, [tight_level], htf_stack="BULL")
    assert fire is None

    wide_level = {"price": LEVEL, "zone_width": 0.30}
    fire2 = detect_pullback_hold(bars, 8, [wide_level], htf_stack="BULL")
    assert fire2 is not None
    assert fire2.band == 0.30


def test_insufficient_bars_before_bar_idx_no_fire():
    bars = _firing_scenario()
    fire = detect_pullback_hold(bars, 2, [LEVEL], htf_stack="BULL")
    assert fire is None


def test_no_levels_no_fire():
    bars = _firing_scenario()
    fire = detect_pullback_hold(bars, 8, [], htf_stack="BULL")
    assert fire is None


def test_scan_session_finds_the_same_fire_as_direct_call():
    bars = _firing_scenario()
    fires = scan_session(bars, [LEVEL], htf_stacks=["BULL"] * len(bars))
    assert len(fires) == 1
    assert fires[0].k_bars == 3


def test_scan_session_rth_only_skips_premarket_bars():
    """A bar stamped before 09:30 ET must never be scanned as bar_idx when rth_only=True."""
    start = dt.datetime(2026, 9, 3, 8, 30)  # premarket -- bar 8 (the reclaim bar) lands at
                                             # 08:30 + 8*5min = 09:10, still before RTH_SCAN_START
    rows = []
    scenario = _firing_scenario()
    for i in range(len(scenario)):
        rows.append({
            "timestamp_et": start + dt.timedelta(minutes=5 * i),
            "open": scenario.iloc[i]["open"], "high": scenario.iloc[i]["high"],
            "low": scenario.iloc[i]["low"], "close": scenario.iloc[i]["close"],
        })
    premarket_bars = pd.DataFrame(rows)
    fires = scan_session(premarket_bars, [LEVEL], htf_stacks=["BULL"] * len(premarket_bars),
                          rth_only=True)
    assert fires == []


def test_frozen_constants_match_task_spec():
    """Pins the frozen constants named in the queue item / pre-reg so a silent drift is caught."""
    assert PULLBACK_MIN_HOLD_BARS == 3
    assert PULLBACK_ZONE_BAND_DOLLARS_DEFAULT == 0.30
    assert PULLBACK_LOOKBACK_BARS == 12


# -- Ledger idempotency (setup/scripts/pullback_hold_shadow.py) -------------------------------

def test_shadow_ledger_rewrite_is_idempotent(tmp_path, monkeypatch):
    """Running the full ledger-rewrite pipeline twice against IDENTICAL underlying tick data
    must produce byte-identical ledger + summary output -- the day_throttle_shadow.py
    idempotency contract (full deterministic recompute, not manual append-dedup)."""
    sys.path.insert(0, str(REPO / "setup" / "scripts"))
    import importlib
    pullback_hold_shadow = importlib.import_module("pullback_hold_shadow")

    fake_ticks = [
        {
            "ts_et": "2026-09-03T10:40:00", "account": "safe", "spy": 745.90,
            "levels_active": [746.00], "htf_15m": "BULL",
        },
        {
            "ts_et": "2026-09-03T10:41:00", "account": "safe", "spy": 745.85,
            "levels_active": [746.00], "htf_15m": "BULL",
        },
        {
            "ts_et": "2026-09-03T10:46:00", "account": "safe", "spy": 745.80,
            "levels_active": [746.00], "htf_15m": "BULL",
        },
        {
            "ts_et": "2026-09-03T10:51:00", "account": "safe", "spy": 745.85,
            "levels_active": [746.00], "htf_15m": "BULL",
        },
        {
            "ts_et": "2026-09-03T10:56:00", "account": "safe", "spy": 745.90,
            "levels_active": [746.00], "htf_15m": "BULL",
        },
        {
            "ts_et": "2026-09-03T11:01:00", "account": "safe", "spy": 746.60,
            "levels_active": [746.00], "htf_15m": "BULL",
        },
    ]

    monkeypatch.setattr(pullback_hold_shadow, "_load_ticks", lambda: fake_ticks)

    ledger_path = tmp_path / "ledger.jsonl"
    summary_path = tmp_path / "summary.json"
    monkeypatch.setattr(pullback_hold_shadow, "LEDGER", ledger_path)
    monkeypatch.setattr(pullback_hold_shadow, "SUMMARY", summary_path)
    monkeypatch.setattr(pullback_hold_shadow, "PREREG",
                         REPO / "analysis" / "recommendations"
                         / "prereg-pullback-hold-bull-trigger-2026-09-03.md")

    rc1 = pullback_hold_shadow.main([])
    assert rc1 == 0
    first_ledger = ledger_path.read_text(encoding="utf-8")
    first_summary = json.loads(summary_path.read_text(encoding="utf-8"))
    del first_summary["_meta"]["generated_at_et"]  # only genuinely time-varying field

    rc2 = pullback_hold_shadow.main([])
    assert rc2 == 0
    second_ledger = ledger_path.read_text(encoding="utf-8")
    second_summary = json.loads(summary_path.read_text(encoding="utf-8"))
    del second_summary["_meta"]["generated_at_et"]

    assert first_ledger == second_ledger
    assert first_summary == second_summary

    # And it must not simply grow unbounded -- rewriting from the same input yields the same
    # row count, not 2x.
    n_lines_1 = len([l for l in first_ledger.splitlines() if l.strip()])
    n_lines_2 = len([l for l in second_ledger.splitlines() if l.strip()])
    assert n_lines_1 == n_lines_2
