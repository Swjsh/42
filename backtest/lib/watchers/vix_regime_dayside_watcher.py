"""VIX_REGIME_DAYSIDE watcher (J_VIX_DAYSIDE) — edge #4, DORMANT live port.

The streaming ``BarContext`` port of the VALIDATED VIX-regime-conditional DAY+SIDE
directional detector in ``backtest/autoresearch/_b5_vix_regime_dayside.py``
(``detect_opt_signals`` + ``favorable_regime`` + ``trend_side``). Ported BYTE-FOR-BYTE —
the trend-side definition (first 3 RTH closes one side of as-of session VWAP), the VIX
regime classifier (level <= trailing-median - low_margin AND 5-bar slope not-rising), the
09:35-11:30 ET morning window and the one-causal-entry/day rule are IDENTICAL to the
research detector, so the live watcher and the autoresearch sim make the SAME decision
(no detector drift, C14).

THESIS (the B5 convergence play, J 2026-06-21):
  Three independent results converge on VIX as THE directional axis for intraday SPY:
  edge#2's day-side selection, the ML feature ranking (VIX #1, vix_slope5 #2), and the
  live vwap_continuation VIX-gate. The distilled system: take the established morning
  day-trend side directionally, but ONLY in the favorable VIX regime (LOW + not-rising) —
  low/declining VIX is where directional continuation pays (L93/L115 declining-VIX).

PATTERN (one entry per day, causal, fill next bar open — no look-ahead, L166).
BYTE-FOR-BYTE the same decision as ``_b5_vix_regime_dayside.detect_opt_signals``:

  1. TREND SIDE from the first TREND_BARS (3) RTH bars: all CLOSE on the same side of
     the *as-of* session VWAP -> that is the day's side (C if above / P if below). IDENTICAL
     to the validated vwap_continuation / vwap_reclaim trend definition (no drift).
  2. VIX REGIME (as-of the candidate entry bar, causal): the favorable regime is
     ``vix_level <= (trailing_median - low_margin)`` AND (slope_rule) ``vix_slope5 <= 0``.
     trailing_median = causal rolling median of the PRIOR VIX_MEDIAN_BARS (78) bars,
     shifted by 1 (a bar never sets its own baseline); vix_slope5 = vix[i] - vix[i-5].
  3. TAKE THE DAY-TREND SIDE directionally on the FIRST bar inside the morning window
     (09:35-11:30 ET) at/after the trend window whose VIX regime is favorable. One entry
     per session; entry fills the NEXT bar open.

VALIDATED CELL (the gate-clearing config — analysis/recommendations/b5-vix-regime-dayside.json):
  low_margin=0.25, slope_rule="not_rising", ATM (strike_offset=0), premium_stop=-0.08.
  Clears ALL 8 anti-cherry-pick gates @ ATM/Safe-2 (OOS +$79.49/tr, drop-top5 +$25.91,
  chart-stop-only OOS +$0.15 POSITIVE = no truncation, posQ 5/6, beats coin-flip null).
  The ITM-2 SURVIVOR tier at the same cell is a truncation-artifact (chart-stop-only OOS
  flips negative) -> NOT shipped. Per C29 (gates do not transfer across strike tiers) the
  Safe-2 ship cell is ATM; this is a Safe-2-only edge as validated.

DORMANT: this module ONLY observes + logs (WATCH_ONLY, OP-21). The heartbeat order path is
  gated on ``params.j_vix_dayside_enabled`` (default FALSE = inert = zero behavior change).
  J flips the flag; J holds REVOKE (Rule 9 / OP-25). Live gate: 3 live J confirmations.

CAUSALITY: session VWAP at bar i uses only that session's bars[0..i]; the trend check, the
  VIX level/median/slope and the morning-window check are all read at-or-before the current
  (trigger) bar's close; entry fills the NEXT bar (heartbeat/sim convention, L166). The VIX
  trailing median is shift(1) so it never includes the current bar's own value (C6).

VIX-SERIES REQUIREMENT (the one structural difference from edge #2): the regime needs an
  intraday VIX series for trailing-median(78) + slope(5). The live ``BarContext`` carries
  only ``vix_now``/``vix_prior`` (not an intraday VIX history). So the streaming wrapper
  reads an OPTIONAL ``ctx.vix_intraday`` series (a list/np.ndarray of 5m VIX closes aligned
  to ``ctx.prior_bars``, newest last) when present; ABSENT it CANNOT confirm the regime and
  returns None (SKIP — never guess, exactly as the research ``favorable_regime`` returns
  None -> skip). This keeps the live wiring honest and DORMANT. The pure core + the gym /
  parity tests exercise the regime math against the research VIX array (where it IS present).

Reuse / template:
  backtest/lib/watchers/vwap_reclaim_failed_break_watcher.py (edge #2 DORMANT shape)
  backtest/autoresearch/_b5_vix_regime_dayside.py (favorable_regime / trend_side / detect_opt_signals)
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from . import WatcherSignal
from ..filters import BarContext


# ── Detection parameters (IDENTICAL to _b5_vix_regime_dayside — no silent drift, C14) ─
TREND_BARS: int = 3                              # first 15 min set the side
ENTRY_GATE: tuple[dt.time, dt.time] = (dt.time(9, 35), dt.time(11, 30))  # morning window
RTH_OPEN: dt.time = dt.time(9, 30)
RTH_CLOSE: dt.time = dt.time(16, 0)

# VIX regime knobs — the VALIDATED gate-clearing cell (b5-vix-regime-dayside.json).
VIX_SLOPE_BARS: int = 5          # vix_slope5 (ML #2 feature): vix[i] - vix[i-5]
VIX_MEDIAN_BARS: int = 78        # ~1 trading day of 5m bars for the trailing-median baseline
DEFAULT_LOW_MARGIN: float = 0.25  # the validated cell: VIX <= (trailing_median - 0.25)
DEFAULT_SLOPE_RULE: str = "not_rising"  # the validated cell: vix_slope5 <= 0

# ── Exit / sizing knobs — ADVISORY FALLBACK ONLY (surfaced on metadata so an observer
#    sees the validated cell). NOT the live authority: the heartbeat / sim MUST source the
#    stop/tp1 from the ISOLATED params keys (j_vix_dayside_premium_stop_pct / _tp1_pct) —
#    NOT from these module constants and NOT from the GLOBAL premium_stop_pct (-0.50
#    catastrophe cap) / tp1_premium_pct (0.50). filters.py exposes
#    vix_dayside_{premium_stop_pct,tp1_pct}(params) to read the isolated keys (gamma-sync
#    single source of truth). These are only the fallback when no params dict is supplied. ─
DEFAULT_STRIKE_OFFSET: int = 0            # ATM (the validated Safe-2 ship cell)
DEFAULT_PREMIUM_STOP_PCT: float = -0.08   # validated cell (== params j_vix_dayside_premium_stop_pct)
DEFAULT_TP1_PREMIUM_PCT: float = 0.30     # Safe-2 v15 TP1 (== params j_vix_dayside_tp1_pct)
DEFAULT_TP1_QTY_FRACTION: float = 0.50    # v15 prod (L108)
DEFAULT_RUNNER_TARGET_PCT: float = 2.5    # v15 prod (L109)

# Spot-price target geometry for the WatcherSignal (advisory; the real-fills exit stack on
# the sim/heartbeat side uses chart-stop + ribbon-flip + chandelier + time).
_TP1_SPY_MOVE: float = 0.70
_RUNNER_SPY_MOVE: float = 2.50
_SWING_LOOKBACK: int = 12                  # chart-stop swing window (matches research _swing_stop)


@dataclass(frozen=True)
class VixDaysideResult:
    """Pure detector output (no ctx) — directly unit-testable."""
    direction: str          # "long" (calls) | "short" (puts)
    side: str               # "C" | "P"
    entry: float            # the candidate entry bar's close
    stop_level: float       # 12-bar swing chart stop (the structural invalidation)
    vix_at_bar: float
    vix_median_at_bar: float
    vix_slope_at_bar: float


# ── Shared VIX-regime primitives — BYTE-FOR-BYTE from _b5_vix_regime_dayside ──────
def causal_vix_median(vix: np.ndarray, window: int = VIX_MEDIAN_BARS) -> np.ndarray:
    """Trailing median of VIX over the PRIOR ``window`` bars (shifted by 1 so bar i's own
    value never sets its own baseline). Causal — out[i] uses vix[i-window..i-1].

    IDENTICAL to ``_b5_vix_regime_dayside.causal_vix_median``."""
    s = pd.Series(vix)
    med = s.rolling(window, min_periods=max(5, window // 4)).median().shift(1)
    return med.to_numpy()


def vix_slope(vix: np.ndarray, bars: int = VIX_SLOPE_BARS) -> np.ndarray:
    """vix[i] - vix[i-bars] (the ML #2 feature). Causal. NaN for i < bars.

    IDENTICAL to ``_b5_vix_regime_dayside.vix_slope``."""
    out = np.full(len(vix), np.nan)
    for i in range(bars, len(vix)):
        out[i] = vix[i] - vix[i - bars]
    return out


def favorable_regime(vix_lvl: Optional[float], vix_med: Optional[float],
                     vix_slp: Optional[float], low_margin: float = DEFAULT_LOW_MARGIN,
                     slope_rule: str = DEFAULT_SLOPE_RULE) -> Optional[bool]:
    """The favorable VIX regime: LOW level (>= low_margin points BELOW trailing median)
    AND (slope_rule) the 5-bar slope not rising. Returns None if inputs unavailable (so the
    day is SKIPPED, never guessed). Pure function of as-of inputs (causal).

    IDENTICAL to ``_b5_vix_regime_dayside.favorable_regime``."""
    if vix_lvl is None or vix_med is None or (isinstance(vix_med, float) and math.isnan(vix_med)):
        return None
    is_low = vix_lvl <= (vix_med - low_margin)
    if slope_rule == "not_rising":
        if vix_slp is None or (isinstance(vix_slp, float) and math.isnan(vix_slp)):
            return None
        not_rising = vix_slp <= 0.0
        return bool(is_low and not_rising)
    return bool(is_low)   # slope_rule == "any"


def trend_side(closes, vwap, n: int = TREND_BARS) -> Optional[str]:
    """The day's side from the first ``n`` RTH bars: all closes one side of as-of VWAP.

    BYTE-FOR-BYTE the same construction as ``_b5_vix_regime_dayside.detect_opt_signals``'s
    head check (and the shared vwap_continuation / vwap_reclaim trend definition): all
    closes above their as-of VWAP -> "C"; all below -> "P"; mixed (or warmup) -> None."""
    head_c = np.asarray(closes[:n], dtype=float)
    head_v = np.asarray(vwap[:n], dtype=float)
    if len(head_c) < n:
        return None
    if np.all(head_c > head_v):
        return "C"
    if np.all(head_c < head_v):
        return "P"
    return None


def _swing_stop(highs, lows, j: int, side: str, entry: float,
                lookback: int = _SWING_LOOKBACK) -> float:
    """12-bar swing chart stop. IDENTICAL geometry to ``_b5_vix_regime_dayside._swing_stop``
    (calls: deepest swing LOW if below close else close-1; puts: highest swing HIGH if above
    close else close+1)."""
    lo = max(0, j - lookback + 1)
    if side == "C":
        rej = float(np.min(lows[lo: j + 1]))
        return rej if rej < entry else entry - 1.0
    rej = float(np.max(highs[lo: j + 1]))
    return rej if rej > entry else entry + 1.0


def detect_vix_regime_dayside_core(
    closes,
    highs,
    lows,
    vwap,
    times,
    vix,
    vix_med,
    vix_slp,
    *,
    low_margin: float = DEFAULT_LOW_MARGIN,
    slope_rule: str = DEFAULT_SLOPE_RULE,
) -> Optional[VixDaysideResult]:
    """Pure VIX_REGIME_DAYSIDE decision over a session's as-of arrays.

    ``closes/highs/lows/vwap`` are the session's RTH arrays (chronological, as-of cumulative
    session VWAP); ``times`` is the matching per-bar ``datetime.time`` array; ``vix`` /
    ``vix_med`` / ``vix_slp`` are the per-bar (as-of) VIX level / causal trailing-median /
    causal 5-bar slope arrays aligned to the SAME bars. Reproduces the per-day body of
    ``_b5_vix_regime_dayside.detect_opt_signals`` EXACTLY (trend side from the head -> first
    morning-window bar in the favorable VIX regime -> that bar's entry). Returns the entry
    bar's signal, or None if no qualifying bar inside the morning window."""
    side = trend_side(closes, vwap, TREND_BARS)
    if side is None:
        return None
    n = len(closes)
    # GUARD = TREND_BARS + 1 (head + >=1 entry candidate). NOTE the research batch detector
    # (_b5_vix_regime_dayside.detect_opt_signals) uses TREND_BARS + 2 as a DEGENERATE-DAY
    # filter over a day's FULL RTH frame; on real 0DTE SPY data every RTH session has >=78
    # bars, so that filter never excludes a real day and the two AGREE on the validated set
    # (proven by test_parity_with_validated_research_detector). Do NOT raise this to +2: the
    # streaming wrapper fires only when the first-favorable bar (j=TREND_BARS) IS the current
    # bar, which is identifiable at exactly TREND_BARS+1 bars — waiting for +2 would push the
    # look past the entry bar and silently kill all live firing for j=TREND_BARS entries.
    if n < TREND_BARS + 1:
        return None
    for j in range(TREND_BARS, n):
        t = times[j]
        if not (ENTRY_GATE[0] <= t <= ENTRY_GATE[1]):
            if t > ENTRY_GATE[1]:
                break
            continue
        lvl = float(vix[j]) if j < len(vix) else None
        med = float(vix_med[j]) if j < len(vix_med) else None
        slp = float(vix_slp[j]) if j < len(vix_slp) else None
        fav = favorable_regime(lvl, med, slp, low_margin, slope_rule)
        if fav is None or not fav:
            continue
        entry = float(closes[j])
        stop = _swing_stop(highs, lows, j, side, entry)
        direction = "long" if side == "C" else "short"
        return VixDaysideResult(
            direction=direction, side=side, entry=entry, stop_level=float(stop),
            vix_at_bar=float(lvl), vix_median_at_bar=float(med),
            vix_slope_at_bar=float(slp) if slp is not None else float("nan"),
        )
    return None


# ── Per-INSTANCE day state (MED-1 fix, mirrors edge #2) ───────────────────────────
class VixRegimeDaysideDetector:
    """Stateful streaming wrapper for VIX_REGIME_DAYSIDE with PER-INSTANCE one-entry/day
    state. Two distinct instances never corrupt each other's guard. The detection itself is
    pure (``detect_vix_regime_dayside_core``); the only state is the per-day
    ``_state_date``/``_fired_today`` pair used to enforce one causal entry per day."""

    def __init__(self) -> None:
        self._state_date: Optional[str] = None
        self._fired_today: bool = False

    def reset_day(self, day_str: str) -> None:
        self._state_date = day_str
        self._fired_today = False

    def detect(self, ctx: BarContext) -> Optional[WatcherSignal]:
        return _detect_impl(ctx, self)


_default_detector = VixRegimeDaysideDetector()


def _reset_day(day_str: str) -> None:
    """Reset the DEFAULT detector's per-day guard (back-compat shim for tests)."""
    _default_detector.reset_day(day_str)


def _session_rth(prior_bars: pd.DataFrame, today: dt.date) -> Optional[pd.DataFrame]:
    """Today's RTH bars (chronological) with an *as-of* cumulative session VWAP column.

    Causal: VWAP at row i uses only rows[0..i] of the session. BYTE-FOR-BYTE the same VWAP
    as ``vwap_reclaim_failed_break_watcher._session_rth_vwap`` / ``session_vwap_asof``
    (typical price (H+L+C)/3 * volume, cumulative)."""
    if prior_bars is None or prior_bars.empty:
        return None
    df = prior_bars
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


def _vix_intraday_series(ctx: BarContext, n_rth: int) -> Optional[np.ndarray]:
    """The intraday VIX 5m-close series ending at the current RTH frame, newest last.

    The regime needs a VIX SERIES (trailing-median 78 + slope 5) the live ``BarContext``
    does NOT carry by default (only ``vix_now``/``vix_prior``). Read an OPTIONAL
    ``ctx.vix_intraday`` (list / np.ndarray, newest last) when present; ABSENT -> None (the
    wrapper then SKIPs — never guess the regime). The series must END aligned to today's RTH
    frame (its last ``n_rth`` values line up with today's RTH bars) but may carry MORE prior
    history so the trailing median(78) + slope(5) have their warmup window — we return the
    FULL array (not just the RTH tail); the caller computes the causal regime over the full
    series and then tail-slices to the RTH bars. We require >= ``n_rth`` values (at minimum
    today's RTH frame). This is the forward-compatible seam: the live feed / heartbeat can
    thread the intraday VIX series in; until it does, the live block stays inert
    (DORMANT-safe)."""
    raw = getattr(ctx, "vix_intraday", None)
    if raw is None:
        return None
    try:
        arr = np.asarray(raw, dtype=float)
    except (TypeError, ValueError):
        return None
    if arr.size < n_rth:
        return None
    return arr


def detect_vix_regime_dayside_setup(ctx: BarContext) -> Optional[WatcherSignal]:
    """Detect VIX_REGIME_DAYSIDE (J_VIX_DAYSIDE) on the current bar (WATCH-ONLY).

    direction="long" (buy calls) on an above-VWAP morning trend in the favorable VIX regime
    (LOW + not-rising); direction="short" (buy puts) on the below-VWAP mirror.

    Fires at most ONCE per day, only inside the morning window (09:35-11:30 ET) after the
    TREND_BARS warmup, when the regime is confirmed favorable as-of the current bar. Returns
    None on any gate miss OR when the intraday VIX series is unavailable (regime unconfirmed
    -> SKIP, never guess). Pure read of ctx; no I/O, no order placement."""
    return _default_detector.detect(ctx)


def _detect_impl(ctx: BarContext, detector: "VixRegimeDaysideDetector") -> Optional[WatcherSignal]:
    """Streaming detection body driven against a specific detector's per-day state."""
    bar_time = ctx.timestamp_et.time()
    today = ctx.timestamp_et.date()
    day_str = today.isoformat()

    if detector._state_date != day_str:
        detector.reset_day(day_str)

    if bar_time < RTH_OPEN or bar_time >= RTH_CLOSE:
        return None
    if detector._fired_today:
        return None
    # Past the morning window: the research loop `break`s the per-day scan.
    if bar_time > ENTRY_GATE[1]:
        return None

    rth = _session_rth(ctx.prior_bars, today)
    if rth is None or len(rth) < TREND_BARS + 1:
        return None

    closes = rth["close"].values
    highs = rth["high"].values
    lows = rth["low"].values
    vwap = rth["_vwap"].values
    times = [t.time() for t in pd.to_datetime(rth["timestamp_et"]).tolist()]
    n_rth = len(closes)

    # VIX series (the one structural requirement). Absent -> regime unconfirmed -> SKIP.
    # The series may carry MORE prior history than today's RTH frame (for the median(78)/
    # slope(5) warmup); compute the causal regime over the FULL series, then tail-slice the
    # regime arrays to the RTH bars so they're index-aligned to the core's RTH iteration.
    vix_full = _vix_intraday_series(ctx, n_rth)
    if vix_full is None:
        return None
    vix_med_full = causal_vix_median(vix_full, VIX_MEDIAN_BARS)
    vix_slp_full = vix_slope(vix_full, VIX_SLOPE_BARS)
    vix = vix_full[-n_rth:]
    vix_med = vix_med_full[-n_rth:]
    vix_slp = vix_slp_full[-n_rth:]

    res = detect_vix_regime_dayside_core(
        closes, highs, lows, vwap, times, vix, vix_med, vix_slp,
        low_margin=DEFAULT_LOW_MARGIN, slope_rule=DEFAULT_SLOPE_RULE,
    )
    if res is None:
        return None

    # The research detector returns ONE entry/day at the first favorable morning bar. For the
    # live wrapper to act on it (entry fills next bar) the qualifying bar must be the CURRENT
    # (just-closed) bar; an earlier qualifying bar means we'd have fired then. Guard so a
    # mid-session backfill never emits a stale entry. No look-ahead either way.
    last_close = float(closes[-1])
    if not np.isclose(res.entry, last_close):
        return None

    detector._fired_today = True
    entry = res.entry
    stop = res.stop_level

    if res.direction == "long":
        tp1_price = round(entry + _TP1_SPY_MOVE, 2)
        runner_price = round(entry + _RUNNER_SPY_MOVE, 2)
        instrument = "calls"
        side_word = "above"
        stop_word = "12-bar swing LOW"
    else:
        tp1_price = round(entry - _TP1_SPY_MOVE, 2)
        runner_price = round(entry - _RUNNER_SPY_MOVE, 2)
        instrument = "puts"
        side_word = "below"
        stop_word = "12-bar swing HIGH"

    vix_now = getattr(ctx, "vix_now", None) or res.vix_at_bar
    reason = (
        f"VIX_REGIME_DAYSIDE ({res.side}): first {TREND_BARS} RTH bars all closed "
        f"{side_word} session VWAP (clean morning day-trend), and the VIX regime is "
        f"FAVORABLE as-of this bar ({bar_time.strftime('%H:%M')} ET, in 09:35-11:30) -> "
        f"VIX={res.vix_at_bar:.2f} <= (trailing_median {res.vix_median_at_bar:.2f} - "
        f"{DEFAULT_LOW_MARGIN}) AND vix_slope5={res.vix_slope_at_bar:.2f} <= 0 (LOW + "
        f"not-rising) -> take the day-trend side, buy {instrument}. Entry={entry:.2f} "
        f"Stop(chart={stop_word})={stop:.2f}. CHART-STOP PRIMARY (L51/L55). Edge #4: "
        f"real-fills clears all 8 gates @ ATM (OOS +$79.49/tr, drop-top5 +$25.91, "
        f"chart-stop-only OOS+ = no truncation). Safe-2 ships ATM (C29). DORMANT until "
        f"params.j_vix_dayside_enabled."
    )

    return WatcherSignal(
        watcher_name="vix_regime_dayside_watcher",
        setup_name="VIX_REGIME_DAYSIDE",
        direction=res.direction,
        entry_price=float(entry),
        stop_price=float(stop),
        tp1_price=float(tp1_price),
        runner_price=float(runner_price),
        confidence="medium",   # data-discovered, not yet live-confirmed (OP-21)
        reason=reason,
        triggers_fired=[
            "VWAP_DAY_TREND_ESTABLISHED",
            "VIX_REGIME_FAVORABLE_LOW_NOT_RISING",
        ],
        metadata={
            "promotion_status": "WATCH_ONLY",
            "trend_bars": TREND_BARS,
            "entry_window_et": [ENTRY_GATE[0].strftime("%H:%M"), ENTRY_GATE[1].strftime("%H:%M")],
            "vix_at_bar": round(res.vix_at_bar, 4),
            "vix_median_at_bar": round(res.vix_median_at_bar, 4),
            "vix_slope5_at_bar": (round(res.vix_slope_at_bar, 4)
                                  if not math.isnan(res.vix_slope_at_bar) else None),
            "low_margin": DEFAULT_LOW_MARGIN,
            "slope_rule": DEFAULT_SLOPE_RULE,
            "vix_median_bars": VIX_MEDIAN_BARS,
            "vix_slope_bars": VIX_SLOPE_BARS,
            "chart_stop": round(stop, 2),
            "stop_basis": "12bar_swing",
            "premium_stop_pct": DEFAULT_PREMIUM_STOP_PCT,         # -0.08 (validated ATM cell)
            "strike_offset": DEFAULT_STRIKE_OFFSET,               # 0 = ATM (Safe-2 ship cell)
            "default_qty": 3,
            "tp1_premium_pct": DEFAULT_TP1_PREMIUM_PCT,
            "tp1_qty_fraction": DEFAULT_TP1_QTY_FRACTION,
            "runner_target_pct": DEFAULT_RUNNER_TARGET_PCT,
            "vix_now": vix_now,
            "validation": "analysis/recommendations/b5-vix-regime-dayside.json",
            "promotion_gate": (
                "OP-21: offline real-fills clears ALL 8 anti-cherry-pick gates @ ATM "
                "(low_margin=0.25, slope_rule=not_rising: OOS +$79.49/tr, drop-top5 +$25.91, "
                "chart-stop-only OOS+ = no truncation, posQ 5/6, beats coin-flip null). ITM-2 "
                "at the same cell is a truncation-artifact (NOT shipped). C29: Safe-2 ships "
                "ATM. Live gate: 3 live J confirmations + Rule 9 before any live order path. "
                "Wiring DORMANT on params.j_vix_dayside_enabled (default FALSE)."
            ),
        },
    )


# ── Self-test ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys as _sys

    def _ts(h, m):
        return dt.datetime(2026, 1, 7, h, m)

    def _bar(h, m, o, hi, lo, c, v=5000):
        return dict(timestamp_et=_ts(h, m), open=o, high=hi, low=lo, close=c, volume=v)

    def _mk_ctx(rows, vix_series, *, vix_now=15.0):
        df = pd.DataFrame(rows)
        cur = df.iloc[-1]
        ctx = BarContext(
            bar_idx=len(df) - 1, timestamp_et=cur["timestamp_et"], bar=cur,
            prior_bars=df, ribbon_now=None, ribbon_history=[], vix_now=vix_now,
            vix_prior=vix_now, vol_baseline_20=1000.0, range_baseline_20=0.5,
            levels_active=[], multi_day_levels=[], htf_15m_stack=None,
        )
        object.__setattr__(ctx, "vix_intraday", vix_series)
        return ctx

    results: list[tuple[str, bool]] = []

    # Build an above-VWAP trend day where the entry bar (4th) is inside the window with a
    # favorable VIX regime (low + falling). Provide a long flat-then-declining VIX series so
    # trailing-median is well above the current level and slope5 <= 0.
    rows = [
        _bar(9, 30, 600.0, 600.6, 599.9, 600.5),
        _bar(9, 35, 600.5, 601.2, 600.4, 601.1),
        _bar(9, 40, 601.1, 601.8, 601.0, 601.7),   # side = C (last trend bar)
        _bar(9, 45, 601.7, 602.4, 601.6, 602.3),   # candidate entry bar (in 09:35-11:30)
    ]
    # VIX series aligned to the 4 RTH bars but we need >= VIX_MEDIAN_BARS prior for a median.
    # Prepend a high-VIX history (median high) then a low current value, declining slope.
    vix_hist = [22.0] * 80 + [16.0, 15.8, 15.6, 15.4]   # last 4 align to the 4 RTH bars
    sig = None
    _reset_day("none")
    for k in range(len(rows)):
        s = detect_vix_regime_dayside_setup(_mk_ctx(rows[: k + 1], vix_hist[: 80 + k + 1]))
        if s is not None:
            sig = s
            break
    fired = sig is not None and sig.direction == "long"
    results.append(("A: above-VWAP trend + favorable VIX (low+falling) SHOULD fire long", fired))
    if sig:
        print(f"[A] FIRED {sig.direction} stop={sig.stop_price} vix={sig.metadata['vix_at_bar']}")
    else:
        print("[A] no signal")

    # B — SHOULD NOT FIRE: VIX rising (slope5 > 0) even though level is low.
    vix_rising = [14.0] * 80 + [15.0, 15.5, 16.0, 16.5]   # rising slope
    sig_b = None
    _reset_day("none")
    for k in range(len(rows)):
        s = detect_vix_regime_dayside_setup(_mk_ctx(rows[: k + 1], vix_rising[: 80 + k + 1]))
        if s is not None:
            sig_b = s
            break
    results.append(("B: VIX rising (slope>0) should NOT fire", sig_b is None))
    print(f"[B] {'no signal (correct)' if sig_b is None else 'FIRED (wrong!)'}")

    # C — SHOULD NOT FIRE: VIX not low (at/above trailing median).
    vix_high = [15.0] * 80 + [15.0, 15.0, 15.0, 15.0]     # level == median, margin not met
    sig_c = None
    _reset_day("none")
    for k in range(len(rows)):
        s = detect_vix_regime_dayside_setup(_mk_ctx(rows[: k + 1], vix_high[: 80 + k + 1]))
        if s is not None:
            sig_c = s
            break
    results.append(("C: VIX not low (no margin below median) should NOT fire", sig_c is None))
    print(f"[C] {'no signal (correct)' if sig_c is None else 'FIRED (wrong!)'}")

    # D — SHOULD NOT FIRE: no intraday VIX series (regime unconfirmed -> SKIP).
    sig_d = None
    _reset_day("none")
    for k in range(len(rows)):
        df = pd.DataFrame(rows[: k + 1])
        cur = df.iloc[-1]
        ctx = BarContext(
            bar_idx=len(df) - 1, timestamp_et=cur["timestamp_et"], bar=cur,
            prior_bars=df, ribbon_now=None, ribbon_history=[], vix_now=15.0,
            vix_prior=15.0, vol_baseline_20=1000.0, range_baseline_20=0.5,
            levels_active=[], multi_day_levels=[], htf_15m_stack=None,
        )
        s = detect_vix_regime_dayside_setup(ctx)
        if s is not None:
            sig_d = s
            break
    results.append(("D: no intraday VIX series -> regime unconfirmed -> SKIP", sig_d is None))
    print(f"[D] {'no signal (correct)' if sig_d is None else 'FIRED (wrong!)'}")

    # E — core: mixed open (no clean one-sided VWAP trend) should NOT fire.
    closes_e = np.array([600.4, 599.2, 599.8, 600.8])
    highs_e = np.array([600.6, 600.6, 599.9, 600.9])
    lows_e = np.array([599.4, 599.0, 599.0, 599.7])
    vwap_e = np.array([600.0, 599.8, 599.8, 600.0])
    times_e = [dt.time(9, 30), dt.time(9, 35), dt.time(9, 40), dt.time(9, 45)]
    vix_e = np.array([22.0] * 4)
    vmed_e = np.array([24.0] * 4)
    vslp_e = np.array([-1.0] * 4)
    core_e = detect_vix_regime_dayside_core(closes_e, highs_e, lows_e, vwap_e, times_e,
                                            vix_e, vmed_e, vslp_e)
    results.append(("E: core mixed open should NOT fire", core_e is None))
    print(f"[E] core={core_e}")

    print("\n=== VIX_REGIME_DAYSIDE self-test ===")
    all_pass = True
    for name, ok in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
        all_pass = all_pass and ok
    print(f"=== {'ALL PASS' if all_pass else 'SOME FAILED'} ===")
    _sys.exit(0 if all_pass else 1)
