"""BEARISH_REJECTION_RIDE_THE_RIBBON — 10-filter setup checklist.

Numerical definitions are sourced from `strategy/chart-anatomy.md` Numerical definitions
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


# Thresholds — pulled from playbook / chart-anatomy / params.
NEWS_FILTER_GRACE_MIN = 15
RIBBON_SPREAD_MIN_CENTS = 30
VIX_BEAR_THRESHOLD = 17.30
VIX_RISING_DEADBAND = 0.05
BREAKDOWN_VOL_MULT = 1.3
VOL_BASELINE_BARS = 20
RANGE_BASELINE_BARS = 20
RIBBON_FLIP_LOOKBACK_BARS = 3
LEVEL_PROXIMITY_DOLLARS = 0.50    # bar must be within $0.50 of a known level to "test" it
CONFLUENCE_TOLERANCE_DOLLARS = 0.30   # multi-day touch within ±$0.30 of today's tested level


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


def buyer_pressure_bar(bar: pd.Series, vol_baseline: float) -> bool:
    """Filter 10 for BULLISH side: green bar with above-average volume.

    Mirror of breakdown_bar_bearish post-relaxation. Used by bullish setup eval.
    """
    if bar["close"] <= bar["open"]:
        return False
    if bar["volume"] < BREAKDOWN_VOL_MULT * vol_baseline:
        return False
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


VIX_BULL_LOW_THRESHOLD = 17.20    # mirror of VIX_BEAR_THRESHOLD (17.30)
VIX_BULL_HARD_CAP = 22.0          # filter 9: VIX < 22 hard


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
    if htf_disagrees and 11 not in disable:
        bull_score = max(0, bull_score - 1)

    return BullishSetupResult(
        passed=(len(blockers) == 0),
        bull_score=bull_score,
        blockers=sorted(blockers),
        triggers_fired=triggers,
        reclaim_level=reclaim_level,
        ribbon_just_flipped_bullish=ribbon_flipped,
        confluence_match=confluence,
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

    # Filter 5: ribbon BEAR-stacked
    if 5 not in disable:
        if ctx.ribbon_now is None or ctx.ribbon_now.stack != "BEAR":
            blockers.append(5)

    # Filter 6: spread >= 30 cents
    if 6 not in disable:
        if ctx.ribbon_now is None or ctx.ribbon_now.spread_cents < RIBBON_SPREAD_MIN_CENTS:
            blockers.append(6)

    # Filter 7: NOT volume_divergence_failed
    if 7 not in disable and volume_divergence_failed(ctx.prior_bars, ctx.bar_idx):
        blockers.append(7)

    # Filter 8: VIX > 17.30 AND vix_rising  (added 2026-05-05; pre-rules historical trades skip this)
    # vix_soft_mode: become a score modifier instead of hard blocker.
    vix_soft_demerit = False
    if 8 not in disable:
        vd = vix_direction(ctx.vix_now, ctx.vix_prior)
        vix_pass = ctx.vix_now > VIX_BEAR_THRESHOLD and vd == "rising"
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
        ctx.bar, ctx.prior_bars, ctx.bar_idx
    )

    # NEW 2026-05-10: wick_rejection trigger (CLAUDE.md OP 17 TDD).
    # Encodes J's 4/29 10:25 setup -- bar pierced level then closed back near it
    # with a significant upper wick, even though close was technically above level.
    # Engine's strict close-below-level missed J's actual entry bar.
    # Verified by tests/test_wick_rejection_trigger.py (4/4 passing).
    wick_level = detect_wick_rejection_bearish(ctx.bar, ctx.levels_active)

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

    if 10 not in disable and len(triggers) < min_triggers:
        blockers.append(10)
    # Defensive: pure ribbon_flip (lagging EMA reorder with no level context) is the
    # weakest trigger class. Require at least one level-tied trigger to avoid pure-
    # confirmation entries.
    elif 10 not in disable:
        level_tied = {"level_rejection", "confluence", "sequence_rejection", "trendline_rejection"}
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
