"""RIBBON_REJECTION_WICK deterministic detector (bear primary + bull mirror).

UNREGISTERED / RESEARCH-ONLY (2026-07-02). Not imported by lib/watchers/__init__.py
or lib/watchers/runner.py — inert to the live engine until explicitly wired
(WIRE-DETECTOR proposal required, arming after close).

Motivating anchor case — J's LIVE read of 2026-07-02 (verbatim mechanics):
  SPY ran up in the morning; breakdown began 10:15-10:20 ET; the 10:25 candle
  printed volume exceeding everything since the open, tested the PREMARKET OPEN
  level and bounced; the 10:30 and 10:35 candles WICKED UP INTO THE EMA RIBBON
  FROM BELOW and were rejected (ribbon = dynamic resistance, stack had not yet
  flipped bear); 10:40 dump; bear flag; 11:00 bearish engulfing + ribbon flip.
  The wick rejections at 10:30/10:35 were the entry — 30 minutes before the
  confirmatory ribbon flip. The engine logged HOLD "no setup passed scoring"
  through the whole window: it has no ribbon-rejection trigger and no volume
  input.

Setup definition (bear side; bull is the exact mirror):
  1. STRUCTURAL BREAK: within the last `break_lookback_bars` bars there is a
     transition bar b whose close crossed BELOW the full ribbon
     (close[b] < band_low[b] while close[b-1] >= band_low[b-1]), after price
     had been ABOVE the full ribbon (some bar in the `above_lookback_bars`
     window before b closed > band_high).
  2. REJECTION WICK on the current (closed) bar:
       - high penetrates INTO/ABOVE the ribbon band (high >= band_low)
       - close is back BELOW the fast EMA by `close_margin_dollars` AND below
         the full ribbon (close < band_low)
       - wick_above_close fraction (high - close) / (high - low) >= wick_frac_min
  3. Context (grid-able):
       - vol_mult_min: volume of the break-initiating bar b >= K x the median
         volume of today's prior RTH bars (K=0 disables)
       - require_stack_not_flipped: ribbon stack at the signal bar is NOT yet
         BEAR (the anticipatory case J described) vs any stack

Entry: next bar open, bear direction (puts). Bull mirror: calls.

Stateless invocation contract (same as shotgun_scalper_detector):
  - Caller passes a continuous 5m frame (warmup bars + today) and the index of
    the most recent CLOSED bar. The detector reads only bars at index <= idx.
  - EMA ribbon may be precomputed over the full frame for scan efficiency —
    EMA at bar i depends only on closes <= i, so this is look-ahead-safe
    (guarded by test_ribbon_rejection_wick.py::test_no_lookahead).
  - No module-level state.

Ribbon periods: fingerprinted Saty ribbon (fast=13 / pivot=20 / slow=48) via
lib.ribbon.compute_ribbon — identical to the live engine's read.

── BATTERY VERDICT 2026-07-02: FAIL — DO NOT WIRE (WATCH_FRAGILE) ──────────
Full battery 2025-01-02..2026-07-01, OPRA real fills, 24 combos, BH-FDR:
0/24 survivors. Scorecard: analysis/recommendations/ribbon-rejection-wick.json.

  ANCHOR: PASS — detector sees J's own case (bearish fires 10:25/10:30/10:40 ET
    on 2026-07-02, stack=BULL pre-flip, 3 fires <= 5). Definition is correct.
  KILL NAIL (why it still fails as a trade):
  - J-exact config (not_flipped + vol>=1.5): N=174, WR=65.5%,
    expectancy=-$16.16/trade, OOS -$30.10, drop-top3 -$3,615. BOTH directions
    negative (short -$12.41, long -$22.01).
  - Best of 24 (wick>=0.5, lb<=6, vol>=2.5, any-stack): full +$2.74/trade but
    IS +$26.98 vs OOS -$21.50 (edge is 2025-only), drop-top3 -$810 (3 trades
    carry everything), slippage breakeven 0.46c/side (half a spread kills it).
  - C3 signature (SPY-price edge != option edge): WR ~65% everywhere yet
    expectancy negative — chandelier locks small wins (114/174 exits), -30%
    catastrophe stops eat big losses. R:R inverted, same failure family as NLWB.
  - The signal DOES beat random entry (null -$23.5/short -$33.4/long per
    trade; several combos p<0.05 + FDR-survive) — relative directional info
    exists but cannot overcome 0DTE premium bleed under any tested config.
  Disclosed limit: exits were FIXED (TP+50%/stop-30%/60min/ATM/chandelier),
  not searched — an exit-redesign rescue is not ruled out, but NLWB's TP/stop
  sweeps (L58) showed this R:R family doesn't rescue via exit knobs.
  Possible future rescue vein: use as EXIT/VETO signal (bear rejection wick =
  don't-enter-bull / tighten-runner), not as an entry.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Optional

import pandas as pd

try:  # package-relative (lib.watchers.*) vs script import both work
    from ..ribbon import compute_ribbon
except ImportError:  # pragma: no cover
    from lib.ribbon import compute_ribbon


RTH_OPEN = dt.time(9, 30)
RTH_CLOSE = dt.time(16, 0)


@dataclass(frozen=True)
class RRWParams:
    """Detection knobs. Grid stays small per spec (<= 36 combos)."""

    wick_frac_min: float = 0.35          # (high-close)/(high-low) rejection fraction
    break_lookback_bars: int = 12        # structural break within last N bars (60 min)
    vol_mult_min: float = 0.0            # break-bar vol >= K x today's prior-bar median; 0 = off
    require_stack_not_flipped: bool = True  # anticipatory: stack NOT yet BEAR (bear side)

    # Fixed (not gridded) — sensible constants, disclosed:
    close_margin_dollars: float = 0.01   # close below fast EMA by at least this
    above_lookback_bars: int = 36        # "was above" search window before the break (3h)
    min_bar_range_dollars: float = 0.10  # ignore micro bars (wick fraction is noise)
    vol_median_min_bars: int = 3         # need >= 3 prior today bars for the vol median


# The loosest values of every gridded knob — used by the battery's superset
# scan so per-combo filters can be applied post-hoc on recorded features.
SUPERSET_PARAMS = RRWParams(
    wick_frac_min=0.35,
    break_lookback_bars=12,
    vol_mult_min=0.0,
    require_stack_not_flipped=False,
)


def _bar_ts(bar: pd.Series):
    ts = bar.get("timestamp_et")
    if ts is None:
        ts = bar.get("time")
    return ts


def _iso(ts) -> str:
    if ts is None:
        return ""
    return ts.isoformat() if hasattr(ts, "isoformat") else str(ts)


def _break_bar_vol_ratio(bars: pd.DataFrame, break_idx: int, params: RRWParams) -> tuple[float, bool]:
    """Break-bar volume vs the median of TODAY's prior RTH bars.

    Returns (ratio, is_day_max). ratio=0.0 when fewer than vol_median_min_bars
    prior same-day RTH bars exist (fails any K>0 combo — early-open safety).
    """
    brk = bars.iloc[break_idx]
    ts = _bar_ts(brk)
    if ts is None or not hasattr(ts, "date"):
        return 0.0, False
    day = ts.date()
    # Bounded lookback (max one session of 5m bars) so battery-scale scans stay O(1) per call.
    prior = bars.iloc[max(0, break_idx - 80): break_idx]
    mask = prior["timestamp_et"].apply(
        lambda t: hasattr(t, "date") and t.date() == day and RTH_OPEN <= t.time() < RTH_CLOSE
    )
    today_prior = prior[mask]
    if len(today_prior) < params.vol_median_min_bars:
        return 0.0, False
    med = float(today_prior["volume"].median())
    if med <= 0:
        return 0.0, False
    v = float(brk["volume"])
    return v / med, bool(v > float(today_prior["volume"].max()))


def detect(
    bars: pd.DataFrame,
    idx: int,
    params: RRWParams = RRWParams(),
    direction: str = "bear",
    ribbon_df: Optional[pd.DataFrame] = None,
) -> Optional[dict]:
    """Detect RIBBON_REJECTION_WICK on the closed bar at `idx`.

    Args:
        bars: continuous 5m frame (warmup + today), columns timestamp_et
            (naive ET), open, high, low, close, volume. RangeIndex 0..n-1.
        idx: index of the most recent CLOSED bar. Never reads beyond it.
        params: detection knobs.
        direction: "bear" (primary) or "bull" (mirror).
        ribbon_df: optional precomputed compute_ribbon(bars["close"]) for scan
            efficiency. Must be row-aligned with `bars`.

    Returns a signal dict or None.
    """
    if bars is None or bars.empty or idx < 2 or idx >= len(bars):
        return None
    if direction not in ("bear", "bull"):
        return None

    if ribbon_df is None:
        # Only closes <= idx exist for the recursion — truncate for safety when
        # computing on demand (precomputed frames are already look-ahead-safe).
        ribbon_df = compute_ribbon(bars["close"].iloc[: idx + 1])

    fast = ribbon_df["fast"]
    pivot = ribbon_df["pivot"]
    slow = ribbon_df["slow"]
    if idx >= len(ribbon_df) or pd.isna(fast.iloc[idx]) or pd.isna(slow.iloc[idx]) or pd.isna(pivot.iloc[idx]):
        return None

    def band_low(i: int) -> float:
        return min(float(fast.iloc[i]), float(pivot.iloc[i]), float(slow.iloc[i]))

    def band_high(i: int) -> float:
        return max(float(fast.iloc[i]), float(pivot.iloc[i]), float(slow.iloc[i]))

    cur = bars.iloc[idx]
    o, h, l, c = (float(cur["open"]), float(cur["high"]), float(cur["low"]), float(cur["close"]))
    rng = h - l
    if rng < params.min_bar_range_dollars:
        return None

    bl_i, bh_i = band_low(idx), band_high(idx)
    fast_i = float(fast.iloc[idx])

    if direction == "bear":
        # (2) rejection wick: close below fast EMA (by margin) AND below the
        # full ribbon; high penetrates into/above the band.
        if not (c < fast_i - params.close_margin_dollars and c < bl_i):
            return None
        if not (h >= bl_i):
            return None
        wick_frac = (h - c) / rng
    else:
        if not (c > fast_i + params.close_margin_dollars and c > bh_i):
            return None
        if not (l <= bh_i):
            return None
        wick_frac = (c - l) / rng

    if wick_frac < params.wick_frac_min:
        return None

    # (1) structural break: most recent transition bar within lookback.
    break_idx: Optional[int] = None
    for b in range(idx, max(idx - params.break_lookback_bars, 1) - 1, -1):
        if pd.isna(fast.iloc[b]) or pd.isna(fast.iloc[b - 1]):
            continue
        if direction == "bear":
            crossed = (
                float(bars.iloc[b]["close"]) < band_low(b)
                and float(bars.iloc[b - 1]["close"]) >= band_low(b - 1)
            )
        else:
            crossed = (
                float(bars.iloc[b]["close"]) > band_high(b)
                and float(bars.iloc[b - 1]["close"]) <= band_high(b - 1)
            )
        if crossed:
            break_idx = b
            break
    if break_idx is None:
        return None

    # "was above" (bear) / "was below" (bull) before the break.
    was_prior_side = False
    lo = max(0, break_idx - params.above_lookback_bars)
    for a in range(break_idx - 1, lo - 1, -1):
        if pd.isna(fast.iloc[a]):
            continue
        ca = float(bars.iloc[a]["close"])
        if direction == "bear" and ca > band_high(a):
            was_prior_side = True
            break
        if direction == "bull" and ca < band_low(a):
            was_prior_side = True
            break
    if not was_prior_side:
        return None

    # (3a) stack filter — anticipatory case: not yet flipped in signal direction.
    stack = str(ribbon_df["stack"].iloc[idx])
    flipped = (stack == "BEAR") if direction == "bear" else (stack == "BULL")
    if params.require_stack_not_flipped and flipped:
        return None

    # (3b) volume of the break-initiating bar vs today's prior-bar median.
    vol_ratio, vol_is_day_max = _break_bar_vol_ratio(bars, break_idx, params)
    if params.vol_mult_min > 0 and vol_ratio < params.vol_mult_min:
        return None

    ts = _bar_ts(cur)
    return {
        "name": "RIBBON_REJECTION_WICK",
        "direction": "bearish" if direction == "bear" else "bullish",
        "trigger_bar_time": _iso(ts),
        "entry_price": c,                      # signal-bar close; fills next bar open
        "stop_chart": (bh_i + 0.05) if direction == "bear" else (bl_i - 0.05),
        "confidence": "high" if (wick_frac >= 0.50 and vol_ratio >= 2.0) else "medium",
        # features (battery combos filter on these post-hoc)
        "wick_frac": round(wick_frac, 4),
        "bars_since_break": idx - break_idx,
        "break_bar_time": _iso(_bar_ts(bars.iloc[break_idx])),
        "vol_break_ratio": round(vol_ratio, 3),
        "vol_is_day_max": vol_is_day_max,
        "stack_at_signal": stack,
        "stack_flipped": flipped,
        "band_low": round(bl_i, 4),
        "band_high": round(bh_i, 4),
        "fast_ema": round(fast_i, 4),
        "bar_high": h,
        "bar_low": l,
        "bar_close": c,
        "reasoning": (
            f"{'Bear' if direction == 'bear' else 'Bull'} ribbon-rejection wick: "
            f"close {c:.2f} {'<' if direction == 'bear' else '>'} fast EMA {fast_i:.2f}, "
            f"{'high' if direction == 'bear' else 'low'} "
            f"{h if direction == 'bear' else l:.2f} penetrated band "
            f"[{bl_i:.2f}, {bh_i:.2f}], wick_frac={wick_frac:.2f}, "
            f"break {idx - break_idx} bars ago (vol {vol_ratio:.1f}x median), "
            f"stack={stack}."
        ),
    }


def detect_both(
    bars: pd.DataFrame,
    idx: int,
    params: RRWParams = RRWParams(),
    ribbon_df: Optional[pd.DataFrame] = None,
) -> list[dict]:
    """Run bear + bull mirrors on one bar; returns 0-2 signals."""
    out = []
    for d in ("bear", "bull"):
        sig = detect(bars, idx, params, direction=d, ribbon_df=ribbon_df)
        if sig is not None:
            out.append(sig)
    return out


__all__ = ["RRWParams", "SUPERSET_PARAMS", "detect", "detect_both"]
