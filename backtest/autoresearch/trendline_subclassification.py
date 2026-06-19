"""
TRENDLINE SUB-CLASSIFICATION (2026-06-17)

Safe IS has n=70 trendline-class trades. These include:
  1. pure trendline_rejection (no co-triggers) — PHANTOM in live (filter 10 fails)
  2. trendline + ribbon_flip — LIVE ELIGIBLE (ribbon_flip passes filter 10)
  3. trendline + sequence_rejection — LIVE ELIGIBLE (sequence_rejection in filter 10)
  4. trendline + level_reclaim — PHANTOM in live for BEAR (level_reclaim not in BEAR filter 10)
  5. other combos

Morning IS trendlines avg=-$50 (n=30). If phantoms cluster in morning and live-eligible
in midday/afternoon, a "pure phantom trendline gate" would improve backtest accuracy
without hurting live (those trades can't fire in live anyway).

For AGG: same analysis on n=49 non-midday IS trendlines.

Security: read-only, no Alpaca calls, no production writes.
"""
from __future__ import annotations
import sys, json, datetime as dt, pathlib, collections
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

SAFE_KW = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=True,
    premium_stop_pct_bear=-0.10,
    tp1_premium_pct=0.50,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.50,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.30,
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
)
SAFE_OVR = {"vix_bull_max": 18.0}

AGG_KW = dict(
    use_real_fills=True,
    midday_trendline_gate=True,
    premium_stop_pct_bear=-0.07,
    tp1_qty_fraction=0.667,
    tp1_premium_pct=0.75,
    runner_target_premium_pct=5.0,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.50,
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
)
AGG_OVR = {"vix_bear_threshold": 15.0, "vix_bull_max": 30.0}


def _run(spy_df, vix_df, start, end, base_kw, ovr):
    return run_backtest(spy_df, vix_df, start_date=start, end_date=end,
                        params_overrides=dict(ovr), **base_kw)


def _tl_subclass(t):
    trig = set(t.triggers_fired)
    has_tl = "trendline_rejection" in trig
    if not has_tl:
        return None
    has_rf = "ribbon_flip" in trig
    has_seq = "sequence_rejection" in trig or "sequence_reclaim" in trig
    has_rec = "level_reclaim" in trig
    has_rej = "level_rejection" in trig
    has_conf = "confluence" in trig
    if has_rf:
        return "tl+ribbon_flip"
    if has_seq:
        return "tl+sequence"
    if has_rec:
        return "tl+lvl_rec"
    if has_rej:
        return "tl+lvl_rej"
    if has_conf:
        return "tl+conf"
    return "tl_pure"


def _time_bucket(t):
    h, m = t.entry_time_et.hour, t.entry_time_et.minute
    if h < 11 or (h == 11 and m < 30):
        return "09:35-11:30"
    if h < 14:
        return "11:30-14:00"
    return "14:00-15:55"


def _is_live_eligible(subclass):
    # live eligible = passes filter 10 via a co-trigger
    # filter 10 for BEAR: level_reject / ribbon_flip / multi_day_confluence / sequence_rejection
    return subclass in ("tl+ribbon_flip", "tl+sequence")


def _analyze_trendlines(trades, label):
    tl_trades = [t for t in trades if _tl_subclass(t) is not None]
    n_total = len(trades)
    n_tl = len(tl_trades)
    print(f"\n{'='*72}")
    print(f"  {label}: total n={n_total}, trendline n={n_tl} ({100*n_tl/n_total:.1f}%)")
    print(f"{'='*72}")

    by_sub = collections.defaultdict(list)
    for t in tl_trades:
        sub = _tl_subclass(t)
        by_sub[sub].append(t)

    print(f"\n  Trendline sub-classification (IS filter 10 eligibility):")
    print(f"  {'Subclass':20s} {'LiveOK':8s} {'n':>4} {'PnL':>9} {'Avg':>8} {'Stop%':>7}")
    print(f"  {'-'*65}")
    for sub in sorted(by_sub.keys(), key=lambda s: -sum(t.dollar_pnl for t in by_sub[s])):
        ts = by_sub[sub]
        pnl = sum(t.dollar_pnl for t in ts)
        stop_n = sum(1 for t in ts if t.exit_reason and "STOP" in t.exit_reason.value and "RUNNER" not in t.exit_reason.value)
        live_ok = "YES" if _is_live_eligible(sub) else "NO(phantom)"
        print(f"  {sub:20s} {live_ok:8s} {len(ts):>4} {pnl:>9,.0f} {pnl/len(ts):>8.0f} {stop_n/len(ts)*100:>6.1f}%")

    # By sub-class × time bucket
    print(f"\n  By sub-class x time bucket:")
    print(f"  {'Subclass':20s} {'Bucket':15s} {'n':>4} {'PnL':>9} {'Avg':>8}")
    print(f"  {'-'*60}")
    bucket_sub = collections.defaultdict(list)
    for t in tl_trades:
        bucket_sub[(_tl_subclass(t), _time_bucket(t))].append(t)
    for (sub, bucket) in sorted(bucket_sub.keys()):
        ts = bucket_sub[(sub, bucket)]
        pnl = sum(t.dollar_pnl for t in ts)
        print(f"  {sub:20s} {bucket:15s} {len(ts):>4} {pnl:>9,.0f} {pnl/len(ts):>8.0f}")

    # Pure trendline: IS and OOS totals
    pure = by_sub.get("tl_pure", [])
    live_eligible = [t for t in tl_trades if _is_live_eligible(_tl_subclass(t))]
    print(f"\n  SUMMARY:")
    print(f"  Pure phantom (tl_pure): n={len(pure)}, pnl={sum(t.dollar_pnl for t in pure):+,.0f} avg={sum(t.dollar_pnl for t in pure)/len(pure):.0f}" if pure else "  Pure phantom (tl_pure): n=0")
    print(f"  Live-eligible (tl+rf/tl+seq): n={len(live_eligible)}, pnl={sum(t.dollar_pnl for t in live_eligible):+,.0f} avg={sum(t.dollar_pnl for t in live_eligible)/len(live_eligible):.0f}" if live_eligible else "  Live-eligible: n=0")
    phantom_non_pure = [t for t in tl_trades if not _is_live_eligible(_tl_subclass(t)) and _tl_subclass(t) != "tl_pure"]
    print(f"  Other phantom (tl+rec/tl+rej/tl+conf): n={len(phantom_non_pure)}, pnl={sum(t.dollar_pnl for t in phantom_non_pure):+,.0f}" if phantom_non_pure else "  Other phantom: n=0")

    return {
        "n_tl": n_tl,
        "by_sub": {
            sub: {"n": len(ts), "pnl": round(sum(t.dollar_pnl for t in ts), 2),
                  "avg": round(sum(t.dollar_pnl for t in ts)/len(ts), 2),
                  "live_eligible": _is_live_eligible(sub)}
            for sub, ts in by_sub.items()
        },
        "pure_phantom_n": len(pure),
        "pure_phantom_pnl": round(sum(t.dollar_pnl for t in pure), 2),
        "live_eligible_n": len(live_eligible),
        "live_eligible_pnl": round(sum(t.dollar_pnl for t in live_eligible), 2),
    }


if __name__ == "__main__":
    print("Loading data...")
    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    print("\n--- SAFE ---")
    r_safe_is = _run(spy_df, vix_df, IS_START, IS_END, SAFE_KW, SAFE_OVR)
    r_safe_oos = _run(spy_df, vix_df, OOS_START, OOS_END, SAFE_KW, SAFE_OVR)
    print(f"Safe IS n={len(r_safe_is.trades)} pnl={sum(t.dollar_pnl for t in r_safe_is.trades):+,.0f}")
    safe_is = _analyze_trendlines(r_safe_is.trades, "Safe IS")
    safe_oos = _analyze_trendlines(r_safe_oos.trades, "Safe OOS")

    print("\n--- AGG ---")
    r_agg_is = _run(spy_df, vix_df, IS_START, IS_END, AGG_KW, AGG_OVR)
    r_agg_oos = _run(spy_df, vix_df, OOS_START, OOS_END, AGG_KW, AGG_OVR)
    print(f"AGG IS n={len(r_agg_is.trades)} pnl={sum(t.dollar_pnl for t in r_agg_is.trades):+,.0f}")
    agg_is = _analyze_trendlines(r_agg_is.trades, "AGG IS")
    agg_oos = _analyze_trendlines(r_agg_oos.trades, "AGG OOS")

    out = {
        "study": "trendline sub-classification (phantom vs live-eligible)",
        "date": "2026-06-17",
        "safe_is": safe_is,
        "safe_oos": safe_oos,
        "agg_is": agg_is,
        "agg_oos": agg_oos,
    }
    out_path = ROOT / "analysis" / "recommendations" / "trendline-subclassification.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nSaved: {out_path}")
