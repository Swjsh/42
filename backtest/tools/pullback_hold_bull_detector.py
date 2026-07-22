"""backtest/tools/pullback_hold_bull_detector.py -- PULLBACK-HOLD bull entry detector.

Frozen pre-reg: analysis/recommendations/pullback-hold-bull-prereg-2026-07-22.json
Queue item: PULLBACK-HOLD-BULL-TRIGGER (automation/overnight/queue.md).

WHAT THIS IS: a pure, no-look-ahead detector of the pattern J named live twice in two days
(DOJO-HARVEST-2026-07-21.md): in an emerging/confirmed up structure, price pulls back and
its LOW enters the zone band around a known (level-memory) level, then CLOSES back above the
zone's top within N bars. This is $2-3 EARLIER than the engine's only existing bull trigger
(ELITE level_reclaim), which by definition only fires after price has already reclaimed the
raw level -- structurally late, per the queue item's root-cause analysis.

PURITY / INJECTION CONTRACT (mirrors crypto/lib/market_structure.py's own `swing_finder`
injection style -- one detector implementation, features computed by the caller):
  - `day_bars`: ONE day's RTH 5m OHLC bars, chronological, columns
    [timestamp_et, open, high, low, close], index 0..n-1 (day-local).
  - `up_structure_ok`: a per-bar boolean sequence, len == len(day_bars), precomputed by the
    CALLER using only bars <= that index (no look-ahead is the caller's contract; this
    module never re-derives it).
  - `levels_at(day_local_idx) -> Sequence[float]`: known level prices visible AS OF that bar
    (typically backtest.lib.watchers.level_memory.LevelMemory.levels_at, itself
    look-ahead-safe by construction -- see that module's own docstring).
  - `rsi_at(day_local_idx) -> float | None`: optional, only consulted when
    confirm_mode == "BOTH".

NO LOOK-AHEAD (C6): the walk only ever inspects bar k for k >= the pullback-low bar j when
looking for the "closes back above zone top within N bars" condition -- this is NOT a
look-ahead violation. The emitted signal's `entry_bar_idx` is dated at the bar k where the
close-above-zone-top ACTUALLY happened; nothing before bar k is claimed to have "known" that
in advance. Guarded by test_pullback_hold_bull.py's truncation test (truncating day_bars to
end right after a signal's entry bar reproduces the identical signal; truncating BEFORE it
drops it -- the standard no-look-ahead pattern used by LevelMemory's own guard test).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal, Optional, Sequence

import pandas as pd

_REPO = Path(__file__).resolve().parents[2]  # .../42 (parent of backtest/ and crypto/)
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

UpStructureMode = Literal["MARKET_STRUCTURE", "PRICE_VWAP"]
ConfirmMode = Literal["NONE", "BOTH"]


@dataclass(frozen=True, slots=True)
class PullbackHoldParams:
    up_structure_mode: UpStructureMode
    zone_band_cents: float          # dollars (e.g. 0.15 / 0.25 / 0.40), symmetric half-width
    hold_bars_n: int                # 1 | 2 | 3
    confirm_mode: ConfirmMode = "NONE"
    rsi_reset_threshold: float = 55.0
    rsi_reset_lookback_bars: int = 6
    structure_lookback_bars: int = 60   # only consulted when up_structure_mode==MARKET_STRUCTURE

    def cell_id(self) -> str:
        band_c = int(round(self.zone_band_cents * 100))
        return f"{self.up_structure_mode}_band{band_c}c_N{self.hold_bars_n}_{self.confirm_mode}"


@dataclass(frozen=True, slots=True)
class PullbackHoldSignal:
    day: str
    pullback_bar_idx: int
    pullback_ts: "pd.Timestamp"
    pullback_low: float
    level_price: float
    zone_low: float
    zone_top: float
    entry_bar_idx: int
    entry_ts: "pd.Timestamp"
    entry_close: float
    bars_to_hold: int
    up_structure_mode: str
    rsi_at_entry: Optional[float]
    rsi_reset_ok: bool
    green_close_ok: bool
    passed_confirmation: bool


def detect_pullback_hold_bull(
    day_bars: pd.DataFrame,
    *,
    up_structure_ok: Sequence[bool],
    levels_at: Callable[[int], Sequence[float]],
    params: PullbackHoldParams,
    day_label: str,
    rsi_at: Optional[Callable[[int], Optional[float]]] = None,
) -> list[PullbackHoldSignal]:
    """Walk one day's bars, oldest first. Returns entry signals in chronological order.

    One pullback-low candidate consumes bars [j, entry_bar_idx] (or just bar j, if no hold
    fires within N bars) -- the next candidate search resumes strictly after that, mirroring
    Rule 4 (no adding without a NEW confirmed trigger): a single continuation never spawns
    overlapping/duplicate signals.
    """
    n = len(day_bars)
    if n == 0:
        return []
    if len(up_structure_ok) != n:
        raise ValueError(f"up_structure_ok length {len(up_structure_ok)} != day_bars length {n}")

    opens = day_bars["open"].astype(float).tolist()
    lows = day_bars["low"].astype(float).tolist()
    closes = day_bars["close"].astype(float).tolist()
    ts_list = list(day_bars["timestamp_et"])

    signals: list[PullbackHoldSignal] = []
    j = 0
    while j < n:
        if not up_structure_ok[j]:
            j += 1
            continue
        levels = levels_at(j)
        if not levels:
            j += 1
            continue
        low_j = lows[j]
        candidates = [L for L in levels if abs(low_j - L) <= params.zone_band_cents]
        if not candidates:
            j += 1
            continue
        level_price = min(candidates, key=lambda L: abs(low_j - L))
        zone_low = level_price - params.zone_band_cents
        zone_top = level_price + params.zone_band_cents

        entry_idx = None
        hold_end = min(j + params.hold_bars_n, n - 1)
        for k in range(j, hold_end + 1):
            if closes[k] > zone_top:
                entry_idx = k
                break

        if entry_idx is None:
            j += 1
            continue

        rsi_val: Optional[float] = None
        green_close_ok = closes[entry_idx] > opens[entry_idx]
        if params.confirm_mode == "BOTH":
            rsi_reset_ok = False
            if rsi_at is not None:
                rsi_val = rsi_at(entry_idx)
                lo_lb = max(0, entry_idx - params.rsi_reset_lookback_bars)
                trail_vals = [v for v in (rsi_at(k2) for k2 in range(lo_lb, entry_idx)) if v is not None]
                rsi_reset_ok = bool(trail_vals) and min(trail_vals) <= params.rsi_reset_threshold
            passed_confirmation = rsi_reset_ok and green_close_ok
        else:
            rsi_reset_ok = True
            passed_confirmation = True

        if passed_confirmation:
            signals.append(PullbackHoldSignal(
                day=day_label, pullback_bar_idx=j, pullback_ts=ts_list[j], pullback_low=low_j,
                level_price=level_price, zone_low=zone_low, zone_top=zone_top,
                entry_bar_idx=entry_idx, entry_ts=ts_list[entry_idx], entry_close=closes[entry_idx],
                bars_to_hold=entry_idx - j, up_structure_mode=params.up_structure_mode,
                rsi_at_entry=rsi_val, rsi_reset_ok=rsi_reset_ok, green_close_ok=green_close_ok,
                passed_confirmation=passed_confirmation,
            ))
        j = entry_idx + 1  # no new candidate search starts inside a just-consumed window

    return signals


# =====================================================================================
# Feature precomputation helpers -- reused by the replay harness, kept here (not
# duplicated) since they are part of the detector's documented injection contract.
# =====================================================================================
def session_vwap_series(day_bars: pd.DataFrame) -> list[float]:
    """Session-anchored (resets each call -- caller passes ONE day's bars) VWAP, per bar,
    cumulative typical-price*volume / cumulative volume. Same convention as
    crypto/lib/indicators.vwap / crypto/lib/confluence._session_vwap. No look-ahead: bar i's
    value uses only bars <= i."""
    out: list[float] = []
    cum_vp = 0.0
    cum_v = 0.0
    for _, r in day_bars.iterrows():
        tp = (float(r["high"]) + float(r["low"]) + float(r["close"])) / 3.0
        vol = float(r.get("volume", 0.0) or 0.0)
        cum_vp += tp * vol
        cum_v += vol
        out.append(cum_vp / cum_v if cum_v > 0 else float(r["close"]))
    return out


def market_structure_up_ok(day_bars: pd.DataFrame, lookback_bars: int = 60) -> list[bool]:
    """Per-bar 'uptrend per crypto.lib.market_structure' boolean, using ONLY a trailing
    day-local window ending at (and including) the candidate bar -- no look-ahead."""
    from datetime import timezone as _tz

    from crypto.lib.bar import Bar
    from crypto.lib.market_structure import analyze_structure

    n = len(day_bars)
    bars_objs: list[Bar] = []
    for _, r in day_bars.iterrows():
        ts = r["timestamp_et"]
        py_ts = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
        if py_ts.tzinfo is None:
            py_ts = py_ts.replace(tzinfo=_tz.utc)
        bars_objs.append(Bar(
            open_time=py_ts, open=float(r["open"]), high=float(r["high"]),
            low=float(r["low"]), close=float(r["close"]),
            volume=float(r.get("volume", 0.0) or 0.0), granularity_seconds=300, source="cache",
        ))
    out = [False] * n
    for i in range(n):
        lo = max(0, i - lookback_bars + 1)
        window = bars_objs[lo:i + 1]
        if len(window) < 8:  # need enough bars to seed >=2 swing highs + >=2 swing lows
            continue
        read = analyze_structure(window)
        out[i] = read.trend == "uptrend"
    return out


def price_above_vwap_ok(day_bars: pd.DataFrame) -> list[bool]:
    vwap = session_vwap_series(day_bars)
    closes = day_bars["close"].astype(float).tolist()
    return [c > v for c, v in zip(closes, vwap)]


def up_structure_series(day_bars: pd.DataFrame, mode: UpStructureMode,
                         structure_lookback_bars: int = 60) -> list[bool]:
    if mode == "MARKET_STRUCTURE":
        return market_structure_up_ok(day_bars, lookback_bars=structure_lookback_bars)
    if mode == "PRICE_VWAP":
        return price_above_vwap_ok(day_bars)
    raise ValueError(f"unknown up_structure_mode {mode!r}")
