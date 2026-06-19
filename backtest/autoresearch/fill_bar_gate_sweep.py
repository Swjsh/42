"""
REQUIRE_BEARISH_FILL_BAR GATE SWEEP (2026-06-17)

Prior analysis (entry_bar_pnl_split.py, older baseline n=85):
  Bearish fill bar: WR=41.1% avg=+$225 (n=56 IS)
  Bullish fill bar: WR=3.4%  avg=-$39  (n=29 IS)
  IS delta=+$1,124, OOS delta=+$424, WF_norm=1.908

NOTE: This is a LOOK-AHEAD gate. In backtest, bar N+1 direction is known.
In LIVE, this requires a one-bar confirmation delay (enter at N+2 open after
confirming N+1 closes bearish). Live implementation needs heartbeat.md change (Rule 9).

THIS SCRIPT: Validate on current production baselines:
  Safe: IS n=130 pnl=+16,174 | AGG: IS n=105 pnl=+11,335

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


def _pnl(trades):
    return sum(t.dollar_pnl for t in trades)


def _date(t):
    et = t.entry_time_et
    return (et.replace(tzinfo=None) if getattr(et, "tzinfo", None) else et).date()


def _run(spy_df, vix_df, start, end, base_kw, ovr, gate):
    kw = dict(base_kw)
    kw["require_bearish_fill_bar"] = gate
    return run_backtest(spy_df, vix_df, start_date=start, end_date=end,
                        params_overrides=dict(ovr), **kw)


def _anchor(base_trades, cand_trades):
    base_by = {_date(t): t.dollar_pnl for t in base_trades}
    cand_by = {_date(t): t.dollar_pnl for t in cand_trades}
    issues = []
    for d in J_WINNERS:
        b, c = base_by.get(d, 0), cand_by.get(d, 0)
        if c < b - 50:
            issues.append(f"  J_WINNER {d}: base={b:.0f} cand={c:.0f} REGRESSION")
    for d in J_LOSERS:
        b, c = base_by.get(d, 0), cand_by.get(d, 0)
        if c < b - 50:
            issues.append(f"  J_LOSER {d}: cand WORSE {c:.0f} vs base {b:.0f}")
    ok = not issues
    print(f"  ANCHOR: {'PASS' if ok else 'FAIL'}")
    for line in issues:
        print(line)
    return ok


def _sweep(spy_df, vix_df, label, base_kw, ovr, expected_is_n, expected_is_pnl):
    print(f"\n{'='*72}")
    print(f"  {label} FILL-BAR GATE SWEEP")
    print(f"{'='*72}")

    print("  Running baseline (gate=False)...")
    b_is = _run(spy_df, vix_df, IS_START, IS_END, base_kw, ovr, gate=False)
    b_oos = _run(spy_df, vix_df, OOS_START, OOS_END, base_kw, ovr, gate=False)
    b_is_pnl = _pnl(b_is.trades)
    b_oos_pnl = _pnl(b_oos.trades)
    print(f"  Baseline IS: n={len(b_is.trades)} pnl={b_is_pnl:+,.0f} (expect n={expected_is_n} pnl={expected_is_pnl:+,})")
    print(f"  Baseline OOS: n={len(b_oos.trades)} pnl={b_oos_pnl:+,.0f}")

    if len(b_is.trades) != expected_is_n:
        print(f"  WARNING: IS n mismatch — params may be wrong. Aborting.")
        return None

    print("\n  Running candidate (gate=True)...")
    c_is = _run(spy_df, vix_df, IS_START, IS_END, base_kw, ovr, gate=True)
    c_oos = _run(spy_df, vix_df, OOS_START, OOS_END, base_kw, ovr, gate=True)
    c_is_pnl = _pnl(c_is.trades)
    c_oos_pnl = _pnl(c_oos.trades)
    print(f"  Candidate IS: n={len(c_is.trades)} pnl={c_is_pnl:+,.0f}")
    print(f"  Candidate OOS: n={len(c_oos.trades)} pnl={c_oos_pnl:+,.0f}")

    n_is = len(b_is.trades)
    n_oos = len(b_oos.trades)
    is_delta = c_is_pnl - b_is_pnl
    oos_delta = c_oos_pnl - b_oos_pnl
    wf_norm = (oos_delta / n_oos) / (is_delta / n_is) if is_delta != 0 else 0.0
    oos_positive = c_oos_pnl > 0

    print(f"\n  IS delta:  {is_delta:+,.0f}")
    print(f"  OOS delta: {oos_delta:+,.0f}")
    print(f"  WF_norm:   {wf_norm:.3f}")
    print(f"  OOS_positive: {oos_positive} ({c_oos_pnl:+,.0f})")

    print(f"\n  IS sub-window breakdown:")
    sw_hurt = 0
    for sw_label, s, e in IS_SUBWINDOWS:
        b = _pnl(_run(spy_df, vix_df, s, e, base_kw, ovr, gate=False).trades)
        c = _pnl(_run(spy_df, vix_df, s, e, base_kw, ovr, gate=True).trades)
        delta = c - b
        hurt = delta < -500
        if hurt:
            sw_hurt += 1
        tag = " <-- HURT" if hurt else ""
        print(f"    {sw_label}: base={b:+,.0f} cand={c:+,.0f} delta={delta:+,.0f}{tag}")

    anchor_ok = _anchor(b_is.trades, c_is.trades)

    # L155 guard: IS_delta must be > 0 — WF formula is invalid when IS is hurt
    if is_delta <= 0:
        print(f"\n  IS_delta <= 0 ({is_delta:+,.0f}): gate hurts or has no IS impact → REJECT")
        return {
            "label": label, "baseline": {"IS_n": n_is, "IS_pnl": round(b_is_pnl, 2), "OOS_n": n_oos, "OOS_pnl": round(b_oos_pnl, 2)},
            "candidate": {"IS_n": len(c_is.trades), "IS_pnl": round(c_is_pnl, 2), "OOS_n": len(c_oos.trades), "OOS_pnl": round(c_oos_pnl, 2)},
            "IS_delta": round(is_delta, 2), "OOS_delta": round(oos_delta, 2), "WF_norm": 0.0,
            "OOS_positive": oos_positive, "SW_hurt": sw_hurt, "anchor_OK": anchor_ok,
            "verdict": "REJECT (IS_delta<=0)",
        }
    print(f"\n  === AUTORATE GATES ===")
    g_oos = "PASS" if oos_positive else "FAIL"
    g_wf = "PASS" if wf_norm >= 0.70 else "FAIL"
    g_sw = "PASS" if sw_hurt <= 1 else "FAIL"
    g_anch = "PASS" if anchor_ok else "FAIL"
    print(f"  OOS_positive: {g_oos}")
    print(f"  WF_norm >= 0.70 ({wf_norm:.3f}): {g_wf}")
    print(f"  SW_hurt <= 1 ({sw_hurt}): {g_sw}")
    print(f"  ANCHOR: {g_anch}")

    all_pass = all(g == "PASS" for g in [g_oos, g_wf, g_sw, g_anch])
    verdict = "AUTO-RATIFY" if all_pass else "REJECT"
    print(f"\n  VERDICT: {verdict}")

    if all_pass:
        print("  NOTE: LOOK-AHEAD gate. Ratifying params.json key for backtest tracking.")
        print("  Live implementation requires heartbeat.md one-bar delay (Rule 9).")

    return {
        "label": label,
        "baseline": {"IS_n": n_is, "IS_pnl": round(b_is_pnl, 2), "OOS_n": n_oos, "OOS_pnl": round(b_oos_pnl, 2)},
        "candidate": {"IS_n": len(c_is.trades), "IS_pnl": round(c_is_pnl, 2), "OOS_n": len(c_oos.trades), "OOS_pnl": round(c_oos_pnl, 2)},
        "IS_delta": round(is_delta, 2),
        "OOS_delta": round(oos_delta, 2),
        "WF_norm": round(wf_norm, 3),
        "OOS_positive": oos_positive,
        "SW_hurt": sw_hurt,
        "anchor_OK": anchor_ok,
        "verdict": verdict,
        "note": "LOOK-AHEAD gate. Live implementation requires heartbeat.md one-bar confirmation delay (Rule 9).",
    }


if __name__ == "__main__":
    print("Loading data...")
    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    safe_result = _sweep(spy_df, vix_df, "SAFE", SAFE_KW, SAFE_OVR,
                         expected_is_n=130, expected_is_pnl=16174)
    agg_result = _sweep(spy_df, vix_df, "AGG", AGG_KW, AGG_OVR,
                        expected_is_n=105, expected_is_pnl=11335)

    out = {
        "study": "require_bearish_fill_bar gate sweep",
        "date": "2026-06-17",
        "safe": safe_result,
        "agg": agg_result,
    }
    out_path = ROOT / "analysis" / "recommendations" / "fill-bar-gate-sweep.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nSaved: {out_path}")
