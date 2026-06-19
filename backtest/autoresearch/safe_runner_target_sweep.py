"""
SAFE_RUNNER_TARGET_SWEEP

Safe production: runner_target_premium_pct=2.5x.
Aggressive: 5.0x — confirmed optimal because OOS runners never exceed 2.5x.

Question for Safe: at 2.5x target, are Safe's OOS runners also exiting below target?
If Safe runners exit at ~1.0-1.5x (ribbon flip / BE stop), lowering to 1.5x or 2.0x
would match reality and not change anything. If they sometimes reach 2.5x, we need
to know the distribution.

Sweep: 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5 (baseline), 3.0

Gates: OOS_positive AND WF >= 0.70 AND SW_hurt <= 1 AND anchor_OK

Security: read-only. No Alpaca calls. Free-tier only.
"""
from __future__ import annotations
import sys
import json
import datetime as dt
import pathlib

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

J_WINNERS = {dt.date(2026, 4, 29), dt.date(2026, 5, 1), dt.date(2026, 5, 4)}
J_LOSERS  = {dt.date(2026, 5, 5), dt.date(2026, 5, 6)}

IS_SUBWINDOWS = [
    ("W1 Jan-Jun 2025", dt.date(2025, 1, 2),  dt.date(2025, 6, 30)),
    ("W2 Jul-Dec 2025", dt.date(2025, 7, 1),  dt.date(2025, 12, 31)),
    ("W3 Jan-Mar 2026", dt.date(2026, 1, 2),  dt.date(2026, 3, 31)),
    ("W4 Apr-May 2026", dt.date(2026, 4, 1),  dt.date(2026, 5, 7)),
]

SAFE_BASE_KW = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=True,
    premium_stop_pct_bear=-0.10,
    tp1_premium_pct=0.50,                 # post-Rank36 production
    tp1_qty_fraction=0.667,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.30,
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
)
SAFE_OVR = {"vix_bull_max": 18.0}

BASELINE_TARGET = 2.5
TARGETS = [1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 3.0]


def _run(spy_df, vix_df, start, end, target):
    return run_backtest(
        spy_df, vix_df,
        start_date=start, end_date=end,
        runner_target_premium_pct=target,
        params_overrides=dict(SAFE_OVR),
        **SAFE_BASE_KW,
    )


def _pnl(trades): return sum(t.dollar_pnl for t in trades)


def _date(t):
    et = t.entry_time_et
    d = et.replace(tzinfo=None) if getattr(et, "tzinfo", None) else et
    return d.date()


def _by_date(trades):
    bd = {}
    for t in trades:
        d = _date(t)
        bd[d] = bd.get(d, 0.0) + t.dollar_pnl
    return bd


def _anchor_ok(cand_bd, base_bd):
    for d in J_WINNERS:
        bp = base_bd.get(d, 0.0)
        cp = cand_bd.get(d, 0.0)
        if bp > 0 and cp < bp * 0.90:
            return False
    return True


if __name__ == "__main__":
    print("=" * 100)
    print("SAFE RUNNER_TARGET_PREMIUM_PCT SWEEP (baseline=2.5x, post-Rank36)")
    print("=" * 100)

    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    # Baseline
    print(f"\n[Baseline at runner_target={BASELINE_TARGET}x]...")
    base_is  = _run(spy_df, vix_df, IS_START,  IS_END,  BASELINE_TARGET)
    base_oos = _run(spy_df, vix_df, OOS_START, OOS_END, BASELINE_TARGET)
    base_is_pnl  = _pnl(base_is.trades)
    base_oos_pnl = _pnl(base_oos.trades)
    n_is  = len(base_is.trades)
    n_oos = len(base_oos.trades)
    base_is_bd = _by_date(base_is.trades)
    print(f"  BASELINE: IS n={n_is} pnl={base_is_pnl:+,.0f} | OOS n={n_oos} pnl={base_oos_pnl:+,.0f}")

    # OOS exit breakdown to understand runner exit distribution
    print(f"\n  [OOS exit breakdown at baseline {BASELINE_TARGET}x]")
    by_exit = {}
    for t in base_oos.trades:
        k = str(getattr(t, "exit_reason", "?") or "?")
        by_exit.setdefault(k, []).append(t)
    for k, ts in sorted(by_exit.items(), key=lambda x: -sum(t.dollar_pnl for t in x[1])):
        n = len(ts); wins = sum(1 for t in ts if t.dollar_pnl > 0); tot = sum(t.dollar_pnl for t in ts)
        print(f"    {k:40}  n={n:>4}  WR={wins/n:.1%}  avg={tot/n:>+.0f}  total={tot:>+.0f}")

    # Runner exit premium distribution for OOS winners
    print(f"\n  [OOS winner exit premiums]")
    wins_oos = [t for t in base_oos.trades if t.dollar_pnl > 0]
    for t in sorted(wins_oos, key=lambda x: -x.dollar_pnl):
        ep = t.entry_premium
        rp = t.runner_exit_premium
        ratio_s = f"{rp/ep:.2f}x" if rp and ep else "N/A"
        er = getattr(t, "exit_reason", "?")
        print(f"    {_date(t)}  entry={ep:.2f}  runner_exit={rp:.2f}  ratio={ratio_s:>6}  pnl={t.dollar_pnl:>+8.0f}  {er}")

    # Sweep
    print(f"\n[SWEEP: runner targets vs baseline {BASELINE_TARGET}x]")
    print(f"  {'target':>7}  {'IS_n':>5}  {'IS_pnl':>9}  {'OOS_n':>5}  {'OOS_pnl':>9}  {'IS_delta':>9}  {'OOS_delta':>10}  {'WF':>7}  {'OOS+':>5}  {'VERDICT'}")
    print("  " + "-" * 105)
    print(f"  {BASELINE_TARGET:>6.2f}x  {n_is:>5}  {base_is_pnl:>+9,.0f}  {n_oos:>5}  {base_oos_pnl:>+9,.0f}  {'(base)':>9}  {'(base)':>10}  {'--':>7}  {'--':>5}  BASELINE")

    results = []
    for tgt in TARGETS:
        cand_is  = _run(spy_df, vix_df, IS_START,  IS_END,  tgt)
        cand_oos = _run(spy_df, vix_df, OOS_START, OOS_END, tgt)
        is_pnl  = _pnl(cand_is.trades)
        oos_pnl = _pnl(cand_oos.trades)
        is_d  = is_pnl  - base_is_pnl
        oos_d = oos_pnl - base_oos_pnl
        wf = (oos_d / n_oos) / (is_d / n_is) if is_d != 0 else float("inf") if oos_d > 0 else float("-inf")
        oos_pos = oos_d > 0
        wf_s = f"{wf:.3f}" if abs(wf) < 200 else ("INF+" if wf > 0 else "INF-")
        verdict = "CANDIDATE" if oos_pos and wf >= 0.70 else ("OOS+" if oos_pos else "OOS-")
        print(f"  {tgt:>6.2f}x  {len(cand_is.trades):>5}  {is_pnl:>+9,.0f}  {len(cand_oos.trades):>5}  {oos_pnl:>+9,.0f}  {is_d:>+9,.0f}  {oos_d:>+10,.0f}  {wf_s:>7}  {'YES' if oos_pos else 'NO':>5}  {verdict}")
        results.append((tgt, cand_is, cand_oos, is_d, oos_d, wf, oos_pos))

    # Best candidate
    passing = [(tgt, ci, co, id_, od, wf) for tgt, ci, co, id_, od, wf, oop in results if oop and wf >= 0.70]
    if not passing:
        print(f"\n  No candidate with OOS+ and WF>=0.70. Baseline {BASELINE_TARGET}x CONFIRMED OPTIMAL.")
    else:
        best = max(passing, key=lambda x: x[4])
        best_tgt, best_ci, best_co, best_id, best_od, best_wf = best
        print(f"\n[Sub-window: runner_target={best_tgt}x]")
        sub_hurts = 0
        sw_results = []
        for label, s, e in IS_SUBWINDOWS:
            b = _run(spy_df, vix_df, s, e, BASELINE_TARGET)
            c = _run(spy_df, vix_df, s, e, best_tgt)
            bp = _pnl(b.trades); cp = _pnl(c.trades); d = cp - bp
            verdict = "HURT" if d < -100 else ("HELP" if d > 100 else "NEUTRAL")
            if verdict == "HURT": sub_hurts += 1
            print(f"  {label:22}  base={bp:>+9,.0f}  cand={cp:>+9,.0f}  delta={d:>+8,.0f}  {verdict}")
            sw_results.append((label, bp, cp, d, verdict))
        sw_pass = sub_hurts <= 1

        cand_is_bd = _by_date(best_ci.trades)
        print(f"\n[Anchor trace: runner_target={best_tgt}x]")
        anchor_fails = []
        for d in sorted(J_WINNERS | J_LOSERS):
            bp = base_is_bd.get(d, 0.0); cp = cand_is_bd.get(d, 0.0)
            fail = bp > 0 and cp < bp * 0.90
            if fail: anchor_fails.append(str(d))
            tag = "(WINNER)" if d in J_WINNERS else "(LOSER)"
            print(f"  {str(d)}  {tag:9}  base={bp:>+8,.0f}  cand={cp:>+8,.0f}  {'FAIL' if fail else 'OK'}")
        anchor_ok = len(anchor_fails) == 0

        wf_s = f"{best_wf:.3f}" if abs(best_wf) < 200 else "INF"
        all_pass = (best_od > 0) and (best_wf >= 0.70) and sw_pass and anchor_ok
        print(f"\n{'='*100}")
        print(f"[VERDICT] SAFE runner_target: {BASELINE_TARGET}x -> {best_tgt}x")
        print(f"  OOS+: {best_od > 0} (delta={best_od:+,.0f})  WF: {best_wf >= 0.70} ({wf_s})  SW: {sw_pass} (HURT={sub_hurts})  Anchor: {anchor_ok}")
        print(f"  >>> {'PASS' if all_pass else 'FAIL'} <<<")
        print(f"{'='*100}")

    print("\nANALYSIS COMPLETE.")
