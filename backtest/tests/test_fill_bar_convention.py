"""Fill-bar convention guard (fillbar audit 2026-07-11).

TWO bar-walk conventions coexist in this codebase, BY DESIGN, and must never drift
silently:

  * t4_exit_matrix (and everything built on its _load_bars/replay: t3, t5) INCLUDES the
    fill bar -- entry fills at bar-0's OPEN and bar-0's own H/L can stop/TP1 (live
    1-min-actuator parity: the real exit manager can act inside the first 5 minutes).
  * lib/simulator_real (the P5 / mass-grind / ship-gate fills authority) EXCLUDES it --
    exit management starts at entry_idx+1 ("min hold = one full bar").

The 2026-07-11 audit (analysis/recommendations/entry-exit-matrix-fillbar-audit-
2026-07-11.md) reproduced T5 layer (a) exactly and re-ran it with the fill bar excluded:
NO T5 verdict or STOP-B decision changed (the four market-entry candidates were
byte-identical; control's expectancy on the burned 250 is the most sensitive single
number, $22.91 -> $35.54). The ONE unsafe combination is a LIMIT fill replayed against
its own fill bar (same-bar TP1 look-behind) -- pinned in t5.replay_entry2_pair's docstring.

These tests pin both sides so any future change to either convention REDs and forces a
conscious re-audit instead of a silent semantic shift.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))
sys.path.insert(0, str(REPO / "backtest" / "tools"))
sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))

import t4_exit_matrix as t4  # noqa: E402


def _synthetic_df() -> pd.DataFrame:
    return pd.DataFrame({
        "timestamp_et": pd.to_datetime([
            "2026-07-06 09:50:00", "2026-07-06 09:55:00", "2026-07-06 10:00:00"]),
        "open": [1.10, 1.00, 0.95],
        "high": [1.20, 1.05, 1.10],
        "low": [0.70, 0.50, 0.90],
        "close": [1.00, 0.95, 1.00],
    })


def test_t4_load_bars_includes_the_fill_bar(monkeypatch):
    """bars[0] must BE the bar at entry_ts (>= mask), whose open is the entry fill.
    If this ever changes to strictly-after, every published T3/T4/T5 artifact stops being
    reproducible and the fillbar audit must be re-run -- change it consciously or not at all."""
    monkeypatch.setattr(t4, "load_contract_bars", lambda symbol: _synthetic_df())
    sig = {"entry_spot": 620.0, "side": "P", "date": "2026-07-06",
           "entry_ts": "2026-07-06T09:55:00"}
    bars = t4._load_bars(sig)
    assert bars is not None and len(bars) == 2, "expected fill bar + one later bar"
    assert bars[0][0] == dt.time(9, 55), "bars[0] must be the fill bar itself (>= entry_ts)"
    assert bars[0][1] == pytest.approx(1.00), "entry premium convention = fill bar's OPEN"


def test_t4_replay_bar0_stop_semantics_vs_fill_bar_excluded():
    """Pins the as-run convention (bar-0's low CAN fire the premium stop) AND demonstrates
    the exact delta the audit measured: the same trade, fill bar excluded, never stops.
    Both behaviors are intentional; this test is the tripwire on either changing."""
    shape = {"premium_stop_pct": -0.20, "tp1_premium_pct": 1.5, "tp1_qty_fraction": 0.8,
             "profit_lock_mode": "fixed", "trail_pct": 0.0, "runner_target_pct": 2.5}
    bars = [(dt.time(9, 55), 1.00, 1.05, 0.50, 0.95),   # fill bar: low breaches -20%
            (dt.time(10, 0), 0.95, 1.10, 0.90, 1.00)]   # later bars never breach
    asrun = t4.replay(1.00, bars, "P", shape, dt.time(15, 40))
    assert asrun["stopped"] is True
    assert asrun["pnl"] == pytest.approx(-0.20 * t4.QTY * 100.0)  # filled AT the stop level

    fixed = t4.replay(1.00, bars[1:], "P", shape, dt.time(15, 40))
    assert fixed["stopped"] is False
    assert fixed["pnl"] == pytest.approx(0.0)  # EOD mark at last close (1.00 = entry)


def test_simulator_real_still_excludes_the_fill_bar():
    """simulator_real's one-full-bar min hold is the reference convention every P5 cell,
    mass grind, and ship-gate was graded under. If this line changes, every cross-tool
    comparison in the fillbar audit is stale -- re-run it before trusting mixed numbers."""
    src = (REPO / "backtest" / "lib" / "simulator_real.py").read_text(encoding="utf-8")
    assert "opt_idx = entry_idx_opt + 1" in src, (
        "simulator_real no longer starts its exit walk at entry_idx+1 (fill bar excluded). "
        "The fill-bar convention contract changed -- re-run the fillbar audit "
        "(analysis/recommendations/entry-exit-matrix-fillbar-audit-2026-07-11.md) and "
        "update t4_exit_matrix's FILL-BAR CONVENTION disclosure before shipping this.")


def test_convention_disclosures_stay_documented():
    """The divergence is only safe while it stays disclosed at the point of use."""
    assert "FILL-BAR CONVENTION" in (t4.__doc__ or ""), (
        "t4_exit_matrix's module docstring lost its FILL-BAR CONVENTION disclosure")
    assert "fill bar itself" in (t4._load_bars.__doc__ or "")
    t5_src = (REPO / "backtest" / "tools" / "t5_confirmatory_matrix.py").read_text(
        encoding="utf-8")
    assert "KNOWN HAZARD (fillbar audit 2026-07-11)" in t5_src, (
        "t5.replay_entry2_pair lost its same-bar-TP1 look-behind hazard note")
