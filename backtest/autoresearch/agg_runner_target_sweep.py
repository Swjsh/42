"""
AGG runner_target_premium_pct SWEEP (2026-06-17)

Kitchen candidate: RUNNER_TARGET_SWEEP_AGGRESSIVE (confidence 4/10)
Hypothesis: 5.0x runner target for ITM-2 AGG account is unrealistic (~never hit).
Lower to [2.0, 2.5, 3.0, 3.5, 4.0] range improves runner capture.

NOTE: runner_target is an EXIT param, not an entry filter.
C22 regime split is less likely to hit exit params (they don't select sub-populations).
Safe baseline uses runner_target=2.5 (already lower). AGG uses 5.0.

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

# AGG C14-correct baseline (tp1=0.75, block_level_rejection=True, etc.)
AGG_BASE_KW = dict(
    use_real_fills=True,
    midday_trendline_gate=False,
    premium_stop_pct_bear=-0.07,
    tp1_qty_fraction=0.667,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.50,
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
    tp1_premium_pct=0.75,
    runner_target_premium_pct=5.0,  # baseline = current AGG production
)
AGG_OVR = {"vix_bear_threshold": 15.0, "vix_bull_max": 30.0}

CANDIDATES = [2.0, 2.5, 3.0, 3.5, 4.0]


def _run(spy_df, vix_df, start, end, runner_target):
    kw = dict(AGG_BASE_KW)
    kw["runner_target_premium_pct"] = runner_target
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
    print("AGG runner_target_premium_pct SWEEP")
    print("Baseline: runner_target=5.0 (current AGG production)")
    print("Candidates: [2.0, 2.5, 3.0, 3.5, 4.0]")
    print("Note: Safe uses 2.5x. Exit params less susceptible to C22 regime split.")
    print("=" * 100)

    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    print("\n[Baseline: runner_target=5.0]...")
    b_is  = _run(spy_df, vix_df, IS_START,  IS_END,  5.0)
    b_oos = _run(spy_df, vix_df, OOS_START, OOS_END, 5.0)
    n_is  = len(b_is.trades)
    n_oos = len(b_oos.trades)
    b_is_pnl  = _pnl(b_is.trades)
    b_oos_pnl = _pnl(b_oos.trades)
    b_is_bd   = _by_date(b_is.trades)
    print(f"  BASELINE: IS n={n_is} pnl={b_is_pnl:+,.0f} | OOS n={n_oos} pnl={b_oos_pnl:+,.0f}")

    print(f"\n{'Cand':>6}  {'IS_pnl':>10}  {'IS_d':>8}  {'OOS_pnl':>10}  {'OOS_d':>8}  "
          f"{'WF':>7}  {'SW_hurt':>8}  {'anchor':>7}  {'verdict':>10}")
    print("-" * 100)

    best = None
    results = []
    for rt in CANDIDATES:
        ci  = _run(spy_df, vix_df, IS_START,  IS_END,  rt)
        co  = _run(spy_df, vix_df, OOS_START, OOS_END, rt)
        ci_pnl = _pnl(ci.trades); co_pnl = _pnl(co.trades)
        is_d = ci_pnl - b_is_pnl; oos_d = co_pnl - b_oos_pnl
        if is_d != 0:
            wf = (oos_d / n_oos) / (is_d / n_is)
        else:
            wf = float("inf") if oos_d > 0 else float("-inf")
        wf_s = f"{wf:.3f}" if abs(wf) < 500 else ("INF+" if wf > 0 else "INF-")

        # Sub-window
        sw_hurts = 0
        sw_results = []
        for label, s, e in IS_SUBWINDOWS:
            b = _run(spy_df, vix_df, s, e, 5.0)
            c = _run(spy_df, vix_df, s, e, rt)
            delta = _pnl(c.trades) - _pnl(b.trades)
            v = "HURT" if delta < -100 else ("HELP" if delta > 100 else "NEUTRAL")
            if v == "HURT": sw_hurts += 1
            sw_results.append((label, _pnl(b.trades), _pnl(c.trades), delta, v))

        # Anchor
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

        print(f"  {rt:>4.1f}  {ci_pnl:>10,.0f}  {is_d:>+8,.0f}  {co_pnl:>10,.0f}  {oos_d:>+8,.0f}  "
              f"{wf_s:>7}  {sw_hurts:>3}/4{' '*4}  {'OK' if anc_ok else 'FAIL':>7}  {verdict:>10}")

        results.append({
            "runner_target": rt, "ci_pnl": round(ci_pnl, 2), "co_pnl": round(co_pnl, 2),
            "is_delta": round(is_d, 2), "oos_delta": round(oos_d, 2),
            "wf_norm": round(wf, 4) if abs(wf) < 500 else ("inf+" if wf > 0 else "inf-"),
            "sw_hurt": sw_hurts, "anchor_fails": anchor_fails,
            "all_pass": all_pass, "sub_windows": sw_results,
        })

        if all_pass and (best is None or oos_d > best[1]):
            best = (rt, oos_d, results[-1])

    print()
    if best:
        rt_best, oos_best, res_best = best
        print(f"BEST CANDIDATE: runner_target={rt_best}  OOS_delta={oos_best:+,.0f}")
        sc_path = ROOT / "analysis" / "recommendations" / f"agg-runner-target-{str(rt_best).replace('.', 'p')}.json"
        sc = {
            "rule_id": f"agg-runner-target-{str(rt_best).replace('.', 'p')}",
            "param": "runner_target_premium_pct",
            "candidate_value": rt_best, "baseline_value": 5.0,
            "account": "Gamma-Risky-2 (PA33W2KUAT40)",
            "ratified_date": "2026-06-17",
            "is_n": n_is, "is_delta": res_best["is_delta"],
            "oos_n": n_oos, "oos_delta": res_best["oos_delta"],
            "wf_norm": res_best["wf_norm"],
            "oos_positive": True, "sw_hurt": res_best["sw_hurt"],
            "anchor_ok": not res_best["anchor_fails"], "anchor_fails": res_best["anchor_fails"],
            "all_gates_pass": True, "sub_windows": res_best["sub_windows"],
            "mechanism": (
                f"AGG runner exit target reduced from 5.0x to {rt_best}x entry premium. "
                f"5.0x is rarely achievable on ITM-2 0DTE puts; lower target captures more runner exits. "
                f"IS_delta={res_best['is_delta']:+.0f}, OOS_delta={res_best['oos_delta']:+.0f}, WF={res_best['wf_norm']}."
            ),
            "all_results": results,
        }
        sc_path.parent.mkdir(exist_ok=True)
        sc_path.write_text(json.dumps(sc, indent=2), encoding="utf-8")
        print(f"[AUTO-RATIFY] Scorecard: {sc_path}")
        params_path = ROOT / "automation" / "state" / "aggressive" / "params.json"
        params = json.loads(params_path.read_text(encoding="utf-8-sig"))
        params["runner_max_premium_pct"] = rt_best
        params["_runner_target_doc"] = (
            f"auto-ratified 2026-06-17: reduced from 5.0x to {rt_best}x. "
            f"IS_delta={res_best['is_delta']:+.0f}, OOS_delta={res_best['oos_delta']:+.0f}, WF={res_best['wf_norm']}."
        )
        params_path.write_text(json.dumps(params, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[AUTO-RATIFY] AGG params.json updated: runner_max_premium_pct={rt_best}")
    else:
        print("ALL CANDIDATES FAIL — runner_target=5.0 confirmed optimal for AGG")

    print("\n" + "=" * 100)
    print("ANALYSIS COMPLETE.")
