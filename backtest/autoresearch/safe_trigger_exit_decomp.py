"""
SAFE TRIGGER-CLASS x EXIT-TYPE DECOMPOSITION (2026-06-17)

Safe IS n=130 pnl=+16,174 (verified). Safe OOS n=21 pnl=+5,900.
conf+lvl_rec was isolated in context-38 (IS n=33 avg=$175, OOS n=6 avg=$450).

THE QUESTION: What do the other 97 Safe IS trades look like?
Which classes drive the IS profit? Which have poor stop rates?
Does any class have a compelling gate?

Companion to agg_trigger_exit_decomp.py (same structure, Safe params).
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

# Safe production params — verified IS n=130 pnl=+16,174
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


def _run(spy_df, vix_df, start, end):
    return run_backtest(spy_df, vix_df, start_date=start, end_date=end,
                        params_overrides=dict(SAFE_OVR), **SAFE_KW)


def _classify(t):
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


def _exit_group(t):
    r = t.exit_reason.value if t.exit_reason else "UNKNOWN"
    if "RUNNER_TIME" in r:
        return "TP1+runner_time"
    if "RUNNER_RIBBON" in r:
        return "TP1+runner_ribbon"
    if "RUNNER_TARGET" in r:
        return "TP1+runner_target"
    if "RUNNER_BE" in r:
        return "TP1+runner_be_stop"
    if "TP1" in r:
        return "TP1_other"
    if "PREMIUM_STOP" in r:
        return "premium_stop"
    if "LEVEL_STOP" in r:
        return "level_stop"
    if "RIBBON_FLIP_BACK" in r:
        return "pre_tp1_ribbon_flip"
    if "TIME_STOP" in r:
        return "time_stop_full"
    return r


def _time_bucket(t):
    h, m = t.entry_time_et.hour, t.entry_time_et.minute
    if h < 11 or (h == 11 and m < 30):
        return "09:35-11:30"
    if h < 14:
        return "11:30-14:00"
    return "14:00-15:55"


def _analyze(trades, label):
    n = len(trades)
    total_pnl = sum(t.dollar_pnl for t in trades)
    print(f"\n{'='*72}")
    print(f"  {label}: n={n} total_pnl=${total_pnl:,.0f} avg=${total_pnl/n:.0f}/trade")
    print(f"{'='*72}")

    by_cls = collections.defaultdict(list)
    for t in trades:
        _, cls = _classify(t)
        by_cls[cls].append(t)

    print(f"\n  By trigger class:")
    print(f"  {'Class':20s} {'n':>4} {'PnL':>9} {'Avg':>8} {'Stop%':>7} {'TP1+runner%':>12} {'VIX_avg':>9}")
    print(f"  {'-'*75}")
    for cls in sorted(by_cls.keys(), key=lambda c: -sum(t.dollar_pnl for t in by_cls[c])):
        ts = by_cls[cls]
        pnl = sum(t.dollar_pnl for t in ts)
        avg = pnl / len(ts)
        stop_n = sum(1 for t in ts if "STOP" in (_exit_group(t)).upper() and "RUNNER" not in _exit_group(t))
        runner_n = sum(1 for t in ts if "runner_time" in _exit_group(t) or "runner_ribbon" in _exit_group(t))
        avg_vix = sum(t.entry_vix for t in ts) / len(ts)
        print(f"  {cls:20s} {len(ts):>4} {pnl:>9,.0f} {avg:>8.0f} {stop_n/len(ts)*100:>6.1f}% {runner_n/len(ts)*100:>11.1f}% {avg_vix:>9.1f}")

    # Survivor breakdown
    print(f"\n  TP1+runner survivors (runner_time + runner_ribbon):")
    print(f"  {'Class':20s} {'n':>4} {'total_pnl':>10} {'avg_pnl':>9}")
    print(f"  {'-'*50}")
    survivor_classes = collections.defaultdict(list)
    for t in trades:
        if _exit_group(t) in ("TP1+runner_time", "TP1+runner_ribbon"):
            _, cls = _classify(t)
            survivor_classes[cls].append(t.dollar_pnl)
    if not survivor_classes:
        print("  (no TP1+runner survivors)")
    else:
        for cls, pnls in sorted(survivor_classes.items(), key=lambda x: -sum(x[1])):
            print(f"  {cls:20s} {len(pnls):>4} {sum(pnls):>10,.0f} {sum(pnls)/len(pnls):>9.0f}")

    # Time bucket × class
    print(f"\n  By time bucket × trigger class:")
    print(f"  {'Bucket':15s} {'Class':20s} {'n':>4} {'PnL':>9} {'Avg':>8} {'Stop%':>7}")
    print(f"  {'-'*70}")
    bucket_cls = collections.defaultdict(list)
    for t in trades:
        _, cls = _classify(t)
        bucket_cls[(_time_bucket(t), cls)].append(t)
    for (bucket, cls) in sorted(bucket_cls.keys()):
        ts = bucket_cls[(bucket, cls)]
        pnl = sum(t.dollar_pnl for t in ts)
        stop_n = sum(1 for t in ts if "STOP" in _exit_group(t).upper() and "RUNNER" not in _exit_group(t))
        print(f"  {bucket:15s} {cls:20s} {len(ts):>4} {pnl:>9,.0f} {pnl/len(ts):>8.0f} {stop_n/len(ts)*100:>6.1f}%")

    # Build result dict
    result = {
        "n": n,
        "total_pnl": round(total_pnl, 2),
        "by_class": {
            cls: {
                "n": len(ts),
                "pnl": round(sum(t.dollar_pnl for t in ts), 2),
                "avg": round(sum(t.dollar_pnl for t in ts) / len(ts), 2),
                "stop_rate": round(sum(1 for t in ts if "STOP" in _exit_group(t).upper() and "RUNNER" not in _exit_group(t)) / len(ts), 3),
                "runner_rate": round(sum(1 for t in ts if "runner_time" in _exit_group(t) or "runner_ribbon" in _exit_group(t)) / len(ts), 3),
                "avg_vix": round(sum(t.entry_vix for t in ts) / len(ts), 2),
            }
            for cls, ts in by_cls.items()
        },
        "tp1_runner_survivors": {
            cls: {"n": len(pnls), "pnl": round(sum(pnls), 2), "avg": round(sum(pnls)/len(pnls), 2)}
            for cls, pnls in survivor_classes.items()
        },
    }
    return result


if __name__ == "__main__":
    print("Loading data...")
    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    print("Running Safe IS (verify: expect IS n=130 pnl=+16,174)...")
    r_is = _run(spy_df, vix_df, IS_START, IS_END)
    is_pnl = sum(t.dollar_pnl for t in r_is.trades)
    print(f"IS: n={len(r_is.trades)} pnl={is_pnl:+,.0f}")
    if len(r_is.trades) != 130:
        print(f"WARNING: expected IS n=130, got n={len(r_is.trades)} — params mismatch!")

    print("Running Safe OOS...")
    r_oos = _run(spy_df, vix_df, OOS_START, OOS_END)
    oos_pnl = sum(t.dollar_pnl for t in r_oos.trades)
    print(f"OOS: n={len(r_oos.trades)} pnl={oos_pnl:+,.0f}")

    is_result = _analyze(r_is.trades, "IS (2025-01-02 to 2026-05-07)")
    oos_result = _analyze(r_oos.trades, "OOS (2026-05-08 to 2026-06-16)")

    out = {
        "study": "Safe trigger-class x exit-type decomposition",
        "date": "2026-06-17",
        "is": is_result,
        "oos": oos_result,
    }
    out_path = ROOT / "analysis" / "recommendations" / "safe_trigger_exit_decomp.json"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nSaved: {out_path}")
