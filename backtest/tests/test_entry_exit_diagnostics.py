"""Pure-logic guard for entry_exit_diagnostics.py (T2). No backtest / no network -- locks the
band assignment + stop-harvest aggregation math so a silent regression in the priors (C7) reds."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))
sys.path.insert(0, str(REPO / "backtest" / "tools"))
import entry_exit_diagnostics as d  # noqa: E402


def test_band_boundaries():
    assert d.band_of(0.05) == "<0.20"
    assert d.band_of(0.19) == "<0.20"
    assert d.band_of(0.20) == "0.20-0.50"
    assert d.band_of(0.50) == "0.50-1.00"
    assert d.band_of(1.00) == ">1.00"
    assert d.band_of(3.14) == ">1.00"


def test_pctile_monotone():
    xs = [0.1, 0.2, 0.3, 0.4, 0.5]
    assert d._pctile(xs, 0.0) == 0.1
    assert d._pctile(xs, 0.5) == 0.3
    assert d._pctile(xs, 0.75) >= d._pctile(xs, 0.25)


def _row(prem, mae5, mae10, mfe, stop_bars, tp_bars):
    return {"entry_premium": prem, "band": d.band_of(prem), "mae_5min": mae5,
            "mae_10min": mae10, "mae_30min": mae10, "mfe_eod": mfe,
            "first_stop_bar": stop_bars, "first_tp_bar": tp_bars, "spread_pct": 0.3}


def test_stop_harvest_counts_stop_before_tp():
    """A signal whose -20% touch (bar 1) precedes its +50% touch (bar 3) counts as harvested;
    one whose +50% (bar 1) precedes -20% (bar 5) does not. Same-bar => stop-first."""
    rows = [
        _row(0.10, -0.2, -0.25, 0.6, {20: 1}, {50: 3}),   # stop-before-tp
        _row(0.11, -0.1, -0.15, 0.7, {20: 5}, {50: 1}),   # tp-before-stop
        _row(0.12, -0.2, -0.2, 0.6, {20: 2}, {50: 2}),    # same bar -> stop-first (counts)
    ]
    agg = d.aggregate(rows, n_signals=3)
    b = agg["bands"]["<0.20"]
    hv = b["stop_harvest"]["tp50"]
    assert hv["n_reached"] == 3  # all three reach +50%
    # 2 of 3 have -20% at/before the +50% bar (rows 1 and 3)
    assert abs(hv["stop20_before"] - round(2 / 3, 3)) < 1e-6


def test_unique_signal_vs_position_count():
    """Effective-n honesty (ground rule 8): n_unique_signals is carried distinct from n_positions."""
    rows = [_row(0.10, -0.2, -0.25, 0.6, {}, {}), _row(1.5, -0.1, -0.1, 0.3, {}, {})]
    agg = d.aggregate(rows, n_signals=1)  # 1 signal priced at 2 strikes
    assert agg["n_positions"] == 2 and agg["n_unique_signals"] == 1
