"""chart_patterns -- visual chart pattern primitives.

These are the patterns a human trader sees in milliseconds but the filter-based
heartbeat can't recognize. Each pattern is a pure function over a `Sequence[Bar]`
(closed 5m bars) returning a `PatternHit` (or `None` if no pattern).

The vision-observer L3 layer (`automation/prompts/chart_vision_observer.md`) reads
the chart visually + qualitatively. These primitives complement that by recognizing
patterns NUMERICALLY from OHLCV — they're the "ground truth" against which the
vision observer's qualitative calls get graded.

Patterns implemented:
    double_bottom_detector  -- W reversal at a price level (today 12:30 + 14:30 cases)

Patterns queued for next session (per CLAUDE.md OP-25 engine-benefit autonomy):
    failed_breakdown_wick   -- bar wicks below level, closes back above (today 09:45 + 11:05)
    rejection_at_level      -- bar tests named level from one side, closes back (today 14:00)
    head_and_shoulders      -- 3-peak reversal (not seen today, common on bigger timeframes)
    inside_bar_consolidation -- N consecutive bars within prior bar's range

All detectors operate on CLOSED bars only (per v15.1 R1 + crypto.lib.closed_bar discipline).
Detector consumers MUST filter via `closed_bar.last_closed_bar(...)` before passing in.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal, Sequence

# Import the canonical Bar shape from the existing crypto/lib primitives if available
# Otherwise we use a minimal compatible structural type.
try:
    from crypto.lib.bar import Bar  # type: ignore[import-not-found]
except Exception:  # pragma: no cover -- fallback for testing in isolation
    @dataclass(frozen=True, slots=True)
    class Bar:  # type: ignore[no-redef]
        time: int  # unix seconds (UTC) of bar OPEN time
        open: float
        high: float
        low: float
        close: float
        volume: int


@dataclass(frozen=True, slots=True)
class PatternHit:
    """A detected chart pattern + supporting evidence + bias hint.

    pattern:           machine-readable pattern name (see PATTERN_NAMES below)
    bar_index:         index in the input sequence where pattern COMPLETES
                       (e.g. for double-bottom = neckline-reclaim bar)
    bias:              directional implication ('bullish' | 'bearish' | 'neutral')
    confidence:        0.0-1.0, derived from pattern-specific structural strength
                       (e.g. double-bottom: tighter lows = higher conf)
    key_price:         the structurally-relevant price of the pattern
                       (e.g. the support level both lows tested)
    notes:             free-form structured detail (bar indices of legs, deltas, etc.)
    """
    pattern: str
    bar_index: int
    bias: Literal["bullish", "bearish", "neutral"]
    confidence: float
    key_price: float
    notes: dict


PATTERN_NAMES: tuple[str, ...] = (
    "double_bottom",
    "double_top",
    "failed_breakdown_wick",
    "failed_breakout_wick",
    "rejection_at_level_bullish",
    "rejection_at_level_bearish",
    "head_and_shoulders",
    "inverse_head_and_shoulders",
    "inside_bar_consolidation",
)

# 16-mo backtest (2026-05-18): every detector lifts +2.5–15.5pp when its bias is
# contrary to the 50-bar SMA.  50 bars = ~4 h 10 min on 5-min data — the swing
# horizon that separates intraday trend from intraday counter-move.
CONTRA_REGIME_SMA_LOOKBACK: int = 50


def _is_local_low(bars: Sequence[Bar], i: int) -> bool:
    """A bar is a local low iff its low is strictly less than both neighbors' lows.
    Boundary bars (i==0 or i==len-1) cannot be local lows."""
    if i <= 0 or i >= len(bars) - 1:
        return False
    return bars[i].low < bars[i - 1].low and bars[i].low < bars[i + 1].low


def _is_local_high(bars: Sequence[Bar], i: int) -> bool:
    """A bar is a local high iff its high is strictly greater than both neighbors' highs."""
    if i <= 0 or i >= len(bars) - 1:
        return False
    return bars[i].high > bars[i - 1].high and bars[i].high > bars[i + 1].high


def double_bottom_detector(
    bars: Sequence[Bar],
    *,
    lookback: int = 20,
    tolerance_pct: float = 0.0015,  # default 0.15% = ~$1.10 on SPY @ $735
    min_separation_bars: int = 2,
    min_neckline_rise_pct: float = 0.002,  # neckline must be at least 0.2% above lows
    require_neckline_reclaim: bool = True,
) -> PatternHit | None:
    """Detect a double-bottom (W reversal) in the last `lookback` bars.

    Algorithm:
        1. Find all local lows in the window
        2. If there are >= 2 local lows AND the last two are within `tolerance_pct`
           of each other AND separated by at least `min_separation_bars`, we have
           a candidate double-bottom
        3. Find the highest high BETWEEN the two lows -- the neckline
        4. The neckline must be at least `min_neckline_rise_pct` above the LOWER
           of the two lows (or the pattern is just chop, not a W)
        5. If `require_neckline_reclaim=True`, the latest CLOSED bar must close
           above the neckline -- this is what differentiates "W forming" from
           "W completed + confirmed"

    Confidence calculation:
        Higher conf if:
            - Lows are tighter (closer together)
            - More bars between the two lows (more developed W)
            - Volume on the second low is higher (capitulation + bounce)
            - Neckline reclaim is clean (close well above neckline, not marginal)

    Args:
        bars:                       closed 5m bars (oldest first, newest last)
        lookback:                   how many recent bars to scan (default 20 = ~1h40m on 5m)
        tolerance_pct:              max % distance between the two lows
        min_separation_bars:        min bars between the two lows
        min_neckline_rise_pct:      neckline must be N% above lower low
        require_neckline_reclaim:   if True, only fire on confirmed reclaim

    Returns:
        PatternHit if double-bottom detected, else None.

    Example (today 12:25-12:35 ET):
        12:25 bar  low 734.48   <- low #1
        12:30 bar  low 734.23   <- low #2 (within tolerance of low #1)
                                <- neckline = max(highs between) = 736.86
        12:35 bar  close >735   <- bullish bias once neckline reclaimed
    """
    if len(bars) < min_separation_bars + 2:
        return None

    window = bars[-lookback:] if len(bars) > lookback else bars
    base_offset = len(bars) - len(window)

    # Find all local lows in the window
    local_lows_idx = [i for i in range(len(window)) if _is_local_low(window, i)]
    if len(local_lows_idx) < 2:
        return None

    # Take the last two local lows
    low2_idx = local_lows_idx[-1]
    low1_idx = local_lows_idx[-2]

    if (low2_idx - low1_idx) < min_separation_bars:
        return None

    low1 = window[low1_idx].low
    low2 = window[low2_idx].low
    lower_low = min(low1, low2)

    # Tolerance check: how far apart are the two lows?
    sep_pct = abs(low1 - low2) / max(low1, low2)
    if sep_pct > tolerance_pct:
        return None

    # Neckline = highest high between the two lows (exclusive of the low bars themselves)
    between = window[low1_idx + 1: low2_idx]
    if not between:
        return None
    neckline = max(b.high for b in between)

    # Neckline must rise meaningfully above the lower low (else it's just chop)
    rise_pct = (neckline - lower_low) / lower_low
    if rise_pct < min_neckline_rise_pct:
        return None

    # Reclaim check: latest bar must close above neckline
    latest_close = window[-1].close
    if require_neckline_reclaim and latest_close <= neckline:
        return None

    # Confidence calculation (v2 — RATIFIED 2026-05-18 evening per
    # analysis/CONFIDENCE-RECALIBRATION-DRAFT-2026-05-18.md).
    #
    # v1 used 4 continuous weights (tightness, developed, volume, reclaim).
    # 16-mo backtest revealed: SEPARATION_PCT (SNR 0.04), BARS_BETWEEN (SNR
    # 0.51) and NECKLINE_RISE_PCT (SNR 0.78) are all NOISE — they don't
    # predict next-bar outcome. Result: 0.60-0.70 band (56.3% WR) beat 0.80+
    # band (52.2% WR) — formula was mis-tuned.
    #
    # v2 replaces continuous weights with 5 independent binary-ish factors,
    # each contributing a fixed amount. Each factor must clear a quality
    # threshold to add to conf. Net effect: only the *clearest* W reversals
    # get high conf, instead of "high-conf" rewarding noise.
    bars_between = low2_idx - low1_idx - 1
    reclaim_pct = (latest_close - neckline) / neckline if require_neckline_reclaim else 0.0
    factors = {
        "decisive_reclaim": reclaim_pct > 0.001 if require_neckline_reclaim else False,   # +0.15
        "low2_volume_higher": window[low2_idx].volume > window[low1_idx].volume,           # +0.15
        "bars_between_sweet_spot": 4 <= bars_between <= 12,                                # +0.10
        "very_tight_lows": sep_pct < tolerance_pct * 0.5,                                  # +0.10
        "decent_neckline_height": rise_pct > 0.005,                                        # +0.05
    }
    weights = {
        "decisive_reclaim": 0.15,
        "low2_volume_higher": 0.11,  # v3: OOS N=26 WR=38.5% solo; 0.11 moves single-factor to 0.56 (<0.60 band)
        "bars_between_sweet_spot": 0.10,
        "very_tight_lows": 0.10,
        "decent_neckline_height": 0.05,
    }
    conf = 0.45  # base — every fired pattern earns at least 0.45
    for f, present in factors.items():
        if present:
            conf += weights[f]
    conf = min(1.0, max(0.0, conf))
    confidence_version = "v2"

    return PatternHit(
        pattern="double_bottom",
        bar_index=base_offset + len(window) - 1,  # the latest/reclaim bar
        bias="bullish",
        confidence=round(conf, 3),
        key_price=round(lower_low, 2),
        notes={
            "low1_bar_idx": base_offset + low1_idx,
            "low2_bar_idx": base_offset + low2_idx,
            "low1_price": round(low1, 2),
            "low2_price": round(low2, 2),
            "neckline": round(neckline, 2),
            "bars_between": bars_between,
            "separation_pct": round(sep_pct, 5),
            "neckline_rise_pct": round(rise_pct, 5),
            "low2_volume_higher": window[low2_idx].volume > window[low1_idx].volume,
            "reclaim_pct": round(reclaim_pct, 5),
            "confidence_version": confidence_version,
            "v2_factors_active": [f for f, p in factors.items() if p],
        },
    )


def double_top_detector(
    bars: Sequence[Bar],
    *,
    lookback: int = 20,
    tolerance_pct: float = 0.0015,
    min_separation_bars: int = 2,
    min_neckline_drop_pct: float = 0.002,
    require_neckline_break: bool = True,
) -> PatternHit | None:
    """Mirror of double_bottom_detector for bearish M patterns.

    Two highs near the same price + a trough between + a break below the trough
    (the bearish equivalent of a W's neckline reclaim).

    Example (today's morning if we'd had data):
        09:45 bar  high ~741.0
        10:00 bar  close 740.55, then 10:35 bar dumps through 738
        -- the 739-740 area has two highs from morning, then break-down through trough = double top

    Same args/conf logic as double_bottom_detector, mirrored.
    """
    if len(bars) < min_separation_bars + 2:
        return None

    window = bars[-lookback:] if len(bars) > lookback else bars
    base_offset = len(bars) - len(window)

    local_highs_idx = [i for i in range(len(window)) if _is_local_high(window, i)]
    if len(local_highs_idx) < 2:
        return None

    high2_idx = local_highs_idx[-1]
    high1_idx = local_highs_idx[-2]

    if (high2_idx - high1_idx) < min_separation_bars:
        return None

    high1 = window[high1_idx].high
    high2 = window[high2_idx].high
    upper_high = max(high1, high2)

    sep_pct = abs(high1 - high2) / max(high1, high2)
    if sep_pct > tolerance_pct:
        return None

    between = window[high1_idx + 1: high2_idx]
    if not between:
        return None
    neckline = min(b.low for b in between)  # for M, neckline is the trough

    drop_pct = (upper_high - neckline) / upper_high
    if drop_pct < min_neckline_drop_pct:
        return None

    latest_close = window[-1].close
    if require_neckline_break and latest_close >= neckline:
        return None

    conf = 0.5
    conf += min(0.15, (tolerance_pct - sep_pct) / tolerance_pct * 0.15)
    bars_between = high2_idx - high1_idx - 1
    conf += min(0.10, bars_between / 8.0 * 0.10)
    if window[high2_idx].volume > window[high1_idx].volume:
        conf += 0.10
    if require_neckline_break:
        break_pct = (neckline - latest_close) / neckline
        conf += min(0.15, break_pct / 0.005 * 0.15)
    conf = min(1.0, max(0.0, conf))

    return PatternHit(
        pattern="double_top",
        bar_index=base_offset + len(window) - 1,
        bias="bearish",
        confidence=round(conf, 3),
        key_price=round(upper_high, 2),
        notes={
            "high1_bar_idx": base_offset + high1_idx,
            "high2_bar_idx": base_offset + high2_idx,
            "high1_price": round(high1, 2),
            "high2_price": round(high2, 2),
            "neckline": round(neckline, 2),
            "bars_between": bars_between,
            "separation_pct": round(sep_pct, 5),
            "neckline_drop_pct": round(drop_pct, 5),
            "high2_volume_higher": window[high2_idx].volume > window[high1_idx].volume,
        },
    )


def failed_breakdown_wick(
    bars: Sequence[Bar],
    *,
    lookback_for_support: int = 10,
    min_wick_to_body_ratio: float = 2.0,
    min_close_back_pct: float = 0.0005,  # 0.05% close back above support
    min_volume_mult: float = 1.3,  # 1.3× 10-bar avg volume to count
    support_price: float | None = None,  # v2: explicit named-level price overrides rolling low
) -> PatternHit | None:
    """Detect a failed-breakdown wick on the LATEST closed bar.

    A failed breakdown is the classic bullish-reversal candle:
        - Bar's LOW dips below recent support (rolling 10-bar low)
        - Bar CLOSES back ABOVE that support with a tall lower wick
        - Wick must be at least N× the body (long-tail candle)
        - Optional: volume confirmation (vol ≥ N× recent avg)

    This is the 2026-05-18 09:45 bar EXACTLY:
        open 738.03, high 739.30, LOW 737.56 (broke 738.10 Carry from above), close 738.86 (back above)
        Body = |738.86 - 738.03| = 0.83
        Lower wick = 738.03 - 737.56 = 0.47 (below open, below low side)
        Actually: wick_below = min(open, close) - low = min(738.03, 738.86) - 737.56 = 738.03 - 737.56 = 0.47
        Body = |close - open| = 0.83
        Wick:body = 0.47/0.83 = 0.57 -- doesn't pass our 2.0 threshold by default
        but the structural pattern is there (sweep below support + close above).

    And the 2026-05-15 09:45 bar (the -$770 fast-V):
        open 738.66, high 739.67, LOW 737.96, close 739.65
        Body = 0.99 (green)
        Lower wick = 738.66 - 737.96 = 0.70
        Wick:body = 0.70/0.99 = 0.71 -- borderline; structural sweep is the key signal

    The "sweep" character is more important than the wick ratio. For v2 we'll
    add a `sweep_of_level` variant that takes an explicit support price.
    For v1 we use rolling N-bar low as the "support" proxy.

    Returns None unless the LATEST bar exhibits the pattern.
    """
    if support_price is None and len(bars) < lookback_for_support + 2:
        return None
    if len(bars) < 3:
        return None

    latest = bars[-1]
    # prior bars for volume calculation (always compute from rolling window)
    vol_lookback = min(lookback_for_support, len(bars) - 1)
    prior = bars[-vol_lookback - 1:-1]  # the N bars BEFORE the latest
    if not prior:
        return None

    # Support: explicit named-level price (v2) or rolling low of prior N bars (v1)
    if support_price is not None:
        support = support_price
    else:
        support = min(b.low for b in prior)

    # Must wick BELOW support (sweep) and close BACK ABOVE (reclaim)
    if latest.low >= support:
        return None
    if latest.close <= support:
        return None

    # How far below support did we wick? (sweep depth)
    sweep_depth = support - latest.low
    if sweep_depth <= 0:
        return None

    # How far above support did we close? (reclaim margin)
    close_margin = latest.close - support
    close_margin_pct = close_margin / support
    if close_margin_pct < min_close_back_pct:
        return None  # Reclaim too marginal -- could be a coincidence

    # Wick:body ratio on the lower side
    body = abs(latest.close - latest.open)
    lower_wick = min(latest.open, latest.close) - latest.low
    wick_ratio = lower_wick / body if body > 0 else float("inf")

    # Volume confirmation (optional, used in confidence)
    avg_vol = sum(b.volume for b in prior) / len(prior) if prior else 0
    vol_mult = latest.volume / avg_vol if avg_vol > 0 else 1.0

    # The pattern fires if EITHER:
    # (a) wick ratio is meaningful AND there's volume, OR
    # (b) the close-back margin is strong (>= 0.1%) regardless of wick ratio
    structural_signal = (
        (wick_ratio >= min_wick_to_body_ratio and vol_mult >= min_volume_mult)
        or close_margin_pct >= 0.001
    )
    if not structural_signal:
        return None

    # Confidence
    conf = 0.5
    # Sweep depth (% below support): deeper = more signal but saturates fast
    sweep_pct = sweep_depth / support
    conf += min(0.15, sweep_pct / 0.002 * 0.15)  # saturates at 0.2% depth
    # Reclaim margin
    conf += min(0.15, close_margin_pct / 0.002 * 0.15)  # saturates at 0.2% margin
    # Wick:body
    if body > 0:
        conf += min(0.10, (wick_ratio - 1.0) / 3.0 * 0.10)  # bonus for tall wicks (saturates at 4:1)
    # Volume
    conf += min(0.10, (vol_mult - 1.0) / 2.0 * 0.10)  # bonus for vol >= 3× avg
    conf = min(1.0, max(0.0, conf))

    return PatternHit(
        pattern="failed_breakdown_wick",
        bar_index=len(bars) - 1,
        bias="bullish",
        confidence=round(conf, 3),
        key_price=round(support, 2),
        notes={
            "support_price": round(support, 2),
            "support_source": "named_level" if support_price is not None else "rolling_low",
            "low": round(latest.low, 2),
            "close": round(latest.close, 2),
            "sweep_depth_dollars": round(sweep_depth, 2),
            "sweep_depth_pct": round(sweep_pct, 5),
            "close_back_margin_dollars": round(close_margin, 2),
            "close_back_margin_pct": round(close_margin_pct, 5),
            "lower_wick_dollars": round(lower_wick, 2),
            "body_dollars": round(body, 2),
            "wick_to_body_ratio": round(wick_ratio, 2) if body > 0 else None,
            "volume": latest.volume,
            "avg_prior_volume": round(avg_vol, 0),
            "volume_mult": round(vol_mult, 2),
        },
    )


def rejection_at_level(
    bars: Sequence[Bar],
    *,
    lookback_for_resistance: int = 10,
    min_wick_to_body_ratio: float = 2.0,
    min_close_back_pct: float = 0.0005,
    min_volume_mult: float = 1.3,
    resistance_price: float | None = None,  # v2: explicit named-level price overrides rolling high
) -> PatternHit | None:
    """Detect a rejection-at-level on the LATEST closed bar (bearish mirror of failed_breakdown_wick).

    A rejection-at-resistance is the classic bearish-reversal candle:
        - Bar's HIGH pokes above recent resistance (rolling 10-bar high)
        - Bar CLOSES back BELOW that resistance with a tall upper wick
        - Wick must be at least N× the body
        - Optional: volume confirmation

    This is the 2026-05-18 14:00 bar:
        open 737.04, HIGH 737.14, low 735.81, close 735.87
        (Tested above 737 zone, rejected, closed at low)
        Body = 1.17, Upper wick = 737.14 - 737.04 = 0.10 -- weak by default thresholds
        But the CLOSE back below was strong (-$1.27 from high)
        v1 fires on close-back-margin alone if >= 0.1%

    Returns None unless the LATEST bar exhibits the pattern.
    """
    if resistance_price is None and len(bars) < lookback_for_resistance + 2:
        return None
    if len(bars) < 3:
        return None

    latest = bars[-1]
    # prior bars for volume calculation (always compute from rolling window)
    vol_lookback = min(lookback_for_resistance, len(bars) - 1)
    prior = bars[-vol_lookback - 1:-1]
    if not prior:
        return None

    # Resistance: explicit named-level price (v2) or rolling high of prior N bars (v1)
    if resistance_price is not None:
        resistance = resistance_price
    else:
        resistance = max(b.high for b in prior)

    # Must wick ABOVE resistance (sweep up) and close BACK BELOW (rejection)
    if latest.high <= resistance:
        return None
    if latest.close >= resistance:
        return None

    sweep_height = latest.high - resistance
    if sweep_height <= 0:
        return None

    close_margin = resistance - latest.close
    close_margin_pct = close_margin / resistance
    if close_margin_pct < min_close_back_pct:
        return None

    body = abs(latest.close - latest.open)
    upper_wick = latest.high - max(latest.open, latest.close)
    wick_ratio = upper_wick / body if body > 0 else float("inf")

    avg_vol = sum(b.volume for b in prior) / len(prior) if prior else 0
    vol_mult = latest.volume / avg_vol if avg_vol > 0 else 1.0

    structural_signal = (
        (wick_ratio >= min_wick_to_body_ratio and vol_mult >= min_volume_mult)
        or close_margin_pct >= 0.001
    )
    if not structural_signal:
        return None

    conf = 0.5
    sweep_pct = sweep_height / resistance
    conf += min(0.15, sweep_pct / 0.002 * 0.15)
    conf += min(0.15, close_margin_pct / 0.002 * 0.15)
    if body > 0:
        conf += min(0.10, (wick_ratio - 1.0) / 3.0 * 0.10)
    conf += min(0.10, (vol_mult - 1.0) / 2.0 * 0.10)
    conf = min(1.0, max(0.0, conf))

    return PatternHit(
        pattern="rejection_at_level_bearish",
        bar_index=len(bars) - 1,
        bias="bearish",
        confidence=round(conf, 3),
        key_price=round(resistance, 2),
        notes={
            "resistance_price": round(resistance, 2),
            "resistance_source": "named_level" if resistance_price is not None else "rolling_high",
            "high": round(latest.high, 2),
            "close": round(latest.close, 2),
            "sweep_height_dollars": round(sweep_height, 2),
            "sweep_height_pct": round(sweep_pct, 5),
            "close_back_margin_dollars": round(close_margin, 2),
            "close_back_margin_pct": round(close_margin_pct, 5),
            "upper_wick_dollars": round(upper_wick, 2),
            "body_dollars": round(body, 2),
            "wick_to_body_ratio": round(wick_ratio, 2) if body > 0 else None,
            "volume": latest.volume,
            "avg_prior_volume": round(avg_vol, 0),
            "volume_mult": round(vol_mult, 2),
        },
    )


def momentum_acceleration(
    bars: Sequence[Bar],
    *,
    min_range_mult: float = 2.0,  # latest bar range >= 2× prior 10-bar avg range
    min_volume_mult: float = 2.0,  # latest bar vol >= 2× prior 10-bar avg vol
    min_body_to_range_pct: float = 0.6,  # body fills >=60% of the range (decisive direction)
    lookback: int = 10,
) -> PatternHit | None:
    """Detect single-bar momentum-acceleration on the LATEST closed bar.

    This is the "big reversal candle" / "expansion bar" / "wide-range bar" signal --
    a bar where price RANGE is significantly bigger than recent average AND volume
    is significantly bigger AND the bar closes decisively in one direction (body
    >= 60% of range).

    Example: 2026-05-18 15:00 ET bar:
        open 733.70, high 738.00, LOW 733.61, close 736.38
        Range = 4.39, prior 10-bar avg range ~$1.10 -> 4× expansion
        Body = |736.38 - 733.70| = 2.68 -> 2.68/4.39 = 61% of range (decisive bullish)
        Volume = 328,247, prior 10-bar avg ~80K -> 4.1× spike
        BIAS: bullish (close > open, recovered from session lows)

    Returns None unless the LATEST bar exhibits the pattern.

    Bias logic:
        - If body decisive AND close > open: bullish
        - If body decisive AND close < open: bearish
    """
    if len(bars) < lookback + 2:
        return None

    latest = bars[-1]
    prior = bars[-lookback - 1:-1]
    if not prior:
        return None

    latest_range = latest.high - latest.low
    if latest_range <= 0:
        return None  # Defensive: degenerate bar

    avg_range = sum(b.high - b.low for b in prior) / len(prior)
    if avg_range <= 0:
        return None

    range_mult = latest_range / avg_range
    if range_mult < min_range_mult:
        return None

    body = abs(latest.close - latest.open)
    body_to_range = body / latest_range
    if body_to_range < min_body_to_range_pct:
        return None  # Bar is wide but doji-like (no decisive direction)

    avg_vol = sum(b.volume for b in prior) / len(prior) if prior else 0
    vol_mult = latest.volume / avg_vol if avg_vol > 0 else 1.0
    if vol_mult < min_volume_mult:
        return None  # Wide range without volume = thin-tape spike, less reliable

    # Direction from close vs open
    bias = "bullish" if latest.close > latest.open else "bearish"

    # Confidence
    # Base 0.5; range mult contributes up to +0.20 (saturates at 5×)
    # Vol mult contributes up to +0.15 (saturates at 5×)
    # Body fill contributes up to +0.15 (saturates at 90%)
    conf = 0.5
    conf += min(0.20, (range_mult - min_range_mult) / 3.0 * 0.20)
    conf += min(0.15, (vol_mult - min_volume_mult) / 3.0 * 0.15)
    conf += min(0.15, (body_to_range - min_body_to_range_pct) / 0.3 * 0.15)
    conf = min(1.0, max(0.0, conf))

    return PatternHit(
        pattern="momentum_acceleration",
        bar_index=len(bars) - 1,
        bias=bias,
        confidence=round(conf, 3),
        key_price=round(latest.close, 2),
        notes={
            "open": round(latest.open, 2),
            "high": round(latest.high, 2),
            "low": round(latest.low, 2),
            "close": round(latest.close, 2),
            "range_dollars": round(latest_range, 2),
            "avg_prior_range_dollars": round(avg_range, 2),
            "range_mult": round(range_mult, 2),
            "body_dollars": round(body, 2),
            "body_to_range_pct": round(body_to_range, 3),
            "volume": latest.volume,
            "avg_prior_volume": round(avg_vol, 0),
            "volume_mult": round(vol_mult, 2),
        },
    )


def contra_regime_only(
    hit: PatternHit | None,
    bars: Sequence[Bar],
    sma_lookback: int = 20,
    confidence_boost: float = 0.05,
) -> PatternHit | None:
    """Filter: pass through a hit ONLY if it's contra-trend; otherwise None.

    This is the production-shape primitive for the engine-eyes contra-trend
    edge. The 16-mo backtest (2026-05-18) found every detector lifts
    +2.5 to +15.5pp when its bias is contrary to the prevailing 20-bar SMA.
    A regime-gated detector = base detector + this wrapper.

    Behavior:
        - hit is None                              -> None
        - hit.bias == 'neutral'                    -> pass through unchanged
                                                       (neutral patterns aren't trend-relative)
        - is_contra_trend returns None             -> None (refuse to classify -> no signal)
        - is_contra_trend returns False (aligned)  -> None (filter out the lower-edge cases)
        - is_contra_trend returns True (contra)    -> pass through with pattern name
                                                       suffixed '::contra_regime' + confidence
                                                       boost (default +0.05)

    Args:
        hit: a PatternHit (or None) from any of the underlying detectors.
        bars: trailing bars INCLUDING the hit bar.
        sma_lookback: trend lookback for `is_contra_trend` (default 20).
        confidence_boost: how much to boost confidence on contra-trend hits.
                          Default 0.05 (modest); the 16-mo data justifies up to 0.15
                          for failed_breakdown_wick and rejection_at_level_bearish.

    Returns:
        Annotated PatternHit if contra-trend, else None.
    """
    if hit is None:
        return None
    if hit.bias == "neutral":
        return hit  # consolidation hits pass through; no trend gate applies

    ct = is_contra_trend(hit, bars, sma_lookback=sma_lookback)
    if ct is not True:
        return None  # None (insufficient bars / flat) or False (aligned) both filter out

    # Annotate the hit
    window = bars[-sma_lookback:] if len(bars) >= sma_lookback else bars
    sma = sum(b.close for b in window) / len(window) if window else 0.0
    return PatternHit(
        pattern=f"{hit.pattern}::contra_regime",
        bar_index=hit.bar_index,
        bias=hit.bias,
        confidence=round(min(1.0, hit.confidence + confidence_boost), 3),
        key_price=hit.key_price,
        notes={
            **hit.notes,
            "regime_filter": "contra_trend",
            "sma_lookback": sma_lookback,
            "sma": round(sma, 2),
            "latest_close": round(bars[-1].close, 2) if bars else None,
            "confidence_boost_applied": confidence_boost,
        },
    )


def is_contra_trend(
    hit: PatternHit,
    bars: Sequence[Bar],
    sma_lookback: int = 20,
) -> bool | None:
    """Classify whether a hit's bias is CONTRARY to the prevailing trend.

    Per the 16-mo backtest (2026-05-18 PATTERN-DISAMBIGUATION-16MO doc):
    every detector lifts +2.5pp to +15.5pp when its bias is contra-trend.
    This helper is the building block for a confidence-boost / gating filter
    consumed by the heartbeat scoring rubric.

    Definitions:
        - In an UPTREND (close > SMA): bearish hit = CONTRA-trend (top-call).
        - In a DOWNTREND (close < SMA): bullish hit = CONTRA-trend (bottom-call).
        - Aligned hits (bullish in uptrend, bearish in downtrend) = NOT contra.
        - Neutral hits (e.g. inside-bar consolidation) -> always None.
        - Insufficient history or flat regime -> None.

    Args:
        hit: a PatternHit produced by one of the detectors.
        bars: trailing bars INCLUDING the bar where the hit completes.
        sma_lookback: trend lookback (default 20 = ~100 min on 5m bars,
                      sized for intraday usability).

    Returns:
        True  if the hit goes against the prevailing trend (HIGHER WR).
        False if the hit aligns with the trend (lower WR).
        None  for neutral hits, insufficient bars, or flat regime.
    """
    if hit is None or not bars:
        return None
    if hit.bias == "neutral":
        return None
    if len(bars) < sma_lookback:
        return None

    window = bars[-sma_lookback:]
    sma = sum(b.close for b in window) / len(window)
    latest_close = bars[-1].close

    if latest_close > sma:
        # Uptrend: contra means BEARISH
        return hit.bias == "bearish"
    elif latest_close < sma:
        # Downtrend: contra means BULLISH
        return hit.bias == "bullish"
    return None  # exactly flat


def disambiguate_by_regime(
    hits: Sequence[PatternHit],
    bars: Sequence[Bar],
    sma_lookback: int = 50,
) -> PatternHit | None:
    """Resolve CONFLICTING pattern hits using prevailing trend (regime).

    When two detectors fire on the same bar with OPPOSITE biases (e.g.,
    double_top bearish + failed_breakdown_wick bullish — today's 12:30 ET case),
    the engine has to pick one. Per the 16-mo backtest finding (2026-05-18),
    patterns work +4-15pp BETTER when their bias is CONTRARY to the prevailing
    50-bar trend. So the rule is: **trust the pattern whose bias goes AGAINST
    the trend** (it's a real reversal signal, not noise).

    Disambiguation rules:
        1. If only one hit, return it as-is
        2. If multiple hits all same bias, return the highest-confidence one
        3. If conflicting bullish + bearish hits:
            - In downtrend (close < SMA): trust the BULLISH hit (it's the reversal)
            - In uptrend  (close > SMA): trust the BEARISH hit (it's calling top)
            - In unknown/flat regime: return None (don't pick)
        4. If all neutral, return the most-confident neutral hit (consolidation tag)

    Args:
        hits: pattern detector outputs for the current bar (any subset of detectors)
        bars: all bars including the current one (used for regime calc)
        sma_lookback: trend lookback (default 50 bars)

    Returns:
        The disambiguated PatternHit, or None if no resolution possible.
    """
    if not hits:
        return None
    if len(hits) == 1:
        return hits[0]

    # Group by bias
    bullish = [h for h in hits if h.bias == "bullish"]
    bearish = [h for h in hits if h.bias == "bearish"]
    neutral = [h for h in hits if h.bias == "neutral"]

    # Single direction -> return highest-conf hit
    if bullish and not bearish:
        return max(bullish, key=lambda h: h.confidence)
    if bearish and not bullish:
        return max(bearish, key=lambda h: h.confidence)
    if neutral and not bullish and not bearish:
        return max(neutral, key=lambda h: h.confidence)

    # Conflicting bullish + bearish -- use regime
    if not bars or len(bars) < sma_lookback:
        return None  # Not enough history to classify regime

    window = bars[-sma_lookback:]
    sma = sum(b.close for b in window) / len(window)
    latest_close = bars[-1].close

    if latest_close < sma:
        # Downtrend: trust the BULLISH hit (it's the reversal)
        winner = max(bullish, key=lambda h: h.confidence)
        # Annotate: this is a regime-resolved hit; the loser is in notes
        loser = max(bearish, key=lambda h: h.confidence)
        return PatternHit(
            pattern=f"{winner.pattern}::regime_resolved_downtrend",
            bar_index=winner.bar_index,
            bias=winner.bias,
            confidence=round(min(1.0, winner.confidence + 0.10), 3),  # boost for regime support
            key_price=winner.key_price,
            notes={
                **winner.notes,
                "regime": "downtrend",
                "sma_50": round(sma, 2),
                "current_close": round(latest_close, 2),
                "disambiguation_resolved": True,
                "rejected_pattern": loser.pattern,
                "rejected_bias": loser.bias,
                "rejected_confidence": loser.confidence,
            },
        )
    elif latest_close > sma:
        # Uptrend: trust the BEARISH hit
        winner = max(bearish, key=lambda h: h.confidence)
        loser = max(bullish, key=lambda h: h.confidence)
        return PatternHit(
            pattern=f"{winner.pattern}::regime_resolved_uptrend",
            bar_index=winner.bar_index,
            bias=winner.bias,
            confidence=round(min(1.0, winner.confidence + 0.10), 3),
            key_price=winner.key_price,
            notes={
                **winner.notes,
                "regime": "uptrend",
                "sma_50": round(sma, 2),
                "current_close": round(latest_close, 2),
                "disambiguation_resolved": True,
                "rejected_pattern": loser.pattern,
                "rejected_bias": loser.bias,
                "rejected_confidence": loser.confidence,
            },
        )
    # close == sma: flat regime, refuse to pick
    return None


def inside_bar_consolidation(
    bars: Sequence[Bar],
    *,
    min_consecutive_inside: int = 2,
    lookback: int = 5,
) -> PatternHit | None:
    """Detect inside-bar consolidation -- the chop signature.

    An "inside bar" is one whose high <= prior bar's high AND low >= prior bar's low.
    Multiple consecutive inside bars means price is compressing inside a reference range
    waiting for breakout. NEUTRAL bias (the breakout direction is unknown until it fires).

    Used for: tagging chop periods + helping the live vision observer recognize
    "wait for breakout" regimes.

    Example: today's mid-day 13:30-14:00 ET range 736.62-737.42 -- multiple bars
    inside the 13:10 bar's range.

    Returns None unless the LATEST N bars are all inside the bar before them.
    """
    if len(bars) < min_consecutive_inside + 1:
        return None

    # Check that the latest min_consecutive_inside bars are each inside the bar before them
    # Reference bar = bars[-min_consecutive_inside - 1]
    ref_idx = len(bars) - min_consecutive_inside - 1
    ref_bar = bars[ref_idx]
    inside_count = 0
    for i in range(ref_idx + 1, len(bars)):
        if bars[i].high <= ref_bar.high and bars[i].low >= ref_bar.low:
            inside_count += 1
        else:
            return None  # Sequence broken -- not a clean inside-bar consolidation

    if inside_count < min_consecutive_inside:
        return None

    # Confidence: more consecutive inside bars = tighter compression = more conviction
    # in eventual breakout direction (still neutral bias)
    base_conf = 0.4 + min(0.3, inside_count / 5.0 * 0.3)  # 0.4 - 0.7 range
    ref_range = ref_bar.high - ref_bar.low
    latest_range = bars[-1].high - bars[-1].low
    compression_ratio = latest_range / ref_range if ref_range > 0 else 1.0
    # Tighter compression boost
    base_conf += min(0.2, (1.0 - compression_ratio) * 0.2)
    conf = min(1.0, max(0.0, base_conf))

    return PatternHit(
        pattern="inside_bar_consolidation",
        bar_index=len(bars) - 1,
        bias="neutral",
        confidence=round(conf, 3),
        key_price=round((ref_bar.high + ref_bar.low) / 2, 2),
        notes={
            "ref_bar_idx": ref_idx,
            "ref_bar_high": round(ref_bar.high, 2),
            "ref_bar_low": round(ref_bar.low, 2),
            "ref_bar_range": round(ref_range, 2),
            "consecutive_inside_count": inside_count,
            "latest_bar_range": round(latest_range, 2),
            "compression_ratio": round(compression_ratio, 3),
        },
    )


def head_and_shoulders_detector(
    bars: Sequence[Bar],
    *,
    lookback: int = 30,
    max_shoulder_diff_pct: float = 0.003,  # shoulders must be within 0.3% of each other
    min_head_prominence_pct: float = 0.002,  # head must be ≥ 0.2% above shoulders
    require_neckline_break: bool = True,
) -> PatternHit | None:
    """Detect a classic Head & Shoulders top -- a 3-peak reversal pattern.

    Structure (left to right):
        - Left shoulder  : a local high at price LS
        - Head           : higher local high, price H > LS
        - Right shoulder : another local high, price RS ≈ LS
        - Neckline       : trough between LS-Head and Head-RS, broken downward = trigger

    Bias: BEARISH (top reversal). The inverse (HEAD_AND_SHOULDERS_BOTTOM) is queued.

    Args:
        bars: trailing window of CLOSED bars (lookback recommended ≥ 25)
        lookback: window size to look back for the structure
        max_shoulder_diff_pct: max LS vs RS diff as % of head price (default 0.3%)
        min_head_prominence_pct: head must be ≥ this % above both shoulders
        require_neckline_break: if True, latest bar's close MUST be below neckline

    Returns:
        PatternHit (bearish, pattern='head_and_shoulders_top') or None.

    Note: This is a 5m-scale H&S — useful for 0DTE intraday tops. On 1m or 15m
    timeframes the detector still works (it's lookback-relative, not bar-time
    sensitive); the proper window is just whatever the consumer's data feeds in.
    """
    if len(bars) < lookback:
        return None

    window = list(bars[-lookback:])
    n = len(window)

    # Find local highs (pivot bars) inside the window. A pivot high is a bar
    # whose high is greater than both neighbors (3-bar pivot).
    pivots: list[int] = []
    for i in range(1, n - 1):
        if window[i].high > window[i - 1].high and window[i].high > window[i + 1].high:
            pivots.append(i)

    if len(pivots) < 3:
        return None

    # Try each consecutive triple of pivots as candidate (LS, Head, RS)
    best_hit: PatternHit | None = None
    best_conf = 0.0

    abs_offset = len(bars) - lookback
    for a, b, c in zip(pivots, pivots[1:], pivots[2:]):
        ls_high = window[a].high
        head_high = window[b].high
        rs_high = window[c].high

        # Head must be HIGHEST
        if not (head_high > ls_high and head_high > rs_high):
            continue
        # Head prominence
        if (head_high - max(ls_high, rs_high)) / head_high < min_head_prominence_pct:
            continue
        # Shoulders roughly equal
        if abs(ls_high - rs_high) / head_high > max_shoulder_diff_pct:
            continue

        # Compute neckline = average of the troughs between LS-Head and Head-RS
        trough_lh = min(window[i].low for i in range(a, b + 1))
        trough_hr = min(window[i].low for i in range(b, c + 1))
        neckline = (trough_lh + trough_hr) / 2.0

        # Optionally require the LAST bar's close to break below neckline
        if require_neckline_break and window[-1].close >= neckline:
            continue

        # Confidence: higher when (a) head prominence is bigger, (b) shoulders
        # tighter, (c) neckline break is decisive (close well below neckline).
        prom = (head_high - max(ls_high, rs_high)) / head_high
        shoulder_diff = abs(ls_high - rs_high) / head_high
        neckline_break_pct = (neckline - window[-1].close) / max(neckline, 1e-6)

        base = 0.40
        base += min(0.25, prom * 50)  # 0.2% prominence -> +0.10
        base += min(0.15, (max_shoulder_diff_pct - shoulder_diff) / max_shoulder_diff_pct * 0.15)
        base += min(0.20, max(0.0, neckline_break_pct) * 50)
        conf = round(min(1.0, max(0.0, base)), 3)

        if conf <= best_conf:
            continue
        best_conf = conf

        best_hit = PatternHit(
            pattern="head_and_shoulders_top",
            bar_index=abs_offset + (n - 1),
            bias="bearish",
            confidence=conf,
            key_price=round(neckline, 2),
            notes={
                "left_shoulder_high": round(ls_high, 2),
                "head_high": round(head_high, 2),
                "right_shoulder_high": round(rs_high, 2),
                "left_shoulder_idx": abs_offset + a,
                "head_idx": abs_offset + b,
                "right_shoulder_idx": abs_offset + c,
                "neckline": round(neckline, 2),
                "head_prominence_pct": round(prom * 100, 3),
                "shoulder_diff_pct": round(shoulder_diff * 100, 3),
                "neckline_break_pct": round(neckline_break_pct * 100, 3),
            },
        )

    return best_hit


# ---------------------------------------------------------------------------
# Contra-regime convenience wrappers (OP-25 2026-05-19)
#
# Each wrapper = base detector + CONTRA_REGIME_SMA_LOOKBACK (50-bar) regime gate.
# Returns None when the hit is aligned with the trend (lower-edge case) or when
# the base detector doesn't fire.  Returns an annotated PatternHit with
# pattern="<base>::contra_regime" when the bias is contrary to the 50-bar SMA.
#
# Usage in the heartbeat scoring rubric:
#     hit = contra_double_bottom(bars)  # None when aligned; hit when contra
#
# Use scan_all_contra_regime(bars) to run all 7 detectors in one call.
# ---------------------------------------------------------------------------

def _contra50(hit: PatternHit | None, bars: Sequence[Bar]) -> PatternHit | None:
    """Pass-through only when hit is contra the CONTRA_REGIME_SMA_LOOKBACK (50-bar) trend."""
    return contra_regime_only(hit, bars, sma_lookback=CONTRA_REGIME_SMA_LOOKBACK)


def contra_double_bottom(bars: Sequence[Bar], **kwargs: object) -> PatternHit | None:
    return _contra50(double_bottom_detector(bars, **kwargs), bars)


def contra_double_top(bars: Sequence[Bar], **kwargs: object) -> PatternHit | None:
    return _contra50(double_top_detector(bars, **kwargs), bars)


def contra_failed_breakdown_wick(bars: Sequence[Bar], **kwargs: object) -> PatternHit | None:
    return _contra50(failed_breakdown_wick(bars, **kwargs), bars)


def contra_rejection_at_level(bars: Sequence[Bar], **kwargs: object) -> PatternHit | None:
    return _contra50(rejection_at_level(bars, **kwargs), bars)


def contra_momentum_acceleration(bars: Sequence[Bar], **kwargs: object) -> PatternHit | None:
    return _contra50(momentum_acceleration(bars, **kwargs), bars)


def contra_inside_bar_consolidation(bars: Sequence[Bar], **kwargs: object) -> PatternHit | None:
    return _contra50(inside_bar_consolidation(bars, **kwargs), bars)


def contra_head_and_shoulders(bars: Sequence[Bar], **kwargs: object) -> PatternHit | None:
    return _contra50(head_and_shoulders_detector(bars, **kwargs), bars)


def scan_all_contra_regime(bars: Sequence[Bar]) -> list[PatternHit]:
    """Run all 7 detectors; return only hits that are contra the 50-bar SMA trend.

    NOTE: Two detectors in this scan have NO confirmed edge per the 357-day
    analysis (`analysis/regime-gated-comparison-2026-05-19.md`):
        - contra_double_top: +0.2pp delta — essentially no improvement
        - contra_failed_breakdown_wick: -1.5pp delta — ALIGNED beats CONTRA
          for wick patterns (they're trend-continuation, not reversal, signals)

    Use scan_high_edge_contra_regime() for production code where only
    evidence-backed detectors should fire.  This full-scan version is
    retained for research + completeness audits.
    """
    candidates = [
        contra_double_bottom(bars),
        contra_double_top(bars),
        contra_failed_breakdown_wick(bars),
        contra_rejection_at_level(bars),
        contra_momentum_acceleration(bars),
        contra_inside_bar_consolidation(bars),
        contra_head_and_shoulders(bars),
    ]
    return [h for h in candidates if h is not None]


# Per 357-day backtest (analysis/regime-gated-comparison-2026-05-19.md):
# Only 4 of 7 contra variants showed positive WR lift.  contra_double_top (+0.2pp)
# and contra_failed_breakdown_wick (-1.5pp) are excluded from the recommended set.
_HIGH_EDGE_CONTRA_DETECTORS: tuple[str, ...] = (
    "double_bottom_contra",          # +3.8pp delta, 503 hits / 357 days
    "rejection_at_level_bearish_contra",  # +2.0pp delta, 115 hits / 357 days
    "momentum_acceleration_contra",  # +7.9pp delta, 87 hits / 357 days (highest edge)
    "head_and_shoulders_top_contra", # +21.9pp delta, 8 hits / 357 days (n too thin, watch-only)
)


def scan_high_edge_contra_regime(bars: Sequence[Bar]) -> list[PatternHit]:
    """Run only the 4 contra-regime detectors with confirmed positive WR lift.

    Excludes contra_double_top (no edge) and contra_failed_breakdown_wick
    (inverted edge — wick patterns are trend-continuation, not reversal).

    Per-detector evidence (357-day analysis, 2026-05-19):
        double_bottom_contra              +3.8pp on 503 hits (~1.4/day)
        rejection_at_level_bearish_contra +2.0pp on 115 hits (~0.3/day)
        momentum_acceleration_contra      +7.9pp on 87 hits  (~0.2/day)
        head_and_shoulders_top_contra     +21.9pp on 8 hits  (watch-only, n insufficient)
    """
    candidates = [
        contra_double_bottom(bars),
        contra_rejection_at_level(bars),
        contra_momentum_acceleration(bars),
        contra_head_and_shoulders(bars),
    ]
    return [h for h in candidates if h is not None]


# Near-named-level high-edge pattern set.
# OOS evidence (90-day analysis 2026-05-20, N=87 trading days):
#   head_and_shoulders_top: 61.5% near_named (N=26) vs 48.5% no_named (+13pp) — CONFIRMED OOS
#   momentum_acceleration:  80% near_named (N=5, 19-day run only) — TENTATIVE, pending N≥20
# Excluded from this set (negative or absent proximity evidence):
#   double_top: 20% near named resistance (N=5) — named levels attract breakout buyers
#   inside_bar_consolidation: neutral bias, proximity not applicable
#   failed_breakdown_wick: insufficient proximity sample
_HIGH_EDGE_NEAR_NAMED_PATTERNS: frozenset[str] = frozenset({
    "head_and_shoulders_top",  # +13pp OOS confirmed (N=26) — primary candidate
    "momentum_acceleration",   # +30pp tentative (N=5 only) — include when N≥20 confirmed
})


def scan_high_edge_near_named(
    bars: Sequence[Bar],
    named_levels: Sequence[dict],
    max_distance: float = 0.50,
) -> list[PatternHit]:
    """Run pattern detectors and return only hits near ★★+ named key levels.

    Enriches each candidate hit with ``enrich_hit_with_proximity`` and returns
    only those where ``notes["near_key_level"] is True``.

    Includes only patterns with confirmed or tentative positive OOS proximity lift:

        head_and_shoulders_top: 61.5% near_named (N=26) vs 48.5% no_named (+13pp).
            90-day OOS confirmed (2026-05-20 pattern_backtest run, N=87 days).
        momentum_acceleration:  80% near_named (N=5, 19-day run only). Tentative —
            include when N≥20 confirmed in pattern_backtest named_level_breakdown.

    Excluded (confirmed negative proximity effect):
        double_top: 20% WR near named resistance (N=5) — named levels attract
            breakout buyers who fade the pattern. Proximity HURTS here.
        inside_bar_consolidation: neutral bias, proximity concept inapplicable.
        failed_breakdown_wick: insufficient sample; excluded until evidence grows.

    **Promotion gate (WATCH-ONLY per OP-21):** promote ``head_and_shoulders_top``
    proximity signal to production heartbeat only when pattern_backtest
    ``named_level_breakdown["head_and_shoulders_top::near_named"]`` shows N≥20
    with WR≥58% across ≥10 trading days.  Heartbeat promotion requires Rule 9.

    Args:
        bars:         Chronological closed Bar list (same contract as other detectors).
        named_levels: Sequence of dicts with at minimum ``"price": float`` and
                      ``"stars": int`` keys.  Stars < 2 are ignored.
        max_distance: Dollar proximity gate.  Default $0.50 validated in 2026-05-20
                      19-day named-level comparison run.

    Returns:
        List of PatternHit objects (0–2 typically), each with
        ``notes["near_key_level"] is True`` and ``nearest_key_level_name`` populated.
        Empty list when no ★★+ named level is within ``max_distance`` of any hit.
    """
    candidates = [
        head_and_shoulders_detector(bars),
        momentum_acceleration(bars),
    ]
    hits = [h for h in candidates if h is not None]
    enriched = [enrich_hit_with_proximity(h, named_levels, max_distance) for h in hits]
    return [h for h in enriched if h.notes.get("near_key_level") is True]


def enrich_hit_with_proximity(
    hit: PatternHit,
    named_levels: Sequence[dict],
    max_distance: float = 0.50,
) -> PatternHit:
    """Return a new PatternHit with ``notes["near_key_level"]`` populated.

    ``near_key_level`` is True when the pattern's ``key_price`` is within
    *max_distance* dollars of any ★2+ named level.  False otherwise.

    This is a research enrichment helper: call it in backtesting drivers
    (pattern_backtest.py) to annotate hits with named-level proximity data
    without modifying detector signatures.

    Production heartbeat integration is WATCH-ONLY per OP-21 until promotion
    gate is met: N≥20 ``near_key_level=True`` momentum_acceleration hits with
    ≥65% WR across ≥10 trading days.  Heartbeat promotion requires Rule 9.

    Args:
        hit:          The PatternHit to enrich.  Original is never mutated
                      (PatternHit is frozen=True).
        named_levels: List of level dicts, each with ``"price"`` (float) and
                      ``"stars"`` (int) keys.  Typically from
                      ``_load_named_levels_from_keyjson`` or
                      ``_derive_named_levels`` in pattern_backtest.py.
        max_distance: Dollar proximity threshold.  Default $0.50 matches the
                      threshold validated in the 19-day comparison run
                      (2026-05-20 analysis/named-level-detector-comparison).

    Returns:
        A new PatternHit identical to *hit* except ``notes`` gains
        ``"near_key_level": bool``.  The ``nearest_key_level_name`` and
        ``nearest_key_level_distance`` fields are also populated when True.
    """
    price = hit.key_price
    best_name: str | None = None
    best_dist: float | None = None
    for lvl in named_levels:
        if lvl.get("stars", 0) < 2:
            continue
        d = abs(lvl["price"] - price)
        if d <= max_distance and (best_dist is None or d < best_dist):
            best_dist = d
            best_name = lvl.get("name", "")
    near = best_name is not None
    new_notes: dict = {
        **hit.notes,
        "near_key_level": near,
    }
    if near:
        new_notes["nearest_key_level_name"] = best_name
        new_notes["nearest_key_level_distance"] = round(best_dist, 3)  # type: ignore[arg-type]
    return replace(hit, notes=new_notes)
