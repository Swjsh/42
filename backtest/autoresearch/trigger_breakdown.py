"""
Trigger-type breakdown: What trigger combos produce IS and OOS P&L?

Uses TradeFill.triggers_fired (list[str]) and TradeFill.entry_vix.
Derives quality_tier from triggers_fired using same logic as orchestrator.py:867-930.

Security: read-only. No Alpaca calls.
"""
from __future__ import annotations
import sys
import pathlib
import datetime as dt
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd
from backtest.lib.orchestrator import run_backtest

DATA_DIR = ROOT / "backtest" / "data"
SPY_FILE  = DATA_DIR / "spy_5m_2025-01-01_2026-05-22.csv"
VIX_FILE  = DATA_DIR / "vix_5m_2025-01-01_2026-05-22.csv"

IS_START  = dt.date(2025, 1, 2)
IS_END    = dt.date(2026, 5, 7)
OOS_START = dt.date(2026, 5, 8)
OOS_END   = dt.date(2026, 5, 22)

BASE = dict(
    use_real_fills=True,
    premium_stop_pct_bear=-0.20,
    premium_stop_pct_bull=-0.08,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.50,
    time_stop_minutes_before_close=20,
    midday_trendline_gate=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    per_trade_risk_cap_pct=0.30,
)


def _quality(triggers: list) -> str:
    tf = set(triggers or [])
    has_conf = "confluence" in tf
    has_rf   = "ribbon_flip_bearish" in tf or "ribbon_flip_bullish" in tf
    has_lvl  = "level_rejection" in tf or "level_reclaim" in tf
    has_seq  = "sequence_rejection" in tf
    has_tl   = "trendline_rejection" in tf
    n        = len(tf)
    if (has_conf and has_rf) or n >= 3:
        return "SUPER"
    if has_conf or has_seq:
        return "ELITE"
    if has_lvl:
        return "LEVEL"
    if has_tl:
        return "TRENDLINE"
    return f"OTHER:{','.join(sorted(tf)) or 'empty'}"


def _trig_key(t) -> str:
    tf = sorted(getattr(t, "triggers_fired", None) or [])
    return "+".join(tf) if tf else "unknown"


def _vix_bucket(t) -> str:
    v = getattr(t, "entry_vix", None)
    if v is None:
        return "VIX-?"
    if v < 15:
        return "VIX<15"
    if v < 17:
        return "VIX 15-17"
    if v < 20:
        return "VIX 17-20"
    if v < 25:
        return "VIX 20-25"
    if v < 35:
        return "VIX 25-35"
    return "VIX 35+"


def _time_bucket(t) -> str:
    et = t.entry_time_et
    if getattr(et, "tzinfo", None):
        et = et.replace(tzinfo=None)
    h = et.hour
    if h < 10:
        return "09:30-09:59"
    if h < 11:
        return "10:xx"
    if h < 12:
        return "11:xx"
    if h < 13:
        return "12:xx"
    if h < 14:
        return "13:xx"
    return "14:xx+"


def _stats(pnls):
    n = len(pnls)
    total = sum(pnls)
    avg = total / n if n else 0
    wr = 100 * sum(1 for p in pnls if p > 0) / n if n else 0
    return n, total, avg, wr


def _table(by: dict, header: str, max_rows: int = 20) -> None:
    print(f"\n  {header}:")
    print(f"  {'key':40}  {'n':>4}  {'pnl':>9}  {'avg':>8}  {'WR':>6}")
    print("  " + "-" * 72)
    rows = sorted(by.items(), key=lambda x: sum(x[1]), reverse=True)
    for k, pnls in rows[:max_rows]:
        n, tot, avg, wr = _stats(pnls)
        print(f"  {str(k):40}  {n:>4}  {tot:>+9.0f}  {avg:>+8.0f}  {wr:>5.1f}%")
    if len(rows) > max_rows:
        print(f"  ... ({len(rows) - max_rows} more rows)")


def _analyze(trades, label: str) -> dict:
    by_trig  = defaultdict(list)
    by_qual  = defaultdict(list)
    by_vix   = defaultdict(list)
    by_time  = defaultdict(list)
    by_cross = defaultdict(list)

    for t in trades:
        p = t.dollar_pnl
        trig = _trig_key(t)
        qual = _quality(getattr(t, "triggers_fired", None) or [])
        vix  = _vix_bucket(t)
        time = _time_bucket(t)

        by_trig[trig].append(p)
        by_qual[qual].append(p)
        by_vix[vix].append(p)
        by_time[time].append(p)
        by_cross[f"{qual}|{trig}"].append(p)

    print(f"\n{'='*80}")
    n, tot, avg, wr = _stats([t.dollar_pnl for t in trades])
    print(f"  {label}: {n} trades, pnl={tot:+.0f}, avg={avg:+.0f}, WR={wr:.1f}%")
    print(f"{'='*80}")

    _table(by_trig, "By trigger set")
    _table(by_qual, "By quality tier (derived)")
    _table(by_vix,  "By VIX bucket at entry")
    _table(by_time, "By time bucket")
    _table(by_cross, "Quality x trigger cross-tab (top 20)")

    return {"by_trig": by_trig, "by_qual": by_qual, "by_vix": by_vix, "by_time": by_time}


if __name__ == "__main__":
    print("TRIGGER BREAKDOWN -- IS vs OOS")
    print(f"IS: {IS_START} -> {IS_END}")
    print(f"OOS: {OOS_START} -> {OOS_END}")

    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    print("\nRunning IS backtest...")
    is_r = run_backtest(spy_df, vix_df, start_date=IS_START, end_date=IS_END, **BASE)
    print("Running OOS backtest...")
    oos_r = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END, **BASE)

    is_m  = _analyze(is_r.trades, "IN-SAMPLE")
    oos_m = _analyze(oos_r.trades, "OUT-OF-SAMPLE")

    print("\n\n--- IS vs OOS COMPARISON ---")

    for dim in ["by_trig", "by_qual", "by_vix", "by_time"]:
        is_d  = is_m[dim]
        oos_d = oos_m[dim]
        all_k = sorted(set(is_d) | set(oos_d))
        title = {"by_trig": "Trigger set", "by_qual": "Quality tier",
                 "by_vix": "VIX bucket", "by_time": "Time bucket"}[dim]
        print(f"\n  {title}:")
        print(f"  {'key':40}  {'IS_n':>4}  {'IS_pnl':>9}  {'IS_WR':>6}  |  {'OOS_n':>4}  {'OOS_pnl':>9}  {'OOS_WR':>7}")
        print("  " + "-" * 88)
        for k in all_k:
            ip = is_d.get(k, [])
            op = oos_d.get(k, [])
            i_n, i_t, _, i_wr = _stats(ip) if ip else (0, 0, 0, 0)
            o_n, o_t, _, o_wr = _stats(op) if op else (0, 0, 0, 0)
            note = ""
            if ip and not op: note = "IS only"
            elif op and not ip: note = "OOS only"
            elif i_t < 0 and o_t > 0: note = "IS loses, OOS wins!"
            elif i_t > 0 and o_t < 0: note = "IS wins, OOS loses"
            print(f"  {str(k):40}  {i_n:>4}  {i_t:>+9.0f}  {i_wr:>5.1f}%  |  "
                  f"{o_n:>4}  {o_t:>+9.0f}  {o_wr:>6.1f}%  {note}")

    print("\nANALYSIS COMPLETE.")
