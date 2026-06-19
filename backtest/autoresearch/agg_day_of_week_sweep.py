"""
AGG DAY-OF-WEEK SWEEP (2026-06-17)

Mirrors safe_day_of_week_sweep.py for the AGG account.
Hypothesis: Day-of-week effects are regime-stable (bypass C22).

Tests:
  1. Block Friday entries
  2. Block Monday entries
  3. Block Monday + Friday
  4. Block Friday afternoon only

Security: read-only. No Alpaca calls. Free-tier only.
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

J_WINNERS = {dt.date(2026, 4, 29), dt.date(2026, 5, 1), dt.date(2026, 5, 4)}
J_LOSERS  = {dt.date(2026, 5, 5), dt.date(2026, 5, 6)}

# AGG production params (with all ratified gates)
AGG_KW = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=True,
    premium_stop_pct_bear=-0.07,
    tp1_premium_pct=0.75,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=5.0,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.50,
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
    block_conf_lvl_rec_afternoon=True,
    block_conf_lvl_rej_midday_afternoon=True,
)
AGG_OVR = {"vix_bull_max": 30.0, "vix_bear_threshold": 15.0, "strike_offset_itm": 2}


def _run(spy_df, vix_df, start, end):
    return run_backtest(spy_df, vix_df, start_date=start, end_date=end,
                        params_overrides=dict(AGG_OVR), **AGG_KW)


def _entry_dt(t):
    et = t.entry_time_et
    return (et.replace(tzinfo=None) if getattr(et, "tzinfo", None) else et)


def _weekday(t):
    return _entry_dt(t).weekday()

def _is_friday(t):     return _weekday(t) == 4
def _is_monday(t):     return _weekday(t) == 0
def _is_mon_fri(t):    return _weekday(t) in (0, 4)
def _is_fri_aft(t):
    if _weekday(t) != 4: return False
    et = _entry_dt(t)
    return et.hour * 60 + et.minute >= 14 * 60

def _date(t):
    return _entry_dt(t).date()


def _stats(trades):
    if not trades:
        return {"n": 0, "total": 0.0, "avg": 0.0}
    pnl = sum(t.dollar_pnl for t in trades)
    return {"n": len(trades), "total": round(pnl, 1), "avg": round(pnl / len(trades), 1)}


def _show_dow(trades, label):
    print(f"\n  {label} -- BY DAY OF WEEK:")
    names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    for i, name in enumerate(names):
        ts = [t for t in trades if _weekday(t) == i]
        s = _stats(ts)
        if s["n"] > 0:
            print(f"  {name:12s} n={s['n']:>3} pnl={s['total']:>8,.0f} avg={s['avg']:>8,.0f}")


def _autorate(spy_df, vix_df, gate_fn, label, base_is_n, base_is_pnl, base_oos_n, base_oos_pnl):
    print(f"\n  {'='*65}")
    print(f"  GATE: {label}")
    r_is  = _run(spy_df, vix_df, IS_START, IS_END)
    r_oos = _run(spy_df, vix_df, OOS_START, OOS_END)

    is_cand  = [t for t in r_is.trades  if gate_fn(t)]
    oos_cand = [t for t in r_oos.trades if gate_fn(t)]
    is_pnl   = sum(t.dollar_pnl for t in is_cand)
    oos_pnl  = sum(t.dollar_pnl for t in oos_cand)
    is_delta  = is_pnl  - base_is_pnl
    oos_delta = oos_pnl - base_oos_pnl

    dropped_is  = [t for t in r_is.trades  if not gate_fn(t)]
    dropped_oos = [t for t in r_oos.trades if not gate_fn(t)]

    print(f"  IS:  base n={base_is_n} pnl={base_is_pnl:+,.0f} | cand n={len(is_cand)} pnl={is_pnl:+,.0f} delta={is_delta:+,.0f}")
    print(f"  OOS: base n={base_oos_n} pnl={base_oos_pnl:+,.0f} | cand n={len(oos_cand)} pnl={oos_pnl:+,.0f} delta={oos_delta:+,.0f}")
    print(f"  Dropped IS n={len(dropped_is)} pnl={sum(t.dollar_pnl for t in dropped_is):+,.0f}")
    print(f"  Dropped OOS n={len(dropped_oos)} pnl={sum(t.dollar_pnl for t in dropped_oos):+,.0f}")

    if is_delta <= 0:
        print(f"  IS_delta={is_delta:+,.0f} <= 0: REJECT (L155)")
        return {"gate": label, "IS_delta": round(is_delta, 2), "OOS_delta": round(oos_delta, 2),
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

    return {"gate": label, "IS_delta": round(is_delta, 2), "OOS_delta": round(oos_delta, 2),
            "WF": round(wf_norm, 3), "OOS_positive": oos_pos, "SW_hurt": sw_hurt,
            "anchor_OK": anchor_ok, "verdict": verdict}


if __name__ == "__main__":
    print("Loading data...")
    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    print("\nRunning AGG baseline (all 5 production gates)...")
    r_is  = _run(spy_df, vix_df, IS_START, IS_END)
    r_oos = _run(spy_df, vix_df, OOS_START, OOS_END)
    base_is_pnl  = sum(t.dollar_pnl for t in r_is.trades)
    base_oos_pnl = sum(t.dollar_pnl for t in r_oos.trades)
    base_is_n    = len(r_is.trades)
    base_oos_n   = len(r_oos.trades)
    print(f"IS:  n={base_is_n} pnl={base_is_pnl:+,.0f}")
    print(f"OOS: n={base_oos_n} pnl={base_oos_pnl:+,.0f}")

    _show_dow(r_is.trades, "IS")
    _show_dow(r_oos.trades, "OOS")

    gates = [
        ("block Friday entries",          lambda t: not _is_friday(t)),
        ("block Monday entries",          lambda t: not _is_monday(t)),
        ("block Monday + Friday",         lambda t: not _is_mon_fri(t)),
        ("block Friday afternoon only",   lambda t: not _is_fri_aft(t)),
    ]

    results = []
    for label, fn in gates:
        r = _autorate(spy_df, vix_df, fn, label, base_is_n, base_is_pnl, base_oos_n, base_oos_pnl)
        results.append(r)

    out = {"study": "AGG day-of-week sweep", "date": "2026-06-17",
           "baseline": {"is_n": base_is_n, "is_pnl": round(base_is_pnl, 2),
                        "oos_n": base_oos_n, "oos_pnl": round(base_oos_pnl, 2)},
           "gates": results}
    out_path = ROOT / "analysis" / "recommendations" / "agg_dow_sweep.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nSaved: {out_path}")

    print("\n\n=== SUMMARY ===")
    for r in results:
        wf = r.get("WF", 0.0)
        print(f"  {r['gate'][:40]:40s} IS={r['IS_delta']:+,.0f} OOS={r['OOS_delta']:+,.0f} WF={wf:.3f} -> {r['verdict']}")
