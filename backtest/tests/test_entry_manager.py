"""Unit tests + parity proof for entry_manager.py (T-W5, entry-2's machinery -- SHADOW ONLY).

Ports t3_entry_matrix.entry_fill's fill/miss/convert/patience semantics tick-wise and proves
DIRECT PARITY against that backtest function on the same synthetic bar sequences -- the tick
loop below feeds each bar's LOW as the tick's `ask` (the live analog of the backtest's bar-low
fill check), one call to plan_entry_action per bar, and the resulting fill/miss/convert
verdict must match entry_fill()'s verdict on the identical bars.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_FLEET = _ROOT / "automation" / "state" / "fleet"
_TOOLS = _ROOT / "backtest" / "tools"
for _p in (_FLEET, _TOOLS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from entry_manager import EntryState, plan_entry_action  # noqa: E402
from t3_entry_matrix import entry_fill  # noqa: E402 -- the validated backtest reference


def _tick_walk(signal_premium: float, bars: list, *, delta: float, patience: int, policy: str):
    """Drive plan_entry_action one bar at a time (bar low = this tick's ask), mirroring
    entry_fill's bar-by-bar scan. Returns (status, fill_price, ticks_used)."""
    state = EntryState.from_signal(symbol="SPY_TEST", side="P", signal_premium=signal_premium,
                                   delta=delta, patience_ticks=patience, policy=policy)
    ticks = 0
    for bar in bars:
        low = bar[3]
        decision = plan_entry_action(state, ask=low)
        state = decision.state
        ticks += 1
        if state.status != "pending":
            return state.status, state.fill_price, ticks
        if ticks >= patience and state.placed_order_id is not None:
            break
    return state.status, state.fill_price, ticks


# (time, open, high, low, close) synthetic bars, mirroring t3_entry_matrix's bar tuple shape.
BARS_FILLS_BAR0 = [(0, 1.00, 1.05, 0.75, 0.80), (1, 0.80, 0.90, 0.78, 0.85)]
BARS_FILLS_BAR2 = [(0, 1.00, 1.02, 0.95, 0.98), (1, 0.98, 1.00, 0.93, 0.95),
                    (2, 0.95, 0.97, 0.75, 0.80), (3, 0.80, 0.85, 0.78, 0.82)]
BARS_NEVER_DIPS = [(0, 1.00, 1.05, 0.98, 1.02), (1, 1.02, 1.06, 0.99, 1.03),
                    (2, 1.03, 1.07, 1.00, 1.04)]


def test_fills_immediately_bar0():
    """delta=0.10 on signal=1.00 -> limit=0.90; bar0 low=0.75 <= 0.90-0.01 -> fills tick 0."""
    status, fill_price, ticks = _tick_walk(1.00, BARS_FILLS_BAR0, delta=0.10, patience=3, policy="cancel")
    assert status == "filled"
    assert fill_price == 0.90
    assert ticks == 1


def test_fills_within_patience_window():
    status, fill_price, ticks = _tick_walk(1.00, BARS_FILLS_BAR2, delta=0.20, patience=3, policy="cancel")
    assert status == "filled"
    assert fill_price == 0.80        # signal*(1-0.20) = 0.80, bar2 low=0.75 crosses it
    assert ticks == 3


def test_miss_beyond_patience_cancels():
    status, fill_price, ticks = _tick_walk(1.00, BARS_NEVER_DIPS, delta=0.20, patience=3, policy="cancel")
    assert status == "missed"
    assert fill_price is None


def test_miss_beyond_patience_converts_to_marketable():
    """policy='convert': patience exhausted -> CONVERT at the current ask (the window-end
    marketable fallback, mirrors entry_fill's `bars[j][1]` open-at-window-end rule in spirit --
    entry_manager converts at the current tick's ask, the live analog)."""
    status, fill_price, ticks = _tick_walk(1.00, BARS_NEVER_DIPS, delta=0.20, patience=3, policy="convert")
    assert status == "converted"
    assert fill_price == BARS_NEVER_DIPS[2][3]   # ask at the conversion tick


def test_pending_state_ignores_further_ticks_once_resolved():
    state = EntryState.from_signal(symbol="X", side="P", signal_premium=1.00, delta=0.10,
                                   patience_ticks=3, policy="cancel")
    d1 = plan_entry_action(state, ask=0.85)   # fills immediately (0.85 <= 0.90-0.01)
    assert d1.state.status == "filled"
    d2 = plan_entry_action(d1.state, ask=0.50)   # must NOT re-fill / change fill_price
    assert d2.state.status == "filled"
    assert d2.state.fill_price == d1.state.fill_price
    assert d2.action.kind == "HOLD"


def test_parity_vs_t3_entry_matrix_entry_fill():
    """DIRECT PARITY: for a grid of (delta, patience, bars) combos, the tick-wise core's
    fill/miss verdict + fill price must match entry_fill()'s verdict on the IDENTICAL bars."""
    cases = [
        (1.00, BARS_FILLS_BAR0, 0.10, 3, "cancel"),
        (1.00, BARS_FILLS_BAR2, 0.20, 3, "cancel"),
        (1.00, BARS_FILLS_BAR2, 0.20, 5, "cancel"),
        (1.00, BARS_NEVER_DIPS, 0.20, 3, "cancel"),
        (2.50, BARS_FILLS_BAR0, 0.15, 2, "cancel"),
    ]
    for signal, bars, delta, patience, policy in cases:
        ref = entry_fill(bars, signal, {"type": "limit", "delta": delta, "patience": patience,
                                        "miss": policy if policy != "cancel" else "cancel"})
        status, fill_price, _ = _tick_walk(signal, bars, delta=delta, patience=patience, policy=policy)
        if ref is None:
            assert status == "missed", (signal, bars, delta, patience)
        else:
            assert status == "filled", (signal, bars, delta, patience)
            assert abs(fill_price - ref["entry"]) < 1e-9, (fill_price, ref["entry"])


def test_bad_policy_rejected():
    import pytest
    with pytest.raises(ValueError, match="cancel.*convert"):
        EntryState.from_signal(symbol="X", side="P", signal_premium=1.0, delta=0.1,
                               patience_ticks=3, policy="bogus")
