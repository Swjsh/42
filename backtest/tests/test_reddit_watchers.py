"""Behavioral tests for the two Reddit-adopted setups: ORB-15 and ERL->IRL."""
from __future__ import annotations
import sys, types, datetime as dt
from pathlib import Path
import pandas as pd
import pytest
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.watchers.orb15_watcher import detect_orb15_break, compute_opening_range_15, _orb15_state
from lib.watchers.erl_irl_watcher import detect_erl_irl, detect_erl_irl_setup


def _b(ts, o, h, l, c, v=80000):
    return {"timestamp_et": pd.Timestamp(ts), "open": o, "high": h, "low": l, "close": c, "volume": v}

def _day(rows):
    return pd.DataFrame([_b(*r) for r in rows])

D = "2026-06-01 "

# ---------- ORB-15 ----------

def _orday():
    return _day([
        (D+"09:30", 100.0, 100.50, 99.80, 100.20),
        (D+"09:35", 100.2, 100.40, 100.00, 100.30),
        (D+"09:40", 100.3, 100.45, 100.10, 100.40),   # OR: high 100.50 low 99.80 range 0.70
    ])

def test_or15_window_and_gate():
    orr = compute_opening_range_15(_orday())
    assert orr is not None and orr.high == 100.50 and orr.low == 99.80
    assert round(orr.range, 2) == 0.70

def test_or15_narrow_gate_rejects_wide():
    wide = _day([(D+"09:30",100,102.0,99.0,101.0),(D+"09:35",101,102.0,100.5,101.5),(D+"09:40",101.5,102.0,100.5,101.0)])
    assert compute_opening_range_15(wide) is None  # range 3.0 >= 1.50

def test_orb15_break_mode_fires_on_breakout():
    _orb15_state.clear()
    df = _orday()
    brk = _b(D+"09:45", 100.40, 101.00, 100.35, 100.90)   # green close > ORH 100.50
    full = pd.concat([df, pd.DataFrame([brk])], ignore_index=True)
    sig = detect_orb15_break(pd.Series(brk), full, 3, 50000, entry_mode="break")
    assert sig is not None and sig.setup_name == "ORB15_LONG" and sig.direction == "long"
    assert sig.metadata["entry_mode"] == "break" and sig.metadata["or_window_minutes"] == 15

def test_orb15_retest_mode_waits_then_fires():
    _orb15_state.clear()
    df = _orday()
    brk = _b(D+"09:45", 100.40, 101.00, 100.35, 100.90)
    full = pd.concat([df, pd.DataFrame([brk])], ignore_index=True)
    # breakout bar: retest mode should WAIT (None)
    assert detect_orb15_break(pd.Series(brk), full, 3, 50000, entry_mode="retest") is None
    rt = _b(D+"09:50", 100.60, 100.95, 100.55, 100.90)    # pullback to ORH zone, green, close>=ORH
    full2 = pd.concat([full, pd.DataFrame([rt])], ignore_index=True)
    sig = detect_orb15_break(pd.Series(rt), full2, 4, 50000, entry_mode="retest")
    assert sig is not None and sig.metadata["entry_mode"] == "retest"

def test_orb15_no_signal_without_breakout():
    _orb15_state.clear()
    df = _orday()
    flat = _b(D+"09:45", 100.30, 100.45, 100.20, 100.35)  # stays inside OR
    full = pd.concat([df, pd.DataFrame([flat])], ignore_index=True)
    assert detect_orb15_break(pd.Series(flat), full, 3, 50000, entry_mode="break") is None


# ---------- ERL -> IRL ----------

def _erl_seq():
    # idx: 0 base, 1 sweep-below-99.50-reclaim, 2 base, 3 displacement, 4 FVG-complete, 5 retrace-entry
    return _day([
        (D+"10:00", 100.00, 100.20, 99.95, 100.10),
        (D+"10:05", 100.10, 100.15, 99.30, 100.05),   # ERL sweep of support 99.50 (low 99.30) + reclaim
        (D+"10:10", 100.05, 100.30, 100.00, 100.25),  # c_first for FVG@4 (high 100.30)
        (D+"10:15", 100.25, 100.95, 100.25, 100.90),  # displacement up
        (D+"10:20", 100.90, 101.10, 100.55, 101.00),  # FVG completes: low 100.55 > high[2] 100.30
        (D+"10:25", 100.45, 100.80, 100.40, 100.70),  # retrace into gap [100.30,100.55] + green hold
    ])

def test_erl_irl_fires_long():
    res = detect_erl_irl(_erl_seq(), bar_idx=5, levels_active=[99.50], vix_now=19.0)
    assert res is not None and res["direction"] == "long"
    assert res["swept_extreme"] == pytest.approx(99.30)
    assert res["stop"] == pytest.approx(99.20)        # swept low - 0.10 buffer
    assert res["entry"] == pytest.approx(100.70)
    assert res["fvg"].gap_bottom == pytest.approx(100.30)

def test_erl_irl_none_without_sweep():
    seq = _erl_seq()
    seq.loc[1, "low"] = 99.60   # no longer pierces support 99.50
    assert detect_erl_irl(seq, bar_idx=5, levels_active=[99.50], vix_now=19.0) is None

def test_erl_irl_none_without_fvg():
    seq = _erl_seq()
    # flatten the displacement so no gap forms
    seq.loc[3, ["open","high","low","close"]] = [100.05, 100.20, 100.00, 100.10]
    seq.loc[4, ["open","high","low","close"]] = [100.10, 100.25, 100.05, 100.20]
    assert detect_erl_irl(seq, bar_idx=5, levels_active=[99.50], vix_now=19.0) is None

def test_erl_irl_setup_wrapper_builds_signal():
    ctx = types.SimpleNamespace(
        bar_idx=5, timestamp_et=pd.Timestamp(D+"10:25"),
        prior_bars=_erl_seq(), levels_active=[99.50, 102.0], vix_now=19.0, htf_15m_stack="BULL",
    )
    sig = detect_erl_irl_setup(ctx)
    assert sig is not None and sig.setup_name == "ERL_IRL_SWEEP_FVG"
    assert sig.watcher_name == "erl_irl_watcher" and sig.direction == "long"
    assert sig.metadata["premium_stop_pct"] == -0.99 and sig.metadata["strike_offset"] == -2
    assert sig.tp1_price == pytest.approx(102.0)   # next external level above entry

def test_erl_irl_setup_time_gated():
    ctx = types.SimpleNamespace(
        bar_idx=5, timestamp_et=pd.Timestamp(D+"09:30"),   # before 09:45 gate
        prior_bars=_erl_seq(), levels_active=[99.50], vix_now=19.0, htf_15m_stack=None,
    )
    assert detect_erl_irl_setup(ctx) is None
