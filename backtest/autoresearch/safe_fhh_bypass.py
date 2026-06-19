"""
SAFE_FHH_BYPASS: include_first_hour_high=True + include_bearish_reversal_bypass=True

Why the combination:
  - include_first_hour_high adds max(09:30-09:55 high) as 'fhh_level_rejection' trigger
  - include_bearish_reversal_bypass skips filter_5 (ribbon stack) + filter_8 (VIX gate)
    ONLY for fhh_level_rejection setups where ribbon=BULL
  - Together they unlock: price rejects FHH while ribbon=BULL → bearish entry allowed
  - The 5/01 11:50 J anchor (+$470 EC) is this exact setup: FHH rejection, ribbon=BULL,
    was blocked by filter_5. Combined gate allows it.
  - Neither gate alone is meaningful (FHH alone showed 0 OOS entries because ribbon=BULL
    entries still hit filter_5; bypass alone never fires without FHH active)

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


def _run(spy_df, vix_df, start, end, use_fhh=False, use_bypass=False):
    return run_backtest(
        spy_df, vix_df,
        start_date=start, end_date=end,
        include_first_hour_high=use_fhh,
        include_bearish_reversal_bypass=use_bypass,
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
    print("SAFE FHH_BYPASS: include_first_hour_high=True + include_bearish_reversal_bypass=True")
    print("The 5/01 J anchor setup: FHH rejection + ribbon=BULL (bypasses filter_5 + filter_8)")
    print("=" * 100)

    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    # Baseline (both False)
    print(f"\n[Baseline: FHH=False, bypass=False]...")
    base_is  = _run(spy_df, vix_df, IS_START,  IS_END,  False, False)
    base_oos = _run(spy_df, vix_df, OOS_START, OOS_END, False, False)
    base_is_pnl  = _pnl(base_is.trades)
    base_oos_pnl = _pnl(base_oos.trades)
    n_is  = len(base_is.trades)
    n_oos = len(base_oos.trades)
    base_is_bd = _by_date(base_is.trades)
    print(f"  BASELINE: IS n={n_is} pnl={base_is_pnl:+,.0f} | OOS n={n_oos} pnl={base_oos_pnl:+,.0f}")

    # Candidate (both True)
    print(f"\n[Candidate: FHH=True, bypass=True]...")
    cand_is  = _run(spy_df, vix_df, IS_START,  IS_END,  True, True)
    cand_oos = _run(spy_df, vix_df, OOS_START, OOS_END, True, True)
    cand_is_pnl  = _pnl(cand_is.trades)
    cand_oos_pnl = _pnl(cand_oos.trades)
    is_delta  = cand_is_pnl  - base_is_pnl
    oos_delta = cand_oos_pnl - base_oos_pnl
    print(f"  CANDIDATE: IS n={len(cand_is.trades)} pnl={cand_is_pnl:+,.0f} | OOS n={len(cand_oos.trades)} pnl={cand_oos_pnl:+,.0f}")
    print(f"  IS_delta={is_delta:+,.0f}  OOS_delta={oos_delta:+,.0f}")

    wf = (oos_delta / n_oos) / (is_delta / n_is) if is_delta != 0 else (float("inf") if oos_delta > 0 else float("-inf"))
    wf_s = f"{wf:.3f}" if abs(wf) < 200 else ("INF+" if wf > 0 else "INF-")
    print(f"  WF_norm = {wf_s}")

    # New entries
    base_is_et  = {t.entry_time_et for t in base_is.trades}
    cand_is_et  = {t.entry_time_et for t in cand_is.trades}
    new_is = [t for t in cand_is.trades if t.entry_time_et not in base_is_et]
    print(f"\n  [NEW IS ENTRIES (FHH bypass unlocked): n={len(new_is)}]")
    if new_is:
        wins = sum(1 for t in new_is if t.dollar_pnl > 0)
        tot  = sum(t.dollar_pnl for t in new_is)
        print(f"    WR={wins/len(new_is):.1%}  total={tot:+,.0f}  avg={tot/len(new_is):+.0f}")
        for t in sorted(new_is, key=lambda x: -x.dollar_pnl)[:15]:
            print(f"    {_date(t)}  pnl={t.dollar_pnl:>+8.0f}  {getattr(t,'exit_reason','?')}")

    # 5/01 J WINNER check
    cand_is_bd = _by_date(cand_is.trades)
    base_501 = base_is_bd.get(dt.date(2026, 5, 1), 0.0)
    cand_501 = cand_is_bd.get(dt.date(2026, 5, 1), 0.0)
    print(f"\n  [5/01 J WINNER check] base={base_501:+.0f}  cand={cand_501:+.0f}  delta={cand_501-base_501:+.0f}")

    base_oos_et = {t.entry_time_et for t in base_oos.trades}
    new_oos = [t for t in cand_oos.trades if t.entry_time_et not in base_oos_et]
    print(f"\n  [NEW OOS ENTRIES: n={len(new_oos)}]")
    for t in sorted(new_oos, key=lambda x: x.dollar_pnl):
        print(f"    {_date(t)}  pnl={t.dollar_pnl:>+8.0f}  {getattr(t,'exit_reason','?')}")

    # Sub-window
    print(f"\n[Sub-window analysis]")
    print(f"  {'Window':22}  {'BASE_n':>6}  {'CAND_n':>6}  {'BASE_pnl':>10}  {'CAND_pnl':>10}  {'delta':>8}  {'verdict':>8}")
    print("  " + "-" * 90)
    sub_hurts = 0
    sw_results = []
    for label, s, e in IS_SUBWINDOWS:
        b = _run(spy_df, vix_df, s, e, False, False)
        c = _run(spy_df, vix_df, s, e, True,  True)
        bp = _pnl(b.trades); cp = _pnl(c.trades); d = cp - bp
        verdict = "HURT" if d < -100 else ("HELP" if d > 100 else "NEUTRAL")
        if verdict == "HURT": sub_hurts += 1
        print(f"  {label:22}  {len(b.trades):>6}  {len(c.trades):>6}  {bp:>+10,.0f}  {cp:>+10,.0f}  {d:>+8,.0f}  {verdict:>8}")
        sw_results.append((label, bp, cp, d, verdict))
    sw_pass = sub_hurts <= 1

    # Anchor
    print(f"\n[Anchor trace]")
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
    print(f"[FINAL VERDICT] Safe FHH+bypass (both False -> both True)")
    print(f"  OOS positive:      {oos_pos}  (delta={oos_delta:+,.0f})")
    print(f"  WF >= 0.70:        {wf_pass}  (WF={wf_s})")
    print(f"  Sub-window stable: {sw_pass}  (HURT={sub_hurts}/4)")
    print(f"  Anchor OK:         {anchor_ok}  (fails={anchor_fails or 'none'})")
    all_pass = oos_pos and wf_pass and sw_pass and anchor_ok
    print(f"\n  >>> {'PASS — AUTO-RATIFYING' if all_pass else 'FAIL — REJECT'} <<<")
    print(f"{'='*100}")

    if all_pass:
        scorecard_path = ROOT / "analysis" / "recommendations" / "safe-fhh-bypass.json"
        scorecard = {
            "rule_id": "safe-fhh-bypass",
            "params": {"include_first_hour_high": True, "include_bearish_reversal_bypass": True},
            "baseline": {"include_first_hour_high": False, "include_bearish_reversal_bypass": False},
            "account": "Gamma-Safe-2 (PA3S2PYAS2WQ)",
            "ratified_date": "2026-06-17",
            "is_n": n_is, "is_delta": is_delta,
            "oos_n": n_oos, "oos_delta": oos_delta,
            "wf_norm": round(wf, 4) if abs(wf) < 1000 else wf,
            "oos_positive": True, "sw_hurt": sub_hurts, "sw_pass": sw_pass,
            "anchor_ok": anchor_ok, "anchor_fails": anchor_fails, "all_gates_pass": True,
            "mechanism": (
                "FHH rejection (first-hour-high as resistance) + bypass of filter_5 (ribbon) "
                "and filter_8 (VIX) for BEARISH_REVERSAL setups. Unlocks counter-trend bears "
                "when price runs up to the morning high and rejects it while ribbon=BULL. "
                "5/01 J anchor (+$470) is the motivating case."
            ),
            "sub_windows": [{"label": l, "base_pnl": b, "cand_pnl": c, "delta": d, "verdict": v}
                            for l, b, c, d, v in sw_results],
        }
        scorecard_path.parent.mkdir(exist_ok=True)
        scorecard_path.write_text(json.dumps(scorecard, indent=2))
        print(f"\n[AUTO-RATIFY] Scorecard: {scorecard_path}")

        params_path = ROOT / "automation" / "state" / "params.json"
        params = json.loads(params_path.read_text())
        params["include_first_hour_high"] = True
        params["include_bearish_reversal_bypass"] = True
        params["_fhh_bypass_doc"] = (
            "FHH_BYPASS (auto-ratified 2026-06-17): include_first_hour_high=True adds "
            "max(09:30-09:55 high) as fhh_level_rejection level. "
            "include_bearish_reversal_bypass=True skips filter_5+8 for fhh_level_rejection "
            "when ribbon=BULL. Unlocks 5/01-style counter-trend bears. "
            "Scorecard: analysis/recommendations/safe-fhh-bypass.json."
        )
        params_path.write_text(json.dumps(params, indent=2))
        print(f"[AUTO-RATIFY] params.json updated: include_first_hour_high=True, include_bearish_reversal_bypass=True")
    else:
        print(f"\n  FHH+bypass REJECTED. Baseline stays.")

    print("\nANALYSIS COMPLETE.")
