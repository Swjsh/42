"""
SAFE trendline_requires_ribbon_flip SWEEP (2026-06-17)

NEVER TESTED. Orchestrator comment shows:
  pure trendline_rejection: n=58, WR=27.6%, avg=-$34 -> IS_delta=+1,970 (removes losers)
  ribbon_flip+trendline: n=6, WR=50%, avg=+$312 -> IS_delta kept

This is the ONLY unexplored direction with POSITIVE IS_delta (+$1,970).
C22 risk: OOS trendline_only trades may flip to winners. But IS_delta > 0
means WF formula is well-defined and gate requirement is OOS_delta > $223.

Account: Gamma-Safe-2 only (post-Rank36 baseline IS n=130 pnl=+16,174).
AGG not tested (AGG trendline_only avg=+$1/trade → IS_delta ~0 → WF undefined).

Security: read-only + auto-ratify if gates pass. No Alpaca calls. Free-tier only.
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

# Safe post-Rank36 baseline
SAFE_BASE_KW = dict(
    use_real_fills=True,
    no_trade_window=None,
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
)
SAFE_OVR = {"vix_bull_max": 18.0}


def _run(spy_df, vix_df, start, end, trb=False):
    return run_backtest(
        spy_df, vix_df,
        start_date=start, end_date=end,
        trendline_requires_ribbon_flip=trb,
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


if __name__ == "__main__":
    print("=" * 100)
    print("SAFE trendline_requires_ribbon_flip SWEEP")
    print("IS analysis (from orchestrator comments): pure trendline n=58 WR=27.6% avg=-$34 -> IS_delta=+$1,970")
    print("FIRST TEST OF THIS GATE. POSITIVE IS_delta means WF is well-defined.")
    print("=" * 100)

    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    # Baseline
    print(f"\n[Baseline: trendline_requires_ribbon_flip=False]...")
    b_is  = _run(spy_df, vix_df, IS_START,  IS_END,  False)
    b_oos = _run(spy_df, vix_df, OOS_START, OOS_END, False)
    b_is_pnl  = _pnl(b_is.trades)
    b_oos_pnl = _pnl(b_oos.trades)
    n_is  = len(b_is.trades)
    n_oos = len(b_oos.trades)
    b_is_bd  = _by_date(b_is.trades)
    print(f"  BASELINE: IS n={n_is} pnl={b_is_pnl:+,.0f} | OOS n={n_oos} pnl={b_oos_pnl:+,.0f}")

    # Candidate
    print(f"\n[Candidate: trendline_requires_ribbon_flip=True]...")
    ci  = _run(spy_df, vix_df, IS_START,  IS_END,  True)
    co  = _run(spy_df, vix_df, OOS_START, OOS_END, True)
    ci_pnl = _pnl(ci.trades)
    co_pnl = _pnl(co.trades)
    is_d  = ci_pnl - b_is_pnl
    oos_d = co_pnl - b_oos_pnl
    removed_is  = n_is  - len(ci.trades)
    removed_oos = n_oos - len(co.trades)

    if is_d != 0:
        wf = (oos_d / n_oos) / (is_d / n_is)
    else:
        wf = float("inf") if oos_d > 0 else float("-inf")
    wf_s = f"{wf:.3f}" if abs(wf) < 500 else ("INF+" if wf > 0 else "INF-")

    print(f"  CANDIDATE: IS n={len(ci.trades)} pnl={ci_pnl:+,.0f} | OOS n={len(co.trades)} pnl={co_pnl:+,.0f}")
    print(f"  IS_delta={is_d:+,.0f}  OOS_delta={oos_d:+,.0f}  WF={wf_s}")
    print(f"  Removed from IS: {removed_is} trendline-only trades | Removed from OOS: {removed_oos} trades")

    # Sub-window
    ci_bd = _by_date(ci.trades)
    print(f"\n[Sub-window analysis]")
    print(f"  {'Window':22}  {'BASE_n':>6}  {'CAND_n':>6}  {'BASE_pnl':>10}  "
          f"{'CAND_pnl':>10}  {'delta':>8}  {'verdict':>8}")
    print("  " + "-" * 90)
    sub_hurts = 0
    sw_results = []
    for label, s, e in IS_SUBWINDOWS:
        b = _run(spy_df, vix_df, s, e, False)
        c = _run(spy_df, vix_df, s, e, True)
        bp = _pnl(b.trades); cp = _pnl(c.trades); d = cp - bp
        verdict = "HURT" if d < -100 else ("HELP" if d > 100 else "NEUTRAL")
        if verdict == "HURT": sub_hurts += 1
        print(f"  {label:22}  {len(b.trades):>6}  {len(c.trades):>6}  {bp:>+10,.0f}  "
              f"{cp:>+10,.0f}  {d:>+8,.0f}  {verdict:>8}")
        sw_results.append((label, bp, cp, d, verdict))
    sw_pass = sub_hurts <= 1

    # Anchor
    print(f"\n[Anchor trace]")
    anchor_fails = []
    for d in sorted(J_WINNERS | J_LOSERS):
        bp = b_is_bd.get(d, 0.0); cp = ci_bd.get(d, 0.0)
        fail = bp > 0 and cp < bp * 0.90
        if fail: anchor_fails.append(str(d))
        tag = "(WINNER)" if d in J_WINNERS else "(LOSER)"
        print(f"  {str(d)}  {tag:9}  base={bp:>+8,.0f}  cand={cp:>+8,.0f}  {'FAIL' if fail else 'OK'}")
    anchor_ok = len(anchor_fails) == 0

    oos_pos = oos_d > 0
    wf_pass = wf >= 0.70
    print(f"\n{'='*100}")
    print(f"[VERDICT] Safe trendline_requires_ribbon_flip=True")
    print(f"  OOS positive:      {oos_pos}  (delta={oos_d:+,.0f})")
    print(f"  WF >= 0.70:        {wf_pass}  (WF={wf_s})")
    print(f"  Sub-window stable: {sw_pass}  (HURT={sub_hurts}/4)")
    print(f"  Anchor OK:         {anchor_ok}  (fails={anchor_fails or 'none'})")
    all_pass = oos_pos and wf_pass and sw_pass and anchor_ok
    print(f"\n  >>> {'PASS - AUTO-RATIFYING' if all_pass else 'FAIL - REJECT'} <<<")
    print("=" * 100)

    if all_pass:
        sc_path = ROOT / "analysis" / "recommendations" / "safe-trendline-requires-ribbon-flip.json"
        sc = {
            "rule_id": "safe-trendline-requires-ribbon-flip",
            "param": "trendline_requires_ribbon_flip",
            "candidate": True,
            "account": "Gamma-Safe-2 (PA3S2PYAS2WQ)",
            "ratified_date": "2026-06-17",
            "is_n": n_is, "is_delta": round(is_d, 2),
            "oos_n": n_oos, "oos_delta": round(oos_d, 2),
            "wf_norm": round(wf, 4),
            "oos_positive": True, "sw_hurt": sub_hurts, "sw_pass": sw_pass,
            "anchor_ok": anchor_ok, "anchor_fails": anchor_fails, "all_gates_pass": True,
            "mechanism": (
                "Blocks pure trendline_rejection entries without ribbon_flip co-trigger. "
                "IS analysis (from orchestrator): pure trendline n=58 WR=27.6% avg=-$34 (losers). "
                "ribbon_flip+trendline n=6 WR=50% avg=+$312 (kept). "
                f"IS_delta={is_d:+.0f} (removed {removed_is} IS losers), "
                f"OOS_delta={oos_d:+.0f} (removed {removed_oos} OOS trades)."
            ),
            "sub_windows": [{"label": l, "base_pnl": b, "cand_pnl": c, "delta": d, "verdict": v}
                            for l, b, c, d, v in sw_results],
        }
        sc_path.parent.mkdir(exist_ok=True)
        sc_path.write_text(json.dumps(sc, indent=2), encoding="utf-8")
        print(f"\n[AUTO-RATIFY] Scorecard: {sc_path}")
        params_path = ROOT / "automation" / "state" / "params.json"
        params = json.loads(params_path.read_text(encoding="utf-8-sig"))
        params["trendline_requires_ribbon_flip"] = True
        params["_trendline_ribbon_flip_doc"] = (
            "auto-ratified 2026-06-17: block pure trendline_rejection entries without ribbon_flip. "
            f"IS_delta={is_d:+.0f}, OOS_delta={oos_d:+.0f}, WF={wf_s}."
        )
        params_path.write_text(json.dumps(params, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[AUTO-RATIFY] params.json updated: trendline_requires_ribbon_flip=True")

    print("\nANALYSIS COMPLETE.")
