"""
AGG_INCLUDE_FIRST_HOUR_HIGH (Rank 27 — Aggressive account)

Orchestrator.py:
  include_first_hour_high=True: adds max(09:30-09:55 bars high) to levels_active after 10:05 ET.
  Motivation: 5/01 11:50 BEARISH_REVERSAL blocked because 724.24 not in level set.

For Aggressive account (all-bear, VIX-conditional):
  First-hour RTH high is a natural intraday resistance level.
  If SPY spends the morning trending up and forms a local high in the first 30 mins,
  then rejects that level later in the day, it would trigger BEARISH_REJECTION_RIDE_THE_RIBBON.
  This gate unlocks those entries.

New entries will fire when:
  (1) SPY forms a high between 09:30-09:55 ET
  (2) After 10:05 ET, SPY rises back to that level and rejects it
  (3) All other BEARISH_REJECTION filters pass (ribbon, VIX, etc.)

Hypothesis: adds quality level-rejection entries on high-momentum open days.

Gates: OOS_positive AND WF >= 0.70 AND SW_hurt <= 1 AND anchor_OK

Security: read-only + auto-ratify if passes. No Alpaca calls. Free-tier only.
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

# Full production Aggressive params (post-Rank35 + TIGHTER_STOP_2 + Rank36 baseline)
AGG_BASE_KW = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=False,
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
)
AGG_OVR = {"vix_bear_threshold": 15.0, "vix_bull_max": 30.0}


def _run(spy_df, vix_df, start, end, use_fhh):
    return run_backtest(
        spy_df, vix_df,
        start_date=start, end_date=end,
        include_first_hour_high=use_fhh,
        params_overrides=dict(AGG_OVR),
        **AGG_BASE_KW,
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
    print("AGG INCLUDE_FIRST_HOUR_HIGH (Rank 27 — Aggressive account)")
    print("Adds max(09:30-09:55 high) to levels_active after 10:05 ET")
    print("=" * 100)

    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    # Baseline
    print(f"\n[Baseline (include_first_hour_high=False)]...")
    base_is  = _run(spy_df, vix_df, IS_START,  IS_END,  False)
    base_oos = _run(spy_df, vix_df, OOS_START, OOS_END, False)
    base_is_pnl  = _pnl(base_is.trades)
    base_oos_pnl = _pnl(base_oos.trades)
    n_is  = len(base_is.trades)
    n_oos = len(base_oos.trades)
    base_is_bd = _by_date(base_is.trades)
    print(f"  BASELINE: IS n={n_is} pnl={base_is_pnl:+,.0f} | OOS n={n_oos} pnl={base_oos_pnl:+,.0f}")

    # Candidate
    print(f"\n[Candidate (include_first_hour_high=True)]...")
    cand_is  = _run(spy_df, vix_df, IS_START,  IS_END,  True)
    cand_oos = _run(spy_df, vix_df, OOS_START, OOS_END, True)
    cand_is_pnl  = _pnl(cand_is.trades)
    cand_oos_pnl = _pnl(cand_oos.trades)
    is_delta  = cand_is_pnl  - base_is_pnl
    oos_delta = cand_oos_pnl - base_oos_pnl

    print(f"  CANDIDATE: IS n={len(cand_is.trades)} pnl={cand_is_pnl:+,.0f} | OOS n={len(cand_oos.trades)} pnl={cand_oos_pnl:+,.0f}")
    print(f"  IS_delta={is_delta:+,.0f}  OOS_delta={oos_delta:+,.0f}")

    wf = (oos_delta / n_oos) / (is_delta / n_is) if is_delta != 0 else float("inf") if oos_delta > 0 else float("-inf")
    wf_s = f"{wf:.3f}" if abs(wf) < 200 else ("INF+" if wf > 0 else "INF-")
    print(f"  WF_norm = {wf_s}")

    # New entries added
    base_is_et = {t.entry_time_et for t in base_is.trades}
    cand_is_et = {t.entry_time_et for t in cand_is.trades}
    new_is = [t for t in cand_is.trades if t.entry_time_et not in base_is_et]
    print(f"\n  [NEW IS ENTRIES (first_hour_high unlocked): n={len(new_is)}]")
    if new_is:
        wins = sum(1 for t in new_is if t.dollar_pnl > 0)
        tot = sum(t.dollar_pnl for t in new_is)
        print(f"    WR={wins/len(new_is):.1%}  total={tot:+,.0f}  avg={tot/len(new_is):+.0f}")
        for t in sorted(new_is, key=lambda x: -x.dollar_pnl)[:10]:
            print(f"    {_date(t)}  pnl={t.dollar_pnl:>+8.0f}  {getattr(t,'exit_reason','?')}")

    new_oos = [t for t in cand_oos.trades if t.entry_time_et not in {t2.entry_time_et for t2 in base_oos.trades}]
    print(f"\n  [NEW OOS ENTRIES: n={len(new_oos)}]")
    for t in sorted(new_oos, key=lambda x: x.dollar_pnl):
        print(f"    {_date(t)}  pnl={t.dollar_pnl:>+8.0f}  {getattr(t,'exit_reason','?')}")

    # Sub-window analysis
    print(f"\n[Sub-window analysis]")
    sub_hurts = 0
    sw_results = []
    print(f"  {'Window':22}  {'BASE_n':>6}  {'CAND_n':>6}  {'BASE_pnl':>10}  {'CAND_pnl':>10}  {'delta':>8}  {'verdict':>8}")
    print("  " + "-" * 90)
    for label, s, e in IS_SUBWINDOWS:
        b = _run(spy_df, vix_df, s, e, False)
        c = _run(spy_df, vix_df, s, e, True)
        bp = _pnl(b.trades); cp = _pnl(c.trades); d = cp - bp
        verdict = "HURT" if d < -100 else ("HELP" if d > 100 else "NEUTRAL")
        if verdict == "HURT": sub_hurts += 1
        print(f"  {label:22}  {len(b.trades):>6}  {len(c.trades):>6}  {bp:>+10,.0f}  {cp:>+10,.0f}  {d:>+8,.0f}  {verdict:>8}")
        sw_results.append((label, bp, cp, d, verdict))
    sw_pass = sub_hurts <= 1

    # Anchor trace
    print(f"\n[Anchor trace]")
    cand_is_bd = _by_date(cand_is.trades)
    anchor_fails = []
    for d in sorted(J_WINNERS | J_LOSERS):
        bp = base_is_bd.get(d, 0.0); cp = cand_is_bd.get(d, 0.0)
        fail = bp > 0 and cp < bp * 0.90
        if fail: anchor_fails.append(str(d))
        tag = "(WINNER)" if d in J_WINNERS else "(LOSER)"
        print(f"  {str(d)}  {tag:9}  base={bp:>+8,.0f}  cand={cp:>+8,.0f}  {'FAIL' if fail else 'OK'}")
    anchor_ok = len(anchor_fails) == 0

    # Verdict
    oos_pos = oos_delta > 0
    wf_pass = wf >= 0.70
    print(f"\n{'='*100}")
    print(f"[FINAL VERDICT] AGG include_first_hour_high: False -> True")
    print(f"  OOS positive:      {oos_pos}  (delta={oos_delta:+,.0f})")
    print(f"  WF >= 0.70:        {wf_pass}  (WF={wf_s})")
    print(f"  Sub-window stable: {sw_pass}  (HURT={sub_hurts}/4)")
    print(f"  Anchor OK:         {anchor_ok}  (fails={anchor_fails or 'none'})")
    all_pass = oos_pos and wf_pass and sw_pass and anchor_ok
    print(f"\n  >>> {'PASS — AUTO-RATIFYING' if all_pass else 'FAIL — REJECT'} <<<")
    print(f"{'='*100}")

    if all_pass:
        scorecard_path = ROOT / "analysis" / "recommendations" / "agg-first-hour-high.json"
        scorecard = {
            "rule_id": "agg-first-hour-high",
            "param": "include_first_hour_high",
            "baseline": False,
            "candidate": True,
            "account": "Gamma-Risky-2 (PA33W2KUAT40)",
            "ratified_date": "2026-06-17",
            "is_n": n_is,
            "is_delta": is_delta,
            "oos_n": n_oos,
            "oos_delta": oos_delta,
            "wf_norm": round(wf, 4) if abs(wf) < 1000 else wf,
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

        params_path = ROOT / "automation" / "state" / "aggressive" / "params.json"
        params = json.loads(params_path.read_text())
        params["include_first_hour_high"] = True
        params["_include_first_hour_high_doc"] = (
            "INCLUDE_FIRST_HOUR_HIGH (Rank 27, auto-ratified 2026-06-17): "
            "adds max(09:30-09:55 high) to levels_active after 10:05 ET. "
            "Scorecard: analysis/recommendations/agg-first-hour-high.json."
        )
        params_path.write_text(json.dumps(params, indent=2))
        print(f"[AUTO-RATIFY] aggressive/params.json updated: include_first_hour_high=True")
    else:
        print(f"\n  include_first_hour_high REJECTED for Aggressive. Baseline False stays.")

    print("\nANALYSIS COMPLETE.")
