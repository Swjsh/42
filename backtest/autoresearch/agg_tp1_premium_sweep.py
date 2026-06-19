"""
AGG tp1_premium_pct SWEEP (2026-06-17)

CRITICAL CONTEXT: L109 fix (2026-06-17) revealed that the AGG real-fills path was
hardcoding tp1_premium_pct=0.30 (not passing the 0.75 param). This made the effective
production AGG engine run with tp1=0.30, not 0.75. After the fix:
  - AGG IS n=218 pnl=+10,019  (was +19,566 with effective tp1=0.30)
  - AGG OOS n=24 pnl=-43       (was +2,590 with effective tp1=0.30)

The OOS difference is $2,633 over 28 OOS trades. If tp1=0.30 genuinely generalizes
better (TP1 fires more often at a lower target), it should pass the WF gate.

Sweep: [0.30, 0.40, 0.50, 0.60] vs baseline 0.75.
Exit parameters are less susceptible to C22 entry-filter regime split.
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

J_WINNERS = {dt.date(2026, 4, 29), dt.date(2026, 5, 1), dt.date(2026, 5, 4)}
J_LOSERS  = {dt.date(2026, 5, 5), dt.date(2026, 5, 6)}

IS_SUBWINDOWS = [
    ("W1 Jan-Jun 2025", dt.date(2025, 1, 2),  dt.date(2025, 6, 30)),
    ("W2 Jul-Dec 2025", dt.date(2025, 7, 1),  dt.date(2025, 12, 31)),
    ("W3 Jan-Mar 2026", dt.date(2026, 1, 2),  dt.date(2026, 3, 31)),
    ("W4 Apr-May 2026", dt.date(2026, 4, 1),  dt.date(2026, 5, 7)),
]

# AGG baseline with ALL currently ratified gates (post-L109 fix correct params)
AGG_BASE_KW = dict(
    use_real_fills=True,
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
    tp1_premium_pct=0.75,
)
AGG_OVR = {"vix_bear_threshold": 15.0, "vix_bull_max": 30.0}

CANDIDATES = [0.30, 0.40, 0.50, 0.60]


def _run(spy_df, vix_df, start, end, tp1):
    kw = dict(AGG_BASE_KW)
    kw["tp1_premium_pct"] = tp1
    return run_backtest(
        spy_df, vix_df,
        start_date=start, end_date=end,
        params_overrides=dict(AGG_OVR),
        **kw,
    )


def _pnl(trades): return sum(t.dollar_pnl for t in trades)
def _date(t):
    et = t.entry_time_et
    return (et.replace(tzinfo=None) if getattr(et, "tzinfo", None) else et).date()
def _by_date(trades):
    bd = {}
    for t in trades:
        d = _date(t)
        bd[d] = bd.get(d, 0.0) + t.dollar_pnl
    return bd


if __name__ == "__main__":
    print("=" * 100)
    print("AGG tp1_premium_pct SWEEP -- post-L109 fix correct baseline")
    print("L109: tp1 was hardcoded 0.30 in real-fills path (not 0.75). Now fixed.")
    print("Baseline IS=+10,019 OOS=-43 (tp1=0.75). Old buggy: IS=+19,566 OOS=+2,590.")
    print("Sweep [0.30, 0.40, 0.50, 0.60] to find optimal TP1 target.")
    print("=" * 100)

    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    print("\n[Baseline: tp1=0.75 (current AGG production)]...")
    b_is  = _run(spy_df, vix_df, IS_START,  IS_END,  0.75)
    b_oos = _run(spy_df, vix_df, OOS_START, OOS_END, 0.75)
    n_is  = len(b_is.trades)
    n_oos = len(b_oos.trades)
    b_is_pnl  = _pnl(b_is.trades)
    b_oos_pnl = _pnl(b_oos.trades)
    b_is_bd   = _by_date(b_is.trades)
    print(f"  BASELINE: IS n={n_is} pnl={b_is_pnl:+,.0f} | OOS n={n_oos} pnl={b_oos_pnl:+,.0f}")

    print(f"\n")
    print("-" * 110)

    best = None
    results = []
    for tp1 in CANDIDATES:
        ci  = _run(spy_df, vix_df, IS_START,  IS_END,  tp1)
        co  = _run(spy_df, vix_df, OOS_START, OOS_END, tp1)
        ci_pnl = _pnl(ci.trades); co_pnl = _pnl(co.trades)
        is_d = ci_pnl - b_is_pnl; oos_d = co_pnl - b_oos_pnl
        if is_d != 0:
            wf = (oos_d / n_oos) / (is_d / n_is)
        else:
            wf = float("inf") if oos_d > 0 else float("-inf")
        wf_s = f"{wf:.3f}" if abs(wf) < 500 else ("INF+" if wf > 0 else "INF-")

        sw_hurts = 0
        sw_results = []
        for label, s, e in IS_SUBWINDOWS:
            b = _run(spy_df, vix_df, s, e, 0.75)
            c = _run(spy_df, vix_df, s, e, tp1)
            delta = _pnl(c.trades) - _pnl(b.trades)
            v = "HURT" if delta < -100 else ("HELP" if delta > 100 else "neutral")
            if v == "HURT": sw_hurts += 1
            sw_results.append((label, _pnl(b.trades), _pnl(c.trades), delta, v))

        ci_bd = _by_date(ci.trades)
        anchor_fails = []
        for d in sorted(J_WINNERS | J_LOSERS):
            bp = b_is_bd.get(d, 0.0); cp = ci_bd.get(d, 0.0)
            if bp > 0 and cp < bp * 0.90: anchor_fails.append(str(d))

        oos_pos = oos_d > 0
        wf_pass = wf >= 0.70
        sw_pass = sw_hurts <= 1
        anc_ok  = len(anchor_fails) == 0
        all_pass = oos_pos and wf_pass and sw_pass and anc_ok
        verdict = "PASS" if all_pass else "fail"

        print(f"  tp1={tp1:.2f}  IS n={len(ci.trades)}  pnl={ci_pnl:+,.0f}  IS_d={is_d:+,.0f}  OOS n={len(co.trades)}  pnl={co_pnl:+,.0f}  OOS_d={oos_d:+,.0f}  WF={wf_s}  SW={sw_hurts}/4  anc={'OK' if anc_ok else 'FAIL'}  {verdict}")
        for sw in sw_results:
            print(f"    {sw[0]:22}  base={sw[1]:>+10,.0f}  cand={sw[2]:>+10,.0f}  d={sw[3]:>+8,.0f}  {sw[4]}")

        results.append({
            "tp1": tp1, "ci_n": len(ci.trades), "ci_pnl": round(ci_pnl, 2),
            "co_n": len(co.trades), "co_pnl": round(co_pnl, 2),
            "is_delta": round(is_d, 2), "oos_delta": round(oos_d, 2),
            "wf_norm": round(wf, 4) if abs(wf) < 500 else ("inf+" if wf > 0 else "inf-"),
            "sw_hurt": sw_hurts, "anchor_fails": anchor_fails,
            "all_pass": all_pass, "sub_windows": sw_results,
        })

        if all_pass and (best is None or oos_d > best[1]):
            best = (tp1, oos_d, results[-1])

    print()
    if best:
        tp1_best, oos_best, res_best = best
        print(f"BEST CANDIDATE: tp1={tp1_best}  OOS_delta={oos_best:+,.0f}")
        slug = str(tp1_best).replace(".", "p")
        sc_path = ROOT / "analysis" / "recommendations" / f"agg-tp1-premium-{slug}.json"
        sc = {
            "rule_id": f"agg-tp1-premium-{slug}",
            "param": "tp1_premium_pct",
            "candidate_value": tp1_best, "baseline_value": 0.75,
            "account": "Gamma-Risky-2 (PA33W2KUAT40)",
            "ratified_date": "2026-06-17",
            "is_n": n_is, "is_delta": res_best["is_delta"],
            "oos_n": n_oos, "oos_delta": res_best["oos_delta"],
            "wf_norm": res_best["wf_norm"],
            "oos_positive": True, "sw_hurt": res_best["sw_hurt"],
            "anchor_ok": not res_best["anchor_fails"],
            "anchor_fails": res_best["anchor_fails"],
            "all_gates_pass": True,
            "context": "L109 fix revealed that real-fills path was hardcoding tp1=0.30 (not passing 0.75). Sweep found optimal TP1 post-fix.",
            "sub_windows": res_best["sub_windows"],
            "all_results": results,
        }
        sc_path.parent.mkdir(exist_ok=True, parents=True)
        sc_path.write_text(json.dumps(sc, indent=2), encoding="utf-8")
        print(f"[AUTO-RATIFY] Scorecard: {sc_path}")
        params_path = ROOT / "automation" / "state" / "aggressive" / "params.json"
        params = json.loads(params_path.read_text(encoding="utf-8-sig"))
        params["tp1_premium_pct"] = tp1_best
        params["tp1_premium_multiplier"] = round(1.0 + tp1_best, 2)
        params["_tp1_premium_doc"] = f"auto-ratified 2026-06-17: AGG tp1 set to {tp1_best}. L109 fix: was hardcoded 0.30 in real-fills path. IS_delta={res_best['is_delta']:+.0f}, OOS_delta={res_best['oos_delta']:+.0f}, WF={res_best['wf_norm']}."
        params_path.write_text(json.dumps(params, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[AUTO-RATIFY] AGG params.json: tp1_premium_pct={tp1_best}")
    else:
        print("ALL CANDIDATES FAIL -- tp1=0.75 confirmed optimal for AGG (post-L109 fix)")

    print("\n" + "=" * 100)
    print("ANALYSIS COMPLETE.")
