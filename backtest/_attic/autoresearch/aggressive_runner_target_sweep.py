"""
AGG_RUNNER_TARGET_SWEEP

Motivated by OOS deep dive:
  TP1+runner exits: all 100% WR. But runners exit on ribbon flip (not 5x target).
  5/13 trade: runner_exit_premium=6.43 vs entry=2.40 (2.68x) — time-stopped, never hit 5x.
  5/08, 5/21: runner_exit_premium ≈ entry_premium (ribbon flip at ~1x, BE-like exit).

Current Aggressive runner_target_premium_pct=5.0 (5x entry premium).
Safe uses 2.5x. Hypothesis: 5x may be too ambitious. Runners often exit before 5x via
ribbon flip or time stop. A lower target captures exits that happen at 2-4x before reversal.

Sweep: 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0 (baseline)

Gates: OOS_positive AND WF>=0.70 AND SW_hurt<=1 AND anchor_OK

Security: read-only. No Alpaca calls. Free-tier only.
"""
from __future__ import annotations
import sys
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

# Aggressive baseline (post-TIGHTER_STOP_2 + Rank35)
AGG_BASE_KW = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=False,
    premium_stop_pct_bear=-0.07,
    tp1_qty_fraction=0.667,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.50,
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
    tp1_premium_pct=0.75,                # C14 fix: must match production (default is 0.30)
)
AGG_OVR = {"vix_bear_threshold": 15.0, "vix_bull_max": 30.0}

TARGETS = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0]  # baseline=5.0


def _pnl(trades):
    return sum(t.dollar_pnl for t in trades)


def _date(t):
    et = t.entry_time_et
    d = et.replace(tzinfo=None) if getattr(et, "tzinfo", None) else et
    return d.date()


def _by_date(trades):
    result = {}
    for t in trades:
        d = _date(t)
        result[d] = result.get(d, 0.0) + t.dollar_pnl
    return result


def _anchor_ok(cand_bd, base_bd):
    for d in J_WINNERS:
        bp = base_bd.get(d, 0.0)
        cp = cand_bd.get(d, 0.0)
        if bp > 0 and cp < bp * 0.90:
            return False
    return True


def _run(spy_df, vix_df, start, end, target):
    overrides = dict(AGG_OVR)
    return run_backtest(
        spy_df, vix_df, start_date=start, end_date=end,
        runner_target_premium_pct=target,
        params_overrides=overrides, **AGG_BASE_KW
    )


if __name__ == "__main__":
    print("=" * 110)
    print("AGG RUNNER_TARGET_PREMIUM_PCT SWEEP")
    print("Motivation: OOS runners exit via ribbon flip/time stop, never hitting 5x target.")
    print("=" * 110)

    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    # Baseline at 5.0x
    base_is  = _run(spy_df, vix_df, IS_START, IS_END, 5.0)
    base_oos = _run(spy_df, vix_df, OOS_START, OOS_END, 5.0)
    base_is_pnl  = _pnl(base_is.trades)
    base_oos_pnl = _pnl(base_oos.trades)
    base_is_bd   = _by_date(base_is.trades)
    n_is_base  = len(base_is.trades)
    n_oos_base = len(base_oos.trades)

    print(f"\n[BASELINE at 5.0x]: IS n={n_is_base} pnl={base_is_pnl:+,.0f} | OOS n={n_oos_base} pnl={base_oos_pnl:+,.0f}")

    # Show exit reason breakdown at baseline to understand runner exits
    print(f"\n[OOS EXIT REASON BREAKDOWN at 5.0x (baseline)]")
    by_exit = {}
    for t in base_oos.trades:
        k = str(getattr(t, "exit_reason", "?") or "?")
        by_exit.setdefault(k, []).append(t)
    print(f"  {'Exit':40}  {'n':>4}  {'WR':>6}  {'avg':>8}  {'total':>9}")
    print("  " + "-" * 75)
    for k, ts in sorted(by_exit.items(), key=lambda x: -sum(t.dollar_pnl for t in x[1])):
        n = len(ts); wins = sum(1 for t in ts if t.dollar_pnl > 0); tot = sum(t.dollar_pnl for t in ts)
        print(f"  {k:40}  {n:>4}  {wins/n:>6.1%}  {tot/n:>+8.0f}  {tot:>+9.0f}")

    # Runner exit premium distribution from OOS winners
    print(f"\n[RUNNER EXIT PREMIUM DISTRIBUTION (OOS winners)]")
    wins = [t for t in base_oos.trades if t.dollar_pnl > 0]
    print(f"  {'Date':12}  {'entry':>7}  {'runner_exit':>12}  {'ratio':>6}  {'pnl':>8}  {'exit_reason'}")
    for t in sorted(wins, key=lambda x: -x.dollar_pnl):
        d = _date(t)
        ep = t.entry_premium
        rp = t.runner_exit_premium
        ratio_s = f"{rp/ep:.2f}x" if rp and ep else "N/A"
        print(f"  {str(d):12}  {ep:>7.2f}  {rp:>12.2f}  {ratio_s:>6}  {t.dollar_pnl:>+8.0f}  {getattr(t,'exit_reason','?')}")

    # Full sweep
    print(f"\n[FULL IS/OOS SUMMARY]")
    print(f"  {'target':>7}  {'IS_n':>5}  {'IS_pnl':>8}  {'OOS_n':>5}  {'OOS_pnl':>9}  {'IS_delta':>9}  {'OOS_delta':>10}  {'WF':>7}  {'OOS+':>5}  {'anchor':>7}")
    print("  " + "-" * 105)
    print(f"  {'5.0x':>7}  {n_is_base:>5}  {base_is_pnl:>+8.0f}  {n_oos_base:>5}  {base_oos_pnl:>+9.0f}  {'(baseline)':>9}  {'(baseline)':>10}  {'--':>7}  {'--':>5}  {'--':>7}")

    results = []
    for tgt in TARGETS[:-1]:  # all except 5.0 (baseline)
        cand_is  = _run(spy_df, vix_df, IS_START, IS_END, tgt)
        cand_oos = _run(spy_df, vix_df, OOS_START, OOS_END, tgt)
        is_pnl   = _pnl(cand_is.trades)
        oos_pnl  = _pnl(cand_oos.trades)
        is_delta  = is_pnl - base_is_pnl
        oos_delta = oos_pnl - base_oos_pnl
        wf = (oos_delta / n_oos_base) / (is_delta / n_is_base) if is_delta != 0 else float("inf") if oos_delta > 0 else float("-inf")
        oos_pos = oos_delta > 0
        cand_oos_bd = _by_date(cand_oos.trades)
        anchor = _anchor_ok(cand_oos_bd, base_is_bd)
        oos_s = "YES" if oos_pos else "NO"
        anc_s = "OK" if anchor else "FAIL"
        wf_s = f"{wf:.3f}" if abs(wf) < 100 else ("INF+" if wf > 0 else "INF-")
        print(f"  {tgt:>6.1f}x  {len(cand_is.trades):>5}  {is_pnl:>+8.0f}  {len(cand_oos.trades):>5}  {oos_pnl:>+9.0f}  {is_delta:>+9.0f}  {oos_delta:>+10.0f}  {wf_s:>7}  {oos_s:>5}  {anc_s:>7}")
        results.append((tgt, cand_is, cand_oos, is_delta, oos_delta, wf, oos_pos, anchor))

    # Best candidate: prefer OOS positive with highest WF
    passing = [(tgt, ci, co, id_, od, wf, a) for tgt, ci, co, id_, od, wf, oo_p, a in results if oo_p and od > 0 and wf >= 0.70]
    best_candidates = [(tgt, ci, co, id_, od, wf, a) for tgt, ci, co, id_, od, wf, oo_p, a in results if oo_p]

    if passing:
        best = max(passing, key=lambda x: x[5])
        verdict_list = passing
    elif best_candidates:
        best = max(best_candidates, key=lambda x: x[4])
        verdict_list = []
    else:
        best = None
        verdict_list = []

    if best:
        best_tgt, best_ci, best_co, best_id, best_od, best_wf, best_anchor = best

        print(f"\n[SUB-WINDOW ANALYSIS: runner_target={best_tgt}x]")
        print(f"  {'Window':20}  {'BASE_n':>6}  {'CAND_n':>6}  {'BASE_pnl':>9}  {'CAND_pnl':>9}  {'delta':>7}  {'verdict':>8}")
        print("  " + "-" * 85)
        sub_hurts = 0
        for label, s, e in IS_SUBWINDOWS:
            b = _run(spy_df, vix_df, s, e, 5.0)
            c = _run(spy_df, vix_df, s, e, best_tgt)
            bp = _pnl(b.trades)
            cp = _pnl(c.trades)
            d = cp - bp
            verdict = "HURT" if d < -100 else ("HELP" if d > 100 else "NEUTRAL")
            if verdict == "HURT":
                sub_hurts += 1
            print(f"  {label:20}  {len(b.trades):>6}  {len(c.trades):>6}  {bp:>+9.0f}  {cp:>+9.0f}  {d:>+7.0f}  {verdict:>8}")
        sub_stable = sub_hurts <= 1

        # Anchor trace
        print(f"\n[ANCHOR TRACE: runner_target={best_tgt}x]")
        base_is_bd_ = _by_date(base_is.trades)
        cand_is_bd  = _by_date(best_ci.trades)
        for d in sorted(J_WINNERS | J_LOSERS):
            bp = base_is_bd_.get(d, 0.0)
            cp = cand_is_bd.get(d, 0.0)
            ok = "OK" if not (bp > 0 and cp < bp * 0.90) else "FAIL"
            tag = " (WINNER)" if d in J_WINNERS else " (LOSER)"
            print(f"  {str(d):12}  base={bp:>+8.0f}  cand={cp:>+8.0f}  {ok}{tag}")

        # OOS exit distribution for best candidate
        print(f"\n[OOS EXIT BREAKDOWN at runner_target={best_tgt}x]")
        by_exit_c = {}
        for t in best_co.trades:
            k = str(getattr(t, "exit_reason", "?") or "?")
            by_exit_c.setdefault(k, []).append(t)
        for k, ts in sorted(by_exit_c.items(), key=lambda x: -sum(t.dollar_pnl for t in x[1])):
            n = len(ts); wins = sum(1 for t in ts if t.dollar_pnl > 0); tot = sum(t.dollar_pnl for t in ts)
            print(f"  {k:40}  n={n:>4}  WR={wins/n:.1%}  avg={tot/n:>+.0f}  total={tot:>+.0f}")

        print(f"\n[FINAL VERDICT: runner_target={best_tgt}x]")
        wf_pass = best_wf >= 0.70
        oos_pos_f = best_od > 0
        wf_s = f"{best_wf:.3f}" if abs(best_wf) < 100 else "INF"
        print(f"  OOS positive:      {oos_pos_f} (delta={best_od:+.0f})")
        print(f"  WF >= 0.70:        {wf_pass} (WF={wf_s})")
        print(f"  Sub-window stable: {sub_stable} (HURT={sub_hurts})")
        print(f"  Anchor OK:         {best_anchor}")
        all_pass = oos_pos_f and wf_pass and sub_stable and best_anchor
        print(f"\n  VERDICT: {'PASS — file A/B scorecard' if all_pass else 'FAIL — reject'}")
        if all_pass:
            print(f"  RECOMMENDATION: Set runner_target_premium_pct={best_tgt} in Aggressive params.json")
    else:
        print(f"\n  No candidate with OOS positive delta. Baseline 5.0x CONFIRMED OPTIMAL.")

    print("\nANALYSIS COMPLETE.")
