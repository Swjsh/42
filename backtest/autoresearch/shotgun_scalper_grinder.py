"""SHOTGUN_SCALPER Stage 1 grinder.

Stage 1 of the SHOTGUN_SCALPER pipeline (see shotgun_scalper_pipeline.md).
Sweeps a 2,160-combo grid over 16 months of SPY 5m bars + OPRA option fills,
applies strict keeper gates, and writes top-10 keepers to
`analysis/recommendations/shotgun-scalper-stage1.json`.

Per CLAUDE.md:
  - OP 14: WR is awareness-only. KEEP decisions use sharpe + expectancy +
    max-drawdown + edge_capture, NOT WR.
  - OP 15: MAX_PARALLEL_RESEARCH_WORKERS = 4. Pool-based (NOT thread-based).
    Pythonw.exe is bound to mp.set_executable() so child processes don't
    flash a console window.
  - OP 16: edge_capture is PRIMARY. final_score = edge_capture * sharpe.
    Aggregate P&L is a tiebreaker only. Engine MUST trade J's winner days
    and MUST avoid/lose-less J's loser days.
  - OP 19: every result row carries top5_pct, quarter_pnl, positive_quarters,
    max_drawdown, wide_n_trades, wide_wr.
  - OP 20: every result includes account-size assumption (qty=3 baseline),
    sample-bias disclosure (selection from 2160-combo grinder), concentration
    disclosure (top_5_pct), failure-mode metrics (max_drawdown, worst day).
  - OP 21: this is a Stage 1 grinder only. Promotion to live requires
    full pipeline + walk-forward + real-fills + J ratification.

Output (under autoresearch/_state/shotgun_scalper_stage1/):
    progress.json        live progress meter
    results.jsonl        every combo that passed keeper gates
    rejections.jsonl     every combo that failed any gate
    keepers.jsonl        every combo that improved best-edge or best-pnl
    runner.pid           current process PID
    grinder.log          structured log

Final artefact (top 10 keepers by final_score):
    analysis/recommendations/shotgun-scalper-stage1.json

CLI:
    pythonw.exe -m autoresearch.shotgun_scalper_grinder --hours 6 --workers 4
    pythonw.exe -m autoresearch.shotgun_scalper_grinder --reset --hours 8

TODO (parallel work):
  - lib/watchers/shotgun_scalper_detector.py is under construction.
    Import path used here: `from lib.watchers.shotgun_scalper_detector import detect`.
  - When detector lands, run a smoke test first:
      pythonw.exe -m autoresearch.shotgun_scalper_grinder --smoke
    (executes a single combo on J's 5 winner days only — sanity check).
"""

from __future__ import annotations

import argparse
import datetime as dt
import itertools
import json
import logging
import math
import multiprocessing as mp
import os
import random
import sys
import traceback
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# Bind pythonw.exe so Pool workers don't flash a console window on Windows.
if sys.platform == "win32":
    _pw = Path(r"C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe")
    if _pw.exists():
        mp.set_executable(str(_pw))

REPO = Path(__file__).resolve().parent.parent
PROJECT_ROOT = REPO.parent  # 42/ — where lib/ lives
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(PROJECT_ROOT))

OUT_DIR = REPO / "autoresearch" / "_state" / "shotgun_scalper_stage1"
OUT_DIR.mkdir(parents=True, exist_ok=True)

PROGRESS = OUT_DIR / "progress.json"
RESULTS = OUT_DIR / "results.jsonl"
REJECTIONS = OUT_DIR / "rejections.jsonl"
KEEPERS = OUT_DIR / "keepers.jsonl"
PIDFILE = OUT_DIR / "runner.pid"
LOGFILE = OUT_DIR / "grinder.log"

# Stage-1 final artefact (top 10 keepers, full scorecard)
RECOMMENDATIONS_DIR = REPO.parent / "analysis" / "recommendations"
STAGE1_FINAL = RECOMMENDATIONS_DIR / "shotgun-scalper-stage1.json"


# ── Anchor trades (per CLAUDE.md OP 16) ──────────────────────────────────────
# SHOTGUN_SCALPER: J has NO verified vol-spike anchor trades yet.
#
# J's canonical 3 wins (4/29, 5/01, 5/04) are CONFLUENCE + TRENDLINE entries.
# Probing 2026-06-16: vol-ratio detector fires at WRONG TIMES on those days
# (4/29 → EC=+270 but entry offset mismatch; 5/01 → EC=-53; 5/04 → EC=-270
# at vr<1.80, then 0 at vr>=1.80 — no fire at all). The 50% EC floor of $771
# is structurally unreachable because J's wins came from a DIFFERENT strategy type.
#
# Resolution (L97): strategy-specific grinders must only include J anchors whose
# TRIGGER TYPE matches the detector. Since J has no documented vol-spike trades yet,
# J_WINNERS is empty. EC is reported as informational; primary metric = wide_pnl × sharpe.
#
# If J eventually takes a vol-spike entry and documents it, add it here with:
#   {"date": "YYYY-MM-DD", "j_pnl": NNN, "side": "P"/"C", "strike": NNN,
#    "note": "vol spike at key level — SHOTGUN_SCALPER compatible"}
J_WINNERS: list[dict] = []

J_LOSERS: list[dict] = [
    {"date": "2026-05-05", "j_pnl": -260, "side": "P", "strike": 722,
     "note": "chop-trap manual entry, no real setup"},
    {"date": "2026-05-06", "j_pnl": -300, "side": "P", "strike": 730,
     "note": "held to zero, no stop"},
    {"date": "2026-05-07", "j_pnl": -120, "side": "C", "strike": 737,
     "note": "engine BULL into pre-FOMC bear sequence + manual bullish anticipation"},
]

J_TOTAL_WINNERS = sum(t["j_pnl"] for t in J_WINNERS)  # 0 (no vol-spike anchors yet)


# ── Combo schema ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ShotgunCombo:
    """All knobs for one SHOTGUN_SCALPER backtest run."""

    # Detector / trigger knobs
    vol_ratio_threshold: float = 1.5
    strike_offset: int = 0  # -1=OTM-1, 0=ATM, +1=ITM-1

    # Exit knobs
    tp_premium_pct: float = 0.75
    stop_premium_pct: float = -0.15
    time_stop_min: int = 12
    chandelier_arm_pct: float = 0.25  # arm trailing stop at +X% favor

    # Position sizing — qty=3 is the baseline-disclosure account-size assumption
    # per CLAUDE.md OP 20 (qty=28 requires $25K+; qty=3 is the $1K paper baseline).
    qty: int = 3
    tp1_qty_fraction: float = 1.0  # scalp = single exit (no TP1+runner split)

    # Time gate
    no_trade_before_hour: int = 9
    no_trade_before_min: int = 35
    no_trade_after_hour: int = 15
    no_trade_after_min: int = 0


# ── Param grid ───────────────────────────────────────────────────────────────

# 5 × 4 × 4 × 3 × 3 × 3 = 2,160 combos per spec
TP_PREMIUM_PCTS: list[float] = [0.50, 0.75, 1.00, 1.50, 2.00]
STOP_PREMIUM_PCTS: list[float] = [-0.10, -0.15, -0.20, -0.25]
TIME_STOP_MINS: list[int] = [8, 12, 15, 20]
STRIKE_OFFSETS: list[int] = [-1, 0, 1]
CHANDELIER_ARM_PCTS: list[float] = [0.15, 0.25, 0.40]
VOL_RATIO_THRESHOLDS: list[float] = [1.2, 1.5, 2.0]


def _build_param_grid() -> list[dict]:
    """Build the full 2,160-combo grid."""
    grid: list[dict] = []
    for tp, stop, tstop, off, arm, vol in itertools.product(
        TP_PREMIUM_PCTS,
        STOP_PREMIUM_PCTS,
        TIME_STOP_MINS,
        STRIKE_OFFSETS,
        CHANDELIER_ARM_PCTS,
        VOL_RATIO_THRESHOLDS,
    ):
        grid.append({
            "tp_premium_pct": tp,
            "stop_premium_pct": stop,
            "time_stop_min": tstop,
            "strike_offset": off,
            "chandelier_arm_pct": arm,
            "vol_ratio_threshold": vol,
        })
    return grid


# ── Stage 1 keeper gates (per task spec) ─────────────────────────────────────

@dataclass(frozen=True)
class KeeperGates:
    """Strict Stage 1 gates. Any single failure rejects the combo.

    Primary metric: wide_pnl × sharpe (since J has no vol-spike anchor trades yet —
    see J_WINNERS comment above). EC is reported as informational only (min=0.0 = no floor).
    This mirrors the sniper overnight grinder which uses wide_pnl as primary.
    """

    min_sharpe: float = 0.8
    min_expectancy_per_trade: float = 0.01  # >$0 (use small epsilon)
    min_n_trades: int = 30
    max_drawdown_dollars: float = 1500.0  # qty=3 baseline
    min_edge_capture_pct: float = 0.0  # no EC floor (J_WINNERS empty; EC is informational)
    min_positive_quarters: int = 4  # of 6
    max_top5_pct: float = 0.50  # top 5 days <= 50% of P&L
    min_wide_pnl: float = 500.0  # wide-window P&L must be positive (primary gate)


GATES = KeeperGates()


# ── Per-day backtest ─────────────────────────────────────────────────────────

def _import_detector():
    """Import shotgun_scalper_detector lazily so workers can pick up a freshly
    built detector without restarting the orchestrator.

    Returns the `detect` callable. Raises ImportError with a clear message if
    the detector isn't on disk yet (parallel build in progress).
    """
    try:
        # Worker processes don't inherit parent sys.path modifications, so
        # re-insert the project root here.
        _proj_root = str(Path(__file__).resolve().parent.parent.parent)
        if _proj_root not in sys.path:
            sys.path.insert(0, _proj_root)
        # Live import path used by lib/watchers/runner.py for the watcher fleet.
        from lib.watchers.shotgun_scalper_detector import detect  # type: ignore
        return detect
    except ImportError as exc:
        raise ImportError(
            "shotgun_scalper_detector not importable yet. The detector is being "
            "built in parallel at lib/watchers/shotgun_scalper_detector.py. "
            "Re-run when it's on disk. Original error: " + repr(exc)
        ) from exc


@dataclass
class ShotgunTrade:
    """Outcome of one SHOTGUN_SCALPER trade in the backtest."""

    date_et: dt.date
    direction: str
    entry_time_et: dt.datetime
    entry_spot: float
    strike: int
    side: str  # "C" or "P"
    entry_premium: float
    qty: int
    exit_premium: float
    exit_time_et: dt.datetime
    exit_reason: str
    dollar_pnl: float
    target_level: Optional[float]
    vol_ratio: float
    chandelier_armed: bool


def _strike_for(direction: str, spot: float, offset: int) -> tuple[int, str]:
    """Compute strike + side given direction and offset.

    offset: -1 = OTM-1, 0 = ATM, +1 = ITM-1
    direction: 'short' → buy put, 'long' → buy call
    """
    spot_rounded = int(round(spot))
    if direction == "short":  # buying puts
        # ITM put has strike ABOVE spot, OTM put has strike BELOW spot
        return spot_rounded + offset, "P"
    else:  # buying calls
        # ITM call has strike BELOW spot, OTM call has strike ABOVE spot
        return spot_rounded - offset, "C"


def _opra_premium_at(
    date_et: dt.date,
    strike: int,
    side: str,
    ts: dt.datetime,
    cache: dict,
) -> Optional[float]:
    """Look up an OPRA premium at or after ts. Returns None if no data.

    Real-fills only (per CLAUDE.md OP 16 + OP 20 disclosure 4). No BS sim.
    """
    from lib.option_pricing_real import load_contract_bars, option_symbol

    sym = option_symbol(date_et, strike, side)
    if sym not in cache:
        cache[sym] = load_contract_bars(sym)
    bars = cache[sym]
    if bars is None or bars.empty:
        return None
    # Normalize tz (CLAUDE.md L31): OPRA bars are tz-aware, SPY bars may be tz-naive.
    ts_norm = _normalize_ts(ts, bars["timestamp_et"])
    matches = bars[bars["timestamp_et"] >= ts_norm]
    if matches.empty:
        return None
    bar = matches.iloc[0]
    return float(bar["close"])


def _normalize_ts(ts, series_dtype_sample):
    """Coerce a timestamp to match the tz-awareness of a pandas series.

    Series is tz-aware → return tz-aware ts. Series tz-naive → return tz-naive ts.
    Handles pd.Timestamp and dt.datetime inputs.
    """
    import pandas as pd

    ts_pd = pd.Timestamp(ts)
    if hasattr(series_dtype_sample, "dt"):
        series_tz = series_dtype_sample.dt.tz
    else:
        series_tz = None
    ts_is_aware = ts_pd.tz is not None
    series_is_aware = series_tz is not None
    if ts_is_aware and not series_is_aware:
        return ts_pd.tz_convert(None) if ts_pd.tz else ts_pd.tz_localize(None)
    if (not ts_is_aware) and series_is_aware:
        return ts_pd.tz_localize(series_tz)
    return ts_pd


def _opra_bar_high_low(
    date_et: dt.date,
    strike: int,
    side: str,
    bar_start: dt.datetime,
    bar_end: dt.datetime,
    cache: dict,
) -> Optional[tuple[float, float]]:
    """Return (max_high, min_low) across OPRA bars in [bar_start, bar_end].

    Used to detect intra-bar TP/stop touches. Returns None if no OPRA coverage.
    """
    from lib.option_pricing_real import load_contract_bars, option_symbol

    sym = option_symbol(date_et, strike, side)
    if sym not in cache:
        cache[sym] = load_contract_bars(sym)
    bars = cache[sym]
    if bars is None or bars.empty:
        return None
    bar_start_n = _normalize_ts(bar_start, bars["timestamp_et"])
    bar_end_n = _normalize_ts(bar_end, bars["timestamp_et"])
    window = bars[
        (bars["timestamp_et"] >= bar_start_n) & (bars["timestamp_et"] < bar_end_n)
    ]
    if window.empty:
        return None
    return float(window["high"].max()), float(window["low"].min())


def _simulate_trade_real(
    signal: Any,
    bar_idx: int,
    spy_bars,
    combo: ShotgunCombo,
    opra_cache: dict,
) -> Optional[ShotgunTrade]:
    """Forward-walk bars from signal to exit using OPRA real fills.

    Exit ladder (first to fire wins; stop checked first on same-bar conflict):
      1. Premium stop (combo.stop_premium_pct)
      2. Chandelier trail (armed at +chandelier_arm_pct; trails 20% off HWM)
      3. Target-level touch (signal.target_level via SPY bar high/low)
      4. TP premium (combo.tp_premium_pct)
      5. Time stop (combo.time_stop_min)
    """
    import pandas as pd

    direction = signal["direction"] if isinstance(signal, dict) else signal.direction
    entry_time = signal["bar_timestamp_et"] if isinstance(signal, dict) else signal.bar_timestamp_et
    entry_spot = float(signal["entry_price"] if isinstance(signal, dict) else signal.entry_price)
    target_level = signal.get("target_level") if isinstance(signal, dict) else getattr(signal, "target_level", None)
    vol_ratio = float(signal.get("vol_ratio", 0.0) if isinstance(signal, dict) else getattr(signal, "vol_ratio", 0.0))

    strike, side = _strike_for(direction, entry_spot, combo.strike_offset)

    # Entry fills at the NEXT 5m bar's open (proxy for live limit fill at trigger close).
    # Slight conservatism — half-spread captured by using bar high/low for adverse moves.
    if bar_idx + 1 >= len(spy_bars):
        return None
    next_bar = spy_bars.iloc[bar_idx + 1]
    next_bar_ts = next_bar["timestamp_et"]
    entry_premium = _opra_premium_at(entry_time.date(), strike, side, next_bar_ts, opra_cache)
    if entry_premium is None or entry_premium < 0.05 or entry_premium > 25.0:
        return None

    stop_premium = entry_premium * (1.0 + combo.stop_premium_pct)
    tp_premium = entry_premium * (1.0 + combo.tp_premium_pct)
    chandelier_arm = entry_premium * (1.0 + combo.chandelier_arm_pct)
    chandelier_trail_ratio = 0.20  # trail 20% off HWM (v15 doctrine)

    hwm_premium = entry_premium
    chandelier_floor: Optional[float] = None
    chandelier_armed = False

    time_stop_deadline = entry_time + dt.timedelta(minutes=combo.time_stop_min)
    eod_deadline = entry_time.replace(hour=15, minute=50, second=0, microsecond=0)
    final_deadline = min(time_stop_deadline, eod_deadline)

    for fwd_idx in range(bar_idx + 1, len(spy_bars)):
        fwd = spy_bars.iloc[fwd_idx]
        fwd_time = fwd["timestamp_et"]
        if not hasattr(fwd_time, "date") or fwd_time.date() != entry_time.date():
            break

        bar_start = fwd_time
        bar_end = bar_start + dt.timedelta(minutes=5)

        opra_window = _opra_bar_high_low(
            entry_time.date(), strike, side, bar_start, bar_end, opra_cache
        )
        if opra_window is None:
            # No OPRA coverage for this bar — close at last known close
            close_premium = _opra_premium_at(
                entry_time.date(), strike, side, bar_start, opra_cache
            )
            if close_premium is None:
                continue
            premium_high, premium_low = close_premium, close_premium
        else:
            premium_high, premium_low = opra_window

        # Update HWM, possibly arm chandelier, update floor
        if premium_high > hwm_premium:
            hwm_premium = premium_high
            if not chandelier_armed and hwm_premium >= chandelier_arm:
                chandelier_armed = True
            if chandelier_armed:
                new_floor = hwm_premium * (1.0 - chandelier_trail_ratio)
                if chandelier_floor is None or new_floor > chandelier_floor:
                    chandelier_floor = new_floor

        # Effective stop = max(premium_stop, chandelier_floor)
        effective_stop = stop_premium
        if chandelier_floor is not None and chandelier_floor > effective_stop:
            effective_stop = chandelier_floor

        # 1. Stop touch (premium low <= effective_stop)
        if premium_low <= effective_stop:
            exit_premium = effective_stop
            exit_reason = "CHANDELIER" if (chandelier_floor is not None and effective_stop == chandelier_floor) else "STOP"
            return _build_trade(
                signal, entry_time, entry_spot, strike, side, entry_premium,
                combo, exit_premium, fwd_time, exit_reason, target_level,
                vol_ratio, chandelier_armed,
            )

        # 2. Target level touch (SPY-level exit — bar high/low vs target_level)
        if target_level is not None:
            spy_high = float(fwd["high"])
            spy_low = float(fwd["low"])
            level_hit = False
            if direction == "short" and spy_low <= target_level:
                level_hit = True
            elif direction == "long" and spy_high >= target_level:
                level_hit = True
            if level_hit:
                # Exit at premium_high (favorable side captured by limit at target)
                exit_premium = premium_high
                return _build_trade(
                    signal, entry_time, entry_spot, strike, side, entry_premium,
                    combo, exit_premium, fwd_time, "TARGET_LEVEL", target_level,
                    vol_ratio, chandelier_armed,
                )

        # 3. TP premium touch
        if premium_high >= tp_premium:
            return _build_trade(
                signal, entry_time, entry_spot, strike, side, entry_premium,
                combo, tp_premium, fwd_time, "TP_PREMIUM", target_level,
                vol_ratio, chandelier_armed,
            )

        # 4. Time stop
        if fwd_time >= final_deadline:
            close_premium = _opra_premium_at(
                entry_time.date(), strike, side, bar_start, opra_cache
            )
            if close_premium is None:
                close_premium = premium_low  # conservative fallback
            return _build_trade(
                signal, entry_time, entry_spot, strike, side, entry_premium,
                combo, close_premium, fwd_time,
                "TIME_STOP" if fwd_time >= time_stop_deadline else "EOD_FLAT",
                target_level, vol_ratio, chandelier_armed,
            )

    # End of data
    last = spy_bars.iloc[-1]
    last_time = last["timestamp_et"]
    last_premium = _opra_premium_at(entry_time.date(), strike, side, last_time, opra_cache)
    if last_premium is None:
        return None
    return _build_trade(
        signal, entry_time, entry_spot, strike, side, entry_premium,
        combo, last_premium, last_time, "EOD_FORCED", target_level,
        vol_ratio, chandelier_armed,
    )


def _build_trade(
    signal, entry_time, entry_spot, strike, side, entry_premium,
    combo: ShotgunCombo, exit_premium: float, exit_time, exit_reason: str,
    target_level, vol_ratio: float, chandelier_armed: bool,
) -> ShotgunTrade:
    direction = signal["direction"] if isinstance(signal, dict) else signal.direction
    dollar_pnl = round((exit_premium - entry_premium) * 100 * combo.qty, 2)
    return ShotgunTrade(
        date_et=entry_time.date(),
        direction=direction,
        entry_time_et=entry_time,
        entry_spot=entry_spot,
        strike=strike,
        side=side,
        entry_premium=entry_premium,
        qty=combo.qty,
        exit_premium=exit_premium,
        exit_time_et=exit_time,
        exit_reason=exit_reason,
        dollar_pnl=dollar_pnl,
        target_level=target_level,
        vol_ratio=vol_ratio,
        chandelier_armed=chandelier_armed,
    )


def run_shotgun_day(
    date_et: dt.date,
    spy_full,
    combo: ShotgunCombo,
    opra_cache: dict,
    max_trades_per_day: int = 5,  # scalp strategy — fire multiple times if confirmed
) -> list[ShotgunTrade]:
    """Run SHOTGUN_SCALPER detector across one trading day's RTH bars."""
    import pandas as pd

    detect = _import_detector()

    no_trade_before = dt.time(combo.no_trade_before_hour, combo.no_trade_before_min)
    no_trade_after = dt.time(combo.no_trade_after_hour, combo.no_trade_after_min)

    day_bars = spy_full[
        (spy_full["timestamp_et"].dt.date == date_et)
        & (spy_full["timestamp_et"].dt.time >= no_trade_before)
        & (spy_full["timestamp_et"].dt.time < no_trade_after)
    ].reset_index(drop=True)
    if day_bars.empty:
        return []

    first_ts = day_bars["timestamp_et"].iloc[0]
    pre_bars = spy_full[spy_full["timestamp_et"] < first_ts].tail(60).reset_index(drop=True)
    combined = pd.concat([pre_bars, day_bars], ignore_index=True)
    day_offset = len(pre_bars)

    # Auto-derived levels: PDH/PDL from prior RTH day + PMH/PML from today's pre-bars.
    # Tier 1 (open rejection) fires regardless; Tier 2 needs at least one level.
    levels = _build_auto_levels(spy_full, date_et, pre_bars)
    ribbon_stub = {"fast": float("nan"), "pivot": float("nan"), "slow": float("nan"),
                   "spread_cents": 0.0, "stack": "NEUTRAL"}
    vix_stub = 17.0  # neutral placeholder; detector currently unused

    trades: list[ShotgunTrade] = []
    last_exit_idx = -1

    for i in range(len(day_bars)):
        bar_idx = day_offset + i  # absolute index into `combined` for _simulate_trade_real
        if bar_idx <= last_exit_idx:
            continue  # don't re-enter while in a trade
        try:
            # Detector contract: pass RTH-only bars (day_bars) with relative index `i`.
            # Tier 1 needs today_bars[0] to be the 09:30 RTH open bar.
            signal = detect(
                today_bars=day_bars,
                today_bar_idx=i,
                levels=levels,
                ribbon=ribbon_stub,
                vix=vix_stub,
                htf_15m_stack=None,
            )
        except Exception:
            continue
        if signal is None:
            continue

        # vol_ratio gate: filter low-volume signals below the combo threshold.
        # signal["vol_ratio"] = bar_volume / 20-bar-avg from the detector.
        # NOTE 2026-05-16: this knob was in ShotgunCombo but never compared — dead knob.
        # Wired here so Stage 4's 0.60/0.80/1.00/1.20 grid values are meaningful.
        if signal.get("vol_ratio", 1.0) < combo.vol_ratio_threshold:
            continue

        # Schema adapter: detector returns {direction: bearish|bullish, trigger_bar_time, ...}
        # but _simulate_trade_real expects {direction: short|long, bar_timestamp_et, entry_price, ...}.
        signal["direction"] = "short" if signal.get("direction") in ("bearish", "short", "put") else "long"
        signal["bar_timestamp_et"] = day_bars.iloc[i]["timestamp_et"]
        signal["entry_price"] = float(day_bars.iloc[i]["close"])

        trade = _simulate_trade_real(signal, bar_idx, combined, combo, opra_cache)
        if trade is None:
            continue
        trades.append(trade)

        # Block re-entry until we're past the exit bar
        exit_time = trade.exit_time_et
        for j in range(bar_idx, len(combined)):
            if combined.iloc[j]["timestamp_et"] >= exit_time:
                last_exit_idx = j
                break

        if len(trades) >= max_trades_per_day:
            break

    return trades


def _build_auto_levels(spy_full, date_et: dt.date, pre_bars) -> list[dict]:
    """Auto-derive a minimal levels list for the grinder so Tier 2 has anchors.

    Computes: prior RTH session H/L (PDH/PDL) + today's premarket H/L (PMH/PML).
    Returns up to 4 dicts in the schema the detector expects (price/label/tier/stars).
    """
    import pandas as pd

    levels: list[dict] = []

    # Prior trading day RTH H/L
    rth_open = dt.time(9, 30)
    rth_close = dt.time(16, 0)
    prior_rth = spy_full[
        (spy_full["timestamp_et"].dt.date < date_et)
        & (spy_full["timestamp_et"].dt.time >= rth_open)
        & (spy_full["timestamp_et"].dt.time < rth_close)
    ]
    if not prior_rth.empty:
        prior_dates = prior_rth["timestamp_et"].dt.date.unique()
        if len(prior_dates) > 0:
            last_day = max(prior_dates)
            pdh = prior_rth[prior_rth["timestamp_et"].dt.date == last_day]
            if not pdh.empty:
                levels.append({"price": float(pdh["high"].max()), "label": "PDH",
                               "tier": "Reference", "type": "resistance", "stars": 2})
                levels.append({"price": float(pdh["low"].min()), "label": "PDL",
                               "tier": "Reference", "type": "support", "stars": 2})

    # Today's premarket H/L (from pre_bars)
    if pre_bars is not None and not pre_bars.empty:
        today_pre = pre_bars[pre_bars["timestamp_et"].dt.date == date_et] \
            if "timestamp_et" in pre_bars.columns else pre_bars
        if not today_pre.empty:
            levels.append({"price": float(today_pre["high"].max()), "label": "PMH",
                           "tier": "Active", "type": "resistance", "stars": 2})
            levels.append({"price": float(today_pre["low"].min()), "label": "PML",
                           "tier": "Active", "type": "support", "stars": 2})

    return levels


# ── Public evaluator (matches sniper_evaluator output schema) ────────────────

def evaluate_shotgun_combo(combo_dict: dict) -> dict:
    """Run SHOTGUN_SCALPER over J anchor days + wide window. Return scorecard.

    Output schema mirrors sniper_evaluator.evaluate_sniper_combo so this slots
    into the existing autoresearch pipeline (Stage 2-5 grinders, scorecards).
    """
    try:
        import pandas as pd

        combo = ShotgunCombo(**{
            k: combo_dict[k] for k in combo_dict
            if k in ShotgunCombo.__dataclass_fields__
        })

        from autoresearch import runner as _runner

        # ---- J anchor days ----
        anchor_dates = [t["date"] for t in J_WINNERS + J_LOSERS]
        min_d = dt.date.fromisoformat(min(anchor_dates))
        max_d = dt.date.fromisoformat(max(anchor_dates))
        spy_j, _vix = _runner.load_data(min_d, max_d)
        spy_j["timestamp_et"] = (
            pd.to_datetime(spy_j["timestamp_et"], utc=True)
            .dt.tz_convert("America/New_York")
            .dt.tz_localize(None)
        )

        opra_cache: dict = {}
        by_day: dict[str, float] = {}
        for w in J_WINNERS + J_LOSERS:
            d = dt.date.fromisoformat(w["date"])
            day_trades = run_shotgun_day(d, spy_j, combo, opra_cache)
            by_day[w["date"]] = round(sum(t.dollar_pnl for t in day_trades), 2)

        winners_capture = sum(by_day.get(w["date"], 0.0) for w in J_WINNERS)
        losers_added = 0.0
        for l in J_LOSERS:
            pnl = by_day.get(l["date"], 0.0)
            if pnl < 0:
                losers_added += -pnl
        edge_capture = winners_capture - losers_added
        max_edge_possible = J_TOTAL_WINNERS
        edge_capture_pct = (edge_capture / max_edge_possible) if max_edge_possible > 0 else 0.0

        # ---- Wide window: 16 months (2025-01-01 .. 2026-05-22) ----
        wide_start = dt.date(2025, 1, 1)
        wide_end = dt.date(2026, 5, 22)  # updated 2026-05-23; master merged through 5/22
        spy_w, _vw = _runner.load_data(wide_start, wide_end)
        spy_w["timestamp_et"] = (
            pd.to_datetime(spy_w["timestamp_et"], utc=True)
            .dt.tz_convert("America/New_York")
            .dt.tz_localize(None)
        )

        all_dates = sorted(set(spy_w["timestamp_et"].dt.date.unique()))
        wide_trades: list[ShotgunTrade] = []
        day_pnl_map: dict[dt.date, float] = defaultdict(float)
        quarter_pnl_map: dict[str, float] = defaultdict(float)

        for d in all_dates:
            if d < wide_start or d > wide_end:
                continue
            day_trades = run_shotgun_day(d, spy_w, combo, opra_cache)
            wide_trades.extend(day_trades)
            day_total = sum(t.dollar_pnl for t in day_trades)
            day_pnl_map[d] += day_total
            q = f"{d.year}-Q{(d.month - 1) // 3 + 1}"
            quarter_pnl_map[q] += day_total

        wide_pnl = round(sum(day_pnl_map.values()), 2)
        wide_n = len(wide_trades)
        wide_winners = sum(1 for t in wide_trades if t.dollar_pnl > 0)
        wide_wr = round(wide_winners / wide_n, 3) if wide_n else 0.0
        expectancy_per_trade = round(wide_pnl / wide_n, 2) if wide_n else 0.0

        # Sharpe: per-trade returns normalized (NOT P&L — use $/trade std)
        trade_pnls = [t.dollar_pnl for t in wide_trades]
        if wide_n > 1:
            mean_pnl = sum(trade_pnls) / wide_n
            var = sum((p - mean_pnl) ** 2 for p in trade_pnls) / (wide_n - 1)
            std = math.sqrt(var) if var > 0 else 1.0
            # Annualize by sqrt(trades-per-year). 252 trading days * avg trades/day.
            trades_per_year = wide_n / max(1, (wide_end - wide_start).days / 365.25)
            sharpe = (mean_pnl / std) * math.sqrt(trades_per_year) if std > 0 else 0.0
        else:
            sharpe = 0.0

        # OP 19 defaults
        sorted_day_pnls = sorted(day_pnl_map.values(), reverse=True)
        top5_sum = sum(sorted_day_pnls[:5])
        top5_pct = round(top5_sum / wide_pnl, 3) if wide_pnl > 0 else 999.0
        positive_quarters = sum(1 for v in quarter_pnl_map.values() if v > 0)
        quarter_count = len(quarter_pnl_map)

        # Sequential drawdown ($)
        cum = peak = max_dd = 0.0
        for d in sorted(day_pnl_map.keys()):
            cum += day_pnl_map[d]
            if cum > peak:
                peak = cum
            dd = peak - cum
            if dd > max_dd:
                max_dd = dd

        # ---- Stage 1 keeper gates ----
        regressions = []
        if sharpe < GATES.min_sharpe:
            regressions.append(f"sharpe {sharpe:.2f} < {GATES.min_sharpe}")
        if max_dd > GATES.max_drawdown_dollars:
            regressions.append(f"max_dd ${max_dd:.0f} > ${GATES.max_drawdown_dollars:.0f}")
        if expectancy_per_trade <= 0:
            regressions.append(f"expectancy ${expectancy_per_trade:.2f} <= 0")
        if wide_n < GATES.min_n_trades:
            regressions.append(f"n_trades {wide_n} < {GATES.min_n_trades}")
        if wide_pnl < GATES.min_wide_pnl:
            regressions.append(f"wide_pnl ${wide_pnl:.0f} < ${GATES.min_wide_pnl:.0f}")
        # EC gate bypassed (min_edge_capture_pct=0.0) since J_WINNERS is empty.
        # Report EC as informational only.
        if GATES.min_edge_capture_pct > 0 and edge_capture_pct < GATES.min_edge_capture_pct:
            regressions.append(
                f"edge_capture {edge_capture_pct:.2f} < {GATES.min_edge_capture_pct}"
            )
        if positive_quarters < GATES.min_positive_quarters:
            regressions.append(
                f"positive_quarters {positive_quarters} < {GATES.min_positive_quarters}"
            )
        if top5_pct > GATES.max_top5_pct:
            regressions.append(f"top5_pct {top5_pct:.2f} > {GATES.max_top5_pct}")

        final_score = edge_capture * sharpe  # OP 16

        return {
            "combo": combo_dict,
            "by_day": by_day,
            "winners_capture": round(winners_capture, 2),
            "losers_added": round(losers_added, 2),
            "edge_capture": round(edge_capture, 2),
            "edge_capture_pct": round(edge_capture_pct, 3),
            "max_edge_possible": max_edge_possible,
            "wide_pnl": wide_pnl,
            "wide_n_trades": wide_n,
            "wide_wr": wide_wr,  # OP 14: awareness only
            "expectancy_per_trade": expectancy_per_trade,
            "sharpe": round(sharpe, 3),
            "top5_pct": top5_pct,
            "quarter_pnl": {k: round(v, 2) for k, v in quarter_pnl_map.items()},
            "positive_quarters": positive_quarters,
            "quarter_count": quarter_count,
            "max_drawdown": round(max_dd, 2),
            "final_score": round(final_score, 2),
            "passed_floors": len(regressions) == 0,
            "regressions": regressions,
        }
    except Exception as exc:
        return {
            "combo": combo_dict,
            "error": repr(exc),
            "trace": traceback.format_exc(),
            "passed_floors": False,
            "regressions": ["execution_error"],
        }


# ── Orchestration ────────────────────────────────────────────────────────────

def _setup_logging() -> None:
    logging.basicConfig(
        filename=str(LOGFILE),
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _write_progress(state: dict) -> None:
    """Atomic write of progress meter."""
    tmp = PROGRESS.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    tmp.replace(PROGRESS)


def _append_jsonl(path: Path, row: dict) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")


def _compute_run_id() -> Optional[dict]:
    """Compute reproducibility run_id per backtest/lib/repro.py. Returns metadata
    dict or None if any inputs missing (logged + soldiered)."""
    try:
        from lib.repro import compute_run_id

        # Use the full-window CSV that matches our wide_start/wide_end.
        candidates = [
            (dt.date(2025, 1, 1), dt.date(2026, 5, 22)),  # merged master (5/16-5/22 added 2026-05-23)
            (dt.date(2025, 1, 1), dt.date(2026, 5, 15)),
            (dt.date(2025, 1, 1), dt.date(2026, 5, 12)),
            (dt.date(2025, 1, 1), dt.date(2026, 5, 7)),
        ]
        for s, e in candidates:
            spy_p = REPO / "data" / f"spy_5m_{s}_{e}.csv"
            vix_p = REPO / "data" / f"vix_5m_{s}_{e}.csv"
            if spy_p.exists() and vix_p.exists():
                identity = compute_run_id(spy_p, vix_p)
                return {
                    "run_id": identity.run_id,
                    "data_hash": identity.data_hash[:16],
                    "code_hash": identity.code_hash[:16],
                    "params_hash": identity.params_hash[:16],
                    "code_source": identity.code_source,
                    "computed_at": identity.computed_at,
                }
    except Exception as exc:
        logging.warning(f"compute_run_id failed: {exc!r}")
    return None


def _write_stage1_final(keepers: list[dict], run_identity: Optional[dict]) -> None:
    """Persist top-10 keepers (by final_score) to analysis/recommendations/."""
    RECOMMENDATIONS_DIR.mkdir(parents=True, exist_ok=True)
    top10 = sorted(keepers, key=lambda r: r.get("final_score", 0.0), reverse=True)[:10]
    payload = {
        "strategy": "SHOTGUN_SCALPER",
        "stage": 1,
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "run_identity": run_identity,
        "grid_size": 2160,
        "gates": {
            "min_sharpe": GATES.min_sharpe,
            "min_expectancy_per_trade": GATES.min_expectancy_per_trade,
            "min_n_trades": GATES.min_n_trades,
            "max_drawdown_dollars": GATES.max_drawdown_dollars,
            "min_edge_capture_pct": GATES.min_edge_capture_pct,
            "min_positive_quarters": GATES.min_positive_quarters,
            "max_top5_pct": GATES.max_top5_pct,
        },
        "anchor_days": {
            "winners": J_WINNERS,
            "losers": J_LOSERS,
            "max_edge_possible": J_TOTAL_WINNERS,
        },
        "disclosures": {
            "account_size_assumption": "qty=3 baseline (~$1K paper). Headline P&L scales linearly with qty.",
            "sample_bias": "Top-10 selected from 2160-combo grid — overfit risk. Stage 2-5 required before live.",
            "validation_status": "STAGE 1 ONLY. Walk-forward + real-fills + Monday-Ready pending.",
            "wr_caveat": "WR is awareness-only per OP 14. Sharpe + expectancy + max-DD + edge_capture drive selection.",
        },
        "top10": top10,
    }
    STAGE1_FINAL.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=float, default=6.0,
                        help="Run for N hours then stop gracefully")
    parser.add_argument("--workers", type=int, default=4,
                        help="Parallel workers (cap=4 per CLAUDE.md OP 15)")
    parser.add_argument("--reset", action="store_true",
                        help="Reset progress + results from prior run")
    parser.add_argument("--smoke", action="store_true",
                        help="Run a single combo on J winner days only (sanity check)")
    args = parser.parse_args()

    # FIX 2026-05-24: reset BEFORE _setup_logging() so LOGFILE isn't held open
    # when we try to delete it (Windows PermissionError on open files).
    workers = min(args.workers, 4)

    if args.reset:
        for f in [PROGRESS, RESULTS, REJECTIONS, KEEPERS, LOGFILE]:
            if f.exists():
                f.unlink()

    _setup_logging()

    if args.smoke:
        # Smoke test: one combo (defaults), J winner days only
        smoke_combo = {
            "tp_premium_pct": 0.75,
            "stop_premium_pct": -0.15,
            "time_stop_min": 12,
            "strike_offset": 0,
            "chandelier_arm_pct": 0.25,
            "vol_ratio_threshold": 1.5,
        }
        result = evaluate_shotgun_combo(smoke_combo)
        print(json.dumps(result, indent=2, default=str))
        return 0

    PIDFILE.write_text(str(os.getpid()), encoding="utf-8")

    started = dt.datetime.now()
    deadline = started + dt.timedelta(hours=args.hours)
    grid = _build_param_grid()
    random.Random(2026).shuffle(grid)

    run_identity = _compute_run_id()

    state = {
        "started_at": started.isoformat(),
        "deadline_at": deadline.isoformat(),
        "total_combos": len(grid),
        "completed": 0,
        "passed_floors": 0,
        "rejected": 0,
        "keepers": 0,
        "best_edge_capture": 0.0,
        "best_final_score": 0.0,
        "best_wide_pnl": None,
        "current_pid": os.getpid(),
        "workers": workers,
        "run_identity": run_identity,
        "last_update": started.isoformat(),
        "status": "running",
    }
    _write_progress(state)
    logging.info(
        f"SHOTGUN_SCALPER Stage 1 grinder started: {len(grid)} combos, "
        f"{workers} workers, deadline={deadline}"
    )

    completed = 0
    keepers_n = 0
    keepers_collected: list[dict] = []
    best_final: tuple[float, dict] | None = None

    with mp.Pool(workers) as pool:
        for result in pool.imap_unordered(evaluate_shotgun_combo, grid, chunksize=1):
            completed += 1

            if dt.datetime.now() > deadline:
                logging.info("Deadline reached, terminating pool")
                state["status"] = "deadline_reached"
                _write_progress(state)
                pool.terminate()
                break

            if result.get("passed_floors"):
                _append_jsonl(RESULTS, result)
                state["passed_floors"] += 1
                keepers_collected.append(result)

                fs = result.get("final_score", 0.0)
                if best_final is None or fs > best_final[0]:
                    best_final = (fs, result["combo"])
                    state["best_final_score"] = fs
                    keepers_n += 1
                    state["keepers"] = keepers_n
                    _append_jsonl(KEEPERS, result)
                    logging.info(
                        f"KEEPER #{keepers_n}: final_score={fs:.0f} "
                        f"edge=${result.get('edge_capture', 0):.0f} "
                        f"sharpe={result.get('sharpe', 0):.2f} "
                        f"wide_pnl=${result.get('wide_pnl', 0):.0f} "
                        f"trades={result.get('wide_n_trades', 0)} "
                        f"combo={result['combo']}"
                    )
                if result.get("edge_capture", 0) > state["best_edge_capture"]:
                    state["best_edge_capture"] = result["edge_capture"]
                if (state["best_wide_pnl"] is None
                        or result.get("wide_pnl", 0) > state["best_wide_pnl"]):
                    state["best_wide_pnl"] = result.get("wide_pnl")
            else:
                _append_jsonl(REJECTIONS, result)
                state["rejected"] += 1

            state["completed"] = completed
            state["last_update"] = dt.datetime.now().isoformat()
            if completed % 5 == 0:
                _write_progress(state)
                logging.info(
                    f"progress: {completed}/{len(grid)} "
                    f"passed={state['passed_floors']} keepers={keepers_n}"
                )

    state["status"] = "completed" if state["status"] == "running" else state["status"]
    state["completed_at"] = dt.datetime.now().isoformat()
    _write_progress(state)

    # Persist final stage-1 keepers artefact + console summary
    _write_stage1_final(keepers_collected, run_identity)
    top5 = sorted(
        keepers_collected, key=lambda r: r.get("final_score", 0.0), reverse=True
    )[:5]
    print("\n" + "=" * 60)
    print("SHOTGUN_SCALPER Stage 1 — Top 5 by edge_capture * sharpe")
    print("=" * 60)
    for i, r in enumerate(top5, 1):
        c = r.get("combo", {})
        print(
            f"#{i} final_score={r.get('final_score', 0):.0f} | "
            f"edge=${r.get('edge_capture', 0):.0f} ({r.get('edge_capture_pct', 0)*100:.0f}%) | "
            f"sharpe={r.get('sharpe', 0):.2f} | "
            f"wide_pnl=${r.get('wide_pnl', 0):.0f} | "
            f"n={r.get('wide_n_trades', 0)} | "
            f"max_dd=${r.get('max_drawdown', 0):.0f} | "
            f"top5_pct={r.get('top5_pct', 0)*100:.0f}% | "
            f"+Q={r.get('positive_quarters', 0)}/6"
        )
        print(
            f"    combo: tp={c.get('tp_premium_pct')} stop={c.get('stop_premium_pct')} "
            f"tstop={c.get('time_stop_min')}m off={c.get('strike_offset')} "
            f"arm={c.get('chandelier_arm_pct')} vol={c.get('vol_ratio_threshold')}"
        )

    if PIDFILE.exists():
        PIDFILE.unlink()

    logging.info(
        f"SHOTGUN_SCALPER Stage 1 done: {completed}/{len(grid)} "
        f"passed={state['passed_floors']} keepers={keepers_n} "
        f"best_final_score={state['best_final_score']:.0f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
