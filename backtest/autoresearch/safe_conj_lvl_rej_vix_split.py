"""
SAFE conf+lvl_rej VIX-STRATIFIED ANALYSIS (2026-06-17)

Safe IS: conf+lvl_rej n=15 avg=$605 at VIX_avg=20.6 (BEST Safe IS class)
Safe OOS: conf+lvl_rej n=6 avg=$77 (large IS→OOS degradation)

THE QUESTION:
  - Is the IS edge driven by a specific VIX bucket (e.g. VIX>20)?
  - Do OOS conf+lvl_rej trades enter at a different VIX regime?
  - Can a VIX gate (e.g. require VIX>=19.0 for conf+lvl_rej) improve OOS?
  - Or is the IS avg=$605 from 1-2 large outlier trades (not a distributional edge)?

APPROACH:
  1. Pull all IS + OOS trades, filter to conf+lvl_rej class
  2. Distribution: VIX buckets <15, 15-18, 18-21, 21-25, >25
  3. Per-bucket: n, pnl, avg, stop%, exit-type breakdown
  4. Correlate VIX with pnl (is it monotonic? or driven by outliers?)
  5. Test: VIX>=19 gate on conf+lvl_rej — does it pass autorate?

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

IS_SUBWINDOWS = [
    ("W1 Jan-Jun 2025", dt.date(2025, 1, 2),  dt.date(2025, 6, 30)),
    ("W2 Jul-Dec 2025", dt.date(2025, 7, 1),  dt.date(2025, 12, 31)),
    ("W3 Jan-Mar 2026", dt.date(2026, 1, 2),  dt.date(2026, 3, 31)),
    ("W4 Apr-May 2026", dt.date(2026, 4, 1),  dt.date(2026, 5, 7)),
]

J_WINNERS = {dt.date(2026, 4, 29), dt.date(2026, 5, 1), dt.date(2026, 5, 4)}
J_LOSERS  = {dt.date(2026, 5, 5), dt.date(2026, 5, 6)}

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


def _run(spy_df, vix_df, start, end, extra_kw=None, extra_ovr=None):
    kw = dict(SAFE_KW)
    ovr = dict(SAFE_OVR)
    if extra_kw:
        kw.update(extra_kw)
    if extra_ovr:
        ovr.update(extra_ovr)
    return run_backtest(spy_df, vix_df, start_date=start, end_date=end,
                        params_overrides=ovr, **kw)


def _classify(t):
    trig = set(t.triggers_fired)
    has_conf = "confluence" in trig
    has_rec = "level_reclaim" in trig
    has_rej = "level_rejection" in trig
    has_rf = "ribbon_flip" in trig
    has_seq = "sequence_rejection" in trig or "sequence_reclaim" in trig
    has_tl = "trendline_rejection" in trig
    if has_conf and has_rec:
        return "conf+lvl_rec"
    if has_conf and has_rej:
        return "conf+lvl_rej"
    if has_conf and has_rf:
        return "conf+rf"
    if has_conf and has_seq:
        return "conf+seq"
    if has_conf:
        return "conf_other"
    if has_rec:
        return "lvl_rec_only"
    if has_rej:
        return "lvl_rej_only"
    if has_tl:
        return "trendline"
    return "other"


def _exit_group(t):
    r = t.exit_reason.value if t.exit_reason else "UNKNOWN"
    if "RUNNER_TIME" in r:
        return "TP1+runner_time"
    if "RUNNER_RIBBON" in r:
        return "TP1+runner_ribbon"
    if "RUNNER_TARGET" in r:
        return "TP1+runner_target"
    if "RUNNER_BE" in r:
        return "TP1+runner_be"
    if "TP1" in r:
        return "TP1_other"
    if "PREMIUM_STOP" in r or "LEVEL_STOP" in r:
        return "STOP"
    if "TIME_STOP" in r:
        return "time_stop"
    return r


def _vix_bucket(vix):
    if vix < 15:
        return "<15"
    if vix < 18:
        return "15-18"
    if vix < 21:
        return "18-21"
    if vix < 25:
        return "21-25"
    return ">=25"


def _date(t):
    et = t.entry_time_et
    return (et.replace(tzinfo=None) if getattr(et, "tzinfo", None) else et).date()


def _analyze_clr(trades, label):
    clr = [t for t in trades if _classify(t) == "conf+lvl_rej"]
    n_all = len(trades)
    n_clr = len(clr)
    if not clr:
        print(f"  {label}: conf+lvl_rej n=0 (from n={n_all} total)")
        return None

    total_pnl = sum(t.dollar_pnl for t in clr)
    avg_vix = sum(t.entry_vix for t in clr) / n_clr
    print(f"\n{'='*72}")
    print(f"  {label}: conf+lvl_rej n={n_clr} (from n={n_all} total) | pnl={total_pnl:+,.0f} avg={total_pnl/n_clr:.0f} VIX_avg={avg_vix:.1f}")
    print(f"{'='*72}")

    # Sort by pnl descending — outlier check
    sorted_t = sorted(clr, key=lambda t: -t.dollar_pnl)
    print(f"\n  Per-trade detail (sorted by pnl):")
    print(f"  {'Date':12s} {'Time':8s} {'VIX':7s} {'Pnl':>9s} {'Exit':25s}")
    print(f"  {'-'*65}")
    for t in sorted_t:
        d = _date(t)
        time_str = t.entry_time_et.strftime("%H:%M")
        eg = _exit_group(t)
        print(f"  {str(d):12s} {time_str:8s} {t.entry_vix:7.1f} {t.dollar_pnl:>9.0f} {eg:25s}")

    # VIX bucket distribution
    print(f"\n  VIX bucket breakdown:")
    print(f"  {'Bucket':10s} {'n':>4} {'pnl':>9} {'avg':>8} {'stop%':>7} {'TP1+runner%':>12}")
    print(f"  {'-'*55}")
    by_bucket = collections.defaultdict(list)
    for t in clr:
        by_bucket[_vix_bucket(t.entry_vix)].append(t)
    for bucket in ["<15", "15-18", "18-21", "21-25", ">=25"]:
        ts = by_bucket[bucket]
        if not ts:
            continue
        pnl = sum(t.dollar_pnl for t in ts)
        stop_n = sum(1 for t in ts if _exit_group(t) == "STOP")
        runner_n = sum(1 for t in ts if "runner" in _exit_group(t))
        print(f"  {bucket:10s} {len(ts):>4} {pnl:>9,.0f} {pnl/len(ts):>8.0f} {stop_n/len(ts)*100:>6.1f}% {runner_n/len(ts)*100:>11.1f}%")

    # Correlation: is higher VIX = higher pnl?
    vix_vals = [t.entry_vix for t in clr]
    pnl_vals = [t.dollar_pnl for t in clr]
    if len(vix_vals) >= 3:
        mean_vix = sum(vix_vals) / len(vix_vals)
        mean_pnl = sum(pnl_vals) / len(pnl_vals)
        cov = sum((v - mean_vix) * (p - mean_pnl) for v, p in zip(vix_vals, pnl_vals)) / len(vix_vals)
        std_vix = (sum((v - mean_vix)**2 for v in vix_vals) / len(vix_vals))**0.5
        std_pnl = (sum((p - mean_pnl)**2 for p in pnl_vals) / len(pnl_vals))**0.5
        corr = cov / (std_vix * std_pnl) if std_vix > 0 and std_pnl > 0 else 0.0
        print(f"\n  VIX-PnL correlation: {corr:+.3f} (n={len(vix_vals)})")
        if abs(corr) > 0.3:
            print(f"  --> {'POSITIVE' if corr > 0 else 'NEGATIVE'} correlation — VIX gate may discriminate!")
        else:
            print(f"  --> Weak correlation — VIX gate unlikely to add discrimination")

    return {
        "n": n_clr,
        "pnl": round(total_pnl, 2),
        "avg": round(total_pnl / n_clr, 2),
        "avg_vix": round(avg_vix, 2),
        "by_bucket": {
            bucket: {
                "n": len(ts),
                "pnl": round(sum(t.dollar_pnl for t in ts), 2),
                "avg": round(sum(t.dollar_pnl for t in ts) / len(ts), 2),
            }
            for bucket, ts in by_bucket.items() if ts
        },
        "per_trade": [
            {"date": str(_date(t)), "vix": round(t.entry_vix, 1), "pnl": round(t.dollar_pnl, 2), "exit": _exit_group(t)}
            for t in sorted_t
        ],
    }


def _gate_sweep(spy_df, vix_df, vix_threshold):
    """Test: only take conf+lvl_rej trades when entry VIX >= vix_threshold."""
    # NOTE: orchestrator doesn't have a conf+lvl_rej VIX gate param natively.
    # We simulate: run baseline, then recompute PnL excluding conf+lvl_rej trades below threshold.
    # This gives the theoretical IS/OOS impact without a new orchestrator param.
    print(f"\n  === VIX>={vix_threshold:.0f} GATE SIMULATION for conf+lvl_rej ===")

    r_is = _run(spy_df, vix_df, IS_START, IS_END)
    r_oos = _run(spy_df, vix_df, OOS_START, OOS_END)

    def _apply_gate(trades, threshold):
        kept, dropped = [], []
        for t in trades:
            if _classify(t) == "conf+lvl_rej" and t.entry_vix < threshold:
                dropped.append(t)
            else:
                kept.append(t)
        return kept, dropped

    is_base = r_is.trades
    oos_base = r_oos.trades
    is_cand, is_drop = _apply_gate(is_base, vix_threshold)
    oos_cand, oos_drop = _apply_gate(oos_base, vix_threshold)

    is_delta = sum(t.dollar_pnl for t in is_cand) - sum(t.dollar_pnl for t in is_base)
    oos_delta = sum(t.dollar_pnl for t in oos_cand) - sum(t.dollar_pnl for t in oos_base)
    n_is = len(is_base)
    n_oos = len(oos_base)
    wf = (oos_delta / n_oos) / (is_delta / n_is) if is_delta != 0 else 0.0
    oos_pos = sum(t.dollar_pnl for t in oos_cand) > 0

    print(f"  IS: baseline_n={n_is} cand_n={len(is_cand)} dropped={len(is_drop)} delta={is_delta:+,.0f}")
    print(f"  OOS: baseline_n={n_oos} cand_n={len(oos_cand)} dropped={len(oos_drop)} delta={oos_delta:+,.0f}")
    print(f"  WF_norm: {wf:.3f}")
    print(f"  OOS_positive: {oos_pos} ({sum(t.dollar_pnl for t in oos_cand):+,.0f})")

    # Sub-window check
    sw_hurt = 0
    for sw_label, s, e in IS_SUBWINDOWS:
        r = _run(spy_df, vix_df, s, e)
        b = sum(t.dollar_pnl for t in r.trades)
        kept, _ = _apply_gate(r.trades, vix_threshold)
        c = sum(t.dollar_pnl for t in kept)
        delta = c - b
        hurt = delta < -500
        if hurt:
            sw_hurt += 1
        tag = " <-- HURT" if hurt else ""
        print(f"    {sw_label}: base={b:+,.0f} cand={c:+,.0f} delta={delta:+,.0f}{tag}")

    # Anchor check
    is_by_date = {_date(t): t.dollar_pnl for t in is_base}
    cand_by_date = {_date(t): t.dollar_pnl for t in is_cand}
    anchor_ok = True
    for d in J_WINNERS:
        b, c = is_by_date.get(d, 0), cand_by_date.get(d, 0)
        if c < b - 50:
            print(f"  ANCHOR FAIL: J_WINNER {d}: base={b:.0f} cand={c:.0f}")
            anchor_ok = False
    for d in J_LOSERS:
        b, c = is_by_date.get(d, 0), cand_by_date.get(d, 0)
        if c < b - 50:
            print(f"  ANCHOR FAIL: J_LOSER {d}: cand WORSE {c:.0f} vs base {b:.0f}")
            anchor_ok = False
    if anchor_ok:
        print("  ANCHOR: PASS")

    # L155 guard: IS_delta must be > 0 — WF formula is invalid when IS is hurt
    if is_delta <= 0:
        print(f"  IS_delta <= 0 ({is_delta:+,.0f}): gate hurts or has no IS impact → REJECT")
        return {"threshold": vix_threshold, "IS_delta": round(is_delta, 2), "OOS_delta": round(oos_delta, 2),
                "WF": 0.0, "OOS_positive": oos_pos, "SW_hurt": sw_hurt, "anchor_OK": anchor_ok,
                "verdict": "REJECT (IS_delta<=0)"}
    g_oos = "PASS" if oos_pos else "FAIL"
    g_wf = "PASS" if wf >= 0.70 else "FAIL"
    g_sw = "PASS" if sw_hurt <= 1 else "FAIL"
    g_anch = "PASS" if anchor_ok else "FAIL"
    all_pass = all(g == "PASS" for g in [g_oos, g_wf, g_sw, g_anch])
    verdict = "AUTO-RATIFY" if all_pass else "REJECT"
    print(f"  OOS_positive: {g_oos} | WF: {g_wf} ({wf:.3f}) | SW: {g_sw} ({sw_hurt}) | ANCHOR: {g_anch}")
    print(f"  VERDICT: {verdict}")
    return {"threshold": vix_threshold, "IS_delta": round(is_delta, 2), "OOS_delta": round(oos_delta, 2),
            "WF": round(wf, 3), "OOS_positive": oos_pos, "SW_hurt": sw_hurt, "anchor_OK": anchor_ok,
            "verdict": verdict}


if __name__ == "__main__":
    print("Loading data...")
    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    print("\nRunning Safe IS (verify: expect n=130 pnl=+16,174)...")
    r_is = _run(spy_df, vix_df, IS_START, IS_END)
    is_pnl = sum(t.dollar_pnl for t in r_is.trades)
    print(f"IS: n={len(r_is.trades)} pnl={is_pnl:+,.0f}")

    print("Running Safe OOS...")
    r_oos = _run(spy_df, vix_df, OOS_START, OOS_END)
    oos_pnl = sum(t.dollar_pnl for t in r_oos.trades)
    print(f"OOS: n={len(r_oos.trades)} pnl={oos_pnl:+,.0f}")

    is_result = _analyze_clr(r_is.trades, "IS (2025-01-02 to 2026-05-07)")
    oos_result = _analyze_clr(r_oos.trades, "OOS (2026-05-08 to 2026-06-16)")

    # VIX gate sweep: test thresholds 17, 18, 19, 20, 21
    print(f"\n{'='*72}")
    print("  VIX GATE SWEEP — conf+lvl_rej only (simulation without new param)")
    print(f"{'='*72}")
    gate_results = []
    for thr in [17.0, 18.0, 19.0, 20.0, 21.0]:
        res = _gate_sweep(spy_df, vix_df, thr)
        gate_results.append(res)

    out = {
        "study": "Safe conf+lvl_rej VIX-stratified analysis",
        "date": "2026-06-17",
        "is": is_result,
        "oos": oos_result,
        "vix_gate_sweep": gate_results,
    }
    out_path = ROOT / "analysis" / "recommendations" / "safe_conj_lvl_rej_vix_split.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nSaved: {out_path}")
