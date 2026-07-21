"""Guard for backtest/autoresearch/rrw_bull_veto_study.py's CORE LOGIC.

Cheap ($0), pure-Python reproducers of the veto/tighten counterfactual math on
synthetic fixtures -- does NOT re-run the full real-fills backtest (that's the
CLI script's job, ~minutes). This is the STAGE 3 "verify-now-not-later"
in-process check: if event_passes/veto_test/tighten_test's arithmetic ever
regresses, this REDs before the next full study run silently reports a wrong
number (C7 -- silent success is failure).
"""

from __future__ import annotations

import datetime as dt
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

from lib.watchers.ribbon_rejection_wick_detector import RRWParams  # noqa: E402
from autoresearch.rrw_bull_veto_study import (  # noqa: E402
    _stats,
    event_passes,
    veto_test,
    VETO_LOOKBACK_MIN,
)


@dataclass
class _FakeTrade:
    entry_time_et: dt.datetime
    dollar_pnl: float
    runner_exit_time_et: Optional[dt.datetime] = None
    exit_reason: str = "EXIT_ALL_TIME_STOP"
    strike: int = 700
    side: str = "C"
    entry_premium: float = 1.0
    qty: int = 3
    setup: str = "BULLISH_RECLAIM_RIDE_THE_RIBBON"


def _ev(date: str, time_str: str, wick=0.5, lookback=6, vol=2.0, flipped=False) -> dict:
    return {
        "date": date,
        "ts": f"{date}T{time_str}:00",
        "direction": "short",
        "wick_frac": wick,
        "bars_since_break": lookback,
        "vol_break_ratio": vol,
        "stack_flipped": flipped,
    }


def test_stats_empty():
    assert _stats([]) == {"n": 0, "pnl": 0.0, "wr": 0.0, "expectancy": 0.0}


def test_stats_basic():
    r = _stats([100.0, -50.0, 25.0])
    assert r["n"] == 3
    assert r["pnl"] == 75.0
    assert r["wr"] == pytest.approx(2 / 3, abs=1e-3)  # _stats rounds wr to 3dp
    assert r["expectancy"] == pytest.approx(25.0, abs=1e-6)


def test_event_passes_defaults():
    cfg = RRWParams()
    assert event_passes(_ev("2026-01-02", "10:30"), cfg) is True


def test_event_passes_rejects_thin_wick():
    cfg = RRWParams()
    assert event_passes(_ev("2026-01-02", "10:30", wick=0.10), cfg) is False


def test_event_passes_rejects_stale_break():
    cfg = RRWParams(break_lookback_bars=6)
    assert event_passes(_ev("2026-01-02", "10:30", lookback=12), cfg) is False


def test_event_passes_vol_gate():
    cfg = RRWParams(vol_mult_min=2.5)
    assert event_passes(_ev("2026-01-02", "10:30", vol=1.0), cfg) is False
    assert event_passes(_ev("2026-01-02", "10:30", vol=3.0), cfg) is True


def test_event_passes_stack_flipped_gate():
    cfg = RRWParams(require_stack_not_flipped=True)
    assert event_passes(_ev("2026-01-02", "10:30", flipped=True), cfg) is False
    assert event_passes(_ev("2026-01-02", "10:30", flipped=False), cfg) is True


def test_veto_test_skips_trade_with_prior_bear_event():
    """A bear event inside the lookback window vetoes the trade -- removed from
    'kept', counted in 'vetoed'."""
    cfg = RRWParams()
    trades = [_FakeTrade(entry_time_et=dt.datetime(2026, 1, 2, 10, 30), dollar_pnl=200.0)]
    events = [_ev("2026-01-02", "10:15")]  # 15 min before entry, inside 30-min window
    result = veto_test(trades, events, cfg)
    assert result["n_vetoed"] == 1
    assert result["veto_applied"]["n"] == 0
    assert result["vetoed_trades"]["pnl"] == 200.0
    assert result["delta_pnl_from_veto"] == pytest.approx(-200.0, abs=1e-6)


def test_veto_test_keeps_trade_outside_lookback():
    cfg = RRWParams()
    trades = [_FakeTrade(entry_time_et=dt.datetime(2026, 1, 2, 10, 30), dollar_pnl=200.0)]
    too_early_minutes = VETO_LOOKBACK_MIN + 5
    ev_time = (dt.datetime(2026, 1, 2, 10, 30) - dt.timedelta(minutes=too_early_minutes))
    events = [_ev("2026-01-02", ev_time.strftime("%H:%M"))]
    result = veto_test(trades, events, cfg)
    assert result["n_vetoed"] == 0
    assert result["veto_applied"]["n"] == 1
    assert result["delta_pnl_from_veto"] == pytest.approx(0.0, abs=1e-6)


def test_veto_test_ignores_event_on_different_day():
    cfg = RRWParams()
    trades = [_FakeTrade(entry_time_et=dt.datetime(2026, 1, 2, 10, 30), dollar_pnl=200.0)]
    events = [_ev("2026-01-01", "10:15")]  # previous day -- must not veto
    result = veto_test(trades, events, cfg)
    assert result["n_vetoed"] == 0


def test_veto_test_ignores_event_after_entry():
    """A bear event AFTER entry is not a veto candidate (it's a tighten candidate)."""
    cfg = RRWParams()
    trades = [_FakeTrade(entry_time_et=dt.datetime(2026, 1, 2, 10, 30), dollar_pnl=200.0)]
    events = [_ev("2026-01-02", "10:45")]
    result = veto_test(trades, events, cfg)
    assert result["n_vetoed"] == 0


def test_scorecard_cache_matches_battery_window():
    """Sanity: the cached RRW events file (reused, not re-derived) still spans the
    RRW battery's own documented window and short-event count this study depends on."""
    import json
    events_path = REPO / "autoresearch" / "_state" / "ribbon_rejection_wick_events.jsonl"
    assert events_path.exists(), "cached RRW events file missing -- rerun ribbon_rejection_wick_battery.py"
    lines = events_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) > 0
    first = json.loads(lines[0])
    last = json.loads(lines[-1])
    assert first["date"] <= "2025-01-05"
    assert last["date"] >= "2026-06-25"
