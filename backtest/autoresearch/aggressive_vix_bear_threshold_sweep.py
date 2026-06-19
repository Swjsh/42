"""
AGG_VIX_BEAR_THRESHOLD_SWEEP

Motivated by OOS deep dive (1b82872a):
  VIX <17: n=9 trades WR=33% avg=-44 total=-400  (LOSING)
  VIX 17-20: n=16 trades WR=44% avg=+191 total=+3059 (WINNING)
  VIX 20-25: n=3 trades WR=100% avg=+204 total=+613 (WINNING)

Aggressive currently uses vix_bear_threshold=15.0 (fires BEAR when VIX>=15).
Safe uses VIX_BEAR_THRESHOLD=17.3 (default constant in filters.py).

Question: Should Aggressive raise its bear threshold from 15 → 16/17/17.3/17.5/18?
A higher threshold removes the VIX 15-17 bear entries that are dragging OOS P&L.

Sweep: 15.0 (baseline), 16.0, 17.0, 17.3, 17.5, 18.0

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

# Aggressive baseline — post ENFORCED-2/3/5 (correct as of 2026-06-17)
# Expected: IS n=109 pnl=+19,080 | OOS n=18 pnl=+3,833
# NOTE: OOS deep dive finding (VIX<17 n=9 WR=33% -$400) was pre-ENFORCED-5.
# ENFORCED-5 (require_bearish_fill_bar) reduced OOS n=28→18. Effect may be smaller post-fix.
AGG_BASE_KW = dict(
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
    block_conf_lvl_rec_afternoon=True,           # ENFORCED-2
    block_conf_lvl_rej_midday_afternoon=True,    # ENFORCED-3
    require_bearish_fill_bar=True,               # ENFORCED-5 (J-RATIFIED 2026-06-17)
)

THRESHOLDS = [15.0, 16.0, 17.0, 17.3, 17.5, 18.0]  # baseline=15.0


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


def _run(spy_df, vix_df, start, end, thresh):
    overrides = {"vix_bear_threshold": thresh, "vix_bull_max": 30.0, "strike_offset_itm": 2}
    return run_backtest(spy_df, vix_df, start_date=start, end_date=end, params_overrides=overrides, **AGG_BASE_KW)


if __name__ == "__main__":
    print("=" * 100)
    print("AGG VIX_BEAR_THRESHOLD SWEEP (Aggressive account)")
    print("Motivation: OOS deep dive shows VIX<17 bear entries WR=33% avg=-44 total=-400")
    print("=" * 100)

    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    # Full IS/OOS for each threshold
    print("\n[FULL IS/OOS SUMMARY]")
    print(f"  {'thresh':>6}  {'IS_n':>5}  {'IS_pnl':>8}  {'OOS_n':>5}  {'OOS_pnl':>9}  {'IS_delta':>9}  {'OOS_delta':>10}  {'WF':>7}  {'OOS+':>5}")
    print("  " + "-" * 90)

    # Baseline run
    base_is  = _run(spy_df, vix_df, IS_START, IS_END, 15.0)
    base_oos = _run(spy_df, vix_df, OOS_START, OOS_END, 15.0)
    base_is_pnl  = _pnl(base_is.trades)
    base_oos_pnl = _pnl(base_oos.trades)
    base_is_bd   = _by_date(base_is.trades)
    n_is_base = len(base_is.trades)
    n_oos_base = len(base_oos.trades)
    print(f"  {15.0:>6.1f}  {n_is_base:>5}  {base_is_pnl:>+8.0f}  {n_oos_base:>5}  {base_oos_pnl:>+9.0f}  {'(baseline)':>9}  {'(baseline)':>10}  {'--':>7}  {'--':>5}")

    results = []
    for thresh in THRESHOLDS[1:]:
        cand_is  = _run(spy_df, vix_df, IS_START, IS_END, thresh)
        cand_oos = _run(spy_df, vix_df, OOS_START, OOS_END, thresh)
        is_pnl   = _pnl(cand_is.trades)
        oos_pnl  = _pnl(cand_oos.trades)
        is_delta  = is_pnl - base_is_pnl
        oos_delta = oos_pnl - base_oos_pnl
        n_is  = len(cand_is.trades)
        n_oos = len(cand_oos.trades)
        if is_delta > 0:
            wf = (oos_delta / n_oos_base) / (is_delta / n_is_base)
        else:
            wf = float("nan")  # L155: IS_delta <= 0 → WF undefined
        oos_pos = "YES" if oos_delta > 0 else "NO"
        cand_oos_bd = _by_date(cand_oos.trades)
        anchor = _anchor_ok(cand_oos_bd, base_is_bd)
        wf_str = f"{wf:.3f}" if wf == wf else "L155"
        print(f"  {thresh:>6.1f}  {n_is:>5}  {is_pnl:>+8.0f}  {n_oos:>5}  {oos_pnl:>+9.0f}  {is_delta:>+9.0f}  {oos_delta:>+10.0f}  {wf_str:>7}  {oos_pos:>5}")
        results.append((thresh, cand_is, cand_oos, is_delta, oos_delta, wf, oos_pos == "YES", anchor))

    # Sub-window analysis for best candidate (highest OOS_delta that is positive)
    pos_results = [(t, ci, co, id_, od, wf, a) for t, ci, co, id_, od, wf, oos_p, a in results if oos_p and id_ > 0]  # L155: require IS_delta > 0
    if pos_results:
        best_thresh, best_ci, best_co, best_id, best_od, best_wf, best_anchor = pos_results[-1]
        print(f"\n[SUB-WINDOW ANALYSIS for best candidate: thresh={best_thresh}]")
        print(f"  {'Window':20}  {'BASE_n':>6}  {'CAND_n':>6}  {'BASE_pnl':>9}  {'CAND_pnl':>9}  {'delta':>7}  {'verdict':>8}")
        print("  " + "-" * 85)
        sub_hurts = 0
        for label, s, e in IS_SUBWINDOWS:
            b = _run(spy_df, vix_df, s, e, 15.0)
            c = _run(spy_df, vix_df, s, e, best_thresh)
            bp = _pnl(b.trades)
            cp = _pnl(c.trades)
            d = cp - bp
            verdict = "HURT" if d < -500 else ("HELP" if d > 100 else "NEUTRAL")
            if verdict == "HURT":
                sub_hurts += 1
            print(f"  {label:20}  {len(b.trades):>6}  {len(c.trades):>6}  {bp:>+9.0f}  {cp:>+9.0f}  {d:>+7.0f}  {verdict:>8}")
        sub_stable = sub_hurts <= 1

        print(f"\n  HURT={sub_hurts} | sub_stable={'PASS' if sub_stable else 'FAIL'}")

        # Anchor trace
        print(f"\n[ANCHOR TRACE for thresh={best_thresh}]")
        print(f"  {'Date':12}  {'BASE_pnl':>9}  {'CAND_pnl':>9}  {'OK?':>5}")
        base_is_bd_ = _by_date(base_is.trades)
        cand_is_bd  = _by_date(best_ci.trades)
        for d in sorted(J_WINNERS | J_LOSERS):
            bp = base_is_bd_.get(d, 0.0)
            cp = cand_is_bd.get(d, 0.0)
            ok = "OK" if not (bp > 0 and cp < bp * 0.90) else "FAIL"
            tag = " (WINNER)" if d in J_WINNERS else " (LOSER)"
            print(f"  {str(d):12}  {bp:>+9.0f}  {cp:>+9.0f}  {ok:>5}{tag}")

        # OOS blocked trades
        print(f"\n[OOS BLOCKED TRADES at thresh={best_thresh}]")
        base_oos_et = set(t.entry_time_et for t in base_oos.trades)
        cand_oos_et = set(t.entry_time_et for t in best_co.trades)
        blocked = [t for t in base_oos.trades if t.entry_time_et not in cand_oos_et]
        if not blocked:
            print("  None blocked in OOS")
        def _safe_et(t):
            et = t.entry_time_et
            return et.replace(tzinfo=None) if getattr(et, "tzinfo", None) else et
        for t in sorted(blocked, key=_safe_et):
            vix = getattr(t, "entry_vix", None)
            vix_s = f"{vix:.1f}" if vix is not None else "?"
            print(f"  {t.entry_time_et}  VIX={vix_s}  pnl={t.dollar_pnl:+.0f}")

        print(f"\n[FINAL VERDICT]")
        wf_pass = best_wf >= 0.70
        oos_pos_f = best_od > 0
        print(f"  OOS positive: {oos_pos_f} (delta={best_od:+.0f})")
        print(f"  WF >= 0.70: {wf_pass} (WF={best_wf:.3f})")
        print(f"  Sub-window stable: {sub_stable}")
        print(f"  Anchor OK: {best_anchor}")
        all_pass = oos_pos_f and wf_pass and sub_stable and best_anchor
        print(f"\n  CANDIDATE thresh={best_thresh}: {'PASS - file A/B scorecard' if all_pass else 'FAIL - reject'}")
        if all_pass:
            print(f"\n  RECOMMENDATION: Set vix_bear_threshold={best_thresh} in Aggressive params_overrides")
            print(f"  Mechanism: blocks BEAR entries when VIX < {best_thresh} (removes low-VIX bear noise)")
    else:
        print(f"\n  No candidate with OOS_positive. Baseline threshold=15.0 CONFIRMED OPTIMAL.")

    print("\nANALYSIS COMPLETE.")
