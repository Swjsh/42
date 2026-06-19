"""
AGG_RIBBON_SPREAD_SWEEP

Motivated by IS composition:
  trendline_only: n=186, WR=30%, avg=+5/trade (+962 total) — barely profitable
  conf+lvl_rec: n=42, avg=+81/trade — profitable
  conf+lvl_rej: n=22, avg=+259/trade — profitable

Current global ribbon_spread_min_cents=30c applies to ALL entry types.
Hypothesis: trendline_only setups require genuine ribbon conviction.
At low ribbon spread (30-35c), trendline entries may be noise. Raising the
minimum spread would filter out the weakest trendline entries while preserving
high-spread confluence/level entries (which typically have wider spread).

Sweep: 25, 30 (baseline), 35, 40, 45, 50 cents.

Gates: OOS_positive AND WF>=0.70 AND SW_hurt<=1 AND anchor_OK

Security: read-only. No Alpaca calls. Free-tier only.
"""
from __future__ import annotations
import sys
import datetime as dt
import pathlib
import json

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
    runner_target_premium_pct=5.0,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.50,
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
    tp1_premium_pct=0.75,                # C14 fix: must match production (default is 0.30)
)

AGG_VIX_OVERRIDES = {"vix_bear_threshold": 15.0, "vix_bull_max": 30.0}

SPREADS = [25, 30, 35, 40, 45, 50]  # cents; 30=baseline


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


def _run(spy_df, vix_df, start, end, spread):
    overrides = dict(AGG_VIX_OVERRIDES)
    overrides["ribbon_spread_min_cents"] = spread
    return run_backtest(spy_df, vix_df, start_date=start, end_date=end, params_overrides=overrides, **AGG_BASE_KW)


def _trigger_label(t):
    trigs = getattr(t, "triggers_fired", [])
    if isinstance(trigs, str):
        try:
            trigs = json.loads(trigs)
        except Exception:
            trigs = [trigs]
    tstr = "+".join(sorted(trigs)) if trigs else ""
    if "confluence" in tstr and "level_rejection" in tstr:
        return "conf+lvl_rej"
    if "confluence" in tstr and "level_reclaim" in tstr:
        return "conf+lvl_rec"
    if "confluence" in tstr:
        return "conf+tl"
    if "level_rejection" in tstr:
        return "lvl_rej"
    if "level_reclaim" in tstr:
        return "lvl_rec"
    return "trendline_only"


if __name__ == "__main__":
    print("=" * 110)
    print("AGG RIBBON_SPREAD_MIN_CENTS SWEEP")
    print("Motivation: IS trendline_only n=186 avg=+5/trade — does higher spread filter weak entries?")
    print("=" * 110)

    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    # Baseline at 30c
    base_is  = _run(spy_df, vix_df, IS_START, IS_END, 30)
    base_oos = _run(spy_df, vix_df, OOS_START, OOS_END, 30)
    base_is_pnl  = _pnl(base_is.trades)
    base_oos_pnl = _pnl(base_oos.trades)
    base_is_bd   = _by_date(base_is.trades)
    n_is_base  = len(base_is.trades)
    n_oos_base = len(base_oos.trades)

    print(f"\n[BASELINE at 30c]: IS n={n_is_base} pnl={base_is_pnl:+,.0f} | OOS n={n_oos_base} pnl={base_oos_pnl:+,.0f}")

    print(f"\n[IS TRIGGER BREAKDOWN at 30c (baseline)]")
    by_trig_is: dict = {}
    for t in base_is.trades:
        k = _trigger_label(t)
        by_trig_is.setdefault(k, []).append(t)
    print(f"  {'Trigger':22}  {'n':>5}  {'WR':>6}  {'avg':>8}  {'total':>9}")
    print("  " + "-" * 60)
    for k, ts in sorted(by_trig_is.items(), key=lambda x: -sum(t.dollar_pnl for t in x[1])):
        n = len(ts); wins = sum(1 for t in ts if t.dollar_pnl > 0); tot = sum(t.dollar_pnl for t in ts)
        print(f"  {k:22}  {n:>5}  {wins/n:>6.1%}  {tot/n:>+8.0f}  {tot:>+9.0f}")

    print(f"\n[OOS TRIGGER BREAKDOWN at 30c (baseline)]")
    by_trig_oos: dict = {}
    for t in base_oos.trades:
        k = _trigger_label(t)
        by_trig_oos.setdefault(k, []).append(t)
    for k, ts in sorted(by_trig_oos.items(), key=lambda x: -sum(t.dollar_pnl for t in x[1])):
        n = len(ts); wins = sum(1 for t in ts if t.dollar_pnl > 0); tot = sum(t.dollar_pnl for t in ts)
        print(f"  {k:22}  {n:>5}  {wins/n:>6.1%}  {tot/n:>+8.0f}  {tot:>+9.0f}")

    # Full IS/OOS sweep
    print(f"\n[FULL IS/OOS SUMMARY]")
    print(f"  {'spread':>6}  {'IS_n':>5}  {'IS_pnl':>8}  {'OOS_n':>5}  {'OOS_pnl':>9}  {'IS_delta':>9}  {'OOS_delta':>10}  {'WF':>7}  {'OOS+':>5}  {'anchor':>7}")
    print("  " + "-" * 100)
    print(f"  {30:>6}  {n_is_base:>5}  {base_is_pnl:>+8.0f}  {n_oos_base:>5}  {base_oos_pnl:>+9.0f}  {'(baseline)':>9}  {'(baseline)':>10}  {'--':>7}  {'--':>5}  {'--':>7}")

    results = []
    for spread in SPREADS:
        if spread == 30:
            continue  # baseline already printed
        cand_is  = _run(spy_df, vix_df, IS_START, IS_END, spread)
        cand_oos = _run(spy_df, vix_df, OOS_START, OOS_END, spread)
        is_pnl   = _pnl(cand_is.trades)
        oos_pnl  = _pnl(cand_oos.trades)
        is_delta  = is_pnl - base_is_pnl
        oos_delta = oos_pnl - base_oos_pnl
        n_is  = len(cand_is.trades)
        n_oos = len(cand_oos.trades)
        wf = (oos_delta / n_oos_base) / (is_delta / n_is_base) if is_delta != 0 else 0.0
        oos_pos = oos_delta > 0
        cand_oos_bd = _by_date(cand_oos.trades)
        anchor = _anchor_ok(cand_oos_bd, base_is_bd)
        oos_s = "YES" if oos_pos else "NO"
        anc_s = "OK" if anchor else "FAIL"
        print(f"  {spread:>6}  {n_is:>5}  {is_pnl:>+8.0f}  {n_oos:>5}  {oos_pnl:>+9.0f}  {is_delta:>+9.0f}  {oos_delta:>+10.0f}  {wf:>7.3f}  {oos_s:>5}  {anc_s:>7}")
        results.append((spread, cand_is, cand_oos, is_delta, oos_delta, wf, oos_pos, anchor))

    # Best candidate analysis
    passing = [(s, ci, co, id_, od, wf, a) for s, ci, co, id_, od, wf, oo_p, a in results if oo_p and od > 0 and wf >= 0.70]
    best_candidates = passing if passing else [(s, ci, co, id_, od, wf, a) for s, ci, co, id_, od, wf, oo_p, a in results if oo_p and od > 0]

    if best_candidates:
        # Use the candidate with best WF if any pass, otherwise best OOS delta
        if passing:
            best = max(passing, key=lambda x: x[5])  # highest WF
        else:
            best = max(best_candidates, key=lambda x: x[4])  # highest OOS delta
        best_spread, best_ci, best_co, best_id, best_od, best_wf, best_anchor = best

        print(f"\n[SUB-WINDOW ANALYSIS: spread={best_spread}c]")
        print(f"  {'Window':20}  {'BASE_n':>6}  {'CAND_n':>6}  {'BASE_pnl':>9}  {'CAND_pnl':>9}  {'delta':>7}  {'verdict':>8}")
        print("  " + "-" * 85)
        sub_hurts = 0
        for label, s, e in IS_SUBWINDOWS:
            b = _run(spy_df, vix_df, s, e, 30)
            c = _run(spy_df, vix_df, s, e, best_spread)
            bp = _pnl(b.trades)
            cp = _pnl(c.trades)
            d = cp - bp
            verdict = "HURT" if d < -100 else ("HELP" if d > 100 else "NEUTRAL")
            if verdict == "HURT":
                sub_hurts += 1
            print(f"  {label:20}  {len(b.trades):>6}  {len(c.trades):>6}  {bp:>+9.0f}  {cp:>+9.0f}  {d:>+7.0f}  {verdict:>8}")
        sub_stable = sub_hurts <= 1

        # Anchor trace
        print(f"\n[ANCHOR TRACE: spread={best_spread}c]")
        base_is_bd_ = _by_date(base_is.trades)
        cand_is_bd  = _by_date(best_ci.trades)
        for d in sorted(J_WINNERS | J_LOSERS):
            bp = base_is_bd_.get(d, 0.0)
            cp = cand_is_bd.get(d, 0.0)
            ok = "OK" if not (bp > 0 and cp < bp * 0.90) else "FAIL"
            tag = " (WINNER)" if d in J_WINNERS else " (LOSER)"
            print(f"  {str(d):12}  base={bp:>+8.0f}  cand={cp:>+8.0f}  {ok}{tag}")

        # Blocked IS trigger breakdown
        print(f"\n[BLOCKED IS TRADES at spread={best_spread}c — trigger breakdown]")
        base_et = set(t.entry_time_et for t in base_is.trades)
        cand_et = set(t.entry_time_et for t in best_ci.trades)
        blocked = [t for t in base_is.trades if t.entry_time_et not in cand_et]
        by_trig_blocked: dict = {}
        for t in blocked:
            k = _trigger_label(t)
            by_trig_blocked.setdefault(k, []).append(t)
        print(f"  Total blocked: n={len(blocked)}")
        for k, ts in sorted(by_trig_blocked.items(), key=lambda x: -len(x[1])):
            n = len(ts); wins = sum(1 for t in ts if t.dollar_pnl > 0); tot = sum(t.dollar_pnl for t in ts)
            print(f"  {k:22}  n={n:>4}  WR={wins/n:.1%}  avg={tot/n:>+.0f}  total={tot:>+.0f}")

        # Blocked OOS trigger breakdown
        print(f"\n[BLOCKED OOS TRADES at spread={best_spread}c — trigger breakdown]")
        base_oos_et = set(t.entry_time_et for t in base_oos.trades)
        cand_oos_et = set(t.entry_time_et for t in best_co.trades)
        blocked_oos = [t for t in base_oos.trades if t.entry_time_et not in cand_oos_et]
        by_trig_blocked_oos: dict = {}
        for t in blocked_oos:
            k = _trigger_label(t)
            by_trig_blocked_oos.setdefault(k, []).append(t)
        print(f"  Total blocked: n={len(blocked_oos)}")
        for k, ts in sorted(by_trig_blocked_oos.items(), key=lambda x: -len(x[1])):
            n = len(ts); wins = sum(1 for t in ts if t.dollar_pnl > 0); tot = sum(t.dollar_pnl for t in ts)
            print(f"  {k:22}  n={n:>4}  WR={wins/n:.1%}  avg={tot/n:>+.0f}  total={tot:>+.0f}")
            for t in sorted(ts, key=lambda x: x.dollar_pnl):
                d = _date(t)
                vix = getattr(t, "entry_vix", None)
                vix_s = f"{vix:.1f}" if vix is not None else "?"
                et = t.entry_time_et
                if getattr(et, "tzinfo", None):
                    et = et.replace(tzinfo=None)
                print(f"    {d}  {str(et.time()):8}  VIX={vix_s}  pnl={t.dollar_pnl:>+7.0f}  exit={getattr(t,'exit_reason','?')}")

        print(f"\n[FINAL VERDICT: spread={best_spread}c]")
        wf_pass = best_wf >= 0.70
        oos_pos_f = best_od > 0
        print(f"  OOS positive:     {oos_pos_f} (delta={best_od:+.0f})")
        print(f"  WF >= 0.70:       {wf_pass} (WF={best_wf:.3f})")
        print(f"  Sub-window stable:{sub_stable} (HURT={sub_hurts})")
        print(f"  Anchor OK:        {best_anchor}")
        all_pass = oos_pos_f and wf_pass and sub_stable and best_anchor
        print(f"\n  VERDICT: {'PASS — file A/B scorecard' if all_pass else 'FAIL — reject'}")
        if all_pass:
            print(f"  RECOMMENDATION: Set ribbon_spread_min_cents={best_spread} in Aggressive params_overrides")
    else:
        print(f"\n  No candidate with OOS positive delta. Baseline 30c confirmed optimal.")
        print(f"  CONCLUSION: ribbon_spread_min_cents increase does not help Aggressive in OOS.")

    print("\nANALYSIS COMPLETE.")
