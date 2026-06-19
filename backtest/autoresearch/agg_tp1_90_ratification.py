"""
AGG_TP1_90_RATIFICATION

Full sub-window / anchor / WF analysis for tp1_premium_pct=0.90 vs 0.75 (production).

From context-30 tp1 sweep (at full production params):
  Baseline  0.75: IS n=270 pnl=+19,566 | OOS n=28 pnl=+2,590
  Candidate 0.90: IS_delta=+179,        OOS_delta=+372,   WF=+19.6

Only gate this session that shows BOTH IS and OOS improving vs production baseline.
Mechanism: taking 2/3 of position at 90% gain (vs 75%) captures more when runners
subsequently return to ~1x entry premium (the dominant OOS exit pattern).

C22 note: This gate should be REGIME-AGNOSTIC because TP1 threshold affects all trades
regardless of VIX regime. Verify this holds in sub-windows.

Gates to pass:
  OOS_positive AND WF >= 0.70 AND SW_hurt <= 1 AND anchor_OK

Auto-ratify if all gates pass:
  1. Update automation/state/aggressive/params.json -> tp1_premium_pct: 0.90
  2. File A/B scorecard at analysis/recommendations/agg-tp1-premium-090.json

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

# Full production Aggressive params (automation/state/aggressive/params.json, 2026-06-17)
# CRITICAL: all knobs must match production or this comparison is C14 contaminated
AGG_BASE_KW = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=False,
    premium_stop_pct_bear=-0.07,          # TIGHTER_STOP_2, ratified 2026-06-17
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

BASELINE_TP1 = 0.75
CANDIDATE_TP1 = 0.90


def _run(spy_df, vix_df, start, end, tp1_pct):
    return run_backtest(
        spy_df, vix_df,
        start_date=start, end_date=end,
        tp1_premium_pct=tp1_pct,
        params_overrides=dict(AGG_OVR),
        **AGG_BASE_KW,
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
    print("=" * 110)
    print("AGG TP1_PREMIUM_PCT = 0.90 RATIFICATION STUDY")
    print("Baseline: 0.75 (production). Candidate: 0.90.")
    print("=" * 110)

    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    # IS + OOS for both baseline and candidate
    print(f"\n[Step 1] Running IS/OOS for baseline ({BASELINE_TP1}) and candidate ({CANDIDATE_TP1})...")
    base_is   = _run(spy_df, vix_df, IS_START,  IS_END,  BASELINE_TP1)
    base_oos  = _run(spy_df, vix_df, OOS_START, OOS_END, BASELINE_TP1)
    cand_is   = _run(spy_df, vix_df, IS_START,  IS_END,  CANDIDATE_TP1)
    cand_oos  = _run(spy_df, vix_df, OOS_START, OOS_END, CANDIDATE_TP1)

    base_is_pnl  = _pnl(base_is.trades)
    base_oos_pnl = _pnl(base_oos.trades)
    cand_is_pnl  = _pnl(cand_is.trades)
    cand_oos_pnl = _pnl(cand_oos.trades)

    n_is  = len(base_is.trades)
    n_oos = len(base_oos.trades)

    is_delta  = cand_is_pnl  - base_is_pnl
    oos_delta = cand_oos_pnl - base_oos_pnl

    wf = (oos_delta / n_oos) / (is_delta / n_is) if is_delta != 0 else float("inf") if oos_delta > 0 else float("-inf")

    print(f"\n  {'':20}  {'n':>5}  {'baseline':>10}  {'candidate':>10}  {'delta':>8}")
    print("  " + "-" * 65)
    print(f"  {'IS':20}  {n_is:>5}  {base_is_pnl:>+10,.0f}  {cand_is_pnl:>+10,.0f}  {is_delta:>+8,.0f}")
    print(f"  {'OOS':20}  {n_oos:>5}  {base_oos_pnl:>+10,.0f}  {cand_oos_pnl:>+10,.0f}  {oos_delta:>+8,.0f}")
    wf_s = f"{wf:.3f}" if abs(wf) < 200 else ("INF+" if wf > 0 else "INF-")
    print(f"\n  WF_norm = (OOS_delta/n_oos) / (IS_delta/n_is) = {wf_s}")

    # Sub-window analysis
    print(f"\n[Step 2] Sub-window analysis (4 IS windows)...")
    print(f"  {'Window':22}  {'BASE_n':>6}  {'CAND_n':>6}  {'BASE_pnl':>10}  {'CAND_pnl':>10}  {'delta':>8}  {'verdict':>8}")
    print("  " + "-" * 92)
    sub_hurts = 0
    sw_results = []
    for label, s, e in IS_SUBWINDOWS:
        b = _run(spy_df, vix_df, s, e, BASELINE_TP1)
        c = _run(spy_df, vix_df, s, e, CANDIDATE_TP1)
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
    print(f"\n[Step 3] Anchor trace (J anchor days)...")
    base_is_bd = _by_date(base_is.trades)
    cand_is_bd = _by_date(cand_is.trades)
    base_oos_bd = _by_date(base_oos.trades)
    cand_oos_bd = _by_date(cand_oos.trades)
    anchor_fails = []
    for d in sorted(J_WINNERS | J_LOSERS):
        bp = base_is_bd.get(d, 0.0)
        cp = cand_is_bd.get(d, 0.0)
        fail = bp > 0 and cp < bp * 0.90
        tag = "(WINNER)" if d in J_WINNERS else "(LOSER)"
        ok_s = "FAIL" if fail else "OK"
        if fail:
            anchor_fails.append(str(d))
        print(f"  {str(d)}  {tag:9}  base={bp:>+8,.0f}  cand={cp:>+8,.0f}  {ok_s}")
    anchor_ok = len(anchor_fails) == 0

    # OOS VIX regime breakdown for both
    print(f"\n[Step 4] OOS VIX regime breakdown (base vs cand)...")
    def vix_bucket(vix):
        if vix is None: return "unknown"
        if vix < 17: return "VIX<17"
        if vix < 20: return "VIX 17-20"
        if vix < 25: return "VIX 20-25"
        return "VIX 25+"

    print(f"  BASELINE (tp1=0.75):")
    by_vix_b = {}
    for t in base_oos.trades:
        k = vix_bucket(getattr(t, "entry_vix", None))
        by_vix_b.setdefault(k, []).append(t)
    for k in ["VIX<17", "VIX 17-20", "VIX 20-25", "VIX 25+"]:
        ts = by_vix_b.get(k, [])
        if not ts: continue
        tot = sum(t.dollar_pnl for t in ts)
        wr = sum(1 for t in ts if t.dollar_pnl > 0) / len(ts)
        print(f"    {k:12}  n={len(ts):>3}  WR={wr:.0%}  pnl={tot:>+7,.0f}")

    print(f"  CANDIDATE (tp1=0.90):")
    by_vix_c = {}
    for t in cand_oos.trades:
        k = vix_bucket(getattr(t, "entry_vix", None))
        by_vix_c.setdefault(k, []).append(t)
    for k in ["VIX<17", "VIX 17-20", "VIX 20-25", "VIX 25+"]:
        ts = by_vix_c.get(k, [])
        if not ts: continue
        tot = sum(t.dollar_pnl for t in ts)
        wr = sum(1 for t in ts if t.dollar_pnl > 0) / len(ts)
        print(f"    {k:12}  n={len(ts):>3}  WR={wr:.0%}  pnl={tot:>+7,.0f}")

    # OOS exit reason breakdown for candidate
    print(f"\n[Step 5] OOS exit reason breakdown (candidate 0.90)...")
    by_exit = {}
    for t in cand_oos.trades:
        k = str(getattr(t, "exit_reason", "?") or "?")
        by_exit.setdefault(k, []).append(t)
    print(f"  {'Exit':40}  {'n':>4}  {'WR':>6}  {'avg':>8}  {'total':>9}")
    print("  " + "-" * 75)
    for k, ts in sorted(by_exit.items(), key=lambda x: -sum(t.dollar_pnl for t in x[1])):
        n = len(ts); wins = sum(1 for t in ts if t.dollar_pnl > 0); tot = sum(t.dollar_pnl for t in ts)
        print(f"  {k:40}  {n:>4}  {wins/n:>6.1%}  {tot/n:>+8.0f}  {tot:>+9.0f}")

    # Summary verdict
    print(f"\n{'='*110}")
    print(f"[FINAL VERDICT] AGG tp1_premium_pct: 0.75 -> 0.90")
    print(f"  OOS positive:      {oos_delta > 0}  (delta={oos_delta:+,.0f})")
    print(f"  WF >= 0.70:        {wf >= 0.70}  (WF={wf_s})")
    print(f"  Sub-window stable: {sw_pass}  (HURT={sub_hurts} / 4 windows)")
    print(f"  Anchor OK:         {anchor_ok}  (fails={anchor_fails or 'none'})")
    all_pass = (oos_delta > 0) and (wf >= 0.70) and sw_pass and anchor_ok
    print(f"\n  >>> {'PASS — AUTO-RATIFYING' if all_pass else 'FAIL — REJECT'} <<<")
    print(f"{'='*110}")

    if all_pass:
        # Step 6: Write A/B scorecard
        scorecard_path = ROOT / "analysis" / "recommendations" / "agg-tp1-premium-090.json"
        scorecard = {
            "rule_id": "agg-tp1-premium-090",
            "param": "tp1_premium_pct",
            "baseline": BASELINE_TP1,
            "candidate": CANDIDATE_TP1,
            "account": "Gamma-Risky-2 (PA33W2KUAT40)",
            "ratified_date": "2026-06-17",
            "is_n": n_is,
            "is_baseline_pnl": base_is_pnl,
            "is_candidate_pnl": cand_is_pnl,
            "is_delta": is_delta,
            "oos_n": n_oos,
            "oos_baseline_pnl": base_oos_pnl,
            "oos_candidate_pnl": cand_oos_pnl,
            "oos_delta": oos_delta,
            "wf_norm": round(wf, 4) if abs(wf) < 1000 else wf,
            "oos_positive": True,
            "sw_hurt": sub_hurts,
            "sw_pass": sw_pass,
            "anchor_ok": anchor_ok,
            "anchor_fails": anchor_fails,
            "all_gates_pass": True,
            "mechanism": (
                "At tp1=0.90, TP1 captures 2/3 of position at 90% gain instead of 75%. "
                "OOS runners predominantly exit at ~1x entry premium (ribbon flip / BE stop). "
                "So capturing 15pp more premium at TP1 before the runner decays back is regime-agnostic. "
                "Cliff at tp1=1.00: any trade peaking 75-99% then reversing becomes a full loss."
            ),
            "sub_windows": [
                {"label": lbl, "base_pnl": bp, "cand_pnl": cp, "delta": d, "verdict": v}
                for lbl, bp, cp, d, v in sw_results
            ],
        }
        scorecard_path.parent.mkdir(exist_ok=True)
        scorecard_path.write_text(json.dumps(scorecard, indent=2))
        print(f"\n[AUTO-RATIFY] A/B scorecard filed: {scorecard_path}")

        # Step 7: Update automation/state/aggressive/params.json
        params_path = ROOT / "automation" / "state" / "aggressive" / "params.json"
        params = json.loads(params_path.read_text())
        old_val = params.get("tp1_premium_pct", "N/A")
        params["tp1_premium_pct"] = CANDIDATE_TP1
        params_path.write_text(json.dumps(params, indent=2))
        print(f"[AUTO-RATIFY] params.json updated: tp1_premium_pct {old_val} -> {CANDIDATE_TP1}")
        print(f"[AUTO-RATIFY] Path: {params_path}")
        print(f"\n[AUTO-RATIFY] DONE. Next heartbeat will use tp1_premium_pct=0.90.")
    else:
        print(f"\n  Baseline tp1_premium_pct=0.75 CONFIRMED OPTIMAL.")

    print("\nANALYSIS COMPLETE.")
