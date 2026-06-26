"""VWAP_RECLAIM_FAILED_BREAK watcher (J_VWAP_RECLAIM_FB) — edge #2, DORMANT live port.

The streaming ``BarContext`` port of the VALIDATED structural detector
``detect_signals`` in ``backtest/autoresearch/_sub_struct_vwap_reclaim_failed_break.py``
(the "failed counter-trend move" edge). Ported BYTE-FOR-BYTE — the per-bar phase
machine, the trend-side definition, the excursion-extreme chart stop, the <=10:30 ET
cutoff and the one-causal-entry/day rule are identical to the research detector, so the
live watcher and the autoresearch sim make the SAME decision (no detector drift, C14).

THESIS (the selection-campaign lesson, C4/L122/L154/L166):
  ADDITIVE confluence is DEAD on 0DTE; the proven edges are STRUCTURAL (one causal
  with-trend entry/day). This is the SUBTRACTIVE/STRUCTURAL-mimic sibling of
  vwap_continuation: it requires a COMPLETED counter-trend VWAP break that THEN FAILS
  and RECLAIMS with-trend — the "failed counter-trend move" shape.

PATTERN (one entry per day, causal, fill next bar open — no look-ahead, L166).
BYTE-FOR-BYTE the same decision as ``_sub_struct_vwap_reclaim_failed_break.detect_signals``:

  1. TREND SIDE from the first TREND_BARS (3) RTH bars: all CLOSE on the same side of
     the *as-of* session VWAP -> that is the day's side (C if above / P if below).
     IDENTICAL to the validated vwap_continuation trend definition (no drift).
  2. COUNTER-TREND BREAK: after the trend bars, the FIRST bar (<= ENTRY_CUTOFF) whose
     CLOSE is on the WRONG side of VWAP begins the "counter-trend move" (broke=True).
     Its excursion extreme starts at that bar (calls: its LOW; puts: its HIGH).
  3. FAILS + RECLAIMS: a later bar (<= ENTRY_CUTOFF) whose CLOSE crosses BACK across
     VWAP in the ORIGINAL trend direction -> the counter-trend move failed and price
     reclaimed VWAP with-trend. THAT reclaim bar is the entry (side = morning trend).
     During the failed break we track the deepest excursion extreme (calls: min low;
     puts: max high) — the chart stop = that extreme (the structural invalidation: if
     price takes out the failed-break extreme, the read was wrong).

  DISTINCT from vwap_continuation: vwap_cont enters the FIRST with-trend continuation
  (breakout/shallow-dip) with NO requirement that price ever crossed VWAP against the
  trend. vwap_reclaim_failed_break REQUIRES a completed counter-trend VWAP break THEN a
  with-trend reclaim.

VALIDATION (real OPRA fills, C1 — clears ALL 8 anti-cherry-pick gates @ ITM-2):
  ITM-2 (strike_offset=-2, batch-2 cell) is the PRIMARY survivor (OOS +$72/tr, posQ 5/6,
  beats coin-flip + same-day null, no-truncation). OTM-2 (strike_offset=+2) FAILS (C29:
  OTM theta/delta eats the alpha). The RESCUE sweep
  (``backtest/autoresearch/_rescue_otm2.py``) finds the Safe-2-tradeable cell. Scorecards:
  ``analysis/recommendations/SUBTRACTIVE-SELECTION-SCORECARD.md`` +
  ``RECLAIM-RESCUE-SCORECARD.md`` (+ the raw ``sub-struct_vwap_reclaim_failed_break.json``
  / ``rescue-otm2.json``).

SHIP CONFIG (per dual-account C29 — gates do not transfer across strike tiers):
  SAFE-2 = ATM (strike_offset=0, tp1_premium_pct=0.30, level_stop_buffer_dollars=0.25,
           premium_stop_pct=-0.08, qty>=3).
  BOLD/aggressive = ITM-2 (strike_offset=-2, the validated batch-2 cell).
  side default 'put' (OP-16 conservative; 'both' is J's call).

DORMANT: this module ONLY observes + logs (WATCH_ONLY, OP-21). The heartbeat order path
  is gated on ``params.j_vwap_reclaim_fb_enabled`` (default FALSE = inert = zero behavior
  change). J flips the flag; J holds REVOKE (Rule 9 / OP-25). Live gate: 3 live J
  confirmations before any live order path.

CAUSALITY: session VWAP at bar i uses only that session's bars[0..i]; the trend check,
  the break detection, the excursion-extreme tracking and the reclaim are all read
  at-or-before the current (trigger) bar's close; entry fills the NEXT bar (heartbeat/sim
  convention, L166).

WARMUP-SAFE: needs >= TREND_BARS+1 RTH bars before it can begin scanning; before that,
  None. Per-day state (trend side, broke flag, excursion extreme, fired flag) resets on
  date change.

Reuse / template:
  backtest/lib/watchers/vwap_continuation_watcher.py (ctx-only session-VWAP shape)
  backtest/autoresearch/_sub_struct_vwap_reclaim_failed_break.py#detect_signals (logic)
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from . import WatcherSignal
from ..filters import BarContext


# ── Detection parameters (IDENTICAL to _sub_struct_vwap_reclaim_failed_break /
#    _edgehunt_vwap_continuation — no silent drift, C14) ─────────────────────────
TREND_BARS: int = 3                       # first 15 min set the side
ENTRY_CUTOFF: dt.time = dt.time(10, 30)   # morning edge band (<= 10:30 ET)

# RTH session window (ET). Mirrors discovery's session bounds.
RTH_OPEN: dt.time = dt.time(9, 30)
RTH_CLOSE: dt.time = dt.time(16, 0)

# ── Exit / sizing knobs — ADVISORY FALLBACK ONLY (LOW-2). These are the Safe-2 ATM
#    SHIP-CELL values, surfaced on WatcherSignal.metadata so an observer sees the
#    validated cell. They are NOT the live authority: the heartbeat / sim MUST source
#    the stop/tp1/buffer from the ISOLATED params keys
#    (j_vwap_reclaim_fb_premium_stop_pct / _tp1_pct / _stop_buffer) — NOT from these
#    module constants and NOT from the GLOBAL premium_stop_pct/tp1_premium_pct (which are
#    the -0.50 catastrophe cap / 0.50 TP1, the WRONG values for this cell). filters.py
#    exposes vwap_reclaim_failed_break_{premium_stop_pct,tp1_pct,stop_buffer}(params) to
#    read the isolated keys (gamma-sync single source of truth). These constants are only
#    the fallback default used when no params dict is supplied (e.g. a bare observation).
#    Per dual-account C29 the Bold ITM-2 cell overrides strike_offset=-2 + tp1=0.75 at the
#    aggressive heartbeat/params. ─────────────────────────────────────────────────────
DEFAULT_STRIKE_OFFSET: int = 0            # ATM (Safe-2 ship cell); Bold = -2 (ITM-2)
DEFAULT_TP1_PREMIUM_PCT: float = 0.30     # Safe-2 ship cell (== params j_vwap_reclaim_fb_tp1_pct)
DEFAULT_LEVEL_STOP_BUFFER_DOLLARS: float = 0.25  # Safe-2 cell (== params j_vwap_reclaim_fb_stop_buffer)
DEFAULT_PREMIUM_STOP_PCT: float = -0.08   # Safe-2 cell (== params j_vwap_reclaim_fb_premium_stop_pct)
DEFAULT_TP1_QTY_FRACTION: float = 0.50    # v15 prod (L108)
DEFAULT_RUNNER_TARGET_PCT: float = 2.5    # v15 prod (L109)

# Spot-price target geometry for the WatcherSignal (advisory; the real-fills exit stack
# on the sim/heartbeat side uses chart-stop + ribbon-flip + chandelier + time).
_TP1_SPY_MOVE: float = 0.70
_RUNNER_SPY_MOVE: float = 2.50


@dataclass(frozen=True)
class VwapReclaimResult:
    """Pure detector output (no ctx) — directly unit-testable. Mirrors the discovery
    Signal (side, stop_level, trigger note) for the reclaim bar the wrapper builds from."""
    direction: str          # "long" (calls) | "short" (puts)
    side: str               # "C" | "P"
    vwap_at_bar: float
    entry: float
    stop_level: float       # failed-break excursion extreme (the chart stop)


def trend_side(closes, vwap, n: int = TREND_BARS) -> Optional[str]:
    """The day's side from the first ``n`` RTH bars: all closes one side of as-of VWAP.

    BYTE-FOR-BYTE the same as ``_sub_struct_vwap_reclaim_failed_break._trend_side``
    (and ``j_daily_pattern_ratify._trend_side``): all closes above their as-of VWAP ->
    "C"; all below -> "P"; mixed (or warmup) -> None.
    """
    head_c = np.asarray(closes[:n], dtype=float)
    head_v = np.asarray(vwap[:n], dtype=float)
    if len(head_c) < n:
        return None
    if np.all(head_c > head_v):
        return "C"
    if np.all(head_c < head_v):
        return "P"
    return None


def detect_vwap_reclaim_failed_break_core(
    closes,
    highs,
    lows,
    vwap,
    times,
    *,
    entry_cutoff: dt.time = ENTRY_CUTOFF,
) -> Optional[VwapReclaimResult]:
    """Pure VWAP_RECLAIM_FAILED_BREAK decision over a session's as-of arrays.

    ``closes/highs/lows/vwap`` are the session's RTH arrays (chronological, as-of
    cumulative session VWAP); ``times`` is the matching per-bar ``datetime.time`` array.
    Reproduces the per-day body of ``_sub_struct_vwap_reclaim_failed_break.detect_signals``
    EXACTLY (trend side from the head -> first counter-trend VWAP-break close -> deepest
    excursion extreme -> first with-trend reclaim close <= cutoff). Returns the reclaim
    bar's signal, or None if the sequence never completes inside the morning window.

    The wrapper drives the SAME phase machine incrementally per bar (the streaming live
    case); this batch core is the parity surface for the test and the offline replay.
    """
    side = trend_side(closes, vwap, TREND_BARS)
    if side is None:
        return None
    n = len(closes)
    if n < TREND_BARS + 1:
        return None

    broke = False                          # has the counter-trend VWAP break happened yet?
    excursion_ext: Optional[float] = None  # deepest extreme during the failed break (the stop)
    for j in range(TREND_BARS, n):
        if times[j] > entry_cutoff:
            break
        v = float(vwap[j])
        if v <= 0:
            continue
        c = float(closes[j])
        if side == "C":
            # Phase 2: counter-trend break = close BELOW VWAP (against bullish trend)
            if not broke:
                if c < v:
                    broke = True
                    excursion_ext = float(lows[j])
                continue
            # During the failed break, track the deepest LOW (the level that must hold)
            excursion_ext = (min(excursion_ext, float(lows[j]))
                             if excursion_ext is not None else float(lows[j]))
            # Phase 3: reclaim = close BACK ABOVE VWAP in the trend direction -> entry
            if c > v:
                return VwapReclaimResult(
                    direction="long", side="C", vwap_at_bar=v,
                    entry=c, stop_level=float(excursion_ext),
                )
        else:
            # Phase 2: counter-trend break = close ABOVE VWAP (against bearish trend)
            if not broke:
                if c > v:
                    broke = True
                    excursion_ext = float(highs[j])
                continue
            excursion_ext = (max(excursion_ext, float(highs[j]))
                             if excursion_ext is not None else float(highs[j]))
            # Phase 3: reclaim = close BACK BELOW VWAP -> entry
            if c < v:
                return VwapReclaimResult(
                    direction="short", side="P", vwap_at_bar=v,
                    entry=c, stop_level=float(excursion_ext),
                )
    return None


# ── Per-INSTANCE day state (MED-1 fix) ────────────────────────────────────────
# PREVIOUSLY this was module-level (_state_date/_fired_today) shared across ALL
# callers. That corrupts the one-entry/day guard when two callers interleave on
# DIFFERENT days — e.g. the backtest engine (filters.py#detect_vwap_reclaim_
# failed_break) is mid-replay of day A when the live watcher runner processes
# day B's first bar: day B's reset clobbers day A's _fired_today, so day A can
# double-fire (or a stale True suppresses day A's legitimate entry). Per C9
# (update ALL state consumers) and C14 (no drift), the per-day guard now lives on
# a per-INSTANCE object. Each caller that wants isolation constructs its own
# detector; the module-level functions delegate to a default singleton so the
# registry call site and the existing tests are unchanged.
class VwapReclaimFailedBreakDetector:
    """Stateful streaming wrapper for VWAP_RECLAIM_FAILED_BREAK with PER-INSTANCE
    one-entry/day state. Two distinct instances never corrupt each other's guard.

    The detection itself is pure (``detect_vwap_reclaim_failed_break_core``); the
    only state is the per-day ``_state_date``/``_fired_today`` pair used to enforce
    one causal entry per day. ``detect(ctx)`` is the streaming entry point."""

    def __init__(self) -> None:
        self._state_date: Optional[str] = None
        self._fired_today: bool = False

    def reset_day(self, day_str: str) -> None:
        self._state_date = day_str
        self._fired_today = False

    def detect(self, ctx: BarContext) -> Optional[WatcherSignal]:
        return _detect_impl(ctx, self)


# Default singleton — the live watcher runner + the gamma-sync filters delegator
# both reach this one through the module-level function. They run on the SAME
# (today's) day in production, so they share correctly; a caller needing true
# isolation (e.g. a backtest harness replaying historical days alongside a live
# pass) constructs its OWN VwapReclaimFailedBreakDetector instance.
_default_detector = VwapReclaimFailedBreakDetector()


def _reset_day(day_str: str) -> None:
    """Reset the DEFAULT detector's per-day guard (back-compat shim for tests)."""
    _default_detector.reset_day(day_str)


def _session_rth_vwap(prior_bars: pd.DataFrame, today: dt.date) -> Optional[pd.DataFrame]:
    """Today's RTH bars (chronological) with an *as-of* cumulative session VWAP column.

    Causal: VWAP at row i uses only rows[0..i] of the session. ``prior_bars`` is the
    full history including the current (trigger) bar at [-1]. BYTE-FOR-BYTE the same
    VWAP as ``vwap_continuation_watcher._session_rth_vwap`` / ``session_vwap_asof``
    (typical price (H+L+C)/3 * volume, cumulative).
    """
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


def detect_vwap_reclaim_failed_break_setup(ctx: BarContext) -> Optional[WatcherSignal]:
    """Detect VWAP_RECLAIM_FAILED_BREAK (J_VWAP_RECLAIM_FB) on the current bar (WATCH-ONLY).

    direction="long" (buy calls) on an above-VWAP morning trend whose counter-trend VWAP
    break FAILS and RECLAIMS with-trend; direction="short" (buy puts) on the below-VWAP
    mirror.

    Fires at most ONCE per day, only inside the morning window (bar CLOSE time <=
    ENTRY_CUTOFF) after the TREND_BARS warmup, when the as-of session arrays complete the
    failed-break -> reclaim sequence on (or by) the current bar. Returns None on any gate
    miss. Pure read of ctx; no I/O, no order placement.

    Thin shim over the DEFAULT detector singleton (MED-1): per-day state is held on the
    instance, not the module, so interleaved callers don't corrupt each other's guard.
    """
    return _default_detector.detect(ctx)


def _detect_impl(
    ctx: BarContext, detector: "VwapReclaimFailedBreakDetector"
) -> Optional[WatcherSignal]:
    """Streaming detection body driven against a specific detector's per-day state."""
    bar_time = ctx.timestamp_et.time()
    today = ctx.timestamp_et.date()
    day_str = today.isoformat()

    # New day -> reset this detector's per-day state.
    if detector._state_date != day_str:
        detector.reset_day(day_str)

    # Only operate inside RTH.
    if bar_time < RTH_OPEN or bar_time >= RTH_CLOSE:
        return None

    # Already took today's one entry.
    if detector._fired_today:
        return None

    # Past the morning cutoff: the discovery loop `break`s the per-day scan. LOW-1:
    # ctx.timestamp_et is the bar's CLOSE time (the heartbeat/sim convention — the bar
    # is acted on once closed), so the <= ENTRY_CUTOFF (10:30) test here is already the
    # closed-bar boundary that matches the research detector's times[j] (rth bar close).
    if bar_time > ENTRY_CUTOFF:
        return None

    rth = _session_rth_vwap(ctx.prior_bars, today)
    if rth is None or len(rth) < TREND_BARS + 1:
        return None

    closes = rth["close"].values
    highs = rth["high"].values
    lows = rth["low"].values
    vwap = rth["_vwap"].values
    times = [t.time() for t in pd.to_datetime(rth["timestamp_et"]).tolist()]

    res = detect_vwap_reclaim_failed_break_core(closes, highs, lows, vwap, times)
    if res is None:
        return None

    # The discovery detector returns ONE entry/day at the reclaim bar. The reclaim must be
    # the CURRENT (just-closed) bar for the live wrapper to act on it (entry fills next
    # bar). If the completed reclaim is an earlier bar, the wrapper already fired that day
    # (state) — but in the streaming case prior bars never completed the sequence, so the
    # batch core returning a reclaim at the last bar == this bar is the live trigger.
    last_close = float(closes[-1])
    if not np.isclose(res.entry, last_close):
        # The completed reclaim sits on an earlier bar than the current one. In the
        # streaming case this should not happen (we'd have fired then); guard anyway so a
        # mid-session backfill never emits a stale entry. No look-ahead either way.
        return None

    # ── Entry — emit signal, mark fired (PER-INSTANCE, MED-1) ─────────────────
    detector._fired_today = True
    entry = res.entry
    v = res.vwap_at_bar
    stop = res.stop_level

    if res.direction == "long":
        tp1_price = round(entry + _TP1_SPY_MOVE, 2)
        runner_price = round(entry + _RUNNER_SPY_MOVE, 2)
        instrument = "calls"
        side_word = "above"
        stop_word = "failed-break LOW"
    else:
        tp1_price = round(entry - _TP1_SPY_MOVE, 2)
        runner_price = round(entry - _RUNNER_SPY_MOVE, 2)
        instrument = "puts"
        side_word = "below"
        stop_word = "failed-break HIGH"

    vix_now = getattr(ctx, "vix_now", None) or 0.0
    reason = (
        f"VWAP_RECLAIM_FAILED_BREAK ({res.side}): first {TREND_BARS} RTH bars all closed "
        f"{side_word} session VWAP (clean morning trend), then price broke VWAP "
        f"COUNTER-trend, FAILED, and RECLAIMED {side_word} VWAP ({v:.2f}) on this bar "
        f"({bar_time.strftime('%H:%M')} ET, <= {ENTRY_CUTOFF.strftime('%H:%M')}) -> buy "
        f"{instrument}. Entry={entry:.2f} Stop(chart={stop_word} = the structural "
        f"invalidation)={stop:.2f}. The 'failed counter-trend move' shape. CHART-STOP "
        f"PRIMARY (L51/L55). VIX={vix_now:.1f}. Edge #2: real-fills clears all 8 gates @ "
        f"ITM-2 (OOS +$72/tr, posQ 5/6); Safe-2 ships ATM, Bold ships ITM-2 (C29). "
        f"DORMANT until params.j_vwap_reclaim_fb_enabled."
    )

    return WatcherSignal(
        watcher_name="vwap_reclaim_failed_break_watcher",
        setup_name="VWAP_RECLAIM_FAILED_BREAK",
        direction=res.direction,
        entry_price=float(entry),
        stop_price=float(stop),
        tp1_price=float(tp1_price),
        runner_price=float(runner_price),
        confidence="medium",   # data-discovered, not yet live-confirmed (OP-21)
        reason=reason,
        triggers_fired=[
            "VWAP_TREND_ESTABLISHED",
            "VWAP_COUNTER_TREND_BREAK_FAILED",
            "VWAP_WITH_TREND_RECLAIM",
        ],
        metadata={
            "promotion_status": "WATCH_ONLY",
            "vwap_at_bar": round(v, 4),
            "trend_bars": TREND_BARS,
            "entry_cutoff_et": ENTRY_CUTOFF.strftime("%H:%M"),
            "chart_stop": round(stop, 2),
            "stop_basis": "failed_break_excursion_extreme",
            "premium_stop_pct": DEFAULT_PREMIUM_STOP_PCT,         # -0.08 (Safe-2 ship cell)
            "strike_offset": DEFAULT_STRIKE_OFFSET,               # 0 = ATM (Safe-2); Bold = -2
            "default_qty": 3,
            "tp1_premium_pct": DEFAULT_TP1_PREMIUM_PCT,
            "level_stop_buffer_dollars": DEFAULT_LEVEL_STOP_BUFFER_DOLLARS,
            "tp1_qty_fraction": DEFAULT_TP1_QTY_FRACTION,
            "runner_target_pct": DEFAULT_RUNNER_TARGET_PCT,
            "vix_now": vix_now,
            "validation": (
                "analysis/recommendations/sub-struct_vwap_reclaim_failed_break.json + "
                "rescue-otm2.json (scorecards: SUBTRACTIVE-SELECTION-SCORECARD.md + "
                "RECLAIM-RESCUE-SCORECARD.md)"
            ),
            "promotion_gate": (
                "OP-21: offline real-fills clears ALL 8 anti-cherry-pick gates @ ITM-2 "
                "(OOS+, posQ 5/6, beats coin-flip + same-day null, no-truncation). C29: "
                "OTM-2 fails (theta/delta) — Safe-2 ships ATM, Bold ships ITM-2. Live "
                "gate: 3 live J confirmations + Rule 9 before any live order path. Wiring "
                "DORMANT on params.j_vwap_reclaim_fb_enabled (default FALSE)."
            ),
        },
    )


# ── Self-test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys as _sys

    def _mk_ctx(rows, *, vix=17.0):
        df = pd.DataFrame(rows)
        cur = df.iloc[-1]
        return BarContext(
            bar_idx=len(df) - 1, timestamp_et=cur["timestamp_et"], bar=cur,
            prior_bars=df, ribbon_now=None, ribbon_history=[], vix_now=vix,
            vix_prior=vix, vol_baseline_20=1000.0, range_baseline_20=0.5,
            levels_active=[], multi_day_levels=[], htf_15m_stack=None,
        )

    def _ts(h, m):
        return dt.datetime(2026, 1, 7, h, m)

    def _bar(h, m, o, hi, lo, c, v=5000):
        return dict(timestamp_et=_ts(h, m), open=o, high=hi, low=lo, close=c, volume=v)

    results: list[tuple[str, bool]] = []

    # ── A — SHOULD FIRE long: above-VWAP trend, dip-close-below (failed break),
    #        then reclaim-close-above. ─────────────────────────────────────────
    _reset_day("none")
    rows_a = [
        _bar(9, 30, 600.0, 600.6, 599.9, 600.5),   # trend bar 1 (close > VWAP)
        _bar(9, 35, 600.5, 601.2, 600.4, 601.1),   # trend bar 2
        _bar(9, 40, 601.1, 601.8, 601.0, 601.7),   # trend bar 3 -> side = C
        _bar(9, 45, 601.7, 601.8, 600.0, 600.2),   # counter-trend break (close < VWAP), low=600.0
    ]
    # drive bar-by-bar; the reclaim is the final bar
    sig_a = None
    _reset_day("none")
    for k in range(len(rows_a)):
        sig_a = detect_vwap_reclaim_failed_break_setup(_mk_ctx(rows_a[: k + 1]))
    # add a reclaim bar that closes back above VWAP
    rows_a2 = rows_a + [_bar(9, 50, 600.2, 601.6, 600.1, 601.5)]   # close back above VWAP -> reclaim
    sig_a = None
    _reset_day("none")
    for k in range(len(rows_a2)):
        s = detect_vwap_reclaim_failed_break_setup(_mk_ctx(rows_a2[: k + 1]))
        if s is not None:
            sig_a = s
            break
    fired_a = sig_a is not None and sig_a.direction == "long"
    results.append(("A: above-VWAP trend + failed break + reclaim SHOULD fire long", fired_a))
    print(f"[A] {('FIRED ' + sig_a.direction + f' stop={sig_a.stop_price} entry={sig_a.entry_price}') if sig_a else 'no signal'}")

    # ── B — SHOULD FIRE short: below-VWAP trend, pop-close-above (failed break),
    #        then reclaim-close-below. ─────────────────────────────────────────
    rows_b = [
        _bar(9, 30, 600.0, 600.1, 599.4, 599.5),   # trend bar 1 (close < VWAP)
        _bar(9, 35, 599.5, 599.6, 598.8, 598.9),   # trend bar 2
        _bar(9, 40, 598.9, 599.0, 598.2, 598.3),   # trend bar 3 -> side = P
        _bar(9, 45, 598.3, 600.0, 598.2, 599.8),   # counter-trend break (close > VWAP), high=600.0
        _bar(9, 50, 599.8, 599.9, 598.0, 598.1),   # reclaim (close < VWAP)
    ]
    sig_b = None
    _reset_day("none")
    for k in range(len(rows_b)):
        s = detect_vwap_reclaim_failed_break_setup(_mk_ctx(rows_b[: k + 1]))
        if s is not None:
            sig_b = s
            break
    fired_b = sig_b is not None and sig_b.direction == "short"
    results.append(("B: below-VWAP trend + failed break + reclaim SHOULD fire short", fired_b))
    print(f"[B] {('FIRED ' + sig_b.direction + f' stop={sig_b.stop_price}') if sig_b else 'no signal'}")

    # ── C — SHOULD NOT FIRE: mixed open (no clean one-sided VWAP trend) ─────────
    rows_c = [
        _bar(9, 30, 600.0, 600.6, 599.4, 600.4),   # close above
        _bar(9, 35, 600.4, 600.6, 599.0, 599.2),   # close below -> mixed
        _bar(9, 40, 599.2, 599.9, 599.0, 599.8),
        _bar(9, 45, 599.8, 600.9, 599.7, 600.8),
        _bar(9, 50, 600.8, 601.5, 600.5, 601.4),
    ]
    sig_c = None
    _reset_day("none")
    for k in range(len(rows_c)):
        s = detect_vwap_reclaim_failed_break_setup(_mk_ctx(rows_c[: k + 1]))
        if s is not None:
            sig_c = s
            break
    results.append(("C: mixed open (no clean trend) should NOT fire", sig_c is None))
    print(f"[C] {'no signal (correct)' if sig_c is None else 'FIRED (wrong!)'}")

    # ── D — SHOULD NOT FIRE: a clean trend with NO counter-trend break (pure
    #        continuation = vwap_cont's job, not this detector's). ─────────────
    rows_d = [
        _bar(9, 30, 600.0, 600.6, 599.9, 600.5),
        _bar(9, 35, 600.5, 601.2, 600.4, 601.1),
        _bar(9, 40, 601.1, 601.8, 601.0, 601.7),
        _bar(9, 45, 601.7, 602.6, 601.6, 602.5),   # fresh high, never closed below VWAP
        _bar(9, 50, 602.5, 603.2, 602.4, 603.1),
    ]
    sig_d = None
    _reset_day("none")
    for k in range(len(rows_d)):
        s = detect_vwap_reclaim_failed_break_setup(_mk_ctx(rows_d[: k + 1]))
        if s is not None:
            sig_d = s
            break
    results.append(("D: no counter-trend break (pure continuation) should NOT fire", sig_d is None))
    print(f"[D] {'no signal (correct)' if sig_d is None else 'FIRED (wrong!)'}")

    # ── E — SHOULD NOT FIRE: reclaim happens AFTER 10:30 cutoff ─────────────────
    rows_e = [
        _bar(10, 15, 600.0, 600.6, 599.9, 600.5),
        _bar(10, 20, 600.5, 601.2, 600.4, 601.1),
        _bar(10, 25, 601.1, 601.8, 601.0, 601.7),  # side = C, last trend bar at 10:25
        _bar(10, 30, 601.7, 601.8, 600.0, 600.2),  # counter-trend break at 10:30 (<= cutoff)
        _bar(10, 35, 600.2, 601.6, 600.1, 601.5),  # reclaim at 10:35 > cutoff -> too late
    ]
    sig_e = None
    _reset_day("none")
    for k in range(len(rows_e)):
        s = detect_vwap_reclaim_failed_break_setup(_mk_ctx(rows_e[: k + 1]))
        if s is not None:
            sig_e = s
            break
    results.append(("E: reclaim past 10:30 cutoff should NOT fire", sig_e is None))
    print(f"[E] {'no signal (correct)' if sig_e is None else 'FIRED (wrong!)'}")

    # ── F — core: stop = the deepest excursion LOW during the failed break ──────
    closes_f = np.array([600.5, 601.1, 601.7, 600.2, 599.8, 601.5])
    highs_f = np.array([600.6, 601.2, 601.8, 601.8, 600.3, 601.6])
    lows_f = np.array([599.9, 601.0, 601.0, 600.0, 599.5, 600.1])  # deepest low during break = 599.5
    vwap_f = np.array([600.2, 600.6, 601.0, 601.0, 601.0, 601.0])
    times_f = [dt.time(9, 30 + 5 * i) for i in range(6)]
    core_f = detect_vwap_reclaim_failed_break_core(closes_f, highs_f, lows_f, vwap_f, times_f)
    f_ok = (core_f is not None and core_f.side == "C" and core_f.direction == "long"
            and abs(core_f.stop_level - 599.5) < 1e-9)
    results.append(("F: core long, stop = deepest failed-break low (599.5)", f_ok))
    print(f"[F] core={core_f}")

    print("\n=== VWAP_RECLAIM_FAILED_BREAK self-test ===")
    all_pass = True
    for name, ok in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
        all_pass = all_pass and ok
    print(f"=== {'ALL PASS' if all_pass else 'SOME FAILED'} ===")
    _sys.exit(0 if all_pass else 1)
