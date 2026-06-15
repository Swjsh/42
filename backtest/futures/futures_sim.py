"""Futures point-P&L bracket simulator for the 42 Futures Edition.

Takes a watcher signal (entry/stop/tp1/runner expressed in SPY price for the proxy,
or already in index points for real bars) and a window of future bars, and returns
realistic futures P&L in $ for `qty` contracts:

    pnl_$ = (index points captured) * instrument.point_value * contracts
            - slippage (1 tick each side) - round-turn commissions/fees

Bracket doctrine mirrors the engine's grade_observation:
  - tp1_fraction of qty exits at TP1; stop moves to break-even on the runner.
  - Runner exits at `runner` target, BE stop, or time-stop at the last bar's close.
  - Full stop before TP1 = full-size loss.

`px_to_points`: multiplier converting an entry-relative PRICE move into INDEX POINTS.
  - Proxy mode (SPY bars):    px_to_points = instrument.spy_to_index (e.g. 10 for MES/ES)
  - Native mode (real bars):  px_to_points = 1.0 (levels already in index points)
"""
from __future__ import annotations
from typing import Optional
import pandas as pd


def simulate_futures(
    direction: str,
    entry: float, stop: float, tp1: float, runner: Optional[float],
    future_bars: pd.DataFrame,
    instrument,
    qty: int = 3,
    tp1_fraction: float = 0.5,
    slippage_ticks: float = 1.0,
    px_to_points: Optional[float] = None,
) -> dict:
    s2p = px_to_points if px_to_points is not None else (instrument.spy_to_index or 1.0)
    pv = instrument.point_value
    tick = instrument.tick_size
    tp1_qty = max(1, int(round(qty * tp1_fraction)))
    run_qty = max(0, qty - tp1_qty)

    filled = False
    stopc = stop
    pts = 0.0   # signed index-points * contracts accumulated
    outcome = "open"

    for b in future_bars.itertuples(index=False):
        hi = float(b.high); lo = float(b.low)
        if direction == "long":
            if not filled and lo <= stopc:
                pts += (stopc - entry) * s2p * qty; outcome = "stopped"; break
            if filled and lo <= stopc:
                pts += (stopc - entry) * s2p * run_qty; outcome = "tp1_then_be"; break
            if runner is not None and hi >= runner:
                if not filled:
                    pts += (tp1 - entry) * s2p * tp1_qty; filled = True
                pts += (runner - entry) * s2p * run_qty; outcome = "runner"; break
            if not filled and hi >= tp1:
                pts += (tp1 - entry) * s2p * tp1_qty; filled = True; stopc = entry
        else:  # short
            if not filled and hi >= stopc:
                pts += (entry - stopc) * s2p * qty; outcome = "stopped"; break
            if filled and hi >= stopc:
                pts += (entry - stopc) * s2p * run_qty; outcome = "tp1_then_be"; break
            if runner is not None and lo <= runner:
                if not filled:
                    pts += (entry - tp1) * s2p * tp1_qty; filled = True
                pts += (entry - runner) * s2p * run_qty; outcome = "runner"; break
            if not filled and lo <= tp1:
                pts += (entry - tp1) * s2p * tp1_qty; filled = True; stopc = entry

    if outcome == "open":
        last = float(future_bars.iloc[-1]["close"]) if len(future_bars) else entry
        rem = run_qty if filled else qty
        if direction == "long":
            pts += (last - entry) * s2p * rem
        else:
            pts += (entry - last) * s2p * rem
        outcome = "tp1_then_timeexit" if filled else "time_exit"

    gross = pts * pv
    slippage_cost = slippage_ticks * tick * pv * qty * 2.0
    commissions = instrument.round_turn_usd * qty
    net = gross - slippage_cost - commissions
    return {"outcome": outcome, "gross": round(gross, 2), "net": round(net, 2),
            "qty": qty, "filled_tp1": filled}
