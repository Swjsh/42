"""Guards for the TRUE multi-day-hold 3-4 DTE sim (chef 2026-07-07 offline R&D).

Locks the load-bearing claims that separate this from the prior intraday-resolved
DTE test — a future refactor must not silently regress them:

  1. The NEW 3/4-DTE cache is genuinely MULTI-DAY: a fetched contract file holds
     real option bars on MORE THAN ONE trading day (the flaw the prior cache had).
  2. The sim's terminal exit uses a REAL option bar, not synthetic intrinsic
     (a held-to-expiry trade prices from the last fetched close, not max(0,K-S)).
  3. A wider stop actually lets positions HELD OVERNIGHT exist (held_overnight True
     is reachable) — otherwise the "multi-day hold" claim is vacuous.
  4. GAP-THROUGH detection: a synthetic day-2 opening bar below the stop exits
     GAP_STOP at the gapped open (worse than the stop level), and the loss is
     booked into gap_loss_dollar.
  5. No look-ahead: entry is the NEXT bar after the trigger; management reads only
     bars at-or-after entry.

These use SYNTHETIC OptionBar frames for the deterministic mechanics (2,3,4,5) and
the REAL cache only for (1) — so the suite passes regardless of which contracts the
backfill managed to fetch (gated on >=1 multi-day file existing).

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_dte34_multiday_hold.py -q
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import pytest

_BT = Path(__file__).resolve().parents[1]
_REPO = _BT.parent
for p in (str(_BT), str(_REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

from autoresearch import _dte34_multiday_hold_sim as M
from autoresearch._dte_expansion_sim import Signal


def _synthetic_opt(rows):
    """rows: list of (ts_iso, open, high, low, close). Returns a cache-shaped frame."""
    df = pd.DataFrame([
        {"timestamp_et": ts, "open": o, "high": h, "low": lo, "close": c,
         "volume": 100, "vwap": c, "trade_count": 10}
        for (ts, o, h, lo, c) in rows
    ])
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"])
    return df


def _spy_frame(rows):
    df = pd.DataFrame([
        {"timestamp_et": ts, "close": c} for (ts, c) in rows
    ])
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"])
    return df


# ── 1. the cache is genuinely multi-day (real data, gated on backfill presence) ──
def test_cache_is_genuinely_multiday():
    files3 = sorted(M.DIR_MULTIDAY[3].glob("*.csv"))
    if not files3:
        pytest.skip("3DTE backfill not present yet")
    # find at least one file spanning >=2 distinct trading days
    spanning = 0
    for f in files3[:40]:
        df = pd.read_csv(f, usecols=["timestamp_et"])
        days = pd.to_datetime(df["timestamp_et"]).dt.date.nunique()
        if days >= 2:
            spanning += 1
    assert spanning > 0, "expected at least one 3DTE contract spanning multiple days"


# ── 2. terminal exit uses a REAL option bar, not synthetic intrinsic ──
def test_terminal_exit_is_real_option_close(monkeypatch):
    # single-day-2 contract; price rises modestly (never hits a wide target/stop) so it
    # rides to the LAST real close (2.10), not any intrinsic value.
    opt = _synthetic_opt([
        ("2025-03-03T09:35:00", 2.00, 2.05, 1.98, 2.02),
        ("2025-03-03T09:40:00", 2.02, 2.08, 2.00, 2.05),
        ("2025-03-04T09:35:00", 2.06, 2.12, 2.04, 2.08),
        ("2025-03-04T15:55:00", 2.08, 2.12, 2.06, 2.10),   # final real bar
    ])
    monkeypatch.setitem(M._MD_CACHE, (3, "SPYTEST"), opt)
    monkeypatch.setattr(M, "option_symbol", lambda e, s, side: "SPYTEST")
    spy = _spy_frame([("2025-03-03T09:30:00", 580.0), ("2025-03-03T09:35:00", 580.0)])
    sg = Signal(bar_idx=0, side="P", stop_level=999.0, note="t")
    f = M.simulate_multiday_hold(sg, spy, 3, strike=585, expiry=dt.date(2025, 3, 4),
                                 side="P", premium_stop_pct=-0.99, target_pct=5.0,
                                 use_chart_stop=False)
    assert f is not None
    assert f.exit_reason == "EXPIRY_CLOSE"
    # exit = last close(2.10) - exit slip(0.02) = 2.08, NOT an intrinsic 585-S value
    assert abs(f.exit_premium - 2.08) < 1e-6, f.exit_premium
    assert f.held_overnight is True


# ── 3. held_overnight is reachable with a wide stop ──
def test_held_overnight_reachable(monkeypatch):
    opt = _synthetic_opt([
        ("2025-03-03T09:35:00", 2.00, 2.02, 1.95, 1.98),
        ("2025-03-04T09:35:00", 1.97, 2.00, 1.90, 1.95),   # survives into day 2
    ])
    monkeypatch.setitem(M._MD_CACHE, (3, "SPYTEST"), opt)
    monkeypatch.setattr(M, "option_symbol", lambda e, s, side: "SPYTEST")
    spy = _spy_frame([("2025-03-03T09:30:00", 580.0), ("2025-03-03T09:35:00", 580.0)])
    sg = Signal(bar_idx=0, side="P", stop_level=999.0, note="t")
    f = M.simulate_multiday_hold(sg, spy, 3, strike=585, expiry=dt.date(2025, 3, 4),
                                 side="P", premium_stop_pct=-0.50, target_pct=5.0,
                                 use_chart_stop=False)
    assert f is not None and f.held_overnight is True
    assert f.n_days_held >= 2


# ── 4. gap-through-stop: day-2 open below stop exits GAP_STOP + books gap_loss ──
def test_gap_through_stop(monkeypatch):
    # entry ~2.00, stop -20% => 1.60. Day 1 never touches it. Day 2 GAPS OPEN to 1.20
    # (below 1.60) -> GAP_STOP fill at 1.20-slip, worse than the 1.60 stop.
    opt = _synthetic_opt([
        ("2025-03-03T09:35:00", 2.00, 2.05, 1.70, 1.75),   # day1 low 1.70 > stop 1.60
        ("2025-03-04T09:35:00", 1.20, 1.25, 1.10, 1.15),   # day2 GAP open 1.20 < stop
    ])
    monkeypatch.setitem(M._MD_CACHE, (3, "SPYTEST"), opt)
    monkeypatch.setattr(M, "option_symbol", lambda e, s, side: "SPYTEST")
    spy = _spy_frame([("2025-03-03T09:30:00", 580.0), ("2025-03-03T09:35:00", 580.0)])
    sg = Signal(bar_idx=0, side="P", stop_level=999.0, note="t")
    f = M.simulate_multiday_hold(sg, spy, 3, strike=585, expiry=dt.date(2025, 3, 4),
                                 side="P", premium_stop_pct=-0.20, target_pct=5.0,
                                 use_chart_stop=False)
    assert f is not None
    assert f.exit_reason == "GAP_STOP"
    assert abs(f.exit_premium - (1.20 - M.DEFAULT_EXIT_SLIPPAGE)) < 1e-6, f.exit_premium
    assert f.gap_loss_dollar < 0.0  # adverse gap booked


# ── 5. no look-ahead: entry is the NEXT bar after the trigger ──
def test_entry_is_next_bar_no_lookahead(monkeypatch):
    opt = _synthetic_opt([
        ("2025-03-03T09:35:00", 9.99, 9.99, 9.99, 9.99),   # trigger-bar-time (must NOT be entry)
        ("2025-03-03T09:40:00", 2.00, 2.10, 1.95, 2.05),   # NEXT bar = real entry
        ("2025-03-03T15:55:00", 2.05, 2.60, 2.00, 2.55),   # target 2.00*1.25=2.50 hit here
    ])
    monkeypatch.setitem(M._MD_CACHE, (3, "SPYTEST"), opt)
    monkeypatch.setattr(M, "option_symbol", lambda e, s, side: "SPYTEST")
    # trigger bar at 09:35; entry must be the 09:40 open (2.00), not 9.99.
    spy = _spy_frame([("2025-03-03T09:35:00", 580.0)])
    sg = Signal(bar_idx=0, side="P", stop_level=999.0, note="t")
    f = M.simulate_multiday_hold(sg, spy, 3, strike=585, expiry=dt.date(2025, 3, 3),
                                 side="P", premium_stop_pct=-0.99, target_pct=0.25,
                                 use_chart_stop=False)
    assert f is not None
    assert abs(f.entry_premium - (2.00 + M.DEFAULT_ENTRY_SLIPPAGE)) < 1e-6, f.entry_premium
    assert f.exit_reason == "TARGET"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
