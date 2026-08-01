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
from crypto.lib.levels import (  # noqa: E402
    Level, LevelEvent, LevelKind, classify_bar_at_level, round_number_levels,
)
from crypto.lib.trendlines import find_swing_points  # noqa: E402


def utc_day_bounds(dt: datetime) -> tuple[datetime, datetime]:
    """[start, end) of dt's UTC calendar day, both tz-aware UTC midnights."""
    if dt.tzinfo is None:
        raise ValueError("dt must be tz-aware")
    dt_utc = dt.astimezone(timezone.utc)
    start = dt_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def _bars_in_range(bars: Sequence[Bar], start: datetime, end: datetime) -> list[Bar]:
    return [b for b in bars if start <= b.open_time < end]


# --- STARVATION FIX (2026-08-01, J drill: "Gamma doesn't have enough experience pulling
# the trigger") -----------------------------------------------------------------------
# Diagnosis (real live tick, 2026-08-01 11:48-12:09 ET): ribbon BEAR-stacked, HOLD "no
# level in range for the current ribbon stack" -- sig.evaluate()'s nearest_directional_level
# only searches within max_distance_pct=0.5% of spot (~$315 at BTC $63k), and the ONLY
# candidates were the original 5 UTC-day levels (PDH/PDL/PDC + intraday H/L). Three
# additional, legitimate crypto level families below widen the candidate set WITHOUT
# touching entry TRIGGER logic itself (classify_bar_at_level / nearest_directional_level
# / sig.evaluate are all unchanged) or EXIT logic (exit_manager/risk_gate untouched) --
# this only gives the SAME trigger search more real candidates to find.
#
#   1. Session H/L (Asia/Europe/US) -- a DELIBERATE SIMPLIFICATION, not the real
#      (overlapping) forex session convention: 3 clean, non-overlapping 8h UTC blocks
#      (00-08/08-16/16-24). These are candidate S/R levels for a 24/7 spot instrument,
#      not a forex-session claim -- precision here doesn't matter, having a few more
#      plausible reaction levels does. Mirrors build_level_set's own "most recently
#      COMPLETED period" discipline (never the currently-forming session).
#   2. Round numbers -- crypto.lib.levels.round_number_levels reused verbatim (already
#      built for exactly this, just never wired into the twin). $500 grid per J's spec.
#   3. Prior-swing H/L -- crypto.lib.trendlines.find_swing_points reused verbatim (the
#      same swing primitive market_structure.py is built on) for the single most recent
#      swing high + swing low, no look-ahead (bars strictly before now_utc only, same C6
#      discipline as intraday_bars below).
#
# Every new level carries a distinct `label` (provenance) -- crypto_twin_core._decision_row
# folds levels.all_levels into a new `levels_active` decision-row field so HOLD-reason
# shifts are auditable per tick, not just inferred from an eventual ENTER.
SESSION_WINDOWS_UTC: tuple[tuple[str, int, int], ...] = (
    ("asia", 0, 8),
    ("europe", 8, 16),
    ("us", 16, 24),
)
ROUND_NUMBER_INCREMENT_USD = 500.0   # J's spec: "$500 grid for BTC"
ROUND_NUMBER_RADIUS = 3              # +/- 3 increments = +/- $1500 candidate band
SWING_WINDOW_BARS = 3                # find_swing_points' bars-per-side fractal (matches
                                      # market_structure.DEFAULT_WINDOW's sibling default)


def _session_bounds_utc(now_utc: datetime, start_hour: int, end_hour: int) -> tuple[datetime, datetime]:
    """[start, end) of the most recently COMPLETED occurrence of a fixed UTC window
    [start_hour, end_hour) relative to now_utc -- today's if it has already fully
    elapsed, else yesterday's (mirrors build_level_set's prior-period discipline: only a
    CLOSED session counts, never the one still forming)."""
    day_start, _ = utc_day_bounds(now_utc)
    start = day_start + timedelta(hours=start_hour)
    end = day_start + timedelta(hours=end_hour)
    if end <= now_utc:
        return start, end
    return start - timedelta(days=1), end - timedelta(days=1)


def _session_levels(bars: Sequence[Bar], now_utc: datetime) -> dict[str, tuple[Optional[Level], Optional[Level]]]:
    """{session_name: (high_level, low_level)} for each of SESSION_WINDOWS_UTC's most
    recently completed occurrence. (None, None) when no bars fall in that window."""
    out: dict[str, tuple[Optional[Level], Optional[Level]]] = {}
    for name, start_h, end_h in SESSION_WINDOWS_UTC:
        start, end = _session_bounds_utc(now_utc, start_h, end_h)
        window_bars = _bars_in_range(bars, start, end)
        if not window_bars:
            out[name] = (None, None)
            continue
        hi = Level(price=round(max(b.high for b in window_bars), 2),
                  kind=LevelKind.PRIOR_PERIOD_HIGH, strength=2, label=f"{name.title()} session H")
        lo = Level(price=round(min(b.low for b in window_bars), 2),
                  kind=LevelKind.PRIOR_PERIOD_LOW, strength=2, label=f"{name.title()} session L")
        out[name] = (hi, lo)
    return out


def _swing_levels(eligible_bars: Sequence[Bar]) -> tuple[Optional[Level], Optional[Level]]:
    """Most recent swing-high / swing-low Level from find_swing_points (no look-ahead --
    caller passes bars already filtered to open_time < now_utc). None/None below the
    fractal's minimum bar count (2*window+1) rather than raising -- a quiet-history tick
    simply gets fewer candidate levels, never a crash."""
    if len(eligible_bars) < 2 * SWING_WINDOW_BARS + 1:
        return None, None
    swings = find_swing_points(eligible_bars, window=SWING_WINDOW_BARS)
    highs = [s for s in swings if s.kind == "swing_high"]
    lows = [s for s in swings if s.kind == "swing_low"]
    sh = sl = None
    if highs:
        last_h = max(highs, key=lambda s: s.bar_index)
        sh = Level(price=round(last_h.price, 2), kind=LevelKind.PRIOR_PERIOD_HIGH,
                  strength=2, label="Swing H")
    if lows:
        last_l = max(lows, key=lambda s: s.bar_index)
        sl = Level(price=round(last_l.price, 2), kind=LevelKind.PRIOR_PERIOD_LOW,
                  strength=2, label="Swing L")
    return sh, sl


@dataclass(frozen=True, slots=True)
class TwinLevelSet:
    """The twin's full level set for one tick, plus provenance for the decision row."""
    prior_day_high: Optional[Level]
    prior_day_low: Optional[Level]
    prior_day_close: Optional[Level]
    intraday_high: Optional[Level]
    intraday_low: Optional[Level]
    session_date_utc: str  # the "today" UTC date these intraday levels belong to
    # STARVATION FIX (2026-08-01): additive level families, every field defaulted so
    # every pre-existing positional/keyword TwinLevelSet(...) call site (there are none
    # outside build_level_set itself, verified by repo-wide grep) stays valid.
    session_asia_high: Optional[Level] = None
    session_asia_low: Optional[Level] = None
    session_europe_high: Optional[Level] = None
    session_europe_low: Optional[Level] = None
    session_us_high: Optional[Level] = None
    session_us_low: Optional[Level] = None
    round_numbers: tuple[Level, ...] = ()
    swing_high: Optional[Level] = None
    swing_low: Optional[Level] = None

    @property
    def all_levels(self) -> list[Level]:
        singles = (self.prior_day_high, self.prior_day_low, self.prior_day_close,
                  self.intraday_high, self.intraday_low,
                  self.session_asia_high, self.session_asia_low,
                  self.session_europe_high, self.session_europe_low,
                  self.session_us_high, self.session_us_low,
                  self.swing_high, self.swing_low)
        return [lv for lv in singles if lv is not None] + list(self.round_numbers)


def build_level_set(bars: Sequence[Bar], now_utc: datetime) -> TwinLevelSet:
    """prior-UTC-day H/L/C (★★★, mirrors SPY's PDH/PDL/PDC prominence) + intraday
    (today-UTC-so-far) H/L (★★, still forming -- matches session_levels_spy's "today's RTH
    high/low so far" tier) + session H/L (Asia/Europe/US) + a $500 round-number grid +
    the most recent swing H/L (STARVATION FIX, 2026-08-01 -- see the block comment above
    TwinLevelSet for why). Bars strictly before `now_utc`'s UTC day boundary are "prior";
    ONLY bars up to now_utc contribute to "intraday" -- no look-ahead (C6 sibling guarantee:
    a level built from a bar that hasn't happened yet is exactly the in-progress-bar
    foot-gun one level up the stack, so callers MUST pass closed-bars-only, see
    crypto_twin_core._closed_bars). Every new family reuses this SAME no-look-ahead
    discipline (session windows are closed-only; round numbers anchor off the latest
    ELIGIBLE close; swings only ever see bars strictly before now_utc).
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

    sessions = _session_levels(bars, now_utc)

    # Round numbers anchor off the latest bar strictly before now_utc (intraday's own
    # closed-bar convention); falls back to the prior day's last close on a fresh UTC-day
    # rollover with no intraday bars yet, else empty (no crash on an empty warmup).
    spot_ref = intraday_bars[-1].close if intraday_bars else (prior_bars[-1].close if prior_bars else None)
    round_numbers = tuple(round_number_levels(spot_ref, ROUND_NUMBER_INCREMENT_USD,
                                              radius=ROUND_NUMBER_RADIUS)) if spot_ref else ()

    eligible_for_swings = sorted([b for b in bars if b.open_time < now_utc], key=lambda b: b.open_time)
    swing_high, swing_low = _swing_levels(eligible_for_swings)

    return TwinLevelSet(prior_day_high=pdh, prior_day_low=pdl, prior_day_close=pdc,
                        intraday_high=ih, intraday_low=il,
                        session_date_utc=today_start.strftime("%Y-%m-%d"),
                        session_asia_high=sessions["asia"][0], session_asia_low=sessions["asia"][1],
                        session_europe_high=sessions["europe"][0], session_europe_low=sessions["europe"][1],
                        session_us_high=sessions["us"][0], session_us_low=sessions["us"][1],
                        round_numbers=round_numbers, swing_high=swing_high, swing_low=swing_low)


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
