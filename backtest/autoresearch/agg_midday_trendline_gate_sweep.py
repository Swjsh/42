"""
AGG MIDDAY_TRENDLINE_GATE SWEEP (2026-06-17)

Safe account has midday_trendline_gate=True (v15.3) blocking 1-trig trendline 11:30-14:00.
AGG does NOT have this gate (midday_trendline_gate=False in production).

AGG IS trendline n=162 avg=$12 (near breakeven), OOS avg=-$10 (slightly negative).
Safe IS showed midday gate removed the IS midday losers (+28.3/c per-trade OOS WF=4.29).

HYPOTHESIS: AGG midday_trendline_gate=True should similarly remove the worst trendline
trades and improve OOS per-trade edge.

GATES: OOS_positive AND WF>=0.70 AND SW_hurt<=1 AND anchor_no_regression.

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

AGG_BASE_KW = dict(
    use_real_fills=True,
    midday_trendline_gate=False,     # baseline: gate OFF
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


def _run(spy_df, vix_df, start, end, gate: bool):
    kw = dict(AGG_BASE_KW)
    kw["midday_trendline_gate"] = gate
    return run_backtest(spy_df, vix_df, start_date=start, end_date=end,
                        params_overrides=dict(AGG_OVR), **kw)


def _pnl(trades): return sum(t.dollar_pnl for t in trades)
def _date(t):
    et = t.entry_time_et
    return (et.replace(tzinfo=None) if getattr(et, "tzinfo", None) else et).date()


def _j_anchor_check(base_trades, cand_trades, label):
    base_by_date = {_date(t): t.dollar_pnl for t in base_trades}
    cand_by_date = {_date(t): t.dollar_pnl for t in cand_trades}
    issues = []
    for d in J_WINNERS:
        base_p = base_by_date.get(d, 0)
        cand_p = cand_by_date.get(d, 0)
        if cand_p < base_p - 50:
            issues.append(f"  J_WINNER {d}: base=${base_p:.0f} cand=${cand_p:.0f} (REGRESSION)")
    for d in J_LOSERS:
        base_p = base_by_date.get(d, 0)
        cand_p = cand_by_date.get(d, 0)
        if cand_p < base_p - 50:
            issues.append(f"  J_LOSER  {d}: cand WORSE ${cand_p:.0f} vs base ${base_p:.0f}")
    if issues:
        print(f"  ANCHOR {label}: FAIL\n" + "\n".join(issues))
        return False
    print(f"  ANCHOR {label}: PASS")
    return True


if __name__ == "__main__":
    print("Loading data...")
    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    print("Running AGG baseline (gate=False, verify IS n=218 pnl=+10,019)...")
    base_is = _run(spy_df, vix_df, IS_START, IS_END, gate=False)
    base_oos = _run(spy_df, vix_df, OOS_START, OOS_END, gate=False)
    b_is_pnl = _pnl(base_is.trades)
    b_oos_pnl = _pnl(base_oos.trades)
    print(f"  Baseline IS: n={len(base_is.trades)} pnl={b_is_pnl:+,.0f}")
    print(f"  Baseline OOS: n={len(base_oos.trades)} pnl={b_oos_pnl:+,.0f}")
    if len(base_is.trades) != 218:
        print(f"  WARNING: expected IS n=218, got {len(base_is.trades)}")

    print("\nRunning AGG candidate (gate=True, midday_trendline_gate enabled)...")
    cand_is = _run(spy_df, vix_df, IS_START, IS_END, gate=True)
    cand_oos = _run(spy_df, vix_df, OOS_START, OOS_END, gate=True)
    c_is_pnl = _pnl(cand_is.trades)
    c_oos_pnl = _pnl(cand_oos.trades)
    print(f"  Candidate IS: n={len(cand_is.trades)} pnl={c_is_pnl:+,.0f}")
    print(f"  Candidate OOS: n={len(cand_oos.trades)} pnl={c_oos_pnl:+,.0f}")

    # Deltas
    is_delta = c_is_pnl - b_is_pnl
    oos_delta = c_oos_pnl - b_oos_pnl
    n_is = len(base_is.trades)
    n_oos = len(base_oos.trades)
    wf_norm = (oos_delta / n_oos) / (is_delta / n_is) if is_delta != 0 else 0.0
    oos_positive = c_oos_pnl > 0

    print(f"\n  IS delta:  {is_delta:+,.0f}")
    print(f"  OOS delta: {oos_delta:+,.0f}")
    print(f"  WF_norm:   {wf_norm:.3f}")
    print(f"  OOS_positive: {oos_positive}")

    # Sub-window hurt check
    sw_hurt = 0
    print(f"\n  IS sub-window breakdown:")
    for label, s, e in IS_SUBWINDOWS:
        b = _pnl(_run(spy_df, vix_df, s, e, gate=False).trades)
        c = _pnl(_run(spy_df, vix_df, s, e, gate=True).trades)
        delta = c - b
        hurt = delta < -500
        if hurt:
            sw_hurt += 1
        tag = " <-- HURT" if hurt else ""
        print(f"    {label}: base={b:+,.0f} cand={c:+,.0f} delta={delta:+,.0f}{tag}")

    # Anchor check
    anchor_ok = _j_anchor_check(base_is.trades, cand_is.trades, "IS J anchors")

    # Gate evaluation
    print(f"\n  === AUTORATE GATES ===")
    gate_oos_pos = "PASS" if oos_positive else "FAIL"
    gate_wf = "PASS" if wf_norm >= 0.70 else "FAIL"
    gate_sw = "PASS" if sw_hurt <= 1 else "FAIL"
    gate_anchor = "PASS" if anchor_ok else "FAIL"
    print(f"  OOS_positive ({c_oos_pnl:+,.0f}): {gate_oos_pos}")
    print(f"  WF_norm >= 0.70 ({wf_norm:.3f}): {gate_wf}")
    print(f"  SW_hurt <= 1 ({sw_hurt} hurt): {gate_sw}")
    print(f"  ANCHOR: {gate_anchor}")

    all_pass = all(g == "PASS" for g in [gate_oos_pos, gate_wf, gate_sw, gate_anchor])
    verdict = "AUTO-RATIFY" if all_pass else "REJECT"
    print(f"\n  VERDICT: {verdict}")

    if all_pass:
        print("\n  ** RATIFICATION: midday_trendline_gate=True -> AGG params.json (automation/state/aggressive/params.json) **")
        print("  Action: update block, no Rule 9 required for params.json (not heartbeat.md)")

    # Save scorecard
    out = {
        "study": "AGG midday_trendline_gate sweep",
        "date": "2026-06-17",
        "candidate": {"midday_trendline_gate": True},
        "baseline": {"IS_n": len(base_is.trades), "IS_pnl": round(b_is_pnl, 2), "OOS_n": len(base_oos.trades), "OOS_pnl": round(b_oos_pnl, 2)},
        "candidate_result": {"IS_n": len(cand_is.trades), "IS_pnl": round(c_is_pnl, 2), "OOS_n": len(cand_oos.trades), "OOS_pnl": round(c_oos_pnl, 2)},
        "IS_delta": round(is_delta, 2),
        "OOS_delta": round(oos_delta, 2),
        "WF_norm": round(wf_norm, 3),
        "OOS_positive": oos_positive,
        "SW_hurt": sw_hurt,
        "anchor_OK": anchor_ok,
        "verdict": verdict,
    }
    out_path = ROOT / "analysis" / "recommendations" / "agg-midday-trendline-gate.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nSaved: {out_path}")
