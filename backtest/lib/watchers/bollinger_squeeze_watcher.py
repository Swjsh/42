"""BOLLINGER_SQUEEZE watcher — WATCH-ONLY per OP-21 (wired DISARMED until the
WIRE-BOLLINGER conductor proposal applies after close).

BB(20,2) bandwidth squeeze (bottom-quintile of its trailing 20-bar window, within
session) FOLLOWED BY an expansion breakout: close crosses the PRIOR bar's band with
volume confirmation (>= 1.3x the 20-bar trailing average). Up-break -> calls;
down-break -> puts. Direction = breakout direction. Per-side 30-min cooldown.

VALIDATION (the one survivor of the 2026-06-25 four-family grind — real OPRA fills):
  family-grind-bollinger_squeeze.json: n_signals=316 over 2025-01-01..2026-06-18,
  13/13 P3 cells PASS-P4 (a coherent ATM/OTM-1 strike/stop surface, not a lucky cell).
  Chosen cell ATM|stop-8 (tp1 0.30 / sell 0.667 / chandelier-trail 0.15):
    n=303 exp +$34.9/tr WR 37% OOS-2026 +$43.6/tr WF 1.431 qpf 1.0 (6/6 quarters)
    top5-day 33% max_dd -$139.2 — the strictly-dominant sibling of the headline
    ATM|stop-15 (judge spot-check 2026-07-02).
  Two-sided: CALLS +$4,531 (+$29/tr) AND PUTS +$6,037 (+$41/tr), both years positive.
  DIRECTION-CONTROLLED null (L188, _verify_bollinger.py): SURVIVES — signal $34.9 >
  dir-null max $26.3; drop-top5 $24.0 > dir-null mean $17.8. Squeeze selection alpha,
  not direction-following (contrast three_ducks: COLLAPSED, dead).
  GRIND-RESULTS.md "the one survivor" section has the full disclosure stack.

────────────────────────────────────────────────────────────────────────────────
PATTERN (BYTE-FOR-BYTE port of autoresearch.family_detectors.detect_bollinger_squeeze
— the detector that was validated; the parity test pins the port to the exact 316
signals the grind funnel produced):

  Per-session BB(20, 2.0) on close (population stdev, TV ta.stdev convention).
  bandwidth bw = (upper - lower) / mid.
  squeeze[k]  = bw[k] <= trailing 20-bar 20th-percentile of bw (causal, within session).
  Fire at bar i (>= second bar of session) when ALL of:
    - any squeeze in the last SQ_RECENT=4 bars (bars [k-4, k-1] — NOT necessarily bar i)
    - bar time within ENTRY_GATE 09:35..15:45 ET
    - volume[i] >= 1.3 x trailing 20-bar mean volume (mean includes bar i, min 20 bars)
    - close[i] > upper[i-1]  -> side C   |   close[i] < lower[i-1] -> side P
    - per-side 30-min cooldown clear
  Stop geometry = 12-bar trailing swing invalidation (same as the random-entry null:
  CALL -> swing LOW must hold, PUT -> swing HIGH), so the validated cell's sim stop
  and this watcher's chart stop are the SAME function (null_baseline._swing_invalidation,
  copied verbatim below + pinned by the parity test).

CAUSALITY: decision at bar i reads only bars <= i (C6 — the family_detectors suite
carries the truncation-invariance guard; the frame scan here is the same code).

OP-21 promotion gate:
  Offline (real-fills): PASS — see VALIDATION above. Wiring spec filed as the
  WIRE-BOLLINGER row in automation/state/conductor-proposals.jsonl (after-close apply).
  This module ONLY observes + signals; nothing imports it on the live path until the
  dispatcher entry is applied.

Sources:
  backtest/autoresearch/family_detectors.py#detect_bollinger_squeeze (validated detector)
  backtest/autoresearch/null_baseline.py#_swing_invalidation (stop geometry)
  backtest/lib/watchers/gap_and_go_watcher.py (structural template)
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

import numpy as np
import pandas as pd

from . import WatcherSignal
from ..filters import BarContext


# ── Detection parameters (IDENTICAL to family_detectors — no silent drift, C14) ─
SQ_LOOKBACK: int = 20        # trailing window for the squeeze percentile (within session)
SQ_QUANTILE: float = 0.20    # bandwidth in bottom 20% of the trailing window = "squeeze"
SQ_RECENT: int = 4           # breakout must occur within 4 bars of a squeeze
VOL_MULT: float = 1.3        # breakout bar volume >= 1.3x its 20-bar trailing average
BB_N: int = 20               # Bollinger length
BB_K: float = 2.0            # Bollinger width (stdev multiples)

RTH_OPEN: dt.time = dt.time(9, 30)
RTH_CLOSE: dt.time = dt.time(16, 0)
ENTRY_GATE: tuple[dt.time, dt.time] = (dt.time(9, 35), dt.time(15, 45))
COOLDOWN_MIN: int = 30       # per-side min gap between signals
SWING_LOOKBACK: int = 12     # swing-stop lookback (== null default)

SIDE_CALL = "C"
SIDE_PUT = "P"

# ── Exit knobs (the VALIDATED ATM|stop-8 cell — family-grind elite #3 by rank,
#    #1 by robustness: lowest max_dd/top5 with the highest exp of the ATM column) ──
DEFAULT_STRIKE_OFFSET: int = 0            # ATM (validated tier; OTM-1 column also PASS)
DEFAULT_PREMIUM_STOP_PCT: float = -0.08   # -8% premium catastrophe stop (validated)
DEFAULT_QTY: int = 3
DEFAULT_TP1_PREMIUM_PCT: float = 0.30     # +30% TP1 (validated)
DEFAULT_TP1_QTY_FRACTION: float = 0.667   # sell 2/3 at TP1 (validated; NOT the Safe 0.8)
DEFAULT_PROFIT_LOCK_MODE: str = "trailing"
DEFAULT_PROFIT_LOCK_TRAIL_PCT: float = 0.15  # chandelier trails 15% off HWM (validated)
DEFAULT_RUNNER_TARGET_PCT: float = 2.5

# Advisory SPY-move translations for the WatcherSignal price fields (obs schema only;
# the real exit stack is premium-based per the validated cell above).
_TP1_SPY_MOVE: float = 0.70
_RUNNER_SPY_MOVE: float = 2.50


# ── frame prep (mirror of family_detectors.build_rth) ────────────────────────
def prep_frame(spy: pd.DataFrame) -> pd.DataFrame:
    """RTH-only frame with a reset RangeIndex + tz-naive timestamp_et + `date`/`t` columns.
    Positional index == the bar_idx every signal dict emits (build_rth parity)."""
    df = spy.copy()
    ts = pd.to_datetime(df["timestamp_et"])
    if getattr(ts.dt, "tz", None) is not None:
        ts = ts.dt.tz_localize(None)
    df["timestamp_et"] = ts
    times = ts.dt.time
    df = df[(times >= RTH_OPEN) & (times < RTH_CLOSE)].reset_index(drop=True)
    df["date"] = df["timestamp_et"].dt.date
    df["t"] = df["timestamp_et"].dt.time
    return df


def _in_window(t: dt.time, window: tuple[dt.time, dt.time]) -> bool:
    return window[0] <= t <= window[1]


def swing_invalidation(rth: pd.DataFrame, idx: int, side: str, swing_lookback: int) -> float:
    """VERBATIM copy of null_baseline._swing_invalidation (the validated stop geometry):
    trailing swing LOW (CALL -> support that must hold) / swing HIGH (PUT -> resistance).
    Causal — uses only bars in ``[idx-lookback+1, idx]``. Parity-pinned by the test."""
    c = float(rth.iloc[idx]["close"])
    lo = max(0, idx - swing_lookback + 1)
    win = rth.iloc[lo: idx + 1]
    if side == "C":
        rej = float(win["low"].min())
        return rej if rej < c else c - 1.0
    rej = float(win["high"].max())
    return rej if rej > c else c + 1.0


def bollinger_session(rth: pd.DataFrame, n: int = BB_N, k: float = BB_K):
    """Per-session Bollinger mid/upper/lower/bandwidth (population stdev, TV ta.stdev).
    BYTE-FOR-BYTE the family_detectors.bollinger_session math."""
    N = len(rth)
    mid = np.full(N, np.nan); up = np.full(N, np.nan)
    lo = np.full(N, np.nan); bw = np.full(N, np.nan)
    close = rth["close"]
    for _, grp in rth.groupby("date", sort=False):
        idx = grp.index.to_numpy()
        s = close.loc[idx]
        m = s.rolling(n, min_periods=n).mean()
        sd = s.rolling(n, min_periods=n).std(ddof=0)   # population stdev (TV convention)
        u = m + k * sd
        d = m - k * sd
        b = (u - d) / m
        mid[idx] = m.to_numpy(); up[idx] = u.to_numpy()
        lo[idx] = d.to_numpy(); bw[idx] = b.to_numpy()
    return mid, up, lo, bw


def _emit(rth: pd.DataFrame, idx: int, side: str, family: str, **meta) -> dict:
    """Signal record — same shape as family_detectors._emit (grind funnel schema)."""
    bar = rth.iloc[idx]
    rej = swing_invalidation(rth, idx, side, SWING_LOOKBACK)
    return {
        "family": family,
        "date": bar["date"],
        "time": bar["timestamp_et"].strftime("%H:%M"),
        "bar_idx": int(idx),
        "side": side,
        "entry_spot": round(float(bar["close"]), 2),
        "rejection_level": round(float(rej), 2),
        "meta": meta,
    }


def _cooldown_ok(last: dict, bar_time, side) -> bool:
    """Per-side 30-min cooldown (no back-to-back same-direction churn)."""
    prev = last.get(side)
    if prev is None:
        return True
    return (bar_time - prev).total_seconds() / 60.0 >= COOLDOWN_MIN


def detect_bollinger_squeeze_frame(rth: pd.DataFrame) -> list[dict]:
    """Full-frame scan — BYTE-FOR-BYTE the validated
    autoresearch.family_detectors.detect_bollinger_squeeze. Input frame must be
    prep_frame()-shaped (RangeIndex, tz-naive timestamp_et, date/t columns).

    Returns the same signal dicts the grind funnel consumed; the parity test pins
    this to the exact 316 signals of the 2025-01-01..2026-06-18 grind window."""
    mid, up, lo, bw = bollinger_session(rth, BB_N, BB_K)
    vol = rth["volume"].to_numpy()
    c = rth["close"].to_numpy()
    out: list[dict] = []
    for _, grp in rth.groupby("date", sort=False):
        idx = grp.index.to_numpy()
        # trailing causal squeeze flag per session bar
        bw_s = pd.Series(bw[idx])
        q = bw_s.rolling(SQ_LOOKBACK, min_periods=SQ_LOOKBACK).quantile(SQ_QUANTILE)
        squeeze = (bw_s <= q).to_numpy()
        volavg = pd.Series(vol[idx]).rolling(20, min_periods=20).mean().to_numpy()
        last: dict = {}
        for k, i in enumerate(idx):
            if k == 0:
                continue
            j = idx[k - 1]
            if any(np.isnan(v) for v in (up[j], lo[j], volavg[k])):
                continue
            # squeeze active within the recent SQ_RECENT bars (but not necessarily THIS bar)
            recent = squeeze[max(0, k - SQ_RECENT):k]
            if not recent.any():
                continue
            t = rth.at[i, "t"]
            if not _in_window(t, ENTRY_GATE):
                continue
            vol_ok = volavg[k] > 0 and vol[i] >= VOL_MULT * volavg[k]
            if not vol_ok:
                continue
            up_break = c[i] > up[j]
            dn_break = c[i] < lo[j]
            side = SIDE_CALL if up_break else (SIDE_PUT if dn_break else None)
            if side is None:
                continue
            bt = rth.at[i, "timestamp_et"]
            if not _cooldown_ok(last, bt, side):
                continue
            out.append(_emit(rth, i, side, "bollinger_squeeze"))
            last[side] = bt
    return out


# ── live ctx wrapper ──────────────────────────────────────────────────────────
def detect_bollinger_squeeze_setup(ctx: BarContext) -> Optional[WatcherSignal]:
    """Detect BOLLINGER_SQUEEZE on the CURRENT bar (WATCH-ONLY).

    Runs the byte-identical frame scan over the session's bars (ctx.prior_bars —
    the dispatcher's sameday frame WITH timestamps, current bar last) and fires
    ONLY when the LAST bar is a signal. The full-session scan makes the per-side
    30-min cooldown and the within-session squeeze/vol baselines exact, so a live
    tick fires precisely where the backtest fired (no live/backtest drift, C14).

    Needs >= ~40 session bars of warmup (BB(20) + 20-bar squeeze percentile), so
    the earliest possible live fire is early afternoon — consistent with the
    validated signal population. Returns None on any gate miss.
    """
    pb = ctx.prior_bars
    if pb is None or len(pb) < (2 * SQ_LOOKBACK) or "timestamp_et" not in pb.columns:
        return None
    if "volume" not in pb.columns:
        return None
    try:
        rth = prep_frame(pb)
    except (KeyError, TypeError, ValueError):
        return None
    if rth.empty:
        return None

    # The trigger bar must be the frame's last bar (the dispatcher guarantees this;
    # re-check so a stale/multi-day frame can never fire on a historical bar).
    last_ts = rth["timestamp_et"].iloc[-1]
    ctx_ts = pd.Timestamp(ctx.timestamp_et)
    if ctx_ts.tz is not None:
        ctx_ts = ctx_ts.tz_localize(None)
    if last_ts != ctx_ts:
        return None

    signals = detect_bollinger_squeeze_frame(rth)
    if not signals or signals[-1]["bar_idx"] != len(rth) - 1:
        return None
    sig = signals[-1]

    side = sig["side"]
    direction = "long" if side == SIDE_CALL else "short"
    entry = float(sig["entry_spot"])
    stop_price = float(sig["rejection_level"])     # 12-bar swing (validated geometry)
    if direction == "long":
        tp1_price = round(entry + _TP1_SPY_MOVE, 2)
        runner_price = round(entry + _RUNNER_SPY_MOVE, 2)
        break_word = "up-break above prior upper band"
        instrument = "calls"
    else:
        tp1_price = round(entry - _TP1_SPY_MOVE, 2)
        runner_price = round(entry - _RUNNER_SPY_MOVE, 2)
        break_word = "down-break below prior lower band"
        instrument = "puts"

    vix_now = getattr(ctx, "vix_now", None) or 0.0
    reason = (
        f"BOLLINGER_SQUEEZE (expansion breakout): BB(20,2) bandwidth squeeze within the "
        f"last {SQ_RECENT} bars, then {break_word} with volume >= {VOL_MULT}x 20-bar avg. "
        f"Direction: {direction} (buy {instrument}). Entry={entry:.2f} "
        f"Stop(chart=12-bar swing)={stop_price:.2f}, premium stop {DEFAULT_PREMIUM_STOP_PCT:.0%}. "
        f"VIX={vix_now:.1f}. Validated: real-fills ATM|stop-8 exp +$34.9/tr, OOS +$43.6/tr, "
        f"WF 1.431, qpf 1.0, two-sided, dir-null SURVIVES "
        f"(family-grind-bollinger_squeeze.json + GRIND-RESULTS.md)."
    )

    return WatcherSignal(
        watcher_name="bollinger_squeeze_watcher",
        setup_name="BOLLINGER_SQUEEZE",
        direction=direction,
        entry_price=entry,
        stop_price=stop_price,
        tp1_price=tp1_price,
        runner_price=runner_price,
        confidence="medium",   # data-discovered, not yet live-confirmed (OP-21)
        reason=reason,
        triggers_fired=[
            "BB_SQUEEZE_RECENT",
            "BAND_BREAK_UP" if direction == "long" else "BAND_BREAK_DOWN",
            "VOLUME_CONFIRM",
        ],
        metadata={
            "promotion_status": "WATCH_ONLY",
            "signal_time": sig["time"],
            "chart_stop": stop_price,
            "premium_stop_pct": DEFAULT_PREMIUM_STOP_PCT,
            "strike_offset": DEFAULT_STRIKE_OFFSET,          # 0 = ATM (validated tier)
            "default_qty": DEFAULT_QTY,
            "tp1_premium_pct": DEFAULT_TP1_PREMIUM_PCT,
            "tp1_qty_fraction": DEFAULT_TP1_QTY_FRACTION,
            "profit_lock_mode": DEFAULT_PROFIT_LOCK_MODE,
            "profit_lock_trail_pct": DEFAULT_PROFIT_LOCK_TRAIL_PCT,
            "runner_target_pct": DEFAULT_RUNNER_TARGET_PCT,
            "vix_now": vix_now,
            "validation": "analysis/recommendations/family-grind-bollinger_squeeze.json",
            "fresh_reverify": "analysis/recommendations/bollinger-squeeze-fresh-reverify.json",
            "promotion_gate": (
                "OP-21: offline real-fills PASS (13/13 P4 surface, dir-null SURVIVES, "
                "two-sided, WF 1.43). Wiring via WIRE-BOLLINGER conductor proposal "
                "(after-close apply); paper trade-to-learn per 2026-07-01 mandate."
            ),
        },
    )
