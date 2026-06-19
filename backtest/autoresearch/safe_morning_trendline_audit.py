"""
SAFE MORNING TRENDLINE AUDIT (2026-06-17)

After the midday_trendline_gate ratification (blocks trendline 11:30+), the
remaining trendline exposure is MORNING ONLY (09:35-11:30 ET).

The full trendline IS class showed avg=-$8.92 (n=64) -- nearly flat and mainly noise.
But that included midday/afternoon trendlines (now blocked). What's the picture for
morning trendlines specifically?

This script:
1. Runs Safe baseline (midday_trendline_gate=True to match production)
2. Breaks down morning trendline by sub-classification (pure, +ribbon_flip, +lvl_rej)
3. Tests gate: block ALL morning trendline entries
4. Tests gate: block morning trendline if ribbon_spread < 35c (need higher conviction)
5. Provides OOS breakdown for validation

Target: identify if morning trendlines are dragging down OOS performance, and whether
a sub-gate can preserve the money-makers (tl+ribbon_flip avg=$498 IS, n=6).

Security: read-only. No Alpaca calls. Free-tier only.
"""
from __future__ import annotations
import sys, json, datetime as dt, collections, pathlib

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

# Production Safe baseline (current params post all 3 ratified gates)
SAFE_KW = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=True,         # ratified gate
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
    block_conf_lvl_rec_afternoon=True,  # ratified gate
)
SAFE_OVR = {"vix_bull_max": 18.0}


def _run(spy_df, vix_df, start, end, extra_kw=None):
    kw = dict(SAFE_KW)
    if extra_kw:
        kw.update(extra_kw)
    return run_backtest(spy_df, vix_df, start_date=start, end_date=end,
                        params_overrides=dict(SAFE_OVR), **kw)


def _classify(t):
    trig = set(t.triggers_fired)
    has_conf  = "confluence" in trig
    has_rec   = "level_reclaim" in trig
    has_rej   = "level_rejection" in trig
    has_rf    = "ribbon_flip" in trig
    has_seq   = "sequence_rejection" in trig or "sequence_reclaim" in trig
    has_tl    = "trendline_rejection" in trig
    if has_conf and has_rec:  return "conf+lvl_rec"
    if has_conf and has_rej:  return "conf+lvl_rej"
    if has_conf and has_rf:   return "conf+rf"
    if has_conf and has_seq:  return "conf+seq"
    if has_conf:              return "conf_other"
    if has_rec:               return "lvl_rec_only"
    if has_rej:               return "lvl_rej_only"
    if has_tl:
        # sub-classify trendline by what else fired
        if has_rf:            return "tl+ribbon_flip"
        if has_rej:           return "tl+lvl_rej"
        if has_rec:           return "tl+lvl_rec"
        if has_seq:           return "tl+seq"
        return "tl_pure"
    return "other"


def _is_morning_tl(t):
    trig = set(t.triggers_fired)
    if "trendline_rejection" not in trig:
        return False
    et = t.entry_time_et
    if getattr(et, "tzinfo", None):
        et = et.replace(tzinfo=None)
    total_min = et.hour * 60 + et.minute
    return total_min < 11 * 60 + 30  # before 11:30 ET


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


def _stats(trades):
    if not trades:
        return {"n": 0, "total": 0.0, "avg": 0.0, "stop_pct": 0.0}
    pnl = sum(t.dollar_pnl for t in trades)
    stops = sum(1 for t in trades if _exit_group(t) == "STOP")
    return {"n": len(trades), "total": round(pnl, 1), "avg": round(pnl / len(trades), 1),
            "stop_pct": round(stops / len(trades) * 100, 1)}


def _show_breakdown(trades, label):
    print(f"\n  {label} -- TRIGGER CLASS BREAKDOWN:")
    print(f"  {'Class':20s} {'n':>4} {'total':>9} {'avg':>8} {'stop%':>7}")
    print(f"  {'-'*55}")
    by_cls = collections.defaultdict(list)
    for t in trades:
        by_cls[_classify(t)].append(t)
    all_classes = sorted(by_cls.keys(), key=lambda c: -abs(sum(x.dollar_pnl for x in by_cls[c])))
    for cls in all_classes:
        s = _stats(by_cls[cls])
        print(f"  {cls:20s} {s['n']:>4} {s['total']:>9,.0f} {s['avg']:>8,.0f} {s['stop_pct']:>6.1f}%")

    print(f"\n  {label} -- MORNING TRENDLINE SUB-BREAKDOWN:")
    print(f"  {'Sub-class':20s} {'n':>4} {'total':>9} {'avg':>8} {'stop%':>7}")
    print(f"  {'-'*55}")
    morning_tl = [t for t in trades if _is_morning_tl(t)]
    by_subcls = collections.defaultdict(list)
    for t in morning_tl:
        by_subcls[_classify(t)].append(t)
    for cls in sorted(by_subcls.keys(), key=lambda c: -abs(sum(x.dollar_pnl for x in by_subcls[c]))):
        s = _stats(by_subcls[cls])
        print(f"  {cls:20s} {s['n']:>4} {s['total']:>9,.0f} {s['avg']:>8,.0f} {s['stop_pct']:>6.1f}%")
    if not morning_tl:
        print(f"  (no morning trendline trades)")

    return by_cls, morning_tl


def _autorate(spy_df, vix_df, gate_fn, gate_label, base_is_n, base_is_pnl, base_oos_n, base_oos_pnl):
    print(f"\n  {'='*65}")
    print(f"  GATE: {gate_label}")
    r_is  = _run(spy_df, vix_df, IS_START, IS_END)
    r_oos = _run(spy_df, vix_df, OOS_START, OOS_END)

    is_cand  = [t for t in r_is.trades  if gate_fn(t)]
    oos_cand = [t for t in r_oos.trades if gate_fn(t)]
    is_pnl   = sum(t.dollar_pnl for t in is_cand)
    oos_pnl  = sum(t.dollar_pnl for t in oos_cand)
    is_delta  = is_pnl  - base_is_pnl
    oos_delta = oos_pnl - base_oos_pnl

    print(f"  IS:  base n={base_is_n} pnl={base_is_pnl:+,.0f} | cand n={len(is_cand)} pnl={is_pnl:+,.0f} delta={is_delta:+,.0f}")
    print(f"  OOS: base n={base_oos_n} pnl={base_oos_pnl:+,.0f} | cand n={len(oos_cand)} pnl={oos_pnl:+,.0f} delta={oos_delta:+,.0f}")

    dropped_is  = [t for t in r_is.trades  if not gate_fn(t)]
    dropped_oos = [t for t in r_oos.trades if not gate_fn(t)]
    print(f"  Dropped IS n={len(dropped_is)} pnl={sum(t.dollar_pnl for t in dropped_is):+,.0f}")
    print(f"  Dropped OOS n={len(dropped_oos)} pnl={sum(t.dollar_pnl for t in dropped_oos):+,.0f}")

    # L155 guard
    if is_delta <= 0:
        print(f"  IS_delta={is_delta:+,.0f} <= 0: REJECT (L155)")
        return {"gate": gate_label, "IS_delta": round(is_delta, 2), "OOS_delta": round(oos_delta, 2),
                "verdict": "REJECT (IS_delta<=0)"}

    n_is, n_oos = base_is_n, base_oos_n
    wf_norm = (oos_delta / n_oos) / (is_delta / n_is)
    oos_pos = oos_pnl > 0

    sw_hurt = 0
    for sw_label, s, e in IS_SUBWINDOWS:
        r = _run(spy_df, vix_df, s, e)
        b = sum(t.dollar_pnl for t in r.trades)
        c = sum(t.dollar_pnl for t in [t2 for t2 in r.trades if gate_fn(t2)])
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

    g_oos  = "PASS" if oos_pos else "FAIL"
    g_wf   = "PASS" if wf_norm >= 0.70 else "FAIL"
    g_sw   = "PASS" if sw_hurt <= 1 else "FAIL"
    g_anch = "PASS" if anchor_ok else "FAIL"
    all_pass = all(g == "PASS" for g in [g_oos, g_wf, g_sw, g_anch])
    verdict = "AUTO-RATIFY" if all_pass else "REJECT"
    print(f"  GATES: OOS={g_oos} WF={g_wf}({wf_norm:.3f}) SW={g_sw}({sw_hurt}) ANCHOR={g_anch}")
    print(f"  VERDICT: {verdict}")

    return {"gate": gate_label, "IS_delta": round(is_delta, 2), "OOS_delta": round(oos_delta, 2),
            "WF": round(wf_norm, 3), "OOS_positive": oos_pos, "SW_hurt": sw_hurt,
            "anchor_OK": anchor_ok, "verdict": verdict}


if __name__ == "__main__":
    print("Loading data...")
    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    print("\nRunning Safe baseline (production params, midday_trendline_gate=True)...")
    r_is  = _run(spy_df, vix_df, IS_START, IS_END)
    r_oos = _run(spy_df, vix_df, OOS_START, OOS_END)
    base_is_pnl  = sum(t.dollar_pnl for t in r_is.trades)
    base_oos_pnl = sum(t.dollar_pnl for t in r_oos.trades)
    base_is_n    = len(r_is.trades)
    base_oos_n   = len(r_oos.trades)
    print(f"IS:  n={base_is_n} pnl={base_is_pnl:+,.0f}")
    print(f"OOS: n={base_oos_n} pnl={base_oos_pnl:+,.0f}")

    # Full class breakdown
    _show_breakdown(r_is.trades, "IS")
    _show_breakdown(r_oos.trades, "OOS")

    # Count morning trendlines
    mt_is  = [t for t in r_is.trades  if _is_morning_tl(t)]
    mt_oos = [t for t in r_oos.trades if _is_morning_tl(t)]
    print(f"\n  Morning trendline IS:  n={len(mt_is)} pnl={sum(t.dollar_pnl for t in mt_is):+,.0f} avg={sum(t.dollar_pnl for t in mt_is)/max(1,len(mt_is)):+,.0f}")
    print(f"  Morning trendline OOS: n={len(mt_oos)} pnl={sum(t.dollar_pnl for t in mt_oos):+,.0f} avg={sum(t.dollar_pnl for t in mt_oos)/max(1,len(mt_oos)):+,.0f}")

    # Gate candidates
    results = []

    # Gate 1: Block ALL morning trendlines
    r = _autorate(spy_df, vix_df,
                  gate_fn=lambda t: not _is_morning_tl(t),
                  gate_label="block all morning trendlines",
                  base_is_n=base_is_n, base_is_pnl=base_is_pnl,
                  base_oos_n=base_oos_n, base_oos_pnl=base_oos_pnl)
    results.append(r)

    # Gate 2: Block morning tl_pure only (keep tl+ribbon_flip and tl+lvl_rej)
    def _is_morning_tl_pure(t):
        if not _is_morning_tl(t):
            return False
        return _classify(t) == "tl_pure"

    r = _autorate(spy_df, vix_df,
                  gate_fn=lambda t: not _is_morning_tl_pure(t),
                  gate_label="block morning tl_pure only (keep tl+rf/tl+rej)",
                  base_is_n=base_is_n, base_is_pnl=base_is_pnl,
                  base_oos_n=base_oos_n, base_oos_pnl=base_oos_pnl)
    results.append(r)

    # Gate 3: Block morning trendline entries before 10:00 ET (early chop)
    def _is_early_morning_tl(t):
        if not _is_morning_tl(t):
            return False
        et = t.entry_time_et
        if getattr(et, "tzinfo", None):
            et = et.replace(tzinfo=None)
        return et.hour < 10

    r = _autorate(spy_df, vix_df,
                  gate_fn=lambda t: not _is_early_morning_tl(t),
                  gate_label="block morning trendlines 09:35-09:59 ET only",
                  base_is_n=base_is_n, base_is_pnl=base_is_pnl,
                  base_oos_n=base_oos_n, base_oos_pnl=base_oos_pnl)
    results.append(r)

    # Save output
    out = {
        "study": "Safe morning trendline audit",
        "date": "2026-06-17",
        "baseline": {
            "is_n": base_is_n, "is_pnl": round(base_is_pnl, 2),
            "oos_n": base_oos_n, "oos_pnl": round(base_oos_pnl, 2),
        },
        "morning_tl_is": _stats(mt_is),
        "morning_tl_oos": _stats(mt_oos),
        "gates": results,
    }
    out_path = ROOT / "analysis" / "recommendations" / "safe_morning_tl_audit.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nSaved: {out_path}")

    print("\n\n=== SUMMARY ===")
    for r in results:
        v = r.get("verdict", "?")
        wf = r.get("WF", 0.0)
        print(f"  {r['gate'][:50]:50s} IS={r['IS_delta']:+,.0f} OOS={r['OOS_delta']:+,.0f} WF={wf:.3f} -> {v}")
