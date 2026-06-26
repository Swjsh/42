"""B4 NOVEL-DATA HUNT — MES(SPX) vs MNQ(NDX) lead-lag / divergence (point-P&L).

HYPOTHESIS (J, 2026-06-21)
--------------------------
NOVEL: We have BOTH MES (E-mini S&P / SPX proxy) and MNQ (E-mini Nasdaq / NDX
proxy) on real, aligned 5m futures bars and have NEVER mined the CROSS-instrument
relationship. The thesis: when ONE index breaks its own structure (session VWAP
cross, or opening-range break) and the OTHER index LAGS (has not yet confirmed the
same directional break), the laggard tends to "catch up" — a pairs / relative-
strength edge a single-index mechanical test structurally cannot capture.

We TRADE THE LAGGARD in the direction of the leader's break (catch-up), point-P&L,
no theta, intraday flat by EOD. We SWEEP the divergence threshold (how far the two
indices' normalized intraday returns must separate before we call it a divergence).

WHY FUTURES NOT 0DTE
--------------------
Point move IS P&L. No theta decay, no premium-stop misfire (the documented killer of
~20 SPY-option lessons, C3). A correct directional read on the laggard either pays in
points or stops out in points — clean test of the SIGNAL, not the option bracket.

SIGNAL CONSTRUCTION (causal, no look-ahead — L14/L34/L57/L94/L161/L165)
-----------------------------------------------------------------------
Per session, for EACH instrument independently, on every 5m bar i (i computed from
bars [0..i], close confirmed):
  * session VWAP (causal cumulative typical-price VWAP).
  * normalized intraday return  r = (close_i - open_session) / open_session
    (% move from the day's first RTH bar open — unit-free so SPX and NDX compare).
  * "above_vwap" / "below_vwap" structural state.

A LEADER BREAK at bar i is: instrument X's close crosses its VWAP (from below->above
= bullish, above->below = bearish) AT bar i (state flip vs bar i-1).

DIVERGENCE at bar i (the entry trigger on the LAGGARD Y):
  * X (leader) just flipped bullish above its VWAP at bar i, AND
  * Y (laggard) is STILL below its VWAP (has NOT confirmed the bullish break), AND
  * the normalized-return spread  (r_X - r_Y)  >= +THRESHOLD  (X leading up by >=thr)
  -> ENTER Y LONG (catch-up). Symmetric for bearish (X flips below, Y still above,
     r_X - r_Y <= -THRESHOLD -> ENTER Y SHORT).
We test BOTH directions of leadership: MES-leads (trade MNQ laggard) AND
MNQ-leads (trade MES laggard) — "both instruments" per the hypothesis.

One entry per (laggard, session) — first qualifying divergence after a warmup gate,
inside the morning window (catch-up is a same-session mean-reversion-of-spread, so we
cut off entries at 13:00 ET and never first-bar). Entry fills NEXT bar open on the
LAGGARD. Exit: chart-invalidation stop (laggard's swing extreme at signal) + ATR trail
so a real catch-up RUNS; hard EOD flat. NO fixed tiny target (let the laggard run to
the leader).

THE SWEEP: divergence threshold THRESHOLD over a grid (the one knob the hypothesis
names). Reported per (laggard-instrument x threshold) cell.

ALL 8 GATES (anti-2.10, no cherry-pick) — futures point-P&L domain:
  1. OOS(2026) per-trade > 0
  2. positive in >= ceil(0.6*Q) quarters  (>=4 of 6)
  3. top-5 winning DAYS < 200% of total P&L  (concentration, OP-20 #5)
  4. n_trades >= 20
  5. drop-top5-days per-trade > 0  (concentration-robust expectancy)
  6. IS(2025) FIRST-HALF per-trade > 0  (sub-window stability, L166)
  7. beats random-entry NULL (same exit logic, matched count/side, random bars; L172)
  8. NO-TRUNCATION (L171 analog for futures): removing the ATR-trail truncation and
     running the SAME entries to chart-stop + EOD only must NOT flip the cell's sign
     positive->negative. If the only thing making it positive is the trailing stop
     cutting the loser tail, the "edge" is the exit structure, not the divergence read.

Run:
  backtest/.venv/Scripts/python.exe backtest/autoresearch/_b4_mes_mnq_divergence.py
Pure Python, $0, no live orders, no option pricing.
"""
from __future__ import annotations

import datetime as dt
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "backtest" / "data" / "futures"
OUT_JSON = ROOT / "analysis" / "recommendations" / "b4-mes-mnq-divergence.json"

POINT_VALUE = {"MNQ": 2.0, "MES": 5.0}
TICK = 0.25
COMMISSION_RT = 1.24
SLIP_TICKS = 1
QTY = 1

RTH_OPEN = dt.time(9, 30)
RTH_CLOSE = dt.time(16, 0)
WARMUP_BARS = 3                     # need a few bars to seat VWAP before trusting a flip
ENTRY_CUTOFF = dt.time(13, 0)      # catch-up is a same-session edge; no late entries
ATR_LEN = 14
ATR_STOP_MULT = 1.5
TRAIL_MULT = 2.5
RANDOM_SEEDS = 30
OOS_TRAIN_FRAC = 0.70

# THE SWEEP: divergence threshold = required normalized-return spread (r_leader - r_laggard).
# Units are fraction-of-session-open (e.g. 0.0010 = 0.10% spread).
THRESHOLDS = [0.0005, 0.0010, 0.0015, 0.0020, 0.0030, 0.0040]


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
    df = df[(df["t"] >= RTH_OPEN) & (df["t"] < RTH_CLOSE)].reset_index(drop=True)
    return df


def quarter(d: dt.date) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


def session_vwap_asof(g: pd.DataFrame) -> np.ndarray:
    tp = (g["high"] + g["low"] + g["close"]) / 3.0
    pv = (tp * g["volume"]).cumsum()
    vv = g["volume"].cumsum().replace(0, np.nan)
    return (pv / vv).bfill().to_numpy()


def atr_series(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> np.ndarray:
    h = high.to_numpy(float); l = low.to_numpy(float); c = close.to_numpy(float)
    n = len(h)
    tr = np.full(n, np.nan)
    tr[0] = h[0] - l[0]
    for i in range(1, n):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    out = np.full(n, np.nan)
    if n < length:
        return out
    out[length - 1] = np.nanmean(tr[:length])
    for i in range(length, n):
        out[i] = (out[i - 1] * (length - 1) + tr[i]) / length
    return out


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Sig:
    laggard: str        # instrument we TRADE ("MES" or "MNQ")
    idx: int            # global bar idx in the laggard df; fill at NEXT bar open
    date: dt.date
    side: str           # "long" / "short"
    chart_stop: float
    note: str


def _per_session_state(df: pd.DataFrame) -> dict:
    """Per date -> dict with global indices, times, closes, vwap, normalized return r,
    above_vwap state, and swing-extreme arrays. Causal: r uses session-open of that day."""
    out = {}
    for day, g in df.groupby("date", sort=True):
        g = g.reset_index()  # 'index' = global idx
        if len(g) < WARMUP_BARS + 2:
            continue
        vwap = session_vwap_asof(g)
        closes = g["close"].to_numpy(float)
        highs = g["high"].to_numpy(float)
        lows = g["low"].to_numpy(float)
        open0 = float(g["open"].iloc[0])
        r = (closes - open0) / open0 if open0 else np.zeros(len(closes))
        above = closes > vwap
        out[day] = {
            "gidx": g["index"].to_numpy(int),
            "times": g["t"].to_numpy(),
            "closes": closes, "highs": highs, "lows": lows,
            "vwap": vwap, "r": r, "above": above,
        }
    return out


def detect_divergence(lead_df: pd.DataFrame, lag_df: pd.DataFrame,
                      lead_state: dict, lag_state: dict,
                      laggard_symbol: str, threshold: float) -> list[Sig]:
    """LEADER breaks its VWAP (state flip at bar i); LAGGARD has NOT confirmed; the
    normalized-return spread exceeds `threshold` -> trade the laggard for catch-up.

    Bars are matched by wall-clock time within the same session (both feeds are RTH 5m
    aligned). Causal: only state at bar i (closed) is used; entry fills next laggard bar.
    One entry per (laggard, session)."""
    out: list[Sig] = []
    for day in sorted(set(lead_state) & set(lag_state)):
        ls = lead_state[day]; gs = lag_state[day]
        # align by time
        lt = {t: k for k, t in enumerate(ls["times"])}
        gt = {t: k for k, t in enumerate(gs["times"])}
        common_t = [t for t in ls["times"] if t in gt]
        fired = False
        for ti, t in enumerate(common_t):
            if fired:
                break
            if t > ENTRY_CUTOFF:
                break
            li = lt[t]; gi = gt[t]
            if li < WARMUP_BARS or gi < WARMUP_BARS or li < 1:
                continue
            # leader flip at this bar (state change vs prior bar)
            lead_flip_up = (not ls["above"][li - 1]) and ls["above"][li]
            lead_flip_dn = ls["above"][li - 1] and (not ls["above"][li])
            spread = ls["r"][li] - gs["r"][gi]   # leader minus laggard normalized return
            if lead_flip_up and (not gs["above"][gi]) and spread >= threshold:
                # leader broke up, laggard still below its VWAP, leader leading up by >=thr
                stop = float(np.min(gs["lows"][:gi + 1]))  # session low so far = invalidation
                out.append(Sig(laggard=laggard_symbol, idx=int(gs["gidx"][gi]), date=day,
                               side="long", chart_stop=stop,
                               note=f"div_up_thr{threshold}"))
                fired = True
            elif lead_flip_dn and gs["above"][gi] and (-spread) >= threshold:
                stop = float(np.max(gs["highs"][:gi + 1]))
                out.append(Sig(laggard=laggard_symbol, idx=int(gs["gidx"][gi]), date=day,
                               side="short", chart_stop=stop,
                               note=f"div_dn_thr{threshold}"))
                fired = True
    return out


# ─────────────────────────────────────────────────────────────────────────────
# POINT-P&L SIMULATOR  (exit: atr_trail with chart-stop floor; or chartstop_eod for L171)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Fill:
    date: dt.date
    side: str
    entry: float
    exit: float
    pnl: float
    bars_held: int
    exit_reason: str


def simulate(df: pd.DataFrame, sig: Sig, symbol: str, *, atr: np.ndarray,
             day_end: dict, exit_mode: str = "atr_trail") -> Optional[Fill]:
    """Fill at NEXT bar open on the laggard; manage bar-by-bar to session close.
    exit_mode 'atr_trail' = chart-stop floor + ATR chandelier trail (let catch-up RUN).
    exit_mode 'chartstop_eod' = chart-stop only + EOD (NO atr truncation) — the L171
    no-truncation reference. Conservative: stop checked each bar; slippage worsens fills."""
    pv = POINT_VALUE[symbol]
    entry_idx = sig.idx + 1
    if entry_idx >= len(df):
        return None
    if df["date"].iloc[entry_idx] != sig.date:
        return None
    a = atr[sig.idx]
    if np.isnan(a) or a <= 0:
        return None
    long = sig.side == "long"
    slip = SLIP_TICKS * TICK
    raw_entry = float(df["open"].iloc[entry_idx])
    entry = raw_entry + slip if long else raw_entry - slip

    if long:
        atr_stop = entry - ATR_STOP_MULT * a
        # honor chart stop if it is closer (more conservative)
        chart = min(sig.chart_stop, entry - TICK)
        stop = chart if exit_mode == "chartstop_eod" else max(atr_stop, chart)
    else:
        atr_stop = entry + ATR_STOP_MULT * a
        chart = max(sig.chart_stop, entry + TICK)
        stop = chart if exit_mode == "chartstop_eod" else min(atr_stop, chart)

    end_idx = day_end[sig.date]
    hh = float(df["high"].iloc[entry_idx]); ll = float(df["low"].iloc[entry_idx])
    exit_price = None; reason = None; bars = 0
    for k in range(entry_idx, end_idx + 1):
        bars += 1
        hi = float(df["high"].iloc[k]); lo = float(df["low"].iloc[k])
        hh = max(hh, hi); ll = min(ll, lo)
        if exit_mode == "atr_trail":
            if long:
                stop = max(stop, hh - TRAIL_MULT * a)
            else:
                stop = min(stop, ll + TRAIL_MULT * a)
        if long and lo <= stop:
            exit_price = stop - slip; reason = "stop"; break
        if (not long) and hi >= stop:
            exit_price = stop + slip; reason = "stop"; break
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
# METRICS + GATES
# ─────────────────────────────────────────────────────────────────────────────
def _by_day(fills: list[Fill]) -> dict:
    d = defaultdict(float)
    for f in fills:
        d[f.date] += f.pnl
    return dict(d)


def metrics(fills: list[Fill]) -> dict:
    if not fills:
        return {"n": 0}
    pnls = np.array([f.pnl for f in fills])
    wins = pnls[pnls > 0]; losses = pnls[pnls < 0]
    by_day = _by_day(fills)
    day_vals = np.array(sorted(by_day.values(), reverse=True))
    total = float(pnls.sum())
    # top-5 winning DAYS concentration
    top5 = float(day_vals[:5].sum()) if len(day_vals) >= 1 else 0.0
    top5_pct = round(100.0 * top5 / total, 1) if total > 0 else None
    # drop top-5 winning days
    drop_days = set(sorted(by_day, key=lambda k: by_day[k], reverse=True)[:5])
    drop_fills = [f for f in fills if f.date not in drop_days]
    drop_pt = round(float(np.mean([f.pnl for f in drop_fills])), 2) if drop_fills else None
    eq = np.cumsum(pnls); peak = np.maximum.accumulate(eq); dd = eq - peak
    pf = (wins.sum() / -losses.sum()) if losses.sum() != 0 else float("inf")
    exit_mix = defaultdict(int)
    for f in fills:
        exit_mix[f.exit_reason] += 1
    n = len(fills)
    return {
        "n": n, "wr": round(100.0 * len(wins) / n, 1),
        "total_pnl": round(total, 0), "per_trade": round(float(pnls.mean()), 2),
        "avg_win": round(float(wins.mean()), 2) if len(wins) else 0.0,
        "avg_loss": round(float(losses.mean()), 2) if len(losses) else 0.0,
        "max_dd": round(float(dd.min()), 0),
        "profit_factor": round(float(pf), 2) if pf != float("inf") else None,
        "avg_bars_held": round(float(np.mean([f.bars_held for f in fills])), 1),
        "top5_day_pct": top5_pct, "drop_top5_per_trade": drop_pt,
        "exit_mix": dict(exit_mix), "n_days": len(by_day),
    }


def by_quarter(fills: list[Fill]) -> dict:
    q = defaultdict(list)
    for f in fills:
        q[quarter(f.date)].append(f.pnl)
    return {k: {"n": len(v), "total": round(float(sum(v)), 0),
                "per_trade": round(float(np.mean(v)), 2)} for k, v in sorted(q.items())}


def is_first_half_per_trade(fills: list[Fill], is_days_sorted: list) -> Optional[float]:
    """IS first-half sub-window per-trade (sub-window stability, L166)."""
    if not is_days_sorted:
        return None
    half = is_days_sorted[: max(1, len(is_days_sorted) // 2)]
    half_set = set(half)
    sub = [f.pnl for f in fills if f.date in half_set]
    return round(float(np.mean(sub)), 2) if sub else None


def random_null(df: pd.DataFrame, sigs: list[Sig], symbol: str, *, atr: np.ndarray,
                day_end: dict, seeds: int = RANDOM_SEEDS) -> dict:
    """Same exit logic (atr_trail), matched trades/day + side mix, random entry bars in
    the same morning window. Returns mean + p95 (luckiest) per-trade over seeds (L172)."""
    per_day = defaultdict(int); sides = []
    for s in sigs:
        per_day[s.date] += 1; sides.append(s.side)
    if not sides:
        return {"per_trade": None, "n_replicates": 0}
    long_frac = sum(1 for x in sides if x == "long") / len(sides)
    # eligible bars: in the entry window of each day, exclude last bar
    day_groups = {d: g for d, g in df.groupby("date")}
    eligible = {}
    for d, g in day_groups.items():
        idxs = g.index.to_numpy()
        times = g["t"].to_numpy()
        mask = np.array([RTH_OPEN <= t <= ENTRY_CUTOFF for t in times])
        ok = idxs[mask]
        ok = ok[ok < idxs[-1]]
        eligible[d] = ok
    rng = np.random.default_rng(42)
    means = []
    for _ in range(seeds):
        fills = []
        for d, cnt in per_day.items():
            ok = eligible.get(d)
            if ok is None or len(ok) == 0:
                continue
            chosen = rng.choice(ok, size=min(cnt, len(ok)), replace=False)
            for gi in chosen:
                side = "long" if rng.random() < long_frac else "short"
                gi = int(gi)
                if side == "long":
                    cstop = float(df["low"].iloc[max(0, gi - 12):gi + 1].min())
                else:
                    cstop = float(df["high"].iloc[max(0, gi - 12):gi + 1].max())
                f = simulate(df, Sig(laggard=symbol, idx=gi, date=d, side=side,
                                     chart_stop=cstop, note="null"),
                             symbol, atr=atr, day_end=day_end)
                if f:
                    fills.append(f)
        if fills:
            means.append(float(np.mean([f.pnl for f in fills])))
    if not means:
        return {"per_trade": None, "n_replicates": 0}
    return {"per_trade": round(float(np.mean(means)), 2),
            "per_trade_std": round(float(np.std(means)), 2),
            "p95": round(float(np.percentile(means, 95)), 2),
            "n_replicates": len(means)}


def eval_cell(df: pd.DataFrame, symbol: str, sigs: list[Sig], atr: np.ndarray,
              day_end: dict, is_days: set, oos_days: set,
              is_days_sorted: list, n_quarters_universe: int) -> dict:
    # primary fills (atr_trail)
    fills = []
    for s in sigs:
        f = simulate(df, s, symbol, atr=atr, day_end=day_end, exit_mode="atr_trail")
        if f:
            fills.append(f)
    # L171 no-truncation reference: same entries, chart-stop + EOD only
    fills_notrunc = []
    for s in sigs:
        f = simulate(df, s, symbol, atr=atr, day_end=day_end, exit_mode="chartstop_eod")
        if f:
            fills_notrunc.append(f)

    is_fills = [f for f in fills if f.date in is_days]
    oos_fills = [f for f in fills if f.date in oos_days]
    m_all = metrics(fills); m_is = metrics(is_fills); m_oos = metrics(oos_fills)
    q = by_quarter(fills)
    pos_q = sum(1 for v in q.values() if v["total"] > 0)
    need_q = math.ceil(0.6 * n_quarters_universe)

    oos_sigs = [s for s in sigs if s.date in oos_days]
    null_oos = random_null(df, oos_sigs, symbol, atr=atr, day_end=day_end)

    m_notrunc = metrics(fills_notrunc)
    is_half = is_first_half_per_trade(fills, is_days_sorted)

    # ── 8 GATES ──────────────────────────────────────────────────────────────
    oos_pt = m_oos.get("per_trade")
    n_all = m_all.get("n", 0)
    null_pt = null_oos.get("per_trade")
    null_p95 = null_oos.get("p95")
    top5 = m_all.get("top5_day_pct")
    drop_pt = m_all.get("drop_top5_per_trade")
    notrunc_pt = m_notrunc.get("per_trade")
    full_pt = m_all.get("per_trade")

    g1_oos = oos_pt is not None and oos_pt > 0
    g2_posq = pos_q >= need_q
    g3_top5 = top5 is not None and top5 < 200.0
    g4_n = n_all >= 20
    g5_drop = drop_pt is not None and drop_pt > 0
    g6_ishalf = is_half is not None and is_half > 0
    # beat the null MEAN at minimum; disclose vs p95 (luckiest) too
    g7_null = (oos_pt is not None and null_pt is not None and oos_pt > null_pt)
    # no-truncation: removing atr trail must NOT flip a positive cell negative
    # (artifact iff full positive but chart-stop+EOD negative)
    truncation_artifact = (full_pt is not None and full_pt > 0
                           and notrunc_pt is not None and notrunc_pt < 0)
    g8_notrunc = not truncation_artifact

    gates = {
        "1_oos_per_trade_pos": g1_oos,
        "2_positive_quarters_>=60pct": g2_posq,
        "3_top5_day_pct_<200": g3_top5,
        "4_n_trades_>=20": g4_n,
        "5_drop_top5_per_trade_>0": g5_drop,
        "6_is_first_half_per_trade_>0": g6_ishalf,
        "7_beats_random_null": g7_null,
        "8_no_truncation_artifact": g8_notrunc,
    }
    clears_all = all(gates.values())
    fails = [k for k, v in gates.items() if not v]

    return {
        "laggard": symbol, "n_signals": len(sigs), "n_fills": len(fills),
        "full": m_all, "is": m_is, "oos": m_oos,
        "by_quarter": q, "positive_quarters": pos_q,
        "n_quarters": n_quarters_universe, "need_quarters": need_q,
        "is_first_half_per_trade": is_half,
        "no_truncation_ref": {"chartstop_eod_per_trade": notrunc_pt,
                              "full_per_trade": full_pt,
                              "is_artifact": truncation_artifact},
        "random_null_oos": null_oos,
        "beats_null_mean": g7_null,
        "beats_null_p95_luckiest": (oos_pt is not None and null_p95 is not None
                                    and oos_pt > null_p95),
        "gates": gates, "clears_all_gates": clears_all, "failing_gates": fails,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    mes = load_futures("MES")
    mnq = load_futures("MNQ")
    common_days = sorted(set(mes["date"]) & set(mnq["date"]))
    mes = mes[mes["date"].isin(common_days)].reset_index(drop=True)
    mnq = mnq[mnq["date"].isin(common_days)].reset_index(drop=True)

    atr_mes = atr_series(mes["high"], mes["low"], mes["close"], ATR_LEN)
    atr_mnq = atr_series(mnq["high"], mnq["low"], mnq["close"], ATR_LEN)
    de_mes = {d: int(g.index[-1]) for d, g in mes.groupby("date")}
    de_mnq = {d: int(g.index[-1]) for d, g in mnq.groupby("date")}

    state_mes = _per_session_state(mes)
    state_mnq = _per_session_state(mnq)

    cut = int(len(common_days) * OOS_TRAIN_FRAC)
    is_days = set(common_days[:cut]); oos_days = set(common_days[cut:])
    is_days_sorted = sorted(is_days)
    n_q = len(set(quarter(d) for d in common_days))

    results = {
        "meta": {
            "hypothesis": ("MES(SPX) vs MNQ(NDX) lead-lag divergence: when one index "
                           "breaks its session-VWAP and the other lags (still on the "
                           "wrong side), trade the laggard for catch-up. Sweep divergence "
                           "threshold. Point-P&L, no theta, intraday flat by EOD."),
            "novel_data": "cross-instrument MES+MNQ relationship — never mined before",
            "generated": "2026-06-21", "qty_micros": QTY,
            "commission_rt": COMMISSION_RT, "slippage_ticks_each_side": SLIP_TICKS,
            "point_value": POINT_VALUE,
            "n_common_days": len(common_days),
            "date_range": [str(common_days[0]), str(common_days[-1])],
            "oos_split": {"is_days": len(is_days), "oos_days": len(oos_days),
                          "oos_start": str(sorted(oos_days)[0]),
                          "train_frac": OOS_TRAIN_FRAC},
            "n_quarters": n_q,
            "exit": ("atr_trail (chart-stop floor + chandelier trail, mult 2.5) so a real "
                     "catch-up runs; hard EOD flat"),
            "entry_window": [str(RTH_OPEN), str(ENTRY_CUTOFF)],
            "threshold_sweep": THRESHOLDS,
            "gate_definitions": {
                "1": "OOS(2026) per-trade > 0",
                "2": f"positive in >= ceil(0.6*{n_q}) quarters",
                "3": "top-5 winning days < 200% of total P&L",
                "4": "n_trades >= 20",
                "5": "drop-top5-days per-trade > 0",
                "6": "IS(2025) first-half per-trade > 0",
                "7": "beats random-entry null (mean), same exit/count/side (L172)",
                "8": "no-truncation: chart-stop+EOD does not flip a positive cell negative (L171)",
            },
        },
        "cells": [],
    }

    # Two leadership configs: MES leads -> trade MNQ ; MNQ leads -> trade MES
    configs = [
        ("MES", "MNQ", mes, mnq, state_mes, state_mnq, atr_mnq, de_mnq),  # leader, laggard
        ("MNQ", "MES", mnq, mes, state_mnq, state_mes, atr_mes, de_mes),
    ]

    best = None
    for lead_sym, lag_sym, lead_df, lag_df, lead_st, lag_st, lag_atr, lag_de in configs:
        for thr in THRESHOLDS:
            sigs = detect_divergence(lead_df, lag_df, lead_st, lag_st, lag_sym, thr)
            cell = eval_cell(lag_df, lag_sym, sigs, lag_atr, lag_de,
                             is_days, oos_days, is_days_sorted, n_q)
            cell["leader"] = lead_sym
            cell["laggard"] = lag_sym
            cell["threshold"] = thr
            results["cells"].append(cell)
            tag = f"{lead_sym}->{lag_sym} thr={thr}"
            o = cell["oos"]
            print(f"[b4-div] {tag:22s} n={cell['n_signals']:3d} "
                  f"oos_pt={o.get('per_trade')} full_pt={cell['full'].get('per_trade')} "
                  f"posQ={cell['positive_quarters']}/{n_q} top5%={cell['full'].get('top5_day_pct')} "
                  f"null={cell['random_null_oos'].get('per_trade')} "
                  f"-> {'CLEARS' if cell['clears_all_gates'] else 'no('+';'.join(cell['failing_gates'])+')'}",
                  flush=True)
            # track best by OOS per-trade among n>=20 cells
            opt = o.get("per_trade")
            if cell["full"].get("n", 0) >= 20 and opt is not None:
                key = opt
                if best is None or key > best[0]:
                    best = (key, tag, cell)

    clears = [c for c in results["cells"] if c["clears_all_gates"]]
    results["n_clearing_cells"] = len(clears)
    results["clearing_cells"] = [{"leader": c["leader"], "laggard": c["laggard"],
                                  "threshold": c["threshold"]} for c in clears]
    if best is not None:
        results["best_cell_by_oos_per_trade"] = {
            "config": best[1], "oos_per_trade": best[0],
            "n_signals": best[2]["n_signals"], "n_fills": best[2]["n_fills"],
            "full_per_trade": best[2]["full"].get("per_trade"),
            "clears_all_gates": best[2]["clears_all_gates"],
            "failing_gates": best[2]["failing_gates"],
        }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\n[b4-div] WROTE {OUT_JSON}")
    print(f"[b4-div] clearing cells (all 8 gates): {len(clears)}")
    if best is not None:
        b = best[2]
        print(f"[b4-div] BEST by OOS per-trade: {best[1]}  oos_pt=${best[0]}  "
              f"n={b['n_signals']}  clears={b['clears_all_gates']}  "
              f"fails={b['failing_gates']}")


if __name__ == "__main__":
    main()
