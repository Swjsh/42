"""PULLBACK-HOLD bull detector -- LANE A, SHADOW-ONLY, ZERO ENGINE WIRING.

Queue item `PULLBACK-HOLD-BULL-TRIGGER` (filed 2026-07-22 Fable review, HIGH, "THE bull-side
build"), re-opened 2026-09-03 for a forward-shadow validation path. See
`automation/overnight/queue.md` for the full root-cause writeup and the three exhibits this
module is checked against.

ROOT CAUSE (unchanged from the 07-22 filing): the engine's only high-conviction bull trigger,
ELITE `level_reclaim` (`backtest/lib/filters.py::detect_level_reclaim`), requires
`bar.low < level < bar.close` on the SAME bar -- by construction it can only confirm AFTER
price has already crossed back above the level, i.e. at-or-after the move. Two of J's own
verified exhibits (07-21 shelf+engulfing bull=9-10 with `triggers=[]` until the trigger finally
fired at the session top; 07-22 pullback low sitting 26c above a KNOWN level_memory level with
`triggers=[]` for 30+ minutes) show the late-trigger -> block_elite_bull tourniquet killing
real bull participation.

RELATION TO THE EXISTING (CLOSED) LANE-A/LANE-B WORK -- read before extending this file:
`backtest/lib/filters.py::detect_pullback_hold_bullish` is a DIFFERENT, already-shadow-logged
implementation of the same vocabulary, built 2026-07-22 and left in place (shadow-only, zero
live effect). Its own Lane-B validation (a 36-cell historical GRID replay through
`exit_manager_walk`, `analysis/recommendations/pullback-hold-bull-prereg-2026-07-22.json` /
`pullback-hold-bull-stage-summary-2026-07-22.md`) ran and closed
`status:CLOSED-LANE-B-NO-CELL-SHIPS` -- an HONEST NULL: 0/36 cells cleared both of J's named
exhibits as sanity anchors (the up-structure confirmation layer used in that grid was itself too
laggy to see J's own earliest read), and 0/36 cleared BH-FDR. `filters.py` is FROZEN for this
build (no edits), so this module is a WHOLLY INDEPENDENT, standalone detector -- not a copy
with tweaks, not an import of the frozen module's internals -- built to run a genuinely
different validation path: a forward-going SHADOW LEDGER (day-over-day EOD scans feeding
`analysis/recommendations/pullback-hold-shadow-ledger.jsonl`) rather than a one-shot historical
grid, plus two structural differences the closed grid never tested as qualifiers:
  1. Levels read from the `key-levels.json` SCHEMA (zone-per-level `zone_width`, when present)
     rather than a single global band constant.
  2. An explicit 15-minute-HTF-not-BEAR gate (reusing `orchestrator.py::_compute_htf_15m_stack`
     read-only, never mutated) as a qualifier layer.
This module makes NO promise the closed grid's null is wrong -- it exists to produce a second,
independently-gathered piece of evidence via a different (forward, not historical-grid)
methodology, per the pre-registered validation plan in
`analysis/recommendations/prereg-pullback-hold-bull-trigger-2026-09-03.md`.

CONTRACT: pure functions over bars + levels. Imported by NOTHING in the live/backtest engine
path (`heartbeat_core.py`, `filters.py`, `orchestrator.py`'s live dispatch, `strategies.py`,
`build_shared_signal.py` never import this module). Consumed only by
`setup/scripts/pullback_hold_shadow.py` (the nightly shadow scanner) and this module's own
tests.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Optional

import pandas as pd

# -- Frozen constants (do not hand-tune off any single exhibit -- C25) --------------------

# Zone band: doctrine default when a level carries no `zone_width` of its own (levels-are-zones,
# J 2026-07-17 -- a level is a band, never a penny-exact price). Matches the existing
# `CONFLUENCE_TOLERANCE_DOLLARS` / `PULLBACK_HOLD_ZONE_BAND_DOLLARS` precedent already used by
# `filters.py::detect_pullback_hold_bullish` and `double_bottom_base_quiet_watcher.py`'s
# `PROXIMITY_MAX_DISTANCE` family -- same order of magnitude, not hand-picked for this module.
PULLBACK_ZONE_BAND_DOLLARS_DEFAULT: float = 0.30

# K: minimum bars (inclusive of the pullback-low bar) that must sit with LOW inside the zone
# band before a reclaim can fire. Frozen per the task spec ("K frozen, e.g. 3").
PULLBACK_MIN_HOLD_BARS: int = 3

# How far back (in 5-min bars) to search for the pullback low. 12 bars = 1 hour, matching the
# existing filters.py PULLBACK_HOLD_LOOKBACK_BARS precedent.
PULLBACK_LOOKBACK_BARS: int = 12

# RTH scan window -- avoid premarket/AH noise; matches the engine's own 09:35 ET entry gate on
# the open side, extended slightly earlier (09:30) so bars are available to seed the lookback.
RTH_SCAN_START: dt.time = dt.time(9, 30)
RTH_SCAN_END: dt.time = dt.time(15, 55)


@dataclass(frozen=True)
class PullbackHoldFire:
    """One confirmed PULLBACK-HOLD bull fire."""

    ts: str                 # bar's timestamp_et, ISO string
    level: float             # the defended level (band center)
    band: float              # the zone_band_dollars actually used for this level
    k_bars: int               # number of hold bars actually observed (>= min_hold_bars)
    trigger_close: float      # the close that confirmed the reclaim
    htf_state: str            # '15m ribbon stack at trigger bar: BULL | BEAR | MIXED | UNKNOWN'

    def as_dict(self) -> dict:
        return {
            "ts": self.ts,
            "level": self.level,
            "band": self.band,
            "k_bars": self.k_bars,
            "trigger_close": self.trigger_close,
            "htf_state": self.htf_state,
        }


def _level_band(level_entry: float | dict, default_band: float) -> tuple[float, float]:
    """Return (price, band) for a level, which may be a bare float or a
    key-levels.json-shaped dict carrying its own `zone_width`."""
    if isinstance(level_entry, dict):
        price = float(level_entry["price"])
        zone_width = level_entry.get("zone_width")
        band = float(zone_width) if zone_width else default_band
        return price, band
    return float(level_entry), default_band


def detect_pullback_hold(
    bars: pd.DataFrame,
    bar_idx: int,
    levels: list,
    htf_stack: Optional[str] = None,
    zone_band_dollars: float = PULLBACK_ZONE_BAND_DOLLARS_DEFAULT,
    min_hold_bars: int = PULLBACK_MIN_HOLD_BARS,
    lookback_bars: int = PULLBACK_LOOKBACK_BARS,
) -> Optional[PullbackHoldFire]:
    """PULLBACK-HOLD bull trigger, evaluated at `bar_idx` (closed bars only -- C6 no-look-ahead:
    `bars` must contain nothing beyond `bar_idx`, or callers must slice to `bar_idx + 1` first).

    Geometry:
      1. Scan the approach window `[bar_idx - lookback_bars .. bar_idx - min_hold_bars]` for the
         bar whose LOW falls inside some level's zone band `[price - band, price + band]`. Among
         all such bars, pick the one with the LOWEST low (the true bottom of the dip, not merely
         the tightest touch -- a still-descending bar can be closer to the level without yet
         being the actual pullback low).
      2. HOLD check: every bar from that low bar through `bar_idx - 1` (inclusive) must have its
         LOW inside `[price - band, price + band]` -- price must have SAT in the zone, not merely
         touched it once and drifted away. A bar whose low exits the band on EITHER side breaks
         the hold (task spec: "holds it ... with lows inside the band").  Requires
         `>= min_hold_bars` such bars.
      3. RECLAIM check: `bars.iloc[bar_idx]` must CLOSE strictly above `price + band` (back above
         the zone ceiling) AND above the highest close seen during the hold window (confirms the
         reclaim broke the hold's own minor structure, not just the zone edge).
      4. HTF check: `htf_stack` (the 15-min ribbon stack visible at `bar_idx`, or None/unknown)
         must NOT be 'BEAR'. None/'UNKNOWN' passes (insufficient warmup is not evidence of BEAR).

    Returns a `PullbackHoldFire` on confirmation, else None.
    """
    if bar_idx < min_hold_bars or not levels:
        return None

    htf_ok = htf_stack != "BEAR"
    if not htf_ok:
        return None

    approach_start = max(0, bar_idx - lookback_bars)
    approach_end = bar_idx - min_hold_bars
    if approach_end < approach_start:
        return None

    best_price: Optional[float] = None
    best_band: Optional[float] = None
    best_low_idx: Optional[int] = None
    best_low_value: Optional[float] = None

    for i in range(approach_start, approach_end + 1):
        low_i = float(bars.iloc[i]["low"])
        for level_entry in levels:
            price, band = _level_band(level_entry, zone_band_dollars)
            if abs(low_i - price) > band:
                continue
            if best_low_value is None or low_i < best_low_value:
                best_low_value = low_i
                best_low_idx = i
                best_price = price
                best_band = band

    if best_price is None or best_low_idx is None or best_band is None:
        return None

    zone_lo = best_price - best_band
    zone_hi = best_price + best_band

    hold_indices = list(range(best_low_idx, bar_idx))  # low bar .. bar_idx-1 inclusive
    if len(hold_indices) < min_hold_bars:
        return None

    highest_hold_close = float("-inf")
    for i in hold_indices:
        low_i = float(bars.iloc[i]["low"])
        if low_i < zone_lo or low_i > zone_hi:
            return None  # left the band during the hold -- pattern invalidated
        close_i = float(bars.iloc[i]["close"])
        highest_hold_close = max(highest_hold_close, close_i)

    current_close = float(bars.iloc[bar_idx]["close"])
    if current_close <= zone_hi or current_close <= highest_hold_close:
        return None

    ts_val = bars.iloc[bar_idx].get("timestamp_et", bars.iloc[bar_idx].name)
    ts_str = str(ts_val)

    return PullbackHoldFire(
        ts=ts_str,
        level=round(best_price, 2),
        band=round(best_band, 2),
        k_bars=len(hold_indices),
        trigger_close=round(current_close, 2),
        htf_state=htf_stack if htf_stack else "UNKNOWN",
    )


def scan_session(
    bars: pd.DataFrame,
    levels_at: dict[int, list] | list,
    htf_stacks: Optional[list[Optional[str]]] = None,
    zone_band_dollars: float = PULLBACK_ZONE_BAND_DOLLARS_DEFAULT,
    min_hold_bars: int = PULLBACK_MIN_HOLD_BARS,
    lookback_bars: int = PULLBACK_LOOKBACK_BARS,
    rth_only: bool = True,
) -> list[PullbackHoldFire]:
    """Scan every closed bar in `bars` (a single-session, ascending-time 5-min OHLC frame with a
    `timestamp_et` column) for PULLBACK-HOLD fires.

    `levels_at` is either:
      - a single list of levels (bare floats or key-levels.json-shaped dicts) applied to the
        whole session, or
      - a dict mapping bar_idx -> list of levels active AT that bar (for callers that have
        per-tick levels_active from a decisions ledger).

    `htf_stacks[i]` (if given) is the 15-min ribbon stack visible at bar i; None/omitted means
    the HTF gate always passes (treated as UNKNOWN, not BEAR).

    Returns fires in bar order. Does not de-duplicate across overlapping windows by design --
    callers wanting one-fire-per-level-per-session should post-filter.
    """
    fires: list[PullbackHoldFire] = []
    n = len(bars)
    for idx in range(n):
        if rth_only:
            ts_val = bars.iloc[idx].get("timestamp_et")
            if ts_val is not None:
                ts = pd.Timestamp(ts_val)
                bar_time = ts.time()
                if bar_time < RTH_SCAN_START or bar_time > RTH_SCAN_END:
                    continue

        if isinstance(levels_at, dict):
            levels = levels_at.get(idx) or []
        else:
            levels = levels_at

        htf = htf_stacks[idx] if htf_stacks is not None and idx < len(htf_stacks) else None

        fire = detect_pullback_hold(
            bars,
            idx,
            levels,
            htf_stack=htf,
            zone_band_dollars=zone_band_dollars,
            min_hold_bars=min_hold_bars,
            lookback_bars=lookback_bars,
        )
        if fire is not None:
            fires.append(fire)

    return fires
