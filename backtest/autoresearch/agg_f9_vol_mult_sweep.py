"""
AGG f9_vol_mult SWEEP (2026-06-17)

f9_vol_mult was previously swept in C14-Batch-6 on the WRONG pre-C14 baseline
(IS n=244 pnl=-5118 because tp1_premium_pct used default 0.30 not production 0.75).
Re-testing with correct C14 baseline (IS n=270 pnl=+19,566 | OOS n=28 pnl=+2,590).

Hypothesis: Filter 9 volume multiplier controls how strict the volume filter is.
At 0.7, we require 70% of 20-bar avg volume. Higher = fewer trades, potentially
cleaner signals. Lower = more trades. Pre-C14 sweep showed all OOS-negative, but
that was on wrong baseline with different IS/OOS populations.

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

# AGG C14-correct baseline
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
    tp1_premium_pct=0.75,
)
AGG_OVR = {"vix_bear_threshold": 15.0, "vix_bull_max": 30.0}

BASELINE_F9 = 0.7
CANDIDATES = [0.5, 1.0, 1.3]  # wider net, tighter, very tight


def _run(spy_df, vix_df, start, end, f9):
    return run_backtest(
        spy_df, vix_df,
        start_date=start, end_date=end,
        f9_vol_mult=f9,
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


if __name__ == "__main__":
    print("=" * 100)
    print(f"AGG f9_vol_mult SWEEP (C14-correct baseline)")
    print(f"Prior sweep on WRONG baseline (tp1=0.30 default, IS pnl=-5118) is INVALID.")
    print(f"Correct baseline: IS n=270 pnl=+19,566 | OOS n=28 pnl=+2,590")
    print("=" * 100)

    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    # Baseline
    print(f"\n[Baseline: f9_vol_mult={BASELINE_F9}]...")
    b_is  = _run(spy_df, vix_df, IS_START,  IS_END,  BASELINE_F9)
    b_oos = _run(spy_df, vix_df, OOS_START, OOS_END, BASELINE_F9)
    b_is_pnl  = _pnl(b_is.trades)
    b_oos_pnl = _pnl(b_oos.trades)
    n_is  = len(b_is.trades)
    n_oos = len(b_oos.trades)
    b_is_bd  = _by_date(b_is.trades)
    print(f"  BASELINE: IS n={n_is} pnl={b_is_pnl:+,.0f} | OOS n={n_oos} pnl={b_oos_pnl:+,.0f}")

    print(f"\n[Sweep: f9_vol_mult candidates = {CANDIDATES}]")
    print(f"  {'f9_vol':>8}  {'IS_n':>6}  {'IS_pnl':>10}  {'OOS_n':>6}  {'OOS_pnl':>10}  "
          f"{'IS_delta':>10}  {'OOS_delta':>10}  {'WF':>8}")
    print("  " + "-" * 90)

    best_candidate = None
    best_wf = -99

    for f9 in CANDIDATES:
        ci  = _run(spy_df, vix_df, IS_START,  IS_END,  f9)
        co  = _run(spy_df, vix_df, OOS_START, OOS_END, f9)
        ci_pnl = _pnl(ci.trades)
        co_pnl = _pnl(co.trades)
        is_d = ci_pnl - b_is_pnl
        oos_d = co_pnl - b_oos_pnl
        if is_d != 0:
            wf = (oos_d / n_oos) / (is_d / n_is)
        else:
            wf = float("inf") if oos_d > 0 else float("-inf")
        wf_s = f"{wf:.3f}" if abs(wf) < 200 else ("INF+" if wf > 0 else "INF-")
        print(f"  {f9:>8.1f}  {len(ci.trades):>6}  {ci_pnl:>+10,.0f}  {len(co.trades):>6}  "
              f"{co_pnl:>+10,.0f}  {is_d:>+10,.0f}  {oos_d:>+10,.0f}  {wf_s:>8}")
        if oos_d > 0 and (best_candidate is None or wf > best_wf):
            best_candidate = (f9, ci, co, is_d, oos_d, wf, wf_s)
            best_wf = wf

    if best_candidate is None:
        print(f"\n  No OOS-positive candidate. AGG f9_vol_mult={BASELINE_F9} CONFIRMED.")
        print("\nANALYSIS COMPLETE.")
        exit(0)

    f9, ci, co, is_d, oos_d, wf, wf_s = best_candidate
    print(f"\n[Best candidate: f9_vol_mult={f9}]")
    print(f"  IS_delta={is_d:+,.0f}  OOS_delta={oos_d:+,.0f}  WF={wf_s}")

    # Sub-window
    ci_bd = _by_date(ci.trades)
    print(f"\n[Sub-window analysis]")
    print(f"  {'Window':22}  {'BASE_n':>6}  {'CAND_n':>6}  {'BASE_pnl':>10}  "
          f"{'CAND_pnl':>10}  {'delta':>8}  {'verdict':>8}")
    print("  " + "-" * 90)
    sub_hurts = 0
    sw_results = []
    for label, s, e in IS_SUBWINDOWS:
        b = _run(spy_df, vix_df, s, e, BASELINE_F9)
        c = _run(spy_df, vix_df, s, e, f9)
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
    print(f"[VERDICT] AGG f9_vol_mult={BASELINE_F9} -> {f9}")
    print(f"  OOS positive:      {oos_pos}  (delta={oos_d:+,.0f})")
    print(f"  WF >= 0.70:        {wf_pass}  (WF={wf_s})")
    print(f"  Sub-window stable: {sw_pass}  (HURT={sub_hurts}/4)")
    print(f"  Anchor OK:         {anchor_ok}  (fails={anchor_fails or 'none'})")
    all_pass = oos_pos and wf_pass and sw_pass and anchor_ok
    print(f"\n  >>> {'PASS - AUTO-RATIFYING' if all_pass else 'FAIL - REJECT'} <<<")
    print("=" * 100)

    if all_pass:
        sc_path = ROOT / "analysis" / "recommendations" / f"agg-f9-vol-{str(f9).replace('.','')}.json"
        sc = {
            "rule_id": f"agg-f9-vol-{str(f9).replace('.', '')}",
            "param": "f9_vol_mult",
            "baseline": BASELINE_F9, "candidate": f9,
            "account": "Gamma-Bold (PA33W2KUAT40)",
            "ratified_date": "2026-06-17",
            "is_n": n_is, "is_delta": round(is_d, 2),
            "oos_n": n_oos, "oos_delta": round(oos_d, 2),
            "wf_norm": round(wf, 4),
            "oos_positive": True, "sw_hurt": sub_hurts, "sw_pass": sw_pass,
            "anchor_ok": anchor_ok, "anchor_fails": anchor_fails, "all_gates_pass": True,
            "mechanism": f"AGG Filter 9 volume multiplier: {BASELINE_F9} -> {f9}",
            "sub_windows": [{"label": l, "base_pnl": b, "cand_pnl": c, "delta": d, "verdict": v}
                            for l, b, c, d, v in sw_results],
        }
        sc_path.parent.mkdir(exist_ok=True)
        sc_path.write_text(json.dumps(sc, indent=2), encoding="utf-8")
        print(f"\n[AUTO-RATIFY] Scorecard: {sc_path}")
        params_path = ROOT / "automation" / "state" / "aggressive" / "params.json"
        params = json.loads(params_path.read_text(encoding="utf-8-sig"))
        params["f9_vol_mult"] = f9
        params["_f9_vol_doc"] = f"auto-ratified 2026-06-17: f9_vol_mult {BASELINE_F9} -> {f9}"
        params_path.write_text(json.dumps(params, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[AUTO-RATIFY] aggressive/params.json updated: f9_vol_mult={f9}")

    print("\nANALYSIS COMPLETE.")
