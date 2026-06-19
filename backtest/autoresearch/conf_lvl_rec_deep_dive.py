"""
conf+lvl_rec DEEP DIVE (2026-06-17)

THE QUESTION: Is there a sub-population of ELITE(conf+lvl_rec) trades with even
stronger edge, identifiable by entry time bucket, VIX bucket, or trigger combo?

conf+lvl_rec = ELITE trades where "confluence" AND "level_reclaim" are both in
triggers_fired. These are the ONLY regime-stable trigger class (IS avg +$173,
OOS avg +$443 per trade).

Safe baseline: tp1=0.50, runner=2.50, stop=-0.10, block_level_rejection=True

Output: console decomposition + analysis/recommendations/conf_lvl_rec_deep_dive.json

Security: read-only, no Alpaca calls, no production writes.
"""
from __future__ import annotations
import sys, json, datetime as dt, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd
from backtest.lib.orchestrator import run_backtest

DATA_DIR = ROOT / "backtest" / "data"
SPY_FILE = DATA_DIR / "spy_5m_2025-01-01_2026-06-16.csv"
VIX_FILE = DATA_DIR / "vix_5m_2025-01-01_2026-06-16.csv"

IS_START  = dt.date(2025, 1, 2)
IS_END    = dt.date(2026, 5, 7)
OOS_START = dt.date(2026, 5, 8)
OOS_END   = dt.date(2026, 6, 16)

IS_SUBWINDOWS = [
    ("W1 Jan-Jun 2025", dt.date(2025, 1, 2),  dt.date(2025, 6, 30)),
    ("W2 Jul-Dec 2025", dt.date(2025, 7, 1),  dt.date(2025, 12, 31)),
    ("W3 Jan-Mar 2026", dt.date(2026, 1, 2),  dt.date(2026, 3, 31)),
    ("W4 Apr-May 2026", dt.date(2026, 4, 1),  dt.date(2026, 5, 7)),
]

# Safe production params (post-L109, matching automation/state/params.json)
import datetime as _dt
# Exact match of SAFE_BASE_KW from safe_premium_stop_sweep.py (the script that verified IS n=130)
SAFE_KW = dict(
    use_real_fills=True,
    no_trade_window=None,              # explicitly disable legacy 14:00-15:00 v11 blackout
    no_trade_before=_dt.time(9, 35),   # 09:35 ET entry gate
    midday_trendline_gate=True,        # v15.3: block 1-trig trendline in 11:30-14:00
    premium_stop_pct_bear=-0.10,
    tp1_premium_pct=0.50,
    tp1_qty_fraction=0.667,            # 2/3 at TP1
    runner_target_premium_pct=2.50,
    time_stop_minutes_before_close=20, # 15:40 ET
    per_trade_risk_cap_pct=0.30,
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
)
SAFE_OVR = {"vix_bull_max": 18.0}   # VIX_BULL_HARD_CAP cap


def _run(spy_df, vix_df, start, end):
    return run_backtest(spy_df, vix_df, start_date=start, end_date=end,
                        params_overrides=dict(SAFE_OVR), **SAFE_KW)


def _classify(t):
    """Return (direction, trigger_class) from TradeFill triggers_fired."""
    trig = set(t.triggers_fired)
    direction = "BULL" if t.side == "C" else "BEAR"
    has_conf = "confluence" in trig
    has_rec = "level_reclaim" in trig
    has_rej = "level_rejection" in trig
    has_rf = "ribbon_flip" in trig
    has_seq = "sequence_rejection" in trig or "sequence_reclaim" in trig
    has_tl = "trendline_rejection" in trig

    if has_conf and has_rec:
        return direction, "conf+lvl_rec"
    if has_conf and has_rej:
        return direction, "conf+lvl_rej"
    if has_conf and has_rf:
        return direction, "conf+rf"
    if has_conf and has_seq:
        return direction, "conf+seq"
    if has_conf:
        return direction, "conf_other"
    if has_rec:
        return direction, "lvl_rec_only"
    if has_rej:
        return direction, "lvl_rej_only"
    if has_tl:
        return direction, "trendline"
    return direction, "other"


def _time_bucket(t):
    et = t.entry_time_et
    h = et.hour if hasattr(et, "hour") else et.replace(tzinfo=None).hour
    m = et.minute if hasattr(et, "minute") else et.replace(tzinfo=None).minute
    mins = h * 60 + m
    if mins < 10 * 60 + 30:
        return "pre-open"
    if mins < 11 * 60 + 30:
        return "morning (09:30-11:30)"
    if mins < 14 * 60:
        return "midday (11:30-14:00)"
    return "afternoon (14:00+)"


def _vix_bucket(v):
    if v is None or v <= 0:
        return "unknown"
    if v < 15:
        return "VIX<15 (low)"
    if v <= 22:
        return "VIX 15-22 (mid)"
    return "VIX>22 (high)"


def _entry_hour(t):
    et = t.entry_time_et
    h = et.hour if hasattr(et, "hour") else et.replace(tzinfo=None).hour
    return f"{h:02d}:xx"


def _decompose(trades, label):
    """Decompose a list of TradeFill objects and return structured breakdown."""
    by_class = {}
    for t in trades:
        direction, cls = _classify(t)
        key = f"{direction}/{cls}"
        if key not in by_class:
            by_class[key] = []
        by_class[key].append(t.dollar_pnl)

    print(f"\n{'='*70}")
    print(f"  {label} — {len(trades)} total trades")
    print(f"{'='*70}")
    print(f"  {'Class':25s}  {'n':>4}  {'Total PnL':>10}  {'Avg/trade':>10}")
    print(f"  {'-'*60}")
    rows = sorted(by_class.items(), key=lambda x: -sum(x[1]))
    for k, pnls in rows:
        print(f"  {k:25s}  {len(pnls):>4}  {sum(pnls):>10,.0f}  {sum(pnls)/len(pnls):>10.0f}")

    # Focus on conf+lvl_rec
    clr = [t for t in trades if _classify(t)[1] == "conf+lvl_rec"]
    if not clr:
        print(f"\n  No conf+lvl_rec trades in {label}")
        return {"n": 0, "total_pnl": 0, "avg_pnl": 0, "by_time": {}, "by_vix": {}, "by_hour": {}}

    print(f"\n  -- conf+lvl_rec DEEP DIVE: n={len(clr)} total_pnl=${sum(t.dollar_pnl for t in clr):,.0f} avg=${sum(t.dollar_pnl for t in clr)/len(clr):.0f}/trade")

    # By time bucket
    by_time = {}
    for t in clr:
        k = _time_bucket(t)
        if k not in by_time:
            by_time[k] = []
        by_time[k].append(t.dollar_pnl)

    print(f"\n  BY TIME BUCKET:")
    for k in ["morning (09:30-11:30)", "midday (11:30-14:00)", "afternoon (14:00+)"]:
        pnls = by_time.get(k, [])
        if pnls:
            print(f"    {k:30s} n={len(pnls):3d}  pnl={sum(pnls):>8,.0f}  avg={sum(pnls)/len(pnls):>7.0f}")
        else:
            print(f"    {k:30s} n=  0  pnl=       0  avg=      0")

    # By VIX bucket
    by_vix = {}
    for t in clr:
        k = _vix_bucket(getattr(t, "entry_vix", None))
        if k not in by_vix:
            by_vix[k] = []
        by_vix[k].append(t.dollar_pnl)

    print(f"\n  BY VIX BUCKET:")
    for k in ["VIX<15 (low)", "VIX 15-22 (mid)", "VIX>22 (high)"]:
        pnls = by_vix.get(k, [])
        if pnls:
            print(f"    {k:20s} n={len(pnls):3d}  pnl={sum(pnls):>8,.0f}  avg={sum(pnls)/len(pnls):>7.0f}")
        else:
            print(f"    {k:20s} n=  0  pnl=       0  avg=      0")

    # By entry hour
    by_hour = {}
    for t in clr:
        k = _entry_hour(t)
        if k not in by_hour:
            by_hour[k] = []
        by_hour[k].append(t.dollar_pnl)

    print(f"\n  BY ENTRY HOUR:")
    for k in sorted(by_hour.keys()):
        pnls = by_hour[k]
        print(f"    {k:8s} n={len(pnls):3d}  pnl={sum(pnls):>8,.0f}  avg={sum(pnls)/len(pnls):>7.0f}")

    # Worst losers
    losers = sorted(clr, key=lambda t: t.dollar_pnl)[:5]
    print(f"\n  TOP 5 WORST conf+lvl_rec trades:")
    for t in losers:
        et = t.entry_time_et
        d = et.date() if hasattr(et, "date") else et.replace(tzinfo=None).date()
        print(f"    {d} {_entry_hour(t)} VIX={getattr(t,'entry_vix',None):.1f} triggers={t.triggers_fired} pnl=${t.dollar_pnl:.0f}")

    # Best winners
    winners = sorted(clr, key=lambda t: -t.dollar_pnl)[:5]
    print(f"\n  TOP 5 BEST conf+lvl_rec trades:")
    for t in winners:
        et = t.entry_time_et
        d = et.date() if hasattr(et, "date") else et.replace(tzinfo=None).date()
        print(f"    {d} {_entry_hour(t)} VIX={getattr(t,'entry_vix',None):.1f} triggers={t.triggers_fired} pnl=${t.dollar_pnl:.0f}")

    return {
        "n": len(clr),
        "total_pnl": round(sum(t.dollar_pnl for t in clr), 2),
        "avg_pnl": round(sum(t.dollar_pnl for t in clr) / len(clr), 2),
        "by_time": {k: {"n": len(v), "total": round(sum(v), 2), "avg": round(sum(v)/len(v), 2)} for k, v in by_time.items()},
        "by_vix": {k: {"n": len(v), "total": round(sum(v), 2), "avg": round(sum(v)/len(v), 2)} for k, v in by_vix.items()},
        "by_hour": {k: {"n": len(v), "total": round(sum(v), 2), "avg": round(sum(v)/len(v), 2)} for k, v in by_hour.items()},
    }


if __name__ == "__main__":
    print("Loading data...")
    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    print("Running Safe IS backtest...")
    r_is = _run(spy_df, vix_df, IS_START, IS_END)
    print(f"IS: n={len(r_is.trades)} pnl={sum(t.dollar_pnl for t in r_is.trades):+,.0f}")

    print("Running Safe OOS backtest...")
    r_oos = _run(spy_df, vix_df, OOS_START, OOS_END)
    print(f"OOS: n={len(r_oos.trades)} pnl={sum(t.dollar_pnl for t in r_oos.trades):+,.0f}")

    is_result = _decompose(r_is.trades, "IS (2025-01-02 to 2026-05-07)")
    oos_result = _decompose(r_oos.trades, "OOS (2026-05-08 to 2026-06-16)")

    # Sub-window breakdown for conf+lvl_rec
    print("\n\nIS SUB-WINDOW BREAKDOWN (conf+lvl_rec only):")
    print(f"  {'Window':25s}  {'n':>4}  {'Total PnL':>10}  {'Avg/trade':>10}")
    print(f"  {'-'*55}")
    sw_results = []
    for label, s, e in IS_SUBWINDOWS:
        r = _run(spy_df, vix_df, s, e)
        clr = [t for t in r.trades if _classify(t)[1] == "conf+lvl_rec"]
        pnl = sum(t.dollar_pnl for t in clr)
        avg = pnl / len(clr) if clr else 0
        print(f"  {label:25s}  {len(clr):>4}  {pnl:>10,.0f}  {avg:>10.0f}")
        sw_results.append({"window": label, "n": len(clr), "total_pnl": round(pnl, 2), "avg_pnl": round(avg, 2)})

    # Save result
    out = {
        "study": "conf+lvl_rec deep dive",
        "date": "2026-06-17",
        "is": is_result,
        "oos": oos_result,
        "is_subwindows": sw_results,
    }
    out_path = ROOT / "analysis" / "recommendations" / "conf_lvl_rec_deep_dive.json"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nSaved: {out_path}")
