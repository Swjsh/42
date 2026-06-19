"""
NLWB (Named-Level Wick-Bounce) Bullish Setup Backtest — Safe account DRAFT.

Hypothesis: When SPY bar.low < PDL AND bar.close > PDL (wick through prior day low,
            close back above) -> intraday support confirmation -> bullish call entry.

Prior scan (2026-06-15 key-levels analysis): PDL N=157 WR=71% (SPY bounce rate).
This script tests the option P&L equivalent.

Setup params:
  Entry:    signal bar close (bar.low < PDL AND bar.close > PDL)
  Level:    PDL = prior day RTH low (09:30-15:55 ET)
  Side:     CALL (bullish)
  Strike:   OTM-2 (ATM + 2 strikes above spot)
  Stop:     -10% premium OR bar.close < PDL (chart stop)
  TP1:      +50% premium, sell 2/3 qty
  Runner:   +250% premium target (2.5x)
  Time:     15:40 ET hard flat
  Gate:     09:35-14:30 ET entry window; one trade per day (first signal)

IS:  2025-01-02 to 2026-05-07 (same split as chandelier research)
OOS: 2026-05-08 to 2026-06-16

DRAFT only — BULLISH_RECLAIM scope lock in effect per CLAUDE.md.
NEVER modifies params.json / heartbeat.md / production state.
"""

from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from lib.pricing import black_scholes, vix_to_iv, time_to_expiry_years, price_atm_call

# ── paths ─────────────────────────────────────────────────────────────────────
DATA_DIR    = Path(__file__).parent.parent / "data"
RESULTS_DIR = Path(__file__).parent / "results"
MASTER_SPY  = DATA_DIR / "spy_5m_2025-01-01_2026-06-16.csv"
MASTER_VIX  = DATA_DIR / "vix_5m_2025-01-01_2026-06-16.csv"

# ── IS/OOS split ──────────────────────────────────────────────────────────────
IS_START  = "2025-01-02"
IS_END    = "2026-05-07"
OOS_START = "2026-05-08"
OOS_END   = "2026-06-16"

SUB_WINDOWS = [
    ("W1_2025H1", "2025-01-02", "2025-06-30"),
    ("W2_2025Q3", "2025-07-01", "2025-09-30"),
    ("W3_2025Q4", "2025-10-01", "2025-12-31"),
    ("W4_2026H1", "2026-01-02", "2026-05-07"),
]

# ── trade params ──────────────────────────────────────────────────────────────
ENTRY_START   = dt.time(9, 35)
ENTRY_END     = dt.time(14, 30)
TIME_STOP     = dt.time(15, 40)
STRIKE_OFFSET = 2        # OTM-2 calls
PREM_STOP_PCT = -0.10   # -10% premium stop
TP1_PCT       = 0.50    # +50% TP1
TP1_FRACTION  = 0.667
RUNNER_PCT    = 2.50    # 2.5x runner cap
QTY           = 5       # Safe $2K OTM-2 base
MULT          = 100     # contract size

# Variants to sweep
VARIANTS = [
    # (label, strike_offset, min_bounce_above_pdl)
    ("OTM-2  bounce>0.00", 2, 0.00),
    ("OTM-2  bounce>0.30", 2, 0.30),
    ("OTM-2  bounce>0.75", 2, 0.75),
    ("OTM-1  bounce>0.00", 1, 0.00),
    ("OTM-1  bounce>0.30", 1, 0.30),
    ("OTM-1  bounce>0.75", 1, 0.75),
    ("ATM    bounce>0.00", 0, 0.00),
    ("ATM    bounce>0.30", 0, 0.30),
    ("ATM    bounce>0.75", 0, 0.75),
]


# ── data loading ──────────────────────────────────────────────────────────────
def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    ts_col = "timestamp_et" if "timestamp_et" in df.columns else df.columns[0]
    ts = pd.to_datetime(df[ts_col], utc=True).dt.tz_convert("America/New_York")
    df = df.copy()
    df["timestamp_et"] = ts
    df["date"] = ts.dt.strftime("%Y-%m-%d")
    df["time"] = ts.dt.strftime("%H:%M")
    return df.reset_index(drop=True)


def load_data():
    print("Loading data...")
    spy_df = _normalize(pd.read_csv(MASTER_SPY))
    vix_df = _normalize(pd.read_csv(MASTER_VIX))
    print(f"  SPY {len(spy_df):,} rows  VIX {len(vix_df):,} rows")
    return spy_df, vix_df


def build_vix_aligned(spy_df: pd.DataFrame, vix_df: pd.DataFrame) -> pd.Series:
    """Map VIX close to each SPY bar by (date, time) key."""
    vix_map = {(r["date"], r["time"]): float(r["close"]) for _, r in vix_df.iterrows()}
    return pd.Series(
        [vix_map.get((r["date"], r["time"]), np.nan) for _, r in spy_df.iterrows()],
        index=spy_df.index,
    )


def build_pdl(spy_df: pd.DataFrame) -> dict:
    """PDL = prior day's RTH (09:30-15:55) low. Returns {date_str: pdl_price}."""
    rth = spy_df[(spy_df["time"] >= "09:30") & (spy_df["time"] <= "15:55")]
    day_low = rth.groupby("date")["low"].min()
    dates   = sorted(day_low.index.tolist())
    return {dates[i]: float(day_low[dates[i - 1]]) for i in range(1, len(dates))}


# ── option pricing ─────────────────────────────────────────────────────────────
def _price_call(spot: float, vix: float, ts, strike_offset: int) -> tuple:
    """Returns (premium, strike) for OTM-{strike_offset} call. None on error."""
    if vix <= 0 or np.isnan(vix):
        return None, None
    try:
        atm = price_atm_call(spot, vix, ts)
        target = atm.strike + strike_offset
        iv  = vix_to_iv(vix)
        tte = time_to_expiry_years(ts)
        if tte <= 1e-6:
            return None, None
        prem, _ = black_scholes(spot, target, iv, tte, is_call=True)
        return float(prem), target
    except Exception:
        return None, None


# ── trade simulation ───────────────────────────────────────────────────────────
@dataclass
class TradeResult:
    date:        str
    entry_time:  str
    entry_spot:  float
    pdl:         float
    entry_prem:  float
    strike:      int
    pnl:         float
    exit_reason: str
    bars_held:   int


def _sim_trade(
    entry_idx:   int,
    spy_df:      pd.DataFrame,
    vix_aligned: pd.Series,
    pdl:         float,
    entry_prem:  float,
    strike:      int,
    entry_ts,
) -> Optional[TradeResult]:
    """Walk forward from entry_idx+1 and compute P&L."""
    stop_prem   = entry_prem * (1.0 + PREM_STOP_PCT)
    tp1_prem    = entry_prem * (1.0 + TP1_PCT)
    runner_prem = entry_prem * (1.0 + RUNNER_PCT)

    qty_tp1    = round(QTY * TP1_FRACTION)
    qty_runner = QTY - qty_tp1

    tp1_hit  = False
    tp1_cash = 0.0
    be_stop  = stop_prem  # runner stop floor (moves to BE after TP1)

    entry_date = spy_df.iloc[entry_idx]["date"]

    for i in range(entry_idx + 1, len(spy_df)):
        bar = spy_df.iloc[i]
        ts  = bar["timestamp_et"]
        t   = ts.time()
        d   = bar["date"]

        # EOD / new day guard
        if d != entry_date:
            exit_prem = 0.01
            pnl = (tp1_cash + qty_runner * (exit_prem - entry_prem) * MULT) if tp1_hit \
                  else QTY * (exit_prem - entry_prem) * MULT
            return _result(spy_df, entry_idx, i, d, entry_prem, strike, pnl, "EOD")

        # Time stop
        if t >= TIME_STOP:
            vix_v = _vix(vix_aligned, i)
            ep, _ = _price_call(float(bar["close"]), vix_v, ts, STRIKE_OFFSET)
            ep = ep or 0.01
            pnl = (tp1_cash + qty_runner * (ep - entry_prem) * MULT) if tp1_hit \
                  else QTY * (ep - entry_prem) * MULT
            return _result(spy_df, entry_idx, i, d, entry_prem, strike, pnl, "TIME")

        vix_v   = _vix(vix_aligned, i)
        bar_low  = float(bar["low"])
        bar_high = float(bar["high"])
        bar_close = float(bar["close"])

        # ── adverse (bar.low) checks (conservative: stop before TP1 in same bar) ──
        # Chart stop: call loses when PDL is undercut again
        if bar_low < pdl:
            ap, _ = _price_call(bar_low, vix_v, ts, STRIKE_OFFSET)
            ap = min(ap or stop_prem, stop_prem)  # at worst stop level
            pnl = (tp1_cash + qty_runner * (ap - entry_prem) * MULT) if tp1_hit \
                  else QTY * (ap - entry_prem) * MULT
            return _result(spy_df, entry_idx, i, d, entry_prem, strike, pnl, "CHART")

        # Premium stop
        ap, _ = _price_call(bar_low, vix_v, ts, STRIKE_OFFSET)
        active_stop = be_stop if tp1_hit else stop_prem
        if ap is not None and ap <= active_stop:
            pnl = (tp1_cash + qty_runner * (active_stop - entry_prem) * MULT) if tp1_hit \
                  else QTY * (active_stop - entry_prem) * MULT
            return _result(spy_df, entry_idx, i, d, entry_prem, strike, pnl, "PREM_STOP")

        # ── favorable (bar.high) checks ──
        fp, _ = _price_call(bar_high, vix_v, ts, STRIKE_OFFSET)
        if fp is not None:
            if not tp1_hit and fp >= tp1_prem:
                tp1_hit = True
                tp1_cash = qty_tp1 * (tp1_prem - entry_prem) * MULT
                be_stop  = entry_prem  # runner stop to breakeven

            if tp1_hit and fp >= runner_prem:
                pnl = tp1_cash + qty_runner * (runner_prem - entry_prem) * MULT
                return _result(spy_df, entry_idx, i, d, entry_prem, strike, pnl, "RUNNER")

    # Safety fallback
    return None


def _vix(vix_aligned: pd.Series, i: int) -> float:
    v = vix_aligned.iloc[i]
    return float(v) if not np.isnan(v) else 20.0


def _result(spy_df, entry_idx, exit_idx, date, entry_prem, strike, pnl, reason):
    eb = spy_df.iloc[entry_idx]
    return TradeResult(
        date=eb["date"],
        entry_time=eb["time"],
        entry_spot=float(eb["close"]),
        pdl=0.0,  # filled by caller
        entry_prem=entry_prem,
        strike=strike,
        pnl=round(pnl, 2),
        exit_reason=reason,
        bars_held=exit_idx - entry_idx,
    )


# ── backtest runner ────────────────────────────────────────────────────────────
def run_window(spy_df, vix_aligned, pdl_by_date, start_str, end_str,
               strike_offset=STRIKE_OFFSET, min_bounce=0.0):
    """Run NLWB over [start_str, end_str]. Returns list[TradeResult]."""
    trades = []
    traded_dates = set()
    i = 0
    n = len(spy_df)

    while i < n:
        row = spy_df.iloc[i]
        d   = row["date"]

        if d < start_str or d > end_str:
            i += 1
            continue

        if d in traded_dates:
            i += 1
            continue

        pdl = pdl_by_date.get(d)
        if pdl is None:
            i += 1
            continue

        t = row["timestamp_et"].time()
        if t < ENTRY_START or t > ENTRY_END:
            i += 1
            continue

        bar_low   = float(row["low"])
        bar_close = float(row["close"])

        # NLWB signal: wick below PDL, close recovers above PDL with min bounce
        if bar_low < pdl and (bar_close - pdl) >= min_bounce:
            vix_v = _vix(vix_aligned, i)
            ts    = row["timestamp_et"]
            ep, strike = _price_call(bar_close, vix_v, ts, strike_offset)

            if ep and ep > 0.01:
                result = _sim_trade(i, spy_df, vix_aligned, pdl, ep, strike, ts)
                if result:
                    result.pdl = pdl
                    trades.append(result)
                    traded_dates.add(d)

        i += 1

    return trades


# ── metrics ────────────────────────────────────────────────────────────────────
def metrics(trades):
    if not trades:
        return {"n": 0, "pnl": 0, "wr": 0.0, "avg": 0.0}
    pnls = [t.pnl for t in trades]
    n    = len(pnls)
    wins = sum(1 for p in pnls if p > 0)
    return {
        "n":   n,
        "pnl": round(sum(pnls), 0),
        "wr":  round(wins / n * 100, 1),
        "avg": round(sum(pnls) / n, 0),
    }


def format_window(label, trades):
    m = metrics(trades)
    exits = {}
    for t in trades:
        exits[t.exit_reason] = exits.get(t.exit_reason, 0) + 1
    exits_str = "  ".join(f"{k}={v}" for k, v in sorted(exits.items()))
    return f"  {label:<22} n={m['n']:>3}  pnl={m['pnl']:>+8,.0f}  WR={m['wr']:>5.1f}%  avg={m['avg']:>+6,.0f}  exits: {exits_str}"


# ── main ──────────────────────────────────────────────────────────────────────
def main():
    spy_df, vix_df = load_data()
    vix_aligned     = build_vix_aligned(spy_df, vix_df)
    pdl_by_date     = build_pdl(spy_df)

    out = RESULTS_DIR / "nlwb_backtest.txt"
    RESULTS_DIR.mkdir(exist_ok=True)

    lines = []
    def emit(s=""):
        print(s)
        lines.append(s)

    emit()
    emit("NLWB (Named-Level Wick-Bounce) Bullish Setup Backtest — Safe account DRAFT")
    emit("Setup: bar.low < PDL AND bar.close > PDL -> buy OTM-2 call")
    emit(f"Entry gate: {ENTRY_START.strftime('%H:%M')}-{ENTRY_END.strftime('%H:%M')} ET | "
         f"Stop: {PREM_STOP_PCT*100:.0f}% prem OR chart | TP1: +{TP1_PCT*100:.0f}% | "
         f"Runner: +{RUNNER_PCT*100:.0f}% | Time: {TIME_STOP.strftime('%H:%M')} ET")
    emit(f"Strike: OTM-{STRIKE_OFFSET} calls | Qty: {QTY} contracts | One per day")
    emit()

    emit()
    emit("=" * 78)
    emit("NLWB VARIANT SWEEP: strike_offset x min_bounce_above_pdl")
    emit("All comparisons vs OTM-2 bounce>0 baseline")
    emit(f"{'Variant':<28} {'IS_n':>4} {'IS_pnl':>8} {'IS_avg':>7} {'OOS_n':>5} {'OOS_pnl':>8} {'OOS_avg':>7} {'WF':>7}  VERDICT")
    emit("-" * 78)

    results_table = []
    for vlabel, voff, vbounce in VARIANTS:
        emit(f"  Running {vlabel}...", )
        is_t  = run_window(spy_df, vix_aligned, pdl_by_date, IS_START,  IS_END,
                           strike_offset=voff, min_bounce=vbounce)
        oos_t = run_window(spy_df, vix_aligned, pdl_by_date, OOS_START, OOS_END,
                           strike_offset=voff, min_bounce=vbounce)
        im = metrics(is_t)
        om = metrics(oos_t)

        ni, no = im["n"], om["n"]
        if ni > 0 and no > 0 and im["avg"] != 0:
            wf = om["avg"] / im["avg"]
        else:
            wf = float("nan")

        oos_pos  = om["pnl"] > 0
        wf_pass  = (not np.isnan(wf)) and wf >= 0.70
        if oos_pos and wf_pass:
            verdict = "RATIFIABLE"
        elif not oos_pos:
            verdict = "OOS_NEG"
        else:
            verdict = f"WF_FAIL({wf:.3f})"

        row = f"  {vlabel:<26} {ni:>4} {im['pnl']:>+8,.0f} {im['avg']:>+7,.0f}  {no:>4} {om['pnl']:>+8,.0f} {om['avg']:>+7,.0f} {wf:>7.3f}  {verdict}"
        emit(row)
        results_table.append((vlabel, voff, vbounce, im, om, wf, verdict, is_t, oos_t))

    emit()
    emit("=" * 78)

    # Detail for baseline (OTM-2, bounce>0)
    base = results_table[0]
    vlabel, voff, vbounce, im, om, wf, verdict, is_trades, oos_trades = base
    n_is = im["n"]

    emit()
    emit(f"DETAIL: {vlabel}")
    emit(f"IS  ({IS_START} to {IS_END}):")
    emit(format_window("IS  overall", is_trades))
    emit()
    emit(f"OOS ({OOS_START} to {OOS_END}):")
    emit(format_window("OOS overall", oos_trades))
    emit()

    emit("Sub-windows (IS only):")
    for name, s, e in SUB_WINDOWS:
        sw = run_window(spy_df, vix_aligned, pdl_by_date, s, e,
                        strike_offset=voff, min_bounce=vbounce)
        emit(format_window(f"  {name}", sw))
    emit()

    emit("Exit breakdown (IS):")
    exits_is: dict = {}
    for t in is_trades:
        exits_is[t.exit_reason] = exits_is.get(t.exit_reason, 0) + 1
    for k, v in sorted(exits_is.items()):
        pct = v / n_is * 100 if n_is > 0 else 0
        emit(f"  {k:<15} n={v:>3}  ({pct:.1f}%)")

    emit()
    emit("Entry time distribution (IS):")
    by_hour: dict = {}
    for t in is_trades:
        h = t.entry_time[:2]
        by_hour[h] = by_hour.get(h, 0) + 1
    for h in sorted(by_hour):
        emit(f"  {h}:xx  n={by_hour[h]}")

    emit()
    emit("Daily PnL sample (IS, first 15):")
    for t in is_trades[:15]:
        emit(f"  {t.date}  {t.entry_time}  PDL={t.pdl:.2f}  spot={t.entry_spot:.2f}  "
             f"prem={t.entry_prem:.2f}  pnl={t.pnl:+.0f}  exit={t.exit_reason}  bars={t.bars_held}")

    emit()
    emit("DONE.")

    out.write_text("\n".join(lines))
    print(f"\nResults written to {out}")


if __name__ == "__main__":
    main()
