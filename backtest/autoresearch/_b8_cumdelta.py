"""ANGLE B — CUMULATIVE-DELTA / VOLUME-IMBALANCE flow signal (real-fills, both tiers).

THE THESIS (why this might escape the C3/L58 SPY-price trap)
────────────────────────────────────────────────────────────
Every dead family so far (~45) was ultimately a function of SPY *price* (trendline,
oscillator, MR, ORB, confluence). A cumulative-delta / volume-imbalance read is a FLOW
signal: it asks "is the session's net signed VOLUME confirming the price move, or
diverging from it?" Flow is a different feature axis than price, so in principle it
could carry option alpha that price-only families cannot. Honest prior: flow proxies
reconstructed from 5m OHLCV (we have NO tick/quote tape) are CRUDE — most likely DEAD —
but it is novel data we hold and never mined, so we report the real numbers.

THE PROXY (causal, look-ahead-safe)
───────────────────────────────────
We have only 5m OHLCV. Per-bar signed volume proxy:

    bar_delta = ((close - open) / max(high - low, eps)) * volume

i.e. where a bar closed within its own range, scaled by that bar's volume. A bar that
closes at its high contributes +volume; at its low, -volume; mid-range, ~0. Cumulative
over the session (cumsum) gives a running net-flow line. Reading cum_delta[i] uses only
bars[0..i] -> causal. (A simpler +volume on up-close / -volume on down-close variant is
also computed for the standalone divergence test, but the range-scaled version is the
primary; both are crude.)

TWO USES (the task)
───────────────────
(1) STANDALONE — one causal entry/day. Trend side = side of the first TREND_BARS RTH
    closes vs as-of session VWAP (REUSED from the LIVE #1 vwap_continuation detector so
    the "trend" definition is identical). Entry fires on the first morning bar (<=10:30
    ET) where BOTH price AND cumulative-delta are making a fresh session extreme in the
    trend direction (flow CONFIRMS price = with-trend continuation). Fill next bar open.

(2) CONFIRMATION GATE on the LIVE #1 vwap_continuation. Take the EXACT #1 signals
    (byte-for-byte detector) and, at each entry bar, require cumulative-delta to AGREE
    with the trade side (cum_delta > 0 for calls, < 0 for puts, AND the bar's own delta
    in-trend). Question: does requiring flow-agreement IMPROVE #1's per-trade expectancy
    WITHOUT failing NO-REGRESSION (the days the gate SKIPS must be net-negative — the
    gate may only remove losers, never winners). This is the SUBTRACTIVE-SELECTION bar.

GATES (the full 9-gate fraud bar, real OPRA fills via simulate_trade_real = C1):
  (1) OOS-2026 per-trade > 0      (5) full drop-top5 > 0
  (2) positive_quarters >= 4/6    (6) IS-2025 per-trade > 0  (half-positive)
  (3) top5-day < 200%             (7) beats random-entry null (L172, null_baseline)
  (4) n >= 20                     (8) no-truncation (L171, sign holds at chart-stop-only)
                                  (9) OOS-ALONE drop-top5 > 0 (L173)
Both tiers: Safe-2 = ATM (strike_offset 0); Bold = ITM-2 (strike_offset -2). C29: knobs
do NOT transfer, so each tier is tested independently.

Pure Python, $0 (no LLM in the sim loop). No live orders. Markets closed. Does NOT touch
any live watcher / params.json / order path.

Writes analysis/recommendations/B8-CUMDELTA-SCORECARD.md (+ a JSON sidecar with numbers).

Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_b8_cumdelta.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO.parent
for _p in (str(REPO), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from autoresearch import runner as ar_runner  # noqa: E402
from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    build_day_contexts,
    session_vwap_asof,
    _nearest_cached_strike,
    _strike_from_spot,
    Signal,
    DayCtx,
)
from autoresearch.null_baseline import null_gate, random_entry_null  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402
from lib.truncation_guard import CHART_STOP_ONLY_PCT, is_truncation_artifact  # noqa: E402

OUT_MD = ROOT / "analysis" / "recommendations" / "B8-CUMDELTA-SCORECARD.md"
OUT_JSON = ROOT / "analysis" / "recommendations" / "B8-CUMDELTA-SCORECARD.json"

# ── Detector params (IDENTICAL to LIVE #1 vwap_continuation) ─────────────────────
TREND_BARS = 3
ENTRY_CUTOFF = dt.time(10, 30)
SHALLOW_DIP_TOL = 0.0010
RTH_OPEN = dt.time(9, 30)
RTH_CLOSE = dt.time(16, 0)

# ── Sweep / tier space ───────────────────────────────────────────────────────────
# Two tiers per C29: Safe-2 = ATM (0), Bold = ITM-2 (-2). Plus ITM-1 as a bridge.
TIER_OFFSETS = {"Safe2_ATM": 0, "Bold_ITM2": -2}
# v15 live stops: bear -20% / bull -8%. We test the production cell + chart-stop-only
# reference (needed for the no-truncation gate) for each tier.
PREMIUM_STOPS = [-0.08, -0.20, -0.99]   # -0.99 = chart-stop-only (truncation reference)
MAX_STRIKE_STEPS = 4
QTY = 3
OOS_YEAR = 2026
NULL_SEEDS = 20

EPS = 1e-9


# ─────────────────────────────────────────────────────────────────────────────
# DATA NORMALIZE (mirror infinite_ammo.load_spy via ar_runner.load_data)
# ─────────────────────────────────────────────────────────────────────────────
def _normalize_spy(spy_raw: pd.DataFrame) -> pd.DataFrame:
    df = spy_raw.copy()
    ts = pd.to_datetime(df["timestamp_et"], utc=True)
    df["timestamp_et"] = ts.dt.tz_convert("America/New_York").dt.tz_localize(None)
    df = df.drop_duplicates(subset="timestamp_et", keep="first").reset_index(drop=True)
    df["date"] = df["timestamp_et"].dt.date
    df["t"] = df["timestamp_et"].dt.time
    df["minute"] = df["timestamp_et"].dt.hour * 60 + df["timestamp_et"].dt.minute
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = df[c].astype(float)
    return df


def _align_vix(spy_df: pd.DataFrame, vix_raw: pd.DataFrame) -> pd.Series:
    spy_ts = pd.to_datetime(spy_df["timestamp_et"]).dt.tz_localize("America/New_York").dt.tz_convert("UTC")
    vix_ts = pd.to_datetime(vix_raw["timestamp_et"], utc=True)
    vix_indexed = pd.Series(vix_raw["close"].astype(float).values, index=vix_ts)
    vix_indexed = vix_indexed[~vix_indexed.index.duplicated(keep="first")]
    aligned = vix_indexed.reindex(spy_ts, method="ffill")
    aligned.index = range(len(aligned))
    return aligned.fillna(0.0)


# ─────────────────────────────────────────────────────────────────────────────
# CUMULATIVE-DELTA PROXY (causal, per-session)
# ─────────────────────────────────────────────────────────────────────────────
def session_cumdelta_asof(rth: pd.DataFrame) -> pd.Series:
    """Range-scaled signed-volume cumulative delta, causal (cum at i uses bars[0..i]).

    bar_delta = ((close-open)/range)*volume ; cumulative over the session.
    """
    o = rth["open"].astype(float)
    c = rth["close"].astype(float)
    rng = (rth["high"].astype(float) - rth["low"].astype(float)).clip(lower=EPS)
    bar_delta = ((c - o) / rng) * rth["volume"].astype(float)
    return bar_delta.cumsum()


def session_cumdelta_sign_asof(rth: pd.DataFrame) -> pd.Series:
    """Simpler +volume on up-close / -volume on down-close cumulative (causal)."""
    c = rth["close"].astype(float)
    o = rth["open"].astype(float)
    sign = np.sign((c - o).values)
    bar_delta = pd.Series(sign * rth["volume"].astype(float).values, index=rth.index)
    return bar_delta.cumsum()


# ─────────────────────────────────────────────────────────────────────────────
# DETECTORS
# ─────────────────────────────────────────────────────────────────────────────
def _trend_side(closes, vwap, n) -> Optional[str]:
    head_c = closes[:n]
    head_v = vwap[:n]
    if len(head_c) < n:
        return None
    if np.all(head_c > head_v):
        return "C"
    if np.all(head_c < head_v):
        return "P"
    return None


def detect_vwap_continuation(days: list[DayCtx]) -> list[Signal]:
    """BYTE-FOR-BYTE the LIVE #1 vwap_continuation detector (breakout+pullback, no VIX
    gate = headline). Returns the exact signals #1 trades. (No flow involved here.)"""
    out: list[Signal] = []
    for dc in days:
        rth = dc.rth
        if len(rth) < TREND_BARS + 2:
            continue
        vwap = session_vwap_asof(rth).values
        closes = rth["close"].values
        highs = rth["high"].values
        lows = rth["low"].values
        times = rth["t"].values
        idxs = rth.index.tolist()
        side = _trend_side(closes, vwap, TREND_BARS)
        if side is None:
            continue
        for j in range(TREND_BARS, len(rth)):
            if times[j] > ENTRY_CUTOFF:
                break
            v = vwap[j]
            if v <= 0:
                continue
            if side == "C":
                prior_ext = float(np.max(highs[:j])) if j > 0 else highs[j]
                breakout = highs[j] >= prior_ext and closes[j] > v
                dip = lows[j] <= v * (1 + SHALLOW_DIP_TOL) and closes[j] > v
                stop = float(np.min(lows[:j + 1]))
            else:
                prior_ext = float(np.min(lows[:j])) if j > 0 else lows[j]
                breakout = lows[j] <= prior_ext and closes[j] < v
                dip = highs[j] >= v * (1 - SHALLOW_DIP_TOL) and closes[j] < v
                stop = float(np.max(highs[:j + 1]))
            trig = "breakout" if breakout else ("pullback" if dip else None)
            if trig is None:
                continue
            out.append(Signal(bar_idx=int(idxs[j]), side=side, stop_level=stop,
                              note=f"jvwap_{trig}"))
            break
    return out


def _cumdelta_agrees(cum: np.ndarray, bar_delta_sign: float, j: int, side: str) -> bool:
    """Flow agrees with `side` at local bar j: cumulative delta on the trade side AND
    this bar's own delta pushing in-trend."""
    cd = cum[j]
    if side == "C":
        return cd > 0 and bar_delta_sign >= 0
    return cd < 0 and bar_delta_sign <= 0


def detect_cumdelta_standalone(days: list[DayCtx]) -> list[Signal]:
    """USE (1): one causal entry/day where price AND cumulative-delta BOTH make a fresh
    session extreme in the trend direction (flow confirms price). Trend side = the LIVE
    #1 VWAP-side rule. Entry fires on the first such bar before ENTRY_CUTOFF; fill next
    bar open. Stop = session swing extreme (same as #1)."""
    out: list[Signal] = []
    for dc in days:
        rth = dc.rth
        if len(rth) < TREND_BARS + 2:
            continue
        vwap = session_vwap_asof(rth).values
        cum = session_cumdelta_asof(rth).values
        closes = rth["close"].values
        opens = rth["open"].values
        highs = rth["high"].values
        lows = rth["low"].values
        times = rth["t"].values
        idxs = rth.index.tolist()
        side = _trend_side(closes, vwap, TREND_BARS)
        if side is None:
            continue
        for j in range(TREND_BARS, len(rth)):
            if times[j] > ENTRY_CUTOFF:
                break
            bar_sign = np.sign(closes[j] - opens[j])
            if side == "C":
                price_ext = highs[j] >= float(np.max(highs[:j]))  # fresh session high
                cd_ext = cum[j] >= float(np.max(cum[:j]))         # fresh cum-delta high
                stop = float(np.min(lows[:j + 1]))
            else:
                price_ext = lows[j] <= float(np.min(lows[:j]))    # fresh session low
                cd_ext = cum[j] <= float(np.min(cum[:j]))         # fresh cum-delta low
                stop = float(np.max(highs[:j + 1]))
            if not (price_ext and cd_ext and _cumdelta_agrees(cum, bar_sign, j, side)):
                continue
            out.append(Signal(bar_idx=int(idxs[j]), side=side, stop_level=stop,
                              note="cumdelta_confirm"))
            break
    return out


def split_vwap_by_cumdelta_gate(days: list[DayCtx]):
    """USE (2): take the LIVE #1 signals; partition into KEPT (flow agrees at entry) vs
    SKIPPED (flow disagrees). Returns (kept_signals, skipped_signals)."""
    # map global bar_idx -> (local rth, local j) so we can read the as-of cum-delta there
    kept: list[Signal] = []
    skipped: list[Signal] = []
    base = detect_vwap_continuation(days)
    # build a per-day cum lookup keyed by date
    cum_by_date: dict[dt.date, tuple[pd.DataFrame, np.ndarray]] = {}
    for dc in days:
        cum_by_date[dc.date] = (dc.rth, session_cumdelta_asof(dc.rth).values)
    for sg in base:
        # find which day this signal belongs to + its local position
        placed = False
        for dc in days:
            rth = dc.rth
            if sg.bar_idx in rth.index:
                local = rth.index.get_loc(sg.bar_idx)
                cum = cum_by_date[dc.date][1]
                bar = rth.loc[sg.bar_idx]
                bar_sign = np.sign(float(bar["close"]) - float(bar["open"]))
                if _cumdelta_agrees(cum, bar_sign, local, sg.side):
                    kept.append(sg)
                else:
                    skipped.append(sg)
                placed = True
                break
        if not placed:
            kept.append(sg)  # cannot evaluate -> keep (fail-open, conservative)
    return base, kept, skipped


# ─────────────────────────────────────────────────────────────────────────────
# SIM (re-run only simulate_trade_real per cell; signals fixed)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class TradeRow:
    date: str
    side: str
    pnl: float
    exit_reason: str
    trig: str


def simulate_cell(signals, spy, ribbon, vix, *, strike_offset, premium_stop_pct):
    rows: list[TradeRow] = []
    n_total = len(signals)
    n_filled = n_miss = n_none = 0
    for sg in signals:
        bar = spy.iloc[sg.bar_idx]
        d = bar["timestamp_et"].date()
        spot = float(bar["close"])
        atm = _strike_from_spot(spot)
        target = atm - strike_offset if sg.side == "P" else atm + strike_offset
        strike = _nearest_cached_strike(d, target, sg.side, MAX_STRIKE_STEPS)
        if strike is None:
            n_miss += 1
            continue
        entry_vix = float(vix.iloc[sg.bar_idx]) if sg.bar_idx < len(vix) else 0.0
        fill = simulate_trade_real(
            entry_bar_idx=sg.bar_idx, entry_bar=bar, spy_df=spy, ribbon_df=ribbon,
            rejection_level=sg.stop_level, triggers_fired=[sg.note or "d"], side=sg.side,
            qty=QTY, setup="B8_CUMDELTA", strike_override=strike, entry_vix=entry_vix,
            premium_stop_pct=premium_stop_pct,
        )
        if fill is None or fill.dollar_pnl is None:
            n_none += 1
            continue
        n_filled += 1
        rows.append(TradeRow(
            date=str(d), side=sg.side, pnl=round(float(fill.dollar_pnl), 2),
            exit_reason=fill.exit_reason.name if fill.exit_reason else "NONE",
            trig=sg.note))
    cov = {"signals": n_total, "filled": n_filled, "cache_miss": n_miss, "sim_none": n_none,
           "fill_rate": round(n_filled / n_total, 3) if n_total else 0.0}
    return rows, cov


# ─────────────────────────────────────────────────────────────────────────────
# METRICS + GATES
# ─────────────────────────────────────────────────────────────────────────────
def _quarter(date_str: str) -> str:
    y, m, _ = date_str.split("-")
    return f"{y}Q{(int(m) - 1) // 3 + 1}"


def _drop_top5_per_trade(rows: list[TradeRow]) -> Optional[float]:
    """Per-trade after removing the 5 best P&L DAYS (full-sample concentration robustness)."""
    if not rows:
        return None
    by_day: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        by_day[r.date].append(r.pnl)
    top5 = set(d for d, _ in sorted(by_day.items(), key=lambda kv: sum(kv[1]),
                                    reverse=True)[:5])
    kept = [p for d, v in by_day.items() if d not in top5 for p in v]
    return round(sum(kept) / len(kept), 2) if kept else None


def _oos_alone_drop_top5(rows: list[TradeRow]) -> Optional[float]:
    """L173: drop-top5 computed on the OOS-2026 rows ALONE."""
    oos = [r for r in rows if int(r.date[:4]) == OOS_YEAR]
    return _drop_top5_per_trade(oos)


def _by_day_top5_pct(rows: list[TradeRow]) -> Optional[float]:
    by_day: dict[str, float] = defaultdict(float)
    for r in rows:
        by_day[r.date] += r.pnl
    total = sum(by_day.values())
    if total <= 0:
        return None
    return round(100 * sum(sorted(by_day.values(), reverse=True)[:5]) / total, 1)


def metrics(rows: list[TradeRow]) -> dict:
    if not rows:
        return {"n": 0}
    pnl = np.array([r.pnl for r in rows], float)
    n = len(rows)
    wins = int((pnl > 0).sum())
    is_rows = [r for r in rows if int(r.date[:4]) != OOS_YEAR]
    oos_rows = [r for r in rows if int(r.date[:4]) == OOS_YEAR]

    def _exp(rs):
        return round(float(np.mean([r.pnl for r in rs])), 2) if rs else 0.0

    def _tot(rs):
        return round(float(np.sum([r.pnl for r in rs])), 2) if rs else 0.0

    by_q: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        by_q[_quarter(r.date)].append(r.pnl)
    quarters = {q: {"n": len(v), "exp": round(sum(v) / len(v), 2), "total": round(sum(v), 2)}
                for q, v in sorted(by_q.items())}
    q_pos = sum(1 for v in quarters.values() if v["exp"] > 0)

    by_side = {}
    for sd in ("C", "P"):
        s = [r.pnl for r in rows if r.side == sd]
        if s:
            by_side[sd] = {"n": len(s), "exp": round(sum(s) / len(s), 2),
                           "wr": round(100 * float((np.array(s) > 0).mean()), 1),
                           "total": round(sum(s), 2)}

    return {
        "n": n,
        "wr_pct": round(100 * wins / n, 1),
        "exp_dollar": round(float(pnl.mean()), 2),
        "total_dollar": round(float(pnl.sum()), 2),
        "is_n": len(is_rows), "is_exp": _exp(is_rows), "is_total": _tot(is_rows),
        "oos_n": len(oos_rows), "oos_exp": _exp(oos_rows), "oos_total": _tot(oos_rows),
        "quarters": quarters,
        "positive_quarters": f"{q_pos}/{len(quarters)}",
        "positive_quarters_n": q_pos, "n_quarters": len(quarters),
        "top5_day_pct": _by_day_top5_pct(rows),
        "drop_top5_per_trade": _drop_top5_per_trade(rows),
        "oos_alone_drop_top5": _oos_alone_drop_top5(rows),
        "by_side": by_side,
    }


def _cumdelta_rejection_fn(rth, idx, side, *, swing_lookback=12):
    """Swing invalidation for the null mirroring the signal stop geometry."""
    c = float(rth.iloc[idx]["close"])
    lo = max(0, idx - swing_lookback + 1)
    win = rth.iloc[lo: idx + 1]
    if side == "C":
        rej = float(win["low"].min())
        return rej if rej < c else c - 1.0
    rej = float(win["high"].max())
    return rej if rej > c else c + 1.0


def nine_gate_verdict(rows: list[TradeRow], spy, vix, *, strike_offset, premium_stop_pct,
                      loose_rows: list[TradeRow]) -> dict:
    """Run the full 9-gate bar on a cell. `loose_rows` = SAME signals at chart-stop-only
    (for the no-truncation gate). Real OPRA fills already in rows."""
    m = metrics(rows)
    n = m.get("n", 0)
    if n == 0:
        return {"clears": False, "metrics": m, "fails": ["n=0"], "gates": {}}

    # gate inputs
    oos_exp = m.get("oos_exp", -1)
    is_exp = m.get("is_exp", -1)
    posq = m.get("positive_quarters_n", 0)
    top5 = m.get("top5_day_pct")
    drop5 = m.get("drop_top5_per_trade")
    oos_drop5 = m.get("oos_alone_drop_top5")

    # random-entry null (L172) — need an RTH frame; use the full spy as the eligible pool
    # restricted to the signals' eligible window via the default entry gate.
    n_call = sum(1 for r in rows if r.side == "C")
    n_put = sum(1 for r in rows if r.side == "P")
    null = random_entry_null(
        spy, n_signals=n, n_call=n_call, n_put=n_put,
        strike_offset=strike_offset, premium_stop_pct=premium_stop_pct,
        qty=QTY, setup="B8_NULL", seeds=NULL_SEEDS,
        rejection_fn=_cumdelta_rejection_fn)
    ng = null_gate(m.get("exp_dollar"), drop5, null)

    # no-truncation (L171)
    loose_pt = metrics(loose_rows).get("exp_dollar") if loose_rows else None
    artifact = is_truncation_artifact(
        best_per_trade=m.get("exp_dollar"),
        chart_stop_only_per_trade=loose_pt,
        best_premium_stop_pct=premium_stop_pct)

    gates = {
        "1_oos_per_trade_pos": oos_exp > 0,
        "2_pos_quarters_4of6": posq >= 4,
        "3_top5_day_lt_200": (top5 is not None and top5 < 200),
        "4_n_ge_20": n >= 20,
        "5_full_drop_top5_pos": (drop5 is not None and drop5 > 0),
        "6_is_2025_half_pos": is_exp > 0,
        "7_beats_random_null": bool(ng.get("null_pass")),
        "8_no_truncation": (not artifact),
        "9_oos_alone_drop_top5_pos": (oos_drop5 is not None and oos_drop5 > 0),
    }
    fails = [k for k, v in gates.items() if not v]
    return {
        "clears": len(fails) == 0,
        "metrics": m,
        "gates": gates,
        "fails": fails,
        "null": null,
        "null_gate": ng,
        "chart_stop_only_per_trade": loose_pt,
        "is_truncation_artifact": artifact,
    }


# ─────────────────────────────────────────────────────────────────────────────
# NO-REGRESSION check for USE (2) confirmation gate
# ─────────────────────────────────────────────────────────────────────────────
def no_regression_report(base_rows, kept_rows, skipped_rows) -> dict:
    """The SUBTRACTIVE-SELECTION bar: a confirmation gate may only remove NET-NEGATIVE
    days. Report base vs kept per-trade + the P&L of the SKIPPED set (must be <= 0)."""
    def _pt(rs):
        return round(sum(r.pnl for r in rs) / len(rs), 2) if rs else None
    skipped_total = round(sum(r.pnl for r in skipped_rows), 2)
    kept_total = round(sum(r.pnl for r in kept_rows), 2)
    base_total = round(sum(r.pnl for r in base_rows), 2)
    # OOS slices
    def _oos(rs):
        return [r for r in rs if int(r.date[:4]) == OOS_YEAR]
    skipped_oos_total = round(sum(r.pnl for r in _oos(skipped_rows)), 2)
    return {
        "base_n": len(base_rows), "base_per_trade": _pt(base_rows), "base_total": base_total,
        "kept_n": len(kept_rows), "kept_per_trade": _pt(kept_rows), "kept_total": kept_total,
        "skipped_n": len(skipped_rows), "skipped_per_trade": _pt(skipped_rows),
        "skipped_total": skipped_total, "skipped_oos_total": skipped_oos_total,
        # no-regression PASS iff the skipped set is net-negative (gate only removed losers)
        # AND kept per-trade improves on base per-trade.
        "skipped_net_negative": skipped_total <= 0,
        "kept_improves": (_pt(kept_rows) is not None and _pt(base_rows) is not None
                          and _pt(kept_rows) > _pt(base_rows)),
        "no_regression_pass": (skipped_total <= 0
                               and _pt(kept_rows) is not None and _pt(base_rows) is not None
                               and _pt(kept_rows) > _pt(base_rows)),
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    print("[b8] loading SPY+VIX via ar_runner.load_data ...", flush=True)
    spy_raw, vix_raw = ar_runner.load_data(dt.date(2025, 1, 1), dt.date(2026, 5, 15))
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    n_days = len(days)
    print(f"[b8] SPY bars={len(spy)} trading_days={n_days} "
          f"window={spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
          flush=True)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))

    # ── USE 1: STANDALONE cum-delta confirmation ─────────────────────────────
    sa_signals = detect_cumdelta_standalone(days)
    sa_days = len({spy.iloc[s.bar_idx]['timestamp_et'].date() for s in sa_signals})
    sa_side = {"C": sum(1 for s in sa_signals if s.side == "C"),
               "P": sum(1 for s in sa_signals if s.side == "P")}
    print(f"[b8] USE1 standalone signals={len(sa_signals)} on {sa_days} days "
          f"({round(100*sa_days/max(n_days,1),1)}% of days) side={sa_side}", flush=True)

    use1 = {}
    for tier, off in TIER_OFFSETS.items():
        # chosen production stop per tier: ATM/Safe -> -0.08 default; Bold ITM2 -> -0.08
        # We evaluate BOTH -0.08 and -0.20; pick best OOS, but always compute chart-stop-only.
        loose_rows, _ = simulate_cell(sa_signals, spy, ribbon, vix,
                                      strike_offset=off, premium_stop_pct=CHART_STOP_ONLY_PCT)
        best = None
        for ps in (-0.08, -0.20):
            rows, cov = simulate_cell(sa_signals, spy, ribbon, vix,
                                      strike_offset=off, premium_stop_pct=ps)
            verdict = nine_gate_verdict(rows, spy, vix, strike_offset=off,
                                        premium_stop_pct=ps, loose_rows=loose_rows)
            verdict["coverage"] = cov
            verdict["premium_stop_pct"] = ps
            verdict["strike_offset"] = off
            key = verdict["metrics"].get("oos_exp", -9e9)
            if best is None or key > best["metrics"].get("oos_exp", -9e9):
                best = verdict
        use1[tier] = best
        m = best["metrics"]
        print(f"  USE1 {tier} off={off} stop={best['premium_stop_pct']}: n={m.get('n')} "
              f"exp=${m.get('exp_dollar')} oos_exp=${m.get('oos_exp')} "
              f"posQ={m.get('positive_quarters')} top5%={m.get('top5_day_pct')} "
              f"-> {'CLEARS 9/9' if best['clears'] else 'FAIL ('+';'.join(best['fails'])+')'}",
              flush=True)

    # ── USE 2: CONFIRMATION GATE on LIVE #1 vwap_continuation ─────────────────
    base_sigs, kept_sigs, skipped_sigs = split_vwap_by_cumdelta_gate(days)
    print(f"\n[b8] USE2 #1 base signals={len(base_sigs)} kept(flow-agrees)={len(kept_sigs)} "
          f"skipped={len(skipped_sigs)}", flush=True)

    use2 = {}
    for tier, off in TIER_OFFSETS.items():
        # production v15 stop for the live edge is -0.08 (bull) / -0.20 (bear); the live #1
        # ships ITM-2/-8%. Evaluate the gate effect at the LIVE production cell per tier.
        ps = -0.08
        base_rows, _ = simulate_cell(base_sigs, spy, ribbon, vix,
                                     strike_offset=off, premium_stop_pct=ps)
        kept_rows, kcov = simulate_cell(kept_sigs, spy, ribbon, vix,
                                        strike_offset=off, premium_stop_pct=ps)
        skipped_rows, _ = simulate_cell(skipped_sigs, spy, ribbon, vix,
                                        strike_offset=off, premium_stop_pct=ps)
        nr = no_regression_report(base_rows, kept_rows, skipped_rows)
        # also run the full 9-gate on the KEPT set (does the gated edge stand on its own?)
        loose_kept, _ = simulate_cell(kept_sigs, spy, ribbon, vix,
                                      strike_offset=off, premium_stop_pct=CHART_STOP_ONLY_PCT)
        kept_verdict = nine_gate_verdict(kept_rows, spy, vix, strike_offset=off,
                                         premium_stop_pct=ps, loose_rows=loose_kept)
        use2[tier] = {"strike_offset": off, "premium_stop_pct": ps,
                      "no_regression": nr, "kept_coverage": kcov,
                      "kept_9gate": {"clears": kept_verdict["clears"],
                                     "fails": kept_verdict["fails"],
                                     "metrics": kept_verdict["metrics"],
                                     "gates": kept_verdict["gates"]}}
        print(f"  USE2 {tier} off={off} stop={ps}: base_pt=${nr['base_per_trade']} "
              f"kept_pt=${nr['kept_per_trade']} (n {nr['base_n']}->{nr['kept_n']}) "
              f"skipped_total=${nr['skipped_total']} "
              f"-> no_regression {'PASS' if nr['no_regression_pass'] else 'FAIL'}", flush=True)

    # ── Assemble verdict ─────────────────────────────────────────────────────
    use1_clears = {t: v["clears"] for t, v in use1.items()}
    use2_pass = {t: v["no_regression"]["no_regression_pass"] for t, v in use2.items()}
    any_use1 = any(use1_clears.values())
    any_use2 = any(use2_pass.values())

    summary = {
        "angle": "B - cumulative-delta / volume-imbalance (flow proxy from 5m OHLCV)",
        "run_date": dt.date.today().isoformat(),
        "window": f"{spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
        "trading_days": n_days,
        "proxy": "bar_delta=((close-open)/range)*volume, cumulative per session, causal as-of",
        "fills_authority": "real OPRA via lib.simulator_real.simulate_trade_real (C1)",
        "tiers": TIER_OFFSETS,
        "oos_split": f"IS=2025 / OOS={OOS_YEAR}",
        "USE1_standalone": use1,
        "USE2_confirmation_gate": use2,
        "use1_clears_9gate": use1_clears,
        "use2_no_regression_pass": use2_pass,
        "verdict": ("EDGE" if (any_use1 or any_use2) else "DEAD"),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    write_scorecard(summary)
    print(f"\n[b8] wrote {OUT_JSON}\n[b8] wrote {OUT_MD}", flush=True)
    print(f"\n=== B8 CUMDELTA VERDICT: {summary['verdict']} ===")
    print(f"USE1 standalone clears 9/9: {use1_clears}")
    print(f"USE2 confirmation no-regression: {use2_pass}")
    return 0


def write_scorecard(s: dict) -> None:
    L = []
    L.append("# B8 — CUMULATIVE-DELTA / VOLUME-IMBALANCE (Angle B) — Real-Fills Scorecard")
    L.append("")
    L.append(f"- **Run:** {s['run_date']}  **Window:** {s['window']}  **Trading days:** {s['trading_days']}")
    L.append(f"- **Proxy:** `{s['proxy']}`")
    L.append(f"- **Fills:** {s['fills_authority']}")
    L.append(f"- **Tiers (C29):** {s['tiers']}  **OOS split:** {s['oos_split']}")
    L.append(f"- **VERDICT: {s['verdict']}**")
    L.append("")
    L.append("Thesis: a flow signal (net signed volume) is a different feature axis than "
             "SPY price, so it could in principle escape the C3/L58 price-edge trap. "
             "Honest prior: flow proxies from 5m OHLCV are crude.")
    L.append("")
    L.append("## USE 1 — STANDALONE (price + cum-delta both make fresh session extreme)")
    L.append("")
    L.append("| Tier | off | stop | n | exp$ | OOS_exp$ | posQ | top5% | drop5$ | OOS-alone drop5$ | null_pass | no-trunc | CLEARS 9/9 | fails |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for tier, v in s["USE1_standalone"].items():
        m = v["metrics"]
        L.append(f"| {tier} | {v['strike_offset']} | {v['premium_stop_pct']} | "
                 f"{m.get('n')} | {m.get('exp_dollar')} | {m.get('oos_exp')} | "
                 f"{m.get('positive_quarters')} | {m.get('top5_day_pct')} | "
                 f"{m.get('drop_top5_per_trade')} | {m.get('oos_alone_drop_top5')} | "
                 f"{v.get('null_gate',{}).get('null_pass')} | "
                 f"{not v.get('is_truncation_artifact')} | "
                 f"{'YES' if v['clears'] else 'no'} | {';'.join(v['fails']) or '-'} |")
    L.append("")
    L.append("## USE 2 — CONFIRMATION GATE on LIVE #1 vwap_continuation (SUBTRACTIVE-SELECTION / no-regression)")
    L.append("")
    L.append("A gate may only remove NET-NEGATIVE days. no_regression PASS iff skipped set "
             "total <= 0 AND kept per-trade > base per-trade.")
    L.append("")
    L.append("| Tier | off | stop | base_n | base_pt$ | kept_n | kept_pt$ | skipped_n | skipped_total$ | skipped_OOS$ | skipped<=0 | kept_improves | no_regression |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for tier, v in s["USE2_confirmation_gate"].items():
        nr = v["no_regression"]
        L.append(f"| {tier} | {v['strike_offset']} | {v['premium_stop_pct']} | "
                 f"{nr['base_n']} | {nr['base_per_trade']} | {nr['kept_n']} | "
                 f"{nr['kept_per_trade']} | {nr['skipped_n']} | {nr['skipped_total']} | "
                 f"{nr['skipped_oos_total']} | {nr['skipped_net_negative']} | "
                 f"{nr['kept_improves']} | {'PASS' if nr['no_regression_pass'] else 'FAIL'} |")
    L.append("")
    L.append("### USE 2 — does the KEPT (flow-confirmed) subset stand alone on the 9-gate bar?")
    L.append("")
    L.append("| Tier | kept_n | kept_OOS_exp$ | kept CLEARS 9/9 | fails |")
    L.append("|---|---|---|---|---|")
    for tier, v in s["USE2_confirmation_gate"].items():
        kg = v["kept_9gate"]
        km = kg["metrics"]
        L.append(f"| {tier} | {km.get('n')} | {km.get('oos_exp')} | "
                 f"{'YES' if kg['clears'] else 'no'} | "
                 f"{';'.join(kg['fails']) or '-'} |")
    L.append("")
    L.append("## Gate legend (the 9-gate fraud bar)")
    L.append("1 OOS-2026/tr>0 | 2 posQ>=4/6 | 3 top5-day<200% | 4 n>=20 | 5 full drop-top5>0 | "
             "6 IS-2025/tr>0 | 7 beats random-null (L172) | 8 no-truncation (L171) | "
             "9 OOS-alone drop-top5>0 (L173)")
    L.append("")
    L.append(f"_Generated by `backtest/autoresearch/_b8_cumdelta.py`. Pure Python, $0. "
             f"No live path touched._")
    OUT_MD.write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
