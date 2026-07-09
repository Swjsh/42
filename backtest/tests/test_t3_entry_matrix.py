"""Pure-logic guard for t3_entry_matrix.entry_fill (T3). No backtest/network. Locks the limit
fill/miss/convert accounting -- the mechanic the whole passive-entry adjudication rests on."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))
sys.path.insert(0, str(REPO / "backtest" / "tools"))
sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))
import t3_entry_matrix as t3  # noqa: E402

_T = dt.time(9, 40)
# bars: (time, open, high, low, close)
BARS = [(_T, 1.00, 1.05, 0.98, 1.00), (_T, 1.00, 1.02, 0.90, 0.92),
        (_T, 0.92, 0.95, 0.80, 0.85), (_T, 0.85, 0.88, 0.70, 0.72)]


def test_market_fills_at_signal_premium():
    f = t3.entry_fill(BARS, 1.00, {"type": "market"})
    assert f["entry"] == 1.00 and f["fill_idx"] == 0 and f["converted"] is False


def test_limit_fills_when_bar_dips_within_patience():
    # limit 10% below 1.00 = 0.90; bar[1] low 0.90 -> needs <= 0.89; bar[2] low 0.80 <= 0.89 fills at 0.90.
    f = t3.entry_fill(BARS, 1.00, {"type": "limit", "delta": 0.10, "patience": 3, "miss": "cancel"})
    assert f is not None and abs(f["entry"] - 0.90) < 1e-9 and f["fill_idx"] == 2


def test_limit_misses_with_cancel_when_too_deep():
    # limit 50% below = 0.50; no bar low <= 0.49 -> cancel -> miss (None).
    f = t3.entry_fill(BARS, 1.00, {"type": "limit", "delta": 0.50, "patience": 4, "miss": "cancel"})
    assert f is None


def test_limit_converts_to_market_at_window_end():
    # same deep limit but convert -> market at bar[min(patience,len-1)].
    f = t3.entry_fill(BARS, 1.00, {"type": "limit", "delta": 0.50, "patience": 2, "miss": "convert"})
    assert f is not None and f["converted"] is True and f["fill_idx"] == 2 and f["entry"] == BARS[2][1]


def test_patience_bounds_the_search():
    # limit 10% (0.90) but patience 1 -> only bar[0] (low 0.98, not <= 0.89) -> cancel miss.
    f = t3.entry_fill(BARS, 1.00, {"type": "limit", "delta": 0.10, "patience": 1, "miss": "cancel"})
    assert f is None
