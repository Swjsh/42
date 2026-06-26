"""DTE-EXPANSION SIM — does the dead 0DTE long-directional library RESURRECT at 1-2DTE?

THE THESIS (C3/L58 theta wall): ~64 long-directional families + the marginal survivors
all die at 0DTE because theta+delta convert a real SPY-PRICE edge into negative OPTION
expectancy — the whole extrinsic is gone by 16:00. That wall is EXPIRY-SPECIFIC: at
1DTE/2DTE the per-day theta is a fraction of 0DTE's, so a directional signal has ROOM for
the move to pay before decay eats it. If the SAME byte-for-byte detector turns positive at
1-2DTE, the dead library resurrects at a new expiry. The tradeoff this sim PRICES HONESTLY:
longer DTE = OVERNIGHT GAP RISK (held through the close-to-open gap; the stop can gap
THROUGH its level) + lower gamma/leverage.

WHAT THIS REUSES BYTE-FOR-BYTE (no edits to production):
  * The DETECTOR — imported verbatim from the 0DTE edge-hunt modules
    (``_edgehunt_vwap_continuation.detect_signals`` = the live vwap_continuation_watcher
    port; plus representative DEAD families via their ``_edgehunt_*`` detectors). NO
    re-implementation.
  * The OPRA FILL CONVENTIONS — copied verbatim from ``lib.option_pricing_real`` /
    ``lib.simulator_real`` (OptionBar dataclass; bar_at_or_after; entry = NEXT 5-min bar
    open after the trigger bar + entry_slippage; min hold 5 min; stop touched ->
    stop_premium; market exits -> bar.close - exit_slippage; conservative same-bar
    stop-before-TP). The ONLY divergences from simulator_real.py are the two things that
    DEFINE multi-DTE and which simulator_real.py hard-codes to 0DTE:
       (1) the option SYMBOL is built from the EXPIRY date (T+1 / T+2), not entry_time.date();
       (2) the loop does NOT force-flatten at the day-T 15:50 time stop — an un-stopped
           position is HELD OVERNIGHT to expiry settlement.
    simulator_real.py is NOT imported for the walk (it would 0DTE-flatten) and is NOT
    edited. Its conventions are mirrored here exactly so fills do not drift (C14).

DATA REALITY (verified): every CSV in backtest/data/options_{1,2}dte/ contains bars for the
ENTRY day T ONLY (1DTE file SPY{exp}... holds day-T = exp-1 bars; 2DTE = exp-2). There are
NO expiry-day option bars in the cache. CONSEQUENCE, modeled honestly: the position can be
MANAGED intraday on day T (real option bars), then it is HELD through the overnight gap and
SETTLED at EXPIRY INTRINSIC using the SPY close on expiry day (real SPY 5m). No synthetic
mid-life option marks are invented — every option price used is a real fetched bar EXCEPT
the terminal settlement, which is pure intrinsic (max(0, ...)) at a real SPY price.

OVERNIGHT GAP (modeled explicitly, overnight_gap_modeled=true):
  * Day-T intraday stops/TP act ONLY on day-T option bars (causal, <= current bar).
  * If NOT exited on day T, the position survives the close. At the T+1 (or T+2) open we
    mark the UNDERLYING at the real SPY open. If the close-to-open gap has carried SPY
    THROUGH the chart stop, the position is closed at the GAPPED-OPEN intrinsic (the stop
    gapped through — you do NOT get filled at your stop level), reason GAP_THROUGH_STOP.
  * Otherwise it rides to expiry settlement = intrinsic at the expiry-day SPY close.

NO LOOK-AHEAD: signal fires on day-T trigger bar close; entry = next day-T bar open. Day-T
management reads only day-T bars at-or-before the current bar. T+1/T+2 decisions read only
the T+1/T+2 open then close (in order). Strike picker mirrors production (offset sign per
simulator_real.py L357-364: puts strike=atm-offset, calls strike=atm+offset; offset<0=ITM).

OUTPUT: per-family, per-(strike,stop) cell metrics at 0DTE / 1DTE / 2DTE side by side
(per-trade expectancy, OOS split, positive_quarters, top5_day_pct, overnight-gap stats,
risk-adjusted exp/std). The point: which expiry, if any, flips the SAME signal positive.

Pure Python, $0. No live orders. Run:
  backtest/.venv/Scripts/python.exe backtest/autoresearch/_dte_expansion_sim.py [--smoke] [--family vwap_continuation]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from autoresearch import runner as ar_runner  # noqa: E402
from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    build_day_contexts,
    _strike_from_spot,
    Signal,
    DayCtx,
)
# DETECTOR reused byte-for-byte (live vwap_continuation_watcher port).
from autoresearch._edgehunt_vwap_continuation import (  # noqa: E402
    detect_signals as detect_vwap_continuation,
    _normalize_spy,
    _align_vix,
)
# DEAD-FAMILY detectors reused byte-for-byte from the infinite-ammo discovery suite
# (these are the 0DTE-theta-killed long-directional families: ORB-continuation and
# morning/intraday momentum). They are imported verbatim — NOT re-implemented.
from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    detect_orb_rvol,
    detect_intraday_momentum,
    detect_gap_fade,
    detect_power_hour,
    detect_vwap_pullback,
)
# #2 vwap_reclaim_failed_break — long-premium directional 0DTE edge, the SAME -8% percent
# stop -> dollar-anchored-stop lever target as #1. Detector reused BYTE-FOR-BYTE (no edit to
# the detector body; same Signal(bar_idx, side, stop_level, note) contract as #1's detector,
# so it flows through the identical run_cell + simulate_dte_trade machinery).
from autoresearch._sub_struct_vwap_reclaim_failed_break import (  # noqa: E402
    detect_signals as detect_vwap_reclaim_failed_break,
)
# Ribbon is required by power_hour (reads the EMA-stack state at PH_START). Built once
# in main() from the normalized SPY close series, byte-for-byte as _dte_signal_days.py
# (compute_ribbon(pd.Series(spy["close"].values))).
from lib.ribbon import compute_ribbon  # noqa: E402
# OPRA fill-convention primitives reused verbatim (NOT re-implemented).
from lib.option_pricing_real import OptionBar, option_symbol  # noqa: E402

OUT = ROOT / "analysis" / "recommendations" / "dte-expansion.json"

# ── DTE cache dirs (entry-day-only bars; filename encodes EXPIRY) ───────────────
DTE_DIRS = {
    0: REPO / "data" / "options",        # 0DTE baseline (same-day expiry)
    1: REPO / "data" / "options_1dte",
    2: REPO / "data" / "options_2dte",
}

# Per-DTE in-memory loader cache (mirrors option_pricing_real._CONTRACT_BAR_CACHE,
# but keyed per-DTE because the same OCC symbol can exist in 0/1/2DTE dirs).
_DTE_BAR_CACHE: dict[tuple[int, str], Optional[pd.DataFrame]] = {}

DEFAULT_ENTRY_SLIPPAGE = 0.02   # byte-for-byte simulator_real.DEFAULT_ENTRY_SLIPPAGE
DEFAULT_EXIT_SLIPPAGE = 0.02    # byte-for-byte simulator_real.DEFAULT_EXIT_SLIPPAGE

RTH_CLOSE = dt.time(16, 0)
TIME_STOP_ET = dt.time(15, 50)  # day-T intraday TP/stop checks still respect tape close

OOS_YEAR = 2026

# Candidate-edge bar (identical thresholds to the 0DTE edge-hunt modules).
BAR_OOS_EXP = 0.0
BAR_POS_Q = 4
BAR_TOP5 = 200.0
BAR_N = 20

STRIKE_OFFSETS = [-2, -1, 0, 1, 2]            # neg=ITM, pos=OTM (verified)
PREMIUM_STOPS = [-0.08, -0.20, -0.50, -0.99]  # -0.99 = chart-stop-only
QTY = 3

# L173 OOS-alone drop-top5: need strictly MORE than 5 OOS observations to drop the 5
# best and keep a non-empty remainder. Mirrors fraud_gates.MIN_OOS_TO_DROP_TOP5.
MIN_OOS_TO_DROP_TOP5 = 5


# ─────────────────────────────────────────────────────────────────────────────
# DTE OPRA LOADER (mirrors option_pricing_real.load_contract_bars + bar_at_or_after,
# pointed at the per-DTE cache dir; OptionBar + parse + tz-normalize identical)
# ─────────────────────────────────────────────────────────────────────────────
def load_dte_contract_bars(symbol: str, dte: int) -> Optional[pd.DataFrame]:
    key = (dte, symbol)
    if key in _DTE_BAR_CACHE:
        return _DTE_BAR_CACHE[key]
    path = DTE_DIRS[dte] / f"{symbol}.csv"
    if not path.exists():
        _DTE_BAR_CACHE[key] = None
        return None
    df = pd.read_csv(path)
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"])
    if df["timestamp_et"].dt.tz is not None:
        df["timestamp_et"] = df["timestamp_et"].dt.tz_localize(None)
    _DTE_BAR_CACHE[key] = df
    return df


def _bar_at_or_after(df: pd.DataFrame, when_et: dt.datetime) -> Optional[OptionBar]:
    """First bar whose timestamp >= when_et (verbatim option_pricing_real.bar_at_or_after)."""
    matches = df[df["timestamp_et"] >= when_et]
    if matches.empty:
        return None
    row = matches.iloc[0]
    return OptionBar(
        timestamp_et=row["timestamp_et"].to_pydatetime(),
        open=float(row["open"]), high=float(row["high"]),
        low=float(row["low"]), close=float(row["close"]),
        volume=int(row["volume"]), vwap=float(row["vwap"]),
        trade_count=int(row["trade_count"]),
    )


def _quote_at_index(df: pd.DataFrame, idx: int) -> Optional[OptionBar]:
    if idx < 0 or idx >= len(df):
        return None
    row = df.iloc[idx]
    return OptionBar(
        timestamp_et=row["timestamp_et"].to_pydatetime(),
        open=float(row["open"]), high=float(row["high"]),
        low=float(row["low"]), close=float(row["close"]),
        volume=int(row["volume"]), vwap=float(row["vwap"]),
        trade_count=int(row["trade_count"]),
    )


def _nearest_cached_strike_dte(d: dt.date, atm: int, side: str, dte: int,
                               max_steps: int = 4) -> Optional[tuple[int, dt.date]]:
    """First cached strike (scanning atm, +-1, +-2...) for the contract EXPIRING `dte`
    trading days after entry day `d`. Returns (strike, expiry_date) or None.

    The DTE cache file for entry day T encodes the EXPIRY in its name. We resolve the
    expiry by trying the OCC symbol for each candidate expiry date and accepting the one
    that has a cached file with day-T bars. We map T->expiry by scanning the cache index
    (built once) so we never invent an expiry that isn't a real listed contract.
    """
    expiry = _expiry_for_entry(d, dte)
    if expiry is None:
        return None
    for step in range(0, max_steps + 1):
        cands = [atm] if step == 0 else [atm - step, atm + step]
        for cand in cands:
            sym = option_symbol(expiry, cand, side)
            if load_dte_contract_bars(sym, dte) is not None:
                return cand, expiry
    return None


# ── Entry-day -> expiry index (built once per DTE from the cache filenames) ─────
_EXPIRY_INDEX: dict[int, dict[dt.date, dt.date]] = {}


def _build_expiry_index(dte: int) -> dict[dt.date, dt.date]:
    """Map entry_day(T) -> expiry_date for every cached contract in the DTE dir.

    Every file's bars are on day T; the filename encodes the expiry. We read each
    file's first timestamp (= day T) once and key the expiry off the filename. This is
    the ground-truth T->expiry map (real listed contracts only)."""
    if dte in _EXPIRY_INDEX:
        return _EXPIRY_INDEX[dte]
    import re
    idx: dict[dt.date, dt.date] = {}
    for f in sorted(DTE_DIRS[dte].glob("*.csv")):
        m = re.match(r"SPY(\d{6})[CP]\d{8}", f.name)
        if not m:
            continue
        expiry = dt.datetime.strptime(m.group(1), "%y%m%d").date()
        if expiry in idx.values() and any(v == expiry for v in idx.values()):
            # already mapped some entry day to this expiry; still need T from this file
            pass
        try:
            first = pd.read_csv(f, nrows=1)["timestamp_et"].iloc[0]
        except Exception:
            continue
        entry_day = pd.to_datetime(first).date()
        # keep the FIRST (earliest-listed) expiry for an entry day (dte=1 => unique)
        if entry_day not in idx or expiry < idx[entry_day]:
            idx[entry_day] = expiry
    _EXPIRY_INDEX[dte] = idx
    return idx


def _expiry_for_entry(d: dt.date, dte: int) -> Optional[dt.date]:
    if dte == 0:
        return d
    return _build_expiry_index(dte).get(d)


# ─────────────────────────────────────────────────────────────────────────────
# SPY expiry-day close lookup (real SPY 5m) for settlement + overnight gap open
# ─────────────────────────────────────────────────────────────────────────────
def _spy_day_open_close(spy: pd.DataFrame) -> dict[dt.date, tuple[float, float]]:
    """date -> (first-RTH open, last close) from the normalized SPY 5m frame."""
    out: dict[dt.date, tuple[float, float]] = {}
    for d, day in spy.groupby("date", sort=True):
        rth = day[(day["t"] >= dt.time(9, 30)) & (day["t"] < RTH_CLOSE)]
        if rth.empty:
            continue
        out[d] = (float(rth["open"].iloc[0]), float(day["close"].iloc[-1]))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# THE DTE TRADE — mirrors simulator_real fill conventions; holds overnight to
# expiry settlement. The ONLY 0DTE-specific divergences are documented inline.
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class DteFill:
    date: str
    side: str
    strike: int
    atm: int
    strike_off: int
    expiry: str
    dte: int
    entry_premium: float
    exit_premium: float
    dollar_pnl: float
    pct_return: float
    exit_reason: str
    held_overnight: bool
    gap_pts: float          # SPY close-to-open gap (signed, in trade-favor)
    note: str


def simulate_dte_trade(
    sg: Signal,
    spy: pd.DataFrame,
    spy_idx_by_global: dict,
    day_open_close: dict[dt.date, tuple[float, float]],
    dte: int,
    *,
    strike: int,
    expiry: dt.date,
    side: str,
    qty: int = QTY,
    premium_stop_pct: float = -0.08,
    tp1_premium_pct: float = 0.30,
    entry_slippage: float = DEFAULT_ENTRY_SLIPPAGE,
    exit_slippage: float = DEFAULT_EXIT_SLIPPAGE,
) -> Optional[DteFill]:
    """One multi-DTE bracket trade on REAL day-T OPRA bars + honest overnight settlement.

    Fill conventions copied verbatim from simulator_real.py:
      - entry = NEXT 5-min option bar open after the trigger bar + entry_slippage (ASK).
      - premium stop = entry*(1+premium_stop_pct); touched (bar.low<=stop) -> fill at stop.
      - TP1 premium fallback = entry*(1+tp1_premium_pct); touched (bar.high>=tp1) -> fill tp1.
      - chart/level stop on SPY close past rejection_level + 0.50 buffer -> market exit.
      - market exits fill at bar.close - exit_slippage; same-bar stop beats TP (conservative).
    Divergence (defines multi-DTE): NO 15:50 force-flatten; an un-exited position is HELD
    overnight and settled at expiry intrinsic, with the overnight gap applied at T+1 open.
    """
    bar = spy.iloc[sg.bar_idx]
    entry_time = bar["timestamp_et"]
    if hasattr(entry_time, "to_pydatetime"):
        entry_time = entry_time.to_pydatetime()
    entry_day = entry_time.date()
    entry_spot = float(bar["close"])
    atm = _strike_from_spot(entry_spot)

    opt_df = load_dte_contract_bars(option_symbol(expiry, strike, side), dte)
    if opt_df is None:
        return None

    # Entry: NEXT 5-min bar open after the trigger bar (no look-ahead). Verbatim convention.
    next_bar_start = entry_time + dt.timedelta(minutes=5)
    entry_bar_opt = _bar_at_or_after(opt_df, next_bar_start)
    if entry_bar_opt is None or entry_bar_opt.open <= 0:
        return None
    entry_premium = entry_bar_opt.open + entry_slippage
    if entry_premium <= 0:
        return None
    stop_premium = entry_premium * (1.0 + premium_stop_pct)
    tp1_premium = entry_premium * (1.0 + tp1_premium_pct)
    rejection_level = sg.stop_level
    level_buf = 0.50  # simulator_real LEVEL_STOP_BUFFER

    # Locate the option-bar index for entry, then walk forward over DAY-T bars only.
    entry_idx_opt = None
    for k in range(len(opt_df)):
        if opt_df.iloc[k]["timestamp_et"] == entry_bar_opt.timestamp_et:
            entry_idx_opt = k
            break
    if entry_idx_opt is None:
        return None

    # SPY index aligned to the entry bar; walk both forward in lockstep over day T.
    spy_idx = sg.bar_idx + 2     # +1 = entry bar, +2 = first managed bar (matches simulator_real)
    opt_idx = entry_idx_opt + 1

    exit_premium: Optional[float] = None
    exit_reason: Optional[str] = None

    while opt_idx < len(opt_df) and spy_idx < len(spy):
        spy_bar = spy.iloc[spy_idx]
        spy_time = spy_bar["timestamp_et"]
        if hasattr(spy_time, "to_pydatetime"):
            spy_time = spy_time.to_pydatetime()
        # Day-T management only: stop walking when we leave entry day (the cache has no
        # T+1 option bars; the rest of the life is settled below).
        if spy_time.date() != entry_day:
            break
        opt_bar = _quote_at_index(opt_df, opt_idx)
        if opt_bar is None:
            opt_idx += 1
            spy_idx += 1
            continue
        if opt_bar.timestamp_et.date() != entry_day:
            break

        worst_premium = opt_bar.low
        best_premium = opt_bar.high

        # (1) Premium stop (conservative: checked before TP on the same bar).
        if worst_premium <= stop_premium:
            exit_premium = stop_premium
            exit_reason = "PREMIUM_STOP"
            break
        # (2) Chart/level stop on SPY close past rejection_level + buffer -> market exit.
        if rejection_level is not None:
            breached = (
                (side == "P" and float(spy_bar["close"]) > rejection_level + level_buf)
                or (side == "C" and float(spy_bar["close"]) < rejection_level - level_buf)
            )
            if breached:
                exit_premium = max(0.01, opt_bar.close - exit_slippage)
                exit_reason = "LEVEL_STOP"
                break
        # (3) TP1 premium fallback -> fill exactly at the bracket level.
        if best_premium >= tp1_premium:
            exit_premium = tp1_premium
            exit_reason = "TP1_PREMIUM"
            break

        opt_idx += 1
        spy_idx += 1

    held_overnight = exit_reason is None
    gap_pts = 0.0

    if held_overnight:
        # ── OVERNIGHT GAP + EXPIRY SETTLEMENT (explicitly modeled) ──────────────
        # No 0DTE flatten. The position survives day-T close. Mark the UNDERLYING at the
        # T+1..expiry opens IN ORDER; the day-T chart stop can GAP THROUGH overnight.
        entry_close_spy = day_open_close.get(entry_day, (entry_spot, entry_spot))[1]

        # Walk each intervening session's OPEN to apply the overnight gap honestly.
        # 1DTE: only the expiry-day open. 2DTE: the T+1 open (intermediate) then expiry open.
        sess = _sessions_between(day_open_close, entry_day, expiry)
        gap_through = False
        prev_close = entry_close_spy
        for sd in sess:
            o, c = day_open_close[sd]
            # signed gap in trade favor (puts: down = favorable; calls: up = favorable)
            g = (prev_close - o) if side == "P" else (o - prev_close)
            gap_pts += g
            # The chart stop can gap THROUGH overnight: if the OPEN is already past the
            # stop level, you do NOT get your stop price — you're out at the gapped open.
            if rejection_level is not None and not gap_through:
                if (side == "P" and o > rejection_level + level_buf) or \
                   (side == "C" and o < rejection_level - level_buf):
                    # Closed at gapped-open intrinsic (stop gapped through).
                    intrinsic = max(0.0, (strike - o) if side == "P" else (o - strike))
                    exit_premium = max(0.0, intrinsic - exit_slippage)
                    exit_reason = "GAP_THROUGH_STOP"
                    gap_through = True
                    break
            prev_close = c

        if not gap_through:
            # Ride to EXPIRY SETTLEMENT = intrinsic at the expiry-day SPY close. No
            # synthetic option mark — pure intrinsic at a real SPY price.
            exp_close = day_open_close.get(expiry)
            if exp_close is None:
                return None  # no SPY data on expiry day -> cannot settle honestly
            sc = exp_close[1]
            intrinsic = max(0.0, (strike - sc) if side == "P" else (sc - strike))
            # Settlement has no exit slippage (cash settle / auto-exercise at intrinsic).
            exit_premium = intrinsic
            exit_reason = "EXPIRY_SETTLEMENT"

    if exit_premium is None or exit_reason is None:
        return None

    dollar_pnl = (exit_premium - entry_premium) * qty * 100.0
    pct = dollar_pnl / (entry_premium * qty * 100.0) if entry_premium > 0 else 0.0
    return DteFill(
        date=str(entry_day), side=side, strike=int(strike), atm=int(atm),
        strike_off=int(strike - atm), expiry=str(expiry), dte=dte,
        entry_premium=round(entry_premium, 4), exit_premium=round(exit_premium, 4),
        dollar_pnl=round(dollar_pnl, 2), pct_return=round(pct, 5),
        exit_reason=exit_reason, held_overnight=held_overnight,
        gap_pts=round(gap_pts, 3), note=sg.note,
    )


def _sessions_between(day_open_close: dict, entry_day: dt.date, expiry: dt.date) -> list[dt.date]:
    """Ordered trading sessions strictly AFTER entry_day up to & incl expiry (real SPY days)."""
    return [d for d in sorted(day_open_close) if entry_day < d <= expiry]


# ─────────────────────────────────────────────────────────────────────────────
# METRICS (identical disclosure shape to the 0DTE edge-hunt: per-trade expectancy,
# IS/OOS split, positive_quarters, top5_day_pct + overnight-gap + risk-adjusted)
# ─────────────────────────────────────────────────────────────────────────────
def _quarter(date_str: str) -> str:
    y, m, _ = date_str.split("-")
    return f"{y}Q{(int(m) - 1) // 3 + 1}"


def _top5_day_pct(rows: list[DteFill]) -> Optional[float]:
    by_day: dict[str, float] = defaultdict(float)
    for r in rows:
        by_day[r.date] += r.dollar_pnl
    total = sum(by_day.values())
    if total <= 0:
        return None
    top5 = sum(sorted(by_day.values(), reverse=True)[:5])
    return round(100 * top5 / total, 1)


def _drop_top5_per_trade(rows: list[DteFill]) -> Optional[float]:
    """Per-trade expectancy after removing the 5 best P&L DAYS (full-sample L173 gate 5).
    Mirrors fraud_gates._per_trade_and_drop_top5 (drops best DAYS not trades)."""
    if not rows:
        return None
    by_day: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        by_day[r.date].append(r.dollar_pnl)
    day_tot = sorted(by_day.items(), key=lambda kv: sum(kv[1]), reverse=True)
    kept = [p for _, pnls in day_tot[5:] for p in pnls]
    return round(sum(kept) / len(kept), 2) if kept else None


def _oos_drop_top5_per_trade(rows: list[DteFill]) -> tuple[Optional[float], int]:
    """OOS-ALONE per-trade after removing the 5 best OOS days (decisive L173 gate 9).
    Returns (per_trade_after_drop, oos_n). None when <=5 OOS observations (uneval)."""
    oos = [r for r in rows if int(r.date[:4]) == OOS_YEAR]
    if len(oos) <= MIN_OOS_TO_DROP_TOP5:
        return None, len(oos)
    by_day: dict[str, list[float]] = defaultdict(list)
    for r in oos:
        by_day[r.date].append(r.dollar_pnl)
    day_tot = sorted(by_day.items(), key=lambda kv: sum(kv[1]), reverse=True)
    kept = [p for _, pnls in day_tot[5:] for p in pnls]
    return (round(sum(kept) / len(kept), 2) if kept else None), len(oos)


def _is_first_half_per_trade(rows: list[DteFill]) -> Optional[float]:
    """IS-2025 first-half (Jan-Jun) per-trade expectancy (gate 6)."""
    fh = [r for r in rows if r.date[:4] == "2025" and r.date[5:7] <= "06"]
    if not fh:
        return None
    return round(sum(r.dollar_pnl for r in fh) / len(fh), 2)


def metrics(rows: list[DteFill]) -> dict:
    if not rows:
        return {"n": 0}
    pnl = np.array([r.dollar_pnl for r in rows], float)
    n = len(rows)
    wins = int((pnl > 0).sum())
    is_rows = [r for r in rows if int(r.date[:4]) != OOS_YEAR]
    oos_rows = [r for r in rows if int(r.date[:4]) == OOS_YEAR]

    def _exp(rs):
        return round(float(np.mean([r.dollar_pnl for r in rs])), 2) if rs else 0.0

    def _tot(rs):
        return round(float(np.sum([r.dollar_pnl for r in rs])), 2) if rs else 0.0

    by_q: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        by_q[_quarter(r.date)].append(r.dollar_pnl)
    quarters = {q: {"n": len(v), "exp": round(sum(v) / len(v), 2), "total": round(sum(v), 2)}
                for q, v in sorted(by_q.items())}
    q_pos = sum(1 for v in quarters.values() if v["exp"] > 0)

    held = [r for r in rows if r.held_overnight]
    gap_through = [r for r in rows if r.exit_reason == "GAP_THROUGH_STOP"]
    settled = [r for r in rows if r.exit_reason == "EXPIRY_SETTLEMENT"]
    std = float(pnl.std(ddof=1)) if n > 1 else 0.0
    drop_top5_full = _drop_top5_per_trade(rows)
    oos_drop_top5, oos_n_chk = _oos_drop_top5_per_trade(rows)
    is_fh = _is_first_half_per_trade(rows)
    # Gap-contribution accounting (held-overnight trades only): total $ that came from
    # the close-to-open gap vs the intraday/settlement move. gap_pts is signed-in-favor.
    gap_dollars = round(float(sum(r.gap_pts for r in held)) * QTY * 100.0, 2)
    return {
        "n": n,
        "wr_pct": round(100 * wins / n, 1),
        "exp_dollar": round(float(pnl.mean()), 2),
        "total_dollar": round(float(pnl.sum()), 2),
        "std_dollar": round(std, 2),
        "risk_adj_exp": round(float(pnl.mean()) / std, 4) if std > 0 else None,
        "is_n": len(is_rows), "is_exp": _exp(is_rows), "is_total": _tot(is_rows),
        "oos_n": len(oos_rows), "oos_exp": _exp(oos_rows), "oos_total": _tot(oos_rows),
        # L173 concentration gates (gate 5 full-sample + gate 9 OOS-alone) + IS-first-half (gate 6).
        "drop_top5_full": drop_top5_full,
        "oos_drop_top5": oos_drop_top5,
        "oos_drop_top5_evaluable": bool(oos_drop_top5 is not None and oos_n_chk > MIN_OOS_TO_DROP_TOP5),
        "is_first_half_exp": is_fh,
        "gap_contribution_dollar": gap_dollars,
        "quarters": quarters,
        "positive_quarters": f"{q_pos}/{len(quarters)}",
        "positive_quarters_n": q_pos, "n_quarters": len(quarters),
        "top5_day_pct": _top5_day_pct(rows),
        "overnight": {
            "held_overnight_n": len(held),
            "held_overnight_pct": round(100 * len(held) / n, 1),
            "gap_through_stop_n": len(gap_through),
            "expiry_settlement_n": len(settled),
            "mean_gap_pts_favor": round(float(np.mean([r.gap_pts for r in held])), 3) if held else 0.0,
        },
        "exit_hist": {k: sum(1 for r in rows if r.exit_reason == k)
                      for k in sorted({r.exit_reason for r in rows})},
    }


def clears_bar(m: dict) -> tuple[bool, list[str]]:
    """Structural gates of the canonical 9-gate bar (anti-pattern 2.10; B7/B8 parity):
      1 OOS/tr>0  2 posQ>=4  3 top5-day<200%(full)  4 n>=20  5 full-drop-top5>0
      6 IS-2025-first-half/tr>0  9 OOS-ALONE drop-top5>0 (decisive L173 de-concentration).
    Gates 7 (random-null L172) and 8 (no-truncation L171) are applied in the post-processor
    on the recorded rows (they need the per-trade row set, not just the metric summary)."""
    fails = []
    if m.get("n", 0) < BAR_N:                                   # gate 4
        fails.append(f"n={m.get('n', 0)}<{BAR_N}")
    if m.get("oos_exp", -1) <= BAR_OOS_EXP:                     # gate 1
        fails.append(f"oos_exp={m.get('oos_exp')}<=0")
    if m.get("positive_quarters_n", 0) < BAR_POS_Q:            # gate 2
        fails.append(f"pos_q={m.get('positive_quarters', '?')}<{BAR_POS_Q}")
    t5 = m.get("top5_day_pct")                                  # gate 3
    if t5 is None or t5 >= BAR_TOP5:
        fails.append(f"top5_day_pct={t5}")
    dt5 = m.get("drop_top5_full")                               # gate 5
    if dt5 is None or dt5 <= 0:
        fails.append(f"drop_top5_full={dt5}<=0")
    ish = m.get("is_first_half_exp")                            # gate 6
    if ish is None or ish <= 0:
        fails.append(f"is_first_half={ish}<=0")
    od5 = m.get("oos_drop_top5")                                # gate 9 (L173 decisive)
    if not m.get("oos_drop_top5_evaluable"):
        fails.append(f"oos_drop_top5_uneval(oos_n<=5)")
    elif od5 is None or od5 <= 0:
        fails.append(f"oos_drop_top5={od5}<=0(L173)")
    return (len(fails) == 0, fails)


# ─────────────────────────────────────────────────────────────────────────────
# FAMILY REGISTRY (detectors reused byte-for-byte). Add dead families as imported.
# ─────────────────────────────────────────────────────────────────────────────
# Each adapter takes a uniform (days, vix, spy) signature and re-shapes to whatever
# the underlying byte-for-byte detector expects. The detector bodies are untouched.
def _detect_vwap(days, vix, spy, ribbon=None):
    # vwap_continuation port: signature is detect_signals(days, vix, ...).
    return detect_vwap_continuation(days, vix, breakout_only=False, put_needs_rising_vix=False)


def _detect_orb(days, vix, spy, ribbon=None):
    # DEAD family: opening-range-breakout continuation on elevated RVOL (Zarattini).
    # native signature: detect_orb_rvol(spy_df, ribbon_df, vix, days). ribbon unused.
    return detect_orb_rvol(spy, None, vix, days)


def _detect_momentum(days, vix, spy, ribbon=None):
    # DEAD family: morning/intraday momentum continuation (Gao-Han-Li-Zhou).
    # native signature: detect_intraday_momentum(spy_df, ribbon_df, vix, days). ribbon unused.
    return detect_intraday_momentum(spy, None, vix, days)


def _detect_power_hour(days, vix, spy, ribbon=None):
    # DEAD family: last-hour trend-continuation entry. native signature
    # detect_power_hour(spy_df, ribbon_df, vix, days) — ribbon IS read (EMA stack must
    # corroborate trend at PH_START). Real ribbon passed (byte-for-byte _dte_signal_days.py).
    return detect_power_hour(spy, ribbon, vix, days)


def _detect_vwap_pullback(days, vix, spy, ribbon=None):
    # DEAD family: VWAP trend-day pullback (POSITIVE-CONTROL among dead families — the
    # trend-ride that is already alive at 0DTE, so it bounds the theta-lift ceiling).
    # native signature: detect_vwap_pullback(spy_df, ribbon_df, vix, days). ribbon unused by body.
    return detect_vwap_pullback(spy, None, vix, days)


def _detect_gap_fade(days, vix, spy, ribbon=None):
    # DEAD family: GAP-FADE — a REVERSAL / reclaim-ride. Fade an opening gap back toward
    # prior close (gap-up -> PUTS, gap-down -> CALLS; 0.25%-1.5% gap band). This is the
    # canonical reversal counterpart to the continuation families above — the task's
    # "second dead directional family (reclaim/reversal-ride)" resurrection test.
    # native signature: detect_gap_fade(spy_df, ribbon_df, vix, days). spy/ribbon/vix unused
    # by the body (reads only DayCtx.prior_close + first RTH bar) — passed for uniformity.
    return detect_gap_fade(spy, None, vix, days)


def _detect_vwap_reclaim_failed_break(days, vix, spy, ribbon=None):
    # #2 vwap_reclaim_failed_break: one causal with-trend VWAP-reclaim-after-failed-break
    # entry/day. Detector signature is detect_signals(days) only (reads DayCtx.rth +
    # session_vwap_asof internally; vix/spy/ribbon unused by the body) — passed for the
    # uniform registry signature. Returns Signal(bar_idx, side, stop_level, note) byte-for-byte.
    return detect_vwap_reclaim_failed_break(days)


FAMILIES = {
    "vwap_continuation": _detect_vwap,   # known-LIVE control (already ships)
    "vwap_reclaim_failed_break": _detect_vwap_reclaim_failed_break,  # #2 — DTE-stop lever target
    "orb_continuation": _detect_orb,     # DEAD 0DTE family — resurrection candidate
    "momentum_morning": _detect_momentum,  # DEAD 0DTE family — resurrection candidate
    "power_hour": _detect_power_hour,    # DEAD 0DTE family (last-hour trend) — resurrection candidate
    "vwap_pullback": _detect_vwap_pullback,  # DEAD 0DTE family (positive control) — resurrection candidate
    "gap_fade": _detect_gap_fade,        # DEAD 0DTE family (REVERSAL/reclaim) — this task
}


# ─────────────────────────────────────────────────────────────────────────────
# CELL RUNNER
# ─────────────────────────────────────────────────────────────────────────────
def run_cell(signals, spy, day_open_close, dte, *, strike_offset, premium_stop_pct,
             tp1_premium_pct=0.30) -> tuple[list[DteFill], dict]:
    rows: list[DteFill] = []
    n_total = len(signals)
    n_filled = n_cache_miss = n_sim_none = n_no_expiry = 0
    for sg in signals:
        bar = spy.iloc[sg.bar_idx]
        d = bar["timestamp_et"].date() if hasattr(bar["timestamp_et"], "date") else bar["timestamp_et"].to_pydatetime().date()
        spot = float(bar["close"])
        atm = _strike_from_spot(spot)
        target = atm - strike_offset if sg.side == "P" else atm + strike_offset
        res = _nearest_cached_strike_dte(d, target, sg.side, dte)
        if res is None:
            if _expiry_for_entry(d, dte) is None:
                n_no_expiry += 1
            else:
                n_cache_miss += 1
            continue
        strike, expiry = res
        fill = simulate_dte_trade(
            sg, spy, {}, day_open_close, dte, strike=strike, expiry=expiry, side=sg.side,
            qty=QTY, premium_stop_pct=premium_stop_pct, tp1_premium_pct=tp1_premium_pct,
        )
        if fill is None:
            n_sim_none += 1
            continue
        n_filled += 1
        rows.append(fill)
    cov = {"signals": n_total, "filled": n_filled, "cache_miss": n_cache_miss,
           "no_expiry_listed": n_no_expiry, "sim_none": n_sim_none,
           "fill_rate": round(n_filled / n_total, 3) if n_total else 0.0}
    return rows, cov


# ─────────────────────────────────────────────────────────────────────────────
# VALIDATION (self-tests) — run with --validate (and inside --smoke)
# ─────────────────────────────────────────────────────────────────────────────
def validate() -> list[str]:
    """Deterministic checks: deep-ITM 1DTE settles at intrinsic; OTM-worthless = -100%;
    overnight gap applied at the T+1 open; per-leg prices are real fetched values."""
    msgs: list[str] = []

    # 1) ITM settlement = intrinsic at expiry SPY close (no synthetic mark).
    #    585P with SPY closing 580.19 on the 2025-03-04 expiry is $4.81 ITM (real cached strike).
    strike, side = 585, "P"
    expiry = dt.date(2025, 3, 4)
    sc = 580.19                        # real SPY 2025-03-04 last close (verified)
    intrinsic = max(0.0, strike - sc)
    assert abs(intrinsic - 4.81) < 0.01, intrinsic
    msgs.append(f"OK ITM 585P settles intrinsic=${intrinsic:.2f} at expiry close {sc}")

    # 2) OTM-worthless expiry -> intrinsic 0 -> -100% of premium.
    otm_intrinsic = max(0.0, 576 - sc)     # 576P with SPY 580.19 = worthless
    assert otm_intrinsic == 0.0
    msgs.append("OK OTM 576P settles worthless (intrinsic=0 => -100% premium)")

    # 3) per-leg prices are REAL fetched values (load a real 1DTE contract bar).
    sym = option_symbol(expiry, 585, "P")
    df = load_dte_contract_bars(sym, 1)
    assert df is not None and len(df) > 0, "expected real 1DTE bars for 585P 2025-03-04"
    assert (df["timestamp_et"].dt.date == dt.date(2025, 3, 3)).all(), "1DTE bars must be entry day T"
    msgs.append(f"OK real 1DTE bars present for {sym}: {len(df)} bars on entry day "
                f"{df['timestamp_et'].iloc[0].date()} (open={df['open'].iloc[0]})")

    # 4) overnight gap applied at the T+1 open (sign convention check).
    #    puts favorable gap = prev_close - open (SPY gaps DOWN overnight => +favor).
    prev_close, t1_open = 581.32, 579.71   # real SPY 03-03 close / 03-04 open
    put_gap = prev_close - t1_open
    assert abs(put_gap - 1.61) < 0.01, put_gap
    msgs.append(f"OK overnight gap modeled at T+1 open: SPY {prev_close}->{t1_open} "
                f"= +{put_gap:.2f} favor for puts (applied before settlement)")

    # 5) expiry index maps entry day -> real listed expiry (1 trading day for 1DTE).
    exp1 = _expiry_for_entry(dt.date(2025, 3, 3), 1)
    assert exp1 == dt.date(2025, 3, 4), exp1
    msgs.append(f"OK expiry index: entry 2025-03-03 -> 1DTE expiry {exp1}")
    return msgs


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def _load_spy_vix():
    # Master SPY/VIX 5m covers 2025-01-02..2026-06-16. The DTE option cache has a few
    # later entry days (to 06-18) but without SPY settlement data those settle as None
    # (skipped honestly). Use the master end (06-16) so the full 2025+2026 history loads.
    spy_raw, vix_raw = ar_runner.load_data(dt.date(2025, 1, 1), dt.date(2026, 6, 16))
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    return spy, vix


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="validate + print one sample trade P&L path")
    ap.add_argument("--validate", action="store_true", help="run deterministic self-tests only")
    ap.add_argument("--family", default="vwap_continuation", choices=list(FAMILIES))
    args = ap.parse_args()

    if args.validate:
        for m in validate():
            print("  " + m)
        print("VALIDATION PASSED")
        return 0

    print("[dte] loading SPY+VIX ...", flush=True)
    spy, vix = _load_spy_vix()
    day_open_close = _spy_day_open_close(spy)
    days = build_day_contexts(spy)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))  # power_hour reads ribbon stack
    n_days = len(days)
    print(f"[dte] SPY bars={len(spy)} trading_days={n_days} "
          f"window={spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
          flush=True)

    detect = FAMILIES[args.family]
    signals = detect(days, vix, spy, ribbon)
    sig_days = len({spy.iloc[s.bar_idx]['timestamp_et'].date() for s in signals})
    print(f"[dte] family={args.family} signals={len(signals)} on {sig_days} days "
          f"side={{'C':{sum(1 for s in signals if s.side=='C')},'P':{sum(1 for s in signals if s.side=='P')}}}",
          flush=True)

    if args.smoke:
        print("\n=== VALIDATION ===")
        for m in validate():
            print("  " + m)
        print("\n=== SAMPLE 1DTE TRADE P&L PATHS (day-T mgmt + overnight gap + settlement) ===")
        _build_expiry_index(1)

        def _print_path(label, fill, sg, d, expiry):
            entry_c = day_open_close.get(d, (0, 0))
            exp_c = day_open_close.get(expiry, (0, 0))
            print(f"  [{label}] signal {d} {sg.side} {sg.note}")
            print(f"    DAY T  ({d}): SPY entry close={float(spy.iloc[sg.bar_idx]['close']):.2f}  "
                  f"picked strike={fill.strike}({fill.strike_off:+d}) expiry={expiry}")
            print(f"    ENTRY  : option open + slip = ${fill.entry_premium:.2f}/contract x{QTY} (next-bar fill, no look-ahead)")
            print(f"    DAY T mgmt: premium-stop=-50%, chart-stop @ {sg.stop_level}, TP1 +30%")
            print(f"    OVERNIGHT: held={fill.held_overnight}  SPY {d}-close={entry_c[1]:.2f} -> "
                  f"{expiry}-open={exp_c[0]:.2f} (gap favor={fill.gap_pts:+.2f}pts)")
            print(f"    SETTLE : SPY {expiry}-close={exp_c[1]:.2f}  exit=${fill.exit_premium:.2f}  reason={fill.exit_reason}")
            print(f"    P&L    : (${fill.exit_premium:.2f}-${fill.entry_premium:.2f}) x{QTY}x100 = "
                  f"${fill.dollar_pnl:.2f}  ({fill.pct_return*100:+.1f}%)")

        first_any = None
        first_held = None
        for sg in signals:
            bar = spy.iloc[sg.bar_idx]
            d = bar["timestamp_et"].date()
            spot = float(bar["close"]); atm = _strike_from_spot(spot)
            target = atm - (-1) if sg.side == "P" else atm + (-1)   # ITM-1
            res = _nearest_cached_strike_dte(d, target, sg.side, 1)
            if res is None:
                continue
            strike, expiry = res
            fill = simulate_dte_trade(sg, spy, {}, day_open_close, 1,
                                      strike=strike, expiry=expiry, side=sg.side,
                                      qty=QTY, premium_stop_pct=-0.50)
            if fill is None:
                continue
            if first_any is None:
                first_any = (fill, sg, d, expiry)
            if fill.held_overnight and first_held is None:
                first_held = (fill, sg, d, expiry)
            if first_any and first_held:
                break
        if first_any:
            _print_path("day-T exit", *first_any)
        if first_held:
            print()
            _print_path("held-overnight->settlement", *first_held)
        if not first_any:
            print("  (no 1DTE sample fillable in window)")
        elif not first_held:
            print("  (no held-overnight 1DTE sample fillable in window)")
        return 0

    # ── FULL SWEEP: 0/1/2 DTE x strike x stop, side by side ──────────────────
    results = {"family": args.family, "run_date": dt.date.today().isoformat(),
               "window": f"{spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
               "n_signals": len(signals), "by_dte": {}}
    for dte in (0, 1, 2):
        _build_expiry_index(dte) if dte else None
        cells = []
        for so in STRIKE_OFFSETS:
            for ps in PREMIUM_STOPS:
                rows, cov = run_cell(signals, spy, day_open_close, dte,
                                     strike_offset=so, premium_stop_pct=ps)
                m = metrics(rows)
                clears, fails = clears_bar(m)
                tier = f"ITM{abs(so)}" if so < 0 else ("ATM" if so == 0 else f"OTM{so}")
                cells.append({"strike_offset": so, "strike_tier": tier,
                              "premium_stop_pct": ps, "coverage": cov, "metrics": m,
                              "clears_bar": clears, "clears_bar_fails": fails,
                              # persisted per-trade rows for gates 7 (null) + 8 (no-trunc)
                              # applied by the post-processor (DTE-LIBRARY-SURVEY builder).
                              "rows": [{"date": r.date, "side": r.side,
                                        "dollar_pnl": r.dollar_pnl,
                                        "pct_return": r.pct_return} for r in rows]})
                mm = m if m.get("n") else {}
                print(f"  DTE={dte} off={so:+d}({tier:>4}) stop={ps:>6} | "
                      f"n={mm.get('n','-'):>3} exp=${mm.get('exp_dollar','-'):>8} "
                      f"oos_exp=${mm.get('oos_exp','-'):>8} posQ={mm.get('positive_quarters','-')} "
                      f"top5%={mm.get('top5_day_pct','-')} held%={mm.get('overnight',{}).get('held_overnight_pct','-') if mm else '-'} "
                      f"-> {'CLEARS' if clears else 'no'}", flush=True)
        clears_cells = [c for c in cells if c["clears_bar"]]
        results["by_dte"][str(dte)] = {"cells": cells, "n_candidate_cells": len(clears_cells),
                                       "candidate_cells": clears_cells}

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\n[dte] wrote {OUT}")

    print("\n=== DTE-EXPANSION VERDICT (does the signal resurrect at longer DTE?) ===")
    for dte in ("0", "1", "2"):
        nc = results["by_dte"][dte]["n_candidate_cells"]
        print(f"  DTE={dte}: {nc} cell(s) clear the candidate-edge bar")
        for c in results["by_dte"][dte]["candidate_cells"]:
            m = c["metrics"]
            print(f"     off={c['strike_offset']:+d}({c['strike_tier']}) stop={c['premium_stop_pct']} "
                  f"-> n={m['n']} oos_exp=${m['oos_exp']} exp=${m['exp_dollar']} "
                  f"posQ={m['positive_quarters']} top5%={m['top5_day_pct']} "
                  f"held_overnight%={m['overnight']['held_overnight_pct']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
