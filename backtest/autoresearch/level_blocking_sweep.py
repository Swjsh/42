"""
LEVEL ENTRY BLOCKING SWEEP

From negative_windows_analysis.py:
  LEVEL trades in NEG windows: n=9, -$869/trade
  LEVEL trades in POS windows: n=8, -$267/trade
  Even in POSITIVE windows, LEVEL trades lose money!

  IS breakdown (from trigger_breakdown.py):
    LEVEL (level_rejection alone): n=17, WR=29.4%, avg -$627/trade, total -$10,659 IS

  The question: does blocking LEVEL entries improve IS AND OOS?

LEVEL quality tier = has level_rejection or level_reclaim trigger, NO confluence, NO sequence_rejection.

Approach: use min_premium_for_level_tiers as a filter
  Actually: min_premium is inert (all LEVEL entries have premium > $0.80).
  Better: use QUALITY_ESCALATION_LOCK or a minimum quality gate.

Alternative approach: test what happens if LEVEL entries are simply removed
  from the simulation by checking if there's a "min_quality" parameter.

Actually: the correct sweep is to test if the LEVEL entries being removed from
  IS+OOS would pass all 4 ratification gates.

Method: Find LEVEL trades in IS/OOS and compute P&L without them.
  This requires extracting LEVEL-classified trades and computing delta.
  Cannot "block" LEVEL via any existing params — must simulate "no LEVEL entries"
  by post-filtering the trade list.

IMPORTANT: This is a DIAGNOSTIC analysis, not a backtest sweep.
  It calculates the THEORETICAL maximum if LEVEL entries were blocked.
  A production gate would require adding a quality_min_gate parameter to the engine.

Security: read-only. No Alpaca calls. Free-tier only.
"""
from __future__ import annotations
import sys
import pathlib
import datetime as dt
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd
from backtest.lib.orchestrator import run_backtest

DATA_DIR = ROOT / "backtest" / "data"
SPY_FILE  = DATA_DIR / "spy_5m_2025-01-01_2026-05-22.csv"
VIX_FILE  = DATA_DIR / "vix_5m_2025-01-01_2026-05-22.csv"

IS_START  = dt.date(2025, 1, 2)
IS_END    = dt.date(2026, 5, 7)
OOS_START = dt.date(2026, 5, 8)
OOS_END   = dt.date(2026, 5, 22)

J_WINNERS = {dt.date(2026, 4, 29), dt.date(2026, 5, 1), dt.date(2026, 5, 4)}

BASE = dict(
    use_real_fills=True,
    premium_stop_pct_bear=-0.20,
    premium_stop_pct_bull=-0.08,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.50,
    time_stop_minutes_before_close=20,
    midday_trendline_gate=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    per_trade_risk_cap_pct=0.30,
)


def _quality(triggers: list) -> str:
    tf = set(triggers or [])
    has_conf = "confluence" in tf
    has_rf   = "ribbon_flip_bearish" in tf or "ribbon_flip_bullish" in tf
    has_lvl  = "level_rejection" in tf or "level_reclaim" in tf
    has_seq  = "sequence_rejection" in tf
    has_tl   = "trendline_rejection" in tf
    n        = len(tf)
    if (has_conf and has_rf) or n >= 3:
        return "SUPER"
    if has_conf or has_seq:
        return "ELITE"
    if has_lvl:
        return "LEVEL"
    if has_tl:
        return "TRENDLINE"
    return "OTHER"


def _date(t):
    et = t.entry_time_et
    d = et.replace(tzinfo=None) if getattr(et, "tzinfo", None) else et
    return d.date()


def _pnl(trades):
    return sum(t.dollar_pnl for t in trades)


def _filter_by_quality(trades, exclude_qualities: set):
    return [t for t in trades if _quality(getattr(t, 'triggers_fired', [])) not in exclude_qualities]


def _anchor_ok(by_date, base_bd):
    for d in J_WINNERS:
        bp = base_bd.get(d, 0.0)
        cp = by_date.get(d, 0.0)
        if bp > 0 and cp < bp * 0.90:
            return False
    return True


def _by_date(trades):
    result = {}
    for t in trades:
        d = _date(t)
        result[d] = result.get(d, 0.0) + t.dollar_pnl
    return result


def _summary(label, trades, base_pnl, base_bd, baseline_n):
    pnl = _pnl(trades)
    bd  = _by_date(trades)
    delta = pnl - base_pnl
    anchor = _anchor_ok(bd, base_bd)
    wins = sum(1 for t in trades if t.dollar_pnl > 0)
    wr = wins / len(trades) * 100 if trades else 0
    print(f"  {label}: n={len(trades)} (-{baseline_n - len(trades)} removed) "
          f"pnl={pnl:+.0f} delta={delta:+.0f} WR={wr:.0f}% anchor={'OK' if anchor else 'FAIL'}")
    return delta, anchor


if __name__ == "__main__":
    print("=" * 90)
    print("LEVEL ENTRY BLOCKING DIAGNOSTIC SWEEP")
    print("=" * 90)

    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    print("\n[BASELINE]")
    is_r  = run_backtest(spy_df, vix_df, start_date=IS_START, end_date=IS_END, **BASE)
    oos_r = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END, **BASE)
    is_pnl  = _pnl(is_r.trades)
    oos_pnl = _pnl(oos_r.trades)
    is_bd = _by_date(is_r.trades)
    n_is = len(is_r.trades)
    n_oos = len(oos_r.trades)
    print(f"  IS n={n_is} pnl={is_pnl:+.0f}")
    print(f"  OOS n={n_oos} pnl={oos_pnl:+.0f}")

    print("\n[IS QUALITY DISTRIBUTION]")
    by_q = defaultdict(list)
    for t in is_r.trades:
        by_q[_quality(getattr(t, 'triggers_fired', []))].append(t)
    for q in ["SUPER", "ELITE", "LEVEL", "TRENDLINE", "OTHER"]:
        ts = by_q[q]
        if ts:
            qp = _pnl(ts)
            qw = sum(1 for t in ts if t.dollar_pnl > 0)
            qwr = qw / len(ts) * 100
            print(f"  {q:12}: n={len(ts):3} pnl={qp:+.0f} WR={qwr:.0f}%  ({qp/len(ts):+.0f}/trade)")

    print("\n[OOS QUALITY DISTRIBUTION]")
    by_q_oos = defaultdict(list)
    for t in oos_r.trades:
        by_q_oos[_quality(getattr(t, 'triggers_fired', []))].append(t)
    for q in ["SUPER", "ELITE", "LEVEL", "TRENDLINE", "OTHER"]:
        ts = by_q_oos[q]
        if ts:
            qp = _pnl(ts)
            qw = sum(1 for t in ts if t.dollar_pnl > 0)
            qwr = qw / len(ts) * 100
            print(f"  {q:12}: n={len(ts):3} pnl={qp:+.0f} WR={qwr:.0f}%  ({qp/len(ts):+.0f}/trade)")

    print("\n[SCENARIO A: Block LEVEL only]")
    is_no_level  = _filter_by_quality(is_r.trades, {"LEVEL"})
    oos_no_level = _filter_by_quality(oos_r.trades, {"LEVEL"})
    is_d, is_a = _summary("IS no-LEVEL ", is_no_level, is_pnl, is_bd, n_is)
    oos_d, oos_a = _summary("OOS no-LEVEL", oos_no_level, oos_pnl, _by_date(oos_r.trades), n_oos)
    wf_a = (oos_d / n_oos) / (is_d / n_is) if is_d != 0 else 0.0
    print(f"  WF_norm: {wf_a:.3f}  {'PASS (>=0.70)' if oos_d > 0 and wf_a >= 0.70 and is_a and oos_a else 'FAIL'}")

    print("\n[SCENARIO B: Block LEVEL + TRENDLINE]")
    is_no_lvl_tl  = _filter_by_quality(is_r.trades, {"LEVEL", "TRENDLINE"})
    oos_no_lvl_tl = _filter_by_quality(oos_r.trades, {"LEVEL", "TRENDLINE"})
    is_d2, is_a2 = _summary("IS no-LVL-TL ", is_no_lvl_tl, is_pnl, is_bd, n_is)
    oos_d2, oos_a2 = _summary("OOS no-LVL-TL", oos_no_lvl_tl, oos_pnl, _by_date(oos_r.trades), n_oos)
    wf_b = (oos_d2 / n_oos) / (is_d2 / n_is) if is_d2 != 0 else 0.0
    print(f"  WF_norm: {wf_b:.3f}  {'PASS (>=0.70)' if oos_d2 > 0 and wf_b >= 0.70 and is_a2 and oos_a2 else 'FAIL'}")

    print("\n[SCENARIO C: Block LEVEL at VIX >= 22]")
    def _no_high_vix_level(trades, vix_thresh=22.0):
        result = []
        for t in trades:
            q = _quality(getattr(t, 'triggers_fired', []))
            vix = getattr(t, 'entry_vix', 0)
            if q == "LEVEL" and vix >= vix_thresh:
                continue
            result.append(t)
        return result

    for thresh in [20.0, 22.0, 25.0]:
        is_c  = _no_high_vix_level(is_r.trades, thresh)
        oos_c = _no_high_vix_level(oos_r.trades, thresh)
        pnl_c_is  = _pnl(is_c)
        pnl_c_oos = _pnl(oos_c)
        is_dc = pnl_c_is - is_pnl
        oos_dc = pnl_c_oos - oos_pnl
        bd_c = _by_date(is_c)
        anchor_c = _anchor_ok(bd_c, is_bd)
        wf_c = (oos_dc / n_oos) / (is_dc / n_is) if is_dc != 0 else 0.0
        verdict = "PASS" if oos_dc > 0 and wf_c >= 0.70 and anchor_c and oos_dc > 0 else "FAIL"
        n_rem_is = n_is - len(is_c)
        n_rem_oos = n_oos - len(oos_c)
        print(f"  LEVEL blocked at VIX>={thresh}: IS delta={is_dc:+.0f} (-{n_rem_is} trades) "
              f"OOS delta={oos_dc:+.0f} (-{n_rem_oos} trades) WF={wf_c:.3f} anchor={'OK' if anchor_c else 'FAIL'} -> {verdict}")

    print("\n[SCENARIO D: Block LEVEL at VIX >= 20 + TRENDLINE at VIX >= 25]")
    def _combined_filter(trades):
        result = []
        for t in trades:
            q = _quality(getattr(t, 'triggers_fired', []))
            vix = getattr(t, 'entry_vix', 0)
            if q == "LEVEL" and vix >= 20.0:
                continue
            if q == "TRENDLINE" and vix >= 25.0:
                continue
            result.append(t)
        return result

    is_d_comb  = _combined_filter(is_r.trades)
    oos_d_comb = _combined_filter(oos_r.trades)
    pnl_d_is   = _pnl(is_d_comb)
    pnl_d_oos  = _pnl(oos_d_comb)
    delta_d_is  = pnl_d_is - is_pnl
    delta_d_oos = pnl_d_oos - oos_pnl
    bd_d = _by_date(is_d_comb)
    anchor_d = _anchor_ok(bd_d, is_bd)
    wf_d = (delta_d_oos / n_oos) / (delta_d_is / n_is) if delta_d_is != 0 else 0.0
    print(f"  Combined: IS delta={delta_d_is:+.0f} (-{n_is - len(is_d_comb)} trades) "
          f"OOS delta={delta_d_oos:+.0f} (-{n_oos - len(oos_d_comb)} trades) "
          f"WF={wf_d:.3f} anchor={'OK' if anchor_d else 'FAIL'}")

    print("\n" + "=" * 90)
    print("SUMMARY")
    print("=" * 90)
    print(f"\n  NOTE: This is a DIAGNOSTIC analysis. Scores computed by post-filtering backtest output,")
    print(f"  NOT by adding a quality_gate parameter to the backtest engine.")
    print(f"  To productionize a PASS scenario, add quality_min_tier parameter to orchestrator.")
    print(f"\n  Key finding: LEVEL trades in IS = {len(by_q['LEVEL'])} trades, total pnl = {_pnl(by_q['LEVEL']):+.0f}")
    print(f"  LEVEL trades in OOS = {len(by_q_oos['LEVEL'])} trades, total pnl = {_pnl(by_q_oos['LEVEL']):+.0f}")

    print("\nANALYSIS COMPLETE.")
