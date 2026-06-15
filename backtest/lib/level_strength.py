"""Level strength scoring + supporting computations.

Capabilities
------------
- Floor Trader Pivot Points (P, R1-R3, S1-S3) from prior-day RTH H/L/C.
- Opening Range High/Low (ORH/ORL) from first 30 min of RTH.
- Per-level strength score: ★/★★/★★★ derived from touch_count, recency,
  multi-timeframe agreement, and volume-at-level.
- Confluence detection: groups levels within ±$0.30 and bumps strength.
- Distance-from-spot filter: drops levels too far from current price unless
  they're high-tier carry levels.

These are pure functions with explicit inputs. Production callers (the
premarket prompt, EOD task) read bars + invoke these.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

CONFLUENCE_PROXIMITY_USD: float = 0.30
DISTANCE_FROM_SPOT_LIMIT_USD: float = 5.0


# ---------------------------------------------------------------------------
# Floor Trader Pivot Points
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PivotLevels:
    """The 7 floor-trader pivot levels."""
    P: float      # Pivot
    R1: float
    R2: float
    R3: float
    S1: float
    S2: float
    S3: float

    def as_list(self) -> list[tuple[str, float]]:
        return [
            ("R3", self.R3), ("R2", self.R2), ("R1", self.R1),
            ("P", self.P),
            ("S1", self.S1), ("S2", self.S2), ("S3", self.S3),
        ]


def floor_trader_pivots(prior_high: float, prior_low: float, prior_close: float) -> PivotLevels:
    """Compute the 7 floor-trader pivot levels from prior session's HLC.

    Formula (standard floor-trader / classic):
        P  = (H + L + C) / 3
        R1 = 2P - L
        S1 = 2P - H
        R2 = P + (H - L)
        S2 = P - (H - L)
        R3 = H + 2(P - L)
        S3 = L - 2(H - P)

    Use prior-day RTH HLC, NOT full-session (premarket spikes pollute pivots
    same way they pollute pdh — see levels.py 2026-05-08 fix).
    """
    range_hl = prior_high - prior_low
    P = (prior_high + prior_low + prior_close) / 3.0
    R1 = 2 * P - prior_low
    S1 = 2 * P - prior_high
    R2 = P + range_hl
    S2 = P - range_hl
    R3 = prior_high + 2 * (P - prior_low)
    S3 = prior_low - 2 * (prior_high - P)
    return PivotLevels(P=P, R1=R1, R2=R2, R3=R3, S1=S1, S2=S2, S3=S3)


# ---------------------------------------------------------------------------
# Opening Range
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OpeningRange:
    """High/low of the first N minutes of RTH."""
    high: float
    low: float
    high_bar_time: dt.datetime
    low_bar_time: dt.datetime
    minutes: int


def opening_range(today_rth_bars: pd.DataFrame, minutes: int = 30) -> OpeningRange | None:
    """Compute the opening range high/low from first N minutes of RTH.

    Args:
        today_rth_bars: DataFrame with `timestamp_et` (datetime), `high`, `low`.
            Must be filtered to today's RTH already (>= 09:30 ET).
        minutes: opening range window (default 30 — covers 6× 5-min bars).

    Returns None if not enough bars yet (e.g., before 10:00 ET).
    """
    if today_rth_bars.empty:
        return None
    df = today_rth_bars.copy()
    df = df.sort_values("timestamp_et").reset_index(drop=True)
    open_time = df["timestamp_et"].iloc[0]
    cutoff = open_time + pd.Timedelta(minutes=minutes)
    window = df[df["timestamp_et"] < cutoff]
    if len(window) < (minutes // 5):
        return None
    high_idx = int(window["high"].idxmax())
    low_idx = int(window["low"].idxmin())
    return OpeningRange(
        high=float(window["high"].max()),
        low=float(window["low"].min()),
        high_bar_time=window["timestamp_et"].iloc[high_idx].to_pydatetime() if hasattr(window["timestamp_et"].iloc[high_idx], "to_pydatetime") else window["timestamp_et"].iloc[high_idx],
        low_bar_time=window["timestamp_et"].iloc[low_idx].to_pydatetime() if hasattr(window["timestamp_et"].iloc[low_idx], "to_pydatetime") else window["timestamp_et"].iloc[low_idx],
        minutes=minutes,
    )


# ---------------------------------------------------------------------------
# Touch counting
# ---------------------------------------------------------------------------

@dataclass
class TouchStats:
    """Per-level test history derived from a bar series.

    A "touch" is a bar whose high or low came within `tolerance_usd` of the level.
    `held_count` = touches that closed back away from the level (rejection).
    `broken_count` = touches that closed past the level (penetration).
    `volume_at_touches` = sum of bar volumes for touch bars.
    """
    touch_count: int = 0
    held_count: int = 0
    broken_count: int = 0
    volume_at_touches: float = 0.0
    last_touched_at: dt.datetime | None = None


def count_touches(
    bars: pd.DataFrame,
    level_price: float,
    tolerance_usd: float = 0.10,
    timestamp_col: str = "timestamp_et",
    high_col: str = "high",
    low_col: str = "low",
    close_col: str = "close",
    volume_col: str = "volume",
) -> TouchStats:
    """Count how many bars touched `level_price` within tolerance.

    Hold = bar tagged the level but closed away from it (rejection).
    Break = bar closed on the opposite side of where it started relative to level.

    Simple heuristic — for full sequence-tracking use orchestrator's level_states.
    """
    if bars.empty:
        return TouchStats()
    stats = TouchStats()
    for _, bar in bars.iterrows():
        high = float(bar[high_col])
        low = float(bar[low_col])
        close = float(bar[close_col])
        vol = float(bar[volume_col]) if volume_col in bars.columns else 0.0
        # Did high or low touch the level (within tolerance)?
        touched = (low <= level_price + tolerance_usd) and (high >= level_price - tolerance_usd)
        if not touched:
            continue
        stats.touch_count += 1
        stats.volume_at_touches += vol
        ts = bar[timestamp_col]
        if hasattr(ts, "to_pydatetime"):
            ts = ts.to_pydatetime()
        if stats.last_touched_at is None or ts > stats.last_touched_at:
            stats.last_touched_at = ts
        # Hold vs break: did the close move away from the level (hold) or past it (break)?
        # If level is above the open, a close > level = break upward; close < level = hold.
        # If level is below the open, mirror.
        open_v = float(bar.get("open", close))
        if open_v < level_price:
            if close > level_price + tolerance_usd:
                stats.broken_count += 1
            else:
                stats.held_count += 1
        elif open_v > level_price:
            if close < level_price - tolerance_usd:
                stats.broken_count += 1
            else:
                stats.held_count += 1
    return stats


# ---------------------------------------------------------------------------
# Strength scoring
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StrengthComponents:
    """Per-component contribution to a level's strength score."""
    touch_score: float    # 0-2.0: log2 curve (T54 2026-05-17) — diminishing returns
    recency_score: int    # 0-2: based on recency_days
    mtf_score: int        # 0-2: based on multi-timeframe agreement
    volume_score: int     # 0-1: based on volume_at_touches vs avg
    confluence_score: int # 0-3: T55 2026-05-16 — count-based cluster depth
    ema_alignment_score: int = 0  # 0-1: T56 2026-05-17 — within $0.30 of Fast/Pivot/Slow EMA

    def total_points(self) -> float:
        return (self.touch_score + self.recency_score + self.mtf_score
                + self.volume_score + self.confluence_score + self.ema_alignment_score)

    def stars(self) -> int:
        """Convert points to 1-3 star rating.
        0-2.9 points → 1 star (weak)
        3.0-4.9 points → 2 stars (medium)
        5.0-9.0 points → 3 stars (strong)
        """
        p = self.total_points()
        if p >= 5.0:
            return 3
        if p >= 3.0:
            return 2
        return 1


def score_level(
    touch_count: int,
    recency_days: float | None,
    mtf_agreement: int,        # 1 = 5m only, 2 = 5m+15m, 3 = 5m+15m+1D
    volume_at_touches: float,
    avg_volume: float,
    confluent_with_count: int = 0,
    level_price: float | None = None,
    ema_values: list[float] | None = None,
    ema_proximity_usd: float = 0.30,
) -> StrengthComponents:
    """Compute strength components from raw inputs.

    Calibrated to give ★★★ to levels that show up on the chart frequently with
    sustained respect, and ★ to levels with thin evidence.

    Optional T56 args:
      level_price: the level's absolute price (e.g. 748.50)
      ema_values: current Fast/Pivot/Slow EMA prices from the ribbon
      ema_proximity_usd: distance threshold for EMA alignment (default $0.30)

    If level_price and ema_values are both provided, adds +1 ema_alignment_score
    when any EMA is within ema_proximity_usd of the level.  This rewards levels
    where S/R and the trend ribbon coincide — a strong institutional reference.
    """
    # Touch score — T54 2026-05-17: log2 diminishing-returns curve.
    # Formula: touch_score = min(0.5 * log2(touch_count + 1), 2.0)
    # This replaces the old integer step-function (0 / 1 / 2) with a smooth float curve:
    #   touch_count=0  → 0.000  (no touches  = no signal)
    #   touch_count=1  → 0.500  (one touch   = weak signal)
    #   touch_count=2  → 0.792  (two touches = building)
    #   touch_count=3  → 1.000  (three       = meaningful)
    #   touch_count=5  → 1.292  (five        = solid)
    #   touch_count=7  → 1.500  (seven       = strong)
    #   touch_count=15 → 2.000  (fifteen     = max, same as old "≥5" floor)
    #   touch_count=20 → 2.000  (capped at 2)
    # Old step-function gave touch=2 for touch_count=3 AND touch_count=100 identically.
    # New curve differentiates them while preserving the 2.0 max cap.
    touch = round(min(0.5 * math.log2(touch_count + 1), 2.0), 3)

    # Recency
    if recency_days is None:
        recency = 0
    elif recency_days <= 1:
        recency = 2
    elif recency_days <= 5:
        recency = 1
    else:
        recency = 0

    # MTF
    if mtf_agreement >= 3:
        mtf = 2
    elif mtf_agreement >= 2:
        mtf = 1
    else:
        mtf = 0

    # Volume
    if avg_volume > 0 and volume_at_touches >= avg_volume * 1.5:
        volume = 1
    else:
        volume = 0

    # Confluence — NEW 2026-05-16 T55: count-based, not binary.
    # 2-level cluster → 1 pt. 3-level cluster → 2 pts. 4+ level cluster → 3 pts.
    # Previously: any confluence = 1 pt (binary). Binary under-rewards tight clusters
    # where 4 levels stack within $0.30 (e.g. PDH + ORH + POC + aVWAP confluence =
    # very high-conviction zone, should score meaningfully higher than a 2-level pair).
    # `confluent_with_count` = number of OTHER nearby levels (0 if isolated).
    confluence = min(confluent_with_count, 3)

    # EMA alignment — T56 2026-05-17: +1 if level is within $0.30 of any ribbon EMA.
    # Rationale: when a static S/R level coincides with a dynamic EMA (trend mean),
    # institutional models see it as double-confirmed support/resistance.
    # Example: PDH at 748.50, Fast EMA at 748.35 → gap = $0.15 ≤ $0.30 → ema_alignment=1.
    # Requires caller to pass both level_price and ema_values; backward-compat defaults to 0.
    if level_price is not None and ema_values:
        ema_alignment = 1 if any(
            abs(level_price - ema) <= ema_proximity_usd for ema in ema_values
        ) else 0
    else:
        ema_alignment = 0

    return StrengthComponents(
        touch_score=touch, recency_score=recency, mtf_score=mtf,
        volume_score=volume, confluence_score=confluence,
        ema_alignment_score=ema_alignment,
    )


# ---------------------------------------------------------------------------
# Confluence detection
# ---------------------------------------------------------------------------

@dataclass
class ConfluenceGroup:
    """Levels that cluster within `proximity_usd`."""
    center_price: float
    member_prices: list[float] = field(default_factory=list)
    member_ids: list[str] = field(default_factory=list)


def find_confluences(
    levels: list[dict],
    proximity_usd: float = CONFLUENCE_PROXIMITY_USD,
    price_key: str = "price",
    id_key: str = "entity_id",
) -> list[ConfluenceGroup]:
    """Group levels that lie within proximity_usd of each other.

    Returns groups of size >= 2 only. Single-member levels are not "confluent".
    """
    if not levels:
        return []
    sorted_levels = sorted(levels, key=lambda lv: lv[price_key])
    groups: list[ConfluenceGroup] = []
    current = ConfluenceGroup(
        center_price=sorted_levels[0][price_key],
        member_prices=[sorted_levels[0][price_key]],
        member_ids=[sorted_levels[0].get(id_key, "?")],
    )
    for lv in sorted_levels[1:]:
        if lv[price_key] - current.member_prices[-1] <= proximity_usd:
            current.member_prices.append(lv[price_key])
            current.member_ids.append(lv.get(id_key, "?"))
            current.center_price = sum(current.member_prices) / len(current.member_prices)
        else:
            if len(current.member_prices) >= 2:
                groups.append(current)
            current = ConfluenceGroup(
                center_price=lv[price_key],
                member_prices=[lv[price_key]],
                member_ids=[lv.get(id_key, "?")],
            )
    if len(current.member_prices) >= 2:
        groups.append(current)
    return groups


# ---------------------------------------------------------------------------
# Distance filter
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Volume-derived levels: VWAP, Anchored VWAP, Volume Profile (POC/VAH/VAL)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class VWAPSnapshot:
    """Volume-weighted average price + standard deviation bands."""
    vwap: float
    upper_1sigma: float
    lower_1sigma: float
    upper_2sigma: float
    lower_2sigma: float
    bars_in_calc: int


def compute_vwap(
    bars: pd.DataFrame,
    high_col: str = "high",
    low_col: str = "low",
    close_col: str = "close",
    volume_col: str = "volume",
) -> VWAPSnapshot | None:
    """Volume-weighted average price + ±1σ/±2σ bands from a bar series.

    Use today's RTH bars only for "today's VWAP". For an Anchored VWAP, slice
    the bar series at the anchor and call this function.
    """
    if bars.empty or volume_col not in bars.columns:
        return None
    typical = (bars[high_col] + bars[low_col] + bars[close_col]) / 3.0
    volume = bars[volume_col].astype(float)
    if volume.sum() <= 0:
        return None
    cum_pv = (typical * volume).cumsum()
    cum_v = volume.cumsum()
    vwap_series = cum_pv / cum_v
    final_vwap = float(vwap_series.iloc[-1])
    # Stdev of typical-price weighted by volume
    weighted_var = (((typical - final_vwap) ** 2) * volume).sum() / volume.sum()
    stdev = float(weighted_var ** 0.5)
    return VWAPSnapshot(
        vwap=final_vwap,
        upper_1sigma=final_vwap + stdev,
        lower_1sigma=final_vwap - stdev,
        upper_2sigma=final_vwap + 2 * stdev,
        lower_2sigma=final_vwap - 2 * stdev,
        bars_in_calc=int(len(bars)),
    )


@dataclass(frozen=True)
class VolumeProfile:
    """Discretized volume-by-price profile: POC, VAH/VAL, HVN/LVN."""
    poc: float       # Point of Control (price with highest volume)
    vah: float       # Value Area High (top of 70%-volume bracket)
    val: float       # Value Area Low (bottom of 70%-volume bracket)
    bucket_size_usd: float
    total_volume: float
    profile: list[tuple[float, float]]  # [(price_bucket_center, volume), ...]


def compute_volume_profile(
    bars: pd.DataFrame,
    bucket_size_usd: float = 0.10,
    value_area_pct: float = 0.70,
    high_col: str = "high",
    low_col: str = "low",
    volume_col: str = "volume",
) -> VolumeProfile | None:
    """Build a volume profile from bars by allocating each bar's volume across
    its price range (high to low), bucketed at `bucket_size_usd`.

    Uniform allocation per bucket within the bar's range — a standard simplification.
    """
    if bars.empty or volume_col not in bars.columns:
        return None
    profile: dict[float, float] = {}
    for _, bar in bars.iterrows():
        h = float(bar[high_col])
        l = float(bar[low_col])
        v = float(bar[volume_col])
        if v <= 0:
            continue
        n_buckets = max(1, int(round((h - l) / bucket_size_usd)) + 1)
        per_bucket = v / n_buckets
        for i in range(n_buckets):
            center = round(l + i * bucket_size_usd, 4)
            profile[center] = profile.get(center, 0.0) + per_bucket
    if not profile:
        return None
    sorted_profile = sorted(profile.items(), key=lambda kv: -kv[1])
    poc_price, _poc_vol = sorted_profile[0]
    total_vol = sum(profile.values())
    target = total_vol * value_area_pct
    accumulated = 0.0
    in_va: list[float] = []
    for price, vol in sorted_profile:
        in_va.append(price)
        accumulated += vol
        if accumulated >= target:
            break
    vah = max(in_va)
    val = min(in_va)
    return VolumeProfile(
        poc=poc_price, vah=vah, val=val,
        bucket_size_usd=bucket_size_usd,
        total_volume=total_vol,
        profile=sorted(profile.items()),
    )


def filter_by_distance(
    levels: list[dict],
    spot: float,
    limit_usd: float = DISTANCE_FROM_SPOT_LIMIT_USD,
    keep_tiers: tuple[str, ...] = ("Carry", "Reference"),
) -> tuple[list[dict], list[dict]]:
    """Split levels into (kept, dropped) based on distance from spot.

    Levels with tier in `keep_tiers` survive regardless of distance — they're
    the deep-context anchors that need to be visible if a multi-day move kicks in.
    """
    kept: list[dict] = []
    dropped: list[dict] = []
    for lv in levels:
        if lv.get("tier") in keep_tiers:
            kept.append(lv)
            continue
        d = abs(float(lv["price"]) - spot)
        if d <= limit_usd:
            kept.append(lv)
        else:
            dropped.append(lv)
    return kept, dropped
