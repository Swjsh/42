"""Level derivation — auto-detects the support/resistance levels the heartbeat would see.

In production, levels are written by premarket from chart structure + protocol audit.
For backtest, we approximate from price history alone:

  * Active levels (today): prior day's high/low/close, today's premarket H/L if we have them,
    today's session high/low so far.
  * Carry / multi-day: 5-day rolling high/low ending yesterday.
  * Round numbers: nearest $1 above and below current price (psychological).

This is a faithful approximation. Real playbook trades sometimes target levels J drew
manually that don't fall out of a rolling-high rule. If e2e tests fail to detect a
specific historical entry, we can extend the detector. The 60-day backtest's value
isn't sensitive to missing 5-10% of levels — the high-quality trades come from the
prior-day-high / multi-day-swing structure, which IS detectable.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import pandas as pd


@dataclass
class LevelSet:
    """Active levels at a point in time."""
    active: list[float]              # all levels currently in play
    multi_day: list[float]           # subset that are >= 1 day old (multi-day reference points)
    # NEW 2026-05-14 T58 — Liquidity-sweep upgraded levels.
    # A level appears in `swept_levels` if a recent bar wicked through it but
    # closed back inside the prior range (institutional liquidity grab pattern).
    # Such levels have higher conviction — engine can size up or take with priority.
    # Default empty list for backward compatibility (existing callers unaffected).
    swept_levels: list[float] = field(default_factory=list)


def detect_levels_at_bar(
    spy_df: pd.DataFrame,
    bar_idx: int,
    bar_timestamp: dt.datetime,
) -> LevelSet:
    """Return the active level set as of `bar_idx` (using ONLY data <= bar_idx).

    No look-ahead bias. The level list is what the heartbeat would have seen at that bar.

    Args:
        spy_df: full SPY 5m OHLCV with `timestamp_et` column
        bar_idx: position of the trigger bar in spy_df
        bar_timestamp: the trigger bar's ET timestamp
    """
    today = bar_timestamp.date()

    # Use only bars at or before bar_idx
    history = spy_df.iloc[:bar_idx + 1].copy()
    history["timestamp_et"] = pd.to_datetime(history["timestamp_et"], utc=True).dt.tz_convert(history["timestamp_et"].iloc[0].tzinfo if hasattr(history["timestamp_et"].iloc[0], "tzinfo") else "America/New_York")
    return _detect_from_history(history, today)


def _detect_from_history(
    history: pd.DataFrame,
    today: dt.date,
    *,
    exclude_intraday_hl: bool = False,
) -> LevelSet:
    """Internal: derive levels from a tz-aware bar history through to right now.

    Uses FULL bars including premarket if provided — PMH/PML are derived from
    bars timestamped 04:00-09:30 ET on `today`.

    Args:
        exclude_intraday_hl: When True, skip today's session H/L levels (the
            ``intraday`` source). Default False = production behavior unchanged.
            Set via level_flags={} in run_backtest() for A/B testing only.
    """
    history = history.copy()
    history["date"] = history["timestamp_et"].dt.date
    history["time"] = history["timestamp_et"].dt.time

    today_bars = history[history["date"] == today]
    prior_bars = history[history["date"] < today]
    yesterday = today - dt.timedelta(days=1)

    # Today's premarket bars (04:00-09:30) — for PMH/PML
    today_premarket = today_bars[today_bars["time"] < dt.time(9, 30)]
    today_rth = today_bars[today_bars["time"] >= dt.time(9, 30)]

    active: list[float] = []
    multi_day: list[float] = []

    # GLOBEX H/L — overnight session = 18:00 prior day → 09:30 today (~15.5 hours).
    # NEW 2026-05-13 T51 (per KEY-LEVELS-DEEPDIVE brainstorm): captures structural
    # levels from the overnight futures-equivalent session that PMH/PML alone misses.
    # Why this matters: 5/13 J trade targeted 736 (premarket low) — 736 was set
    # during overnight Globex action, not the 04:00-09:30 ET window the old code
    # used. Adding Globex extends premarket coverage backward by ~9 hours.
    yesterday_eve_bars = history[
        (history["date"] == yesterday) & (history["time"] >= dt.time(18, 0))
    ]
    today_pre930 = today_bars[today_bars["time"] < dt.time(9, 30)]
    globex_bars = pd.concat([yesterday_eve_bars, today_pre930], ignore_index=False)
    if not globex_bars.empty:
        globex_high = float(globex_bars["high"].max())
        globex_low = float(globex_bars["low"].min())
        active.append(globex_high)
        active.append(globex_low)

    # PMH / PML — premarket high and low for today (key levels in the playbook)
    if not today_premarket.empty:
        pmh = float(today_premarket["high"].max())
        pml = float(today_premarket["low"].min())
        active.append(pmh)
        active.append(pml)

        # Also detect "tested rejection" levels in premarket — bars whose highs cluster
        # at a specific price ($0.05 buckets), top 3 most-touched. Captures levels J
        # would draw based on repeated rejection (e.g., 721.58 on 5/4 was tested ~5 times
        # in premarket while the absolute PMH was 722.41 from a single 04:00 wick).
        high_buckets = (today_premarket["high"] * 20).round() / 20
        bucket_counts = high_buckets.value_counts()
        # Take buckets with >= 3 touches OR the top 3
        for bucket_price, count in bucket_counts.head(5).items():
            if count >= 3:
                active.append(float(bucket_price))

    if prior_bars.empty:
        if not today_rth.empty:
            active.append(float(today_rth["high"].max()))
            active.append(float(today_rth["low"].min()))
        active = _dedupe(active)
        return LevelSet(active=active, multi_day=multi_day)

    prior_dates = sorted(prior_bars["date"].unique())

    # Prior day's H/L/C — RTH ONLY (09:30-16:00 ET).
    # FIXED 2026-05-08: previously used full session including premarket spikes,
    # which hijacked pdh on days like 5/7 (premarket 04:00 wick to $737.91 became
    # the "prior day high" and $736.11 RTH high was lost). The RTH high is what
    # the playbook treats as the structural level. Premarket spikes go to a
    # separate `premarket_high` field if needed.
    last_date = prior_dates[-1]
    last_day_full = prior_bars[prior_bars["date"] == last_date]
    last_day_rth = last_day_full[
        (last_day_full["timestamp_et"].dt.time >= dt.time(9, 30))
        & (last_day_full["timestamp_et"].dt.time < dt.time(16, 0))
    ]
    if not last_day_rth.empty:
        pdh = float(last_day_rth["high"].max())
        pdl = float(last_day_rth["low"].min())
        pdc = float(last_day_rth["close"].iloc[-1])
    else:
        # Fallback: no RTH bars in prior day (rare — holiday-shortened session?)
        pdh = float(last_day_full["high"].max())
        pdl = float(last_day_full["low"].min())
        pdc = float(last_day_full["close"].iloc[-1])
    for v in (pdh, pdl, pdc):
        active.append(v)
        multi_day.append(v)

    # NEW 2026-05-16 T53 — Volume Profile POC (Point of Control) for prior day.
    # POC = the $0.10 price bucket where the most volume traded during prior RTH session.
    # Widely used by professional traders as a "fair value" magnet and S/R pivot.
    # Institutions often defend or target the prior-day POC when price returns to it.
    # Why $0.10 buckets: SPY trades at ~$570, so $0.10 ≈ 0.018% increments → ~5700 buckets
    # across full range. RTH bars span $1-5 typical daily range → 10-50 meaningful buckets.
    poc = _compute_poc_prior_day(last_day_rth, bucket_size=0.10)
    if poc is not None:
        active.append(poc)
        multi_day.append(poc)

    # 5-day rolling high/low — RTH only, excluding today
    last5_full = prior_bars[prior_bars["date"].isin(prior_dates[-5:])]
    last5_rth = last5_full[
        (last5_full["timestamp_et"].dt.time >= dt.time(9, 30))
        & (last5_full["timestamp_et"].dt.time < dt.time(16, 0))
    ]
    if not last5_rth.empty:
        rh = float(last5_rth["high"].max())
        rl = float(last5_rth["low"].min())
        active.append(rh)
        active.append(rl)
        multi_day.append(rh)
        multi_day.append(rl)

    # Today's session H/L so far (active only).
    # Gated by exclude_intraday_hl flag for A/B scorecard testing (level_shadow_ab.py).
    if not today_rth.empty and not exclude_intraday_hl:
        active.append(float(today_rth["high"].max()))
        active.append(float(today_rth["low"].min()))

    # NEW 2026-05-13 T52 — Daily/weekly/monthly opens (institutional reference levels).
    # Per KEY-LEVELS-DEEPDIVE brainstorm: institutions watch (a) today's RTH open,
    # (b) this week's RTH open (Monday open or earliest weekday available),
    # (c) prior week's RTH close (last Friday's RTH close),
    # (d) prior month's last-trading-day RTH close. These often act as magnets
    # or pivots even when no historical H/L sits at that price.

    # (a) Today's RTH open — the 09:30 bar's open
    if not today_rth.empty:
        today_open = float(today_rth["open"].iloc[0])
        active.append(today_open)

    # (b) This week's RTH open — find Monday-or-earliest of current week
    today_iso_weekday = today.isoweekday()  # 1=Mon, 7=Sun
    week_monday = today - dt.timedelta(days=today_iso_weekday - 1)
    week_dates_so_far = [d for d in (prior_dates + [today]) if week_monday <= d <= today]
    if week_dates_so_far:
        week_open_date = week_dates_so_far[0]
        if week_open_date == today and not today_rth.empty:
            # Today IS the start of the week (Monday or holiday-shortened) — use today's open
            week_open = float(today_rth["open"].iloc[0])
            active.append(week_open)
            # Don't add to multi_day — it's today, not a historical level
        else:
            week_open_bars = history[
                (history["date"] == week_open_date)
                & (history["timestamp_et"].dt.time >= dt.time(9, 30))
            ]
            if not week_open_bars.empty:
                week_open = float(week_open_bars["open"].iloc[0])
                active.append(week_open)
                multi_day.append(week_open)

    # (c) Prior week's RTH close — find Friday-or-latest of last week
    last_week_friday = week_monday - dt.timedelta(days=3)  # Mon - 3 = Fri
    # Walk back up to 5 days to find the latest available trading day from last week
    prior_week_close_date = None
    for offset in range(5):
        candidate = last_week_friday - dt.timedelta(days=offset)
        if candidate in prior_dates:
            prior_week_close_date = candidate
            break
    if prior_week_close_date is not None:
        pwc_bars = history[
            (history["date"] == prior_week_close_date)
            & (history["timestamp_et"].dt.time >= dt.time(9, 30))
            & (history["timestamp_et"].dt.time < dt.time(16, 0))
        ]
        if not pwc_bars.empty:
            prior_week_close = float(pwc_bars["close"].iloc[-1])
            active.append(prior_week_close)
            multi_day.append(prior_week_close)

    # (d) Prior month's RTH close — find last trading day of previous month
    if today.month == 1:
        prev_month_year, prev_month = today.year - 1, 12
    else:
        prev_month_year, prev_month = today.year, today.month - 1
    prior_month_dates = [d for d in prior_dates if d.year == prev_month_year and d.month == prev_month]
    if prior_month_dates:
        prior_month_close_date = max(prior_month_dates)
        pmc_bars = history[
            (history["date"] == prior_month_close_date)
            & (history["timestamp_et"].dt.time >= dt.time(9, 30))
            & (history["timestamp_et"].dt.time < dt.time(16, 0))
        ]
        if not pmc_bars.empty:
            prior_month_close = float(pmc_bars["close"].iloc[-1])
            active.append(prior_month_close)
            multi_day.append(prior_month_close)

    # NEW 2026-05-13 T57 — Anchored VWAP from significant pivots.
    # Per KEY-LEVELS-DEEPDIVE: aVWAP from a swing high/low is dynamic S/R
    # that moves with time. Captures "average price since the pivot" which
    # institutions watch as a magnet.
    #
    # Algorithm:
    #   1. Find the most recent significant swing high + swing low (10-day lookback)
    #   2. For each anchor, compute VWAP from that bar to current
    #   3. Add aVWAP value to multi_day (it's a derived/dynamic level)
    avwap_levels = _compute_anchored_vwaps(history, today, n_anchors=2)
    for avwap in avwap_levels:
        active.append(avwap)
        multi_day.append(avwap)

    # Round numbers
    if not today_rth.empty:
        last_close = float(today_rth["close"].iloc[-1])
    elif not today_premarket.empty:
        last_close = float(today_premarket["close"].iloc[-1])
    else:
        last_close = pdc
    active.append(float(int(last_close)) + 1.0)
    active.append(float(int(last_close)))

    active = _dedupe(active)
    multi_day = _dedupe(multi_day)

    # NEW 2026-05-14 T58 — Liquidity sweep detection.
    # For each level in `active`, check if a recent bar (last 3 trading days RTH)
    # wicked through it but closed back inside the prior range. Such levels are
    # institutional liquidity-grab survivors — flag as ★ upgraded.
    swept = _detect_swept_levels(history, today, active, lookback_days=3)

    return LevelSet(active=active, multi_day=multi_day, swept_levels=swept)


def _detect_swept_levels(
    history: pd.DataFrame,
    today: dt.date,
    levels: list[float],
    lookback_days: int = 3,
    min_pierce_cents: float = 0.10,
    max_close_distance_cents: float = 0.30,
) -> list[float]:
    """Identify levels that were SWEPT (wicked through then closed back inside) in recent history.

    A level at price L is "swept" if any bar in the lookback window:
      - Has H > L + min_pierce_cents (pierced from below) AND close ≤ L
        → bullish liquidity grab below resistance, level rejected, level upgraded
      OR
      - Has L < L - min_pierce_cents (pierced from above) AND close ≥ L
        → bearish liquidity grab above support, level rejected, level upgraded
      AND
      - The pierce-to-close distance must be ≥ max_close_distance_cents (meaningful rejection,
        not a tiny wick)

    Returns the list of levels (subset of `levels`) that show this pattern.

    Args:
        history: full bar DataFrame
        today: current date
        levels: candidate levels to check (typically active set from _detect_from_history)
        lookback_days: how many trading days to scan
        min_pierce_cents: minimum wick distance through level to count as sweep ($0.10 default)
        max_close_distance_cents: minimum body-distance from level after sweep ($0.30 default)
    """
    if history.empty or not levels:
        return []
    history = history.copy()
    if "date" not in history.columns:
        history["date"] = history["timestamp_et"].dt.date
    cutoff_date = today - dt.timedelta(days=lookback_days)
    recent = history[
        (history["date"] >= cutoff_date)
        & (history["timestamp_et"].dt.time >= dt.time(9, 30))
        & (history["timestamp_et"].dt.time < dt.time(16, 0))
    ]
    if recent.empty:
        return []

    swept: set[float] = set()
    for L in levels:
        # Bullish liquidity grab: H > L + pierce, close ≤ L (rejected from above)
        bull_grab = recent[
            (recent["high"] > L + min_pierce_cents)
            & (recent["close"] <= L)
            & ((L - recent["close"]) >= max_close_distance_cents)
        ]
        # Bearish liquidity grab: L < L - pierce, close ≥ L (rejected from below)
        bear_grab = recent[
            (recent["low"] < L - min_pierce_cents)
            & (recent["close"] >= L)
            & ((recent["close"] - L) >= max_close_distance_cents)
        ]
        if not bull_grab.empty or not bear_grab.empty:
            swept.add(L)
    return sorted(swept)


def _compute_anchored_vwaps(
    history: pd.DataFrame,
    today: dt.date,
    n_anchors: int = 2,
    lookback_days: int = 10,
) -> list[float]:
    """Find recent swing pivots + compute anchored VWAP from each to today.

    Returns up to `n_anchors × 2` aVWAP values (1 per swing high + 1 per swing low,
    times n_anchors of each). Empty list if insufficient history.

    A "swing pivot" here = a bar whose high (or low) is the local extremum over
    a 5-bar window before AND after. Coarse-grained but robust on 5m bars.
    """
    if history.empty or "high" not in history.columns:
        return []

    # Restrict to the lookback window (RTH only — premarket wicks distort)
    cutoff_date = today - dt.timedelta(days=lookback_days)
    window = history[
        (history["date"] >= cutoff_date)
        & (history["timestamp_et"].dt.time >= dt.time(9, 30))
        & (history["timestamp_et"].dt.time < dt.time(16, 0))
    ].reset_index(drop=True)
    if len(window) < 11:  # need 5 bars before + pivot + 5 bars after
        return []

    out: list[float] = []
    pivot_window = 5  # bars before AND after that pivot must exceed

    # Find swing highs and lows (top + bottom by extreme value, that survived a 5-bar window)
    swing_highs: list[int] = []  # indices in `window` of swing high pivots
    swing_lows: list[int] = []
    for i in range(pivot_window, len(window) - pivot_window):
        bar_high = window["high"].iloc[i]
        bar_low = window["low"].iloc[i]
        is_swing_high = (
            bar_high == window["high"].iloc[i - pivot_window:i + pivot_window + 1].max()
        )
        is_swing_low = (
            bar_low == window["low"].iloc[i - pivot_window:i + pivot_window + 1].min()
        )
        if is_swing_high:
            swing_highs.append(i)
        if is_swing_low:
            swing_lows.append(i)

    # Pick the `n_anchors` most recent (highest index) of each
    recent_highs = swing_highs[-n_anchors:]
    recent_lows = swing_lows[-n_anchors:]

    # Compute aVWAP from each anchor to end of window
    for anchor_idx in recent_highs + recent_lows:
        anchor_to_end = window.iloc[anchor_idx:].copy()
        if anchor_to_end.empty:
            continue
        # Typical price = (H + L + C) / 3
        typical = (anchor_to_end["high"] + anchor_to_end["low"] + anchor_to_end["close"]) / 3.0
        vol = anchor_to_end["volume"].astype(float)
        total_vol = vol.sum()
        if total_vol <= 0:
            continue
        avwap = float((typical * vol).sum() / total_vol)
        out.append(avwap)

    return out


def _compute_poc_prior_day(
    rth_bars: pd.DataFrame,
    bucket_size: float = 0.10,
) -> float | None:
    """Compute Volume Profile Point of Control (POC) for a prior RTH session.

    POC = the $0.10 price bucket that captured the most cumulative volume.
    Each bar's volume is attributed to its typical price ((H+L+C)/3) bucket.

    Args:
        rth_bars: prior-day RTH OHLCV DataFrame (already filtered 09:30–16:00).
        bucket_size: bucket width in dollars (default $0.10).

    Returns:
        The bucket center price with maximum volume, or None if insufficient data.
    """
    if rth_bars.empty or "volume" not in rth_bars.columns:
        return None
    typical = (rth_bars["high"] + rth_bars["low"] + rth_bars["close"]) / 3.0
    # Bucket = round typical price to nearest bucket boundary
    buckets = (typical / bucket_size).round() * bucket_size
    bucket_vol = {}
    for bkt, vol in zip(buckets, rth_bars["volume"]):
        bucket_vol[bkt] = bucket_vol.get(bkt, 0.0) + float(vol)
    if not bucket_vol:
        return None
    poc = max(bucket_vol, key=lambda k: bucket_vol[k])
    return round(float(poc), 2)


def _dedupe(values: list[float], tolerance: float = 0.05) -> list[float]:
    """Sort + collapse near-duplicates."""
    values = sorted(set(values))
    if not values:
        return []
    out = [values[0]]
    for v in values[1:]:
        if v - out[-1] > tolerance:
            out.append(v)
    return out
