"""
SAFE TIME-OF-DAY × TRIGGER-CLASS GATE SWEEP (2026-06-17)

From safe_trigger_exit_decomp.py results (IS n=130, OOS n=21):
  conf+lvl_rec: IS morning n=20 avg=$398, midday n=8 avg=-$221, afternoon n=5 avg=-$82
  conf+lvl_rej: IS n=15 avg=$605 (VIX analysis ongoing)

THE QUESTION: Does a "morning-only" gate for specific classes improve OOS?
  - Block conf+lvl_rec midday/afternoon (only trade it morning)?
  - Block conf+lvl_rej outside 11:30-14:30 window?
  - Or does midday-block hurt OOS (where data is sparser)?

APPROACH: For each candidate gate, simulate IS+OOS impact via post-hoc filtering.
No new orchestrator params needed (same as VIX simulation approach).

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


def _time_bucket(t):
    h, m = t.entry_time_et.hour, t.entry_time_et.minute
    total_min = h * 60 + m
    if total_min < 11 * 60 + 30:
        return "morning"  # 09:35-11:30
    if total_min < 14 * 60:
        return "midday"   # 11:30-14:00
    return "afternoon"   # 14:00-15:55


def _date(t):
    et = t.entry_time_et
    return (et.replace(tzinfo=None) if getattr(et, "tzinfo", None) else et).date()


def _exit_group(t):
    r = t.exit_reason.value if t.exit_reason else "UNKNOWN"
    if "RUNNER_TIME" in r or "RUNNER_RIBBON" in r or "RUNNER_TARGET" in r:
        return "TP1+runner"
    if "STOP" in r:
        return "STOP"
    return r


def _show_time_breakdown(trades, label):
    """Show per-class x time-bucket breakdown."""
    print(f"\n  {label} — Class x Time breakdown:")
    print(f"  {'Class':20s} {'Bucket':12s} {'n':>4} {'pnl':>9} {'avg':>8} {'stop%':>7}")
    print(f"  {'-'*65}")
    buckets = collections.defaultdict(list)
    for t in trades:
        cls = _classify(t)
        bk = _time_bucket(t)
        buckets[(cls, bk)].append(t)

    # Sort by class, then time
    for cls in ["conf+lvl_rec", "conf+lvl_rej", "lvl_rec_only", "trendline", "other"]:
        for bk in ["morning", "midday", "afternoon"]:
            ts = buckets[(cls, bk)]
            if not ts:
                continue
            pnl = sum(t.dollar_pnl for t in ts)
            stop_n = sum(1 for t in ts if _exit_group(t) == "STOP")
            print(f"  {cls:20s} {bk:12s} {len(ts):>4} {pnl:>9,.0f} {pnl/len(ts):>8.0f} {stop_n/len(ts)*100:>6.1f}%")

    return buckets


def _simulate_gate(base_trades, cand_trades_fn, label):
    """Simulate a gate by post-filtering: gate drops trades where cand_trades_fn returns False."""
    kept = [t for t in base_trades if cand_trades_fn(t)]
    dropped = [t for t in base_trades if not cand_trades_fn(t)]
    return kept, dropped


def _autorate_gate(spy_df, vix_df, gate_fn, gate_label):
    """Run autorate check on a gate defined by gate_fn (returns True = keep trade)."""
    print(f"\n  {'='*68}")
    print(f"  GATE: {gate_label}")
    print(f"  {'='*68}")

    r_is = _run(spy_df, vix_df, IS_START, IS_END)
    r_oos = _run(spy_df, vix_df, OOS_START, OOS_END)

    is_base_pnl = sum(t.dollar_pnl for t in r_is.trades)
    oos_base_pnl = sum(t.dollar_pnl for t in r_oos.trades)

    is_cand = [t for t in r_is.trades if gate_fn(t)]
    oos_cand = [t for t in r_oos.trades if gate_fn(t)]

    is_cand_pnl = sum(t.dollar_pnl for t in is_cand)
    oos_cand_pnl = sum(t.dollar_pnl for t in oos_cand)

    n_is = len(r_is.trades)
    n_oos = len(r_oos.trades)
    is_delta = is_cand_pnl - is_base_pnl
    oos_delta = oos_cand_pnl - oos_base_pnl
    wf = (oos_delta / n_oos) / (is_delta / n_is) if is_delta != 0 else 0.0
    oos_pos = oos_cand_pnl > 0

    dropped_is = [t for t in r_is.trades if not gate_fn(t)]
    dropped_oos = [t for t in r_oos.trades if not gate_fn(t)]

    print(f"  IS: base n={n_is} pnl={is_base_pnl:+,.0f} | cand n={len(is_cand)} pnl={is_cand_pnl:+,.0f} delta={is_delta:+,.0f}")
    print(f"  OOS: base n={n_oos} pnl={oos_base_pnl:+,.0f} | cand n={len(oos_cand)} pnl={oos_cand_pnl:+,.0f} delta={oos_delta:+,.0f}")
    print(f"  Dropped IS n={len(dropped_is)} pnl_dropped={sum(t.dollar_pnl for t in dropped_is):+,.0f}")
    print(f"  Dropped OOS n={len(dropped_oos)} pnl_dropped={sum(t.dollar_pnl for t in dropped_oos):+,.0f}")
    print(f"  WF_norm: {wf:.3f} | OOS_positive: {oos_pos}")

    sw_hurt = 0
    for sw_label, s, e in IS_SUBWINDOWS:
        r = _run(spy_df, vix_df, s, e)
        b = sum(t.dollar_pnl for t in r.trades)
        c = sum(t.dollar_pnl for t in [t for t in r.trades if gate_fn(t)])
        d = c - b
        hurt = d < -500
        if hurt:
            sw_hurt += 1
        tag = " <-- HURT" if hurt else ""
        print(f"    {sw_label}: base={b:+,.0f} cand={c:+,.0f} delta={d:+,.0f}{tag}")

    anchor_ok = True
    base_by = {_date(t): t.dollar_pnl for t in r_is.trades}
    cand_by = {_date(t): t.dollar_pnl for t in is_cand}
    for d in J_WINNERS:
        b, c = base_by.get(d, 0), cand_by.get(d, 0)
        if c < b - 50:
            print(f"  ANCHOR FAIL J_WINNER {d}: base={b:.0f} cand={c:.0f}")
            anchor_ok = False
    for d in J_LOSERS:
        b, c = base_by.get(d, 0), cand_by.get(d, 0)
        if c < b - 50:
            print(f"  ANCHOR FAIL J_LOSER {d}: cand={c:.0f} worse than base={b:.0f}")
            anchor_ok = False
    if anchor_ok:
        print("  ANCHOR: PASS")

    # L155 guard: IS_delta must be > 0 — WF formula is invalid when IS is hurt
    if is_delta <= 0:
        print(f"  IS_delta <= 0 ({is_delta:+,.0f}): gate hurts or has no IS impact -> REJECT")
        return {"gate": gate_label, "IS_delta": round(is_delta, 2), "OOS_delta": round(oos_delta, 2),
                "WF": 0.0, "OOS_positive": oos_pos, "SW_hurt": sw_hurt, "anchor_OK": anchor_ok,
                "verdict": "REJECT (IS_delta<=0)"}
    g_oos = "PASS" if oos_pos else "FAIL"
    g_wf = "PASS" if wf >= 0.70 else "FAIL"
    g_sw = "PASS" if sw_hurt <= 1 else "FAIL"
    g_anch = "PASS" if anchor_ok else "FAIL"
    all_pass = all(g == "PASS" for g in [g_oos, g_wf, g_sw, g_anch])
    verdict = "AUTO-RATIFY" if all_pass else "REJECT"
    print(f"  GATES: OOS={g_oos} WF={g_wf}({wf:.3f}) SW={g_sw}({sw_hurt}) ANCHOR={g_anch}")
    print(f"  VERDICT: {verdict}")

    return {
        "gate": gate_label,
        "IS_delta": round(is_delta, 2),
        "OOS_delta": round(oos_delta, 2),
        "WF": round(wf, 3),
        "OOS_positive": oos_pos,
        "SW_hurt": sw_hurt,
        "anchor_OK": anchor_ok,
        "verdict": verdict,
    }


if __name__ == "__main__":
    print("Loading data...")
    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    print("\nRunning Safe IS (verify: expect n=130)...")
    r_is = _run(spy_df, vix_df, IS_START, IS_END)
    r_oos = _run(spy_df, vix_df, OOS_START, OOS_END)
    print(f"IS: n={len(r_is.trades)} pnl={sum(t.dollar_pnl for t in r_is.trades):+,.0f}")
    print(f"OOS: n={len(r_oos.trades)} pnl={sum(t.dollar_pnl for t in r_oos.trades):+,.0f}")

    is_buckets = _show_time_breakdown(r_is.trades, "IS")
    oos_buckets = _show_time_breakdown(r_oos.trades, "OOS")

    # Gate candidates based on the IS decomp:
    # 1. Block conf+lvl_rec midday+afternoon (IS midday avg=-$221, afternoon avg=-$82)
    # 2. Block trendline morning (IS morning avg=-$10 for tl_pure — but this overlaps midday_trendline_gate)
    # 3. Block lvl_rec_only midday (IS: midday avg potentially poor)
    # 4. Allow ONLY conf classes in midday/afternoon (conf+lvl_rec/rej only in afternoon)

    gates = [
        (
            "block conf+lvl_rec midday+afternoon",
            lambda t: not (_classify(t) == "conf+lvl_rec" and _time_bucket(t) in ("midday", "afternoon"))
        ),
        (
            "block conf+lvl_rec afternoon only",
            lambda t: not (_classify(t) == "conf+lvl_rec" and _time_bucket(t) == "afternoon")
        ),
        (
            "block conf+lvl_rec midday only",
            lambda t: not (_classify(t) == "conf+lvl_rec" and _time_bucket(t) == "midday")
        ),
        (
            "morning-only for ALL trades (block midday+afternoon for all classes)",
            lambda t: _time_bucket(t) == "morning"
        ),
        (
            "block non-conf midday+afternoon (conf-only after 11:30)",
            lambda t: not (_classify(t) not in ("conf+lvl_rec", "conf+lvl_rej", "conf+rf", "conf+seq", "conf_other")
                           and _time_bucket(t) in ("midday", "afternoon"))
        ),
    ]

    results = []
    for gate_label, gate_fn in gates:
        res = _autorate_gate(spy_df, vix_df, gate_fn, gate_label)
        results.append(res)

    out = {
        "study": "Safe time-of-day x trigger-class gate sweep",
        "date": "2026-06-17",
        "is_n": len(r_is.trades),
        "oos_n": len(r_oos.trades),
        "is_pnl": round(sum(t.dollar_pnl for t in r_is.trades), 2),
        "oos_pnl": round(sum(t.dollar_pnl for t in r_oos.trades), 2),
        "gate_results": results,
    }
    out_path = ROOT / "analysis" / "recommendations" / "safe_time_class_gate.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nSaved: {out_path}")
