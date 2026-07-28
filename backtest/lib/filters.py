"""BEARISH_REJECTION_RIDE_THE_RIBBON — 10-filter setup checklist.

Numerical definitions are sourced from `markdown/0dte/chart-anatomy.md` Numerical definitions
section. Every soft adjective is bound to a number.

Filters (per `automation/prompts/heartbeat.md`):
  1.  time >= 09:35 ET
  2.  news clear (no current no_trade_window — backtest assumes clear; macro-calendar.json
        could be wired in later)
  3.  budget > risk (always true in backtest)
  4.  day-trades >= 1 (always true in backtest)
  5.  ribbon BEAR-stacked (Fast < Pivot < Slow)
  6.  spread >= 30 cents
  7.  NOT volume_divergence_failed
  8.  VIX > 17.30 AND vix_rising
  9.  breakdown_bar_bearish on last closed bar
  10. htf_15m_alignment AND >= 2 of 3 triggers
        (level reject / ribbon flip / multi-day-trendline confluence)
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from .ribbon import RibbonState
from .structure_shift import (
    STRUCTURE_SHIFT_K_DEFAULT,
    detect_structure_shift_bear,
    detect_structure_shift_bull,
)


# Thresholds — pulled from playbook / chart-anatomy / params.
NEWS_FILTER_GRACE_MIN = 15
RIBBON_SPREAD_MIN_CENTS = 30
VIX_BEAR_THRESHOLD = 17.30
VIX_RISING_DEADBAND = 0.05
VIX_HARD_CAP_BEAR = 999.0   # L114: block BEAR entries when VIX > this (panic extremes). Default=999=off.
VIX_DECLINING_REQUIRED_BEAR = False  # L115: require multi-day VIX declining (vix_now < vix_5d_ma) for BEAR entries.
                                     # Default=False (backward compatible). Targets Apr-26 tariff-shock (escalating VIX).
                                     # Test per L93: "if a VIX gate is needed, test DECLINING direction only."
VOL_BASELINE_BARS = 20
RANGE_BASELINE_BARS = 20
RIBBON_FLIP_LOOKBACK_BARS = 3
CONFLUENCE_TOLERANCE_DOLLARS = 0.30   # multi-day touch within ±$0.30 of today's tested level
TRENDLINE_LOOKBACK_BARS = 60          # bars to look back for descending pivots (60 × 5 min = 5 hours)
TRENDLINE_MIN_SWINGS = 3              # minimum descending pivots required (3 = real trendline, not noise)
WICK_MIN_PCT_OF_RANGE = 0.50         # upper wick must be ≥ 50% of bar range for wick_rejection trigger
WICK_MIN_DOLLARS = 0.15              # upper wick must be ≥ $0.15 for wick_rejection trigger
WICK_CLOSE_TOLERANCE = 0.10          # close can be up to $0.10 above level (wick-rejection leniency)

# PULLBACK_HOLD_ZONE_BAND_DOLLARS: levels-are-zones doctrine (J 2026-07-17) — a level is a
# BAND, not a penny-exact price. Pre-registered at the same $0.30 width already used for
# CONFLUENCE_TOLERANCE_DOLLARS (an existing, already-doctrine-sanctioned band width) rather
# than hand-picked for this detector specifically (C25/no-hand-tuning discipline).
PULLBACK_HOLD_ZONE_BAND_DOLLARS = 0.30
PULLBACK_HOLD_MIN_HOLD_BARS = 2       # bars (incl. the pullback-low bar) that must defend the zone before reclaim
PULLBACK_HOLD_LOOKBACK_BARS = 12      # how far back to search for the pullback low (12 × 5 min = 1 hour)


@dataclass
class LevelState:
    """Per-level state across bars (NEW 2026-05-07 — syncs heartbeat key-levels.json schema).

    Tracks role + bounce_history so the backtest can detect the sequence_rejection
    pattern (3+ progressively-lower-highs at a broken level).
    """
    price: float
    role: Optional[str] = None  # None | "broken_to_resistance" | "broken_to_support"
    broken_at_bar_idx: Optional[int] = None
    bounce_history: list = field(default_factory=list)  # [{"bar_idx", "high_reached"|"low_reached"}]


@dataclass
class BarContext:
    """Everything needed to evaluate the bearish setup at a single bar.

    The bar at `bar_idx` is the candidate "trigger bar" — the bar that just closed.
    All filters reference data up to and including this bar; nothing forward.
    """
    bar_idx: int
    timestamp_et: dt.datetime
    bar: pd.Series                    # OHLCV row for the trigger bar
    prior_bars: pd.DataFrame          # full history, indexed by bar position, including the trigger bar
    ribbon_now: Optional[RibbonState]
    ribbon_history: list              # list[RibbonState | None] — stacks of last RIBBON_FLIP_LOOKBACK_BARS+1 bars
    vix_now: float
    vix_prior: float                  # vix value at prior bar (for direction)
    vol_baseline_20: float
    range_baseline_20: float
    levels_active: list[float]        # support/resistance levels (prior day H/L, swings, etc.)
    multi_day_levels: list[float]     # subset of levels that are multi-day (>= 1 day old)
    htf_15m_stack: Optional[str]      # "BULL" | "BEAR" | "MIXED" | None (insufficient data)
    level_states: dict = field(default_factory=dict)  # price (str) -> LevelState — for sequence_rejection lookup
    fhh_level: Optional[float] = None   # rank 27: first-hour-high supplement (separate trigger path)
    vix_5d_ma: float = 0.0              # L115: rolling 5-day VIX daily-close average (prior days only, no look-ahead)
    vix_20d_ma: float = 0.0             # L115: rolling 20-day VIX daily-close average (prior days only, no look-ahead)


@dataclass
class SetupResult:
    """Output of evaluate_bearish_setup."""
    passed: bool
    bear_score: int                   # 0..10 — number of filters that passed
    blockers: list[int] = field(default_factory=list)
    triggers_fired: list[str] = field(default_factory=list)
    rejection_level: Optional[float] = None
    ribbon_just_flipped_bearish: bool = False
    confluence_match: Optional[float] = None  # the multi-day level price if confluence detected


# ----- vix direction primitives -----

def vix_direction(now: float, prior: float) -> str:
    """rising | falling | flat — uses 0.05 deadband to suppress noise."""
    if now > prior + VIX_RISING_DEADBAND:
        return "rising"
    if now < prior - VIX_RISING_DEADBAND:
        return "falling"
    return "flat"


# ----- per-bar predicates (chart-anatomy numerical defs) -----

def vol_baseline_20bar(prior_bars: pd.DataFrame, idx: int) -> float:
    """20-bar SMA of volume immediately preceding bar `idx` (does NOT include bar idx)."""
    if idx < VOL_BASELINE_BARS:
        return float(prior_bars["volume"].iloc[:idx].mean()) if idx > 0 else 0.0
    return float(prior_bars["volume"].iloc[idx - VOL_BASELINE_BARS:idx].mean())


def range_baseline_20bar(prior_bars: pd.DataFrame, idx: int) -> float:
    """20-bar SMA of (high - low) preceding bar `idx`."""
    if idx < RANGE_BASELINE_BARS:
        sub = prior_bars.iloc[:idx]
    else:
        sub = prior_bars.iloc[idx - RANGE_BASELINE_BARS:idx]
    if len(sub) == 0:
        return 0.0
    return float((sub["high"] - sub["low"]).mean())


def breakdown_bar_bearish(
    bar: pd.Series, fast_ema: float, vol_baseline: float, vol_mult: float = 1.3,
) -> bool:
    """Filter 9: seller pressure bar.

    RELAXED 2026-05-07 (synced from heartbeat.md): dropped `close<Fast EMA` and
    `body in lower 40%` sub-clauses. Prior strict version vetoed the 11:50/12:00
    textbook 735.40 rejection on 2026-05-07 because rejection bars closed near
    the level, not below Fast EMA, and had wicks.

    Selling pressure now defined simply as: red bar with above-average volume.

    `vol_mult` configurable (default 1.3x). Sniper-mode tests use 1.0x or 0.7x
    to catch J's morning rejection bars where the move hasn't started so volume
    hasn't spiked yet.

    Args:
        bar: pandas Series with open/high/low/close/volume.
        fast_ema: kept in signature for backwards compat — no longer consulted.
        vol_baseline: 20-bar SMA of volume.
        vol_mult: minimum volume multiplier (default 1.3x).
    """
    _ = fast_ema  # intentionally unused after relaxation
    if bar["close"] >= bar["open"]:
        return False  # not red
    if bar["volume"] < vol_mult * vol_baseline:
        return False  # below threshold
    return True


def _bar_geometry(bar: pd.Series) -> dict:
    """Compute body/wick percentages for a single bar.

    Returns {body_pct, upper_wick_pct, lower_wick_pct, is_red, is_green, range}.
    All percentages 0..1. range == 0 means flat bar (no wicks); all pcts return 0.
    """
    high = float(bar["high"])
    low = float(bar["low"])
    open_ = float(bar["open"])
    close = float(bar["close"])
    rng = high - low
    if rng <= 0:
        return {"body_pct": 0, "upper_wick_pct": 0, "lower_wick_pct": 0,
                "is_red": False, "is_green": False, "range": 0.0}
    body = abs(close - open_)
    upper_wick = high - max(open_, close)
    lower_wick = min(open_, close) - low
    return {
        "body_pct": body / rng,
        "upper_wick_pct": upper_wick / rng,
        "lower_wick_pct": lower_wick / rng,
        "is_red": close < open_,
        "is_green": close > open_,
        "range": rng,
    }


def is_doji(bar: pd.Series) -> bool:
    """Body < 10% of range — indecision."""
    g = _bar_geometry(bar)
    return g["range"] > 0 and g["body_pct"] < 0.10


def is_shooting_star(bar: pd.Series) -> bool:
    """Bearish reversal: red, long upper wick, small lower wick, small body.

    upper_wick >= 50%, lower_wick <= 20%, body <= 30%.
    """
    g = _bar_geometry(bar)
    return (
        g["is_red"]
        and g["upper_wick_pct"] >= 0.50
        and g["lower_wick_pct"] <= 0.20
        and g["body_pct"] <= 0.30
    )


def is_hammer(bar: pd.Series) -> bool:
    """Bullish reversal: green, long lower wick, small upper wick, small body."""
    g = _bar_geometry(bar)
    return (
        g["is_green"]
        and g["lower_wick_pct"] >= 0.50
        and g["upper_wick_pct"] <= 0.20
        and g["body_pct"] <= 0.30
    )


def is_bearish_marubozu(bar: pd.Series) -> bool:
    """Strong bearish continuation: red, body >= 75%, tiny wicks (<=10% each)."""
    g = _bar_geometry(bar)
    return (
        g["is_red"]
        and g["body_pct"] >= 0.75
        and g["upper_wick_pct"] <= 0.10
        and g["lower_wick_pct"] <= 0.10
    )


def is_bullish_marubozu(bar: pd.Series) -> bool:
    """Mirror of bearish_marubozu."""
    g = _bar_geometry(bar)
    return (
        g["is_green"]
        and g["body_pct"] >= 0.75
        and g["upper_wick_pct"] <= 0.10
        and g["lower_wick_pct"] <= 0.10
    )


def is_decisive_bar(bar: pd.Series, min_body_ratio: float = 0.50) -> bool:
    """Body-vs-wick ratio gate (T59 — optional HIGH-quality entry filter).

    Returns True if the bar's body is at least `min_body_ratio` of total bar range,
    indicating directional conviction. A bar with body=$0.10 / range=$0.60 has
    ratio ≈0.17 — indecisive wick-dominated; a bar with body=$0.40 / range=$0.50
    has ratio=0.80 — strong conviction.

    Doji bars (range=0) return False — no range means no directional information.
    Callers may invert (NOT is_decisive_bar) to explicitly REJECT wick-heavy bars.

    Args:
        bar: pandas Series with open/high/low/close.
        min_body_ratio: minimum body/range fraction (default 0.50).
    """
    g = _bar_geometry(bar)
    if g["range"] == 0:
        return False  # doji — no range, no conviction
    return g["body_pct"] >= min_body_ratio


def is_bearish_engulfing(bar_prev: pd.Series, bar_now: pd.Series) -> bool:
    """2-bar pattern: prev green, now red with body covering prev's body."""
    g_prev = _bar_geometry(bar_prev)
    g_now = _bar_geometry(bar_now)
    if not (g_prev["is_green"] and g_now["is_red"]):
        return False
    if g_now["body_pct"] < 0.50:
        return False
    return (
        float(bar_now["open"]) >= float(bar_prev["close"])
        and float(bar_now["close"]) <= float(bar_prev["open"])
    )


def is_bullish_engulfing(bar_prev: pd.Series, bar_now: pd.Series) -> bool:
    """Mirror: prev red, now green with body covering prev's body."""
    g_prev = _bar_geometry(bar_prev)
    g_now = _bar_geometry(bar_now)
    if not (g_prev["is_red"] and g_now["is_green"]):
        return False
    if g_now["body_pct"] < 0.50:
        return False
    return (
        float(bar_now["open"]) <= float(bar_prev["close"])
        and float(bar_now["close"]) >= float(bar_prev["open"])
    )


def detect_candlestick_pattern_bearish(
    bar: pd.Series,
    bar_prev: Optional[pd.Series],
    levels_active: list[float],
    bar_close_price: float,
    proximity: float = 0.30,
) -> Optional[str]:
    """Returns the name of the first bearish pattern that fires near a resistance level,
    or marubozu (which doesn't require level proximity since it's a strength signal).
    Returns None if no pattern.
    """
    # Marubozu is a continuation strength signal — no level proximity required
    if is_bearish_marubozu(bar):
        return "bearish_marubozu"

    # Shooting star + bearish engulfing require proximity to a resistance level
    near_resistance = any(abs(bar_close_price - L) <= proximity for L in levels_active)
    if not near_resistance:
        return None

    if is_shooting_star(bar):
        return "shooting_star"
    if bar_prev is not None and is_bearish_engulfing(bar_prev, bar):
        return "bearish_engulfing"
    return None


def detect_candlestick_pattern_bullish(
    bar: pd.Series,
    bar_prev: Optional[pd.Series],
    levels_active: list[float],
    bar_close_price: float,
    proximity: float = 0.30,
) -> Optional[str]:
    """Mirror of bearish version."""
    if is_bullish_marubozu(bar):
        return "bullish_marubozu"
    near_support = any(abs(bar_close_price - L) <= proximity for L in levels_active)
    if not near_support:
        return None
    if is_hammer(bar):
        return "hammer"
    if bar_prev is not None and is_bullish_engulfing(bar_prev, bar):
        return "bullish_engulfing"
    return None


def _detect_sweep_at_level(
    prior_bars: pd.DataFrame,
    bar_idx: int,
    level: float,
    direction: str,  # "bearish" (up-sweep → blocks bullish) or "bullish" (down-sweep → blocks bearish)
    min_wick_pct: float = 0.0003,         # 0.03% ≈ $0.22 on SPY @ $735
    min_close_back_pct: float = 0.0005,   # 0.05% ≈ $0.37 on SPY @ $735
    block_window_bars: int = 3,
    clean_prior_bars: int = 3,
) -> bool:
    """Check if a level was swept in the prior `block_window_bars` bars.

    BEARISH_SWEEP (up-sweep):
        bar.high > level + wick_threshold AND bar.close < level - close_threshold
        AND all `clean_prior_bars` bars before the sweep bar closed BELOW the level.
        → price was below level; one bar wicked above but closed back below.
        → blocks BULLISH reclaim at this level (5/14 09:58 ENTER_BULL misfire class).

    BULLISH_SWEEP (down-sweep):
        bar.low < level - wick_threshold AND bar.close > level + close_threshold
        AND all `clean_prior_bars` bars before the sweep bar closed ABOVE the level.
        → price was above level; one bar wicked below but closed back above.
        → blocks BEARISH rejection at this level (mirror foot-gun class).

    Mirrors crypto/lib/sweep.py detect_sweeps() logic.
    Candidate: strategy/candidates/2026-05-16-bearish-sweep-blocker.md
    """
    wick_threshold = level * min_wick_pct
    close_threshold = level * min_close_back_pct

    look_start = max(0, bar_idx - block_window_bars)
    look_end = bar_idx  # exclusive — don't check the current bar itself
    if look_start >= look_end:
        return False

    for sweep_i in range(look_start, look_end):
        sb = prior_bars.iloc[sweep_i]
        sb_h = float(sb["high"])
        sb_l = float(sb["low"])
        sb_c = float(sb["close"])

        if direction == "bearish":
            # Up-sweep: wick exceeded level from below; close fell back below
            if sb_h - level < wick_threshold:
                continue
            if level - sb_c < close_threshold:
                continue
            # clean_prior bars immediately before sweep_i all closed BELOW the level
            p_start = max(0, sweep_i - clean_prior_bars)
            p_end = sweep_i
            if p_end <= p_start:
                continue
            if not all(float(prior_bars.iloc[j]["close"]) < level for j in range(p_start, p_end)):
                continue
            return True  # bearish sweep found

        else:  # direction == "bullish"
            # Down-sweep: wick fell below level from above; close recovered above
            if level - sb_l < wick_threshold:
                continue
            if sb_c - level < close_threshold:
                continue
            # clean_prior bars immediately before sweep_i all closed ABOVE the level
            p_start = max(0, sweep_i - clean_prior_bars)
            p_end = sweep_i
            if p_end <= p_start:
                continue
            if not all(float(prior_bars.iloc[j]["close"]) > level for j in range(p_start, p_end)):
                continue
            return True  # bullish sweep found

    return False


# ----- Fair Value Gap (IRL) primitive — added 2026-06-14 for ERL->IRL adoption -----

@dataclass(frozen=True)
class FVG:
    """A Fair Value Gap (3-candle imbalance) — the IRL entry zone of an ERL->IRL setup.

    Bullish FVG completing at candle i:  low[i]  > high[i-2]   (up-displacement candle i-1).
    Bearish FVG completing at candle i:  high[i] < low[i-2]    (down-displacement candle i-1).
    The (gap_bottom, gap_top) band is the unfilled imbalance — price tends to retrace
    into it before continuing in the displacement direction.
    """
    direction: str        # "bullish" | "bearish"
    gap_bottom: float
    gap_top: float
    gap_size: float
    formed_at_idx: int    # index of the 3rd candle (i) that completes the gap


def detect_fvg(
    prior_bars: pd.DataFrame,
    idx: int,
    direction: str,
    min_gap_dollars: float = 0.10,
) -> Optional[FVG]:
    """Detect a 3-candle Fair Value Gap ending at bar `idx`.

    Uses candles (idx-2, idx-1, idx); idx-1 is the displacement candle. The gap is the
    non-overlap between candle idx-2 and candle idx:

        bullish:  gap = low[idx]   - high[idx-2]   (>0 => unfilled up-gap)
        bearish:  gap = low[idx-2] - high[idx]     (>0 => unfilled down-gap)

    Returns an FVG when gap >= `min_gap_dollars` (a displacement-strength filter), else
    None. Pure function of OHLC — no state, no look-ahead beyond `idx`.
    """
    if idx < 2 or idx >= len(prior_bars):
        return None
    c_first = prior_bars.iloc[idx - 2]
    c_third = prior_bars.iloc[idx]
    if direction == "bullish":
        gap = float(c_third["low"]) - float(c_first["high"])
        if gap >= min_gap_dollars:
            return FVG("bullish", float(c_first["high"]), float(c_third["low"]), gap, idx)
    elif direction == "bearish":
        gap = float(c_first["low"]) - float(c_third["high"])
        if gap >= min_gap_dollars:
            return FVG("bearish", float(c_third["high"]), float(c_first["low"]), gap, idx)
    return None


def detect_sequence_rejection(
    level_state: "Optional[LevelState]",
) -> bool:
    """Filter 10 sequence_rejection trigger (NEW 2026-05-07 — syncs heartbeat.md).

    Returns True if a level has bounce_history with >=3 entries where high_reached
    values are strictly decreasing AND the most recent retest closed below the level.
    Captures the lower-highs stairstep pattern (today's 736.12 → 735.61 → 735.41
    sequence at the broken 735.40 level).
    """
    if level_state is None:
        return False
    if level_state.role != "broken_to_resistance":
        return False
    history = level_state.bounce_history
    if len(history) < 3:
        return False
    # Last 3 entries strictly decreasing highs?
    last_three_highs = [e["high_reached"] for e in history[-3:]]
    return last_three_highs[0] > last_three_highs[1] > last_three_highs[2]


def detect_sequence_reclaim(
    level_state: "Optional[LevelState]",
) -> bool:
    """Mirror of sequence_rejection for BULLISH side: 3+ progressively HIGHER lows
    at a `broken_to_support` level."""
    if level_state is None:
        return False
    if level_state.role != "broken_to_support":
        return False
    history = level_state.bounce_history
    if len(history) < 3:
        return False
    last_three_lows = [e["low_reached"] for e in history[-3:]]
    return last_three_lows[0] < last_three_lows[1] < last_three_lows[2]


def volume_divergence_failed(prior_bars: pd.DataFrame, idx: int) -> bool:
    """Setup invalidated when a breakdown bar at idx-1 or idx-2 is followed within
    1-2 bars by a recovery bar that closes UP and has volume >= breakdown bar volume.

    Pattern (working backward from the trigger bar at idx):
      - breakdown at idx-1, recovery at idx                    (1-bar)
      - breakdown at idx-2, recovery at idx-1                  (1-bar)
      - breakdown at idx-2, recovery at idx                    (2-bar)
    """
    if idx < 2:  # need at least 3 bars total (idx-2, idx-1, idx)
        return False
    candidates = []  # (breakdown_idx, recovery_idx) pairs
    if idx - 1 >= 0:
        candidates.append((idx - 1, idx))
    if idx - 2 >= 0:
        candidates.append((idx - 2, idx - 1))
        candidates.append((idx - 2, idx))
    for bd_idx, rec_idx in candidates:
        bd = prior_bars.iloc[bd_idx]
        rec = prior_bars.iloc[rec_idx]
        if bd["close"] >= bd["open"]:
            continue  # breakdown candidate must be red
        if rec["close"] > rec["open"] and rec["volume"] >= bd["volume"]:
            return True
    return False


# ----- triggers -----

def detect_level_rejection(
    bar: pd.Series, levels_active: list[float]
) -> Optional[float]:
    """Returns the level that was rejected if bar.high > level AND bar.close < level.

    Picks the highest such level (most-rejected/most-relevant). Returns None if no rejection.

    No proximity guard: `high > level AND close < level` already implies the bar reached
    the level. Whether close pulled back $0.20 or $1.50 doesn't change "this was a rejection."
    """
    rejected = []
    for lvl in levels_active:
        if bar["high"] > lvl and bar["close"] < lvl:
            rejected.append(lvl)
    if not rejected:
        return None
    return max(rejected)


def detect_wick_rejection_bearish(
    bar: pd.Series,
    levels_active: list[float],
    min_wick_pct_of_range: float = 0.50,
    min_wick_dollars: float = 0.15,
    close_tolerance_above_level: float = 0.10,
) -> Optional[float]:
    """Detect a WICK rejection of an overhead level (J's 4/29 10:25 setup).

    Engine's `detect_level_rejection` requires close STRICTLY below level. J reads
    the chart and enters on a wick rejection even when close is slightly ABOVE
    the level (the bar pierced + pulled back, showing rejection in real time).

    Encodes J's 4/29 entry: bar O=711.37 H=711.65 L=711.34 C=711.48 with level
    711.40 -- bar pierced by 0.25 then closed 0.17 below the high, only 0.08
    above the level. Strict `close < level` misses this; wick analysis catches it.

    Trigger fires when:
      1. bar.high reaches the level (bar.high >= level - small fudge)
      2. upper wick is significant: (high - close) >= max(min_wick_dollars,
         min_wick_pct_of_range * range)
      3. close is within tolerance of the level (close <= level + tolerance)
         -- prevents firing on bars that pushed THROUGH the level

    Returns the rejected level price if all three conditions are met.
    """
    if not levels_active:
        return None
    high = float(bar["high"])
    low = float(bar["low"])
    close = float(bar["close"])
    bar_range = high - low
    if bar_range <= 0:
        return None
    upper_wick = high - close

    # Find the level being rejected: highest level whose price is below the bar's
    # high but within close-tolerance distance from the close.
    candidates = []
    for L in levels_active:
        if high < L:
            continue  # bar didn't reach the level
        if close > L + close_tolerance_above_level:
            continue  # bar pushed through, not rejected
        candidates.append(L)
    if not candidates:
        return None
    level = max(candidates)  # highest reached + rejected level

    # Confirm wick is significant
    wick_threshold = max(min_wick_dollars, min_wick_pct_of_range * bar_range)
    if upper_wick < wick_threshold:
        return None

    return float(round(level, 2))


def detect_trendline_rejection_bearish(
    bar: pd.Series,
    prior_bars: pd.DataFrame,
    bar_idx: int,
    lookback_bars: int = 60,
    min_swings: int = 3,
    proximity_pct: float = 0.0010,
    require_decreasing: bool = True,
) -> Optional[float]:
    """Detect rejection of a descending trendline (J's 5/1 setup).

    Encodes J's edge: when SPY tests a downward-sloping line connecting recent local
    highs and gets rejected, that's a bearish signal even without a horizontal level.

    Algorithm:
        1. Look back `lookback_bars` from current.
        2. Find local-high pivots (a bar's high > both neighbors).
        3. If we have >= `min_swings` pivots AND they're strictly decreasing,
           fit a line through the last 3 pivot highs (slope + intercept).
        4. Project to the current bar index → get expected trendline price.
        5. If current bar.high reaches the trendline (within proximity_pct of price)
           AND closes BELOW the trendline AND closes red → trigger fires.

    Args:
        bar: current 5m bar
        prior_bars: dataframe of bars before this one (for pivot finding)
        bar_idx: index of current bar in prior_bars (so we know "now")
        lookback_bars: how far back to scan for pivots (default 30 = 2.5 hours)
        min_swings: minimum pivots required (default 3 = real trendline, not noise)
        proximity_pct: how close bar.high must come to the line (0.0008 = 0.08% = ~58c on SPY 720)
        require_decreasing: if True, pivots must be strictly decreasing (descending trendline only)

    Returns the trendline price at current bar (a "level") if rejection fires, else None.
    Returning the price lets it integrate with the existing level-tied trigger logic.
    """
    if bar_idx < lookback_bars + 2:
        return None
    if prior_bars is None or len(prior_bars) < lookback_bars + 2:
        return None

    # Slice the lookback window (last `lookback_bars` bars before current bar)
    start = max(0, bar_idx - lookback_bars)
    window = prior_bars.iloc[start:bar_idx]
    if len(window) < min_swings * 5:  # need enough room for sequential peak search
        return None

    # SEQUENTIAL DESCENDING PEAKS algorithm (encoded for J's chart-reader pattern,
    # verified by tests/test_trendline_trigger.py per OP 17):
    # 1. Find the GLOBAL highest bar in the lookback window.
    # 2. Find the next-highest bar at least MIN_BAR_SEPARATION after that point.
    # 3. Repeat for `min_swings` pivots.
    # 4. If all pivots are strictly decreasing, fit a line through them.
    # The min-separation gap (10 bars = 50 min) prevents adjacent-bar noise pivots
    # (e.g., 5/1 had 10:20 peak with 10:25 right next to it -- without separation,
    # algorithm would pick 10:25 instead of the real next peak at 11:50).
    MIN_BAR_SEPARATION = 10
    highs = window["high"].values
    recent_pivots: list[tuple[int, float]] = []
    search_start = 0
    for _ in range(min_swings):
        if search_start >= len(highs):
            break
        sub_highs = highs[search_start:]
        if len(sub_highs) == 0:
            break
        rel_pos = int(sub_highs.argmax())
        pos = search_start + rel_pos
        val = float(highs[pos])
        if require_decreasing and recent_pivots and val >= recent_pivots[-1][1]:
            return None  # next selected peak isn't lower -- no descending trendline
        recent_pivots.append((pos, val))
        search_start = pos + MIN_BAR_SEPARATION

    if len(recent_pivots) < min_swings:
        return None

    # Fit a line through the recent pivots: y = slope * x + intercept
    # x = relative bar index (within window), y = high price
    n = len(recent_pivots)
    sum_x = sum(p[0] for p in recent_pivots)
    sum_y = sum(p[1] for p in recent_pivots)
    sum_xx = sum(p[0] * p[0] for p in recent_pivots)
    sum_xy = sum(p[0] * p[1] for p in recent_pivots)
    denom = n * sum_xx - sum_x * sum_x
    if denom == 0:
        return None
    slope = (n * sum_xy - sum_x * sum_y) / denom
    intercept = (sum_y - slope * sum_x) / n

    # For bearish trendline, slope must be negative (descending highs)
    if require_decreasing and slope >= 0:
        return None

    # Project line to the current bar's relative index in the window
    current_rel_idx = len(window)  # current bar is one past the window
    trendline_price = slope * current_rel_idx + intercept

    # Trendline must still be above current spot (otherwise it's irrelevant)
    if trendline_price <= float(bar["close"]):
        return None

    # Rejection criteria:
    # 1. bar.high reached or exceeded trendline (within proximity)
    # 2. bar closes below the trendline
    # 3. bar is RED (close < open) — confirms the rejection
    proximity_dollars = trendline_price * proximity_pct
    reached_line = float(bar["high"]) >= (trendline_price - proximity_dollars)
    closed_below = float(bar["close"]) < trendline_price
    is_red = float(bar["close"]) < float(bar["open"])

    if reached_line and closed_below and is_red:
        return float(round(trendline_price, 2))
    return None


def detect_ribbon_flip_bearish(ribbon_history: list) -> bool:
    """True if the ribbon stack transitioned to BEAR within the last `RIBBON_FLIP_LOOKBACK_BARS`.

    "Flip" = previously not BEAR (was BULL or MIXED), now BEAR.
    """
    if len(ribbon_history) < 2:
        return False
    current = ribbon_history[-1]
    if current is None or current.stack != "BEAR":
        return False
    # Check if any of the prior LOOKBACK bars was non-BEAR
    look = ribbon_history[max(0, len(ribbon_history) - RIBBON_FLIP_LOOKBACK_BARS - 1):-1]
    for prior_state in look:
        if prior_state is not None and prior_state.stack != "BEAR":
            return True
    return False


def detect_confluence(
    rejection_level: Optional[float], multi_day_levels: list[float]
) -> Optional[float]:
    """True if the rejected level was also tested in prior days (multi-day trendline proxy).

    Returns the matching multi-day level if confluence detected, else None.
    """
    if rejection_level is None:
        return None
    for lvl in multi_day_levels:
        if abs(lvl - rejection_level) <= CONFLUENCE_TOLERANCE_DOLLARS:
            return lvl
    return None


# ----- BULLISH primitives (mirrors of bearish) -----

def detect_level_reclaim(
    bar: pd.Series, levels_active: list[float]
) -> Optional[float]:
    """Bullish mirror of detect_level_rejection.

    Returns the level that was reclaimed if bar.low < level AND bar.close > level.
    Picks the lowest such level (most-reclaimed). Returns None if no reclaim.
    """
    reclaimed = []
    for lvl in levels_active:
        if bar["low"] < lvl and bar["close"] > lvl:
            reclaimed.append(lvl)
    if not reclaimed:
        return None
    return min(reclaimed)


def detect_ribbon_flip_bullish(ribbon_history: list) -> bool:
    """True if the ribbon stack transitioned to BULL within the last `RIBBON_FLIP_LOOKBACK_BARS`.

    Mirror of detect_ribbon_flip_bearish.
    """
    if len(ribbon_history) < 2:
        return False
    current = ribbon_history[-1]
    if current is None or current.stack != "BULL":
        return False
    look = ribbon_history[max(0, len(ribbon_history) - RIBBON_FLIP_LOOKBACK_BARS - 1):-1]
    for prior_state in look:
        if prior_state is not None and prior_state.stack != "BULL":
            return True
    return False


def detect_wick_reclaim_bullish(
    bar: pd.Series,
    levels_active: list[float],
    min_wick_pct_of_range: float = 0.50,
    min_wick_dollars: float = 0.15,
    close_tolerance_below_level: float = 0.10,
) -> Optional[float]:
    """Detect a WICK reclaim of an underlying support level. Bull mirror of
    detect_wick_rejection_bearish -- SHADOW-LOGGED only (see evaluate_bullish_setup's
    `shadow_triggers_fired`; NOT wired into `triggers`/scoring, 2026-07-15 fix-ship task).

    Engine's `detect_level_reclaim` requires close STRICTLY above level. This mirrors
    J's 4/29 10:25 wick-rejection pattern (which a strict close-below-level check
    missed) for the bull side: a bar that pierces BELOW a support level intrabar but
    closes back up near/above it, even when close is technically still slightly below
    the level, with a significant LOWER wick showing buyers defended the level in
    real time.

    Trigger fires when:
      1. bar.low reaches the level (bar.low <= level)
      2. lower wick is significant: (close - low) >= max(min_wick_dollars,
         min_wick_pct_of_range * range)
      3. close is within tolerance of the level (close >= level - tolerance)
         -- prevents firing on bars that pushed THROUGH the level to the downside

    Returns the reclaimed level price if all three conditions are met, else None.
    """
    if not levels_active:
        return None
    high = float(bar["high"])
    low = float(bar["low"])
    close = float(bar["close"])
    bar_range = high - low
    if bar_range <= 0:
        return None
    lower_wick = close - low

    # Find the level being reclaimed: lowest level whose price is above the bar's
    # low but within close-tolerance distance from the close. Mirror of the bear
    # version's "highest reached + rejected level" (max) -- here the nearest support
    # actually defended is the LOWEST reached candidate, not the highest.
    candidates = []
    for L in levels_active:
        if low > L:
            continue  # bar didn't reach the level
        if close < L - close_tolerance_below_level:
            continue  # bar pushed through, not reclaimed
        candidates.append(L)
    if not candidates:
        return None
    level = min(candidates)  # lowest reached + reclaimed level

    # Confirm wick is significant
    wick_threshold = max(min_wick_dollars, min_wick_pct_of_range * bar_range)
    if lower_wick < wick_threshold:
        return None

    return float(round(level, 2))


def detect_pullback_hold_bullish(
    bar: pd.Series,
    prior_bars: pd.DataFrame,
    bar_idx: int,
    levels_active: list[float],
    zone_band_dollars: float = PULLBACK_HOLD_ZONE_BAND_DOLLARS,
    min_hold_bars: int = PULLBACK_HOLD_MIN_HOLD_BARS,
    lookback_bars: int = PULLBACK_HOLD_LOOKBACK_BARS,
) -> Optional[float]:
    """PULLBACK-HOLD bull trigger (Lane-A vocabulary build, queue item
    PULLBACK-HOLD-BULL-TRIGGER, filed 2026-07-22 Fable review).

    SHADOW-LOGGED ONLY — see `evaluate_bullish_setup`'s `shadow_triggers_fired`; NOT
    wired into `triggers`/`bull_score`/`passed`. Lane-B validation (frozen pre-reg →
    real-fills replay through exit_manager_walk → full 4-condition gate + concentration
    + BH-FDR, per OP-16) must clear before any live wiring — same precedent as
    `detect_wick_reclaim_bullish` / `detect_trendline_reclaim_bullish`, both shadow-only
    pending their own Lane-B.

    ROOT CAUSE this targets: `detect_level_reclaim` requires `bar.low < level < bar.close`
    on the SAME bar — by construction it can only fire AFTER price has already crossed
    back above the level, i.e. at-or-after the move (queue item's two verified exhibits:
    07-21 shelf+engulfing bull=9-10 with triggers=[] until the trigger finally fired at
    the session top; 07-22 pullback low sitting 26c above a KNOWN level_memory level with
    triggers=[] for 30+ minutes). PULLBACK-HOLD instead watches for price dipping INTO a
    level's zone band (never a penny-exact touch — levels-are-zones, J 2026-07-17),
    HOLDING there (not closing below the zone floor) for >= `min_hold_bars`, then
    breaking back above the minor structure the hold itself built (the highest close
    seen during the hold window) — an entry that can fire bars EARLIER than
    `detect_level_reclaim` ever can, at the shelf itself rather than the confirmation bar.

    Geometry (closed bars only — C6 no-look-ahead: `bar_idx` is the last bar examined,
    `prior_bars` includes it and nothing forward):
      1. Scan the "approach" window `[bar_idx - lookback_bars .. bar_idx - min_hold_bars]`
         for the bar whose LOW enters some level's zone band
         `[level - zone_band_dollars, level + zone_band_dollars]`. Pick the level with the
         TIGHTEST touch (smallest |low - level|) across the whole window.
      2. `low_idx` = the index of that tightest-touching bar.
      3. HOLD check: every bar from `low_idx` through `bar_idx - 1` inclusive must CLOSE
         >= `level - zone_band_dollars` (the zone floor was defended, not lost) — a single
         close below the floor invalidates the whole pattern (returns None).
      4. RECLAIM check: `bar` (the current, `bar_idx`) must CLOSE strictly above the
         highest close seen in the hold window AND still be >= the zone floor.

    Returns the defended level (float, rounded to cents) if the pattern confirms on
    `bar`, else None. Mirrors `detect_wick_reclaim_bullish`'s Optional[float] contract.
    """
    if bar_idx < min_hold_bars or not levels_active:
        return None

    approach_start = max(0, bar_idx - lookback_bars)
    approach_end = bar_idx - min_hold_bars  # last bar allowed to be the pullback low
    if approach_end < approach_start:
        return None

    # Find "the pullback low" = the EARLIEST bar achieving the LOWEST low among all
    # bars in the approach window whose low is within zone_band_dollars of some level
    # (i.e. the actual bottom of the dip, not merely the closest-to-level touch —
    # a bar still descending toward the level can tie or beat a later bar's distance
    # without yet being the true low, so pick by extremity-of-low first).
    best_level: Optional[float] = None
    best_low_idx: Optional[int] = None
    best_low_value: Optional[float] = None

    for i in range(approach_start, approach_end + 1):
        low_i = float(prior_bars.iloc[i]["low"])
        nearest_level = min(levels_active, key=lambda lvl: abs(low_i - lvl))
        if abs(low_i - nearest_level) > zone_band_dollars:
            continue  # this bar never entered any level's zone band
        if best_low_value is None or low_i < best_low_value:
            best_low_value = low_i
            best_low_idx = i
            best_level = nearest_level

    if best_level is None or best_low_idx is None:
        return None

    zone_floor = best_level - zone_band_dollars

    hold_indices = list(range(best_low_idx, bar_idx))  # low_idx .. bar_idx-1 inclusive
    if len(hold_indices) < min_hold_bars:
        return None  # not enough bars actually held before the reclaim bar

    highest_hold_close = float("-inf")
    for i in hold_indices:
        close_i = float(prior_bars.iloc[i]["close"])
        if close_i < zone_floor:
            return None  # zone floor broken during the hold — pattern invalidated
        highest_hold_close = max(highest_hold_close, close_i)

    current_close = float(bar["close"])
    if current_close < zone_floor:
        return None
    if current_close <= highest_hold_close:
        return None  # hasn't broken above the hold-window structure yet

    return float(round(best_level, 2))


def detect_trendline_reclaim_bullish(
    bar: pd.Series,
    prior_bars: pd.DataFrame,
    bar_idx: int,
    lookback_bars: int = 60,
    min_swings: int = 3,
    proximity_pct: float = 0.0010,
    require_decreasing: bool = True,
) -> Optional[float]:
    """Detect a bullish RECLAIM (breakout) of a descending trendline. Bull mirror of
    detect_trendline_rejection_bearish -- SHADOW-LOGGED only (see evaluate_bullish_setup's
    `shadow_triggers_fired`; NOT wired into `triggers`/scoring, 2026-07-15 fix-ship task).

    GEOMETRY CHOICE (markdown/audits/DIRECTIONAL-GATE-DEEP-RESEARCH-2026-07-15.md §4
    item 1 named two candidates and asked for an explicit pick): (a) the SAME
    descending-high-pivot line the bear function fits, but price BREAKS ABOVE it
    instead of getting rejected, vs. (b) an ascending-support line that was
    previously violated and is now being re-crossed. CHOSE (a):
      - Doctrine precedent: playbook.md's CANDIDATE `TRENDLINE_BREAK_VOLUME` pattern
        (line ~449) names this EXACT geometry -- "PUTS on ascending break / CALLS on
        descending break" -- J's own words (2026-05-11): "trend line break... volume
        and trend line break, this is clean." A descending-line breakout is the
        doctrine-recognized bullish trendline pattern, not the ascending-support-
        reclaim alternative.
      - (a) reuses the bear function's pivot-finding/line-fit UNCHANGED (same
        descending, strictly-decreasing pivots, same least-squares fit, same
        "reached the line" approach check) -- only the terminal outcome flips
        (closes ABOVE + green, not below + red). (b) would need NEW ascending-pivot
        fitting logic (zero existing test coverage in this file) PLUS cross-bar
        violation STATE the bear function's pure single-bar contract doesn't carry
        -- that is inventing new logic, not mirroring existing logic.
    This detector does NOT implement TRENDLINE_BREAK_VOLUME itself (no volume gate,
    no retest requirement -- that stays a separate, not-yet-built, NOT YET TRADABLE
    n=2 candidate); it borrows only the geometry precedent.

    Algorithm: identical pivot-finding to detect_trendline_rejection_bearish
    (SEQUENTIAL DESCENDING PEAKS over `lookback_bars`, fit a line through
    `min_swings` strictly-decreasing local-high pivots -- see that function's
    docstring for the full pivot-search details). Fires when the current bar's high
    reaches the projected line (within proximity_pct) AND closes ABOVE it AND is
    green -- the direct complement of the bear function's reached+closed-below+red
    rejection check.

    Returns the trendline price at current bar if reclaim/breakout fires, else None.
    """
    if bar_idx < lookback_bars + 2:
        return None
    if prior_bars is None or len(prior_bars) < lookback_bars + 2:
        return None

    start = max(0, bar_idx - lookback_bars)
    window = prior_bars.iloc[start:bar_idx]
    if len(window) < min_swings * 5:
        return None

    # SEQUENTIAL DESCENDING PEAKS -- byte-identical search to
    # detect_trendline_rejection_bearish (same overhead descending-resistance line;
    # only the terminal outcome check differs, below).
    MIN_BAR_SEPARATION = 10
    highs = window["high"].values
    recent_pivots: list[tuple[int, float]] = []
    search_start = 0
    for _ in range(min_swings):
        if search_start >= len(highs):
            break
        sub_highs = highs[search_start:]
        if len(sub_highs) == 0:
            break
        rel_pos = int(sub_highs.argmax())
        pos = search_start + rel_pos
        val = float(highs[pos])
        if require_decreasing and recent_pivots and val >= recent_pivots[-1][1]:
            return None  # next selected peak isn't lower -- no descending trendline
        recent_pivots.append((pos, val))
        search_start = pos + MIN_BAR_SEPARATION

    if len(recent_pivots) < min_swings:
        return None

    n = len(recent_pivots)
    sum_x = sum(p[0] for p in recent_pivots)
    sum_y = sum(p[1] for p in recent_pivots)
    sum_xx = sum(p[0] * p[0] for p in recent_pivots)
    sum_xy = sum(p[0] * p[1] for p in recent_pivots)
    denom = n * sum_xx - sum_x * sum_x
    if denom == 0:
        return None
    slope = (n * sum_xy - sum_x * sum_y) / denom
    intercept = (sum_y - slope * sum_x) / n

    # For a descending trendline, slope must still be negative (decreasing highs)
    if require_decreasing and slope >= 0:
        return None

    current_rel_idx = len(window)
    trendline_price = slope * current_rel_idx + intercept

    # Mirror of the bear function's early-exit ("trendline must still be above
    # current spot"): here the trendline must still be below-or-at the close for a
    # breakout above it to be meaningful. Same redundant-but-documented shape,
    # consistent with (not contradicting) the closed_above check below.
    if trendline_price >= float(bar["close"]):
        return None

    # Reclaim/breakout criteria (complement of the bear rejection criteria):
    # 1. bar.high reached or exceeded the trendline (SAME "reached" check as bear --
    #    the APPROACH to the line is identical regardless of the eventual outcome)
    # 2. bar closes ABOVE the trendline (breaks through, vs. bear's closes below)
    # 3. bar is GREEN, close > open (confirms the breakout, vs. bear's red)
    proximity_dollars = trendline_price * proximity_pct
    reached_line = float(bar["high"]) >= (trendline_price - proximity_dollars)
    closed_above = float(bar["close"]) > trendline_price
    is_green = float(bar["close"]) > float(bar["open"])

    if reached_line and closed_above and is_green:
        return float(round(trendline_price, 2))
    return None


@dataclass
class BullishSetupResult:
    """Output of evaluate_bullish_setup."""
    passed: bool
    bull_score: int                   # 0..11
    blockers: list[int] = field(default_factory=list)
    triggers_fired: list[str] = field(default_factory=list)
    reclaim_level: Optional[float] = None
    ribbon_just_flipped_bullish: bool = False
    confluence_match: Optional[float] = None
    shadow_triggers_fired: list[str] = field(default_factory=list)
    # ^ SHADOW-LOGGED bull trigger mirrors (2026-07-15 fix-ship task): detected here,
    # NEVER merged into `triggers_fired` -- so they cannot affect `passed`/`bull_score`
    # (this dataclass), nor engine_cli.py's `_derive_routing` (trigger-COUNT tie-break
    # between bear/bull) or `_derive_tier` (quality-tier classification), both of which
    # read `triggers_fired` only. Visible on this object for any caller (analysis,
    # future backtests, a later promotion step) that wants to inspect/log them; not yet
    # threaded into core-decisions.jsonl (that requires touching engine_cli.py's
    # `decide_payload` + heartbeat_core.py's `run_account`, out of scope for this
    # additive change -- see test_bull_trendline_wick_reclaim_shadow_only.py).


VIX_BULL_LOW_THRESHOLD = 17.20    # mirror of VIX_BEAR_THRESHOLD (17.30)
VIX_BULL_HARD_CAP = 22.0          # filter 9: VIX < 22 hard (WS2 unblock 2026-06-26, was 18)


def evaluate_bullish_setup(
    ctx: BarContext,
    disable_filters: Optional[list[int]] = None,
    min_triggers: int = 1,
    no_trade_before: Optional[dt.time] = None,
    no_trade_window: Optional[tuple] = None,
    f10_vol_mult: float = 0.7,
    # --- NEW: BEARISH_SWEEP_BLOCKER gate (strategy/candidates/2026-05-16-bearish-sweep-blocker.md) ---
    sweep_blocker_enabled: bool = False,
    sweep_min_wick_pct: float = 0.0003,
    sweep_min_close_back_pct: float = 0.0005,
    sweep_block_window_bars: int = 3,
    sweep_clean_prior_bars: int = 3,
    # --- STRUCTURE-SHIFT-CONFIRMATION-AT-LEVELS (mirror of evaluate_bearish_setup's flag;
    # see that docstring block for the full pre-reg/doctrine citation). Bull side: waives
    # the htf_15m-disagreement SOFT score demerit (never a hard blocker to begin with) when
    # a structure shift confirms — the OR-alternative to HTF agreement. FLAG-GATED, DEFAULT
    # FALSE, byte-identical when off (see the bull_score block below).
    structure_shift_confirmation: bool = False,
    structure_shift_k: int = STRUCTURE_SHIFT_K_DEFAULT,
) -> BullishSetupResult:
    """Run all 11 bullish filters + trigger checks. Mirror of evaluate_bearish_setup
    with the v11-ratified parameters.

    Filters (per heartbeat.md BULLISH (11)):
      1.  time gates (>=10:00 ET, NOT in 14:00-15:00 window)
      2.  news clear (backtest stub)
      3.  budget>risk (always pass in backtest)
      4.  day-trades>=1 (always pass)
      5.  ribbon BULL-stacked Fast>Pivot>Slow
      6.  spread>=30c
      7.  NOT volume_divergence_failed (mirror of bearish)
      8.  VIX<17.20 OR vix_falling
      9.  VIX<22 (HARD)
      10. buyer pressure: close>open AND vol>=0.7x 20-bar avg (RATIFIED v11)
      11. ≥min_triggers of {level_reclaim / ribbon_flip / multi_day_confluence /
          sequence_reclaim} AND htf_15m != BEAR (-1 score modifier if BEAR)
    """
    disable = set(disable_filters or [])
    blockers: list[int] = []
    triggers: list[str] = []
    reclaim_level = None
    ribbon_flipped = False
    confluence = None

    # Filter 1: time gate
    if 1 not in disable:
        bar_time = ctx.timestamp_et.time()
        if bar_time < dt.time(9, 35):
            blockers.append(1)
        elif no_trade_before is not None and bar_time < no_trade_before:
            blockers.append(1)
        elif no_trade_window is not None:
            # Supports a single (start, end) tuple OR a list of (start, end) tuples
            # (multi-window support added 2026-05-24 for AM dead-zone + chop-window combinations)
            _windows = (
                [no_trade_window]
                if isinstance(no_trade_window[0], dt.time)
                else list(no_trade_window)
            )
            if any(w[0] <= bar_time < w[1] for w in _windows):
                blockers.append(1)

    # Filters 2, 3, 4: always pass in backtest

    # Filter 5: ribbon BULL-stacked
    if 5 not in disable:
        if ctx.ribbon_now is None or ctx.ribbon_now.stack != "BULL":
            blockers.append(5)

    # Filter 6: spread >= 30c
    if 6 not in disable:
        if ctx.ribbon_now is None or ctx.ribbon_now.spread_cents < RIBBON_SPREAD_MIN_CENTS:
            blockers.append(6)

    # Filter 7: NOT volume_divergence (mirror of bearish — recovery bar with ≥ vol after green breakout)
    if 7 not in disable:
        # Inverse: green breakout, then red recovery >= vol = setup invalidated
        if _bullish_volume_divergence_failed(ctx.prior_bars, ctx.bar_idx):
            blockers.append(7)

    # Filter 8: VIX < 17.20 OR falling
    if 8 not in disable:
        vd = vix_direction(ctx.vix_now, ctx.vix_prior)
        vix_pass = ctx.vix_now < VIX_BULL_LOW_THRESHOLD or vd == "falling"
        if not vix_pass:
            blockers.append(8)

    # Filter 9: VIX < 22 HARD
    if 9 not in disable:
        if ctx.vix_now >= VIX_BULL_HARD_CAP:
            blockers.append(9)

    # Filter 10: buyer pressure (configurable vol_mult)
    if 10 not in disable:
        if ctx.ribbon_now is not None:
            if not buyer_pressure_bar_v11(ctx.bar, ctx.vol_baseline_20, vol_mult=f10_vol_mult):
                blockers.append(10)
        else:
            blockers.append(10)

    # Filter 11: HTF + ≥ triggers
    htf_disagrees = ctx.htf_15m_stack == "BEAR"
    reclaim_level = detect_level_reclaim(ctx.bar, ctx.levels_active)

    # Pre-compute confluence NOW so the sweep_blocker carve-out can check it.
    # (confluence is also used below when populating the triggers list — same result.)
    confluence = detect_confluence(reclaim_level, ctx.multi_day_levels)

    # SWEEP_BLOCKER gate (filter 12): block BULLISH entry if a BEARISH_SWEEP (up-sweep)
    # was detected at the reclaim_level in the prior sweep_block_window_bars bars.
    # An up-sweep means price wicked ABOVE the level but closed BACK BELOW — bulls
    # failed to hold the level. Entering BULL on the next bar is the 5/14 09:58 misfire class.
    # This is a HARD block (structural) — cannot be bypassed by allow_one_blocker.
    # CONFLUENCE CARVE-OUT (2026-05-21): if 3+ independent signals align (confluence),
    # the sweep is treated as a liquidity grab before the actual breakout, not a rejection.
    # Stage-3 showed 0% correct-block rate on confluence entries — the gate was blocking
    # the engine's highest-conviction setups. See sweep-blocker-stage3.json for evidence.
    if (sweep_blocker_enabled and reclaim_level is not None
            and confluence is None  # carve-out: skip block if confluence confirmed
            and 12 not in (disable_filters or [])):
        if _detect_sweep_at_level(
            ctx.prior_bars, ctx.bar_idx, reclaim_level,
            direction="bearish",
            min_wick_pct=sweep_min_wick_pct,
            min_close_back_pct=sweep_min_close_back_pct,
            block_window_bars=sweep_block_window_bars,
            clean_prior_bars=sweep_clean_prior_bars,
        ):
            blockers.append(12)

    ribbon_flipped = detect_ribbon_flip_bullish(ctx.ribbon_history)
    # confluence already computed above (moved to pre-sweep position for carve-out check)

    # Look up level state for sequence_reclaim check
    level_state = None
    if reclaim_level is not None and ctx.level_states:
        for state in ctx.level_states.values():
            if abs(state.price - reclaim_level) <= 0.05:
                level_state = state
                break
    sequence_reclaimed = detect_sequence_reclaim(level_state) if level_state else False

    if reclaim_level is not None:
        triggers.append("level_reclaim")
    if ribbon_flipped:
        triggers.append("ribbon_flip")
    if confluence is not None:
        triggers.append("confluence")
    if sequence_reclaimed:
        triggers.append("sequence_reclaim")

    if 11 not in disable and len(triggers) < min_triggers:
        blockers.append(11)
    elif 11 not in disable:
        # Defensive: same v11.1 hardening — require at least one level-tied trigger
        level_tied = {"level_reclaim", "confluence", "sequence_reclaim"}
        if not any(t in level_tied for t in triggers):
            blockers.append(11)

    bull_score = 11 - len(blockers)
    # HTF disagreement demerit — waived by a positive structure-shift confirmation when
    # structure_shift_confirmation is armed (the OR-alternative to HTF agreement; see the
    # signature docstring block). Byte-identical when the flag is off: structure_shift_bull
    # is never computed (stays None), so the demerit always applies exactly as before.
    if htf_disagrees and 11 not in disable:
        structure_shift_bull = (
            detect_structure_shift_bull(
                ctx.prior_bars, ctx.bar_idx, ctx.levels_active, k=structure_shift_k,
            )
            if structure_shift_confirmation
            else None
        )
        if structure_shift_bull is None:
            bull_score = max(0, bull_score - 1)

    # ── SHADOW-LOGGED bull trigger mirrors (2026-07-15 fix-ship-repeat root-cause task) ──
    # markdown/audits/DIRECTIONAL-GATE-DEEP-RESEARCH-2026-07-15.md §4 "New-trigger work
    # items" #1: bull had 4 trigger types vs bear's 6 -- trendline_rejection and
    # wick_rejection(-promotion) had no bull mirror at all. Computed here for VISIBILITY
    # and measurement, deliberately kept OUT of `triggers` (and therefore out of
    # `blockers`/`bull_score`/`passed` above, and out of engine_cli.py's
    # `_derive_routing`/`_derive_tier`, both of which read only `triggers_fired`).
    # Zero real-fills evidence exists for either pattern yet; OP-16's eval-first gate
    # requires an A/B scorecard before a new trigger may affect live scoring. This
    # mirrors the context_bundle "logged-only, decision-path-blind" precedent
    # (test_context_bundle_tag_no_behavior_change.py). Placed AFTER bull_score/blockers
    # are finalized so it's textually obvious this cannot have influenced them --
    # proven by test_bull_trendline_wick_reclaim_shadow_only.py.
    shadow_triggers: list[str] = []
    _shadow_trendline_reclaim = detect_trendline_reclaim_bullish(
        ctx.bar, ctx.prior_bars, ctx.bar_idx,
        lookback_bars=TRENDLINE_LOOKBACK_BARS,
        min_swings=TRENDLINE_MIN_SWINGS,
    )
    if _shadow_trendline_reclaim is not None:
        shadow_triggers.append("trendline_reclaim")
    _shadow_wick_reclaim = detect_wick_reclaim_bullish(
        ctx.bar, ctx.levels_active,
        min_wick_pct_of_range=WICK_MIN_PCT_OF_RANGE,
        min_wick_dollars=WICK_MIN_DOLLARS,
        close_tolerance_below_level=WICK_CLOSE_TOLERANCE,
    )
    if _shadow_wick_reclaim is not None:
        shadow_triggers.append("wick_reclaim")
    _shadow_pullback_hold = detect_pullback_hold_bullish(
        ctx.bar, ctx.prior_bars, ctx.bar_idx, ctx.levels_active,
        zone_band_dollars=PULLBACK_HOLD_ZONE_BAND_DOLLARS,
        min_hold_bars=PULLBACK_HOLD_MIN_HOLD_BARS,
        lookback_bars=PULLBACK_HOLD_LOOKBACK_BARS,
    )
    if _shadow_pullback_hold is not None:
        shadow_triggers.append("pullback_hold")

    return BullishSetupResult(
        passed=(len(blockers) == 0),
        bull_score=bull_score,
        blockers=sorted(blockers),
        triggers_fired=triggers,
        reclaim_level=reclaim_level,
        ribbon_just_flipped_bullish=ribbon_flipped,
        confluence_match=confluence,
        shadow_triggers_fired=shadow_triggers,
    )


def buyer_pressure_bar_v11(bar: pd.Series, vol_baseline: float, vol_mult: float = 0.7) -> bool:
    """Filter 10 BULLISH: green bar + vol >= vol_mult * 20-bar avg (RATIFIED v11 0.7x)."""
    if bar["close"] <= bar["open"]:
        return False
    if bar["volume"] < vol_mult * vol_baseline:
        return False
    return True


def _bullish_volume_divergence_failed(prior_bars: pd.DataFrame, idx: int) -> bool:
    """Setup invalidated when a green breakout bar is followed within 1-2 bars by a red
    recovery bar that closes DOWN with volume >= breakout bar volume.

    Mirror of volume_divergence_failed (bearish).
    """
    if idx < 2:
        return False
    candidates = []
    if idx - 1 >= 0:
        candidates.append((idx - 1, idx))
    if idx - 2 >= 0:
        candidates.append((idx - 2, idx - 1))
        candidates.append((idx - 2, idx))
    for bo_idx, rec_idx in candidates:
        bo = prior_bars.iloc[bo_idx]
        rec = prior_bars.iloc[rec_idx]
        if bo["close"] <= bo["open"]:
            continue  # breakout candidate must be green
        if rec["close"] < rec["open"] and rec["volume"] >= bo["volume"]:
            return True
    return False


# ----- filter evaluation -----

def evaluate_bearish_setup(
    ctx: BarContext,
    disable_filters: Optional[list[int]] = None,
    min_triggers: int = 1,    # RATIFIED 2026-05-07: was 2; sweep showed 27 trades / 59% WR / -$546 vs 13/46%/-$742 baseline
    vix_soft_mode: bool = False,
    allow_one_blocker: bool = False,
    allow_one_blocker_min_spread_cents: int = 0,
    no_trade_before: Optional[dt.time] = None,    # e.g. dt.time(10, 0) blocks pre-10am entries
    no_trade_window: Optional[tuple] = None,      # e.g. (dt.time(14, 0), dt.time(15, 0)) blocks afternoon
    f9_vol_mult: float = 0.7,                     # RATIFIED 2026-05-07 v11 — was 1.3 (too strict, missed morning rejections)
    # --- NEW: BEARISH_SWEEP_BLOCKER gate (strategy/candidates/2026-05-16-bearish-sweep-blocker.md) ---
    sweep_blocker_enabled: bool = False,
    sweep_min_wick_pct: float = 0.0003,
    sweep_min_close_back_pct: float = 0.0005,
    sweep_block_window_bars: int = 3,
    sweep_clean_prior_bars: int = 3,
    # --- RANK 28: BEARISH_REVERSAL bypass (2026-06-16) ---
    # When True, removes filter_5 (ribbon stack) and filter_8 (VIX gate) for setups where
    # ribbon=BULL + level_rejection (no trendline). The 5/01 11:50 J anchor (+$470 EC).
    # DEFAULT FALSE — Rule 9 flag. Enable via run_backtest(include_bearish_reversal_bypass=True)
    # for A/B testing only. Production heartbeat.md edit requires J ratification.
    bearish_reversal_bypass: bool = False,
    # V4 quality discriminators (study 2026-06-16). Choose at most one per run.
    # fhh_quality_proximity: FHH within X$ of any multi_day_level. ANTI-CORRELATED
    #   with J anchor pattern — removes 5/01 at all thresholds (0.50, 1.00, 2.00).
    #   Valid research tool for OPPOSITE setups (FHH = prior-range resistance).
    # fhh_above_max_prior_min: FHH >= X$ above max(multi_day_levels). Gap-up hypothesis:
    #   5/01 gap-up FHH=724.24 is above PDH~722; 5/08 FHH=736.66 is below PDH~737.
    #   None = off for both (backward compatible default).
    fhh_quality_proximity: Optional[float] = None,
    fhh_above_max_prior_min: Optional[float] = None,
    # --- STRUCTURE-SHIFT-CONFIRMATION-AT-LEVELS (2026-07-28, Rule-9 mid-session waiver
    # documented in the pre-reg) — Gap 1 fix from J-MARKET-PHILOSOPHY.md: replaces the
    # LAGGING ribbon-stack confirmation with an immediate price-structure confirmation
    # (failed retest + break of the prior swing low) for level-tied setups. FLAG-GATED,
    # DEFAULT FALSE. When False, `structure_shift_bear` below is never computed (the
    # `structure_shift_confirmation and ...` guard short-circuits) so filter 5 is
    # BYTE-IDENTICAL to pre-flag behavior. The ribbon check is NEVER removed — this is a
    # pure OR-alternative. Pre-reg: analysis/recommendations/
    # prereg-structure-shift-confirmation-2026-07-28.json. Predicate:
    # backtest/lib/structure_shift.py#detect_structure_shift_bear.
    structure_shift_confirmation: bool = False,
    structure_shift_k: int = STRUCTURE_SHIFT_K_DEFAULT,
) -> SetupResult:
    """Run all 10 bearish filters + trigger checks. Return SetupResult.

    Args:
        disable_filters: filter numbers to skip (treat as auto-pass). Used for
            historical regime testing — e.g. filter 8 (VIX > 17.30 + rising) was
            added 2026-05-05 and didn't apply to the 4/29, 5/1, 5/4 historical trades.
        min_triggers: minimum filter-10 triggers required to fire (default 2).
            Lowering to 1 catches more J-quality early-rejection setups but adds noise.
        vix_soft_mode: if True, filter 8 becomes a -1 score modifier instead of a
            hard block. Allows VIX-falling environments (post-FOMC, calm regimes) to
            still produce setups when other filters are strong.
        allow_one_blocker: if True, the setup can pass with up to 1 filter blocked
            (excluding filters 1-4 which are environmental + filter 5 which is the
            ribbon stack — those are structural, not modulatable).
        allow_one_blocker_min_spread_cents: when allow_one_blocker is True and F6
            (ribbon spread) is the sole non-structural blocker, only bypass F6 if the
            actual spread is >= this threshold. Default 0 = no extra guard (same as
            original allow_one_blocker behavior). Setting to e.g. 25 prevents allow_one_
            blocker from firing when the ribbon is extremely tight (e.g. 16c on 4/29 09:45)
            while still catching near-threshold setups (e.g. 29c on 5/04 11:10).
    """
    disable = set(disable_filters or [])
    blockers: list[int] = []
    triggers: list[str] = []
    rejection_level = None
    ribbon_flipped = False
    confluence = None

    # Filter 1: time >= 09:35 ET (and time-window restrictions)
    if 1 not in disable:
        bar_time = ctx.timestamp_et.time()
        if bar_time < dt.time(9, 35):
            blockers.append(1)
        elif no_trade_before is not None and bar_time < no_trade_before:
            blockers.append(1)
        elif no_trade_window is not None:
            # Supports a single (start, end) tuple OR a list of (start, end) tuples
            # (multi-window support added 2026-05-24 for AM dead-zone + chop-window combinations)
            _windows = (
                [no_trade_window]
                if isinstance(no_trade_window[0], dt.time)
                else list(no_trade_window)
            )
            if any(w[0] <= bar_time < w[1] for w in _windows):
                blockers.append(1)

    # Filter 2: news clear (backtest stub — assumes clear unless wired)
    # Filters 3, 4: always pass in backtest (budget, day-trades)

    # Filter 5: ribbon BEAR-stacked (OR structure-shift confirmation when flag-armed —
    # see the structure_shift_confirmation docstring block above the signature).
    # Byte-identical to the pre-flag check when structure_shift_confirmation=False: the
    # `structure_shift_confirmation and not ribbon_bear_ok` guard short-circuits, leaving
    # `structure_shift_bear` at None, so `not (ribbon_bear_ok or False)` == the original
    # `ctx.ribbon_now is None or ctx.ribbon_now.stack != "BEAR"` (De Morgan's).
    if 5 not in disable:
        ribbon_bear_ok = ctx.ribbon_now is not None and ctx.ribbon_now.stack == "BEAR"
        structure_shift_bear = (
            detect_structure_shift_bear(
                ctx.prior_bars, ctx.bar_idx, ctx.levels_active, k=structure_shift_k,
            )
            if structure_shift_confirmation and not ribbon_bear_ok
            else None
        )
        if not (ribbon_bear_ok or structure_shift_bear is not None):
            blockers.append(5)

    # Filter 6: spread >= 30 cents
    if 6 not in disable:
        if ctx.ribbon_now is None or ctx.ribbon_now.spread_cents < RIBBON_SPREAD_MIN_CENTS:
            blockers.append(6)

    # Filter 7: NOT volume_divergence_failed
    if 7 not in disable and volume_divergence_failed(ctx.prior_bars, ctx.bar_idx):
        blockers.append(7)

    # Filter 8: VIX > 17.30 AND vix_rising  (added 2026-05-05; pre-rules historical trades skip this)
    # VIX_HARD_CAP_BEAR: when vix_now > cap, also block (targets panic extremes: Apr 2026 Liberation Day VIX=52).
    # vix_soft_mode: become a score modifier instead of hard blocker.
    vix_soft_demerit = False
    if 8 not in disable:
        vd = vix_direction(ctx.vix_now, ctx.vix_prior)
        vix_pass = ctx.vix_now > VIX_BEAR_THRESHOLD and vd == "rising"
        if vix_pass and ctx.vix_now > VIX_HARD_CAP_BEAR:
            vix_pass = False  # panic-extreme VIX: options mis-priced (L99/L100), stop misfires
        if vix_pass and VIX_DECLINING_REQUIRED_BEAR and ctx.vix_5d_ma > 0.0 and ctx.vix_20d_ma > 0.0:
            # L115: require multi-day VIX declining for BEAR entries (L93 recommendation).
            # Uses 5d_MA vs 20d_MA crossover (golden/death cross on VIX):
            #   5d_MA > 20d_MA = short-term VIX above long-term avg = ESCALATING regime → block
            #   5d_MA < 20d_MA = short-term VIX below long-term avg = DECLINING regime → allow
            # This discriminates Liberation Day escalation (Apr 2-30, 5d>20d) from
            # post-shock recovery (May 8+, 5d<20d as spike fades from the long-term window).
            if ctx.vix_5d_ma > ctx.vix_20d_ma:
                vix_pass = False
        if not vix_pass:
            if vix_soft_mode:
                vix_soft_demerit = True   # -1 score modifier; doesn't block
            else:
                blockers.append(8)

    # Filter 9: breakdown_bar_bearish (vol threshold configurable via f9_vol_mult)
    if 9 not in disable:
        if ctx.ribbon_now is not None:
            if not breakdown_bar_bearish(
                ctx.bar, ctx.ribbon_now.fast, ctx.vol_baseline_20, vol_mult=f9_vol_mult
            ):
                blockers.append(9)
        else:
            blockers.append(9)

    # Filter 10: HTF alignment (SOFT modifier) + >= 2 of 4 triggers
    # SYNCED 2026-05-07 from heartbeat.md:
    # - HTF disagreement is a -1 score modifier, NOT a hard block
    # - Triggers expanded to 4: level_rejection, ribbon_flip, confluence, sequence_rejection
    htf_disagrees = ctx.htf_15m_stack == "BULL"  # bearish setup wants HTF != BULL
    rejection_level = detect_level_rejection(ctx.bar, ctx.levels_active)
    ribbon_flipped = detect_ribbon_flip_bearish(ctx.ribbon_history)
    confluence = detect_confluence(rejection_level, ctx.multi_day_levels)

    # NEW 2026-05-09 night: trendline_rejection trigger (CLAUDE.md OP 17 TDD).
    # Encodes J's 5/1-style setup: rejection of a descending intraday trendline.
    # Verified by tests/test_trendline_trigger.py (3/3 passing).
    trendline_level = detect_trendline_rejection_bearish(
        ctx.bar, ctx.prior_bars, ctx.bar_idx,
        lookback_bars=TRENDLINE_LOOKBACK_BARS,
        min_swings=TRENDLINE_MIN_SWINGS,
    )

    # NEW 2026-05-10: wick_rejection trigger (CLAUDE.md OP 17 TDD).
    # Encodes J's 4/29 10:25 setup -- bar pierced level then closed back near it
    # with a significant upper wick, even though close was technically above level.
    # Engine's strict close-below-level missed J's actual entry bar.
    # Verified by tests/test_wick_rejection_trigger.py (4/4 passing).
    wick_level = detect_wick_rejection_bearish(
        ctx.bar, ctx.levels_active,
        min_wick_pct_of_range=WICK_MIN_PCT_OF_RANGE,
        min_wick_dollars=WICK_MIN_DOLLARS,
        close_tolerance_above_level=WICK_CLOSE_TOLERANCE,
    )

    # Look up level state for sequence_rejection check
    level_state = None
    if rejection_level is not None and ctx.level_states:
        # Find LevelState by approximate price match (within $0.05)
        for state in ctx.level_states.values():
            if abs(state.price - rejection_level) <= 0.05:
                level_state = state
                break
    sequence_rejected = detect_sequence_rejection(level_state) if level_state else False

    # Candlestick pattern detection (NEW 2026-05-07).
    # ROLLED BACK from being a trigger: v4 backtest with candlestick triggers
    # showed P&L $309 → $135 (-56%) and expectancy $24 → $8 (-67%) due to noisy
    # marubozu firings on mid-trend continuation bars. Candlesticks now serve as
    # AWARENESS LANGUAGE for chart description and journaling — NOT entry triggers.
    # The functions remain available for use in journal narrative and live-chart
    # description (per chart-anatomy.md "Live-chart language doctrine").
    bar_prev = ctx.prior_bars.iloc[ctx.bar_idx - 1] if ctx.bar_idx > 0 else None
    candlestick_pattern = detect_candlestick_pattern_bearish(
        ctx.bar, bar_prev, ctx.levels_active, float(ctx.bar["close"])
    )
    # Pattern is captured for forensic record but does NOT contribute to triggers.

    wick_only_level_rejection = False
    if rejection_level is not None:
        triggers.append("level_rejection")
    elif wick_level is not None:
        # Wick rejection acts as a level-tied trigger when close-rejection misses.
        # Reuse the rejection_level slot so downstream chart-stop computation works.
        rejection_level = wick_level
        triggers.append("level_rejection")
        wick_only_level_rejection = True
    # Rank 27 / 2026-06-16: FHH supplemental level check. Only fires when no base level
    # produced level_rejection. Generates fhh_level_rejection (NOT level_rejection) so
    # trendline_only_setup logic is unaffected — see L96 inverse-dependency fix.
    if ctx.fhh_level is not None and rejection_level is None:
        fhh_rej = detect_level_rejection(ctx.bar, [ctx.fhh_level])
        if fhh_rej is not None:
            rejection_level = fhh_rej
            triggers.append("fhh_level_rejection")
    if ribbon_flipped:
        triggers.append("ribbon_flip")
    if confluence is not None:
        triggers.append("confluence")
    if sequence_rejected:
        triggers.append("sequence_rejection")
    if trendline_level is not None:
        triggers.append("trendline_rejection")

    # 2026-05-09 night: TRENDLINE-CHOP-ZONE relaxation (encodes J's 5/1 setup).
    # When trendline_rejection fires AS THE ONLY level-tied trigger, J takes the
    # trade even in chop conditions (mixed ribbon, low VIX). This block removes
    # filters 5 (ribbon BEAR) and 8 (VIX) from the blocker list when ONLY trendline
    # fires, replacing each with a -1 score demerit. Other level-tied triggers
    # (level_rejection, confluence, sequence_rejection) still require full ribbon+VIX.
    trendline_only_setup = (
        "trendline_rejection" in triggers and
        "level_rejection" not in triggers and
        "confluence" not in triggers and
        "sequence_rejection" not in triggers
    )
    # 2026-05-10: wick-only chop relaxation TRIED + REVERTED.
    # Result: caused engine to take J's loser on 5/05 + dragged 5/01 deeper
    # negative. 4/29 already wins via 12:25 close-below level_rejection so
    # wick relaxation isn't needed to capture J's edge. Wick trigger is kept
    # as a level_rejection promotion when other filters all pass naturally
    # (no chop relaxation), so it can still help on bars where filters are
    # otherwise green but the wick was the rejection signal.
    _ = wick_only_level_rejection  # kept for future experiments
    trendline_chop_demerit = 0
    if trendline_only_setup:
        if 5 in blockers:
            blockers.remove(5)
            trendline_chop_demerit += 1
        if 8 in blockers:
            blockers.remove(8)
            trendline_chop_demerit += 1
        # Filter 9 (vol confirmation) also relaxed -- J's chop trade had low vol
        if 9 in blockers:
            blockers.remove(9)
            trendline_chop_demerit += 1

    # BEARISH_REVERSAL bypass (2026-06-16 / Rank 28): When ribbon=BULL and a base-level
    # or FHH rejection fires WITHOUT a trendline trigger, the setup is a countertrend
    # reversal entry. Bypass filter_5 (ribbon stack) and filter_8 (VIX gate) only.
    # This is the 5/01 11:50 J anchor setup (ribbon=BULL, level_rejection, +$470 EC).
    # Mutually exclusive with trendline_only_setup (trendline_only requires NO level_rejection;
    # this requires level_rejection|fhh AND NO trendline_rejection). Ribbon=BEAR entries
    # already pass filter_5 naturally — this bypass only fires when ribbon=BULL blocks it.
    # Rule 9 flag: gated on bearish_reversal_bypass=True (default False). Production
    # heartbeat.md edit requires J ratification before enabling.
    bearish_reversal_setup = False
    bearish_reversal_demerit = 0
    if bearish_reversal_bypass:
        # Restricted to fhh_level_rejection ONLY (not standard level_rejection).
        # Rationale: FHH is a clean, fresh, session-defined resistance (first hour high).
        # Standard level_rejection on BULL ribbon is too noisy — fires on any level in
        # any context. FHH rejection specifically means "price ran up to the morning high
        # and was rejected there while ribbon stayed BULL" — the 5/01 11:50 J anchor case.
        # Requires include_first_hour_high=True to be meaningful (fhh_level_rejection never
        # fires without the FHH feature active). These two features compose together.
        bearish_reversal_setup = (
            "fhh_level_rejection" in triggers
            and "trendline_rejection" not in triggers
            and ctx.ribbon_now is not None
            and ctx.ribbon_now.stack == "BULL"
        )
        # V4 quality gate — two mutually exclusive discriminators (study 2026-06-16):
        # 1. fhh_quality_proximity: FHH within X dollars of a multi_day_level (ANTI-CORRELATED
        #    with J anchor — 5/01 FHH is ABOVE all prior levels, not near them; proximity gate
        #    removes 5/01 at all thresholds. Do not use for J-anchor-style setups.)
        # 2. fhh_above_max_prior_min: FHH must be >= X above max(multi_day_levels). Captures
        #    the gap-up pattern: price punched above prior range and formed a fresh high.
        #    Hypothesis: 5/01 (FHH=724.24, PDH~722 → gap=~2.24) passes; 5/08 (FHH=736.66,
        #    PDH~737 → FHH < max_prior) blocked. Empirically tested 2026-06-16.
        if bearish_reversal_setup and fhh_quality_proximity is not None and ctx.fhh_level is not None:
            bearish_reversal_setup = any(
                abs(ctx.fhh_level - ml) <= fhh_quality_proximity
                for ml in ctx.multi_day_levels
            )
        if bearish_reversal_setup and fhh_above_max_prior_min is not None and ctx.fhh_level is not None:
            if ctx.multi_day_levels:
                bearish_reversal_setup = (
                    ctx.fhh_level >= max(ctx.multi_day_levels) + fhh_above_max_prior_min
                )
        if bearish_reversal_setup:
            if 5 in blockers:
                blockers.remove(5)
                bearish_reversal_demerit += 1
            if 8 in blockers:
                blockers.remove(8)
                bearish_reversal_demerit += 1

    if 10 not in disable and len(triggers) < min_triggers:
        blockers.append(10)
    # Defensive: pure ribbon_flip (lagging EMA reorder with no level context) is the
    # weakest trigger class. Require at least one level-tied trigger to avoid pure-
    # confirmation entries.
    elif 10 not in disable:
        level_tied = {"level_rejection", "fhh_level_rejection", "confluence", "sequence_rejection", "trendline_rejection"}
        if not any(t in level_tied for t in triggers):
            blockers.append(10)

    # SWEEP_BLOCKER gate (filter 11): block BEARISH entry if a BULLISH_SWEEP (down-sweep)
    # was detected at the rejection_level in the prior sweep_block_window_bars bars.
    # A down-sweep means price wicked BELOW the level but closed BACK ABOVE — bears
    # tried to break the level but bulls defended. Entering BEAR on the next bar is the
    # mirror foot-gun class of 5/14 09:58 ENTER_BULL. Hard block; cannot be bypassed.
    # CONFLUENCE CARVE-OUT (2026-05-21): triggers is populated before this check (see above).
    # If 3+ signals align (confluence confirmed), skip the sweep block — a sweep into a
    # confluence level is more likely a liquidity grab than a genuine rejection.
    # Stage-3 showed both incorrectly-blocked winners had 'confluence' trigger.
    # Candidate: strategy/candidates/2026-05-16-bearish-sweep-blocker.md
    if (sweep_blocker_enabled and rejection_level is not None
            and "confluence" not in triggers  # carve-out: skip block if confluence confirmed
            and 11 not in (disable or set())):
        if _detect_sweep_at_level(
            ctx.prior_bars, ctx.bar_idx, rejection_level,
            direction="bullish",
            min_wick_pct=sweep_min_wick_pct,
            min_close_back_pct=sweep_min_close_back_pct,
            block_window_bars=sweep_block_window_bars,
            clean_prior_bars=sweep_clean_prior_bars,
        ):
            blockers.append(11)

    bear_score = 10 - len(blockers)
    # HTF disagreement is now a -1 score modifier (soft), not blocker
    if htf_disagrees and 10 not in disable:
        bear_score = max(0, bear_score - 1)
    # VIX soft-mode demerit (when vix_soft_mode=True and VIX condition not met)
    if vix_soft_demerit:
        bear_score = max(0, bear_score - 1)
    # Trendline-chop-zone demerit: each relaxed filter (5, 8, 9) costs -1 to the score
    # so trendline-only setups score lower than full setups -- still tradeable but graded.
    if trendline_chop_demerit:
        bear_score = max(0, bear_score - trendline_chop_demerit)
    # BEARISH_REVERSAL demerit: countertrend level entries score lower than BEAR-ribbon entries.
    if bearish_reversal_demerit:
        bear_score = max(0, bear_score - bearish_reversal_demerit)

    # `allow_one_blocker` mode: setup can fire with up to 1 blocker outside
    # the structural-required set (1, 2, 3, 4, 5). Filters 6, 7, 8, 9, 10 are
    # candidate slack slots.
    # Filter 11 (sweep_block) is HARD when sweep_blocker_enabled — cannot be bypassed.
    STRUCTURAL_REQUIRED = {1, 2, 3, 4, 5}
    if sweep_blocker_enabled:
        STRUCTURAL_REQUIRED = STRUCTURAL_REQUIRED | {11}
    if allow_one_blocker:
        non_structural_blockers = [b for b in blockers if b not in STRUCTURAL_REQUIRED]
        structural_blockers = [b for b in blockers if b in STRUCTURAL_REQUIRED]
        # Extra guard: when F6 (ribbon spread) is the sole non-structural blocker
        # and allow_one_blocker_min_spread_cents > 0, require spread >= threshold.
        # Prevents premature early-morning entries when ribbon is extremely tight
        # (e.g. 16c on 4/29 09:45) while still catching near-threshold setups
        # (e.g. 29c on 5/04 11:10) when allow_one_blocker_min_spread_cents <= 29.
        spread_gate_ok = True
        if (allow_one_blocker_min_spread_cents > 0
                and non_structural_blockers == [6]
                and ctx.ribbon_now is not None):
            spread_gate_ok = ctx.ribbon_now.spread_cents >= allow_one_blocker_min_spread_cents
        # Allow if: no structural blockers AND at most 1 non-structural blocker
        # AND spread gate satisfied (if F6 is the sole slack blocker)
        passed = (len(structural_blockers) == 0
                  and len(non_structural_blockers) <= 1
                  and spread_gate_ok)
    else:
        passed = len(blockers) == 0

    return SetupResult(
        passed=passed,
        bear_score=bear_score,
        blockers=sorted(blockers),
        triggers_fired=triggers,
        rejection_level=rejection_level,
        ribbon_just_flipped_bearish=ribbon_flipped,
        confluence_match=confluence,
    )


# ─────────────────────────────────────────────────────────────────────────────
# GAMMA-SYNC seam — VWAP_RECLAIM_FAILED_BREAK (J_VWAP_RECLAIM_FB, edge #2, DORMANT).
#
# OP-4 / "no code drift between live and backtest": the backtest engine must make the
# SAME entry decision as the live heartbeat for this setup. We guarantee that by SINGLE
# SOURCE OF TRUTH — both call the one validated detector
# (lib.watchers.vwap_reclaim_failed_break_watcher.detect_vwap_reclaim_failed_break_setup),
# which is itself a byte-for-byte port of the research detector
# (autoresearch._sub_struct_vwap_reclaim_failed_break.detect_signals). filters.py exposes
# the thin delegators below so any backtest caller that reaches for "the filters library"
# detection gets EXACTLY the live watcher's logic — there is no second copy to drift.
#
# The import is FUNCTION-LOCAL on purpose: the watcher module imports BarContext FROM this
# file, so a module-top import here would be circular. Deferring it to call time breaks the
# cycle while keeping the single-source guarantee.
#
# DORMANT: the detector is pure/read-only and never places an order. Whether the backtest
# engine HONORS the entry is gated by params.j_vwap_reclaim_fb_enabled (default FALSE),
# exactly mirroring the heartbeat's flag check — so backtest==live in the inert default too.
# ─────────────────────────────────────────────────────────────────────────────
def detect_vwap_reclaim_failed_break(ctx: "BarContext"):
    """Backtest-engine entry point for VWAP_RECLAIM_FAILED_BREAK (edge #2).

    Delegates byte-for-byte to the live watcher detector (single source of truth, no
    drift). Returns the watcher's ``WatcherSignal`` (side/entry/chart-stop) or ``None``.
    Pure/causal: reads only ``ctx.prior_bars`` (today's RTH through the trigger bar).
    """
    from .watchers.vwap_reclaim_failed_break_watcher import (
        detect_vwap_reclaim_failed_break_setup,
    )
    return detect_vwap_reclaim_failed_break_setup(ctx)


def vwap_reclaim_failed_break_enabled(params: Optional[dict]) -> bool:
    """The DORMANT flag the backtest engine checks before HONORING an edge-#2 entry.

    Mirrors the heartbeat's ``params.json#j_vwap_reclaim_fb_enabled`` gate (default
    FALSE = inert). Keeping the flag read here means backtest and live share one gate
    semantics: detection always runs (so observation/parity holds), but the entry is
    acted on only when the flag is true.
    """
    if not params:
        return False
    return bool(params.get("j_vwap_reclaim_fb_enabled", False))


def vwap_reclaim_failed_break_side(params: Optional[dict]) -> str:
    """The configured side filter for edge #2 (default 'put', OP-16-conservative).

    Mirrors ``params.json#j_vwap_reclaim_fb_side``. 'put' | 'call' | 'both'.
    """
    if not params:
        return "put"
    return str(params.get("j_vwap_reclaim_fb_side", "put"))


# ── ISOLATED exit knobs (HIGH-1/HIGH-2/LOW-2 gamma-sync) ──────────────────────
# The backtest engine MUST honor the SAME isolated stop/tp1/buffer the live heartbeat
# reads — NOT the global premium_stop_pct (-0.50 catastrophe cap) / tp1_premium_pct
# (0.50) / chart_stop_buffer_dollars (0.50), which are the WRONG values for this cell.
# These three readers are the single source of truth for "what exit does edge #2 use",
# shared by backtest and (by the matching keys) the heartbeat prose. Fallback to the
# validated Safe-2 ATM ship-cell defaults when the key is absent (e.g. an older params
# snapshot) so the engine never silently falls back to the catastrophe cap.
_RECLAIM_FB_DEFAULT_PREMIUM_STOP_PCT = -0.08   # Safe-2 ATM ship cell
_RECLAIM_FB_DEFAULT_TP1_PCT = 0.30             # Safe-2 ATM ship cell
_RECLAIM_FB_DEFAULT_STOP_BUFFER = 0.25         # Safe-2 ATM ship cell


def vwap_reclaim_failed_break_premium_stop_pct(params: Optional[dict]) -> float:
    """Isolated premium stop for edge #2 — ``params#j_vwap_reclaim_fb_premium_stop_pct``.

    Default -0.08 (the validated cell stop). NEVER the global ``premium_stop_pct``.
    """
    if not params:
        return _RECLAIM_FB_DEFAULT_PREMIUM_STOP_PCT
    return float(params.get("j_vwap_reclaim_fb_premium_stop_pct",
                            _RECLAIM_FB_DEFAULT_PREMIUM_STOP_PCT))


def vwap_reclaim_failed_break_tp1_pct(params: Optional[dict]) -> float:
    """Isolated TP1 premium % for edge #2 — ``params#j_vwap_reclaim_fb_tp1_pct``.

    Default 0.30 (Safe-2 ATM cell). Bold/aggressive params sets 0.75. NEVER the global
    ``tp1_premium_pct``.
    """
    if not params:
        return _RECLAIM_FB_DEFAULT_TP1_PCT
    return float(params.get("j_vwap_reclaim_fb_tp1_pct", _RECLAIM_FB_DEFAULT_TP1_PCT))


def vwap_reclaim_failed_break_stop_buffer(params: Optional[dict]) -> float:
    """Isolated chart-stop buffer ($) for edge #2 — ``params#j_vwap_reclaim_fb_stop_buffer``.

    Default 0.25 (Safe-2 ATM cell). Bold sets 0.50. NEVER the global
    ``chart_stop_buffer_dollars``.
    """
    if not params:
        return _RECLAIM_FB_DEFAULT_STOP_BUFFER
    return float(params.get("j_vwap_reclaim_fb_stop_buffer", _RECLAIM_FB_DEFAULT_STOP_BUFFER))


# ─────────────────────────────────────────────────────────────────────────────
# GAMMA-SYNC seam — VIX_REGIME_DAYSIDE (J_VIX_DAYSIDE, edge #4, DORMANT).
#
# OP-4 / "no code drift between live and backtest": the backtest engine must make the
# SAME entry decision as the live heartbeat for this setup. We guarantee that by SINGLE
# SOURCE OF TRUTH — both call the one validated detector
# (lib.watchers.vix_regime_dayside_watcher.detect_vix_regime_dayside_setup), which is itself
# a byte-for-byte port of the research detector
# (autoresearch._b5_vix_regime_dayside.detect_opt_signals / favorable_regime / trend_side).
# The import is FUNCTION-LOCAL (the watcher imports BarContext FROM this file -> a module-top
# import would be circular). DORMANT: detection is pure/read-only; whether the engine HONORS
# the entry is gated by params.j_vix_dayside_enabled (default FALSE), mirroring the heartbeat.
# ─────────────────────────────────────────────────────────────────────────────
def detect_vix_regime_dayside(ctx: "BarContext"):
    """Backtest-engine entry point for VIX_REGIME_DAYSIDE (edge #4).

    Delegates byte-for-byte to the live watcher detector (single source of truth, no drift).
    Returns the watcher's ``WatcherSignal`` (side/entry/chart-stop) or ``None``. Pure/causal:
    reads only ``ctx.prior_bars`` (today's RTH through the trigger bar) + the optional
    ``ctx.vix_intraday`` series for the regime; absent the VIX series it returns None (SKIP).
    """
    from .watchers.vix_regime_dayside_watcher import detect_vix_regime_dayside_setup
    return detect_vix_regime_dayside_setup(ctx)


def vix_dayside_enabled(params: Optional[dict]) -> bool:
    """The DORMANT flag the backtest engine checks before HONORING an edge-#4 entry.

    Mirrors the heartbeat's ``params.json#j_vix_dayside_enabled`` gate (default FALSE = inert).
    Detection always runs (so observation/parity holds), but the entry is acted on only when
    the flag is true.
    """
    if not params:
        return False
    return bool(params.get("j_vix_dayside_enabled", False))


def vix_dayside_side(params: Optional[dict]) -> str:
    """The configured side filter for edge #4 (default 'both' — BOTH sides validated POSITIVE
    @ ATM: C +$47.37/52.1% / P +$38.74/50.0%). Mirrors ``params.json#j_vix_dayside_side``.
    'put' | 'call' | 'both'. OP-16 keeps bull-side new entries DRAFT until 3 live wins, so a
    'both' flip is J's call; 'put' is the OP-16-conservative bear-only first step.
    """
    if not params:
        return "both"
    return str(params.get("j_vix_dayside_side", "both"))


# ── ISOLATED exit knobs (HIGH-1 gamma-sync) ───────────────────────────────────
# The backtest engine MUST honor the SAME isolated stop/tp1 the live heartbeat reads — NOT
# the global premium_stop_pct (-0.50 catastrophe cap) / tp1_premium_pct (0.50), which are the
# WRONG values for this cell. These readers are the single source of truth for "what exit
# does edge #4 use", shared by backtest and (by the matching keys) the heartbeat prose.
# Fallback to the validated ATM ship-cell defaults when the key is absent (older params
# snapshot) so the engine never silently falls back to the catastrophe cap.
_VIX_DAYSIDE_DEFAULT_PREMIUM_STOP_PCT = -0.08   # validated ATM cell stop (the -8% that clears all 8 gates)
_VIX_DAYSIDE_DEFAULT_TP1_PCT = 0.30             # Safe-2 v15 TP1


def vix_dayside_premium_stop_pct(params: Optional[dict]) -> float:
    """Isolated premium stop for edge #4 — ``params#j_vix_dayside_premium_stop_pct``.

    Default -0.08 (the validated cell stop). NEVER the global ``premium_stop_pct`` (-0.50).
    """
    if not params:
        return _VIX_DAYSIDE_DEFAULT_PREMIUM_STOP_PCT
    return float(params.get("j_vix_dayside_premium_stop_pct",
                            _VIX_DAYSIDE_DEFAULT_PREMIUM_STOP_PCT))


def vix_dayside_tp1_pct(params: Optional[dict]) -> float:
    """Isolated TP1 premium % for edge #4 — ``params#j_vix_dayside_tp1_pct``.

    Default 0.30 (Safe-2 ATM cell). NEVER the global ``tp1_premium_pct`` (0.50).
    """
    if not params:
        return _VIX_DAYSIDE_DEFAULT_TP1_PCT
    return float(params.get("j_vix_dayside_tp1_pct", _VIX_DAYSIDE_DEFAULT_TP1_PCT))


# ─────────────────────────────────────────────────────────────────────────────
# GAMMA-SYNC seam — LEVEL_BREAK_FIRST_STRIKE (LBFS, SHADOW-LOGGED 2026-07-15).
#
# OP-4 / "no code drift between live and backtest": the backtest engine must make the
# SAME entry decision as the live heartbeat for this setup. We guarantee that by SINGLE
# SOURCE OF TRUTH — both call the one detector
# (lib.watchers.level_break_first_strike_watcher.detect_lbfs_setup). The import is
# FUNCTION-LOCAL (the watcher imports BarContext FROM this file -> a module-top import
# would be circular; same pattern as detect_vix_regime_dayside/detect_vwap_reclaim_failed_break
# above).
#
# STATUS (2026-07-15 revalidation, analysis/recommendations/
# lbfs-shadow-wiring-revalidation-2026-07-15.json): the existing N=19 VIX>=20 ATM
# real-fills cohort (2026-05-24, re-confirmed byte-identical under today's
# simulate_trade_real) shows a POSITIVE aggregate (WR=58.8%, +$762.60) but FAILS a
# proper chronological walk-forward split (IS +$1,351.80 / OOS -$589.20, wf_ratio=-0.44,
# < the 0.70 bar) — the OOS half is dominated by a 2026-03-24..04-07 cluster. Verdict:
# STUDY_FAILS_BAR_SHIP_SHADOW_ONLY_REGARDLESS. A 2-month extension scan (2026-05-16..
# 2026-07-14) found 26 new MIXED-ribbon-break signals but ZERO at VIX>=20 (no new
# ratifiable-regime evidence). The watcher's own docstring precondition ("3 live J
# observations confirmed") is separately VERIFIED UNMET (0/3; op21_live_confirmed=0
# since the 2026-05-19 registration row, zero journal/self-audit mentions).
#
# SHADOW ONLY: detection is pure/read-only; setup/scripts/setup_dispatch.py dispatches
# it every tick (params.j_lbfs_enabled, default FALSE) so fired/skip_reason is VISIBLE
# in the live decision ledger (core-decisions.jsonl's extra_signals), but
# 'level_break_first_strike' is deliberately ABSENT from params.extra_setup_exec_armed
# -- heartbeat_core._extra_exec_armed therefore returns False unconditionally, so
# _route_extra_setups always logs WATCH_NOT_ARMED and _execute is NEVER called. This
# mirrors double_bottom_base_quiet's 2026-06-28 "WIRED DISARMED" shipping shape
# (setup_dispatch.py's own precedent) — not a new mechanism.
# ─────────────────────────────────────────────────────────────────────────────
def detect_lbfs(ctx: "BarContext"):
    """Backtest-engine entry point for LEVEL_BREAK_FIRST_STRIKE (LBFS).

    Delegates to the live watcher detector (single source of truth, no drift).
    Returns the watcher's ``WatcherSignal`` (side/entry/chart-stop) or ``None``.
    Pure/causal: reads only ``ctx.bar``/``ctx.ribbon_now``/``ctx.vix_now``/
    ``ctx.vix_prior``/``ctx.vol_baseline_20``/``ctx.levels_active``/``ctx.timestamp_et``.
    """
    from .watchers.level_break_first_strike_watcher import detect_lbfs_setup
    return detect_lbfs_setup(ctx)


def lbfs_enabled(params: Optional[dict]) -> bool:
    """The SHADOW flag the backtest engine checks before HONORING an LBFS entry.

    Mirrors the heartbeat's ``params.json#j_lbfs_enabled`` gate. Detection always runs
    when True (so observation/parity holds and the signal is visible in the ledger),
    but per the 2026-07-15 revalidation (STUDY_FAILS_BAR — see the module comment
    above), the entry is NEVER acted on this session: 'level_break_first_strike' is
    deliberately absent from params.extra_setup_exec_armed, so no order can be placed
    regardless of this flag's value. Default False (key absent) = fully inert.
    """
    if not params:
        return False
    return bool(params.get("j_lbfs_enabled", False))


# ─────────────────────────────────────────────────────────────────────────────
# WP-5: per-setup STRIKE override for vwap_continuation (the live edge is at the
#        WRONG strike). SINGLE SOURCE OF TRUTH for "what strike does
#        vwap_continuation use", shared by backtest and (by the matching keys)
#        the heartbeat prose — mirrors the WP-0 isolated-exit-accessor pattern.
#
# THE LEAK (analysis/recommendations/WP5-STRIKE-AB-SCORECARD.md): the ONE live
# edge (vwap_continuation, j_vwap_cont_enabled=true on Safe-2) fires the GENERIC
# v15 OTM-2 tier — the WEAKEST of four cells. Validated cell per account (C29 —
# strikes do NOT transfer across accounts): Safe-2 → ATM, Bold → ITM-2.
#
# CONVENTION (load-bearing — sim-accuracy gate, OP-16): these accessors return the
# offset in the LIVE-PARAMS convention (NEGATIVE=OTM, POSITIVE=ITM, the same
# convention as v15_strike_offset_per_tier): ATM=0, ITM-2=+2, OTM-2=-2. The
# orchestrator/risk_gate translates to the INVERSE simulator_real convention
# (NEGATIVE=ITM) by NEGATING, exactly as the existing per-tier path does
# (orchestrator `kwargs["strike_offset"] = -tier.strike_offset`). The literals
# live ONLY here (single source of truth); risk_gate never re-types them.
#
# ACCOUNT-AWARENESS: params.json IS per-account, so the per-account validated
# offset is carried IN the params file — Safe's params sets
# j_vwap_cont_strike_offset_safe, Bold's sets j_vwap_cont_strike_offset_bold. The
# accessor returns whichever account-specific key is present (Safe key preferred
# when both exist — defensive; in production exactly one is set per file), falling
# back to the validated Safe-2 ATM ship-cell default when neither key is present
# (older snapshot) so the engine never silently picks a wrong strike.
#
# DORMANT: vwap_cont_strike_override_enabled mirrors params.json
# #j_vwap_cont_strike_override_enabled (default FALSE = inert). While FALSE the
# dispatch returns the generic v15 tier UNCHANGED → byte-identical behavior.
# ─────────────────────────────────────────────────────────────────────────────
_VWAP_CONT_STRIKE_OFFSET_DEFAULT = 0   # Safe-2 ATM ship cell (live-params convention)


def vwap_cont_strike_override_enabled(params: Optional[dict]) -> bool:
    """The DORMANT flag gating the WP-5 vwap_continuation per-setup STRIKE override.

    Mirrors ``params.json#j_vwap_cont_strike_override_enabled`` (default FALSE = inert
    → the generic v15 tier strike is used, byte-identical to today). Flip true (in
    daylight, per account) to re-strike vwap_continuation to its validated cell.
    """
    if not params:
        return False
    return bool(params.get("j_vwap_cont_strike_override_enabled", False))


def vwap_cont_strike_offset(params: Optional[dict]) -> int:
    """The validated vwap_continuation strike offset for THIS account (live-params convention).

    LIVE-PARAMS convention (NEGATIVE=OTM, POSITIVE=ITM): ATM=0, ITM-2=+2, OTM-2=-2.
    The caller (risk_gate.select_strike_offset) NEGATES this to the inverse
    simulator_real convention. Reads the account-specific key carried in the params
    file — Safe sets ``j_vwap_cont_strike_offset_safe`` (=0, ATM), Bold sets
    ``j_vwap_cont_strike_offset_bold`` (=2, ITM-2). Safe key preferred when both are
    present (defensive); falls back to the Safe-2 ATM ship-cell default (0) when
    neither is present so an older snapshot never silently picks a wrong strike.
    """
    if not params:
        return _VWAP_CONT_STRIKE_OFFSET_DEFAULT
    if "j_vwap_cont_strike_offset_safe" in params:
        return int(params["j_vwap_cont_strike_offset_safe"])
    if "j_vwap_cont_strike_offset_bold" in params:
        return int(params["j_vwap_cont_strike_offset_bold"])
    return _VWAP_CONT_STRIKE_OFFSET_DEFAULT


# ─────────────────────────────────────────────────────────────────────────────
# WP-8: per-setup 1DTE EXPIRY + DOLLAR-ANCHORED STOP override for vwap_continuation
#        (THE DOUBLING). SINGLE SOURCE OF TRUTH for "what expiry / what stop does
#        vwap_continuation use", shared by backtest and (by the matching keys) the
#        heartbeat prose — the exact mirror of the WP-5 strike accessor pattern above.
#
# THE DOUBLING (validated CLEAN-WIN both tiers, OOS ~2x, maxDD flat/better, Sortino
# +80-123%, 11-gate incl L173): the live edge currently trades a 0DTE contract with a
# -8% PERCENT premium stop. Validated config trades a 1DTE (T+1 expiry) contract with a
# per-account DOLLAR-ANCHORED stop (Safe-2 ATM=$35.88, Bold ITM-2=$67.68) replacing the
# -8% percent stop. These are TWO independent flags (a deployment may flip expiry and
# stop separately) — each defaults FALSE = inert = byte-identical to today.
#
# CONVENTION: the dollar stop is a POSITIVE dollar amount of per-contract premium loss
# tolerated. The accessor just returns the validated per-account magnitude; the resolver
# constructs the bracket. Per-account validated value carried IN the params file (Safe vs
# Bold key), exactly like the strike accessor — Safe sets j_vwap_cont_dollar_stop_safe,
# Bold sets j_vwap_cont_dollar_stop_bold. Safe key preferred when both present (defensive;
# in production exactly one is set per file), falling back to the Safe-2 ATM ship-cell
# default so an older snapshot never silently picks a wrong stop.
#
# DORMANT: both flags mirror params.json (default FALSE = inert). While FALSE the
# resolver returns 0DTE + the -8% percent stop UNCHANGED → byte-identical behavior.
# ─────────────────────────────────────────────────────────────────────────────
_VWAP_CONT_DOLLAR_STOP_DEFAULT = 35.88   # Safe-2 ATM ship cell ($ per-contract premium)


def vwap_cont_1dte_enabled(params: Optional[dict]) -> bool:
    """The DORMANT flag gating the WP-8 vwap_continuation 1DTE-expiry override.

    Mirrors ``params.json#j_vwap_cont_1dte_enabled`` (default FALSE = inert → the order
    path uses the current 0DTE expiry, byte-identical to today). Flip true (in daylight,
    per account) to trade the validated 1DTE contract.
    """
    if not params:
        return False
    return bool(params.get("j_vwap_cont_1dte_enabled", False))


def vwap_cont_dollar_stop_enabled(params: Optional[dict]) -> bool:
    """The DORMANT flag gating the WP-8 vwap_continuation dollar-anchored-stop override.

    Mirrors ``params.json#j_vwap_cont_dollar_stop_enabled`` (default FALSE = inert → the
    order path uses the current -8% percent stop via select_exit_params, byte-identical to
    today). Flip true (in daylight, per account) to use the validated $-anchored stop.
    """
    if not params:
        return False
    return bool(params.get("j_vwap_cont_dollar_stop_enabled", False))


def vwap_cont_dollar_stop(params: Optional[dict]) -> float:
    """The validated vwap_continuation dollar-anchored stop for THIS account.

    Returns a POSITIVE dollar magnitude (per-contract premium loss tolerated). Reads the
    account-specific key carried in the params file — Safe sets
    ``j_vwap_cont_dollar_stop_safe`` (=35.88, ATM), Bold sets
    ``j_vwap_cont_dollar_stop_bold`` (=67.68, ITM-2). Safe key preferred when both are
    present (defensive); falls back to the Safe-2 ATM ship-cell default when neither is
    present so an older snapshot never silently picks a wrong stop.
    """
    if not params:
        return _VWAP_CONT_DOLLAR_STOP_DEFAULT
    if "j_vwap_cont_dollar_stop_safe" in params:
        return float(params["j_vwap_cont_dollar_stop_safe"])
    if "j_vwap_cont_dollar_stop_bold" in params:
        return float(params["j_vwap_cont_dollar_stop_bold"])
    return _VWAP_CONT_DOLLAR_STOP_DEFAULT
