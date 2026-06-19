"""infinite_ammo_discovery — first-principles intraday SPY edge discovery.

"INFINITE AMMO" edge discovery: generate NEW directional-intraday-SPY edge
hypotheses grounded in documented microstructure, implement each as a minimal
*causal* detector on the 5-min bars, then STANDALONE-backtest every signal on
REAL OPRA option fills (no Black-Scholes). Keep only survivors.

This is strategy CREATION from the candle data itself — the diversifying
complement to mining J's trade history. It is NOT gated on J's anchors: an edge
qualifies on its own merits (standalone real-fills expectancy > 0 AND OOS
sign-stable AND DSR not-FAIL).

PROPOSE-ONLY (Rule 9). Nothing here is wired into the live engine, params, or the
order path. Survivors become WATCH-ONLY candidate slots for the regime-aware book
(``backtest/lib/engine/regime_book.py``). Output is a scorecard JSON only.

REUSE, not a framework
----------------------
* Real fills: ``lib.simulator_real.simulate_trade_real`` (the exact harness J's
  setups use). Entry is causal: trigger fires on a bar's CLOSE, fill is the NEXT
  bar's open + slippage (MIN HOLD 5 min). No look-ahead by construction.
* Ribbon: ``lib.ribbon.compute_ribbon``. VIX align: same logic as orchestrator.
* Stats: ``lib.validation.gate.evaluate_candidate`` (DSR/PSR, Bailey-Lopez de Prado).

THE HYPOTHESES (grounded, both directions where applicable)
-----------------------------------------------------------
H1  INTRADAY MOMENTUM (standalone entry, Gao-Han-Li-Zhou 2018, peer-reviewed):
    the first-half-hour return predicts the last-half-hour return. Implemented as
    a STANDALONE afternoon entry in the direction of a strong, trending morning
    (open->reference-time move beyond a vol-scaled threshold). NOT the failed
    morning-sign *gate* — a fresh entry on its own.
H2  GAP FADE vs GAP-AND-GO: SPY opens beyond yesterday's close by a gap; either
    it fades back toward the prior close (fade) or holds and continues (go).
    Tested as two separate detectors, both directions.
H3  ORB + RVOL (Zarattini 2023): opening-range breakout, but ONLY on elevated
    relative-volume "in-play" days — the regime where the ORB edge is documented
    to live. Both directions.
H4  VWAP TREND-DAY PULLBACK: on a day trending cleanly on one side of session
    VWAP, enter the pullback that tags VWAP in the trend direction.
H5  POWER-HOUR CONTINUATION: in the last hour, enter in the direction of the
    day's established trend (0DTE-era late directional flow).

Each detector returns causal Signal records; every signal is simulated at the
nearest-cached ATM strike (offset disclosed) AND at ITM-1, with a chart/structural
stop. We measure standalone expectancy, WR, per-quarter, IS/OOS sign-stability
(L166), and the DSR verdict.

Usage
-----
    python backtest/autoresearch/infinite_ammo_discovery.py
        [--spy PATH] [--vix PATH] [--qty 3] [--max-strike-steps 4]
        [--out analysis/recommendations/infinite-ammo-discovery.json]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]          # ...\42\backtest
PROJECT = REPO.parent                               # ...\42
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from lib.ribbon import compute_ribbon, RibbonState   # noqa: E402
from lib.option_pricing_real import (                # noqa: E402
    option_symbol,
    load_contract_bars,
)
from lib.simulator_real import simulate_trade_real, _strike_from_spot  # noqa: E402
from lib.validation.gate import evaluate_candidate   # noqa: E402

# RTH session window (ET). SPY CSV spans 04:00-19:55; we only trade the cash session.
RTH_OPEN = dt.time(9, 30)
RTH_CLOSE = dt.time(16, 0)
# OOS split: chronological 70/30 (L166 sign-stability). Pre-cutoff = IS, post = OOS.
OOS_SPLIT_FRAC = 0.70
# n_trials for DSR deflation = number of hypotheses x directions x strike tiers we
# searched in this run (selection-bias correction). Set after building the matrix.


# ─────────────────────────────────────────────────────────────────────────────
# DATA LOADING (mirror orchestrator / bull_ribbon_reversal_real_fills conventions)
# ─────────────────────────────────────────────────────────────────────────────
def load_spy(path: str) -> pd.DataFrame:
    """Load SPY 5-min CSV -> TZ-naive ET, add date/time/minute helper columns."""
    df = pd.read_csv(path)
    ts = pd.to_datetime(df["timestamp_et"], utc=True)
    df["timestamp_et"] = ts.dt.tz_convert("America/New_York").dt.tz_localize(None)
    df = df.drop_duplicates(subset="timestamp_et", keep="first").reset_index(drop=True)
    df["date"] = df["timestamp_et"].dt.date
    df["t"] = df["timestamp_et"].dt.time
    df["minute"] = df["timestamp_et"].dt.hour * 60 + df["timestamp_et"].dt.minute
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = df[c].astype(float)
    return df


def align_vix(spy_df: pd.DataFrame, vix_path: str) -> pd.Series:
    """Forward-fill VIX close onto SPY bar timestamps (orchestrator._align_vix_to_spy)."""
    vix_df = pd.read_csv(vix_path)
    spy_ts = pd.to_datetime(spy_df["timestamp_et"]).dt.tz_localize("America/New_York").dt.tz_convert("UTC")
    vix_ts = pd.to_datetime(vix_df["timestamp_et"], utc=True)
    vix_indexed = pd.Series(vix_df["close"].astype(float).values, index=vix_ts)
    vix_indexed = vix_indexed[~vix_indexed.index.duplicated(keep="first")]
    aligned = vix_indexed.reindex(spy_ts, method="ffill")
    aligned.index = range(len(aligned))
    return aligned.fillna(0.0)


# ─────────────────────────────────────────────────────────────────────────────
# PER-DAY FEATURE PRECOMPUTE (all look-ahead-safe; only used causally below)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class DayCtx:
    """Per-day, look-ahead-safe scaffolding. Index ranges are GLOBAL spy_df indices.

    Every field is either a static daily fact (prior close, RTH index span) or an
    *as-of* series the detectors only ever read at-or-before the current bar.
    """
    date: dt.date
    idx0: int                 # global index of first RTH bar
    idx_last: int             # global index of last RTH bar
    prior_close: Optional[float]
    rth: pd.DataFrame         # RTH-only slice (global index preserved)


def build_day_contexts(spy_df: pd.DataFrame) -> list[DayCtx]:
    """One DayCtx per trading day with >= a usable RTH session."""
    out: list[DayCtx] = []
    prior_close: Optional[float] = None
    for d, day in spy_df.groupby("date", sort=True):
        rth = day[(day["t"] >= RTH_OPEN) & (day["t"] < RTH_CLOSE)]
        if len(rth) >= 12:    # need at least an hour of bars to be meaningful
            out.append(
                DayCtx(
                    date=d,
                    idx0=int(rth.index[0]),
                    idx_last=int(rth.index[-1]),
                    prior_close=prior_close,
                    rth=rth,
                )
            )
        # prior_close for NEXT day = this day's last RTH close (or last bar if no RTH)
        prior_close = float(day["close"].iloc[-1])
    return out


def session_vwap_asof(rth: pd.DataFrame) -> pd.Series:
    """Cumulative session VWAP using typical price * volume, look-ahead-safe.

    VWAP at bar i uses only bars[0..i] of the session -> reading it at the current
    bar is causal. Typical price = (H+L+C)/3.
    """
    tp = (rth["high"] + rth["low"] + rth["close"]) / 3.0
    pv = (tp * rth["volume"]).cumsum()
    vv = rth["volume"].cumsum().replace(0, np.nan)
    return (pv / vv).bfill()


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL RECORD + DETECTOR CONTRACT
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Signal:
    """A causal entry signal. Entry is the NEXT bar after `bar_idx` (sim handles it).

    `stop_level` is the structural/chart price used for the simulator's level stop
    (None => premium-stop only). `side`: 'P' bearish / 'C' bullish.
    """
    bar_idx: int
    side: str
    stop_level: Optional[float]
    note: str = ""


# A detector reads (spy_df, ribbon_df, vix, day_contexts) and returns Signals.
Detector = Callable[[pd.DataFrame, pd.DataFrame, pd.Series, list[DayCtx]], list[Signal]]


def _bar_range_baseline(spy_df: pd.DataFrame, idx: int, lookback: int = 20) -> float:
    """Mean (H-L) over the prior `lookback` bars (look-ahead-safe; excludes idx)."""
    start = max(0, idx - lookback)
    if start >= idx:
        return 0.0
    sl = spy_df.iloc[start:idx]
    return float((sl["high"] - sl["low"]).mean())


# ─────────────────────────────────────────────────────────────────────────────
# H1 — INTRADAY MOMENTUM (standalone afternoon entry; Gao-Han-Li-Zhou)
# ─────────────────────────────────────────────────────────────────────────────
def detect_intraday_momentum(spy_df, ribbon_df, vix, days) -> list[Signal]:
    """Enter at REF_TIME in the direction of a strong trending morning.

    Morning move = (price at REF_TIME) / (RTH open) - 1, measured AT ref_time bar
    close. If |move| exceeds a vol-scaled threshold (ATR-like daily range proxy),
    enter in the SAME direction (continuation). One entry per day.

    Causal: the morning return uses only bars up to ref_time; entry is the next bar.
    """
    REF_TIME = dt.time(13, 0)          # 1pm ET reference (after lunch, before power hour)
    MIN_MOVE_PCT = 0.0035              # >= 0.35% morning move to call it "trending"
    out: list[Signal] = []
    for dc in days:
        rth = dc.rth
        open_px = float(rth["open"].iloc[0])
        ref = rth[rth["t"] <= REF_TIME]
        if len(ref) < 6 or open_px <= 0:
            continue
        ref_bar = ref.iloc[-1]
        ref_idx = int(ref.index[-1])
        move = float(ref_bar["close"]) / open_px - 1.0
        if abs(move) < MIN_MOVE_PCT:
            continue
        side = "C" if move > 0 else "P"
        # structural stop: the session extreme AGAINST the trade up to ref_time
        if side == "C":
            stop = float(ref["low"].min())
        else:
            stop = float(ref["high"].max())
        out.append(Signal(bar_idx=ref_idx, side=side, stop_level=stop,
                          note=f"morning_move={move:+.4f}"))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# H2a — GAP FADE  /  H2b — GAP-AND-GO
# ─────────────────────────────────────────────────────────────────────────────
def _gap_setup(days) -> list[tuple[DayCtx, float, int, pd.Series]]:
    """Shared gap precompute: (dc, gap_pct, first_bar_idx, first_bar) for gapped days."""
    res = []
    for dc in days:
        if dc.prior_close is None or dc.prior_close <= 0:
            continue
        first = dc.rth.iloc[0]
        first_idx = int(dc.rth.index[0])
        gap = float(first["open"]) / dc.prior_close - 1.0
        res.append((dc, gap, first_idx, first))
    return res


def detect_gap_fade(spy_df, ribbon_df, vix, days) -> list[Signal]:
    """Fade an opening gap back toward prior close.

    Gap up >= MIN_GAP -> buy PUTS (expect fade down to prior close).
    Gap down <= -MIN_GAP -> buy CALLS (expect fade up to prior close).
    Entry on the FIRST RTH bar's close (fill next bar). Stop = the opening
    extreme in the gap direction (gap up -> stop above session high so far).
    """
    MIN_GAP = 0.0025          # >= 0.25% overnight gap
    MAX_GAP = 0.015           # skip > 1.5% gaps (often news-driven runaway)
    out: list[Signal] = []
    for dc, gap, fidx, fbar in _gap_setup(days):
        if not (MIN_GAP <= abs(gap) <= MAX_GAP):
            continue
        if gap > 0:
            side = "P"                       # fade the gap-up
            stop = float(fbar["high"])       # opening bar high
        else:
            side = "C"                       # fade the gap-down
            stop = float(fbar["low"])
        out.append(Signal(bar_idx=fidx, side=side, stop_level=stop,
                          note=f"gap={gap:+.4f}"))
    return out


def detect_gap_and_go(spy_df, ribbon_df, vix, days) -> list[Signal]:
    """Trade gap continuation after a confirming first bar.

    Gap up AND the first RTH bar closes green (above its open) -> buy CALLS.
    Gap down AND first bar closes red -> buy PUTS. The first-bar confirmation is
    what separates 'go' from 'fade'. Entry on first-bar close (fill next bar).
    Stop = first bar's opposite extreme.
    """
    MIN_GAP = 0.0025
    MAX_GAP = 0.015
    out: list[Signal] = []
    for dc, gap, fidx, fbar in _gap_setup(days):
        if not (MIN_GAP <= abs(gap) <= MAX_GAP):
            continue
        green = float(fbar["close"]) > float(fbar["open"])
        red = float(fbar["close"]) < float(fbar["open"])
        if gap > 0 and green:
            out.append(Signal(bar_idx=fidx, side="C", stop_level=float(fbar["low"]),
                              note=f"gap={gap:+.4f}+green"))
        elif gap < 0 and red:
            out.append(Signal(bar_idx=fidx, side="P", stop_level=float(fbar["high"]),
                              note=f"gap={gap:+.4f}+red"))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# H3 — OPENING-RANGE BREAKOUT + RVOL (Zarattini)
# ─────────────────────────────────────────────────────────────────────────────
def detect_orb_rvol(spy_df, ribbon_df, vix, days) -> list[Signal]:
    """ORB on elevated-RVOL days only.

    Opening range = first ORB_MIN minutes (high/low). After the OR closes, the
    FIRST bar to CLOSE beyond the OR high/low triggers a breakout entry — but only
    if the day's opening-range volume is elevated vs a trailing baseline (RVOL >=
    RVOL_MIN). One entry per day (first break). Stop = opposite side of the OR.

    RVOL is computed from the OR bars' total volume vs the median OR-window volume
    of the prior RVOL_LOOKBACK days (look-ahead-safe: prior days only).
    """
    ORB_MIN = 30                # 30-min opening range (09:30-10:00)
    RVOL_MIN = 1.20             # OR volume >= 1.2x trailing median => "in play"
    RVOL_LOOKBACK = 20
    or_vol_history: list[float] = []
    out: list[Signal] = []
    for dc in days:
        rth = dc.rth
        or_end_min = 9 * 60 + 30 + ORB_MIN
        or_bars = rth[rth["minute"] < or_end_min]
        if len(or_bars) < 3:
            or_vol_history.append(float(or_bars["volume"].sum()) if len(or_bars) else 0.0)
            continue
        or_high = float(or_bars["high"].max())
        or_low = float(or_bars["low"].min())
        or_vol = float(or_bars["volume"].sum())

        # RVOL vs trailing median (prior days only -> causal)
        rvol = None
        if len(or_vol_history) >= 5:
            med = float(np.median([v for v in or_vol_history[-RVOL_LOOKBACK:] if v > 0]) or 0.0)
            if med > 0:
                rvol = or_vol / med
        or_vol_history.append(or_vol)
        if rvol is None or rvol < RVOL_MIN:
            continue

        # first post-OR bar to CLOSE beyond the range
        post = rth[rth["minute"] >= or_end_min]
        for gi, row in post.iterrows():
            c = float(row["close"])
            if c > or_high:
                out.append(Signal(bar_idx=int(gi), side="C", stop_level=or_low,
                                  note=f"ORBup rvol={rvol:.2f}"))
                break
            if c < or_low:
                out.append(Signal(bar_idx=int(gi), side="P", stop_level=or_high,
                                  note=f"ORBdn rvol={rvol:.2f}"))
                break
    return out


# ─────────────────────────────────────────────────────────────────────────────
# H4 — VWAP TREND-DAY PULLBACK
# ─────────────────────────────────────────────────────────────────────────────
def detect_vwap_pullback(spy_df, ribbon_df, vix, days) -> list[Signal]:
    """On a one-sided-VWAP trend day, enter the pullback that tags VWAP.

    Trend established when the first TREND_BARS RTH bars all CLOSE on the same side
    of session VWAP (clean trend day). After that, the FIRST bar whose low (uptrend)
    or high (downtrend) touches within TOUCH_TOL of VWAP while still closing on the
    trend side triggers an in-trend pullback entry. One entry per day.

    Causal: session VWAP at each bar uses only that session's prior bars; the trend
    check and the touch are both evaluated at-or-before the entry bar's close.
    """
    TREND_BARS = 6              # first 30 min all one side of VWAP
    TOUCH_TOL = 0.0008          # within 0.08% of VWAP counts as a tag
    out: list[Signal] = []
    for dc in days:
        rth = dc.rth.copy()
        if len(rth) < TREND_BARS + 3:
            continue
        vwap = session_vwap_asof(rth).values
        closes = rth["close"].values
        highs = rth["high"].values
        lows = rth["low"].values
        head = closes[:TREND_BARS]
        vhead = vwap[:TREND_BARS]
        if np.all(head > vhead):
            side = "C"
        elif np.all(head < vhead):
            side = "P"
        else:
            continue
        # scan after the trend window for the first VWAP tag in-trend
        idxs = rth.index.tolist()
        for j in range(TREND_BARS, len(rth)):
            v = vwap[j]
            if v <= 0:
                continue
            if side == "C":
                tagged = lows[j] <= v * (1 + TOUCH_TOL) and closes[j] > v
                stop = float(np.min(lows[:j + 1]))
            else:
                tagged = highs[j] >= v * (1 - TOUCH_TOL) and closes[j] < v
                stop = float(np.max(highs[:j + 1]))
            if tagged:
                out.append(Signal(bar_idx=int(idxs[j]), side=side, stop_level=stop,
                                  note="vwap_pullback"))
                break
    return out


# ─────────────────────────────────────────────────────────────────────────────
# H5 — POWER-HOUR CONTINUATION
# ─────────────────────────────────────────────────────────────────────────────
def detect_power_hour(spy_df, ribbon_df, vix, days) -> list[Signal]:
    """Last-hour entry in the direction of the day's established trend.

    At PH_START, if the day is trending (open->PH_START move beyond MIN_MOVE) AND
    the ribbon stack agrees with that direction, enter in the trend direction for
    the final-hour push. One entry per day. Stop = the session extreme against the
    trade as of PH_START.

    Causal: move + ribbon are read at the PH_START bar close; entry is next bar.
    """
    PH_START = dt.time(15, 0)          # 3pm ET — final hour
    MIN_MOVE_PCT = 0.0030
    out: list[Signal] = []
    for dc in days:
        rth = dc.rth
        open_px = float(rth["open"].iloc[0])
        upto = rth[rth["t"] <= PH_START]
        if len(upto) < 12 or open_px <= 0:
            continue
        bar = upto.iloc[-1]
        bidx = int(upto.index[-1])
        move = float(bar["close"]) / open_px - 1.0
        if abs(move) < MIN_MOVE_PCT:
            continue
        rb = _ribbon_state(ribbon_df, bidx)
        if rb is None:
            continue
        side = "C" if move > 0 else "P"
        # require ribbon to corroborate the trend direction
        if side == "C" and rb.stack != "BULL":
            continue
        if side == "P" and rb.stack != "BEAR":
            continue
        if side == "C":
            stop = float(upto["low"].min())
        else:
            stop = float(upto["high"].max())
        out.append(Signal(bar_idx=bidx, side=side, stop_level=stop,
                          note=f"PH move={move:+.4f} stack={rb.stack}"))
    return out


def _ribbon_state(ribbon_df: pd.DataFrame, idx: int) -> Optional[RibbonState]:
    if idx < 0 or idx >= len(ribbon_df):
        return None
    row = ribbon_df.iloc[idx]
    if row["stack"] == "WARMUP" or pd.isna(row["fast"]):
        return None
    return RibbonState(
        fast=float(row["fast"]), pivot=float(row["pivot"]), slow=float(row["slow"]),
        spread_cents=float(row["spread_cents"]), stack=str(row["stack"]),
    )


# ─────────────────────────────────────────────────────────────────────────────
# REAL-FILLS SIMULATION OF A SIGNAL SET
# ─────────────────────────────────────────────────────────────────────────────
def _nearest_cached_strike(d: dt.date, atm: int, side: str, max_steps: int) -> Optional[int]:
    """First cached strike scanning atm, atm-+1, atm-+2... (proxy when ATM uncached)."""
    for step in range(0, max_steps + 1):
        cands = [atm] if step == 0 else [atm - step, atm + step]
        for cand in cands:
            if load_contract_bars(option_symbol(d, cand, side)) is not None:
                return cand
    return None


@dataclass
class TradeRow:
    date: str
    time_et: str
    side: str
    strike: int
    atm: int
    strike_off: int
    entry_premium: float
    dollar_pnl: float
    pct_return: float
    exit_reason: str
    hold_min: int
    note: str


def simulate_signals(
    signals: list[Signal],
    spy_df: pd.DataFrame,
    ribbon_df: pd.DataFrame,
    vix: pd.Series,
    qty: int,
    strike_offset: int,
    max_strike_steps: int,
) -> tuple[list[TradeRow], dict]:
    """Simulate every signal at the requested strike tier on real fills.

    strike_offset is applied to the ATM strike in the SIMULATOR's sign convention
    (puts: ITM = strike above spot => offset -1 raises strike; calls mirror). We
    pre-resolve the nearest CACHED strike at that offset for honest fills and pass
    it as strike_override. Returns (trade_rows, coverage_stats).
    """
    rows: list[TradeRow] = []
    n_total = len(signals)
    n_filled = 0
    n_cache_miss = 0
    n_sim_none = 0
    for sg in signals:
        bar = spy_df.iloc[sg.bar_idx]
        d = bar["timestamp_et"].date()
        spot = float(bar["close"])
        atm = _strike_from_spot(spot)
        # target strike in simulator convention, then snap to nearest cached
        if sg.side == "P":
            target = atm - strike_offset
        else:
            target = atm + strike_offset
        strike = _nearest_cached_strike(d, target, sg.side, max_strike_steps)
        if strike is None:
            n_cache_miss += 1
            continue
        entry_vix = float(vix.iloc[sg.bar_idx]) if sg.bar_idx < len(vix) else 0.0
        fill = simulate_trade_real(
            entry_bar_idx=sg.bar_idx,
            entry_bar=bar,
            spy_df=spy_df,
            ribbon_df=ribbon_df,
            rejection_level=sg.stop_level,
            triggers_fired=[sg.note or "discovery"],
            side=sg.side,
            qty=qty,
            setup="DISCOVERY",
            strike_override=strike,
            entry_vix=entry_vix,
        )
        if fill is None or fill.dollar_pnl is None:
            n_sim_none += 1
            continue
        n_filled += 1
        rows.append(TradeRow(
            date=str(d),
            time_et=str(bar["t"]),
            side=sg.side,
            strike=int(strike),
            atm=int(atm),
            strike_off=int(strike - atm),
            entry_premium=round(float(fill.entry_premium), 4),
            dollar_pnl=round(float(fill.dollar_pnl), 2),
            pct_return=round(float(fill.pct_return_on_premium), 5),
            exit_reason=fill.exit_reason.name if fill.exit_reason else "NONE",
            hold_min=int(fill.hold_minutes or 0),
            note=sg.note,
        ))
    cov = {
        "signals": n_total,
        "filled": n_filled,
        "cache_miss": n_cache_miss,
        "sim_none": n_sim_none,
        "fill_rate": round(n_filled / n_total, 3) if n_total else 0.0,
    }
    return rows, cov


# ─────────────────────────────────────────────────────────────────────────────
# METRICS  (expectancy, WR, per-quarter, IS/OOS sign-stability, DSR)
# ─────────────────────────────────────────────────────────────────────────────
def _quarter(date_str: str) -> str:
    y, m, _ = date_str.split("-")
    q = (int(m) - 1) // 3 + 1
    return f"{y}Q{q}"


def summarize(rows: list[TradeRow], oos_cut_date: str, n_trials: int) -> dict:
    """Standalone metrics for one signal set. Uses % return on premium for
    expectancy/Sharpe (qty-independent edge measure) and $ P&L for context."""
    if not rows:
        return {"n": 0, "verdict": "NO_TRADES"}
    pct = np.array([r.pct_return for r in rows], dtype=float)
    pnl = np.array([r.dollar_pnl for r in rows], dtype=float)
    wins = int((pnl > 0).sum())
    n = len(rows)

    exp_pct = float(pct.mean())
    exp_dollar = float(pnl.mean())
    wr = round(100.0 * wins / n, 1)

    # direction split (calls vs puts) — guards against a single-direction beta
    # artifact: a real intraday edge should hold on BOTH sides over 16 months.
    by_side: dict[str, dict] = {}
    for sd in ("C", "P"):
        sp = np.array([r.dollar_pnl for r in rows if r.side == sd], dtype=float)
        if sp.size:
            by_side[sd] = {
                "n": int(sp.size),
                "exp_dollar": round(float(sp.mean()), 2),
                "win_rate_pct": round(100.0 * float((sp > 0).mean()), 1),
                "total_dollar": round(float(sp.sum()), 2),
            }
    both_dirs_positive = bool(
        all(b["exp_dollar"] > 0 for b in by_side.values()) and len(by_side) == 2
    )

    # per-quarter expectancy ($) and sign
    by_q: dict[str, list[float]] = {}
    for r in rows:
        by_q.setdefault(_quarter(r.date), []).append(r.dollar_pnl)
    quarters = {q: {"n": len(v), "exp_dollar": round(float(np.mean(v)), 2),
                    "total": round(float(np.sum(v)), 2)}
                for q, v in sorted(by_q.items())}
    q_signs = [1 if v["exp_dollar"] > 0 else 0 for v in quarters.values()]
    q_positive_frac = round(sum(q_signs) / len(q_signs), 2) if q_signs else 0.0

    # IS/OOS chronological split + sign stability (L166)
    is_rows = [r for r in rows if r.date < oos_cut_date]
    oos_rows = [r for r in rows if r.date >= oos_cut_date]
    is_exp = float(np.mean([r.pct_return for r in is_rows])) if is_rows else 0.0
    oos_exp = float(np.mean([r.pct_return for r in oos_rows])) if oos_rows else 0.0
    is_exp_d = float(np.mean([r.dollar_pnl for r in is_rows])) if is_rows else 0.0
    oos_exp_d = float(np.mean([r.dollar_pnl for r in oos_rows])) if oos_rows else 0.0
    oos_sign_stable = bool(
        is_rows and oos_rows and (is_exp > 0) and (oos_exp > 0)
    )

    # DSR / PSR verdict on the % return stream (selection-bias corrected)
    dsr_block: dict = {}
    try:
        if pct.std(ddof=0) > 0 and n >= 2:
            gr = evaluate_candidate(pct, n_trials=n_trials)
            dsr_block = gr.to_dict()
        else:
            dsr_block = {"verdict": "DEGENERATE", "note": "zero-variance returns"}
    except Exception as exc:  # noqa: BLE001 — surface, never crash the run
        dsr_block = {"verdict": "ERROR", "error": str(exc)}

    dsr_verdict = dsr_block.get("verdict", "UNKNOWN")

    # ── Outlier / concentration robustness (drop-top-N winners) ──────────────
    # A real edge must survive removing its few biggest winners; a fragile one is
    # carried by 1-5 lottery trades and goes negative once they are dropped. We
    # require the mean $ P&L AFTER dropping the top 5 winners to stay POSITIVE.
    spnl = np.sort(pnl)
    def _drop_top_mean(k: int) -> float:
        if k <= 0 or k >= n:
            return float(spnl.mean())
        return float(spnl[:-k].mean())
    drop_top5_mean = round(_drop_top_mean(5), 2)
    drop_top3_mean = round(_drop_top_mean(3), 2)
    drop_top1_mean = round(_drop_top_mean(1), 2)
    gross_wins = float(pnl[pnl > 0].sum())
    top5_share = round(float(spnl[-5:].sum()) / gross_wins, 3) if gross_wins > 0 else 0.0
    robust_to_outliers = bool(n >= 10 and drop_top5_mean > 0)

    # CANDIDATE gate (honest): standalone exp>0 (% AND $) AND OOS sign-stable AND
    # DSR not-FAIL AND robust to dropping the top-5 winners (not lottery-driven).
    survivor = bool(
        exp_pct > 0 and exp_dollar > 0 and oos_sign_stable
        and dsr_verdict != "FAIL" and robust_to_outliers
    )

    return {
        "n": n,
        "wins": wins,
        "win_rate_pct": wr,
        "exp_pct_return": round(exp_pct, 5),
        "exp_dollar_per_trade": round(exp_dollar, 2),
        "total_dollar_pnl": round(float(pnl.sum()), 2),
        "drop_top1_mean_dollar": drop_top1_mean,
        "drop_top3_mean_dollar": drop_top3_mean,
        "drop_top5_mean_dollar": drop_top5_mean,
        "top5_winner_share_of_gross_wins": top5_share,
        "robust_to_outliers": robust_to_outliers,
        "by_side": by_side,
        "both_dirs_positive": both_dirs_positive,
        "is_n": len(is_rows),
        "oos_n": len(oos_rows),
        "is_exp_pct": round(is_exp, 5),
        "oos_exp_pct": round(oos_exp, 5),
        "is_exp_dollar": round(is_exp_d, 2),
        "oos_exp_dollar": round(oos_exp_d, 2),
        "oos_sign_stable": oos_sign_stable,
        "quarters": quarters,
        "q_positive_frac": q_positive_frac,
        "dsr": dsr_block,
        "dsr_verdict": dsr_verdict,
        "SURVIVOR": survivor,
    }


# ─────────────────────────────────────────────────────────────────────────────
# DRIVER
# ─────────────────────────────────────────────────────────────────────────────
HYPOTHESES: dict[str, tuple[str, Detector, str]] = {
    # key: (human title, detector, suggested regime fit)
    "H1_intraday_momentum": (
        "Intraday momentum standalone afternoon entry (Gao-Han-Li-Zhou)",
        detect_intraday_momentum, "bull_trend / bear_trend"),
    "H2a_gap_fade": (
        "Opening-gap fade toward prior close", detect_gap_fade, "range_pin / neutral"),
    "H2b_gap_and_go": (
        "Opening-gap continuation after confirming first bar", detect_gap_and_go,
        "bull_trend / bear_trend"),
    "H3_orb_rvol": (
        "Opening-range breakout on elevated RVOL (Zarattini)", detect_orb_rvol,
        "high_vol / bull_trend / bear_trend"),
    "H4_vwap_pullback": (
        "VWAP trend-day pullback in trend direction", detect_vwap_pullback,
        "bull_trend / bear_trend"),
    "H5_power_hour": (
        "Power-hour continuation (ribbon-corroborated)", detect_power_hour,
        "bull_trend / bear_trend"),
}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--spy", default=str(REPO / "data" / "spy_5m_2025-01-01_2026-06-16.csv"))
    ap.add_argument("--vix", default=str(REPO / "data" / "vix_5m_2025-01-01_2026-06-16.csv"))
    ap.add_argument("--qty", type=int, default=3)
    ap.add_argument("--max-strike-steps", type=int, default=4)
    ap.add_argument("--out", default=str(PROJECT / "analysis" / "recommendations" /
                                         "infinite-ammo-discovery.json"))
    args = ap.parse_args()

    print(f"Loading SPY {args.spy}")
    spy = load_spy(args.spy)
    vix = align_vix(spy, args.vix)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    days = build_day_contexts(spy)
    print(f"SPY bars={len(spy)} days={len(days)} "
          f"range {spy['date'].min()}..{spy['date'].max()} VIX aligned={len(vix)}")

    # OOS cutoff = chronological 70/30 by DAY (not by row) for clean IS/OOS by date.
    all_dates = [dc.date for dc in days]
    cut_i = int(len(all_dates) * OOS_SPLIT_FRAC)
    oos_cut_date = str(all_dates[cut_i])
    print(f"OOS cut date = {oos_cut_date} (IS {cut_i} days / OOS {len(all_dates)-cut_i} days)")

    # Strike tiers to evaluate per hypothesis: ATM (offset 0) and ITM-1.
    # offset is in simulator convention (puts: +offset above spot; -1 => ITM-1).
    strike_tiers = {"ATM": 0, "ITM1": -1}
    # n_trials for DSR deflation (selection-bias correction). We count not just the
    # 6 hypotheses x 2 tiers shipped, but the broader implicit search: each detector
    # embeds both directions and 1-2 threshold choices made during design. A
    # defensible conservative count is ~30 (6 families x ~2 thresholds x 2 dirs x ...).
    # Larger n_trials => stricter deflation; we deliberately err strict.
    n_trials = 30

    results: dict = {}
    for key, (title, detector, regime_fit) in HYPOTHESES.items():
        print(f"\n=== {key}: {title} ===")
        signals = detector(spy, ribbon, vix, days)
        side_counts = {"P": sum(1 for s in signals if s.side == "P"),
                       "C": sum(1 for s in signals if s.side == "C")}
        print(f"  signals={len(signals)} (P={side_counts['P']} C={side_counts['C']})")
        tier_blocks: dict = {}
        for tname, off in strike_tiers.items():
            rows, cov = simulate_signals(
                signals, spy, ribbon, vix, args.qty, off, args.max_strike_steps)
            summ = summarize(rows, oos_cut_date, n_trials)
            tier_blocks[tname] = {"coverage": cov, "metrics": summ}
            v = summ.get("dsr_verdict", "?")
            print(f"  [{tname}] filled={cov['filled']}/{cov['signals']} "
                  f"exp%={summ.get('exp_pct_return')} exp$={summ.get('exp_dollar_per_trade')} "
                  f"WR={summ.get('win_rate_pct')}% OOS_stable={summ.get('oos_sign_stable')} "
                  f"DSR={v} SURVIVOR={summ.get('SURVIVOR')}")
        results[key] = {
            "title": title,
            "regime_fit": regime_fit,
            "signal_count": len(signals),
            "side_counts": side_counts,
            "tiers": tier_blocks,
        }

    # Survivor roll-up: a hypothesis survives if ANY strike tier is a SURVIVOR.
    survivors = []
    for key, blk in results.items():
        for tname, tb in blk["tiers"].items():
            if tb["metrics"].get("SURVIVOR"):
                m = tb["metrics"]
                survivors.append({
                    "hypothesis": key, "title": blk["title"], "tier": tname,
                    "regime_fit": blk["regime_fit"],
                    "n": m["n"], "exp_dollar_per_trade": m["exp_dollar_per_trade"],
                    "exp_pct_return": m["exp_pct_return"], "win_rate_pct": m["win_rate_pct"],
                    "oos_sign_stable": m["oos_sign_stable"], "dsr_verdict": m["dsr_verdict"],
                })

    output = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "script": "backtest/autoresearch/infinite_ammo_discovery.py",
        "purpose": (
            "First-principles intraday SPY edge DISCOVERY (infinite-ammo), NOT gated "
            "on J anchors. Standalone real-fills (OPRA) validation of 5 microstructure "
            "hypotheses. Propose-only (Rule 9); survivors are WATCH-ONLY candidates for "
            "the regime-aware book."
        ),
        "method": {
            "fills": "lib.simulator_real.simulate_trade_real (real OPRA bars, causal "
                     "next-bar-open entry, chart/level + premium stops, v15 exit stack)",
            "strike_tiers": strike_tiers,
            "strike_resolution": "nearest cached strike to target offset (proxy disclosed "
                                 "via strike_off); max_strike_steps="
                                 f"{args.max_strike_steps}",
            "qty": args.qty,
            "oos_split": f"chronological {OOS_SPLIT_FRAC:.0%}/{(1-OOS_SPLIT_FRAC):.0%} by day; "
                         f"cut={oos_cut_date}",
            "dsr": "lib.validation.gate.evaluate_candidate on % return stream; "
                   f"n_trials={n_trials} (selection-bias correction)",
            "candidate_gate": "exp_pct>0 AND exp_dollar>0 AND oos_sign_stable AND DSR!=FAIL",
        },
        "disclosure_OP20": {
            "real_fills": True,
            "opra_window": "options cached through ~2026-05-29; signals after that have "
                           "no fills and are dropped (counted in coverage.cache_miss).",
            "proxy_strikes": "ATM not always cached; nearest-cached strike used and the "
                             "true offset reported per trade (strike_off). ITM/OTM proxy "
                             "shifts P&L modestly (L58) — directionally valid.",
            "no_look_ahead": "all detector features computed at-or-before the trigger bar "
                             "close; entry is the NEXT bar open (sim-enforced).",
            "caveat": "standalone single-setup eval on proxy levels — candidates worth a "
                      "real-level re-test, NOT ready-to-trade setups.",
        },
        "data": {
            "spy": Path(args.spy).name,
            "vix": Path(args.vix).name,
            "days": len(days),
            "date_range": [str(spy["date"].min()), str(spy["date"].max())],
        },
        "hypotheses": results,
        "survivors": survivors,
        "survivor_count": len(survivors),
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2, default=str))
    print(f"\nWrote {out_path}")
    print(f"SURVIVORS: {len(survivors)}")
    for s in survivors:
        print(f"  - {s['hypothesis']} [{s['tier']}] exp$={s['exp_dollar_per_trade']} "
              f"WR={s['win_rate_pct']}% n={s['n']} DSR={s['dsr_verdict']} "
              f"regime={s['regime_fit']}")


if __name__ == "__main__":
    main()
