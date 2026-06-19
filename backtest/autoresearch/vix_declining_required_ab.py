"""
A/B test: vix_declining_required_bear=True on post-Rank35 Safe baseline.

Prior test (batch 9, pre-Rank34): IS +$3,843 improvement but OOS_delta=0
(all 15 OOS trades already in declining-VIX regime). That used IS n=244 baseline.

Current baseline is IS n=128 (post block_elite_bull + vix_bull_max=18.0).
Re-testing to get correct deltas + per-anchor-day analysis + sub-window stability.

Hypothesis: vix_declining_required_bear=True blocks entries on VIX-rising days
(tariff shock escalation) which are net losers. J anchor days (4/29, 5/01, 5/04)
are declining-VIX entries and should be preserved.
"""
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backtest"))

import pandas as pd
from lib.orchestrator import run_backtest

MASTER_SPY = ROOT / "backtest" / "data" / "spy_5m_2025-01-01_2026-06-16.csv"
MASTER_VIX = ROOT / "backtest" / "data" / "vix_5m_2025-01-01_2026-06-16.csv"

IS_START  = dt.date(2025, 1, 2)
IS_END    = dt.date(2026, 5, 7)
OOS_START = dt.date(2026, 5, 8)
OOS_END   = dt.date(2026, 6, 16)

J_ANCHOR_DATES = {
    dt.date(2026, 4, 29): ("4/29 WINNER", +342),
    dt.date(2026, 5, 1):  ("5/01 WINNER", +470),
    dt.date(2026, 5, 4):  ("5/04 WINNER", +730),
    dt.date(2026, 5, 5):  ("5/05 LOSER",  -260),
    dt.date(2026, 5, 6):  ("5/06 LOSER",  -300),
    dt.date(2026, 5, 7):  ("5/07 LOSER",  -165),
}

# Post-Rank35 Safe baseline (block_elite_bull + vix_bull_max=18.0)
BASE_KWARGS = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=True,
    premium_stop_pct_bear=-0.10,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.50,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.30,
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
    params_overrides={"vix_bull_max": 18.0},
)

GATE_KWARGS = dict(**BASE_KWARGS)
GATE_KWARGS["params_overrides"] = {"vix_bull_max": 18.0, "vix_declining_required_bear": True}

IS_SUBWINDOWS = [
    ("W1_2025H1", dt.date(2025, 1, 2),  dt.date(2025, 6, 30)),
    ("W2_2025H2", dt.date(2025, 7, 1),  dt.date(2025, 12, 31)),
    ("W3_Q12026", dt.date(2026, 1, 1),  dt.date(2026, 3, 31)),
    ("W4_Apr26",  dt.date(2026, 4, 1),  dt.date(2026, 5, 7)),
]
OOS_SUBWINDOWS = [
    ("OOS_W1", dt.date(2026, 5, 8),  dt.date(2026, 5, 22)),
    ("OOS_W2", dt.date(2026, 5, 23), dt.date(2026, 6, 16)),
]


def summarize_result(label, result):
    pnl = sum(t.dollar_pnl for t in result.trades)
    wins = sum(1 for t in result.trades if t.dollar_pnl > 0)
    wr = wins / max(1, len(result.trades)) * 100
    print(f"  {label}: n={len(result.trades)} WR={wr:.0f}% pnl={pnl:+,.0f}")
    return pnl


def per_anchor_analysis(label, base_r, gate_r):
    print(f"\n=== ANCHOR DAY ANALYSIS ({label}) ===")
    print(f"{'Date':>12} {'desc':>16} {'J_ref':>8} {'base_pnl':>10} {'gate_pnl':>10} {'delta':>8} {'verdict':>10}")
    print("-" * 80)
    # Index trades by entry date
    def by_date(trades):
        d = {}
        for t in trades:
            entry_dt = getattr(t, "entry_time_et", None)
            if entry_dt:
                day = entry_dt.date() if hasattr(entry_dt, "date") else entry_dt
                d.setdefault(day, []).append(t)
        return d

    base_by_date = by_date(base_r.trades)
    gate_by_date = by_date(gate_r.trades)

    anchor_ok = True
    for anchor_date, (desc, j_ref) in sorted(J_ANCHOR_DATES.items()):
        base_day_pnl = sum(t.dollar_pnl for t in base_by_date.get(anchor_date, []))
        gate_day_pnl = sum(t.dollar_pnl for t in gate_by_date.get(anchor_date, []))
        delta = gate_day_pnl - base_day_pnl
        if anchor_date <= IS_END:
            window = "IS"
            if desc.endswith("WINNER") and delta < -50:
                verdict = "REGRESSION"
                anchor_ok = False
            elif desc.endswith("LOSER") and delta < -10:
                verdict = "WORSE"
            elif delta >= 0:
                verdict = "OK"
            else:
                verdict = "MINOR_REGR"
        else:
            window = "OOS"
            verdict = "OK" if delta >= 0 else "MINOR_REGR"
        print(f"  {anchor_date!s:>12} ({window}) {desc:>16} {j_ref:>+8} {base_day_pnl:>+10.0f} {gate_day_pnl:>+10.0f} {delta:>+8.0f} {verdict:>10}")

    return anchor_ok


def run():
    print("Loading data...")
    spy = pd.read_csv(MASTER_SPY)
    vix = pd.read_csv(MASTER_VIX)
    print(f"SPY {len(spy)} rows, VIX {len(vix)} rows")

    print("\n=== BASELINE (post-Rank35) ===")
    is_base = run_backtest(spy, vix, start_date=IS_START, end_date=IS_END, **BASE_KWARGS)
    oos_base = run_backtest(spy, vix, start_date=OOS_START, end_date=OOS_END, **BASE_KWARGS)
    base_is_pnl = summarize_result("IS BASE", is_base)
    base_oos_pnl = summarize_result("OOS BASE", oos_base)

    print("\n=== GATE: vix_declining_required_bear=True ===")
    is_gate = run_backtest(spy, vix, start_date=IS_START, end_date=IS_END, **GATE_KWARGS)
    oos_gate = run_backtest(spy, vix, start_date=OOS_START, end_date=OOS_END, **GATE_KWARGS)
    gate_is_pnl = summarize_result("IS GATE", is_gate)
    gate_oos_pnl = summarize_result("OOS GATE", oos_gate)

    is_rm = len(is_base.trades) - len(is_gate.trades)
    oos_rm = len(oos_base.trades) - len(oos_gate.trades)
    is_dlt = gate_is_pnl - base_is_pnl
    oos_dlt = gate_oos_pnl - base_oos_pnl

    print(f"\nIS delta: {is_dlt:+,.0f} ({is_rm} trades removed)")
    print(f"OOS delta: {oos_dlt:+,.0f} ({oos_rm} trades removed)")

    n_is = len(is_base.trades)
    n_oos = len(oos_base.trades)

    if abs(is_dlt) < 1:
        print("WF: INERT (IS change < $1)")
        verdict = "INERT"
    elif is_dlt < 0:
        print("WF: IS_NEG - REJECT")
        verdict = "REJECT"
    elif oos_dlt < 0:
        print("WF: OOS_NEG - REJECT")
        verdict = "REJECT"
    elif oos_rm == 0:
        print(f"WF: INDETERMINATE (n_oos_blocked=0; IS improvement IS-only, cannot validate OOS)")
        verdict = "IS_ONLY"
    else:
        wf = (oos_dlt / n_oos) / (is_dlt / n_is)
        print(f"WF={wf:.3f} {'PASS' if wf >= 0.70 else 'FAIL'} (gate 0.70)")
        verdict = "PASS" if wf >= 0.70 else "FAIL"

    print(f"Overall verdict: {verdict}")

    # Which IS trades are blocked?
    print(f"\n=== BLOCKED IS TRADES (n={is_rm}) ===")
    base_set = {id(t): t for t in is_base.trades}
    gate_set = {id(t) for t in is_gate.trades}
    blocked_total_pnl = 0
    by_quarter = {"Q1_2025": [], "Q2_2025": [], "Q3_2025": [], "Q4_2025": [], "Q1_2026": [], "W4_Apr26": []}

    for t in is_base.trades:
        if id(t) not in gate_set:
            entry_dt = getattr(t, "entry_time_et", None)
            entry_date = entry_dt.date() if hasattr(entry_dt, "date") else None
            vix_now = getattr(t, "entry_vix", 0)
            pnl = t.dollar_pnl
            blocked_total_pnl += pnl
            if entry_date:
                if entry_date < dt.date(2025, 4, 1):
                    by_quarter["Q1_2025"].append(pnl)
                elif entry_date < dt.date(2025, 7, 1):
                    by_quarter["Q2_2025"].append(pnl)
                elif entry_date < dt.date(2025, 10, 1):
                    by_quarter["Q3_2025"].append(pnl)
                elif entry_date < dt.date(2026, 1, 1):
                    by_quarter["Q4_2025"].append(pnl)
                elif entry_date < dt.date(2026, 4, 1):
                    by_quarter["Q1_2026"].append(pnl)
                else:
                    by_quarter["W4_Apr26"].append(pnl)
            print(f"  {entry_dt} VIX={vix_now:.1f} pnl={pnl:+.0f}")
    print(f"Total blocked IS P&L: {blocked_total_pnl:+.0f} (removing this improves IS by {-blocked_total_pnl:+.0f})")

    print("\nBlocked IS by quarter:")
    for q, pnls in by_quarter.items():
        if pnls:
            print(f"  {q}: n={len(pnls)} pnl={sum(pnls):+.0f}")

    # Anchor day analysis
    anchor_ok = per_anchor_analysis("IS+OOS", is_base, is_gate)
    if anchor_ok:
        print("\nAnchor check: OK (no WINNER regression)")
    else:
        print("\nAnchor check: FAIL (WINNER regression detected)")

    # Sub-window IS stability
    print("\n=== IS SUB-WINDOW STABILITY ===")
    print(f"{'Window':>12} {'base_n':>7} {'base_pnl':>10} {'gate_n':>7} {'gate_pnl':>10} {'delta':>+8} {'rm':>4} {'verdict':>8}")
    print("-" * 80)
    hurt = 0
    for name, ws, we in IS_SUBWINDOWS:
        sw_base = run_backtest(spy, vix, start_date=ws, end_date=we, **BASE_KWARGS)
        sw_gate = run_backtest(spy, vix, start_date=ws, end_date=we, **GATE_KWARGS)
        base_p = sum(t.dollar_pnl for t in sw_base.trades)
        gate_p = sum(t.dollar_pnl for t in sw_gate.trades)
        delta = gate_p - base_p
        rm = len(sw_base.trades) - len(sw_gate.trades)
        v = "HELP" if delta >= 0 else "HURT"
        if delta < 0:
            hurt += 1
        print(f"{name:>12} {len(sw_base.trades):>7} {base_p:>+10.0f} {len(sw_gate.trades):>7} {gate_p:>+10.0f} {delta:>+8.0f} {rm:>4} {v:>8}")
    print(f"IS sub-windows HURT: {hurt}/4 (gate: <=1 MARGINAL, 0 STABLE)")

    # OOS sub-window
    print("\n=== OOS SUB-WINDOW ===")
    for name, ws, we in OOS_SUBWINDOWS:
        sw_base = run_backtest(spy, vix, start_date=ws, end_date=we, **BASE_KWARGS)
        sw_gate = run_backtest(spy, vix, start_date=ws, end_date=we, **GATE_KWARGS)
        base_p = sum(t.dollar_pnl for t in sw_base.trades)
        gate_p = sum(t.dollar_pnl for t in sw_gate.trades)
        delta = gate_p - base_p
        rm = len(sw_base.trades) - len(sw_gate.trades)
        print(f"  {name}: base_n={len(sw_base.trades)} base_pnl={base_p:+.0f} gate_n={len(sw_gate.trades)} gate_pnl={gate_p:+.0f} delta={delta:+.0f} rm={rm}")

    print(f"\nvix_declining_required_bear A/B complete. verdict={verdict}")


if __name__ == "__main__":
    run()
