"""VWAP_TREND_PULLBACK watcher (H4) — trend-day pullback to session VWAP.

The LIVE detector for the data-discovered survivor ``H4_vwap_pullback`` (the
diversifying, non-J-anchored edge from ``backtest/autoresearch/infinite_ammo_discovery.py``).
Ratified by ``backtest/autoresearch/vwap_pullback_ratify.py`` ->
``analysis/recommendations/vwap-trend-pullback-LIVE.json``:

    ATM real-OPRA fills: exp +$45.88/trade, WR 42.4%, n=92, total +$4,221
    OOS +$69.22/trade, OOS sign-stable, DSR PASS, drop-top5 +$25.43 (broad-based),
    both sides positive (C 46.3% / P 36.8%). Causality: future-poison PASS (no
    look-ahead). Walk-forward median 1.679 (OOS per-trade > IS), 64% OOS months
    positive. Sub-window: 1/4 hurt. Honest caveat: regime-sensitive — bled
    2025-Q2/Q3, then 7 consecutive positive OOS months 2025-11..2026-05; proxy
    strikes (L58), not real ★★★ levels; n modest.

THIS DETECTOR IS THE EXACT ENTRY LOGIC of ``detect_vwap_pullback`` (the discovery
detector that produced the validated numbers), re-expressed in the streaming
``BarContext`` form the live watcher fleet uses. Parity is asserted in
``backtest/tests/test_vwap_trend_pullback_watcher.py`` (same signals on the same
historical day as the batch detector).

PATTERN (one entry per day):
  1. TREND ESTABLISHED: the first TREND_BARS (6) RTH bars all CLOSE on the same side
     of the *as-of* session VWAP (clean one-sided open).
         all closes > their VWAP  -> uptrend  -> CALLs
         all closes < their VWAP  -> downtrend -> PUTs
  2. PULLBACK TAG (after the trend window): the FIRST bar whose
         uptrend:   low  <= VWAP * (1 + TOUCH_TOL)  AND  close > VWAP   -> enter CALL
         downtrend: high >= VWAP * (1 - TOUCH_TOL)  AND  close < VWAP   -> enter PUT
     fires the in-trend pullback entry. One per day; cooldown is "fired today".
  3. STOP (chart/structural, L51/L55/C2 — chart-stop ONLY, no premium stop):
         uptrend:   session min low  to date (against a call)
         downtrend: session max high to date (against a put)

CAUSALITY: session VWAP at bar i uses only that session's bars[0..i] (cumulative
typical-price * volume); the trend check and the touch are evaluated at-or-before
the entry bar's close. Entry fills NEXT bar (heartbeat/sim convention). Verified by
the future-poison test in the ratify harness.

WARMUP-SAFE: needs >= TREND_BARS+1 RTH bars in the session before it can fire; before
that it returns None. Per-day state (trend side, fired flag) resets on date change.

WATCH_ONLY by default per OP-21 (3 live J wins before any live order path). The
scorecard clears the OP-16/OP-22 SHIP bar (OOS+ AND WF>=0.70 AND sub-window stable
AND A/B scorecard filed) for an after-hours propose-and-ship of the heartbeat wiring;
J holds REVOKE. This module itself NEVER places an order — order placement is the
heartbeat's job once wired.

Reuse / template: backtest/lib/watchers/floor_hold_bounce_watcher.py (ctx-only
watcher shape); the discovery detector backtest/autoresearch/infinite_ammo_discovery.py
(detect_vwap_pullback) for the exact logic.
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

import numpy as np
import pandas as pd

from . import WatcherSignal
from ..filters import BarContext


# ── Detection parameters (match infinite_ammo_discovery.detect_vwap_pullback) ──
TREND_BARS: int = 6           # first 30 min (6x5m) all one side of VWAP = clean trend day
TOUCH_TOL: float = 0.0008     # within 0.08% of VWAP counts as a tag

# RTH session window (ET). Mirrors discovery's RTH_OPEN/RTH_CLOSE; the pullback can
# fire any time after the trend window within RTH (no extra time gate — the trend
# structure IS the gate; J directive "remove time gates" honored).
RTH_OPEN: dt.time = dt.time(9, 30)
RTH_CLOSE: dt.time = dt.time(16, 0)

# ── Exit knobs (v15 stack; chart-stop ONLY per L51/L55/C2) ────────────────────
DEFAULT_PREMIUM_STOP_PCT: float = -0.99   # disabled — chart stop is the only exit gate
DEFAULT_TP1_PREMIUM_PCT: float = 0.30     # v15 TP1 fallback
DEFAULT_TP1_QTY_FRACTION: float = 0.50    # v15 prod
DEFAULT_RUNNER_TARGET_PCT: float = 2.5    # v15 prod
DEFAULT_STRIKE_OFFSET: int = 2            # ATM/ITM1 validated; mapped to account tier at wiring


# ── Per-day module state (resets on date change) ──────────────────────────────
# Live + replay both call this once per bar in chronological order, so simple
# module-level day state is sufficient and matches the floor_hold / cooldown pattern.
_state_date: Optional[str] = None
_trend_side: Optional[str] = None      # "C" | "P" | None (no clean trend today)
_trend_resolved: bool = False          # have we evaluated the TREND_BARS window yet
_fired_today: bool = False


def _reset_day(day_str: str) -> None:
    global _state_date, _trend_side, _trend_resolved, _fired_today
    _state_date = day_str
    _trend_side = None
    _trend_resolved = False
    _fired_today = False


def _session_rth_vwap(prior_bars: pd.DataFrame, today: dt.date) -> Optional[pd.DataFrame]:
    """Return today's RTH bars (chronological) with an *as-of* cumulative session
    VWAP column. Causal: VWAP at row i uses only rows[0..i] of the session.

    prior_bars is the full history including the current (trigger) bar at [-1].
    """
    if prior_bars is None or prior_bars.empty:
        return None
    df = prior_bars
    # Filter to today's RTH. timestamp_et may be tz-aware or naive; normalize via .dt.
    ts = df["timestamp_et"]
    try:
        dates = ts.dt.date
        times = ts.dt.time
    except AttributeError:
        return None
    mask = (dates == today) & (times >= RTH_OPEN) & (times < RTH_CLOSE)
    rth = df.loc[mask]
    if rth.empty:
        return None
    rth = rth.sort_values("timestamp_et")
    tp = (rth["high"] + rth["low"] + rth["close"]) / 3.0
    pv = (tp * rth["volume"]).cumsum()
    vv = rth["volume"].cumsum().replace(0, np.nan)
    vwap = (pv / vv).bfill()
    out = rth.copy()
    out["_vwap"] = vwap.values
    return out


def detect_vwap_trend_pullback_setup(ctx: BarContext) -> Optional[WatcherSignal]:
    """Detect VWAP_TREND_PULLBACK (H4) on the current bar.

    Returns a WatcherSignal (direction long=CALL / short=PUT) on the first in-trend
    session-VWAP tag of a clean one-sided-VWAP trend day; None otherwise. One signal
    per day. Pure read of ctx; no I/O, no order placement.
    """
    global _trend_side, _trend_resolved, _fired_today

    bar_time = ctx.timestamp_et.time()
    today = ctx.timestamp_et.date()
    day_str = today.isoformat()

    # New day -> reset per-day state.
    if _state_date != day_str:
        _reset_day(day_str)

    # Only operate inside RTH.
    if bar_time < RTH_OPEN or bar_time >= RTH_CLOSE:
        return None
    # Already took today's one entry.
    if _fired_today:
        return None

    rth = _session_rth_vwap(ctx.prior_bars, today)
    if rth is None or len(rth) < TREND_BARS + 1:
        return None  # warmup: need the trend window + at least one post-window bar

    closes = rth["close"].values
    highs = rth["high"].values
    lows = rth["low"].values
    vwap = rth["_vwap"].values

    # ── Resolve the trend side ONCE, from the first TREND_BARS bars (as-of VWAP) ──
    if not _trend_resolved:
        head_c = closes[:TREND_BARS]
        head_v = vwap[:TREND_BARS]
        if np.all(head_c > head_v):
            _trend_side = "C"
        elif np.all(head_c < head_v):
            _trend_side = "P"
        else:
            _trend_side = None
        _trend_resolved = True

    if _trend_side is None:
        return None  # not a clean one-sided trend day

    # The current bar is the last row of `rth` (prior_bars includes the trigger bar).
    j = len(rth) - 1
    if j < TREND_BARS:
        return None  # still inside the trend window — no pullback entries yet

    v = float(vwap[j])
    if v <= 0:
        return None
    cur_close = float(closes[j])
    cur_high = float(highs[j])
    cur_low = float(lows[j])

    if _trend_side == "C":
        tagged = cur_low <= v * (1 + TOUCH_TOL) and cur_close > v
        stop = float(np.min(lows[: j + 1]))   # session min low to date (matches discovery)
        direction = "long"
    else:
        tagged = cur_high >= v * (1 - TOUCH_TOL) and cur_close < v
        stop = float(np.max(highs[: j + 1]))  # session max high to date
        direction = "short"

    if not tagged:
        return None

    # ── Entry — emit signal, mark fired ──────────────────────────────────────
    _fired_today = True
    entry = cur_close

    # Spot-price exit proxies (heartbeat/sim use the premium-% knobs in metadata for
    # canonical exits; these spot levels are advisory like the other watchers).
    if direction == "long":
        tp1_price = entry + 0.70
        runner_price = entry + 2.50
    else:
        tp1_price = entry - 0.70
        runner_price = entry - 2.50

    vix_now = getattr(ctx, "vix_now", None) or 17.0
    dist_pct = abs(cur_low - v) / v if direction == "long" else abs(cur_high - v) / v

    # Confidence: tighter VWAP tag = cleaner pullback. (Tiered like the fleet; the
    # validated edge is the BASE pattern — confidence is for ranking, not gating.)
    if dist_pct <= 0.0003:
        confidence = "high"
    elif dist_pct <= 0.0006:
        confidence = "medium"
    else:
        confidence = "low"

    side_letter = "C" if direction == "long" else "P"
    return WatcherSignal(
        watcher_name="vwap_trend_pullback",
        setup_name="VWAP_TREND_PULLBACK",
        direction=direction,
        entry_price=float(entry),
        stop_price=float(stop),
        tp1_price=float(tp1_price),
        runner_price=float(runner_price),
        confidence=confidence,
        reason=(
            f"VWAP trend-day pullback ({side_letter}): first {TREND_BARS} RTH bars all "
            f"closed {'above' if side_letter == 'C' else 'below'} session VWAP (clean "
            f"{'up' if side_letter == 'C' else 'down'}trend), then this bar tagged VWAP "
            f"({v:.2f}) in-trend (close {cur_close:.2f} {'>' if side_letter == 'C' else '<'} "
            f"VWAP) -> enter {'calls' if side_letter == 'C' else 'puts'}. "
            f"Chart-stop {stop:.2f} (session {'low' if side_letter == 'C' else 'high'} to "
            f"date; chart-stop ONLY per L51/L55). VIX={vix_now:.1f}. "
            f"H4 data-discovered edge (OOS +$69/trade, DSR PASS, causality PASS)."
        ),
        triggers_fired=["vwap_trend_established", "vwap_pullback_tag"],
        metadata={
            "vwap_at_bar": round(v, 4),
            "trend_bars": TREND_BARS,
            "touch_tol_pct": TOUCH_TOL,
            "vwap_tag_distance_pct": round(dist_pct, 5),
            "strike_offset": DEFAULT_STRIKE_OFFSET,
            "default_premium_stop_pct": DEFAULT_PREMIUM_STOP_PCT,
            "default_tp1_pct": DEFAULT_TP1_PREMIUM_PCT,
            "default_tp1_qty_fraction": DEFAULT_TP1_QTY_FRACTION,
            "default_runner_target_pct": DEFAULT_RUNNER_TARGET_PCT,
            "winner_combo_source": "analysis/recommendations/vwap-trend-pullback-LIVE.json",
            "promotion_status": "WATCH_ONLY",
            "ship_bar": "OOS+ AND WF>=0.70 AND sub-window stable AND A/B scorecard filed "
                        "(OP-16/OP-22) — scorecard PASS; J holds REVOKE.",
        },
    )
