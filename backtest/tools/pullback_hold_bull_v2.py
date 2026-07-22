"""backtest/tools/pullback_hold_bull_v2.py -- PULLBACK-HOLD bull entry detector, ITERATION 2.

Frozen pre-reg: analysis/recommendations/pullback-hold-bull-prereg-v2-2026-07-22.json
v1 (superseded, kept as committed evidence): backtest/tools/pullback_hold_bull_detector.py,
analysis/recommendations/pullback-hold-bull-stage-summary-2026-07-22.md (NO_CELL_SHIPS, honest
null -- root cause: both v1 up-structure qualifiers (MARKET_STRUCTURE, PRICE_VWAP) read False
AT the pullback-low bar and only recovered True 15-45 min later; "low within band of ANY
LevelMemory level" fired 9-13x/day, diluting to noise).

WHAT CHANGED (v2, fixes exactly v1's two diagnosed failures, nothing else):
  1. IMPULSE-LEG up-structure qualifier -- computable causally AT the pullback-low bar itself
     (no trend-confirmation lag, no VWAP-crossing lag). Within the last K bars there must exist
     an upswing leg (low->high) of >= M dollars; the CURRENT bar's own low must retrace <= R of
     that leg AND sit ABOVE the leg's origin low (a genuine higher low, never an undercut).
  2. SELECTIVITY -- "any known level" is replaced by a level that is EITHER (a) already
     battle-tested (>=1 same-day touch/bounce before this pullback) or (b) IS the impulse leg's
     own origin low (the most meaningful kind of support: literally where the current move
     launched from). Disclosed to cut entry frequency hard vs v1's any-level rule.

IMPULSE-LEG DEFINITION (frozen, hand-verified against both of J's named exhibits before this
grid was run -- see the pre-reg's `up_structure_qualifier.hand_verification` block):
  - Bars are EXTENDED (04:00 ET premarket onward, same calendar day, chronological) so the
    leg lookback can reach behind the 09:30 open on days where the real impulse started
    pre-market (exactly what v1's RTH-only, trend-confirmation-lag qualifiers could never see
    early in the session -- this is the direct fix for v1's diagnosed failure #1).
  - `leg_high` = max(CLOSE) over the K EXTENDED bars strictly BEFORE the candidate bar (close,
    not intrabar high/low, to avoid single-wick noise -- same convention PRICE_VWAP already
    used in v1).
  - `leg_origin_low` = the LOW of the bar exactly K bars back (the trailing window's own FIRST
    bar) -- a fixed, deterministic reference, never a searched extremum. This is deliberate:
    searching for the single lowest low anywhere in the K-bar window lets one low-liquidity
    premarket wick (verified this fire: 2026-07-22 08:55 ET, volume 152,849 vs a ~10-50k
    typical premarket bar, low 744.30) get cherry-picked as "the origin," which manufactures
    an artificially generous leg and breaks the intended R-grid asymmetry (verified: with a
    searched-min origin, retrace computes to 0.52, so EVEN R=0.618 would pass -- collapsing
    the whole point of testing R as a selectivity axis). The fixed trailing-bar reference does
    not have this failure mode and is fully causal (K bars is caller-controlled, pre-registered).
  - `leg_dollars` = leg_high - leg_origin_low; must be >= M.
  - `pullback_low` = the candidate bar's OWN low (intrabar, matching the hold-zone's own
    definition of "the low that entered the zone").
  - `retrace` = (leg_high - pullback_low) / leg_dollars; must be <= R.
  - `pullback_low` must be STRICTLY above `leg_origin_low` (a genuine higher low).
  No look-ahead (C6): the K-bar window is bars strictly BEFORE the candidate bar, plus the
  candidate bar's own low -- nothing at or after the candidate bar's close is ever consulted.

SELECTIVITY MODES (replaces v1's "any LevelMemory level in the zone band"):
  - PRIOR_INTERACTION: the matched level must have had >=1 same-day bar (strictly BEFORE the
    pullback-low candidate bar) whose high/low came within LevelMemory's own TOUCH_TOL (0.20,
    reused -- not a new invented constant) of the level price.
  - LEG_ORIGIN: the matched level must itself be within `zone_band_cents` (reused, not a new
    invented tolerance) of the SAME candidate bar's own impulse-leg `leg_origin_low` -- i.e.
    the level being held above must coincide with where the current impulse leg started.

PURITY / INJECTION CONTRACT: same style as v1 -- pure detector, features precomputed by the
caller (`up_structure_ok`, `leg_origin_lows`, `levels_at`, `prior_touch_ok`), no I/O, no
broker imports, no global state.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal, Optional, Sequence

import pandas as pd

_REPO = Path(__file__).resolve().parents[2]  # .../42 (parent of backtest/ and crypto/)
_BACKTEST = _REPO / "backtest"
for _p in (str(_REPO), str(_BACKTEST)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

SelectivityMode = Literal["PRIOR_INTERACTION", "LEG_ORIGIN"]

# Reused, not re-derived -- LevelMemory's own touch tolerance (module default).
from lib.watchers.level_memory import TOUCH_TOL as LEVEL_MEMORY_TOUCH_TOL  # noqa: E402


@dataclass(frozen=True, slots=True)
class ImpulseLegParams:
    k_bars: int              # 12 | 24 -- trailing EXTENDED-bar lookback window
    min_leg_dollars: float   # M -- minimum leg size in dollars
    max_retrace_pct: float   # R -- maximum allowed retracement fraction of the leg

    def mode_id(self) -> str:
        return f"K{self.k_bars}_M{self.min_leg_dollars:.2f}_R{self.max_retrace_pct:.3f}"


@dataclass(frozen=True, slots=True)
class ImpulseLegBar:
    ok: bool
    leg_high: Optional[float]
    leg_origin_low: Optional[float]
    leg_dollars: Optional[float]
    retrace_pct: Optional[float]


@dataclass(frozen=True, slots=True)
class PullbackHoldV2Params:
    impulse_leg_mode: str            # human label, e.g. "K24_M1.00_R0.786" (== ImpulseLegParams.mode_id())
    k_bars: int
    min_leg_dollars: float
    max_retrace_pct: float
    selectivity_mode: SelectivityMode
    zone_band_cents: float           # dollars, symmetric half-width
    hold_bars_n: int                 # 1 | 2

    def cell_id(self) -> str:
        band_c = int(round(self.zone_band_cents * 100))
        return f"{self.impulse_leg_mode}_{self.selectivity_mode}_band{band_c}c_N{self.hold_bars_n}"


@dataclass(frozen=True, slots=True)
class PullbackHoldSignalV2:
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
    impulse_leg_mode: str
    selectivity_mode: str
    leg_high: Optional[float]
    leg_origin_low: Optional[float]
    retrace_pct: Optional[float]


# =====================================================================================
# Impulse-leg feature precomputation -- EXTENDED (premarket-inclusive) bars in, one
# ImpulseLegBar per RTH-day-local bar out. No look-ahead: window is strictly BEFORE the
# candidate bar's own extended-frame index; the candidate's own low is the only thing
# from "now" ever consulted.
# =====================================================================================
def impulse_leg_series(
    ext_day_bars: pd.DataFrame,
    rth_day_bars: pd.DataFrame,
    params: ImpulseLegParams,
) -> list[ImpulseLegBar]:
    """ext_day_bars: ONE day's bars from premarket open (04:00 ET) through RTH close,
    chronological, columns [timestamp_et, open, high, low, close, ...]. rth_day_bars: the
    RTH-only subset (09:30-16:00) of the SAME day, in the SAME row order the caller uses
    for entry/hold scanning. Returns one ImpulseLegBar per row of rth_day_bars."""
    ext_local = ext_day_bars.reset_index(drop=True)
    ext_ts_to_idx = {ts: i for i, ts in enumerate(ext_local["timestamp_et"])}
    closes = ext_local["close"].astype(float).tolist()
    lows = ext_local["low"].astype(float).tolist()

    out: list[ImpulseLegBar] = []
    for _, row in rth_day_bars.iterrows():
        ext_i = ext_ts_to_idx.get(row["timestamp_et"])
        if ext_i is None or ext_i < params.k_bars:
            out.append(ImpulseLegBar(False, None, None, None, None))
            continue
        window_start = ext_i - params.k_bars
        leg_high = max(closes[window_start:ext_i])
        leg_origin_low = lows[window_start]
        leg_dollars = leg_high - leg_origin_low
        pullback_low = float(row["low"])
        if leg_dollars <= 0 or leg_dollars < params.min_leg_dollars or pullback_low <= leg_origin_low:
            out.append(ImpulseLegBar(False, leg_high, leg_origin_low,
                                      leg_dollars if leg_dollars > 0 else None, None))
            continue
        retrace = (leg_high - pullback_low) / leg_dollars
        ok = retrace <= params.max_retrace_pct
        out.append(ImpulseLegBar(ok, leg_high, leg_origin_low, leg_dollars, retrace))
    return out


# =====================================================================================
# Selectivity qualifiers
# =====================================================================================
def prior_same_day_touch_ok(
    rth_day_bars: pd.DataFrame, level_price: float, before_idx: int,
    tol: float = LEVEL_MEMORY_TOUCH_TOL,
) -> bool:
    """True iff some bar STRICTLY before `before_idx` (same day, day-local index) had its
    high or low come within `tol` of `level_price` -- i.e. the level was already
    battle-tested by the time this pullback candidate showed up. No look-ahead: only bars
    < before_idx are inspected."""
    highs = rth_day_bars["high"].astype(float).tolist()
    lows = rth_day_bars["low"].astype(float).tolist()
    for k in range(0, before_idx):
        if (lows[k] - tol) <= level_price <= (highs[k] + tol):
            return True
    return False


def leg_origin_match_ok(level_price: float, leg_origin_low: Optional[float], tol: float) -> bool:
    """True iff `level_price` coincides (within `tol`) with the SAME bar's own impulse-leg
    origin low -- i.e. the level being held above IS where the current leg launched from."""
    if leg_origin_low is None:
        return False
    return abs(level_price - leg_origin_low) <= tol


# =====================================================================================
# Main detector walk -- mirrors v1's detect_pullback_hold_bull structure exactly (same
# no-overlap-consumption / no-look-ahead contract), swapping in the impulse-leg
# up-structure gate and the selectivity-filtered level match. Confirmation (RSI-reset +
# green-close) is DROPPED in v2 -- not part of the frozen v2 grid axes (disclosed
# simplification, made to respect the <=36 cell cap; see the pre-reg).
# =====================================================================================
def detect_pullback_hold_bull_v2(
    day_bars: pd.DataFrame,
    *,
    up_structure_ok: Sequence[bool],
    leg_origin_lows: Sequence[Optional[float]],
    leg_highs: Sequence[Optional[float]],
    retrace_pcts: Sequence[Optional[float]],
    levels_at: Callable[[int], Sequence[float]],
    params: PullbackHoldV2Params,
    day_label: str,
) -> list[PullbackHoldSignalV2]:
    """Walk one day's RTH bars, oldest first. Returns entry signals in chronological order.

    One pullback-low candidate consumes bars [j, entry_bar_idx] -- the next candidate
    search resumes strictly after that (Rule 4: no adding without a NEW confirmed
    trigger -- a single continuation never spawns overlapping/duplicate signals).
    """
    n = len(day_bars)
    if n == 0:
        return []
    if len(up_structure_ok) != n:
        raise ValueError(f"up_structure_ok length {len(up_structure_ok)} != day_bars length {n}")

    lows = day_bars["low"].astype(float).tolist()
    closes = day_bars["close"].astype(float).tolist()
    ts_list = list(day_bars["timestamp_et"])

    signals: list[PullbackHoldSignalV2] = []
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
        band_candidates = [L for L in levels if abs(low_j - L) <= params.zone_band_cents]
        if not band_candidates:
            j += 1
            continue

        if params.selectivity_mode == "PRIOR_INTERACTION":
            candidates = [L for L in band_candidates
                          if prior_same_day_touch_ok(day_bars, L, j)]
        else:  # LEG_ORIGIN
            origin = leg_origin_lows[j]
            candidates = [L for L in band_candidates
                          if leg_origin_match_ok(L, origin, params.zone_band_cents)]

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

        signals.append(PullbackHoldSignalV2(
            day=day_label, pullback_bar_idx=j, pullback_ts=ts_list[j], pullback_low=low_j,
            level_price=level_price, zone_low=zone_low, zone_top=zone_top,
            entry_bar_idx=entry_idx, entry_ts=ts_list[entry_idx], entry_close=closes[entry_idx],
            bars_to_hold=entry_idx - j, impulse_leg_mode=params.impulse_leg_mode,
            selectivity_mode=params.selectivity_mode, leg_high=leg_highs[j],
            leg_origin_low=leg_origin_lows[j], retrace_pct=retrace_pcts[j],
        ))
        j = entry_idx + 1  # no new candidate search starts inside a just-consumed window

    return signals
