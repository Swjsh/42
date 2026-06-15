"""PIN-FADE watcher — only fires on classified-chop days (NOT every day).

Per J's 2026-05-10 guidance: "we don't have to try and force chop, it's fine
if it's not every day, just every good opportunity."

Detects high-conviction PIN-FADE setups:
  - Chop classifier: VIX < 17 AND SPY range last 1h < 0.5% of price
  - Ribbon stack: MIXED (no clear directional bias)
  - Bar near VWAP (within $0.30) — pinning behavior
  - Time: 11:00-14:00 ET (post-opening, pre-close turbulence)
  - Setup: SPY rejected from extreme of recent range, fading back to VWAP

Entry idea (for future LIVE TRADING when promoted):
  - Sell premium (short straddle or iron condor) at VWAP
  - Defined risk via wings ($0.50 above ORH and below ORL)
  - Profit from theta decay + mean reversion to VWAP
  - Time stop at 15:00 ET (before close volatility)

For WATCH-ONLY: emit WatcherSignal so we can log + grade these setups.
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

import pandas as pd

from . import WatcherSignal


# Chop classifier thresholds
MAX_VIX_FOR_CHOP = 17.0
MAX_RANGE_PCT_LAST_HOUR = 0.005       # 0.5% of price
MAX_RANGE_PCT_TODAY = 0.012           # 1.2% — full-day range still small
PINFADE_TIME_START = dt.time(11, 0)
PINFADE_TIME_END = dt.time(14, 0)
VWAP_PROXIMITY_DOLLARS = 0.30


def _vwap(day_bars: pd.DataFrame) -> float:
    """Cumulative typical-price VWAP from session start."""
    if day_bars.empty:
        return 0.0
    typical = (day_bars["high"] + day_bars["low"] + day_bars["close"]) / 3
    cum_pv = (typical * day_bars["volume"]).cumsum()
    cum_v = day_bars["volume"].cumsum()
    return float(cum_pv.iloc[-1] / cum_v.iloc[-1]) if cum_v.iloc[-1] > 0 else 0.0


def detect_pinfade(
    bar: pd.Series,
    day_bars: pd.DataFrame,
    vix_now: float,
    ribbon_stack: Optional[str],
) -> Optional[WatcherSignal]:
    """Detect a PIN-FADE setup. Returns None on most bars (intentionally rare).

    Args:
        bar: current 5min bar
        day_bars: all bars from today through current
        vix_now: current VIX value
        ribbon_stack: "BULL" | "BEAR" | "MIXED" | None
    """
    bar_t = bar["timestamp_et"].time() if hasattr(bar["timestamp_et"], "time") else dt.time(0, 0)

    # Time gate
    if bar_t < PINFADE_TIME_START or bar_t > PINFADE_TIME_END:
        return None

    # Chop classifier
    if vix_now > MAX_VIX_FOR_CHOP:
        return None  # too much vol for chop strategy
    if ribbon_stack != "MIXED":
        return None  # trending day, skip pin-fade

    # Range check — last hour and today
    last_hour_bars = day_bars.tail(12)  # 12 × 5min = 1h
    if len(last_hour_bars) < 6:
        return None  # not enough data
    hour_high = float(last_hour_bars["high"].max())
    hour_low = float(last_hour_bars["low"].min())
    hour_range_pct = (hour_high - hour_low) / float(bar["close"])
    if hour_range_pct > MAX_RANGE_PCT_LAST_HOUR:
        return None  # too volatile in last hour

    today_high = float(day_bars["high"].max())
    today_low = float(day_bars["low"].min())
    day_range_pct = (today_high - today_low) / float(bar["close"])
    if day_range_pct > MAX_RANGE_PCT_TODAY:
        return None  # too volatile overall

    # VWAP proximity — bar must be near VWAP (pinning behavior)
    vwap = _vwap(day_bars)
    bar_close = float(bar["close"])
    vwap_dist = abs(bar_close - vwap)
    if vwap_dist > VWAP_PROXIMITY_DOLLARS:
        return None  # not pinning

    # All conditions met — emit pin-fade signal
    # Setup: sell straddle at VWAP, wings at hour high/low + $0.50 buffer
    short_call_strike = round(vwap)
    short_put_strike = round(vwap)
    long_call_strike = round(hour_high + 0.50)
    long_put_strike = round(hour_low - 0.50)

    return WatcherSignal(
        watcher_name="pinfade_watcher",
        setup_name="PIN_FADE_IRON_CONDOR",
        direction="neutral",
        entry_price=bar_close,
        stop_price=hour_high if bar_close < vwap else hour_low,  # opposite side of range
        tp1_price=vwap,         # target = VWAP itself (premium decay)
        runner_price=None,      # no runner for premium-sell
        confidence="high",       # if all gates pass, conviction is real
        reason=f"chop confirmed (VIX={vix_now:.1f}<{MAX_VIX_FOR_CHOP}, "
               f"hour_range={hour_range_pct*100:.2f}%<0.5%, "
               f"day_range={day_range_pct*100:.2f}%<1.2%, ribbon=MIXED), "
               f"SPY {bar_close:.2f} near VWAP {vwap:.2f}",
        triggers_fired=["chop_classifier", "vwap_pin", "ribbon_mixed"],
        metadata={
            "vix": vix_now,
            "vwap": vwap,
            "vwap_dist": vwap_dist,
            "hour_high": hour_high,
            "hour_low": hour_low,
            "hour_range_pct": hour_range_pct,
            "day_range_pct": day_range_pct,
            "iron_condor": {
                "short_call_strike": short_call_strike,
                "short_put_strike": short_put_strike,
                "long_call_strike": long_call_strike,
                "long_put_strike": long_put_strike,
            },
        },
    )
