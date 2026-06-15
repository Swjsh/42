"""SHOTGUN_SCALPER deterministic detector.

A 0DTE SPY directional scalp strategy with three independent trigger tiers.
Each tier is a separate internal function so unit tests can exercise them
in isolation.

  Tier 1 — OPEN_REJECTION
    The 09:30 RTH bar prints an upper wick >= 33% of its range and closes
    in the lower half. The setup is bearish. Live trigger fires when the
    most recent bar's close falls below the open of the 09:30 bar.

  Tier 2 — LEVEL_REJECT_LIVE
    A named level (Active/Carry/Multi-day) is touched, a reversal candle
    prints against the level (lower-high or higher-low) with volume
    >= 1.5x the trailing 20-bar average, and the most recent bar crosses
    back through the body midpoint of the rejection candle.

  Tier 3 — TRENDLINE_BREAK_RETEST
    An intraday trendline of >=3 swing touches spanning >=30 min breaks,
    price retests the broken line within 6 bars and closes on the
    opposite side, then the next bar crosses away from the line.

Stateless invocation contract:
  - Each call receives the full today_bars frame plus the current bar
    index. The detector reads only bars at index <= today_bar_idx and
    never touches today_bars[today_bar_idx + 1].
  - No module-level state. Repeat invocation on the same inputs returns
    the same answer.
  - Caller is responsible for closed-bar safety; pass only closed bars.

Per CLAUDE.md OP 21, the strategy launches WATCH-ONLY. The detector
returns trigger metadata only; order placement is the caller's concern.
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

import pandas as pd


RTH_OPEN = dt.time(9, 30)
RTH_CLOSE = dt.time(16, 0)

# Tier 1 thresholds.
OPEN_REJECTION_WICK_FRACTION = 0.33
OPEN_REJECTION_MIN_RANGE = 0.40  # dollars; below this the bar is too small to trust

# Tier 2 thresholds.
LEVEL_TOUCH_TOLERANCE_DOLLARS = 0.10
LEVEL_REJECT_VOL_MULT = 1.5

# Tier 3 thresholds.
TRENDLINE_MIN_TOUCHES = 3
TRENDLINE_MIN_SPAN_MINUTES = 30
TRENDLINE_FIT_TOLERANCE_DOLLARS = 0.20
TRENDLINE_RETEST_LOOKBACK_BARS = 6
TRENDLINE_BREAK_BODY_MIN_CENTS = 0.05
# Volume confirmation for TBR — 2026-05-24 analysis: vol_ratio>=1.5 → +$1.75/obs (n=77)
# vs vol_ratio<1.5 → -$0.58/obs (n=261).  Signals below threshold are downgraded to "low"
# confidence (still emitted for observation; downstream consumers may filter).
TBR_VOL_CONFIRM_MULT = 1.5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bar_time(bar: pd.Series) -> dt.time:
    ts = bar.get("time")
    if ts is None:
        ts = bar.get("timestamp_et")
    if ts is None:
        raise ValueError("bar missing 'time' / 'timestamp_et' column")
    if isinstance(ts, str):
        ts = pd.to_datetime(ts)
    return ts.time() if hasattr(ts, "time") else dt.time(0, 0)


def _bar_ts(bar: pd.Series):
    ts = bar.get("time")
    if ts is None:
        ts = bar.get("timestamp_et")
    return ts


def _vol_ratio(today_bars: pd.DataFrame, idx: int, window: int = 20) -> float:
    """Volume relative to the trailing `window`-bar average, excluding bar `idx`."""
    if idx <= 0:
        return 0.0
    start = max(0, idx - window)
    prior = today_bars.iloc[start:idx]
    if prior.empty:
        return 0.0
    avg = float(prior["volume"].mean())
    if avg <= 0:
        return 0.0
    cur = float(today_bars.iloc[idx]["volume"])
    return cur / avg


def _bar_range(bar: pd.Series) -> float:
    return float(bar["high"]) - float(bar["low"])


def _bar_body_midpoint(bar: pd.Series) -> float:
    return (float(bar["open"]) + float(bar["close"])) / 2.0


def _iso(ts) -> str:
    if ts is None:
        return ""
    if hasattr(ts, "isoformat"):
        return ts.isoformat()
    return str(ts)


# ---------------------------------------------------------------------------
# Tier 1 — OPEN_REJECTION
# ---------------------------------------------------------------------------


def _detect_open_rejection(
    today_bars: pd.DataFrame,
    today_bar_idx: int,
    levels: list[dict],
) -> Optional[dict]:
    """Tier 1: 09:30 bar upper-wick rejection, trigger on live cross under open."""
    if today_bars is None or today_bars.empty or today_bar_idx < 0:
        return None
    if today_bar_idx >= len(today_bars):
        return None

    first = today_bars.iloc[0]
    if _bar_time(first) != RTH_OPEN:
        return None

    rng = _bar_range(first)
    if rng < OPEN_REJECTION_MIN_RANGE:
        return None

    o = float(first["open"])
    h = float(first["high"])
    l = float(first["low"])
    c = float(first["close"])

    # OPEN_REJECTION measures rejection from the high to the bearish close:
    # how far did the bar travel down from its high relative to its range?
    # Standard upper-wick "high - max(o,c)" misses opens-near-the-high scenarios
    # where the body itself is the rejection. We use `high - close` for bearish
    # bars (close < open) and `high - max(o,c)` otherwise so a normal green bar
    # with a long upper shadow still qualifies.
    if c < o:
        rejection_from_high = h - c
    else:
        rejection_from_high = h - max(o, c)
    if rejection_from_high / rng < OPEN_REJECTION_WICK_FRACTION:
        return None

    half = l + rng / 2.0
    if c >= half:
        return None  # close must be in lower half

    # Live cross trigger: current bar's close prints below the 09:30 open.
    cur = today_bars.iloc[today_bar_idx]
    if today_bar_idx == 0:
        return None  # cannot trigger on the rejection bar itself
    if float(cur["close"]) >= o:
        return None

    # ONCE-PER-SESSION GATE (2026-05-16 fix): the original detector fired on
    # EVERY subsequent bar that closed below the 09:30 open, producing 214
    # Tier 1 fires over 16 weeks of replay (-$1,553). OPEN_REJECTION is by
    # design a one-shot setup: the first bar after the open bar that confirms
    # the rejection IS the entry. If any earlier bar already crossed below
    # the open, the trigger has passed.
    for prior_idx in range(1, today_bar_idx):
        prior = today_bars.iloc[prior_idx]
        if float(prior["close"]) < o:
            return None  # earlier bar already triggered; we missed our spot

    # Also gate by elapsed bars: must be within the first 6 bars (30 min) of
    # the open. After that, the OPEN_REJECTION thesis has decayed.
    if today_bar_idx > 6:
        return None

    target_level, target_label = _nearest_level_below(float(cur["close"]), levels)

    return {
        "tier": 1,
        "name": "OPEN_REJECTION",
        "direction": "bearish",
        "trigger_bar_time": _iso(_bar_ts(cur)),
        "rejection_high": h,
        "rejection_low": l,
        "target_level": target_level if target_level is not None else l,
        "target_label": target_label or "open_bar_low",
        "stop_chart": h + 0.05,
        "confidence": "high" if rejection_from_high / rng >= 0.50 else "medium",
        "vol_ratio": _vol_ratio(today_bars, 0),
        "reasoning": (
            f"09:30 bar rejection-from-high {rejection_from_high:.2f} "
            f"({rejection_from_high / rng * 100:.0f}% of range {rng:.2f}), "
            f"close {c:.2f} in lower half (mid={half:.2f}). "
            f"Live close {float(cur['close']):.2f} crossed below open {o:.2f}."
        ),
    }


# ---------------------------------------------------------------------------
# Tier 2 — LEVEL_REJECT_LIVE
# ---------------------------------------------------------------------------


def _nearest_level_below(price: float, levels: list[dict]) -> tuple[Optional[float], Optional[str]]:
    best: tuple[Optional[float], Optional[str]] = (None, None)
    best_gap = float("inf")
    for lv in levels or []:
        try:
            p = float(lv.get("price"))
        except (TypeError, ValueError):
            continue
        if p < price:
            gap = price - p
            if gap < best_gap:
                best_gap = gap
                best = (p, lv.get("label") or lv.get("source") or "level")
    return best


def _nearest_level_above(price: float, levels: list[dict]) -> tuple[Optional[float], Optional[str]]:
    best: tuple[Optional[float], Optional[str]] = (None, None)
    best_gap = float("inf")
    for lv in levels or []:
        try:
            p = float(lv.get("price"))
        except (TypeError, ValueError):
            continue
        if p > price:
            gap = p - price
            if gap < best_gap:
                best_gap = gap
                best = (p, lv.get("label") or lv.get("source") or "level")
    return best


def _detect_level_reject(
    today_bars: pd.DataFrame,
    today_bar_idx: int,
    levels: list[dict],
) -> Optional[dict]:
    """Tier 2: level touch + reversal candle + volume + live cross of body midpoint."""
    if today_bars is None or today_bars.empty or today_bar_idx <= 0:
        return None
    if today_bar_idx >= len(today_bars):
        return None
    if not levels:
        return None

    cur = today_bars.iloc[today_bar_idx]
    cur_close = float(cur["close"])

    # Look back up to 6 bars for a rejection candle at a named level. The
    # rejection bar may be the current bar itself (back=0) — in that case the
    # bar's close on the favourable side IS the live cross of its own midpoint.
    for back in range(0, min(7, today_bar_idx + 1)):
        rej_idx = today_bar_idx - back
        rej = today_bars.iloc[rej_idx]
        prev = today_bars.iloc[rej_idx - 1] if rej_idx > 0 else None
        if prev is None:
            continue

        rej_h = float(rej["high"])
        rej_l = float(rej["low"])
        rej_o = float(rej["open"])
        rej_c = float(rej["close"])
        prev_h = float(prev["high"])
        prev_l = float(prev["low"])

        vr = _vol_ratio(today_bars, rej_idx)
        if vr < LEVEL_REJECT_VOL_MULT:
            continue

        # BEARISH path: rejection at a resistance — bar tagged level then printed lower-high.
        for lv in levels:
            try:
                lp = float(lv.get("price"))
            except (TypeError, ValueError):
                continue
            label = lv.get("label") or lv.get("source") or f"{lp:.2f}"

            # Bearish rejection: high touches level from below, prints lower-high vs prev,
            # closes red.
            touched_from_below = (
                rej_h >= lp - LEVEL_TOUCH_TOLERANCE_DOLLARS
                and rej_h <= lp + LEVEL_TOUCH_TOLERANCE_DOLLARS * 4
            )
            if (
                touched_from_below
                and rej_h < prev_h
                and rej_c < rej_o
            ):
                mid = _bar_body_midpoint(rej)
                if cur_close < mid:
                    target_level, target_label = _nearest_level_below(cur_close, levels)
                    return {
                        "tier": 2,
                        "name": "LEVEL_REJECT_LIVE",
                        "direction": "bearish",
                        "trigger_bar_time": _iso(_bar_ts(cur)),
                        "rejection_high": rej_h,
                        "rejection_low": rej_l,
                        "target_level": target_level if target_level is not None else rej_l,
                        "target_label": target_label or "prior_low",
                        "stop_chart": rej_h + 0.05,
                        "confidence": "high" if vr >= 2.0 else "medium",
                        "vol_ratio": vr,
                        "reasoning": (
                            f"Bearish reject at {label}@{lp:.2f}: bar high {rej_h:.2f} "
                            f"touched level, lower-high vs prior {prev_h:.2f}, "
                            f"red close {rej_c:.2f}, vol {vr:.2f}x. Live close "
                            f"{cur_close:.2f} crossed below body mid {mid:.2f}."
                        ),
                    }

            # Bullish reclaim: low pokes level from above, prints higher-low vs prev,
            # closes green.
            touched_from_above = (
                rej_l <= lp + LEVEL_TOUCH_TOLERANCE_DOLLARS
                and rej_l >= lp - LEVEL_TOUCH_TOLERANCE_DOLLARS * 4
            )
            if (
                touched_from_above
                and rej_l > prev_l
                and rej_c > rej_o
            ):
                mid = _bar_body_midpoint(rej)
                if cur_close > mid:
                    target_level, target_label = _nearest_level_above(cur_close, levels)
                    return {
                        "tier": 2,
                        "name": "LEVEL_REJECT_LIVE",
                        "direction": "bullish",
                        "trigger_bar_time": _iso(_bar_ts(cur)),
                        "rejection_high": rej_h,
                        "rejection_low": rej_l,
                        "target_level": target_level if target_level is not None else rej_h,
                        "target_label": target_label or "prior_high",
                        "stop_chart": rej_l - 0.05,
                        "confidence": "high" if vr >= 2.0 else "medium",
                        "vol_ratio": vr,
                        "reasoning": (
                            f"Bullish reclaim at {label}@{lp:.2f}: bar low {rej_l:.2f} "
                            f"poked level, higher-low vs prior {prev_l:.2f}, "
                            f"green close {rej_c:.2f}, vol {vr:.2f}x. Live close "
                            f"{cur_close:.2f} crossed above body mid {mid:.2f}."
                        ),
                    }

    return None


# ---------------------------------------------------------------------------
# Tier 3 — TRENDLINE_BREAK_RETEST
# ---------------------------------------------------------------------------


def _swing_points(bars: pd.DataFrame, kind: str, window: int = 2) -> list[tuple[int, float]]:
    """Return list of (bar_idx, price) swing highs or lows in `bars`.

    A swing high at index i requires bars[i].high > bars[i-k].high for all k in
    1..window and >= bars[i+k].high for all k in 1..window (where in-range).
    Same logic for lows, inverted.
    """
    out: list[tuple[int, float]] = []
    if bars is None or bars.empty:
        return out
    n = len(bars)
    col = "high" if kind == "high" else "low"
    for i in range(window, n - window):
        center = float(bars.iloc[i][col])
        is_swing = True
        for k in range(1, window + 1):
            left = float(bars.iloc[i - k][col])
            right = float(bars.iloc[i + k][col])
            if kind == "high":
                if center <= left or center < right:
                    is_swing = False
                    break
            else:
                if center >= left or center > right:
                    is_swing = False
                    break
        if is_swing:
            out.append((i, center))
    return out


def _fit_line_through_points(p1: tuple[int, float], p2: tuple[int, float]) -> tuple[float, float]:
    """Return (slope_per_bar, intercept_at_idx_0)."""
    x1, y1 = p1
    x2, y2 = p2
    if x2 == x1:
        return 0.0, y1
    slope = (y2 - y1) / (x2 - x1)
    intercept = y1 - slope * x1
    return slope, intercept


def _count_touches(
    points: list[tuple[int, float]],
    slope: float,
    intercept: float,
    tol: float,
) -> list[tuple[int, float]]:
    """Return points within `tol` dollars of the fitted line."""
    out = []
    for (xi, yi) in points:
        line_y = slope * xi + intercept
        if abs(yi - line_y) <= tol:
            out.append((xi, yi))
    return out


def _detect_trendline_break(
    today_bars: pd.DataFrame,
    today_bar_idx: int,
    levels: list[dict],
) -> Optional[dict]:
    """Tier 3: trendline of >=3 touches breaks, retest within 6 bars, reject."""
    if today_bars is None or today_bar_idx < 6:
        return None
    if today_bar_idx >= len(today_bars):
        return None

    # Limit to bars at idx <= today_bar_idx (closed-bar safety).
    history = today_bars.iloc[: today_bar_idx + 1].copy().reset_index(drop=True)
    if len(history) < 7:
        return None

    # Bar-to-bar time delta. Assume uniform 5min cadence (caller responsibility).
    bars_per_30min = 6

    cur = history.iloc[-1]
    cur_close = float(cur["close"])
    cur_open = float(cur["open"])

    # Try both rising support (swing lows) and falling resistance (swing highs).
    # FIX 2026-05-16 (L45-adjacent): the original loop returned on the first
    # `kind` that produced a candidate, which biased detection toward bearish
    # breaks (rising-support broken = bear, evaluated first). 16 weeks of
    # historical observations were 29 short / 0 long despite a clear uptrend
    # in the underlying. The fix: search BOTH kinds, score candidates by
    # touch_count + span, return the best.
    candidates: list[dict] = []
    for kind in ("low", "high"):
        swings = _swing_points(history.iloc[:-1], kind=kind)  # exclude current bar
        if len(swings) < TRENDLINE_MIN_TOUCHES:
            continue

        best: Optional[dict] = None

        # Iterate over every pair of swings as line candidates.
        for i in range(len(swings)):
            for j in range(i + 1, len(swings)):
                p1 = swings[i]
                p2 = swings[j]
                if p2[0] - p1[0] < bars_per_30min:
                    continue
                slope, intercept = _fit_line_through_points(p1, p2)
                touches = _count_touches(
                    swings, slope, intercept, TRENDLINE_FIT_TOLERANCE_DOLLARS
                )
                if len(touches) < TRENDLINE_MIN_TOUCHES:
                    continue
                span_bars = touches[-1][0] - touches[0][0]
                if span_bars < bars_per_30min:
                    continue

                line_at_break = slope * (len(history) - 1) + intercept

                # Look for a break: a bar (at idx <= today_bar_idx - 1) that
                # closed on the opposite side of the line vs the trendline kind.
                # For a falling resistance (swing highs), a break is close > line.
                # For a rising support (swing lows), a break is close < line.
                break_idx: Optional[int] = None
                break_dir: Optional[str] = None
                last_touch_idx = touches[-1][0]
                for bi in range(last_touch_idx + 1, len(history) - 1):
                    bar = history.iloc[bi]
                    line_y = slope * bi + intercept
                    body = float(bar["close"]) - float(bar["open"])
                    if kind == "high":  # falling resistance — bull break
                        if float(bar["close"]) - line_y > TRENDLINE_BREAK_BODY_MIN_CENTS and body > 0:
                            break_idx = bi
                            break_dir = "bullish"
                            break
                    else:  # rising support — bear break
                        if line_y - float(bar["close"]) > TRENDLINE_BREAK_BODY_MIN_CENTS and body < 0:
                            break_idx = bi
                            break_dir = "bearish"
                            break

                if break_idx is None:
                    continue

                # Within TRENDLINE_RETEST_LOOKBACK_BARS, look for a retest +
                # rejection (close back on opposite side of the line).
                retest_idx: Optional[int] = None
                for ri in range(break_idx + 1, min(break_idx + 1 + TRENDLINE_RETEST_LOOKBACK_BARS,
                                                   len(history))):
                    bar = history.iloc[ri]
                    line_y = slope * ri + intercept
                    if break_dir == "bullish":
                        # retest from above; bar low touches line; close back above
                        if float(bar["low"]) <= line_y + TRENDLINE_FIT_TOLERANCE_DOLLARS:
                            if float(bar["close"]) > line_y:
                                retest_idx = ri
                                break
                    else:
                        # retest from below; bar high touches line; close back below
                        if float(bar["high"]) >= line_y - TRENDLINE_FIT_TOLERANCE_DOLLARS:
                            if float(bar["close"]) < line_y:
                                retest_idx = ri
                                break

                if retest_idx is None:
                    continue

                # Live trigger: most recent bar moves away from the line in the
                # break direction.
                cur_line_y = slope * (len(history) - 1) + intercept
                if break_dir == "bullish":
                    if cur_close <= cur_line_y:
                        continue
                else:
                    if cur_close >= cur_line_y:
                        continue

                vr_cur = _vol_ratio(history, len(history) - 1)
                # Confidence: volume confirmation required for high/medium.
                # Without sufficient volume the TBR is downgraded to "low"
                # (2026-05-24: vol_ratio>=1.5 → +$1.75/obs, <1.5 → -$0.58/obs).
                if vr_cur >= TBR_VOL_CONFIRM_MULT:
                    _tbr_confidence = "high" if len(touches) >= 4 else "medium"
                else:
                    _tbr_confidence = "low"
                cand = {
                    "tier": 3,
                    "name": "TRENDLINE_BREAK_RETEST",
                    "direction": break_dir,
                    "trigger_bar_time": _iso(_bar_ts(cur)),
                    "rejection_high": float(history.iloc[retest_idx]["high"]),
                    "rejection_low": float(history.iloc[retest_idx]["low"]),
                    "target_level": (
                        _nearest_level_above(cur_close, levels)[0]
                        if break_dir == "bullish"
                        else _nearest_level_below(cur_close, levels)[0]
                    ),
                    "target_label": (
                        _nearest_level_above(cur_close, levels)[1]
                        if break_dir == "bullish"
                        else _nearest_level_below(cur_close, levels)[1]
                    ),
                    "stop_chart": (
                        float(history.iloc[retest_idx]["low"]) - 0.05
                        if break_dir == "bullish"
                        else float(history.iloc[retest_idx]["high"]) + 0.05
                    ),
                    "confidence": _tbr_confidence,
                    "vol_ratio": vr_cur,
                    "reasoning": (
                        f"Trendline {kind} ({len(touches)} touches over "
                        f"{span_bars} bars, slope {slope:.4f}/bar) broke "
                        f"{break_dir} at bar idx {break_idx}; retest held at "
                        f"idx {retest_idx} on {history.iloc[retest_idx]['low']:.2f}/"
                        f"{history.iloc[retest_idx]['high']:.2f}; live close "
                        f"{cur_close:.2f} away from line {cur_line_y:.2f}."
                    ),
                }
                # Fill targets with reasonable defaults if no level available.
                if cand["target_level"] is None:
                    cand["target_level"] = (
                        cur_close + 1.0 if break_dir == "bullish" else cur_close - 1.0
                    )
                    cand["target_label"] = "default_1pt"

                # Score: more touches + wider span = better quality candidate.
                cand["_score"] = len(touches) * 10 + span_bars
                if best is None or cand["_score"] > best.get("_score", 0):
                    best = cand
            # End j loop — DO NOT break here; let the i loop fully run.
        # End i loop. If we found a best for this kind, record it.
        if best is not None:
            candidates.append(best)

    if not candidates:
        return None

    # Cross-kind selection: pick the highest-scoring candidate (both bullish
    # and bearish breaks considered equally).
    winner = max(candidates, key=lambda c: c.get("_score", 0))
    winner.pop("_score", None)
    return winner


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def detect(
    today_bars: pd.DataFrame,
    today_bar_idx: int,
    levels: list[dict],
    ribbon: dict,
    vix: float,
    htf_15m_stack: Optional[str],
    auto_derive_intraday_levels: bool = False,
) -> Optional[dict]:
    """Run all three SHOTGUN_SCALPER tiers; return the first one that fires.

    Tier priority: 1 (open rejection) > 2 (level reject live) > 3 (trendline).

    Args:
        today_bars: 5m bars with columns time/timestamp_et, open, high, low,
            close, volume. Must include the 09:30 RTH bar at index 0 for
            Tier 1 to fire.
        today_bar_idx: integer index of the most recent CLOSED bar. The
            detector never reads beyond this index.
        levels: list of dicts with at least 'price' and ideally 'label'.
        ribbon: ribbon snapshot dict (fast, pivot, slow, spread_cents, stack).
            Reserved for confidence weighting / future filters; not strictly
            required.
        vix: current VIX print (float). Reserved for future filters.
        htf_15m_stack: 15m ribbon stack string ("BULL", "BEAR", "NEUTRAL") or None.

    Returns:
        Trigger dict (see module docstring for schema) or None.
    """
    if today_bars is None or today_bars.empty:
        return None
    if today_bar_idx < 0 or today_bar_idx >= len(today_bars):
        return None

    # Augment levels with intraday rolling derivations so Tier 2 has anchors
    # even when caller's `levels` list is sparse (typical in historical replay).
    # OPT-IN via auto_derive_intraday_levels=True. Default False to preserve
    # test fixtures that don't expect derived levels. Per L34 closed-bar
    # discipline: only reads bars at idx <= today_bar_idx.
    enriched = list(levels or [])
    if auto_derive_intraday_levels:
        enriched.extend(_derive_intraday_levels(today_bars, today_bar_idx))

    for fn in (_detect_open_rejection, _detect_level_reject, _detect_trendline_break):
        result = fn(today_bars, today_bar_idx, enriched)
        if result is None:
            continue
        # HTF regime gate (Stage 4 addition 2026-05-16): suppress signals that
        # contradict the 15-min macro ribbon stack.  Caller passes None when no
        # HTF context is available (grinder Stage 1-3, legacy callers) → gate
        # is transparent and existing behaviour is preserved.
        if htf_15m_stack in ("BULL", "BEAR"):
            sig_dir = result.get("direction", "")
            if htf_15m_stack == "BEAR" and sig_dir in ("bullish", "long"):
                continue  # 15m macro bearish → skip bullish tier, try next
            if htf_15m_stack == "BULL" and sig_dir in ("bearish", "short"):
                continue  # 15m macro bullish → skip bearish tier, try next
        return result
    return None


def _derive_intraday_levels(today_bars: pd.DataFrame, today_bar_idx: int) -> list[dict]:
    """Auto-derive named-level candidates from today's bars up to bar_idx.

    Returns up to 6 dicts in the detector's expected schema:
      - SESSION_HIGH / SESSION_LOW : highest high / lowest low of today's
        bars seen so far
      - RTH_OPEN_PRICE             : open of the first RTH bar (the 09:30 bar)
      - ROLLING_60MIN_HIGH/LOW     : 12-bar high / low ending at current bar
      - ROLLING_30MIN_HIGH/LOW     : 6-bar high / low ending at current bar

    All levels are within the SHOTGUN detector's tolerance (no de-duplication
    by price — Tier 2 already iterates and short-circuits on first match).
    """
    if today_bars is None or today_bar_idx < 1:
        return []
    history = today_bars.iloc[: today_bar_idx + 1]
    if history.empty:
        return []

    out: list[dict] = []

    try:
        session_high = float(history["high"].max())
        session_low = float(history["low"].min())
        out.append({"price": session_high, "label": "SESSION_HIGH",
                    "tier": "Active", "type": "resistance", "stars": 2})
        out.append({"price": session_low, "label": "SESSION_LOW",
                    "tier": "Active", "type": "support", "stars": 2})

        first_bar = history.iloc[0]
        first_open = float(first_bar["open"])
        out.append({"price": first_open, "label": "RTH_OPEN_PRICE",
                    "tier": "Reference", "type": "resistance", "stars": 2})

        # Rolling 60-min (12 bars) and 30-min (6 bars) high/low.
        for n_bars, prefix in ((12, "ROLLING_60MIN"), (6, "ROLLING_30MIN")):
            recent = history.tail(n_bars)
            if len(recent) >= 3:
                rh = float(recent["high"].max())
                rl = float(recent["low"].min())
                out.append({"price": rh, "label": f"{prefix}_HIGH",
                            "tier": "Active", "type": "resistance", "stars": 2})
                out.append({"price": rl, "label": f"{prefix}_LOW",
                            "tier": "Active", "type": "support", "stars": 2})
    except Exception:
        # Best-effort: a single bad bar shouldn't break detection.
        pass

    return out


__all__ = [
    "detect",
    "_detect_open_rejection",
    "_detect_level_reject",
    "_detect_trendline_break",
]
