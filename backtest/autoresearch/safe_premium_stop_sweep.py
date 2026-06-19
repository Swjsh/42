"""
SAFE premium_stop_pct_bear SWEEP (2026-06-17)

Kitchen candidate: SAFE_ACCOUNT_PREMIUM_STOP_SWEEP (confidence 6/10)
Hypothesis: AGG ratified -0.07 stop. Safe uses -0.10. OTM-2 strikes (lower delta)
may benefit from tighter stop (-0.07/-0.08) or looser stop (-0.12/-0.15).

Note: this is an EXIT parameter, less susceptible to C22 entry-filter regime split.
Safe post-L109 baseline confirmed: IS n=130 pnl=+16,174 | OOS n=21 pnl=+5,900.

Security: read-only + auto-ratify if gates pass. No Alpaca calls.
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

SAFE_BASE_KW = dict(
    use_real_fills=True,
    no_trade_window=(dt.time(11, 30), dt.time(12, 0)),   # ENFORCED-4
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
    block_conf_lvl_rec_afternoon=True,                    # ENFORCED-1
)
SAFE_OVR = {"vix_bull_max": 18.0}

# Production=-0.10. Tighter candidates: -0.07/-0.08/-0.09. Looser: -0.12.
CANDIDATES = [-0.07, -0.08, -0.09, -0.11, -0.12]


def _run(spy_df, vix_df, start, end, stop):
    kw = dict(SAFE_BASE_KW)
    kw["premium_stop_pct_bear"] = stop
    return run_backtest(
        spy_df, vix_df,
        start_date=start, end_date=end,
        params_overrides=dict(SAFE_OVR),
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
    print("SAFE premium_stop_pct_bear SWEEP")
    print("Baseline: -0.10. Confirmed IS=+16,174 OOS=+5,900 (post-L109 correct params).")
    print("Candidates: [-0.07, -0.08, -0.12, -0.15]. AGG ratified -0.07 (WF=0.725).")
    print("=" * 100)

    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    print("\n[Baseline: premium_stop=-0.10]...")
    b_is  = _run(spy_df, vix_df, IS_START,  IS_END,  -0.10)
    b_oos = _run(spy_df, vix_df, OOS_START, OOS_END, -0.10)
    n_is  = len(b_is.trades)
    n_oos = len(b_oos.trades)
    b_is_pnl  = _pnl(b_is.trades)
    b_oos_pnl = _pnl(b_oos.trades)
    b_is_bd   = _by_date(b_is.trades)
    print(f"  BASELINE: IS n={n_is} pnl={b_is_pnl:+,.0f} | OOS n={n_oos} pnl={b_oos_pnl:+,.0f}")

    best = None
    results = []
    for stop in CANDIDATES:
        ci  = _run(spy_df, vix_df, IS_START,  IS_END,  stop)
        co  = _run(spy_df, vix_df, OOS_START, OOS_END, stop)
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
            b = _run(spy_df, vix_df, s, e, -0.10)
            c = _run(spy_df, vix_df, s, e, stop)
            delta = _pnl(c.trades) - _pnl(b.trades)
            v = "HURT" if delta < -500 else ("HELP" if delta > 100 else "neutral")
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

        print(f"\n  stop={stop:.2f}  IS n={len(ci.trades)} pnl={ci_pnl:+,.0f}  IS_d={is_d:+,.0f}  OOS n={len(co.trades)} pnl={co_pnl:+,.0f}  OOS_d={oos_d:+,.0f}  WF={wf_s}  SW={sw_hurts}/4  anc={'OK' if anc_ok else 'FAIL'}  >>> {verdict} <<<")
        for sw in sw_results:
            print(f"    {sw[0]:22}  base={sw[1]:>+10,.0f}  cand={sw[2]:>+10,.0f}  d={sw[3]:>+8,.0f}  {sw[4]}")

        results.append({
            "stop": stop, "ci_n": len(ci.trades), "ci_pnl": round(ci_pnl, 2),
            "co_n": len(co.trades), "co_pnl": round(co_pnl, 2),
            "is_delta": round(is_d, 2), "oos_delta": round(oos_d, 2),
            "wf_norm": round(wf, 4) if abs(wf) < 500 else ("inf+" if wf > 0 else "inf-"),
            "sw_hurt": sw_hurts, "anchor_fails": anchor_fails,
            "all_pass": all_pass, "sub_windows": sw_results,
        })

        if all_pass and (best is None or oos_d > best[1]):
            best = (stop, oos_d, results[-1])

    print()
    if best:
        stop_best, oos_best, res_best = best
        print(f"BEST CANDIDATE: stop={stop_best}  OOS_delta={oos_best:+,.0f}")
        slug = str(stop_best).replace("-", "neg").replace(".", "p")
        sc_path = ROOT / "analysis" / "recommendations" / f"safe-premium-stop-{slug}.json"
        sc = {
            "rule_id": f"safe-premium-stop-{slug}",
            "param": "premium_stop_pct_bear",
            "candidate_value": stop_best, "baseline_value": -0.10,
            "account": "Gamma-Safe-2 (PA3S2PYAS2WQ)",
            "ratified_date": "2026-06-17",
            "is_n": n_is, "is_delta": res_best["is_delta"],
            "oos_n": n_oos, "oos_delta": res_best["oos_delta"],
            "wf_norm": res_best["wf_norm"],
            "oos_positive": True, "sw_hurt": res_best["sw_hurt"],
            "anchor_ok": not res_best["anchor_fails"],
            "anchor_fails": res_best["anchor_fails"],
            "all_gates_pass": True,
            "mechanism": f"Safe premium_stop changed from -0.10 to {stop_best}. AGG precedent: -0.07 ratified (WF=0.725). OTM-2 vs ITM-2 stop dynamics. IS_delta={res_best['is_delta']:+.0f}, OOS_delta={res_best['oos_delta']:+.0f}, WF={res_best['wf_norm']}.",
            "sub_windows": res_best["sub_windows"],
            "all_results": results,
        }
        sc_path.parent.mkdir(exist_ok=True, parents=True)
        sc_path.write_text(json.dumps(sc, indent=2), encoding="utf-8")
        print(f"[AUTO-RATIFY] Scorecard: {sc_path}")
        params_path = ROOT / "automation" / "state" / "params.json"
        params = json.loads(params_path.read_text(encoding="utf-8-sig"))
        params["premium_stop_pct_bear"] = stop_best
        params["premium_stop_multiplier"] = round(1.0 + stop_best, 2)
        params["_premium_stop_pct_bear_doc"] = f"auto-ratified 2026-06-17: Safe bear stop changed {PRODUCTION_STOP} -> {stop_best}. IS_delta={res_best['is_delta']:+.0f}, OOS_delta={res_best['oos_delta']:+.0f}, WF={res_best['wf_norm']}."
        params_path.write_text(json.dumps(params, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[AUTO-RATIFY] Safe params.json updated: premium_stop_pct_bear={stop_best}")
    else:
        print("ALL CANDIDATES FAIL -- premium_stop=-0.10 confirmed optimal for Safe")

    print("\n" + "=" * 100)
    print("ANALYSIS COMPLETE.")
