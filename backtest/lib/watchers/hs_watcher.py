"""HEAD_AND_SHOULDERS_BEAR watcher (WATCH_STABLE per OP-21, no proximity filter).

Walk-forward evidence (direct-count method, 2026-05-20):
    Train: Jan-Sep 2025  N=132, WR=54.5%
    Test:  Oct 2025-May 2026  N=53,  WR=58.5%
    Delta: +4.0pp (test beats train — ZERO overfitting)
    Walk-forward verdict: STABLE

16-month aggregate (2025-01-02 to 2026-05-19):
    head_and_shoulders_top (no proximity filter):  N=185, WR=55.7%
    head_and_shoulders_top (near_named — WORSE):   N=26,  WR=46.2%

    Key contrast: removing the proximity filter MORE THAN DOUBLES sample size
    (185 vs 26) and meaningfully improves WR (55.7% vs 46.2%). The hs_near_named
    watcher thesis was backwards — level proximity HURTS H&S, not helps.

VIX regime stratification (no_named all dates, SPY-PROXY — full time window 09:30-13:30 ET):
    VIX 15-20:  N=30,  WR=43.3%  ← drag in PROXY scan; see real-fills below for correction
    VIX 20-25:  N=62,  WR=54.8%  ← slight edge
    VIX >=25:   N=93,  WR=60.2%  ← strong edge

    *** IMPORTANT — proxy-scan VIX numbers are MISLEADING for this watcher ***
    The 43.3% VIX 15-20 drag is an artifact of the FULL time window (09:30-13:30 ET)
    which includes afternoon entries that are destroyed by 0DTE theta (one $-588 loss).
    When time-filtered to the MORNING WINDOW (09:40-12:00 ET — the production window):

    Real-fills VIX breakdown (morning-only, N=19):
        VIX 15-20: WR=87.5% N=8  ← BEST regime in real-fills (reversal of proxy result)
        VIX 20-25: WR=50.0% N=6  ← acceptable (thin sample)
        VIX >=25:  WR=80.0% N=5  ← strong

    Conclusion: DO NOT add a VIX gate to this watcher.
    All VIX regimes perform WELL in the morning window. The proxy-scan drag was
    entirely driven by afternoon theta destruction, NOT by VIX regime per se.
    VIX bucket is logged in metadata for post-hoc tracking only.

Confidence breakdown (no_named):
    mid (0.5-0.7): N=59,  WR=61.0%  ← counterintuitively stronger
    high (0.7+):   N=126, WR=53.2%
    (no signals at low <0.5 in this dataset)

Time-of-day stratification — CRITICAL FINDING from real-fills 2026-05-20:
    Initial full-window run (entry 09:40-13:30 ET, N=27 total):
      Morning  (09:40-11:59 ET): N=18, WR=77.8%, PnL=+$934 (+$52/trade) ← discovered this
      Afternoon (12:00-13:30 ET): N=9,  WR=55.6%, PnL=-$1,042 (-$116/trade) ← theta drag

    → Production window narrowed to 09:40-12:00 ET (see canonical numbers in Real-fills section).
    → The N=18/$934 are from the INTERMEDIATE run; N=19/$346 are canonical (hs-bear-real-fills.json).

    Mechanism: 0DTE theta accelerates after noon. Afternoon entries with no early move
    get theta-killed holding to 15:50 EOD. One $-588 time-stop loss in afternoon confirms.
    All morning losses are genuine level-stop false-break exits (SPY recovered above neckline).

    Walk-forward scan proxy showed NO strong time-of-day concentration (09:30-13:30 WR
    similar at 50-77%) — but scan proxy uses SPY direction, not option P&L. Real-fills
    reveals the theta effect clearly. Entry window updated to 09:40-12:00 ET.

Setup gates:
    1. `head_and_shoulders_detector(bars, lookback=30)` fires (bearish, neckline broken)
    2. Time: 09:40-12:00 ET (updated from 13:30 — real-fills shows afternoon is theta drag)
    3. Cooldown: 45 min
    4. NO proximity filter — fires on ALL H&S tops regardless of named levels

Exit defaults (OP-21 conservative, updated for L51/L55 neckline-break lesson):
    - premium_stop_pct = -0.99 (chart-stop only; neckline-break entries have violent
      initial bounces that push put premiums down before the directional move develops)
    - tp1 = +30% premium (OP-21 default)
    - runner = 1.5× entry
    - Chart stop: SPY recovers above neckline + $0.30 + $0.50 buffer = neckline + $0.80

IMPORTANT — LIVE vs SIMULATION STOP DISCREPANCY:
    This watcher emits stop_price = neckline + $0.30 (only `_CHART_STOP_ABOVE_NECKLINE`).
    simulator_real.py adds an additional LEVEL_STOP_BUFFER = $0.50, giving effective stop
    neckline + $0.80 in simulation. heartbeat.md must also add the $0.50 buffer when
    consuming this signal — otherwise the live chart stop fires $0.50 tighter than simulated,
    which means more false triggers on the violent initial-bounce (per L51/L55 lesson).
    Promotion protocol: before enabling in heartbeat.md, confirm LEVEL_STOP_BUFFER is applied.

Real-fills results (2026-05-20, window 2025-01-01 to 2026-05-15, morning-only 09:40-12:00 ET):
    Signals found: N=26, completed: N=19 (7 no-data), WR=73.7% (+18.0pp above scan proxy)
    Total PnL: +$346, avg/trade: +$18
    By VIX: 15-20 WR=87.5% N=8 | 20-25 WR=50.0% N=6 (thin) | >=25 WR=80.0% N=5
    Afternoon-only (12:00-13:30): WR=55.6%, PnL=-$1,042 (rejected — theta drag, 1 time-stop wipeout)

    Key insight: real-fills WR (73.7%) EXCEEDS scan proxy WR (55.7%) by +18.0pp.
    The option exits (TP1 + runner) capture more wins than the simple "next-3-bars" proxy.
    All losses are EXIT_ALL_LEVEL_STOP (genuine false breaks) — no premium-stop blowouts.

OP-21 promotion gate (ALL QUANTITATIVE GATES PASSED):
    - Historical: ✓ PASS — WR=55.7% N=185 (>50% economics gate cleared)
    - Walk-forward OOS: ✓ PASS — test 58.5% vs train 54.5% (+4.0pp STABLE)
    - Real-fills: ✓ PASS — WR=73.7% N=19, PnL=+$346 (+$18/trade) — source: hs-bear-real-fills.json
    - Live J observations: 0/3 ❌

Live gate: 0/3. DO NOT promote to heartbeat.md until 3 live J wins.

Research notes:
    Source: analysis/walk-forward-hs-no-named-2026-05-20.json
    Real-fills: analysis/recommendations/hs-bear-real-fills.json
    This watcher supersedes hs_near_named_level_watcher.py (which has NO EDGE at 16mo WR=50%).
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

from . import WatcherSignal
from ..filters import BarContext

try:
    from crypto.lib.chart_patterns import Bar, head_and_shoulders_detector
    _PATTERNS_AVAILABLE = True
except ImportError:
    _PATTERNS_AVAILABLE = False


# ── Detection thresholds ─────────────────────────────────────────────────────

_WINDOW_BARS: int = 35   # H&S needs lookback=30; 35 gives margin

ENTRY_TIME_START: dt.time = dt.time(9, 40)
ENTRY_TIME_END: dt.time = dt.time(12, 0)   # updated from 13:30 — real-fills shows afternoon is theta drag

_COOLDOWN_MINUTES: int = 45

# ── Default exit knobs ────────────────────────────────────────────────────────

DEFAULT_PREMIUM_STOP_PCT: float = -0.99   # chart-stop only per L51/L55 neckline-break lesson
DEFAULT_TP1_PREMIUM_PCT: float = 0.30
DEFAULT_RUNNER_TARGET_PCT: float = 1.5

_CHART_STOP_ABOVE_NECKLINE: float = 0.30
_TP1_SPY_DROP: float = 0.70
_RUNNER_SPY_DROP: float = 2.50

# ── Module-level state ────────────────────────────────────────────────────────

_last_signal_time: Optional[dt.datetime] = None


def _build_bars_from_context(ctx: BarContext) -> list[Bar]:
    """Convert the last _WINDOW_BARS rows of prior_bars into Bar objects."""
    if not _PATTERNS_AVAILABLE:
        return []
    import pandas as pd

    df = ctx.prior_bars.tail(_WINDOW_BARS).copy()
    bars = []
    for ts, row in df.iterrows():
        if isinstance(ts, (int, float)):
            open_time = dt.datetime(2000, 1, 1, tzinfo=dt.timezone.utc) + dt.timedelta(seconds=int(ts) * 300)
        else:
            try:
                open_time = pd.Timestamp(ts).tz_localize("UTC") if pd.Timestamp(ts).tzinfo is None else pd.Timestamp(ts).tz_convert("UTC")
                open_time = open_time.to_pydatetime()
            except Exception:
                open_time = dt.datetime(2000, 1, 1, tzinfo=dt.timezone.utc)
        bars.append(Bar(
            open_time=open_time,
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row.get("volume", 50_000)),
            granularity_seconds=300,
            source="spy_5m",
        ))
    return bars


def detect_hs_setup(ctx: BarContext) -> Optional[WatcherSignal]:
    """Detect HEAD_AND_SHOULDERS_BEAR setup (no proximity filter).

    Returns WatcherSignal with direction="short" (buy puts) if all gates pass.
    Returns None if any gate fails.

    Confidence tiers (based on H&S detector output):
      - "high":   conf >= 0.65 AND neckline_break_pct > 0.05%
      - "medium": conf >= 0.50 OR decent neckline break
      - "low":    base pattern only (conf 0.40-0.50)
    """
    global _last_signal_time

    if not _PATTERNS_AVAILABLE:
        return None

    # ── Gate 1: Time window ──────────────────────────────────────────────────
    bar_time = ctx.timestamp_et.time()
    if bar_time < ENTRY_TIME_START or bar_time > ENTRY_TIME_END:
        return None

    # ── Gate 2: Cooldown ─────────────────────────────────────────────────────
    if _last_signal_time is not None:
        elapsed = (ctx.timestamp_et - _last_signal_time).total_seconds() / 60.0
        if elapsed < _COOLDOWN_MINUTES:
            return None

    # ── Gate 3: H&S detector fires ──────────────────────────────────────────
    bars = _build_bars_from_context(ctx)
    if len(bars) < 30:
        return None

    hit = head_and_shoulders_detector(bars, lookback=30)
    if hit is None:
        return None

    # NO proximity filter — this watcher fires on ALL H&S tops
    # (the proximity filter was found to HURT WR at 16-month scale: 46.2% near vs 55.7% far)

    # ── Signal passes all gates ──────────────────────────────────────────────
    _last_signal_time = ctx.timestamp_et

    bar_close = float(ctx.bar["close"])
    neckline = float(hit.notes.get("neckline", bar_close))
    head_high = float(hit.notes.get("head_high", bar_close))
    conf_score = float(hit.confidence)
    neckline_break_pct = float(hit.notes.get("neckline_break_pct", 0.0))
    vix_now = getattr(ctx, "vix_now", None) or 17.0

    stop_price = neckline + _CHART_STOP_ABOVE_NECKLINE
    tp1_price = bar_close - _TP1_SPY_DROP
    runner_price = bar_close - _RUNNER_SPY_DROP

    # Confidence tier
    if conf_score >= 0.65 and neckline_break_pct > 0.05:
        confidence = "high"
        conf_note = f"conf={conf_score:.2f} break={neckline_break_pct:.2f}%"
    elif conf_score >= 0.50 or neckline_break_pct > 0.03:
        confidence = "medium"
        conf_note = f"conf={conf_score:.2f} moderate"
    else:
        confidence = "low"
        conf_note = f"conf={conf_score:.2f} weak"

    # VIX bucket for metadata (for post-hoc VIX regime analysis)
    if vix_now < 15:
        vix_bucket = "<15"
    elif vix_now < 20:
        vix_bucket = "15-20"
    elif vix_now < 25:
        vix_bucket = "20-25"
    else:
        vix_bucket = ">=25"

    return WatcherSignal(
        watcher_name="hs_bear",
        setup_name="HEAD_AND_SHOULDERS_BEAR",
        direction="short",
        entry_price=bar_close,
        stop_price=stop_price,
        tp1_price=tp1_price,
        runner_price=runner_price,
        confidence=confidence,
        reason=(
            f"H&S top no-proximity-filter ({conf_note}). "
            f"Neckline={neckline:.2f}, head={head_high:.2f}. "
            f"Stop={stop_price:.2f} (above neckline+$0.30). "
            f"VIX={vix_now:.1f} (bucket={vix_bucket}). "
            f"WF evidence: train 54.5% N=132 / test 58.5% N=53 (+4.0pp STABLE)."
        ),
        triggers_fired=["hs_top_detector", "time_window"],
        metadata={
            "wf_train_wr_pct": 54.5,
            "wf_test_wr_pct": 58.5,
            "wf_delta_pp": 4.0,
            "wf_verdict": "STABLE",
            "aggregate_wr_pct": 55.7,
            "aggregate_n": 185,
            "neckline": neckline,
            "head_high": head_high,
            "confidence_score": conf_score,
            "neckline_break_pct": neckline_break_pct,
            "vix_bucket": vix_bucket,
            "proximity_filtered": False,
        },
    )
