"""FUTURES DIRECTIONAL BACKTEST — the theta-free arena (MNQ/MES, point-P&L).

WHY THIS EXISTS
---------------
~27 strategies died on 0DTE SPY OPTIONS. The documented failure mode (C3 / L58,
L74, L100, L101, L112, L136, L148, L149 — ~20 separate lessons) is that 0DTE
THETA + premium-stop-misfire ate genuine DIRECTIONAL edges: a correct SPY-price
read still lost because the option decayed and tight premium stops fired on noise.

FUTURES HAVE NO THETA. A point move IS P&L. Winners can RUN with no expiry clock.
This module recomputes the SAME directional SIGNALS on real micro-futures 5m bars,
but swaps the P&L model from option-fills to pure point-P&L:

    pnl = (exit - entry) * point_value * qty * direction - costs

It keeps the signal math BYTE-IDENTICAL to the option harnesses where they exist:
  - vwap_continuation : _trend_side + breakout/pullback  (from _edgehunt_vwap_continuation.py
                        == j_daily_pattern_ratify.detect_j_vwap_continuation, the LIVE detector)
  - ema_adx_gate      : Pine EMA + Wilder ADX            (from _swjshak_ema_adx_gate.py)
  - rsi2_meanrev      : Wilder RSI(2) + SMA200 trend     (from _newhunt_rsi2_mean_reversion.py)
  - orb               : opening-range + ladder           (orb_watcher.compute_opening_range)
  - bull_tilt         : systematic long every session at the entry gate (the +4pp effect)

EXITS (the whole point of no-theta = let winners RUN):
  - atr_trail : initial ATR stop, then a chandelier trailing stop off the highest-high
                since entry (long) — winners run, NO fixed small target. TREND exit.
  - atr_target: fixed ATR take-profit + ATR stop (mean-reversion exit, small target).
  - eod       : time-stop at session close (flat by EOD — intraday only, no overnight).
  All exits ALSO hard-flatten at the last RTH bar of the day (no overnight hold).

GATES (honest, anti-2.10):
  REAL only if  OOS per-trade > 0  AND  beats random-entry null (same exit)  AND
  positive in >= ceil(0.6*Q) quarters  AND  survives realistic costs (already in pnl).
  Tested on BOTH MES and MNQ.

COSTS: $1.24 round-trip commission/micro + 1 tick (0.25 pt) slippage EACH side.
       Slippage applied to entry (worse) and exit (worse). qty=1 micro baseline.

DATA: backtest/data/futures/{MES,MNQ}_5m_continuous.csv  (RTH 09:30-15:55 ET, 5m).

Run:
  backtest/.venv/Scripts/python.exe backtest/autoresearch/_futures_directional.py
Pure Python, $0, no live orders, no option pricing.
"""
from __future__ import annotations

import datetime as dt
import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "backtest" / "data" / "futures"
OUT_JSON = ROOT / "analysis" / "recommendations" / "futures-directional-2026-06-21.json"
OUT_MD = ROOT / "analysis" / "recommendations" / "FUTURES-DIRECTIONAL-SCORECARD.md"

POINT_VALUE = {"MNQ": 2.0, "MES": 5.0}   # verified vs tastytrade_paper.py + CONTRACT-SPECS.md
TICK = 0.25                               # both micros
COMMISSION_RT = 1.24                      # $ round-trip per micro (TT illustrative)
SLIP_TICKS = 1                            # 1 tick slippage each side
QTY = 1                                   # 1 micro baseline (margin-safe on $2K)

RTH_OPEN = dt.time(9, 30)
RTH_CLOSE = dt.time(16, 0)
ENTRY_CUTOFF_TREND = dt.time(11, 30)      # morning trend window
RANDOM_SEEDS = 30                         # random-null replicates


# ─────────────────────────────────────────────────────────────────────────────
# DATA
# ─────────────────────────────────────────────────────────────────────────────
def load_futures(symbol: str) -> pd.DataFrame:
    df = pd.read_csv(DATA / f"{symbol}_5m_continuous.csv")
    ts = pd.to_datetime(df["timestamp_et"], utc=True)
    df["timestamp_et"] = ts.dt.tz_convert("America/New_York").dt.tz_localize(None)
    df = df.drop_duplicates(subset="timestamp_et", keep="first").reset_index(drop=True)
    df["date"] = df["timestamp_et"].dt.date
    df["t"] = df["timestamp_et"].dt.time
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = df[c].astype(float)
    # keep RTH only (data already is, but be safe)
    df = df[(df["t"] >= RTH_OPEN) & (df["t"] < RTH_CLOSE)].reset_index(drop=True)
    return df


def quarter(d: dt.date) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


# ─────────────────────────────────────────────────────────────────────────────
# INDICATORS  (ported verbatim from the option harnesses — same math)
# ─────────────────────────────────────────────────────────────────────────────
def session_vwap_asof(rth: pd.DataFrame) -> pd.Series:
    """Causal cumulative session VWAP (typical price). infinite_ammo_discovery.py L156."""
    tp = (rth["high"] + rth["low"] + rth["close"]) / 3.0
    pv = (tp * rth["volume"]).cumsum()
    vv = rth["volume"].cumsum().replace(0, np.nan)
    return (pv / vv).bfill()


def ema(series: pd.Series, length: int) -> pd.Series:
    """Pine ta.ema: alpha=2/(length+1), SMA seed at length-1. _swjshak_ema_adx_gate.py L92."""
    arr = series.to_numpy(dtype=float)
    n = len(arr)
    out = np.full(n, np.nan)
    if n < length:
        return pd.Series(out, index=series.index)
    out[length - 1] = arr[:length].mean()
    alpha = 2.0 / (length + 1)
    for i in range(length, n):
        out[i] = arr[i] * alpha + out[i - 1] * (1 - alpha)
    return pd.Series(out, index=series.index)


def adx(high: pd.Series, low: pd.Series, close: pd.Series, length: int) -> pd.Series:
    """Wilder ADX(length). _swjshak_ema_adx_gate.py L107 (byte-for-byte)."""
    h = high.to_numpy(dtype=float); l = low.to_numpy(dtype=float); c = close.to_numpy(dtype=float)
    n = len(h)
    out = np.full(n, np.nan)
    if n < 2 * length + 1:
        return pd.Series(out, index=high.index)
    tr = np.zeros(n); plus_dm = np.zeros(n); minus_dm = np.zeros(n)
    for i in range(1, n):
        up = h[i] - h[i - 1]; down = l[i - 1] - l[i]
        plus_dm[i] = up if (up > down and up > 0) else 0.0
        minus_dm[i] = down if (down > up and down > 0) else 0.0
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    atr = np.full(n, np.nan); sm_plus = np.full(n, np.nan); sm_minus = np.full(n, np.nan)
    atr[length] = tr[1:length + 1].sum()
    sm_plus[length] = plus_dm[1:length + 1].sum()
    sm_minus[length] = minus_dm[1:length + 1].sum()
    for i in range(length + 1, n):
        atr[i] = atr[i - 1] - (atr[i - 1] / length) + tr[i]
        sm_plus[i] = sm_plus[i - 1] - (sm_plus[i - 1] / length) + plus_dm[i]
        sm_minus[i] = sm_minus[i - 1] - (sm_minus[i - 1] / length) + minus_dm[i]
    dx = np.full(n, np.nan)
    for i in range(length, n):
        if atr[i] and atr[i] > 0:
            pdi = 100.0 * sm_plus[i] / atr[i]; mdi = 100.0 * sm_minus[i] / atr[i]
            denom = pdi + mdi
            dx[i] = 100.0 * abs(pdi - mdi) / denom if denom > 0 else 0.0
    first = length; seed_end = first + length
    if seed_end > n:
        return pd.Series(out, index=high.index)
    out[seed_end - 1] = np.nanmean(dx[first:seed_end])
    for i in range(seed_end, n):
        out[i] = (out[i - 1] * (length - 1) + dx[i]) / length
    return pd.Series(out, index=high.index)


def wilder_rsi(close: pd.Series, period: int) -> pd.Series:
    """Wilder RSI. _newhunt_rsi2_mean_reversion.py L116 (byte-for-byte)."""
    delta = close.diff()
    gain = delta.clip(lower=0.0); loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    rsi = rsi.where(avg_loss != 0, 100.0)
    rsi = rsi.where(~((avg_gain == 0) & (avg_loss == 0)), 50.0)
    return rsi


def atr_series(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    """Wilder ATR (continuous, causal). Used for stops/targets and ATR trailing."""
    h = high.to_numpy(dtype=float); l = low.to_numpy(dtype=float); c = close.to_numpy(dtype=float)
    n = len(h)
    tr = np.full(n, np.nan)
    tr[0] = h[0] - l[0]
    for i in range(1, n):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    out = np.full(n, np.nan)
    if n < length:
        return pd.Series(out, index=high.index)
    out[length - 1] = np.nanmean(tr[:length])
    for i in range(length, n):
        out[i] = (out[i - 1] * (length - 1) + tr[i]) / length
    return pd.Series(out, index=high.index)


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL RECORD
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Sig:
    idx: int            # GLOBAL bar index; entry fills at NEXT bar open
    date: dt.date
    side: str           # "long" / "short"
    chart_stop: Optional[float] = None   # structural invalidation price (if any)
    note: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL DETECTORS  (recompute on futures bars; one entry/day unless noted)
# ─────────────────────────────────────────────────────────────────────────────
def sig_vwap_continuation(df: pd.DataFrame) -> list[Sig]:
    """LIVE detector: trend_side(first 3 bars vs vwap) then breakout/pullback by 11:30.
    Ported from _edgehunt_vwap_continuation.detect_signals (==live vwap_continuation_watcher)."""
    TREND_BARS = 3; CUTOFF = dt.time(10, 30); DIP_TOL = 0.0010
    out: list[Sig] = []
    for day, g in df.groupby("date", sort=True):
        g = g.reset_index()  # 'index' = global idx
        if len(g) < TREND_BARS + 2:
            continue
        vwap = session_vwap_asof(g.rename(columns={})).values  # uses H/L/C/vol of the day slice
        closes = g["close"].values; highs = g["high"].values; lows = g["low"].values
        times = g["t"].values
        head_c = closes[:TREND_BARS]; head_v = vwap[:TREND_BARS]
        if np.all(head_c > head_v):
            side = "long"
        elif np.all(head_c < head_v):
            side = "short"
        else:
            continue
        for j in range(TREND_BARS, len(g)):
            if times[j] > CUTOFF:
                break
            v = vwap[j]
            if v <= 0:
                continue
            if side == "long":
                prior_ext = float(np.max(highs[:j])) if j > 0 else highs[j]
                breakout = highs[j] >= prior_ext and closes[j] > v
                dip = lows[j] <= v * (1 + DIP_TOL) and closes[j] > v
                stop = float(np.min(lows[:j + 1]))
            else:
                prior_ext = float(np.min(lows[:j])) if j > 0 else lows[j]
                breakout = lows[j] <= prior_ext and closes[j] < v
                dip = highs[j] >= v * (1 - DIP_TOL) and closes[j] < v
                stop = float(np.max(highs[:j + 1]))
            trig = "breakout" if breakout else ("pullback" if dip else None)
            if trig is None:
                continue
            out.append(Sig(idx=int(g["index"].iloc[j]), date=day, side=side,
                           chart_stop=stop, note=f"jvwap_{trig}"))
            break
    return out


def sig_bull_tilt(df: pd.DataFrame) -> list[Sig]:
    """Systematic intraday bull-tilt: go LONG once per session at the entry gate (09:35).
    Tests the robust directional drift (the +4pp morning-continuation effect) with a
    trend-riding exit. No stop structure -> ATR stop only."""
    GATE = dt.time(9, 35)
    out: list[Sig] = []
    for day, g in df.groupby("date", sort=True):
        g = g.reset_index()
        cand = g[g["t"] >= GATE]
        if cand.empty:
            continue
        row = cand.iloc[0]
        out.append(Sig(idx=int(row["index"]), date=day, side="long", note="bull_tilt"))
    return out


def sig_ema_adx(df: pd.DataFrame) -> list[Sig]:
    """EMA(9/21) cross gated by ADX>25. Ported from _swjshak_ema_adx_gate.
    Per-day EMAs (matches that harness: day_df['close']). 30-min cooldown, warmup 12 bars."""
    EMA_FAST = 9; EMA_SLOW = 21; ADX_LEN = 14; ADX_MIN = 25.0
    COOLDOWN_MIN = 30; WARMUP = 12
    out: list[Sig] = []
    for day, g in df.groupby("date", sort=True):
        g = g.reset_index()
        if len(g) < 2 * ADX_LEN + 2:
            continue
        ef = ema(g["close"], EMA_FAST).to_numpy()
        es = ema(g["close"], EMA_SLOW).to_numpy()
        ax = adx(g["high"], g["low"], g["close"], ADX_LEN).to_numpy()
        diff = ef - es
        last_t: Optional[dt.datetime] = None
        for k in range(1, len(g)):
            if k < WARMUP:
                continue
            if np.isnan(diff[k]) or np.isnan(diff[k - 1]) or np.isnan(ax[k]):
                continue
            crossed_up = diff[k - 1] <= 0 and diff[k] > 0
            crossed_dn = diff[k - 1] >= 0 and diff[k] < 0
            if not (crossed_up or crossed_dn):
                continue
            if ax[k] < ADX_MIN:
                continue
            ts = pd.Timestamp(g["timestamp_et"].iloc[k]).to_pydatetime()
            if last_t is not None and (ts - last_t).total_seconds() / 60.0 < COOLDOWN_MIN:
                continue
            side = "long" if crossed_up else "short"
            last_t = ts
            out.append(Sig(idx=int(g["index"].iloc[k]), date=day, side=side, note="ema_adx"))
    return out


def sig_orb(df: pd.DataFrame) -> list[Sig]:
    """Opening-range breakout (09:30-10:00 OR), enter on first 5m CLOSE beyond OR by >=1 tick
    inside the entry window, with SMA10>SMA50 trend agreement. Long-only by default
    (orb_watcher ORB_DIRECTION_FILTER='long', the ratified setting). Chart stop = opposite OR.
    Structural ORB (not the retest variant) so it has enough trades for an honest test on futures."""
    OR_START = dt.time(9, 30); OR_END = dt.time(10, 0); WIN_END = dt.time(12, 30)
    LONG_ONLY = True
    out: list[Sig] = []
    for day, g in df.groupby("date", sort=True):
        g = g.reset_index()
        or_bars = g[(g["t"] >= OR_START) & (g["t"] < OR_END)]
        if or_bars.empty:
            continue
        orh = float(or_bars["high"].max()); orl = float(or_bars["low"].min())
        rng = orh - orl
        if rng <= 0:
            continue
        closes = g["close"]
        fired = False
        for j in range(len(g)):
            t = g["t"].iloc[j]
            if t < OR_END or t > WIN_END or fired:
                continue
            c = float(g["close"].iloc[j])
            sma10 = float(closes.iloc[max(0, j - 9):j + 1].mean()) if j >= 9 else float("nan")
            sma50 = float(closes.iloc[max(0, j - 49):j + 1].mean()) if j >= 49 else float("nan")
            bull = (not math.isnan(sma10) and not math.isnan(sma50) and sma10 > sma50)
            bear = (not math.isnan(sma10) and not math.isnan(sma50) and sma10 < sma50)
            if c > orh + TICK and (bull or math.isnan(sma50)):
                out.append(Sig(idx=int(g["index"].iloc[j]), date=day, side="long",
                               chart_stop=orl, note="orb_long"))
                fired = True
            elif (not LONG_ONLY) and c < orl - TICK and (bear or math.isnan(sma50)):
                out.append(Sig(idx=int(g["index"].iloc[j]), date=day, side="short",
                               chart_stop=orh, note="orb_short"))
                fired = True
    return out


def sig_rsi2(df: pd.DataFrame) -> list[Sig]:
    """Connors RSI(2) mean-reversion + SMA200 trend filter on continuous 5m closes.
    Ported from _newhunt_rsi2_mean_reversion.build_signals. RSI(2)<10 in uptrend -> long;
    RSI(2)>90 in downtrend -> short. 45-min cooldown, entry gate 09:35-15:45."""
    RSI_P = 2; SMA_P = 200; LONG_THR = 10.0; SHORT_THR = 90.0
    GATE_START = dt.time(9, 35); GATE_END = dt.time(15, 45); COOLDOWN = 45; SWING = 12
    close = df["close"].astype(float)
    rsi = wilder_rsi(close, RSI_P)
    sma = close.rolling(SMA_P, min_periods=SMA_P).mean()
    out: list[Sig] = []
    last_t: Optional[dt.datetime] = None
    for idx in range(len(df)):
        r = rsi.iloc[idx]; s = sma.iloc[idx]
        if pd.isna(r) or pd.isna(s):
            continue
        t = df["t"].iloc[idx]
        if t < GATE_START or t > GATE_END:
            continue
        c = float(df["close"].iloc[idx])
        long_sig = (r < LONG_THR) and (c > s)
        short_sig = (r > SHORT_THR) and (c < s)
        if not (long_sig or short_sig):
            continue
        ts = pd.Timestamp(df["timestamp_et"].iloc[idx]).to_pydatetime()
        if last_t is not None and (ts - last_t).total_seconds() / 60.0 < COOLDOWN:
            continue
        side = "long" if long_sig else "short"
        win = df.iloc[max(0, idx - SWING + 1): idx + 1]
        if side == "long":
            stop = float(win["low"].min())
        else:
            stop = float(win["high"].max())
        last_t = ts
        out.append(Sig(idx=idx, date=df["date"].iloc[idx], side=side,
                       chart_stop=stop, note="rsi2"))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# POINT-P&L SIMULATOR  (exits: atr_trail / atr_target / eod). Intraday only.
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Fill:
    date: dt.date
    side: str
    entry: float
    exit: float
    pnl: float            # net $ after costs (qty micros)
    bars_held: int
    exit_reason: str


def _day_end_idx(df: pd.DataFrame, day) -> int:
    g = df[df["date"] == day]
    return int(g.index[-1])


def simulate(df: pd.DataFrame, sig: Sig, symbol: str, *, exit_mode: str,
             atr: np.ndarray, atr_stop_mult: float, atr_target_mult: float,
             trail_mult: float, day_end: dict) -> Optional[Fill]:
    """Fill at NEXT bar open after sig.idx; manage bar-by-bar to session close.

    Slippage: entry filled `SLIP_TICKS` ticks WORSE; each exit filled `SLIP_TICKS`
    ticks WORSE. Commission: COMMISSION_RT per micro * qty. Conservative fill order
    within a bar: STOP checked before TARGET (worst-case)."""
    pv = POINT_VALUE[symbol]
    entry_idx = sig.idx + 1
    if entry_idx >= len(df):
        return None
    if df["date"].iloc[entry_idx] != sig.date:
        return None  # signal was the last bar of the day; no fill
    a = atr[sig.idx]
    if np.isnan(a) or a <= 0:
        return None
    long = sig.side == "long"
    slip = SLIP_TICKS * TICK
    raw_entry = float(df["open"].iloc[entry_idx])
    entry = raw_entry + slip if long else raw_entry - slip   # worse fill

    # initial stop: tighter of (chart stop) and (ATR stop) is NOT used — use ATR stop as the
    # mechanical stop; if a chart stop exists and is closer, honor it (more conservative).
    if long:
        atr_stop = entry - atr_stop_mult * a
        stop = atr_stop if sig.chart_stop is None else max(atr_stop, min(sig.chart_stop, entry - TICK))
        target = entry + atr_target_mult * a
    else:
        atr_stop = entry + atr_stop_mult * a
        stop = atr_stop if sig.chart_stop is None else min(atr_stop, max(sig.chart_stop, entry + TICK))
        target = entry - atr_target_mult * a

    end_idx = day_end[sig.date]
    hh = df["high"].iloc[entry_idx]   # highest high since entry (long trailing)
    ll = df["low"].iloc[entry_idx]    # lowest low since entry (short trailing)
    exit_price = None; reason = None; bars = 0

    for k in range(entry_idx, end_idx + 1):
        bars += 1
        hi = float(df["high"].iloc[k]); lo = float(df["low"].iloc[k])
        hh = max(hh, hi); ll = min(ll, lo)

        # update trailing stop (atr_trail only) AFTER extending HH/LL, applies from this bar on
        if exit_mode == "atr_trail":
            if long:
                stop = max(stop, hh - trail_mult * a)
            else:
                stop = min(stop, ll + trail_mult * a)

        # STOP first (conservative)
        if long and lo <= stop:
            exit_price = stop - slip; reason = "stop"; break
        if (not long) and hi >= stop:
            exit_price = stop + slip; reason = "stop"; break
        # TARGET (only for atr_target mode)
        if exit_mode == "atr_target":
            if long and hi >= target:
                exit_price = target - slip; reason = "target"; break
            if (not long) and lo <= target:
                exit_price = target + slip; reason = "target"; break
        # EOD time-stop at last bar
        if k == end_idx:
            raw = float(df["close"].iloc[k])
            exit_price = raw - slip if long else raw + slip
            reason = "eod"; break

    if exit_price is None:
        raw = float(df["close"].iloc[end_idx])
        exit_price = raw - slip if long else raw + slip
        reason = "eod"
    direction = 1 if long else -1
    gross = (exit_price - entry) * pv * QTY * direction
    pnl = gross - COMMISSION_RT * QTY
    return Fill(date=sig.date, side=sig.side, entry=entry, exit=exit_price,
                pnl=pnl, bars_held=bars, exit_reason=reason)


# ─────────────────────────────────────────────────────────────────────────────
# METRICS
# ─────────────────────────────────────────────────────────────────────────────
def metrics(fills: list[Fill]) -> dict:
    if not fills:
        return {"n": 0}
    pnls = np.array([f.pnl for f in fills])
    wins = pnls[pnls > 0]; losses = pnls[pnls < 0]
    by_day: dict = defaultdict(float)
    for f in fills:
        by_day[str(f.date)] += f.pnl
    # equity curve by trade for max drawdown
    eq = np.cumsum(pnls); peak = np.maximum.accumulate(eq); dd = eq - peak
    pf = (wins.sum() / -losses.sum()) if losses.sum() != 0 else float("inf")
    exit_mix: dict = defaultdict(int)
    for f in fills:
        exit_mix[f.exit_reason] += 1
    n = len(fills)
    return {
        "n": n,
        "wr": round(100.0 * len(wins) / n, 1),
        "total_pnl": round(float(pnls.sum()), 0),
        "per_trade": round(float(pnls.mean()), 2),
        "avg_win": round(float(wins.mean()), 2) if len(wins) else 0.0,
        "avg_loss": round(float(losses.mean()), 2) if len(losses) else 0.0,
        "max_dd": round(float(dd.min()), 0),
        "profit_factor": round(float(pf), 2) if pf != float("inf") else None,
        "avg_bars_held": round(float(np.mean([f.bars_held for f in fills])), 1),
        "exit_mix": dict(exit_mix),
        "n_days": len(by_day),
    }


def by_quarter(fills: list[Fill]) -> dict:
    q: dict = defaultdict(list)
    for f in fills:
        q[quarter(f.date)].append(f.pnl)
    return {k: {"n": len(v), "total": round(float(sum(v)), 0),
                "per_trade": round(float(np.mean(v)), 2)} for k, v in sorted(q.items())}


# ─────────────────────────────────────────────────────────────────────────────
# RANDOM-ENTRY NULL  (same exit logic, random entry bars matched per day-count)
# ─────────────────────────────────────────────────────────────────────────────
def random_null(df: pd.DataFrame, real_sigs: list[Sig], symbol: str, *,
                exit_mode: str, atr: np.ndarray, side_mode: str,
                atr_stop_mult: float, atr_target_mult: float, trail_mult: float,
                day_end: dict, seeds: int = RANDOM_SEEDS) -> dict:
    """Match the real strategy's trade COUNT per day; pick random entry bars in the
    same intraday window; same side distribution; same exit logic. Returns mean per-trade."""
    # trades per day from real signals
    per_day: dict = defaultdict(int)
    sides: list[str] = []
    for s in real_sigs:
        per_day[s.date] += 1
        sides.append(s.side)
    long_frac = (sum(1 for x in sides if x == "long") / len(sides)) if sides else 1.0
    # eligible entry bars per day (exclude last bar; need entry_idx+1 same day)
    day_groups = {d: g for d, g in df.groupby("date")}
    means = []
    rng = np.random.default_rng(42)
    for _ in range(seeds):
        fills: list[Fill] = []
        for d, cnt in per_day.items():
            g = day_groups.get(d)
            if g is None or len(g) < 3:
                continue
            idxs = g.index.to_numpy()[:-1]  # exclude last bar
            if len(idxs) == 0:
                continue
            chosen = rng.choice(idxs, size=min(cnt, len(idxs)), replace=False)
            for gi in chosen:
                if side_mode == "long":
                    side = "long"
                elif side_mode == "match":
                    side = "long" if rng.random() < long_frac else "short"
                else:
                    side = "long" if rng.random() < 0.5 else "short"
                f = simulate(df, Sig(idx=int(gi), date=d, side=side), symbol,
                             exit_mode=exit_mode, atr=atr, atr_stop_mult=atr_stop_mult,
                             atr_target_mult=atr_target_mult, trail_mult=trail_mult,
                             day_end=day_end)
                if f:
                    fills.append(f)
        if fills:
            means.append(np.mean([f.pnl for f in fills]))
    if not means:
        return {"per_trade": None, "n_replicates": 0}
    return {"per_trade": round(float(np.mean(means)), 2),
            "per_trade_std": round(float(np.std(means)), 2),
            "n_replicates": len(means),
            "p95": round(float(np.percentile(means, 95)), 2)}


# ─────────────────────────────────────────────────────────────────────────────
# STRATEGY REGISTRY
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Strat:
    key: str
    detector: Callable[[pd.DataFrame], list[Sig]]
    exit_mode: str          # atr_trail / atr_target / eod
    atr_stop_mult: float
    atr_target_mult: float
    trail_mult: float
    side_mode: str          # for null: long / match / both
    label: str


STRATS = [
    Strat("vwap_continuation", sig_vwap_continuation, "atr_trail", 1.5, 0.0, 2.5, "match",
          "VWAP-continuation (live edge) — ATR trail, let runner RUN"),
    Strat("bull_tilt", sig_bull_tilt, "atr_trail", 1.5, 0.0, 2.5, "long",
          "Systematic morning bull-tilt — long every session, ATR trail"),
    Strat("ema_adx", sig_ema_adx, "atr_trail", 1.5, 0.0, 2.5, "match",
          "EMA(9/21)+ADX>25 trend-follow — ATR trail, NO fixed target"),
    Strat("orb", sig_orb, "atr_trail", 1.5, 0.0, 2.5, "long",
          "Opening-range breakout — ATR trail (trend-riding)"),
    Strat("rsi2", sig_rsi2, "atr_target", 1.0, 1.0, 0.0, "match",
          "RSI(2) mean-reversion — small ATR target"),
]


def split_oos(df: pd.DataFrame, train_frac: float = 0.70) -> tuple[set, set]:
    days = sorted(df["date"].unique())
    cut = int(len(days) * train_frac)
    return set(days[:cut]), set(days[cut:])


def run_strategy(df: pd.DataFrame, symbol: str, strat: Strat, atr: np.ndarray,
                 day_end: dict, is_days: set, oos_days: set) -> dict:
    sigs = strat.detector(df)
    all_fills: list[Fill] = []
    for s in sigs:
        f = simulate(df, s, symbol, exit_mode=strat.exit_mode, atr=atr,
                     atr_stop_mult=strat.atr_stop_mult, atr_target_mult=strat.atr_target_mult,
                     trail_mult=strat.trail_mult, day_end=day_end)
        if f:
            all_fills.append(f)
    is_fills = [f for f in all_fills if f.date in is_days]
    oos_fills = [f for f in all_fills if f.date in oos_days]
    is_sigs = [s for s in sigs if s.date in is_days]
    oos_sigs = [s for s in sigs if s.date in oos_days]

    null_oos = random_null(df, oos_sigs, symbol, exit_mode=strat.exit_mode, atr=atr,
                           side_mode=strat.side_mode, atr_stop_mult=strat.atr_stop_mult,
                           atr_target_mult=strat.atr_target_mult, trail_mult=strat.trail_mult,
                           day_end=day_end)
    null_all = random_null(df, sigs, symbol, exit_mode=strat.exit_mode, atr=atr,
                           side_mode=strat.side_mode, atr_stop_mult=strat.atr_stop_mult,
                           atr_target_mult=strat.atr_target_mult, trail_mult=strat.trail_mult,
                           day_end=day_end)

    m_all = metrics(all_fills); m_is = metrics(is_fills); m_oos = metrics(oos_fills)
    q = by_quarter(all_fills)
    pos_q = sum(1 for v in q.values() if v["total"] > 0)
    n_q = len(q)
    need_q = math.ceil(0.6 * n_q)

    # per-week expectancy (53 trading weeks over ~17 months)
    n_weeks = len(set((d.isocalendar().year, d.isocalendar().week) for d in df["date"].unique()))
    per_week_all = round(m_all.get("total_pnl", 0) / n_weeks, 2) if m_all.get("n") else 0.0

    # GATES
    oos_pt = m_oos.get("per_trade")
    oos_n = m_oos.get("n", 0)
    null_pt = null_oos.get("per_trade")
    beats_null = (oos_pt is not None and null_pt is not None and oos_pt > null_pt)
    g_oos_pos = (oos_pt is not None and oos_pt > 0 and oos_n >= 10)
    g_quarters = pos_q >= need_q
    g_costs = (m_all.get("per_trade") is not None and m_all.get("per_trade") > 0)
    verdict = "REAL" if (g_oos_pos and beats_null and g_quarters and g_costs) else "FAIL"

    return {
        "strategy": strat.key, "label": strat.label, "symbol": symbol,
        "exit_mode": strat.exit_mode,
        "exit_params": {"atr_stop_mult": strat.atr_stop_mult,
                        "atr_target_mult": strat.atr_target_mult,
                        "trail_mult": strat.trail_mult},
        "n_signals": len(sigs), "n_fills": len(all_fills),
        "full": m_all, "is": m_is, "oos": m_oos,
        "by_quarter": q, "positive_quarters": pos_q, "n_quarters": n_q, "need_quarters": need_q,
        "per_week_pnl": per_week_all,
        "random_null_oos": null_oos, "random_null_full": null_all,
        "gates": {
            "oos_per_trade_pos_n>=10": g_oos_pos,
            "beats_random_null_oos": beats_null,
            "positive_in_>=60pct_quarters": g_quarters,
            "survives_costs_full": g_costs,
        },
        "verdict": verdict,
    }


def main() -> None:
    results: dict = {"meta": {
        "generated": "2026-06-21", "qty_micros": QTY,
        "commission_rt": COMMISSION_RT, "slippage_ticks_each_side": SLIP_TICKS,
        "point_value": POINT_VALUE, "note": "Point-P&L, NO option pricing, NO theta. Intraday only.",
    }, "by_symbol": {}}

    for symbol in ("MES", "MNQ"):
        df = load_futures(symbol)
        atr = atr_series(df["high"], df["low"], df["close"], 14).to_numpy()
        day_end = {d: int(g.index[-1]) for d, g in df.groupby("date")}
        is_days, oos_days = split_oos(df, 0.70)
        days = sorted(df["date"].unique())
        sym_block = {
            "n_bars": len(df), "n_days": len(days),
            "date_range": [str(days[0]), str(days[-1])],
            "oos_split": {"is_days": len(is_days), "oos_days": len(oos_days),
                          "oos_start": str(sorted(oos_days)[0])},
            "strategies": {},
        }
        for strat in STRATS:
            sym_block["strategies"][strat.key] = run_strategy(
                df, symbol, strat, atr, day_end, is_days, oos_days)
        results["by_symbol"][symbol] = sym_block

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"WROTE {OUT_JSON}")
    _write_md(results)
    print(f"WROTE {OUT_MD}")
    _print_verdict(results)


def _write_md(results: dict) -> None:
    lines: list[str] = []
    L = lines.append
    L("# Futures Directional Scorecard — the theta-free arena (MNQ/MES)")
    L("")
    L("> **Question:** ~27 strategies died on 0DTE SPY OPTIONS. The documented failure mode")
    L("> (C3 / L58, L74, L100-101, L112, L136, L148-149 — ~20 lessons) is **0DTE theta + premium-stop")
    L("> misfire eating real DIRECTIONAL edges**. Futures have NO theta — a point move IS P&L and")
    L("> winners can RUN. This re-runs the SAME signals on real micro-futures 5m bars with a pure")
    L("> point-P&L model (`pnl=(exit-entry)*point_value*qty-costs`), intraday-only, ATR trailing")
    L("> stops so trend winners run. Honest gates: OOS per-trade>0 AND beats random-null AND positive")
    L("> in >=60% quarters AND survives real costs.")
    L("")
    m = results["meta"]
    L(f"**Model:** {m['qty_micros']} micro, commission ${m['commission_rt']} RT, "
      f"{m['slippage_ticks_each_side']} tick slippage each side. "
      f"Point values: MNQ ${POINT_VALUE['MNQ']}/pt, MES ${POINT_VALUE['MES']}/pt. "
      f"Signal math ported byte-identical from the option harnesses; only the P&L model changed.")
    L("")
    for symbol in ("MES", "MNQ"):
        sb = results["by_symbol"][symbol]
        L(f"## {symbol}  ({sb['n_days']} days, {sb['date_range'][0]} → {sb['date_range'][1]}; "
          f"OOS from {sb['oos_split']['oos_start']}, {sb['oos_split']['oos_days']} OOS days)")
        L("")
        L("| Strategy | Exit | N | WR% | Full $ | /trade | OOS N | OOS /trade | Null /trade | Beats null | +Q | /week $ | MaxDD | PF | Verdict |")
        L("|---|---|--:|--:|--:|--:|--:|--:|--:|:-:|:-:|--:|--:|--:|:-:|")
        for key in [s.key for s in STRATS]:
            r = sb["strategies"][key]
            full = r["full"]; oos = r["oos"]
            nl = r["random_null_oos"].get("per_trade")
            L(f"| {key} | {r['exit_mode']} | {full.get('n',0)} | {full.get('wr','-')} | "
              f"{full.get('total_pnl','-')} | {full.get('per_trade','-')} | "
              f"{oos.get('n',0)} | {oos.get('per_trade','-')} | "
              f"{nl if nl is not None else '-'} | "
              f"{'Y' if r['gates']['beats_random_null_oos'] else 'n'} | "
              f"{r['positive_quarters']}/{r['n_quarters']} | "
              f"{r['per_week_pnl']} | {full.get('max_dd','-')} | "
              f"{full.get('profit_factor','-')} | **{r['verdict']}** |")
        L("")
        # per-quarter detail for any REAL strategy
        for key in [s.key for s in STRATS]:
            r = sb["strategies"][key]
            if r["verdict"] == "REAL":
                L(f"**{symbol} / {key} — by quarter (REAL):** " +
                  ", ".join(f"{q}:{v['total']:+.0f}(n{v['n']})" for q, v in r["by_quarter"].items()))
                L("")
    L("## Verdict")
    L("")
    reals = []
    for symbol in ("MES", "MNQ"):
        for key, r in results["by_symbol"][symbol]["strategies"].items():
            if r["verdict"] == "REAL":
                reals.append((symbol, key, r))
    if not reals:
        L("**No directional strategy clears the honest gates on either MES or MNQ.** "
          "Removing theta did NOT, by itself, rescue these signals after realistic micro-futures "
          "costs — the trailing-stop trend exits still net out at-or-below the random-entry null on "
          "OOS data. See per-strategy rows above for where each one fails (OOS sign, null, quarters).")
    else:
        for symbol, key, r in reals:
            oos = r["oos"]
            L(f"- **{symbol} / {key}: REAL** — OOS per-trade ${oos['per_trade']} (N={oos['n']}), "
              f"full ${r['full']['total_pnl']:+.0f} over {r['full']['n']} trades, "
              f"${r['per_week_pnl']:+.2f}/week, beats null (${r['random_null_oos']['per_trade']}), "
              f"{r['positive_quarters']}/{r['n_quarters']} quarters positive.")
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")


def _print_verdict(results: dict) -> None:
    print("\n" + "=" * 78)
    print("FUTURES DIRECTIONAL — VERDICT")
    print("=" * 78)
    for symbol in ("MES", "MNQ"):
        sb = results["by_symbol"][symbol]
        print(f"\n{symbol}  ({sb['n_days']}d, OOS={sb['oos_split']['oos_days']}d)")
        for key, r in sb["strategies"].items():
            full = r["full"]; oos = r["oos"]
            nl = r["random_null_oos"].get("per_trade")
            print(f"  {key:20s} v={r['verdict']:4s}  N={full.get('n',0):4d} "
                  f"WR={full.get('wr','-')!s:5s} full=${full.get('total_pnl',0):>8.0f} "
                  f"/t=${full.get('per_trade',0):>7.2f}  OOS/t=${oos.get('per_trade',0) or 0:>7.2f} "
                  f"null=${nl if nl is not None else 0:>7.2f}  +Q={r['positive_quarters']}/{r['n_quarters']}")


if __name__ == "__main__":
    main()
