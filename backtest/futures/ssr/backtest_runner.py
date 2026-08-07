"""SSR battery trade runner -- turns SSRSignal objects into simulated trades.

Contract (work order, Builder 3): `run_trades(bars, snapshots, signals,
instrument, *, atr) -> list[dict]`. Full rule text lives in
backtest/futures/analysis/SSR-battery/DESIGN.md section 3 ("Risk" +
"Concurrency") -- summarized inline at each decision point below so the code
is self-auditing without cross-referencing the doc.

Per-signal pipeline:
    entry = NEXT bar's open (skip if no next bar)
    R = abs(entry - stop); stop from the signal (chart stop). R <= 0 or
        R < 1 tick -> skip, degenerate.
    tp1 = entry +/- 1.5R (profit direction)
    runner = nearest opposing level from the bar's LevelSnapshot strictly
        beyond tp1 in the profit direction, else 3R fallback; capped at 5R.
    future_bars = entry bar .. the last bar <= 16:55 ET of the signal's
        trading day (trading day = 18:00 ET (D-1) -> 17:00 ET (D)).
    futures_sim.simulate_futures(...) with px_to_points=1.0 -- ALWAYS.
        These are NATIVE real-instrument bars (GC/NQ/ES via yfinance), never
        the SPY-proxy convention futures_sim.py defaults to. Omitting
        px_to_points would silently fall back to instrument.spy_to_index
        (e.g. ES=10.0) and distort every point by 10x -- the single most
        dangerous default in this call, so it is never left implicit.

Concurrency: ONE open position per instrument. A position is considered open
from its entry bar through its simulated EXIT bar (inclusive) -- computed by
`_exit_bar_offset`, a read-only mirror of futures_sim.simulate_futures's own
bar-by-bar fill-order loop (STOP-checked-before-target on a same-bar
conflict). futures_sim.py is a read-only shared module (HARD RULE) and does
not expose which bar it exited on, so this mirror is the only way to know
when the next signal is allowed to enter without duplicating simulate_futures
itself. Signals are processed in chronological (bar_index) order; any
signal whose ENTRY bar falls at-or-before the open position's exit bar is
skipped and counted (`skipped_while_open`).

`levels` (ssr/levels.py) is a sibling, parallel-built module -- NOT imported
here. `run_trades` only depends on the LevelSnapshot DUCK TYPE its caller
passes in (`.all_levels() -> Iterable[(name, price)]`, or a bare float/2-tuple
for robustness), keeping this file's only hard dependency the shared,
already-stable `futures.futures_sim`.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

_BACKTEST_DIR = Path(__file__).resolve().parents[2]
if str(_BACKTEST_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKTEST_DIR))

from futures.futures_sim import simulate_futures  # noqa: E402

FLAT_TIME_ET = dt.time(16, 55)
DAY_ROLL_TIME_ET = dt.time(18, 0)   # trading day D ends 17:00 D, begins 18:00 (D-1)
TP1_R_MULT = 1.5
RUNNER_FALLBACK_R_MULT = 3.0
RUNNER_CAP_R_MULT = 5.0
QTY = 3
TP1_FRACTION = 2.0 / 3.0
SLIPPAGE_TICKS = 1.0
NATIVE_PX_TO_POINTS = 1.0  # ALWAYS -- see module docstring.

__all__ = ["run_trades", "future_bars_through_flat"]


def _direction_sign(direction: str) -> float:
    if direction not in ("long", "short"):
        raise ValueError(f"direction must be 'long' or 'short', got {direction!r}")
    return 1.0 if direction == "long" else -1.0


def _trading_day(ts_et: pd.Timestamp) -> dt.date:
    """Trading day per DESIGN.md sec 3: 18:00 ET (D-1) -> 17:00 ET (D).

    Mirrors ssr/levels.py::trading_day's semantics (same frozen spec,
    independently written here to keep this file's only hard import
    `futures.futures_sim` -- see module docstring). A timestamp at/after
    18:00 ET belongs to the NEXT calendar date's trading day; the
    17:00-18:00 ET Globex maintenance gap never carries real bars (both
    entry window 03:00-15:00 ET and this repo's data never populate it) so
    it is not specially handled.
    """
    return (ts_et + pd.Timedelta(days=1)).date() if ts_et.time() >= DAY_ROLL_TIME_ET else ts_et.date()


def future_bars_through_flat(bars: pd.DataFrame, entry_idx: int, ts_et: pd.Timestamp) -> pd.DataFrame:
    """bars[entry_idx : last bar with timestamp_et <= 16:55 ET of ts_et's trading day],
    reindexed 0..k-1. Empty (0-row) frame if entry_idx is already past that cutoff
    or out of range -- caller decides how to treat that (see `run_trades`)."""
    n = len(bars)
    if n == 0 or entry_idx < 0 or entry_idx >= n:
        return bars.iloc[0:0]
    tz = bars["timestamp_et"].dt.tz
    cutoff = pd.Timestamp.combine(_trading_day(ts_et), FLAT_TIME_ET)
    cutoff = cutoff.tz_localize(tz) if tz is not None else cutoff
    mask = (bars["timestamp_et"] <= cutoff).to_numpy()
    valid_positions = np.flatnonzero(mask)
    if valid_positions.size == 0 or int(valid_positions.max()) < entry_idx:
        return bars.iloc[entry_idx:entry_idx]
    end_idx = int(valid_positions.max())
    return bars.iloc[entry_idx:end_idx + 1].reset_index(drop=True)


def _exit_bar_offset(direction: str, entry: float, stop: float, tp1: float,
                      runner: Optional[float], future_bars: pd.DataFrame) -> int:
    """0-based offset into `future_bars` of the bar where futures_sim.simulate_futures
    would resolve this position's exit. Deliberately mirrors that function's own
    bar-by-bar loop ORDER (stop checked before target on a same-bar conflict) --
    simulate_futures itself never returns which bar it exited on, and it is a
    read-only shared module (HARD RULE, never edited here), so this is the only
    way to learn that without re-deriving P&L a second time. Keep this in
    lockstep with futures_sim.py's loop if that module's fill order ever changes.
    """
    n = len(future_bars)
    if n == 0:
        return -1
    filled = False
    stopc = stop
    for i, b in enumerate(future_bars.itertuples(index=False)):
        hi = float(b.high)
        lo = float(b.low)
        if direction == "long":
            if not filled and lo <= stopc:
                return i
            if filled and lo <= stopc:
                return i
            if runner is not None and hi >= runner:
                return i
            if not filled and hi >= tp1:
                filled, stopc = True, entry
        else:
            if not filled and hi >= stopc:
                return i
            if filled and hi >= stopc:
                return i
            if runner is not None and lo <= runner:
                return i
            if not filled and lo <= tp1:
                filled, stopc = True, entry
    return n - 1  # never resolved within the window -> time exit at the last bar


def _level_price(lvl) -> Optional[float]:
    """`lvl` is a (name, price) tuple per ssr/levels.py's LevelSnapshot.all_levels()
    contract. A bare float/int is also accepted (defensive -- keeps this file
    decoupled from levels.py's exact class, see module docstring)."""
    if isinstance(lvl, tuple) and len(lvl) == 2:
        return float(lvl[1])
    if isinstance(lvl, (int, float)):
        return float(lvl)
    return None


def _pick_runner(snapshot, entry: float, tp1: float, direction: str, r_points: float) -> tuple[float, str]:
    """Nearest opposing level from `snapshot.all_levels()` strictly beyond tp1
    in the profit direction; else a fixed 3R. Either way, capped at 5R from
    entry. Returns (runner_price, source) with source in
    {"level", "fallback_3r", "capped_5r"} for per-cell disclosure."""
    sign = _direction_sign(direction)
    candidates: list[float] = []
    if snapshot is not None:
        for lvl in snapshot.all_levels():
            price = _level_price(lvl)
            if price is None:
                continue
            if (sign > 0 and price > tp1) or (sign < 0 and price < tp1):
                candidates.append(price)

    cap_price = entry + sign * RUNNER_CAP_R_MULT * r_points
    if candidates:
        nearest = min(candidates) if sign > 0 else max(candidates)
        if (sign > 0 and nearest > cap_price) or (sign < 0 and nearest < cap_price):
            return cap_price, "capped_5r"
        return nearest, "level"
    return entry + sign * RUNNER_FALLBACK_R_MULT * r_points, "fallback_3r"


def _extract_shift_mode(state_trace) -> str:
    """Best-effort human-readable label for which SWEPT->SHIFTED confirmation
    fired (BOS / pivot / displacement per DESIGN.md sec 3). `state_trace`'s
    exact shape is owned by detector.py (a sibling, parallel-built module) --
    this is a diagnostic-only field, so an unrecognized shape degrades to
    "unknown" rather than raising (caller counts the fallback)."""
    candidate_keys = ("shift_mode", "shift_reason", "shift_type", "shifted_via", "mode")
    if isinstance(state_trace, dict):
        for key in candidate_keys:
            if key in state_trace and state_trace[key]:
                return str(state_trace[key])
        for entry in state_trace.get("events", []) if isinstance(state_trace.get("events"), list) else []:
            if isinstance(entry, dict) and entry.get("state") == "SHIFTED":
                for key in candidate_keys:
                    if key in entry and entry[key]:
                        return str(entry[key])
    elif isinstance(state_trace, (list, tuple)):
        for entry in state_trace:
            if isinstance(entry, dict) and entry.get("state") in ("SHIFTED", None):
                for key in candidate_keys:
                    if key in entry and entry[key]:
                        return str(entry[key])
    return "unknown"


def run_trades(
    bars: pd.DataFrame,
    snapshots: list,
    signals: list,
    instrument,
    *,
    atr: Optional[pd.Series] = None,
    stats: Optional[dict] = None,
) -> list[dict]:
    """Walk `signals` chronologically through `bars`, one open position at a
    time, and return a list of trade dicts (see module docstring for the
    per-signal pipeline). `stats`, if passed a dict, is updated IN PLACE with
    skip/fallback counters -- an additive keyword-only param so the frozen
    call shape `run_trades(bars, snapshots, signals, instrument, *, atr)`
    still works unchanged for any caller that doesn't need the counts.
    """
    counts = {
        "skipped_while_open": 0,
        "skipped_no_next_bar": 0,
        "skipped_degenerate": 0,
        "skipped_no_future_bars": 0,
        "runner_fallback_3r": 0,
        "runner_capped_5r": 0,
        "snapshot_missing": 0,
        "shift_mode_unknown": 0,
    }
    trades: list[dict] = []
    n_bars = len(bars)
    position_open_until = -1

    ordered = sorted(signals, key=lambda s: (s.bar_index, s.ts_et))
    for sig in ordered:
        entry_idx = sig.bar_index + 1
        if entry_idx >= n_bars:
            counts["skipped_no_next_bar"] += 1
            continue
        if entry_idx <= position_open_until:
            counts["skipped_while_open"] += 1
            continue

        entry = float(bars["open"].iloc[entry_idx])
        stop = float(sig.stop_price)
        r_points = abs(entry - stop)
        tick = float(instrument.tick_size)
        if r_points <= 0 or r_points < tick:
            counts["skipped_degenerate"] += 1
            continue

        future_bars = future_bars_through_flat(bars, entry_idx, sig.ts_et)
        if len(future_bars) == 0:
            counts["skipped_no_future_bars"] += 1
            continue

        direction = sig.direction
        sign = _direction_sign(direction)
        tp1 = entry + sign * TP1_R_MULT * r_points

        snapshot = snapshots[sig.bar_index] if 0 <= sig.bar_index < len(snapshots) else None
        if snapshot is None:
            counts["snapshot_missing"] += 1
        runner, runner_source = _pick_runner(snapshot, entry, tp1, direction, r_points)
        if runner_source == "fallback_3r":
            counts["runner_fallback_3r"] += 1
        elif runner_source == "capped_5r":
            counts["runner_capped_5r"] += 1

        result = simulate_futures(
            direction, entry, stop, tp1, runner, future_bars, instrument,
            qty=QTY, tp1_fraction=TP1_FRACTION, slippage_ticks=SLIPPAGE_TICKS,
            px_to_points=NATIVE_PX_TO_POINTS,
        )

        exit_offset = max(_exit_bar_offset(direction, entry, stop, tp1, runner, future_bars), 0)
        position_open_until = entry_idx + exit_offset

        shift_mode = _extract_shift_mode(sig.state_trace)
        if shift_mode == "unknown":
            counts["shift_mode_unknown"] += 1

        atr_at_entry = None
        if atr is not None and 0 <= sig.bar_index < len(atr):
            v = float(atr.iloc[sig.bar_index])
            atr_at_entry = v if np.isfinite(v) else None

        trades.append({
            "date": _trading_day(sig.ts_et),
            "ts_entry_et": bars["timestamp_et"].iloc[entry_idx],
            "direction": direction,
            "level_name": sig.level_name,
            "shift_mode": shift_mode,
            "entry": round(entry, 4),
            "stop": round(stop, 4),
            "tp1": round(tp1, 4),
            "runner": round(runner, 4),
            "runner_source": runner_source,
            "outcome": result["outcome"],
            "gross": result["gross"],
            "net": result["net"],
            "r_points": round(r_points, 4),
            "bars_held": exit_offset,
            "atr_at_entry": atr_at_entry,
        })

    if stats is not None:
        stats.update(counts)
    return trades
