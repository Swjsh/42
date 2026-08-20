"""multi/lib/filters.py — SYMBOL-PARAMETERIZED fork of the SPY ribbon_ride 0-11 bull/bear
scoring engine (backtest/lib/filters.py).

J directive 2026-08-19 (verbatim): "copy the entire spy engine and then paste it... so you
replicate it. Right? You don't touch the original, and then you make it so we trade other
names... nothing should say hard coded for spy."

THIS IS A FORK, NOT AN IMPORT. This module does not import backtest/lib/filters.py,
backtest/lib/ribbon.py, backtest/lib/structure_shift.py, automation/state/fleet/*, or any
other SPY-lane module — every primitive it needs (ribbon EMAs, ATR, bar geometry, trigger
detectors, the two evaluate_*_setup functions) is copied and re-derived here so a future edit
to the SPY engine can NEVER reach this file, and vice versa.

WHAT WAS DROPPED vs the SPY original (deliberately, not an oversight — see the task report
for the full list): the DORMANT per-edge accessors (VWAP_RECLAIM_FAILED_BREAK, LBFS,
VIX_REGIME_DAYSIDE, the WP-5/WP-8 strike+stop overrides) which delegate to separate SPY
watcher modules not in scope here; the experimental Rule-9-flagged research knobs that default
OFF on SPY too (structure_shift_confirmation, bearish_reversal_bypass, fhh_quality gates,
trendline_bypass_scope variants, allow_one_blocker) — these are SPY-history research artifacts,
not part of the core 0-11 checklist, and every one of them is a no-op at its SPY default. The
core checklist — ribbon stack, spread, volume pressure, breakdown/buyer bar, level rejection/
reclaim, wick rejection/reclaim, trendline rejection/reclaim, ribbon flip, confluence,
sequence rejection/reclaim, pullback-hold, the sweep blocker, and both evaluate_*_setup
functions with their exact filter numbering — is ported in full.

────────────────────────────────────────────────────────────────────────────
THE SPY-DOLLAR -> SYMBOL-RELATIVE CONVERSION (the point of this file)
────────────────────────────────────────────────────────────────────────────
The SPY original hardcodes tolerances in raw dollars, tuned by eye against a ~$700 underlying.
A $0.30 tolerance is 0.04% of SPY at $700 but 0.7% of a $42 stock — same code, wildly
different meaning across a ~70-name universe running from TLT (~$60) to MSTR/COIN-class
high-beta names. Every such constant below is converted to ONE of two symbol-relative bases,
chosen per constant's role:

  * ATR(14)-relative (Wilder, computed live from THIS symbol's own bars — see atr_wilder()):
    used for "how much intrabar noise counts as a real wick/pierce/level-touch" tolerances.
    ATR captures a symbol's OWN realized volatility character directly, which a flat percent
    cannot (a low-price high-volatility name and a high-price calm name can share a price but
    not a wiggle). The multiplier for each constant is chosen to preserve the ORIGINAL
    constant's rough proportion to typical SPY 5-minute intrabar noise — stated here as an
    explicit, flagged ASSUMPTION (not measured empirically this session, since no live
    multi-symbol bars exist yet to calibrate against): REFERENCE_5M_ATR_ASSUMPTION_USD = $0.55.
    This is a documented starting point for A/B validation once real fills exist, not a claim
    of precision — flag it for recalibration.

  * percent-of-price (anchored on the task-given SPY reference price of $700, computed
    dynamically against each bar's own close so it also self-adjusts if a symbol's price
    drifts over time): used for "how far apart are two PRICE LEVELS in absolute terms"
    concepts — ribbon EMA spread and the level-activity proximity band (the latter lives in
    multi/lib/signal.py, the $12 ACTIVE_BAND). These scale with the underlying's price level
    itself, not with short-horizon bar noise — using ATR here would make the ribbon-spread
    gate LOOSER exactly during a VIX spike (when ATR balloons), which is backwards; a flat
    percent of price stays stable through a volatility event.

Every conversion below carries its own comment naming the ORIGINAL SPY dollar constant and
the resulting multiplier. VIX_RISING_DEADBAND and the VIX_* threshold levels are UNCONVERTED
by design — VIX is a market-wide index, not scaled to any one underlying's price, so no
per-symbol conversion applies to it at all (see the VIX REGIME section below for why it is
non-blocking here regardless).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

# ─────────────────────────────────────────────────────────────────────────────
# RIBBON — forked from backtest/lib/ribbon.py. EMA periods are BAR-COUNT based
# (13/20/48 bars), not price-scale — they transfer unchanged across symbols and
# timeframes. Only the SPREAD SIGNIFICANCE THRESHOLD (a dollar distance in the
# original) needed conversion; see RIBBON_SPREAD_MIN_PCT_OF_PRICE below.
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_RIBBON_PERIODS = {"fast_ema": 13, "pivot_ema": 20, "slow_ema": 48}


@dataclass(frozen=True)
class RibbonState:
    """Snapshot of the ribbon at a single bar. `spread_pct` (NEW vs the SPY original) is the
    symbol-relative form of `spread_cents` — spread_cents is kept for shape-familiarity /
    journaling display, but filter comparisons use spread_pct so the gate means the same
    thing on a $40 stock as it does on a $700 one."""
    fast: float
    pivot: float
    slow: float
    spread_cents: float       # max - min across (fast, pivot, slow), in cents (display only)
    spread_pct: float         # spread_cents/100 as a fraction of price — what filters compare
    stack: str                # 'BULL' | 'BEAR' | 'MIXED'

    @property
    def is_bull_stacked(self) -> bool:
        return self.stack == "BULL"

    @property
    def is_bear_stacked(self) -> bool:
        return self.stack == "BEAR"


def ema(closes: pd.Series | np.ndarray, period: int) -> np.ndarray:
    """Standard EMA, SMA-seeded for the first `period` bars (matches TradingView ta.ema)."""
    arr = np.asarray(closes, dtype=float)
    n = len(arr)
    if n < period:
        return np.full(n, np.nan)
    alpha = 2.0 / (period + 1.0)
    out = np.full(n, np.nan)
    out[period - 1] = arr[:period].mean()
    for i in range(period, n):
        out[i] = alpha * arr[i] + (1.0 - alpha) * out[i - 1]
    return out


def compute_ribbon(closes: pd.Series, periods: dict[str, int] | None = None) -> pd.DataFrame:
    """Compute the full ribbon state for every bar. Returns a DataFrame with columns
    fast/pivot/slow/spread_cents/spread_pct/stack, indexed identically to `closes`."""
    if periods is None:
        periods = DEFAULT_RIBBON_PERIODS

    fast = ema(closes, periods["fast_ema"])
    pivot = ema(closes, periods["pivot_ema"])
    slow = ema(closes, periods["slow_ema"])

    df = pd.DataFrame({"fast": fast, "pivot": pivot, "slow": slow}, index=closes.index)

    triple_max = df[["fast", "pivot", "slow"]].max(axis=1)
    triple_min = df[["fast", "pivot", "slow"]].min(axis=1)
    df["spread_cents"] = (triple_max - triple_min) * 100.0
    # spread_pct: symbol-relative — divide by the bar's own close (guard divide-by-zero on a
    # degenerate zero/negative close, which should never happen for real bars but must not
    # raise inside a pure vectorized column op).
    close_arr = np.asarray(closes, dtype=float)
    safe_close = np.where(close_arr > 0, close_arr, np.nan)
    df["spread_pct"] = (triple_max - triple_min) / safe_close

    df["stack"] = "WARMUP"
    valid = df[["fast", "pivot", "slow"]].notna().all(axis=1)
    bull = valid & (df["fast"] > df["pivot"]) & (df["pivot"] > df["slow"])
    bear = valid & (df["fast"] < df["pivot"]) & (df["pivot"] < df["slow"])
    mixed = valid & ~(bull | bear)
    df.loc[bull, "stack"] = "BULL"
    df.loc[bear, "stack"] = "BEAR"
    df.loc[mixed, "stack"] = "MIXED"
    return df


def ribbon_at(ribbon_df: pd.DataFrame, idx) -> Optional[RibbonState]:
    """Return RibbonState at a specific index, or None if not yet warmed up."""
    row = ribbon_df.loc[idx]
    if row["stack"] == "WARMUP" or pd.isna(row["fast"]):
        return None
    return RibbonState(
        fast=float(row["fast"]), pivot=float(row["pivot"]), slow=float(row["slow"]),
        spread_cents=float(row["spread_cents"]),
        spread_pct=float(row["spread_pct"]) if pd.notna(row["spread_pct"]) else 0.0,
        stack=str(row["stack"]),
    )


# ─────────────────────────────────────────────────────────────────────────────
# ATR (Wilder) — the volatility normalizer. Convention (true-range smoothed with Wilder
# alpha, SMA-seeded) matches crypto/lib/indicators.py's existing ATR so the codebase has ONE
# ATR convention, not two — reimplemented here (not imported) per the no-cross-lane-import rule.
# ─────────────────────────────────────────────────────────────────────────────

def true_range_series(bars: pd.DataFrame) -> np.ndarray:
    """True range per bar: max(high-low, |high-prev_close|, |low-prev_close|). First bar
    has no prior close so its TR is just high-low."""
    n = len(bars)
    out = np.full(n, np.nan)
    if n == 0:
        return out
    highs = bars["high"].to_numpy(dtype=float)
    lows = bars["low"].to_numpy(dtype=float)
    closes = bars["close"].to_numpy(dtype=float)
    out[0] = highs[0] - lows[0]
    for i in range(1, n):
        out[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
    return out


def atr_wilder(bars: pd.DataFrame, length: int = 14) -> np.ndarray:
    """Wilder ATR(length). First `length` values are NaN (need `length` true-ranges to seed
    the SMA); value at index `length` is the SMA seed, recursion (Wilder alpha = 1/length)
    from there on."""
    n = len(bars)
    out = np.full(n, np.nan)
    if n <= length:
        return out
    tr = true_range_series(bars)
    seed = float(np.mean(tr[1:length + 1]))
    if np.isnan(seed):
        return out
    out[length] = seed
    for i in range(length + 1, n):
        out[i] = (out[i - 1] * (length - 1) + tr[i]) / length
    return out


ATR_LENGTH_DEFAULT = 14

# Documented, FLAGGED assumption — see the module docstring's conversion section. Not measured
# this session; a starting point for the ATR-relative multipliers below, subject to
# recalibration once real multi-symbol bars are in hand.
REFERENCE_5M_ATR_ASSUMPTION_USD = 0.55   # dollars

# The task's own explicit anchor for percent-of-price conversions (NOT an assumption — given).
REFERENCE_PRICE_ANCHOR_USD = 700.0


# ─────────────────────────────────────────────────────────────────────────────
# THRESHOLDS — every one converted from a SPY-dollar constant. Original value + conversion
# math is in each comment. See module docstring for WHY each uses ATR vs percent-of-price.
# ─────────────────────────────────────────────────────────────────────────────

NEWS_FILTER_GRACE_MIN = 15            # minutes — time-based, symbol-agnostic, unconverted
# was RIBBON_SPREAD_MIN_CENTS=30 (i.e. $0.30) on the source engine at $700 -> percent-of-price
# = 0.30/700
RIBBON_SPREAD_MIN_PCT_OF_PRICE = 0.30 / REFERENCE_PRICE_ANCHOR_USD   # ≈ 0.0429% of price

VIX_BEAR_THRESHOLD = 17.30            # UNCONVERTED — VIX is a market index, not underlying-priced
VIX_RISING_DEADBAND = 0.05            # VIX points — UNCONVERTED, same reasoning
VIX_BULL_LOW_THRESHOLD = 17.20
VIX_BULL_HARD_CAP = 22.0
VIX_PANIC_EXTREME = 30.0              # informational-only threshold for the regime descriptor

VOL_BASELINE_BARS = 20                # bar count — symbol-agnostic, unconverted
RANGE_BASELINE_BARS = 20
RIBBON_FLIP_LOOKBACK_BARS = 3
TRENDLINE_LOOKBACK_BARS = 60
TRENDLINE_MIN_SWINGS = 3
WICK_MIN_PCT_OF_RANGE = 0.50          # ratio of bar range — already symbol-agnostic
PULLBACK_HOLD_MIN_HOLD_BARS = 2
PULLBACK_HOLD_LOOKBACK_BARS = 12

# was CONFLUENCE_TOLERANCE_DOLLARS = 0.30 ("multi-day touch within ±$0.30 of today's level")
# multiplier = 0.30 / REFERENCE_5M_ATR_ASSUMPTION_USD(0.55) ≈ 0.545, rounded to 0.55
CONFLUENCE_TOLERANCE_ATR_MULT = 0.55

# was WICK_MIN_DOLLARS = 0.15 ("upper wick must be >= $0.15")
# multiplier = 0.15 / 0.55 ≈ 0.273, rounded to 0.27
WICK_MIN_ATR_MULT = 0.27

# was WICK_CLOSE_TOLERANCE = 0.10 ("close can be up to $0.10 above level")
# multiplier = 0.10 / 0.55 ≈ 0.182, rounded to 0.18
WICK_CLOSE_TOLERANCE_ATR_MULT = 0.18

# was PULLBACK_HOLD_ZONE_BAND_DOLLARS = 0.30 — doctrine note in the SPY original: "pre-
# registered at the SAME $0.30 width already used for CONFLUENCE_TOLERANCE_DOLLARS rather
# than hand-picked for this detector specifically." We preserve that same-width relationship.
PULLBACK_HOLD_ZONE_BAND_ATR_MULT = CONFLUENCE_TOLERANCE_ATR_MULT

# was detect_candlestick_pattern_bearish(..., proximity: float = 0.30) — the same $0.30
# "near a resistance level" concept as CONFLUENCE_TOLERANCE_DOLLARS; same treatment.
CANDLESTICK_PROXIMITY_ATR_MULT = CONFLUENCE_TOLERANCE_ATR_MULT

# was the inline `abs(state.price - rejection_level) <= 0.05` LevelState price-match tolerance
# (appears twice in the SPY original: once for sequence_rejection, once for sequence_reclaim)
# multiplier = 0.05 / 0.55 ≈ 0.091, rounded to 0.09
LEVEL_STATE_MATCH_ATR_MULT = 0.09

# was detect_fvg's min_gap_dollars = 0.10 -- NOT PORTED. detect_fvg is defined in the SPY
# original but never called by evaluate_bearish_setup/evaluate_bullish_setup (it backs a
# separate watcher module, vwap_reclaim_failed_break_watcher, which is also not ported —
# see the module docstring's "what was dropped" list). Left out of scope deliberately.

# min_wick_pct / min_close_back_pct (sweep detector) and proximity_pct (trendline detector)
# were ALREADY percent-of-price in the SPY original (0.0003, 0.0005, 0.0010) — no conversion
# needed; kept as function default args, unchanged, at their call sites below.


def _atr_tolerance(mult: float, atr_14: float) -> float:
    """ATR-relative tolerance in dollars for THIS symbol's current volatility."""
    return mult * atr_14


def _pct_tolerance(pct_of_price: float, price: float) -> float:
    """Percent-of-price tolerance in dollars for THIS symbol's current price."""
    return pct_of_price * price


def confluence_tolerance(atr_14: float) -> float:
    return _atr_tolerance(CONFLUENCE_TOLERANCE_ATR_MULT, atr_14)


def wick_min_dollars(atr_14: float) -> float:
    return _atr_tolerance(WICK_MIN_ATR_MULT, atr_14)


def wick_close_tolerance(atr_14: float) -> float:
    return _atr_tolerance(WICK_CLOSE_TOLERANCE_ATR_MULT, atr_14)


def pullback_hold_zone_band(atr_14: float) -> float:
    return _atr_tolerance(PULLBACK_HOLD_ZONE_BAND_ATR_MULT, atr_14)


def candlestick_proximity(atr_14: float) -> float:
    return _atr_tolerance(CANDLESTICK_PROXIMITY_ATR_MULT, atr_14)


def level_state_match_tolerance(atr_14: float) -> float:
    return _atr_tolerance(LEVEL_STATE_MATCH_ATR_MULT, atr_14)


def ribbon_spread_min_dollars(price: float) -> float:
    return _pct_tolerance(RIBBON_SPREAD_MIN_PCT_OF_PRICE, price)


# ─────────────────────────────────────────────────────────────────────────────
# STATE / CONTEXT / RESULT DATACLASSES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class LevelState:
    """Per-level state across bars. Tracks role + bounce_history so the engine can detect
    sequence_rejection/sequence_reclaim (3+ progressively-lower-highs / higher-lows)."""
    price: float
    role: Optional[str] = None  # None | "broken_to_resistance" | "broken_to_support"
    broken_at_bar_idx: Optional[int] = None
    bounce_history: list = field(default_factory=list)


@dataclass
class BarContext:
    """Everything needed to evaluate a setup at a single bar, for ONE symbol.

    `symbol` and `atr_14` are the two fields that do NOT exist on the SPY original's
    BarContext — symbol for provenance/journaling (never branched on), atr_14 because it is
    the volatility anchor every converted threshold above reads. Caller (multi/lib/signal.py)
    computes atr_14 from THIS symbol's own bars via atr_wilder() — never a borrowed/shared
    value.
    """
    bar_idx: int
    timestamp_et: dt.datetime
    bar: pd.Series
    prior_bars: pd.DataFrame
    ribbon_now: Optional[RibbonState]
    ribbon_history: list
    vix_now: Optional[float]
    vix_prior: Optional[float]
    vol_baseline_20: float
    range_baseline_20: float
    atr_14: float
    symbol: str
    levels_active: list[float]
    multi_day_levels: list[float]
    htf_15m_stack: Optional[str]
    level_states: dict = field(default_factory=dict)
    fhh_level: Optional[float] = None
    vix_5d_ma: float = 0.0
    vix_20d_ma: float = 0.0


@dataclass
class SetupResult:
    """Output of evaluate_bearish_setup. Shape matches the SPY original's SetupResult plus
    `vix_regime` (new — VIX is logged, never a blocker here) and `symbol`/`candlestick_pattern`
    (new, informational)."""
    passed: bool
    bear_score: int                   # 0..10 — same denominator as the SPY original
    blockers: list[int] = field(default_factory=list)
    triggers_fired: list[str] = field(default_factory=list)
    rejection_level: Optional[float] = None
    ribbon_just_flipped_bearish: bool = False
    confluence_match: Optional[float] = None
    vix_regime: dict = field(default_factory=dict)
    candlestick_pattern: Optional[str] = None
    symbol: str = ""


@dataclass
class BullishSetupResult:
    """Output of evaluate_bullish_setup. Mirror of SetupResult for the bull side."""
    passed: bool
    bull_score: int                   # 0..11 — same denominator as the SPY original
    blockers: list[int] = field(default_factory=list)
    triggers_fired: list[str] = field(default_factory=list)
    reclaim_level: Optional[float] = None
    ribbon_just_flipped_bullish: bool = False
    confluence_match: Optional[float] = None
    vix_regime: dict = field(default_factory=dict)
    symbol: str = ""
    shadow_triggers_fired: list[str] = field(default_factory=list)
    # ^ shadow-logged mirrors (trendline_reclaim / wick_reclaim / pullback_hold), same
    # eval-first precedent as the SPY original: detected + visible, never merged into
    # `triggers_fired` and therefore never able to affect `passed`/`bull_score`.


# ─────────────────────────────────────────────────────────────────────────────
# VIX REGIME — logged, NEVER a hard per-symbol blocker.
#
# WHY: VIX is a market-wide (SPX-options-implied) volatility index. It is a reasonable regime
# input for an index product (SPY tracks the same index VIX is derived from) but a WEAK one
# for a single name — a biotech binary-event day or an idiosyncratic earnings gap can be
# completely decoupled from market-wide VIX in either direction, and a hard VIX gate tuned on
# SPY's own relationship to its own index would silently mis-gate every other symbol in the
# universe for a reason that has nothing to do with that symbol's actual setup. So here VIX
# is computed and attached to every result as `vix_regime` (level/direction/favorability/
# panic-extreme flags) for logging, shadow-scoring, and future per-symbol-beta research — but
# it never appends to `blockers` and never changes `bear_score`/`bull_score`/`passed`.
# ─────────────────────────────────────────────────────────────────────────────

def vix_direction(now: Optional[float], prior: Optional[float]) -> str:
    """rising | falling | flat | unknown — 0.05 deadband (VIX points, unconverted — see above)."""
    if now is None or prior is None:
        return "unknown"
    if now > prior + VIX_RISING_DEADBAND:
        return "rising"
    if now < prior - VIX_RISING_DEADBAND:
        return "falling"
    return "flat"


def compute_vix_regime(
    vix_now: Optional[float], vix_prior: Optional[float],
    vix_5d_ma: float = 0.0, vix_20d_ma: float = 0.0,
) -> dict:
    """Regime descriptor — informational only (see section header). None-safe: a missing VIX
    read (vix_now is None) yields an explicit 'unknown' regime, never a fabricated favorable
    or unfavorable default."""
    if vix_now is None:
        return {
            "level": None, "direction": "unknown", "bear_favorable": None,
            "bull_favorable": None, "panic_extreme": None, "escalating_regime": None,
        }
    direction = vix_direction(vix_now, vix_prior)
    return {
        "level": vix_now,
        "direction": direction,
        "bear_favorable": bool(vix_now > VIX_BEAR_THRESHOLD and direction == "rising"),
        "bull_favorable": bool(vix_now < VIX_BULL_LOW_THRESHOLD or direction == "falling"),
        "panic_extreme": bool(vix_now > VIX_PANIC_EXTREME),
        "escalating_regime": (
            bool(vix_5d_ma > vix_20d_ma) if (vix_5d_ma and vix_20d_ma) else None
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# PER-BAR PREDICATES
# ─────────────────────────────────────────────────────────────────────────────

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


def breakdown_bar_bearish(bar: pd.Series, vol_baseline: float, vol_mult: float = 0.7) -> bool:
    """Seller-pressure bar: red + volume >= vol_mult * 20-bar baseline. vol_mult is already
    relative to THIS symbol's own volume baseline — no dollar/price conversion applies."""
    if bar["close"] >= bar["open"]:
        return False
    if bar["volume"] < vol_mult * vol_baseline:
        return False
    return True


def buyer_pressure_bar(bar: pd.Series, vol_baseline: float, vol_mult: float = 0.7) -> bool:
    """Buyer-pressure bar (bull mirror): green + volume >= vol_mult * 20-bar baseline."""
    if bar["close"] <= bar["open"]:
        return False
    if bar["volume"] < vol_mult * vol_baseline:
        return False
    return True


def _bar_geometry(bar: pd.Series) -> dict:
    """Body/wick percentages for a single bar — ALL ratios (0..1), already symbol-agnostic."""
    high = float(bar["high"]); low = float(bar["low"])
    open_ = float(bar["open"]); close = float(bar["close"])
    rng = high - low
    if rng <= 0:
        return {"body_pct": 0, "upper_wick_pct": 0, "lower_wick_pct": 0,
                "is_red": False, "is_green": False, "range": 0.0}
    body = abs(close - open_)
    upper_wick = high - max(open_, close)
    lower_wick = min(open_, close) - low
    return {
        "body_pct": body / rng, "upper_wick_pct": upper_wick / rng,
        "lower_wick_pct": lower_wick / rng,
        "is_red": close < open_, "is_green": close > open_, "range": rng,
    }


def is_doji(bar: pd.Series) -> bool:
    g = _bar_geometry(bar)
    return g["range"] > 0 and g["body_pct"] < 0.10


def is_shooting_star(bar: pd.Series) -> bool:
    g = _bar_geometry(bar)
    return g["is_red"] and g["upper_wick_pct"] >= 0.50 and g["lower_wick_pct"] <= 0.20 and g["body_pct"] <= 0.30


def is_hammer(bar: pd.Series) -> bool:
    g = _bar_geometry(bar)
    return g["is_green"] and g["lower_wick_pct"] >= 0.50 and g["upper_wick_pct"] <= 0.20 and g["body_pct"] <= 0.30


def is_bearish_marubozu(bar: pd.Series) -> bool:
    g = _bar_geometry(bar)
    return g["is_red"] and g["body_pct"] >= 0.75 and g["upper_wick_pct"] <= 0.10 and g["lower_wick_pct"] <= 0.10


def is_bullish_marubozu(bar: pd.Series) -> bool:
    g = _bar_geometry(bar)
    return g["is_green"] and g["body_pct"] >= 0.75 and g["upper_wick_pct"] <= 0.10 and g["lower_wick_pct"] <= 0.10


def is_decisive_bar(bar: pd.Series, min_body_ratio: float = 0.50) -> bool:
    g = _bar_geometry(bar)
    if g["range"] == 0:
        return False
    return g["body_pct"] >= min_body_ratio


def is_bearish_engulfing(bar_prev: pd.Series, bar_now: pd.Series) -> bool:
    g_prev = _bar_geometry(bar_prev); g_now = _bar_geometry(bar_now)
    if not (g_prev["is_green"] and g_now["is_red"]):
        return False
    if g_now["body_pct"] < 0.50:
        return False
    return float(bar_now["open"]) >= float(bar_prev["close"]) and float(bar_now["close"]) <= float(bar_prev["open"])


def is_bullish_engulfing(bar_prev: pd.Series, bar_now: pd.Series) -> bool:
    g_prev = _bar_geometry(bar_prev); g_now = _bar_geometry(bar_now)
    if not (g_prev["is_red"] and g_now["is_green"]):
        return False
    if g_now["body_pct"] < 0.50:
        return False
    return float(bar_now["open"]) <= float(bar_prev["close"]) and float(bar_now["close"]) >= float(bar_prev["open"])


def detect_candlestick_pattern_bearish(
    bar: pd.Series, bar_prev: Optional[pd.Series], levels_active: list[float],
    bar_close_price: float, atr_14: float,
) -> Optional[str]:
    """Forensic/journaling pattern name only — NOT wired into triggers (matches the SPY
    original's own rollback: candlestick triggers hurt P&L when tried on SPY; kept as
    awareness language). `proximity` (was a bare 0.30 dollar default) is now ATR-relative."""
    if is_bearish_marubozu(bar):
        return "bearish_marubozu"
    proximity = candlestick_proximity(atr_14)
    near_resistance = any(abs(bar_close_price - lvl) <= proximity for lvl in levels_active)
    if not near_resistance:
        return None
    if is_shooting_star(bar):
        return "shooting_star"
    if bar_prev is not None and is_bearish_engulfing(bar_prev, bar):
        return "bearish_engulfing"
    return None


# ─────────────────────────────────────────────────────────────────────────────
# SWEEP DETECTOR — min_wick_pct/min_close_back_pct were ALREADY percent-of-price in the SPY
# original; ported unchanged, no conversion needed.
# ─────────────────────────────────────────────────────────────────────────────

def _detect_sweep_at_level(
    prior_bars: pd.DataFrame, bar_idx: int, level: float, direction: str,
    min_wick_pct: float = 0.0003, min_close_back_pct: float = 0.0005,
    block_window_bars: int = 3, clean_prior_bars: int = 3,
) -> bool:
    wick_threshold = level * min_wick_pct
    close_threshold = level * min_close_back_pct
    look_start = max(0, bar_idx - block_window_bars)
    look_end = bar_idx
    if look_start >= look_end:
        return False
    for sweep_i in range(look_start, look_end):
        sb = prior_bars.iloc[sweep_i]
        sb_h = float(sb["high"]); sb_l = float(sb["low"]); sb_c = float(sb["close"])
        if direction == "bearish":
            if sb_h - level < wick_threshold:
                continue
            if level - sb_c < close_threshold:
                continue
            p_start = max(0, sweep_i - clean_prior_bars); p_end = sweep_i
            if p_end <= p_start:
                continue
            if not all(float(prior_bars.iloc[j]["close"]) < level for j in range(p_start, p_end)):
                continue
            return True
        else:
            if level - sb_l < wick_threshold:
                continue
            if sb_c - level < close_threshold:
                continue
            p_start = max(0, sweep_i - clean_prior_bars); p_end = sweep_i
            if p_end <= p_start:
                continue
            if not all(float(prior_bars.iloc[j]["close"]) > level for j in range(p_start, p_end)):
                continue
            return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# SEQUENCE REJECTION/RECLAIM — pure bounce-history logic, no price constants.
# ─────────────────────────────────────────────────────────────────────────────

def detect_sequence_rejection(level_state: Optional[LevelState]) -> bool:
    if level_state is None or level_state.role != "broken_to_resistance":
        return False
    history = level_state.bounce_history
    if len(history) < 3:
        return False
    last_three = [e["high_reached"] for e in history[-3:]]
    return last_three[0] > last_three[1] > last_three[2]


def detect_sequence_reclaim(level_state: Optional[LevelState]) -> bool:
    if level_state is None or level_state.role != "broken_to_support":
        return False
    history = level_state.bounce_history
    if len(history) < 3:
        return False
    last_three = [e["low_reached"] for e in history[-3:]]
    return last_three[0] < last_three[1] < last_three[2]


def volume_divergence_failed(prior_bars: pd.DataFrame, idx: int) -> bool:
    if idx < 2:
        return False
    candidates = []
    if idx - 1 >= 0:
        candidates.append((idx - 1, idx))
    if idx - 2 >= 0:
        candidates.append((idx - 2, idx - 1))
        candidates.append((idx - 2, idx))
    for bd_idx, rec_idx in candidates:
        bd = prior_bars.iloc[bd_idx]; rec = prior_bars.iloc[rec_idx]
        if bd["close"] >= bd["open"]:
            continue
        if rec["close"] > rec["open"] and rec["volume"] >= bd["volume"]:
            return True
    return False


def _bullish_volume_divergence_failed(prior_bars: pd.DataFrame, idx: int) -> bool:
    if idx < 2:
        return False
    candidates = []
    if idx - 1 >= 0:
        candidates.append((idx - 1, idx))
    if idx - 2 >= 0:
        candidates.append((idx - 2, idx - 1))
        candidates.append((idx - 2, idx))
    for bo_idx, rec_idx in candidates:
        bo = prior_bars.iloc[bo_idx]; rec = prior_bars.iloc[rec_idx]
        if bo["close"] <= bo["open"]:
            continue
        if rec["close"] < rec["open"] and rec["volume"] >= bo["volume"]:
            return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# TRIGGERS
# ─────────────────────────────────────────────────────────────────────────────

def detect_level_rejection(bar: pd.Series, levels_active: list[float]) -> Optional[float]:
    rejected = [lvl for lvl in levels_active if bar["high"] > lvl and bar["close"] < lvl]
    return max(rejected) if rejected else None


def detect_level_reclaim(bar: pd.Series, levels_active: list[float]) -> Optional[float]:
    reclaimed = [lvl for lvl in levels_active if bar["low"] < lvl and bar["close"] > lvl]
    return min(reclaimed) if reclaimed else None


def detect_wick_rejection_bearish(
    bar: pd.Series, levels_active: list[float], atr_14: float,
    min_wick_pct_of_range: float = WICK_MIN_PCT_OF_RANGE,
) -> Optional[float]:
    """Wick rejection of an overhead level even when close is slightly ABOVE it. `min_wick_
    dollars`/`close_tolerance_above_level` (bare $0.15/$0.10 defaults in the SPY original) are
    now derived from atr_14 — see wick_min_dollars()/wick_close_tolerance() above."""
    if not levels_active:
        return None
    high = float(bar["high"]); low = float(bar["low"]); close = float(bar["close"])
    bar_range = high - low
    if bar_range <= 0:
        return None
    upper_wick = high - close
    close_tolerance_above_level = wick_close_tolerance(atr_14)
    candidates = [L for L in levels_active if high >= L and close <= L + close_tolerance_above_level]
    if not candidates:
        return None
    level = max(candidates)
    wick_threshold = max(wick_min_dollars(atr_14), min_wick_pct_of_range * bar_range)
    if upper_wick < wick_threshold:
        return None
    return float(round(level, 4))


def detect_wick_reclaim_bullish(
    bar: pd.Series, levels_active: list[float], atr_14: float,
    min_wick_pct_of_range: float = WICK_MIN_PCT_OF_RANGE,
) -> Optional[float]:
    """Bull mirror of detect_wick_rejection_bearish — SHADOW-LOGGED only in
    evaluate_bullish_setup (matches the SPY original's own eval-first precedent: never wired
    into `triggers`/`bull_score`/`passed` until a Lane-B validation clears it on THIS symbol
    set)."""
    if not levels_active:
        return None
    high = float(bar["high"]); low = float(bar["low"]); close = float(bar["close"])
    bar_range = high - low
    if bar_range <= 0:
        return None
    lower_wick = close - low
    close_tolerance_below_level = wick_close_tolerance(atr_14)
    candidates = [L for L in levels_active if low <= L and close >= L - close_tolerance_below_level]
    if not candidates:
        return None
    level = min(candidates)
    wick_threshold = max(wick_min_dollars(atr_14), min_wick_pct_of_range * bar_range)
    if lower_wick < wick_threshold:
        return None
    return float(round(level, 4))


def _fit_descending_pivots(
    window: pd.DataFrame, min_swings: int, require_decreasing: bool,
) -> Optional[tuple[float, float]]:
    """Shared pivot-fit for the trendline detectors — SEQUENTIAL DESCENDING PEAKS: find the
    global-highest bar, then the next-highest at least MIN_BAR_SEPARATION later, repeat.
    Returns (slope, intercept) of the least-squares line through the pivots, or None."""
    MIN_BAR_SEPARATION = 10
    highs = window["high"].to_numpy(dtype=float)
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
            return None
        recent_pivots.append((pos, val))
        search_start = pos + MIN_BAR_SEPARATION
    if len(recent_pivots) < min_swings:
        return None
    n = len(recent_pivots)
    sum_x = sum(p[0] for p in recent_pivots); sum_y = sum(p[1] for p in recent_pivots)
    sum_xx = sum(p[0] * p[0] for p in recent_pivots); sum_xy = sum(p[0] * p[1] for p in recent_pivots)
    denom = n * sum_xx - sum_x * sum_x
    if denom == 0:
        return None
    slope = (n * sum_xy - sum_x * sum_y) / denom
    intercept = (sum_y - slope * sum_x) / n
    if require_decreasing and slope >= 0:
        return None
    return slope, intercept


def detect_trendline_rejection_bearish(
    bar: pd.Series, prior_bars: pd.DataFrame, bar_idx: int,
    lookback_bars: int = TRENDLINE_LOOKBACK_BARS, min_swings: int = TRENDLINE_MIN_SWINGS,
    proximity_pct: float = 0.0010,  # ALREADY percent-of-price in the SPY original — unchanged
    require_decreasing: bool = True,
) -> Optional[float]:
    if bar_idx < lookback_bars + 2 or prior_bars is None or len(prior_bars) < lookback_bars + 2:
        return None
    start = max(0, bar_idx - lookback_bars)
    window = prior_bars.iloc[start:bar_idx]
    if len(window) < min_swings * 5:
        return None
    fit = _fit_descending_pivots(window, min_swings, require_decreasing)
    if fit is None:
        return None
    slope, intercept = fit
    current_rel_idx = len(window)
    trendline_price = slope * current_rel_idx + intercept
    if trendline_price <= float(bar["close"]):
        return None
    proximity_dollars = trendline_price * proximity_pct
    reached_line = float(bar["high"]) >= (trendline_price - proximity_dollars)
    closed_below = float(bar["close"]) < trendline_price
    is_red = float(bar["close"]) < float(bar["open"])
    if reached_line and closed_below and is_red:
        return float(round(trendline_price, 4))
    return None


def detect_trendline_reclaim_bullish(
    bar: pd.Series, prior_bars: pd.DataFrame, bar_idx: int,
    lookback_bars: int = TRENDLINE_LOOKBACK_BARS, min_swings: int = TRENDLINE_MIN_SWINGS,
    proximity_pct: float = 0.0010, require_decreasing: bool = True,
) -> Optional[float]:
    """Bull mirror (breakout above the SAME descending-high-pivot line) — SHADOW-LOGGED
    only, same precedent as detect_wick_reclaim_bullish."""
    if bar_idx < lookback_bars + 2 or prior_bars is None or len(prior_bars) < lookback_bars + 2:
        return None
    start = max(0, bar_idx - lookback_bars)
    window = prior_bars.iloc[start:bar_idx]
    if len(window) < min_swings * 5:
        return None
    fit = _fit_descending_pivots(window, min_swings, require_decreasing)
    if fit is None:
        return None
    slope, intercept = fit
    current_rel_idx = len(window)
    trendline_price = slope * current_rel_idx + intercept
    if trendline_price >= float(bar["close"]):
        return None
    proximity_dollars = trendline_price * proximity_pct
    reached_line = float(bar["high"]) >= (trendline_price - proximity_dollars)
    closed_above = float(bar["close"]) > trendline_price
    is_green = float(bar["close"]) > float(bar["open"])
    if reached_line and closed_above and is_green:
        return float(round(trendline_price, 4))
    return None


def detect_ribbon_flip_bearish(ribbon_history: list) -> bool:
    if len(ribbon_history) < 2:
        return False
    current = ribbon_history[-1]
    if current is None or current.stack != "BEAR":
        return False
    look = ribbon_history[max(0, len(ribbon_history) - RIBBON_FLIP_LOOKBACK_BARS - 1):-1]
    return any(p is not None and p.stack != "BEAR" for p in look)


def detect_ribbon_flip_bullish(ribbon_history: list) -> bool:
    if len(ribbon_history) < 2:
        return False
    current = ribbon_history[-1]
    if current is None or current.stack != "BULL":
        return False
    look = ribbon_history[max(0, len(ribbon_history) - RIBBON_FLIP_LOOKBACK_BARS - 1):-1]
    return any(p is not None and p.stack != "BULL" for p in look)


def detect_confluence(
    rejection_level: Optional[float], multi_day_levels: list[float], atr_14: float,
) -> Optional[float]:
    """True if the rejected/reclaimed level was also tested in prior days. Tolerance was
    CONFLUENCE_TOLERANCE_DOLLARS=$0.30 in the SPY original — now confluence_tolerance(atr_14)."""
    if rejection_level is None:
        return None
    tol = confluence_tolerance(atr_14)
    for lvl in multi_day_levels:
        if abs(lvl - rejection_level) <= tol:
            return lvl
    return None


def detect_pullback_hold_bullish(
    bar: pd.Series, prior_bars: pd.DataFrame, bar_idx: int, levels_active: list[float],
    atr_14: float, min_hold_bars: int = PULLBACK_HOLD_MIN_HOLD_BARS,
    lookback_bars: int = PULLBACK_HOLD_LOOKBACK_BARS,
) -> Optional[float]:
    """PULLBACK-HOLD bull trigger — SHADOW-LOGGED only (same status as on SPY: Lane-B
    validation pending, never wired into scoring). `zone_band_dollars` (bare $0.30 default in
    the SPY original) is now pullback_hold_zone_band(atr_14)."""
    if bar_idx < min_hold_bars or not levels_active:
        return None
    zone_band_dollars = pullback_hold_zone_band(atr_14)
    approach_start = max(0, bar_idx - lookback_bars)
    approach_end = bar_idx - min_hold_bars
    if approach_end < approach_start:
        return None

    best_level: Optional[float] = None
    best_low_idx: Optional[int] = None
    best_low_value: Optional[float] = None
    for i in range(approach_start, approach_end + 1):
        low_i = float(prior_bars.iloc[i]["low"])
        nearest_level = min(levels_active, key=lambda lvl: abs(low_i - lvl))
        if abs(low_i - nearest_level) > zone_band_dollars:
            continue
        if best_low_value is None or low_i < best_low_value:
            best_low_value = low_i; best_low_idx = i; best_level = nearest_level
    if best_level is None or best_low_idx is None:
        return None

    zone_floor = best_level - zone_band_dollars
    hold_indices = list(range(best_low_idx, bar_idx))
    if len(hold_indices) < min_hold_bars:
        return None

    highest_hold_close = float("-inf")
    for i in hold_indices:
        close_i = float(prior_bars.iloc[i]["close"])
        if close_i < zone_floor:
            return None
        highest_hold_close = max(highest_hold_close, close_i)

    current_close = float(bar["close"])
    if current_close < zone_floor or current_close <= highest_hold_close:
        return None
    return float(round(best_level, 4))


# ─────────────────────────────────────────────────────────────────────────────
# EVALUATE — the two entry points. Filter NUMBERING matches the SPY original exactly (bear
# 1-10 core + optional 11 sweep block; bull 1-11 core + optional 12 sweep block) so anyone
# cross-referencing SPY doctrine finds the same shape here. Filter 8 (bear) / 8+9 (bull) — VIX
# — NEVER append to `blockers`; see the VIX REGIME section above.
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_bearish_setup(
    ctx: BarContext,
    disable_filters: Optional[list[int]] = None,
    min_triggers: int = 1,
    no_trade_before: Optional[dt.time] = None,
    no_trade_window: Optional[tuple] = None,
    f9_vol_mult: float = 0.7,
    sweep_blocker_enabled: bool = False,
    sweep_min_wick_pct: float = 0.0003,
    sweep_min_close_back_pct: float = 0.0005,
    sweep_block_window_bars: int = 3,
    sweep_clean_prior_bars: int = 3,
) -> SetupResult:
    """Run the 10-filter bearish checklist + trigger checks (BEARISH_REJECTION_RIDE_THE_RIBBON,
    symbol-parameterized). See the module docstring for what was intentionally dropped vs the
    SPY original."""
    disable = set(disable_filters or [])
    blockers: list[int] = []
    triggers: list[str] = []
    rejection_level: Optional[float] = None
    ribbon_flipped = False
    confluence: Optional[float] = None

    if ctx.prior_bars is None or len(ctx.prior_bars) == 0 or ctx.bar_idx >= len(ctx.prior_bars):
        raise ValueError(
            f"evaluate_bearish_setup[{ctx.symbol}]: prior_bars is empty or bar_idx out of "
            f"range (bar_idx={ctx.bar_idx}, len={0 if ctx.prior_bars is None else len(ctx.prior_bars)}) "
            f"-- refusing to score on missing/short bar data."
        )

    # Filter 1: time gate
    if 1 not in disable:
        bar_time = ctx.timestamp_et.time()
        if bar_time < dt.time(9, 35):
            blockers.append(1)
        elif no_trade_before is not None and bar_time < no_trade_before:
            blockers.append(1)
        elif no_trade_window is not None:
            windows = [no_trade_window] if isinstance(no_trade_window[0], dt.time) else list(no_trade_window)
            if any(w[0] <= bar_time < w[1] for w in windows):
                blockers.append(1)
    # Filters 2/3/4: news/budget/day-trades stubs — always pass here (execution-layer concern,
    # owned by a sibling module; this file is scoring-only per the HARD RULES).

    # Filter 5: ribbon BEAR-stacked
    if 5 not in disable:
        if ctx.ribbon_now is None or ctx.ribbon_now.stack != "BEAR":
            blockers.append(5)

    # Filter 6: ribbon spread >= threshold (symbol-relative — see ribbon_spread_min_dollars)
    if 6 not in disable:
        price = float(ctx.bar["close"])
        spread_dollars = 0.0 if ctx.ribbon_now is None else ctx.ribbon_now.spread_cents / 100.0
        if ctx.ribbon_now is None or spread_dollars < ribbon_spread_min_dollars(price):
            blockers.append(6)

    # Filter 7: NOT volume_divergence_failed
    if 7 not in disable and volume_divergence_failed(ctx.prior_bars, ctx.bar_idx):
        blockers.append(7)

    # Filter 8: VIX regime — LOGGED ONLY, never blocks (see VIX REGIME section above)
    vix_regime = compute_vix_regime(ctx.vix_now, ctx.vix_prior, ctx.vix_5d_ma, ctx.vix_20d_ma)

    # Filter 9: breakdown_bar_bearish
    if 9 not in disable:
        if ctx.ribbon_now is not None:
            if not breakdown_bar_bearish(ctx.bar, ctx.vol_baseline_20, vol_mult=f9_vol_mult):
                blockers.append(9)
        else:
            blockers.append(9)

    # Filter 10: HTF soft-demerit + >= min_triggers of the trigger set
    htf_disagrees = ctx.htf_15m_stack == "BULL"
    rejection_level = detect_level_rejection(ctx.bar, ctx.levels_active)
    ribbon_flipped = detect_ribbon_flip_bearish(ctx.ribbon_history)
    confluence = detect_confluence(rejection_level, ctx.multi_day_levels, ctx.atr_14)

    wick_level = detect_wick_rejection_bearish(ctx.bar, ctx.levels_active, ctx.atr_14)

    level_state = None
    if rejection_level is not None and ctx.level_states:
        tol = level_state_match_tolerance(ctx.atr_14)
        for state in ctx.level_states.values():
            if abs(state.price - rejection_level) <= tol:
                level_state = state
                break
    sequence_rejected = detect_sequence_rejection(level_state) if level_state else False

    trendline_level = detect_trendline_rejection_bearish(
        ctx.bar, ctx.prior_bars, ctx.bar_idx,
        lookback_bars=TRENDLINE_LOOKBACK_BARS, min_swings=TRENDLINE_MIN_SWINGS,
    )

    bar_prev = ctx.prior_bars.iloc[ctx.bar_idx - 1] if ctx.bar_idx > 0 else None
    candlestick_pattern = detect_candlestick_pattern_bearish(
        ctx.bar, bar_prev, ctx.levels_active, float(ctx.bar["close"]), ctx.atr_14,
    )  # forensic/journaling only — never a trigger

    if rejection_level is not None:
        triggers.append("level_rejection")
    elif wick_level is not None:
        rejection_level = wick_level
        triggers.append("level_rejection")
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

    if 10 not in disable and len(triggers) < min_triggers:
        blockers.append(10)
    elif 10 not in disable:
        level_tied = {"level_rejection", "fhh_level_rejection", "confluence",
                       "sequence_rejection", "trendline_rejection"}
        if not any(t in level_tied for t in triggers):
            blockers.append(10)

    # Filter 11 (optional): sweep blocker — HARD block, cannot be bypassed, matches SPY's
    # own "confluence carve-out" (skip the block if 3+ signals already aligned).
    if (sweep_blocker_enabled and rejection_level is not None
            and "confluence" not in triggers and 11 not in disable):
        if _detect_sweep_at_level(
            ctx.prior_bars, ctx.bar_idx, rejection_level, direction="bullish",
            min_wick_pct=sweep_min_wick_pct, min_close_back_pct=sweep_min_close_back_pct,
            block_window_bars=sweep_block_window_bars, clean_prior_bars=sweep_clean_prior_bars,
        ):
            blockers.append(11)

    bear_score = 10 - len([b for b in blockers if b != 11])
    if 11 in blockers:
        bear_score = 0  # hard structural block, same as the SPY original's sweep-block treatment
    if htf_disagrees and 10 not in disable:
        bear_score = max(0, bear_score - 1)

    return SetupResult(
        passed=(len(blockers) == 0), bear_score=bear_score, blockers=sorted(blockers),
        triggers_fired=triggers, rejection_level=rejection_level,
        ribbon_just_flipped_bearish=ribbon_flipped, confluence_match=confluence,
        vix_regime=vix_regime, candlestick_pattern=candlestick_pattern, symbol=ctx.symbol,
    )


def evaluate_bullish_setup(
    ctx: BarContext,
    disable_filters: Optional[list[int]] = None,
    min_triggers: int = 1,
    no_trade_before: Optional[dt.time] = None,
    no_trade_window: Optional[tuple] = None,
    f10_vol_mult: float = 0.7,
    sweep_blocker_enabled: bool = False,
    sweep_min_wick_pct: float = 0.0003,
    sweep_min_close_back_pct: float = 0.0005,
    sweep_block_window_bars: int = 3,
    sweep_clean_prior_bars: int = 3,
) -> BullishSetupResult:
    """Run the 11-filter bullish checklist + trigger checks (BULLISH_RECLAIM_RIDE_THE_RIBBON,
    symbol-parameterized). Mirror of evaluate_bearish_setup."""
    disable = set(disable_filters or [])
    blockers: list[int] = []
    triggers: list[str] = []
    reclaim_level: Optional[float] = None
    ribbon_flipped = False
    confluence: Optional[float] = None

    if ctx.prior_bars is None or len(ctx.prior_bars) == 0 or ctx.bar_idx >= len(ctx.prior_bars):
        raise ValueError(
            f"evaluate_bullish_setup[{ctx.symbol}]: prior_bars is empty or bar_idx out of "
            f"range (bar_idx={ctx.bar_idx}, len={0 if ctx.prior_bars is None else len(ctx.prior_bars)}) "
            f"-- refusing to score on missing/short bar data."
        )

    # Filter 1: time gate
    if 1 not in disable:
        bar_time = ctx.timestamp_et.time()
        if bar_time < dt.time(9, 35):
            blockers.append(1)
        elif no_trade_before is not None and bar_time < no_trade_before:
            blockers.append(1)
        elif no_trade_window is not None:
            windows = [no_trade_window] if isinstance(no_trade_window[0], dt.time) else list(no_trade_window)
            if any(w[0] <= bar_time < w[1] for w in windows):
                blockers.append(1)
    # Filters 2/3/4: stubs, always pass

    # Filter 5: ribbon BULL-stacked
    if 5 not in disable:
        if ctx.ribbon_now is None or ctx.ribbon_now.stack != "BULL":
            blockers.append(5)

    # Filter 6: ribbon spread >= threshold
    if 6 not in disable:
        price = float(ctx.bar["close"])
        spread_dollars = 0.0 if ctx.ribbon_now is None else ctx.ribbon_now.spread_cents / 100.0
        if ctx.ribbon_now is None or spread_dollars < ribbon_spread_min_dollars(price):
            blockers.append(6)

    # Filter 7: NOT volume_divergence (bull mirror)
    if 7 not in disable and _bullish_volume_divergence_failed(ctx.prior_bars, ctx.bar_idx):
        blockers.append(7)

    # Filters 8 + 9: VIX regime — LOGGED ONLY, never blocks
    vix_regime = compute_vix_regime(ctx.vix_now, ctx.vix_prior, ctx.vix_5d_ma, ctx.vix_20d_ma)

    # Filter 10: buyer pressure
    if 10 not in disable:
        if ctx.ribbon_now is not None:
            if not buyer_pressure_bar(ctx.bar, ctx.vol_baseline_20, vol_mult=f10_vol_mult):
                blockers.append(10)
        else:
            blockers.append(10)

    # Filter 11: HTF soft-demerit + >= min_triggers
    htf_disagrees = ctx.htf_15m_stack == "BEAR"
    reclaim_level = detect_level_reclaim(ctx.bar, ctx.levels_active)
    confluence = detect_confluence(reclaim_level, ctx.multi_day_levels, ctx.atr_14)
    ribbon_flipped = detect_ribbon_flip_bullish(ctx.ribbon_history)

    level_state = None
    if reclaim_level is not None and ctx.level_states:
        tol = level_state_match_tolerance(ctx.atr_14)
        for state in ctx.level_states.values():
            if abs(state.price - reclaim_level) <= tol:
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
        level_tied = {"level_reclaim", "confluence", "sequence_reclaim"}
        if not any(t in level_tied for t in triggers):
            blockers.append(11)

    # Filter 12 (optional): sweep blocker (bull side — blocks on a BEARISH up-sweep)
    if (sweep_blocker_enabled and reclaim_level is not None
            and confluence is None and 12 not in disable):
        if _detect_sweep_at_level(
            ctx.prior_bars, ctx.bar_idx, reclaim_level, direction="bearish",
            min_wick_pct=sweep_min_wick_pct, min_close_back_pct=sweep_min_close_back_pct,
            block_window_bars=sweep_block_window_bars, clean_prior_bars=sweep_clean_prior_bars,
        ):
            blockers.append(12)

    bull_score = 11 - len([b for b in blockers if b != 12])
    if 12 in blockers:
        bull_score = 0
    if htf_disagrees and 11 not in disable:
        bull_score = max(0, bull_score - 1)

    # Shadow-logged bull trigger mirrors — detected + visible, never merged into `triggers`
    shadow_triggers: list[str] = []
    if detect_trendline_reclaim_bullish(
        ctx.bar, ctx.prior_bars, ctx.bar_idx,
        lookback_bars=TRENDLINE_LOOKBACK_BARS, min_swings=TRENDLINE_MIN_SWINGS,
    ) is not None:
        shadow_triggers.append("trendline_reclaim")
    if detect_wick_reclaim_bullish(ctx.bar, ctx.levels_active, ctx.atr_14) is not None:
        shadow_triggers.append("wick_reclaim")
    if detect_pullback_hold_bullish(
        ctx.bar, ctx.prior_bars, ctx.bar_idx, ctx.levels_active, ctx.atr_14,
    ) is not None:
        shadow_triggers.append("pullback_hold")

    return BullishSetupResult(
        passed=(len(blockers) == 0), bull_score=bull_score, blockers=sorted(blockers),
        triggers_fired=triggers, reclaim_level=reclaim_level,
        ribbon_just_flipped_bullish=ribbon_flipped, confluence_match=confluence,
        vix_regime=vix_regime, symbol=ctx.symbol, shadow_triggers_fired=shadow_triggers,
    )
