"""
SAFE_TP1_POST_RANK36

TP1 premium pct sweep for Safe account using the correct post-Rank36 baseline.

Rank-36 (ratified 2026-06-17) raised Safe tp1_premium_pct from 0.30 to 0.50.
IS +3335 / OOS +2172 WF=3.969. Production is now 0.50.

Question: is 0.50 optimal, or does 0.60/0.70/0.75/0.80/0.90 improve further?
Same mechanism as Aggressive: runners exit at ~1x premium (ribbon flip/BE stop), so
capturing more at TP1 is regime-agnostic. BUT the cliff depends on Safe's peak
premium distribution — if trades typically peak 50-69% before reversing, setting
TP1 at 0.70 turns those into full losses.

Gates: OOS_positive AND WF >= 0.70 AND SW_hurt <= 1 AND anchor_OK

Auto-ratify if all gates pass:
  Update automation/state/params.json -> tp1_premium_pct
  File A/B scorecard at analysis/recommendations/safe-tp1-post-rank36.json

Security: read-only except auto-ratify block. No Alpaca calls. Free-tier only.
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

# Full production Safe params (automation/state/params.json, post-Rank36, 2026-06-17)
SAFE_BASE_KW = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=True,
    premium_stop_pct_bear=-0.10,          # Safe: -0.10 (premium_stop_pct_bear in params.json)
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.50,       # Safe: 2.5x runner
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.30,          # Safe: 30% risk
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
)
SAFE_OVR = {"vix_bull_max": 18.0}        # Safe: bull hard cap 18.0 (Rank-35)

BASELINE_TP1 = 0.50   # post-Rank36 production value
TP1_CANDIDATES = [0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 1.00]


def _run(spy_df, vix_df, start, end, tp1_pct):
    return run_backtest(
        spy_df, vix_df,
        start_date=start, end_date=end,
        tp1_premium_pct=tp1_pct,
        params_overrides=dict(SAFE_OVR),
        **SAFE_BASE_KW,
    )


def _pnl(trades):
    return sum(t.dollar_pnl for t in trades)


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
    print("SAFE TP1_PREMIUM_PCT SWEEP (post-Rank36 baseline = 0.50)")
    print(f"Gates: OOS_positive AND WF>=0.70 AND SW_hurt<=1 AND anchor_OK")
    print("=" * 100)

    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    # Baseline
    print(f"\n[Running baseline at tp1={BASELINE_TP1}]...")
    base_is  = _run(spy_df, vix_df, IS_START,  IS_END,  BASELINE_TP1)
    base_oos = _run(spy_df, vix_df, OOS_START, OOS_END, BASELINE_TP1)
    base_is_pnl  = _pnl(base_is.trades)
    base_oos_pnl = _pnl(base_oos.trades)
    n_is  = len(base_is.trades)
    n_oos = len(base_oos.trades)
    base_is_bd = _by_date(base_is.trades)
    print(f"  BASELINE: IS n={n_is} pnl={base_is_pnl:+,.0f} | OOS n={n_oos} pnl={base_oos_pnl:+,.0f}")

    # OOS exit breakdown at baseline
    print(f"\n  OOS exit breakdown at baseline (tp1={BASELINE_TP1}):")
    by_exit = {}
    for t in base_oos.trades:
        k = str(getattr(t, "exit_reason", "?") or "?")
        by_exit.setdefault(k, []).append(t)
    for k, ts in sorted(by_exit.items(), key=lambda x: -sum(t.dollar_pnl for t in x[1])):
        n = len(ts); wins = sum(1 for t in ts if t.dollar_pnl > 0); tot = sum(t.dollar_pnl for t in ts)
        print(f"    {k:40}  n={n:>4}  WR={wins/n:.1%}  avg={tot/n:>+.0f}  total={tot:>+.0f}")

    # Runner exit premium distribution
    print(f"\n  OOS winner exit premiums (base vs entry):")
    wins_oos = [t for t in base_oos.trades if t.dollar_pnl > 0]
    for t in sorted(wins_oos, key=lambda x: -x.dollar_pnl)[:10]:
        ep = t.entry_premium
        rp = t.runner_exit_premium
        ratio_s = f"{rp/ep:.2f}x" if rp and ep else "N/A"
        print(f"    {_date(t)}  entry={ep:.2f}  runner_exit={rp:.2f}  ratio={ratio_s}  pnl={t.dollar_pnl:+.0f}  {getattr(t,'exit_reason','?')}")

    # Sweep
    print(f"\n[TP1 SWEEP vs baseline {BASELINE_TP1}]")
    print(f"  {'TP1':>5}  {'IS_n':>5}  {'IS_pnl':>9}  {'OOS_n':>5}  {'OOS_pnl':>9}  {'IS_delta':>9}  {'OOS_delta':>10}  {'WF':>7}  {'OOS+':>5}  {'VERDICT'}")
    print("  " + "-" * 105)
    print(f"  {BASELINE_TP1:>5.2f}  {n_is:>5}  {base_is_pnl:>+9,.0f}  {n_oos:>5}  {base_oos_pnl:>+9,.0f}  {'(base)':>9}  {'(base)':>10}  {'--':>7}  {'--':>5}  BASELINE")

    results = []
    for tp1 in TP1_CANDIDATES:
        cand_is  = _run(spy_df, vix_df, IS_START,  IS_END,  tp1)
        cand_oos = _run(spy_df, vix_df, OOS_START, OOS_END, tp1)
        is_pnl  = _pnl(cand_is.trades)
        oos_pnl = _pnl(cand_oos.trades)
        is_d  = is_pnl  - base_is_pnl
        oos_d = oos_pnl - base_oos_pnl
        wf = (oos_d / n_oos) / (is_d / n_is) if is_d != 0 else float("inf") if oos_d > 0 else float("-inf")
        oos_pos = oos_d > 0
        wf_pass = wf >= 0.70
        wf_s = f"{wf:.3f}" if abs(wf) < 200 else ("INF+" if wf > 0 else "INF-")
        verdict = "CANDIDATE" if oos_pos and wf_pass else ("OOS+" if oos_pos else "OOS-")
        print(f"  {tp1:>5.2f}  {len(cand_is.trades):>5}  {is_pnl:>+9,.0f}  {len(cand_oos.trades):>5}  {oos_pnl:>+9,.0f}  {is_d:>+9,.0f}  {oos_d:>+10,.0f}  {wf_s:>7}  {'YES' if oos_pos else 'NO':>5}  {verdict}")
        results.append((tp1, cand_is, cand_oos, is_d, oos_d, wf, oos_pos, wf_pass))

    # Best passing candidate: highest OOS_delta among OOS+ with WF>=0.70
    passing = [(tp1, ci, co, id_, od, wf) for tp1, ci, co, id_, od, wf, oo_p, wf_p in results if oo_p and wf_p]
    if not passing:
        # Fall back to OOS+ only
        passing = [(tp1, ci, co, id_, od, wf) for tp1, ci, co, id_, od, wf, oo_p, _ in results if oo_p]

    if not passing:
        print(f"\n  No OOS-positive candidate. Baseline {BASELINE_TP1} CONFIRMED OPTIMAL.")
    else:
        # Pick highest OOS delta
        best = max(passing, key=lambda x: x[4])
        best_tp1, best_ci, best_co, best_id, best_od, best_wf = best

        print(f"\n[Sub-window analysis: tp1={best_tp1}]")
        print(f"  {'Window':22}  {'BASE_n':>6}  {'CAND_n':>6}  {'BASE_pnl':>10}  {'CAND_pnl':>10}  {'delta':>8}  {'verdict':>8}")
        print("  " + "-" * 90)
        sub_hurts = 0
        sw_results = []
        for label, s, e in IS_SUBWINDOWS:
            b = _run(spy_df, vix_df, s, e, BASELINE_TP1)
            c = _run(spy_df, vix_df, s, e, best_tp1)
            bp = _pnl(b.trades)
            cp = _pnl(c.trades)
            d = cp - bp
            verdict = "HURT" if d < -100 else ("HELP" if d > 100 else "NEUTRAL")
            if verdict == "HURT":
                sub_hurts += 1
            print(f"  {label:22}  {len(b.trades):>6}  {len(c.trades):>6}  {bp:>+10,.0f}  {cp:>+10,.0f}  {d:>+8,.0f}  {verdict:>8}")
            sw_results.append((label, bp, cp, d, verdict))
        sw_pass = sub_hurts <= 1

        # Anchor trace
        print(f"\n[Anchor trace: tp1={best_tp1}]")
        cand_is_bd = _by_date(best_ci.trades)
        anchor_fails = []
        for d in sorted(J_WINNERS | J_LOSERS):
            bp = base_is_bd.get(d, 0.0)
            cp = cand_is_bd.get(d, 0.0)
            fail = bp > 0 and cp < bp * 0.90
            if fail:
                anchor_fails.append(str(d))
            tag = "(WINNER)" if d in J_WINNERS else "(LOSER)"
            print(f"  {str(d)}  {tag:9}  base={bp:>+8,.0f}  cand={cp:>+8,.0f}  {'FAIL' if fail else 'OK'}")
        anchor_ok = len(anchor_fails) == 0

        # Verdict
        wf_s = f"{best_wf:.3f}" if abs(best_wf) < 200 else ("INF+" if best_wf > 0 else "INF-")
        oos_pos_f = best_od > 0
        wf_pass_f = best_wf >= 0.70
        print(f"\n{'='*100}")
        print(f"[FINAL VERDICT] SAFE tp1_premium_pct: {BASELINE_TP1} -> {best_tp1}")
        print(f"  OOS positive:      {oos_pos_f}  (delta={best_od:+,.0f})")
        print(f"  WF >= 0.70:        {wf_pass_f}  (WF={wf_s})")
        print(f"  Sub-window stable: {sw_pass}  (HURT={sub_hurts}/4)")
        print(f"  Anchor OK:         {anchor_ok}  (fails={anchor_fails or 'none'})")
        all_pass = oos_pos_f and wf_pass_f and sw_pass and anchor_ok
        print(f"\n  >>> {'PASS — AUTO-RATIFYING' if all_pass else 'FAIL — REJECT'} <<<")
        print(f"{'='*100}")

        if all_pass:
            scorecard_path = ROOT / "analysis" / "recommendations" / "safe-tp1-post-rank36.json"
            scorecard = {
                "rule_id": "safe-tp1-post-rank36",
                "param": "tp1_premium_pct",
                "baseline": BASELINE_TP1,
                "candidate": best_tp1,
                "account": "Gamma-Safe-2 (PA3S2PYAS2WQ)",
                "ratified_date": "2026-06-17",
                "is_n": n_is,
                "is_baseline_pnl": base_is_pnl,
                "is_candidate_pnl": _pnl(best_ci.trades),
                "is_delta": best_id,
                "oos_n": n_oos,
                "oos_baseline_pnl": base_oos_pnl,
                "oos_candidate_pnl": _pnl(best_co.trades),
                "oos_delta": best_od,
                "wf_norm": round(best_wf, 4) if abs(best_wf) < 1000 else best_wf,
                "oos_positive": True,
                "sw_hurt": sub_hurts,
                "sw_pass": sw_pass,
                "anchor_ok": anchor_ok,
                "anchor_fails": anchor_fails,
                "all_gates_pass": True,
                "sub_windows": [
                    {"label": lbl, "base_pnl": bp, "cand_pnl": cp, "delta": d, "verdict": v}
                    for lbl, bp, cp, d, v in sw_results
                ],
            }
            scorecard_path.parent.mkdir(exist_ok=True)
            scorecard_path.write_text(json.dumps(scorecard, indent=2))
            print(f"\n[AUTO-RATIFY] Scorecard: {scorecard_path}")

            # Update params.json
            params_path = ROOT / "automation" / "state" / "params.json"
            params = json.loads(params_path.read_text())
            old_val = params.get("tp1_premium_pct", "N/A")
            params["tp1_premium_pct"] = best_tp1
            old_doc = params.get("_exits_section", "")
            params["_exits_section"] = (
                old_doc.rstrip() +
                f" Post-Rank36: tp1_premium_pct raised {BASELINE_TP1}->{best_tp1} (safe-tp1-post-rank36.json, 2026-06-17)."
            )
            params_path.write_text(json.dumps(params, indent=2))
            print(f"[AUTO-RATIFY] params.json tp1_premium_pct: {old_val} -> {best_tp1}")
        else:
            print(f"\n  Baseline {BASELINE_TP1} CONFIRMED OPTIMAL for Safe account.")

    print("\nANALYSIS COMPLETE.")
