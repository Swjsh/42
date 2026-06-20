"""VWAP_CONTINUATION watcher (J_VWAP_CONT) — J's near-daily morning edge, LIVE port.

The streaming ``BarContext`` port of ``detect_j_vwap_continuation`` (the validated
detector in ``backtest/autoresearch/j_daily_pattern_ratify.py``), which translated J's
own dominant repeatable winning pattern — **VWAP-ALIGNED MORNING CONTINUATION**, mined
from his 313 real Webull winners (``webull_daily_pattern_miner.py``) — into a causal
SPY detector and ran the full OP-22 stack on real OPRA fills.

Scorecard: ``analysis/recommendations/j-daily-pattern-LIVE.json``
  Headline J_VWAP_CONT / ATM, chart-stop-only, real OPRA fills 2025-01..2026-06:
    n=153, exp +$38.3/trade, WR 76.5%, total +$5,860, fires 42.1% of days (2.11/wk =
    NEAR-DAILY), both sides + (C +$26.0/77.4% / P +$53.3/75.4%), drop-top5 +$24.45
    (broad), DSR PASS, OOS sign-stable (+$24.12/trade), q+ 4/6.
  VIX-GATED variant (J_VWAP_CONT_VIXGATE / ITM1) is the strongest single cell:
    n=152, exp +$50.5/trade, WR 77.6%, WF median +0.962, q+ 5/6 — the put-side
    VIX-character gate (C5) lifts the put book (+$53→+$57) and the recent-quarter drag.

OP-22 GATE TALLY (HONEST — this is a 6-of-7 NEAR-SURVIVOR, NOT a clean auto-ship):
  PASS: OOS-positive | WF-median≥0.70 (ITM1 + VIXGATE) | sub-window-stable (q≥60%) |
        DSR-not-FAIL | both-directions-positive | drop-top5-robust.
  FAIL: all-cuts-OOS-positive — the lone failing window is the most-recent OOS slice
        (2026-Q2: partial OPRA coverage + a put-side bear-chop patch). Not a structural
        break (same class as the shipped H4 VWAP-pullback). => ships DORMANT / flip-ready
        with the recent-quarter caveat, gated on ``params.j_vwap_cont_enabled`` (default
        FALSE = inert = zero behavior change). J flips it; J holds REVOKE (Rule 9 / OP-25).

────────────────────────────────────────────────────────────────────────────────
PATTERN (one entry per day, causal, fill next bar open — no look-ahead, L166).
BYTE-FOR-BYTE the same decision as ``detect_j_vwap_continuation``:

  1. TREND SIDE from the first TREND_BARS (3) RTH bars: all CLOSE on the same side of
     the *as-of* session VWAP -> that is the day's side (C if above / P if below).
  2. After the trend window, the FIRST MORNING bar (time <= ENTRY_CUTOFF, 10:30 ET)
     that CONTINUES in the trend direction while still closing on the trend side:
       breakout = a fresh in-trend session extreme (matches J's breakout-dominant
                  winners) AND close still on the trend side of VWAP;
       pullback = a shallow VWAP-ward dip then a with-trend close (low<=VWAP*(1+tol)
                  for calls / high>=VWAP*(1-tol) for puts) AND close on the trend side.
     trig = "breakout" else ("pullback" else None). One entry/day; cooldown = fired.
  3. VIX PUT-GATE (C5, optional via ``put_needs_rising_vix``): a put only fires when the
     as-of VIX 5-bar slope is >= 0. A real down-trend expands vol; falling VIX =
     bear-chop that stops out put-side continuation (mirrors J's own put-side bleed).
  4. STOP = structural session extreme against the trade as of the entry bar
     (calls: session min low to date; puts: session max high to date). CHART-STOP ONLY
     (premium stop disabled — live CHART-STOP-PRIMARY doctrine, L51/L55/C2).

CAUSALITY: session VWAP at bar i uses only that session's bars[0..i]; the trend check,
the continuation trigger, and the VIX slope are all read at-or-before the entry bar's
close; entry fills the NEXT bar (heartbeat/sim convention, L166). Verified by the
future-poison check in the ratify harness + the parity test
(``backtest/tests/test_vwap_continuation_watcher.py``).

WARMUP-SAFE: needs >= TREND_BARS+1 RTH bars before it can fire; before that, None.
Per-day state (trend side, fired flag, VIX history) resets on date change.

OP-21 promotion gate:
  Offline (real-fills, this scorecard): NEAR-SURVIVOR (6/7 OP-22; recent-Q soft). Ships
    WATCH_ONLY/dormant flag-gated wiring like gap-and-go + vwap-trend-pullback.
  Live gate: accumulate observations -> 3 live J confirmations -> Rule 9. This module
    ONLY observes + logs; order placement is the heartbeat's job once J flips the flag.

Reuse / template:
  backtest/lib/watchers/vwap_trend_pullback_watcher.py (ctx-only session-VWAP shape)
  backtest/autoresearch/j_daily_pattern_ratify.py#detect_j_vwap_continuation (logic)
  backtest/lib/watchers/gap_and_go_watcher.py (pure-core + ctx-wrapper structure)
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from . import WatcherSignal
from ..filters import BarContext


# ── Detection parameters (IDENTICAL to j_daily_pattern_ratify — no silent drift, C14) ─
TREND_BARS: int = 3                       # first 15 min set the side (J entered early)
ENTRY_CUTOFF: dt.time = dt.time(10, 30)   # J's morning edge band (<= 10:30 ET)
SHALLOW_DIP_TOL: float = 0.0010           # within 0.10% of VWAP = with-trend pullback tag
VIX_SLOPE_LOOKBACK: int = 5               # as-of 5-bar VIX slope for the put-gate (C5)

# Realized-vol FLOOR (GOAL 1, 2026-06-20) — DORMANT default-off instrumentation.
#   Skip the entry when the session's as-of realized vol is below this floor (the
#   "dead quiet-tape" signature C1 found bleeds). Default 0.0 = OFF = byte-for-byte
#   identical to prior behavior (the rvol is still LOGGED in metadata at every trigger
#   so live N can accrue toward the >=35 promotion bar). Verdict on the LIVE chart-stop
#   config is WATCH, NOT ship — see scorecard analysis/recommendations/vwap-cont-rvol-floor.json:
#   on chart-stop NO floor reaches 7/7 OP-22 (the 2026-Q2 recent-quarter OOS slice stays
#   negative at every threshold AND chart-stop rolling-WF median is structurally <0.70).
#   The floor IS clean on the -8% premium-stop config (7/7 + own-OOS generalizes) — but
#   the live watcher trades chart-stop, and exit knobs don't transfer (C29/L149). So this
#   is wired DORMANT only; J flips j_vwap_cont_realized_vol_floor_bps (and j_vwap_cont_enabled)
#   once live N>=35 confirms it holds on the live config.
DEFAULT_REALIZED_VOL_FLOOR_BPS: float = 0.0   # 0 = OFF (inert); C1 candidate value = 9.0

# RTH session window (ET). Mirrors discovery's session bounds.
RTH_OPEN: dt.time = dt.time(9, 30)
RTH_CLOSE: dt.time = dt.time(16, 0)

# ── Exit knobs (v15 stack; chart-stop ONLY per L51/L55/C2) ────────────────────
DEFAULT_PREMIUM_STOP_PCT: float = -0.99   # disabled — chart stop is the only exit gate
DEFAULT_TP1_PREMIUM_PCT: float = 0.30     # v15 TP1 fallback when no chart level hit
DEFAULT_TP1_QTY_FRACTION: float = 0.50    # v15 prod (L108)
DEFAULT_RUNNER_TARGET_PCT: float = 2.5    # v15 prod (L109)
DEFAULT_STRIKE_OFFSET: int = 0            # ATM (validated tier; ITM1 also PASS, stronger)

# Spot-price target geometry for the WatcherSignal (advisory; the real-fills exit stack
# on the sim/heartbeat side uses chart-stop + ribbon-flip + chandelier + time).
_TP1_SPY_MOVE: float = 0.70
_RUNNER_SPY_MOVE: float = 2.50


@dataclass(frozen=True)
class VwapContinuationResult:
    """Pure detector output (no ctx) — directly unit-testable. Mirrors the discovery
    Signal (side, stop_level, trigger note) for the bar the wrapper builds from."""
    direction: str          # "long" (calls) | "short" (puts)
    side: str               # "C" | "P"
    trigger: str            # "breakout" | "pullback"
    vwap_at_bar: float
    entry: float
    stop_level: float       # session extreme against the trade (chart stop)


def trend_side(closes, vwap, n: int = TREND_BARS) -> Optional[str]:
    """The day's side from the first ``n`` RTH bars: all closes one side of as-of VWAP.

    BYTE-FOR-BYTE the same as ``j_daily_pattern_ratify._trend_side``: all closes above
    their as-of VWAP -> "C"; all below -> "P"; mixed (or warmup) -> None.
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


def vix_slope(vix_series, look: int = VIX_SLOPE_LOOKBACK,
              fallback_1bar: Optional[float] = None) -> float:
    """As-of VIX slope = vix[-1] - vix[-1-look] over a chronological VIX history.

    Look-ahead-safe: only past-and-current VIX values. Mirrors
    ``j_daily_pattern_ratify._vix_slope`` (which reads ``vix[idx] - vix[idx-look]`` on
    the GLOBAL multi-day VIX series indexed at the entry bar).

    Cross-session-VIX parity note (C5/L166): the discovery slope spans 5 bars on the
    *continuous* VIX series, so it crosses the overnight boundary and is effectively
    ALWAYS active (``idx < look`` is essentially never true mid-day). The live
    ``BarContext`` exposes only ``vix_now`` / ``vix_prior`` per bar, so the wrapper
    rebuilds a *per-session* VIX history; in the first ``look`` morning bars that
    history is too short to span the window. To preserve the gate's INTENT (puts only
    when vol is not falling) from the first morning bar — matching the discovery's
    always-active behavior — pass ``fallback_1bar = vix_now - vix_prior``; the function
    uses that 1-bar direction until the session history is deep enough for the true
    5-bar slope. With no fallback supplied it returns 0.0 when the history is short
    (the literal discovery guard), which leaves the gate inactive — used by the pure
    unit test of the deep-history path.
    """
    arr = np.asarray(vix_series, dtype=float)
    if len(arr) <= look:
        return float(fallback_1bar) if fallback_1bar is not None else 0.0
    return float(arr[-1] - arr[-1 - look])


def realized_vol_bps(closes) -> float:
    """As-of session realized vol = stdev (ddof=1) of 5m close-to-close LOG returns, in bps.

    BYTE-FOR-BYTE the same definition as the validation harness
    (``autoresearch.vwap_cont_rvol_floor.realized_vol_bps`` and the shared
    ``j_regime_forward_validate._realized_vol_bps``): ``std(diff(log(closes)), ddof=1) * 1e4``.
    Causal — ``closes`` is the session's RTH closes from open through the current (trigger)
    bar, so it reads only bars[0..trigger]. Live-computable from the 5m closes the heartbeat
    already caches. Returns 0.0 on too-short history (< 3 closes -> < 2 returns).
    """
    c = np.asarray(closes, dtype=float)
    if c.size < 3:
        return 0.0
    rets = np.diff(np.log(c))
    if rets.size < 2:
        return 0.0
    return float(np.std(rets, ddof=1) * 1e4)


def detect_vwap_continuation_core(
    closes,
    highs,
    lows,
    vwap,
    j: int,
    *,
    breakout_only: bool = False,
    shallow_dip_tol: float = SHALLOW_DIP_TOL,
) -> Optional[VwapContinuationResult]:
    """Pure J_VWAP_CONT decision for the candidate entry bar ``j`` of a session.

    ``closes/highs/lows/vwap`` are the session's as-of arrays (RTH, chronological);
    ``vwap`` is the cumulative as-of session VWAP. ``j`` is the index of the trigger bar
    within those arrays (j >= TREND_BARS). Reproduces the per-bar body of
    ``detect_j_vwap_continuation`` EXACTLY (trend side from the head, then the first
    in-trend breakout-or-pullback bar; stop = session extreme against the trade):

      side == "C": prior_ext = max(highs[:j]); breakout = highs[j] >= prior_ext AND
                   closes[j] > v; dip = lows[j] <= v*(1+tol) AND closes[j] > v;
                   stop = min(lows[:j+1]).
      side == "P": prior_ext = min(lows[:j]); breakout = lows[j] <= prior_ext AND
                   closes[j] < v; dip = highs[j] >= v*(1-tol) AND closes[j] < v;
                   stop = max(highs[:j+1]).

    Returns None when there is no clean trend side, ``j`` is inside the trend window,
    VWAP is non-positive, or the bar is neither a breakout nor a (allowed) pullback.
    Does NOT apply the VIX put-gate or the time-cutoff — those are the wrapper/loop's
    job (the discovery loop applies the cutoff via ``break`` and the VIX gate via
    ``continue``); the core is the inner per-bar test so the parity test can drive it.
    """
    side = trend_side(closes, vwap, TREND_BARS)
    if side is None:
        return None
    if j < TREND_BARS or j >= len(closes):
        return None
    v = float(vwap[j])
    if v <= 0:
        return None

    cj = float(closes[j])
    hj = float(highs[j])
    lj = float(lows[j])

    if side == "C":
        prior_ext = float(np.max(highs[:j])) if j > 0 else hj
        breakout = hj >= prior_ext and cj > v
        dip = lj <= v * (1 + shallow_dip_tol) and cj > v
        stop = float(np.min(lows[: j + 1]))
        direction = "long"
    else:
        prior_ext = float(np.min(lows[:j])) if j > 0 else lj
        breakout = lj <= prior_ext and cj < v
        dip = hj >= v * (1 - shallow_dip_tol) and cj < v
        stop = float(np.max(highs[: j + 1]))
        direction = "short"

    trig = "breakout" if breakout else ("pullback" if dip else None)
    if breakout_only:
        trig = "breakout" if breakout else None
    if trig is None:
        return None

    return VwapContinuationResult(
        direction=direction, side=side, trigger=trig,
        vwap_at_bar=v, entry=cj, stop_level=stop,
    )


# ── Per-day module state (resets on date change) ──────────────────────────────
# Live + replay both call this once per bar in chronological order, so simple
# module-level day state is sufficient (matches the vwap_trend_pullback pattern).
_state_date: Optional[str] = None
_fired_today: bool = False
_vix_hist: list[float] = []          # chronological as-of VIX per RTH bar (this session)
_evaluated_bars: set[int] = set()    # RTH bar indices already VIX-appended (no double count)


def _reset_day(day_str: str) -> None:
    global _state_date, _fired_today, _vix_hist, _evaluated_bars
    _state_date = day_str
    _fired_today = False
    _vix_hist = []
    _evaluated_bars = set()


def _session_rth_vwap(prior_bars: pd.DataFrame, today: dt.date) -> Optional[pd.DataFrame]:
    """Today's RTH bars (chronological) with an *as-of* cumulative session VWAP column.

    Causal: VWAP at row i uses only rows[0..i] of the session. ``prior_bars`` is the
    full history including the current (trigger) bar at [-1]. Mirrors
    ``vwap_trend_pullback_watcher._session_rth_vwap`` and ``session_vwap_asof`` (the
    discovery VWAP: typical price (H+L+C)/3 * volume, cumulative).
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


def detect_vwap_continuation_setup(
    ctx: BarContext,
    *,
    breakout_only: bool = False,
    put_needs_rising_vix: bool = False,
    realized_vol_floor_bps: float = DEFAULT_REALIZED_VOL_FLOOR_BPS,
) -> Optional[WatcherSignal]:
    """Detect VWAP_CONTINUATION (J_VWAP_CONT) on the current bar (WATCH-ONLY).

    direction="long" (buy calls) on an above-VWAP morning trend's first in-trend
    breakout/pullback bar; direction="short" (buy puts) on the below-VWAP mirror.

    Fires at most ONCE per day, only inside the morning window (bar time <= ENTRY_CUTOFF)
    after the TREND_BARS warmup, when the pure core qualifies the bar AND (for puts, when
    ``put_needs_rising_vix``) the as-of VIX 5-bar slope is >= 0. Returns None on any gate
    miss. Pure read of ctx; no I/O, no order placement.

    ``breakout_only`` / ``put_needs_rising_vix`` select the validated variants
    (J_VWAP_BREAKOUT / J_VWAP_CONT_VIXGATE). The wiring default is the full pattern
    (both triggers) with the VIX gate OFF, matching the headline J_VWAP_CONT/ATM cell;
    the heartbeat can opt into the VIX-gated cell via a param.

    ``realized_vol_floor_bps`` (GOAL 1, DORMANT default 0.0 = OFF): when > 0, skip the
    entry if the session's as-of realized vol (stdev of 5m close-to-close log-returns to
    the trigger, in bps) is below the floor — C1's "skip the dead quiet tape" lever. The
    as-of rvol is ALWAYS recorded in ``metadata['realized_vol_bps']`` (even when the floor
    is off) so live N can accrue toward the >=35 promotion bar. Verdict on the live
    chart-stop config is WATCH (no floor reaches 7/7 OP-22; the 2026-Q2 OOS slice stays
    negative + chart-stop WF<0.70). Inert at the 0.0 default — see vwap-cont-rvol-floor.json.
    """
    global _fired_today, _vix_hist, _evaluated_bars

    bar_time = ctx.timestamp_et.time()
    today = ctx.timestamp_et.date()
    day_str = today.isoformat()

    # New day -> reset per-day state.
    if _state_date != day_str:
        _reset_day(day_str)

    # Only operate inside RTH.
    if bar_time < RTH_OPEN or bar_time >= RTH_CLOSE:
        return None

    rth = _session_rth_vwap(ctx.prior_bars, today)
    if rth is None or len(rth) < TREND_BARS + 1:
        # Still warming up — but keep the VIX history in sync with the RTH bar count so
        # the as-of slope spans the right window once we reach the entry zone. Use the
        # RTH length as the chronological clock (one VIX sample per distinct RTH bar).
        if rth is not None:
            _sync_vix_hist(ctx, len(rth))
        return None

    # Keep one as-of VIX sample per RTH bar seen so far (causal; current bar included).
    _sync_vix_hist(ctx, len(rth))

    # Already took today's one entry.
    if _fired_today:
        return None

    # The current bar is the last row of `rth` (prior_bars includes the trigger bar).
    j = len(rth) - 1
    if j < TREND_BARS:
        return None  # inside the trend window — no entries yet

    # Morning window gate (discovery `break`s the per-day scan past the cutoff).
    if bar_time > ENTRY_CUTOFF:
        return None

    closes = rth["close"].values
    highs = rth["high"].values
    lows = rth["low"].values
    vwap = rth["_vwap"].values

    res = detect_vwap_continuation_core(
        closes, highs, lows, vwap, j, breakout_only=breakout_only,
    )
    if res is None:
        return None

    # VIX put-gate (C5): puts only when the as-of VIX slope >= 0. (Discovery `continue`s
    # — keeps scanning the morning — when a put fails this; the wrapper returns None for
    # this bar, and a later morning bar can still qualify.) The 1-bar fallback
    # (vix_now - vix_prior) keeps the gate active in the first <=5 morning bars, matching
    # the discovery's cross-session always-active slope.
    _vix_1bar = (getattr(ctx, "vix_now", 0.0) or 0.0) - (getattr(ctx, "vix_prior", 0.0) or 0.0)
    if (put_needs_rising_vix and res.side == "P"
            and vix_slope(_vix_hist, fallback_1bar=_vix_1bar) < 0):
        return None

    # As-of realized vol (GOAL 1). Computed once for both the (dormant) floor gate and the
    # always-on metadata log. Same definition as the validation harness (causal: session
    # RTH closes through the trigger bar). Checked BEFORE marking fired so a sub-floor bar
    # does NOT consume the day's single entry — byte-for-byte matches the harness (which
    # just drops sub-floor signals; the day yields no trade). Inert when floor <= 0.
    rvol_bps = realized_vol_bps(closes)
    if realized_vol_floor_bps > 0 and rvol_bps < realized_vol_floor_bps:
        return None

    # ── Entry — emit signal, mark fired ───────────────────────────────────────
    _fired_today = True
    entry = res.entry
    v = res.vwap_at_bar
    stop = res.stop_level

    if res.direction == "long":
        tp1_price = round(entry + _TP1_SPY_MOVE, 2)
        runner_price = round(entry + _RUNNER_SPY_MOVE, 2)
        instrument = "calls"
        side_word = "above"
    else:
        tp1_price = round(entry - _TP1_SPY_MOVE, 2)
        runner_price = round(entry - _RUNNER_SPY_MOVE, 2)
        instrument = "puts"
        side_word = "below"

    vix_now = getattr(ctx, "vix_now", None) or 0.0
    slope = vix_slope(_vix_hist, fallback_1bar=_vix_1bar)
    reason = (
        f"VWAP_CONTINUATION ({res.side} {res.trigger}): first {TREND_BARS} RTH bars all "
        f"closed {side_word} session VWAP (clean morning trend), then this bar "
        f"({bar_time.strftime('%H:%M')} ET, <= {ENTRY_CUTOFF.strftime('%H:%M')}) "
        f"continued in-trend ({res.trigger}) closing {side_word} VWAP ({v:.2f}) -> buy "
        f"{instrument}. Entry={entry:.2f} Stop(chart={'session low' if res.direction == 'long' else 'session high'} "
        f"to date)={stop:.2f}. Premium stop DISABLED (chart-stop only, L51/L55). "
        f"VIX={vix_now:.1f} (as-of 5-bar slope {slope:+.2f}). J's near-daily edge: "
        f"real-fills exp +$38.3/WR 76.5%, fires 42% of days, DSR PASS, both dirs + "
        f"(j-daily-pattern-LIVE.json). NEAR-SURVIVOR (6/7 OP-22; recent-Q soft)."
    )

    return WatcherSignal(
        watcher_name="vwap_continuation_watcher",
        setup_name="VWAP_CONTINUATION",
        direction=res.direction,
        entry_price=float(entry),
        stop_price=float(stop),
        tp1_price=float(tp1_price),
        runner_price=float(runner_price),
        confidence="medium",   # data-discovered, not yet live-confirmed (OP-21)
        reason=reason,
        triggers_fired=[
            "VWAP_TREND_ESTABLISHED",
            f"VWAP_CONTINUATION_{res.trigger.upper()}",
        ],
        metadata={
            "promotion_status": "WATCH_ONLY",
            "trigger": res.trigger,
            "vwap_at_bar": round(v, 4),
            "trend_bars": TREND_BARS,
            "entry_cutoff_et": ENTRY_CUTOFF.strftime("%H:%M"),
            "shallow_dip_tol": SHALLOW_DIP_TOL,
            "vix_now": vix_now,
            "vix_5bar_slope": round(slope, 4),
            "put_vix_gate_applied": bool(put_needs_rising_vix),
            # GOAL 1: as-of realized vol (always logged for live N-accrual) + the dormant floor
            "realized_vol_bps": round(rvol_bps, 3),
            "realized_vol_floor_bps": float(realized_vol_floor_bps),
            "realized_vol_floor_applied": bool(realized_vol_floor_bps > 0),
            "chart_stop": round(stop, 2),
            "premium_stop_pct": DEFAULT_PREMIUM_STOP_PCT,    # -0.99 = disabled
            "strike_offset": DEFAULT_STRIKE_OFFSET,           # 0 = ATM (validated tier)
            "default_qty": 3,
            "tp1_premium_pct": DEFAULT_TP1_PREMIUM_PCT,
            "tp1_qty_fraction": DEFAULT_TP1_QTY_FRACTION,
            "runner_target_pct": DEFAULT_RUNNER_TARGET_PCT,
            "validation": "analysis/recommendations/j-daily-pattern-LIVE.json",
            "promotion_gate": (
                "OP-21: offline real-fills NEAR-SURVIVOR (6/7 OP-22 — OOS+, WF>=0.70 "
                "ITM1/VIXGATE, q>=60%, DSR PASS, both dirs +, drop-top5 robust; misses "
                "all-cuts-OOS+ on the recent-Q soft window). Live gate: 3 live J "
                "confirmations + Rule 9 before any live order path."
            ),
        },
    )


def _sync_vix_hist(ctx: BarContext, rth_len: int) -> None:
    """Append today's as-of ``vix_now`` once per distinct RTH bar (chronological clock).

    The wrapper is called once per bar in order; ``rth_len`` is today's RTH bar count
    through the current bar. We record one VIX sample per RTH bar index so ``vix_slope``
    spans exactly ``VIX_SLOPE_LOOKBACK`` *bars* (matching the discovery slope, which
    indexes the global VIX series by entry bar). Idempotent per bar index.
    """
    global _vix_hist, _evaluated_bars
    if rth_len <= 0:
        return
    idx = rth_len - 1
    if idx in _evaluated_bars:
        return
    _evaluated_bars.add(idx)
    vix_now = getattr(ctx, "vix_now", None)
    _vix_hist.append(float(vix_now) if vix_now is not None else 0.0)


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

    # ── A — SHOULD FIRE long: clean above-VWAP open then a fresh-high breakout ──
    # 3 green bars climbing (all closes above their as-of VWAP), then a new-high bar.
    _reset_day("none")
    rows_a = [
        _bar(9, 30, 600.0, 600.6, 599.9, 600.5),
        _bar(9, 35, 600.5, 601.2, 600.4, 601.1),
        _bar(9, 40, 601.1, 601.8, 601.0, 601.7),
        _bar(9, 45, 601.7, 602.6, 601.6, 602.5),   # fresh high, close > VWAP -> breakout
    ]
    sig_a = detect_vwap_continuation_setup(_mk_ctx(rows_a))
    fired_a = sig_a is not None and sig_a.direction == "long" and sig_a.metadata["trigger"] == "breakout"
    results.append(("A: above-VWAP trend + fresh-high SHOULD fire long breakout", fired_a))
    print(f"[A] {('FIRED ' + sig_a.direction + ' ' + sig_a.metadata['trigger'] + f' stop={sig_a.stop_price}') if sig_a else 'no signal'}")

    # ── B — SHOULD FIRE short: clean below-VWAP open then a fresh-low breakout ──
    _reset_day("none")
    rows_b = [
        _bar(9, 30, 600.0, 600.1, 599.4, 599.5),
        _bar(9, 35, 599.5, 599.6, 598.8, 598.9),
        _bar(9, 40, 598.9, 599.0, 598.2, 598.3),
        _bar(9, 45, 598.3, 598.4, 597.4, 597.5),   # fresh low, close < VWAP -> breakout
    ]
    sig_b = detect_vwap_continuation_setup(_mk_ctx(rows_b))
    fired_b = sig_b is not None and sig_b.direction == "short" and sig_b.metadata["trigger"] == "breakout"
    results.append(("B: below-VWAP trend + fresh-low SHOULD fire short breakout", fired_b))
    print(f"[B] {('FIRED ' + sig_b.direction + ' ' + sig_b.metadata['trigger'] + f' stop={sig_b.stop_price}') if sig_b else 'no signal'}")

    # ── C — SHOULD NOT FIRE: mixed open (no clean one-sided VWAP trend) ─────────
    _reset_day("none")
    rows_c = [
        _bar(9, 30, 600.0, 600.6, 599.4, 600.4),   # close above
        _bar(9, 35, 600.4, 600.6, 599.0, 599.2),   # close below -> mixed
        _bar(9, 40, 599.2, 599.9, 599.0, 599.8),
        _bar(9, 45, 599.8, 600.9, 599.7, 600.8),
    ]
    sig_c = detect_vwap_continuation_setup(_mk_ctx(rows_c))
    results.append(("C: mixed open (no clean trend) should NOT fire", sig_c is None))
    print(f"[C] {'no signal (correct)' if sig_c is None else 'FIRED (wrong!)'}")

    # ── D — SHOULD NOT FIRE: past the morning cutoff (11:00 > 10:30) ───────────
    _reset_day("none")
    rows_d = [_bar(h, m, 600.0 + i * 0.2, 600.6 + i * 0.2, 599.9 + i * 0.2, 600.5 + i * 0.2)
              for i, (h, m) in enumerate([(10, 15), (10, 20), (10, 25)])]
    rows_d.append(_bar(11, 0, 600.9, 601.9, 600.8, 601.8))   # breakout but 11:00 > cutoff
    sig_d = detect_vwap_continuation_setup(_mk_ctx(rows_d))
    results.append(("D: continuation past 10:30 cutoff should NOT fire", sig_d is None))
    print(f"[D] {'no signal (correct)' if sig_d is None else 'FIRED (wrong!)'}")

    # ── E/F/F2 — VIX put-gate (C5). Clean below-VWAP fresh-low breakout day. The first
    # qualifying put bar is the 4th RTH bar; the gate is active from the first morning
    # bar via the 1-bar vix_now-vix_prior fallback (matches the discovery's always-active
    # cross-session slope). We drive bar-by-bar with a strictly FALLING / RISING vix and
    # take the FIRST fired signal.
    def _first_fire(rows, vix_seq, *, gate):
        _reset_day("none")
        for k in range(len(rows)):
            ctx = _mk_ctx(rows[: k + 1], vix=vix_seq[k])
            # set vix_prior to the previous bar's vix so the 1-bar fallback has direction
            ctx.vix_prior = vix_seq[k - 1] if k > 0 else vix_seq[k]
            s = detect_vwap_continuation_setup(ctx, put_needs_rising_vix=gate)
            if s is not None:
                return s, k
        return None, None

    base_e = [
        _bar(9, 30, 600.0, 600.1, 599.4, 599.5),
        _bar(9, 35, 599.5, 599.6, 598.8, 598.9),
        _bar(9, 40, 598.9, 599.0, 598.2, 598.3),
        _bar(9, 45, 598.3, 598.4, 597.4, 597.5),   # fresh-low breakout, close < VWAP
    ]
    falling = [20.0, 19.0, 18.0, 17.0]   # 1-bar slope at entry bar < 0
    rising = [16.0, 17.0, 18.0, 19.0]    # 1-bar slope at entry bar > 0

    sig_e, _ = _first_fire(base_e, falling, gate=True)
    results.append(("E: VIX-gated put with FALLING vix should NOT fire", sig_e is None))
    print(f"[E] {'no signal (correct)' if sig_e is None else 'FIRED (wrong!)'}")

    sig_f, _ = _first_fire(base_e, falling, gate=False)
    results.append(("F: same day, VIX gate OFF, fires short breakout (control)",
                    sig_f is not None and sig_f.direction == "short" and sig_f.metadata["trigger"] == "breakout"))
    print(f"[F] {('FIRED ' + sig_f.direction + ' ' + sig_f.metadata['trigger']) if sig_f else 'no signal'}")

    sig_f2, _ = _first_fire(base_e, rising, gate=True)
    results.append(("F2: VIX gate ON + RISING vix, fires short (gate satisfied)", sig_f2 is not None and sig_f2.direction == "short"))
    print(f"[F2] {('FIRED ' + sig_f2.direction) if sig_f2 else 'no signal'}")

    # ── G2 — pure vix_slope: deep history uses the 5-bar span (discovery semantics) ─
    rising_hist = [15.0, 15.5, 16.0, 16.5, 17.0, 18.0]   # len 6 > look=5; slope=18-15=+3
    falling_hist = [20.0, 19.5, 19.0, 18.5, 18.0, 16.0]  # slope=16-20=-4
    g2 = (abs(vix_slope(rising_hist) - 3.0) < 1e-9 and abs(vix_slope(falling_hist) + 4.0) < 1e-9
          and vix_slope([17.0, 17.0]) == 0.0                          # short history, no fallback -> 0
          and vix_slope([17.0, 17.0], fallback_1bar=-0.5) == -0.5)    # short history, fallback used
    results.append(("G2: vix_slope deep-history 5-bar span + short-history fallback", g2))
    print(f"[G2] rising={vix_slope(rising_hist):+.1f} falling={vix_slope(falling_hist):+.1f} (expect +3.0 / -4.0)")

    # ── G — core parity: matches the discovery per-bar condition on a known case ─
    closes = np.array([600.5, 601.1, 601.7, 602.5])
    highs = np.array([600.6, 601.2, 601.8, 602.6])
    lows = np.array([599.9, 600.4, 601.0, 601.6])
    # as-of VWAP roughly tracking below the closes (uptrend) — approximate with typical px
    vwap = np.array([600.17, 600.57, 600.97, 601.4])
    core = detect_vwap_continuation_core(closes, highs, lows, vwap, 3)
    results.append(("G: core long breakout side=C stop=session-low", core is not None and core.side == "C" and core.trigger == "breakout" and core.stop_level == 599.9))
    print(f"[G] core={core}")

    # ── H — breakout_only suppresses a pullback-only bar ───────────────────────
    # craft a bar that is a pullback (dips to VWAP, closes above) but NOT a fresh high
    closes_h = np.array([601.0, 601.5, 602.0, 601.6])
    highs_h = np.array([601.1, 601.6, 602.1, 601.7])   # bar 3 high 601.7 < prior max 602.1 -> not breakout
    lows_h = np.array([600.6, 601.1, 601.6, 600.95])
    vwap_h = np.array([600.8, 601.0, 601.2, 601.0])    # bar3 low 600.95 <= vwap*(1+tol) ~601.6, close 601.6>vwap -> pullback
    core_pb = detect_vwap_continuation_core(closes_h, highs_h, lows_h, vwap_h, 3)
    core_pb_only = detect_vwap_continuation_core(closes_h, highs_h, lows_h, vwap_h, 3, breakout_only=True)
    results.append(("H: pullback bar fires full, suppressed by breakout_only",
                    core_pb is not None and core_pb.trigger == "pullback" and core_pb_only is None))
    print(f"[H] full={core_pb}, breakout_only={core_pb_only}")

    print("\n=== VWAP_CONTINUATION self-test ===")
    all_pass = True
    for name, ok in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
        all_pass = all_pass and ok
    print(f"=== {'ALL PASS' if all_pass else 'SOME FAILED'} ===")
    _sys.exit(0 if all_pass else 1)
