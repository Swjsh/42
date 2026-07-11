"""crypto_twin_levels -- UTC-day session-anchor level set for the crypto twin.

The 1:1 mapping (per markdown/planning/CRYPTO-TWIN-TRAINING-GROUND.md): SPY's PDH/PDL
(prior RTH day's high/low) + today's intraday H/L becomes, for a 24/7 instrument,
prior-UTC-day H/L/C + intraday(today-UTC-so-far) H/L. "Session" = the UTC calendar day.

This is NEW code, not a fork: crypto.lib.levels.prior_period_levels() takes a bar-COUNT
lookback (N most recent closed bars), not a calendar-day boundary -- there is no existing
UTC-day-boundary primitive to reuse. crypto.lib.session_levels_spy.py is the closest
precedent (same technique -- filter bars by a date boundary, take H/L/C of the slice --
applied to SPY's RTH clock instead of a UTC calendar day) and this module deliberately
mirrors its shape/idioms rather than inventing a new style.

Uses crypto.lib.bar.Bar + crypto.lib.levels.Level/LevelKind/classify_bar_at_level for the
value types and reaction classification -- REUSE per HARD RAILS ("the ribbon/level/
structure detectors -- bars are bars").
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Sequence

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from crypto.lib.bar import Bar  # noqa: E402
from crypto.lib.levels import Level, LevelEvent, LevelKind, classify_bar_at_level  # noqa: E402


def utc_day_bounds(dt: datetime) -> tuple[datetime, datetime]:
    """[start, end) of dt's UTC calendar day, both tz-aware UTC midnights."""
    if dt.tzinfo is None:
        raise ValueError("dt must be tz-aware")
    dt_utc = dt.astimezone(timezone.utc)
    start = dt_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def _bars_in_range(bars: Sequence[Bar], start: datetime, end: datetime) -> list[Bar]:
    return [b for b in bars if start <= b.open_time < end]


@dataclass(frozen=True, slots=True)
class TwinLevelSet:
    """The twin's full level set for one tick, plus provenance for the decision row."""
    prior_day_high: Optional[Level]
    prior_day_low: Optional[Level]
    prior_day_close: Optional[Level]
    intraday_high: Optional[Level]
    intraday_low: Optional[Level]
    session_date_utc: str  # the "today" UTC date these intraday levels belong to

    @property
    def all_levels(self) -> list[Level]:
        return [lv for lv in (self.prior_day_high, self.prior_day_low, self.prior_day_close,
                              self.intraday_high, self.intraday_low) if lv is not None]


def build_level_set(bars: Sequence[Bar], now_utc: datetime) -> TwinLevelSet:
    """prior-UTC-day H/L/C (★★★, mirrors SPY's PDH/PDL/PDC prominence) + intraday
    (today-UTC-so-far) H/L (★★, still forming -- matches session_levels_spy's "today's RTH
    high/low so far" tier). Bars strictly before `now_utc`'s UTC day boundary are "prior";
    ONLY bars up to now_utc contribute to "intraday" -- no look-ahead (C6 sibling guarantee:
    a level built from a bar that hasn't happened yet is exactly the in-progress-bar
    foot-gun one level up the stack, so callers MUST pass closed-bars-only, see
    crypto_twin_core._closed_bars).
    """
    today_start, today_end = utc_day_bounds(now_utc)
    prior_start = today_start - timedelta(days=1)
    prior_bars = _bars_in_range(bars, prior_start, today_start)
    intraday_bars = [b for b in _bars_in_range(bars, today_start, today_end) if b.open_time < now_utc]

    pdh = pdl = pdc = None
    if prior_bars:
        pdh = Level(price=round(max(b.high for b in prior_bars), 2),
                   kind=LevelKind.PRIOR_PERIOD_HIGH, strength=3, label="Prior-UTC-day H")
        pdl = Level(price=round(min(b.low for b in prior_bars), 2),
                   kind=LevelKind.PRIOR_PERIOD_LOW, strength=3, label="Prior-UTC-day L")
        pdc = Level(price=round(prior_bars[-1].close, 2),
                   kind=LevelKind.PIVOT_P, strength=2, label="Prior-UTC-day C")

    ih = il = None
    if intraday_bars:
        ih = Level(price=round(max(b.high for b in intraday_bars), 2),
                  kind=LevelKind.PRIOR_PERIOD_HIGH, strength=2, label="Intraday H (forming)")
        il = Level(price=round(min(b.low for b in intraday_bars), 2),
                  kind=LevelKind.PRIOR_PERIOD_LOW, strength=2, label="Intraday L (forming)")

    return TwinLevelSet(prior_day_high=pdh, prior_day_low=pdl, prior_day_close=pdc,
                        intraday_high=ih, intraday_low=il,
                        session_date_utc=today_start.strftime("%Y-%m-%d"))


def nearest_directional_level(levels: Sequence[Level], spot: float, side: str,
                              max_distance_pct: float = 0.5) -> Optional[Level]:
    """The level nearest `spot`, directionally filtered by `side` (mirrors
    exit_manager.nearest_active_level's directional-filter correctness guard, ported to a
    %-of-price distance since BTC's price scale varies wildly from SPY's):

    side="bear" (short/PUT analog) only considers levels AT/ABOVE spot (resistance just
    rejected); side="bull" (long/CALL analog) only considers levels AT/BELOW spot (support
    just reclaimed). max_distance_pct is a % of spot, not a fixed dollar radius (SPY's
    exit_manager uses a fixed $2.00 -- meaningless once spot could be $20k or $120k BTC).
    """
    if side not in ("bull", "bear") or not levels:
        return None
    max_dist = spot * (max_distance_pct / 100.0)
    best: Optional[Level] = None
    best_dist: Optional[float] = None
    for lv in levels:
        if side == "bear" and lv.price < spot:
            continue
        if side == "bull" and lv.price > spot:
            continue
        dist = abs(lv.price - spot)
        if dist <= max_dist and (best_dist is None or dist < best_dist):
            best, best_dist = lv, dist
    return best


def classify_reactions(bar: Bar, levels: Sequence[Level],
                       min_margin_pct: float = 0.05) -> dict[float, LevelEvent]:
    """{level_price: LevelEvent} for how the CLOSED trigger bar interacted with each level.
    Thin fan-out over crypto.lib.levels.classify_bar_at_level -- no new classification logic."""
    return {lv.price: classify_bar_at_level(bar, lv, min_margin_pct=min_margin_pct) for lv in levels}
