"""
AGG EXIT TYPE AUDIT (updated 2026-06-17 post-ENFORCED-5)

L148 hypothesis: AGG runner almost never hits 5.0x target;
exits via TP1_THEN_RUNNER_RIBBON or TP1_THEN_RUNNER_TIME.

This script quantifies the exit type distribution for AGG IS/OOS
and answers: what fraction of trades exit via each reason?

Cook queue: 6b403baf
Security: read-only, no Alpaca calls, no production writes.
"""
from __future__ import annotations
import sys, json, datetime as dt, pathlib, collections
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd
from backtest.lib.orchestrator import run_backtest
from backtest.lib.simulator_real import ExitReason

DATA_DIR = ROOT / "backtest" / "data"
SPY_FILE = DATA_DIR / "spy_5m_2025-01-01_2026-06-16.csv"
VIX_FILE = DATA_DIR / "vix_5m_2025-01-01_2026-06-16.csv"

IS_START  = dt.date(2025, 1, 2)
IS_END    = dt.date(2026, 5, 7)
OOS_START = dt.date(2026, 5, 8)
OOS_END   = dt.date(2026, 6, 16)

# AGG production params — post ENFORCED-2/3/5 (correct as of 2026-06-17)
# Expected baseline: IS n=109 pnl=+$19,080 | OOS n=18 pnl=+$3,833
AGG_KW = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
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
    block_conf_lvl_rec_afternoon=True,           # ENFORCED-2
    block_conf_lvl_rej_midday_afternoon=True,    # ENFORCED-3
    require_bearish_fill_bar=True,               # ENFORCED-5 (J-RATIFIED 2026-06-17)
)
AGG_OVR = {"vix_bear_threshold": 15.0, "vix_bull_max": 30.0, "strike_offset_itm": 2}


def _run(spy_df, vix_df, start, end):
    return run_backtest(spy_df, vix_df, start_date=start, end_date=end,
                        params_overrides=dict(AGG_OVR), **AGG_KW)


def _audit(trades, label):
    n = len(trades)
    if n == 0:
        print(f"\n{label}: no trades")
        return {}

    total_pnl = sum(t.dollar_pnl for t in trades)
    print(f"\n{'='*70}")
    print(f"  {label}: n={n}  total_pnl=${total_pnl:,.0f}  avg=${total_pnl/n:.0f}/trade")
    print(f"{'='*70}")

    # Exit reason distribution
    by_reason = collections.Counter()
    pnl_by_reason = collections.defaultdict(list)
    for t in trades:
        r = t.exit_reason.value if t.exit_reason else "UNKNOWN"
        by_reason[r] += 1
        pnl_by_reason[r].append(t.dollar_pnl)

    print(f"\n  EXIT REASON DISTRIBUTION:")
    print(f"  {'Reason':40s}  {'n':>5}  {'%':>6}  {'Total PnL':>10}  {'Avg':>8}")
    print(f"  {'-'*75}")
    for reason, cnt in sorted(by_reason.items(), key=lambda x: -x[1]):
        pct = cnt / n * 100
        pnls = pnl_by_reason[reason]
        avg = sum(pnls) / len(pnls)
        print(f"  {reason:40s}  {cnt:>5}  {pct:>5.1f}%  {sum(pnls):>10,.0f}  {avg:>8.0f}")

    # Is runner_target_hit_rate as low as L148 claims?
    target_hits = sum(1 for r in by_reason if "RUNNER_TARGET" in r)
    print(f"\n  RUNNER TARGET HIT RATE: {target_hits}/{n} = {target_hits/n*100:.1f}%")
    runner_exits = sum(by_reason.get(r, 0) for r in
                       ["TP1_THEN_RUNNER_TARGET", "TP1_THEN_RUNNER_RIBBON",
                        "TP1_THEN_RUNNER_TIME", "TP1_THEN_RUNNER_BE_STOP"])
    stops = sum(by_reason.get(r, 0) for r in
                ["EXIT_ALL_PREMIUM_STOP", "EXIT_ALL_LEVEL_STOP"])
    time_stops = by_reason.get("EXIT_ALL_TIME_STOP", 0)
    print(f"  STOP-LOSS exits:        {stops}/{n} = {stops/n*100:.1f}%")
    print(f"  TIME-STOP exits (full): {time_stops}/{n} = {time_stops/n*100:.1f}%")
    print(f"  TP1 then runner:        {runner_exits}/{n} = {runner_exits/n*100:.1f}%")

    # PnL by exit group
    groups = {
        "runner_target_hit": [t for t in trades if t.exit_reason and "RUNNER_TARGET" in t.exit_reason.value],
        "runner_ribbon": [t for t in trades if t.exit_reason and t.exit_reason.value == "TP1_THEN_RUNNER_RIBBON"],
        "runner_time": [t for t in trades if t.exit_reason and t.exit_reason.value == "TP1_THEN_RUNNER_TIME"],
        "runner_be_stop": [t for t in trades if t.exit_reason and t.exit_reason.value == "TP1_THEN_RUNNER_BE_STOP"],
        "full_stop": [t for t in trades if t.exit_reason and t.exit_reason.value in ("EXIT_ALL_PREMIUM_STOP", "EXIT_ALL_LEVEL_STOP")],
        "full_time": [t for t in trades if t.exit_reason and t.exit_reason.value == "EXIT_ALL_TIME_STOP"],
    }
    print(f"\n  BY EXIT GROUP:")
    for g, gtrades in groups.items():
        if gtrades:
            gpnl = sum(t.dollar_pnl for t in gtrades)
            print(f"  {g:20s}  n={len(gtrades):3d}  pnl={gpnl:>8,.0f}  avg={gpnl/len(gtrades):>7.0f}")

    result = {}
    for reason, pnls in pnl_by_reason.items():
        result[reason] = {
            "n": len(pnls),
            "pct": round(len(pnls) / n * 100, 1),
            "total_pnl": round(sum(pnls), 2),
            "avg_pnl": round(sum(pnls) / len(pnls), 2),
        }
    return result


if __name__ == "__main__":
    print("Loading data...")
    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    print("Running AGG IS backtest...")
    r_is = _run(spy_df, vix_df, IS_START, IS_END)
    is_pnl = sum(t.dollar_pnl for t in r_is.trades)
    print(f"IS: n={len(r_is.trades)} pnl={is_pnl:+,.0f}")

    print("Running AGG OOS backtest...")
    r_oos = _run(spy_df, vix_df, OOS_START, OOS_END)
    oos_pnl = sum(t.dollar_pnl for t in r_oos.trades)
    print(f"OOS: n={len(r_oos.trades)} pnl={oos_pnl:+,.0f}")

    is_result = _audit(r_is.trades, "AGG IS (2025-01-02 to 2026-05-07)")
    oos_result = _audit(r_oos.trades, "AGG OOS (2026-05-08 to 2026-06-16)")

    # Check REAL fills flag
    real_fills_count = sum(1 for t in r_is.trades if "::BS_FALLBACK" not in (t.setup or ""))
    print(f"\n  [INFO] IS trades using real-fills path: {real_fills_count}/{len(r_is.trades)}")

    # Save
    out = {
        "study": "AGG exit type audit",
        "date": "2026-06-17",
        "is_n": len(r_is.trades),
        "is_pnl": round(is_pnl, 2),
        "oos_n": len(r_oos.trades),
        "oos_pnl": round(oos_pnl, 2),
        "is_exit_distribution": is_result,
        "oos_exit_distribution": oos_result,
        "l148_runner_target_hit_rate_is": round(
            sum(1 for t in r_is.trades if t.exit_reason and "RUNNER_TARGET" in t.exit_reason.value)
            / len(r_is.trades) * 100, 1
        ) if r_is.trades else 0,
        "l148_runner_target_hit_rate_oos": round(
            sum(1 for t in r_oos.trades if t.exit_reason and "RUNNER_TARGET" in t.exit_reason.value)
            / len(r_oos.trades) * 100, 1
        ) if r_oos.trades else 0,
    }
    out_path = ROOT / "analysis" / "recommendations" / "agg_exit_type_audit.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nSaved: {out_path}")
