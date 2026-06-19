"""
SAFE_SWEEP_BLOCKER

sweep_blocker_enabled=True: blocks entries where the trigger level was recently
"swept" (quickly touched and reversed) in the counter-direction. The 5/14 09:58
misfire class — price briefly swept a level but didn't truly reject it.

Mechanism: if the last N bars show a wick through the level followed by close BACK
inside (sweep pattern), the entry is blocked as "noisy rejection."
Params: sweep_min_wick_pct=0.0003, sweep_min_close_back_pct=0.0005,
        sweep_block_window_bars=3, sweep_clean_prior_bars=3

Hypothesis: filtering out swept-level entries reduces false positives and
improves win rate at the cost of lower trade count.

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


def _run(spy_df, vix_df, start, end, sweep_enabled):
    return run_backtest(
        spy_df, vix_df,
        start_date=start, end_date=end,
        sweep_blocker_enabled=sweep_enabled,
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
    print("SAFE SWEEP_BLOCKER_ENABLED")
    print("Blocks entries where trigger level was recently 'swept' (quick wick-and-reverse)")
    print("=" * 100)

    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    # Baseline
    print(f"\n[Baseline: sweep_blocker_enabled=False]...")
    base_is  = _run(spy_df, vix_df, IS_START,  IS_END,  False)
    base_oos = _run(spy_df, vix_df, OOS_START, OOS_END, False)
    base_is_pnl  = _pnl(base_is.trades)
    base_oos_pnl = _pnl(base_oos.trades)
    n_is  = len(base_is.trades)
    n_oos = len(base_oos.trades)
    base_is_bd = _by_date(base_is.trades)
    print(f"  BASELINE: IS n={n_is} pnl={base_is_pnl:+,.0f} | OOS n={n_oos} pnl={base_oos_pnl:+,.0f}")

    # Candidate
    print(f"\n[Candidate: sweep_blocker_enabled=True]...")
    cand_is  = _run(spy_df, vix_df, IS_START,  IS_END,  True)
    cand_oos = _run(spy_df, vix_df, OOS_START, OOS_END, True)
    cand_is_pnl  = _pnl(cand_is.trades)
    cand_oos_pnl = _pnl(cand_oos.trades)
    is_delta  = cand_is_pnl  - base_is_pnl
    oos_delta = cand_oos_pnl - base_oos_pnl
    print(f"  CANDIDATE: IS n={len(cand_is.trades)} pnl={cand_is_pnl:+,.0f} | OOS n={len(cand_oos.trades)} pnl={cand_oos_pnl:+,.0f}")
    print(f"  IS_delta={is_delta:+,.0f}  OOS_delta={oos_delta:+,.0f}")

    wf = (oos_delta / n_oos) / (is_delta / n_is) if is_delta != 0 else (float("inf") if oos_delta > 0 else float("-inf"))
    wf_s = f"{wf:.3f}" if abs(wf) < 200 else ("INF+" if wf > 0 else "INF-")
    print(f"  WF_norm = {wf_s}")

    # Blocked trades
    base_is_et = {t.entry_time_et for t in base_is.trades}
    cand_is_et = {t.entry_time_et for t in cand_is.trades}
    blocked_is = [t for t in base_is.trades if t.entry_time_et not in cand_is_et]
    print(f"\n  [IS BLOCKED TRADES (sweep identified): n={len(blocked_is)}]")
    if blocked_is:
        wins = sum(1 for t in blocked_is if t.dollar_pnl > 0)
        tot  = sum(t.dollar_pnl for t in blocked_is)
        print(f"    WR={wins/len(blocked_is):.1%}  total={tot:+,.0f}  avg={tot/len(blocked_is):+.0f}")
        for t in sorted(blocked_is, key=lambda x: x.dollar_pnl)[:10]:
            print(f"    {_date(t)}  pnl={t.dollar_pnl:>+8.0f}  {getattr(t,'exit_reason','?')}")
    else:
        print("    None (gate has no effect on IS entries)")

    base_oos_et = {t.entry_time_et for t in base_oos.trades}
    cand_oos_et = {t.entry_time_et for t in cand_oos.trades}
    blocked_oos = [t for t in base_oos.trades if t.entry_time_et not in cand_oos_et]
    print(f"\n  [OOS BLOCKED TRADES: n={len(blocked_oos)}]")
    if blocked_oos:
        wins = sum(1 for t in blocked_oos if t.dollar_pnl > 0)
        tot  = sum(t.dollar_pnl for t in blocked_oos)
        print(f"    WR={wins/len(blocked_oos):.1%}  total={tot:+,.0f}  avg={tot/len(blocked_oos):+.0f}")
        for t in sorted(blocked_oos, key=lambda x: x.dollar_pnl):
            print(f"    {_date(t)}  pnl={t.dollar_pnl:>+8.0f}  {getattr(t,'exit_reason','?')}")

    # Sub-window
    print(f"\n[Sub-window analysis]")
    print(f"  {'Window':22}  {'BASE_n':>6}  {'CAND_n':>6}  {'BASE_pnl':>10}  {'CAND_pnl':>10}  {'delta':>8}  {'verdict':>8}")
    print("  " + "-" * 90)
    sub_hurts = 0
    sw_results = []
    for label, s, e in IS_SUBWINDOWS:
        b = _run(spy_df, vix_df, s, e, False)
        c = _run(spy_df, vix_df, s, e, True)
        bp = _pnl(b.trades); cp = _pnl(c.trades); d = cp - bp
        verdict = "HURT" if d < -100 else ("HELP" if d > 100 else "NEUTRAL")
        if verdict == "HURT": sub_hurts += 1
        print(f"  {label:22}  {len(b.trades):>6}  {len(c.trades):>6}  {bp:>+10,.0f}  {cp:>+10,.0f}  {d:>+8,.0f}  {verdict:>8}")
        sw_results.append((label, bp, cp, d, verdict))
    sw_pass = sub_hurts <= 1

    # Anchor
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

    oos_pos = oos_delta > 0
    wf_pass = wf >= 0.70
    print(f"\n{'='*100}")
    print(f"[FINAL VERDICT] Safe sweep_blocker: False -> True")
    print(f"  OOS positive:      {oos_pos}  (delta={oos_delta:+,.0f})")
    print(f"  WF >= 0.70:        {wf_pass}  (WF={wf_s})")
    print(f"  Sub-window stable: {sw_pass}  (HURT={sub_hurts}/4)")
    print(f"  Anchor OK:         {anchor_ok}  (fails={anchor_fails or 'none'})")
    all_pass = oos_pos and wf_pass and sw_pass and anchor_ok
    print(f"\n  >>> {'PASS — AUTO-RATIFYING' if all_pass else 'FAIL — REJECT'} <<<")
    print(f"{'='*100}")

    if all_pass:
        scorecard_path = ROOT / "analysis" / "recommendations" / "safe-sweep-blocker.json"
        scorecard = {
            "rule_id": "safe-sweep-blocker",
            "param": "sweep_blocker_enabled",
            "baseline": False, "candidate": True,
            "account": "Gamma-Safe-2 (PA3S2PYAS2WQ)",
            "ratified_date": "2026-06-17",
            "is_n": n_is, "is_delta": is_delta,
            "oos_n": n_oos, "oos_delta": oos_delta,
            "wf_norm": round(wf, 4) if abs(wf) < 1000 else wf,
            "oos_positive": True, "sw_hurt": sub_hurts, "sw_pass": sw_pass,
            "anchor_ok": anchor_ok, "anchor_fails": anchor_fails, "all_gates_pass": True,
            "mechanism": (
                "Blocks entries where trigger level was recently swept (quick wick-and-reverse). "
                "5/14 09:58 misfire class: price briefly sweeps level without genuine rejection. "
                "Params: min_wick_pct=0.0003, min_close_back_pct=0.0005, window=3bars, clean_prior=3bars."
            ),
            "sub_windows": [{"label": l, "base_pnl": b, "cand_pnl": c, "delta": d, "verdict": v}
                            for l, b, c, d, v in sw_results],
        }
        scorecard_path.parent.mkdir(exist_ok=True)
        scorecard_path.write_text(json.dumps(scorecard, indent=2))
        print(f"\n[AUTO-RATIFY] Scorecard: {scorecard_path}")

        params_path = ROOT / "automation" / "state" / "params.json"
        params = json.loads(params_path.read_text())
        params["sweep_blocker_enabled"] = True
        params["_sweep_blocker_doc"] = (
            "SWEEP_BLOCKER (auto-ratified 2026-06-17): blocks entries when trigger level "
            "was recently swept (quick wick-through-and-close-back). Prevents 5/14-class "
            "misfire entries on noisy level touches. "
            "Scorecard: analysis/recommendations/safe-sweep-blocker.json."
        )
        params_path.write_text(json.dumps(params, indent=2))
        print(f"[AUTO-RATIFY] params.json updated: sweep_blocker_enabled=True")
    else:
        print(f"\n  sweep_blocker REJECTED. Baseline False stays.")

    print("\nANALYSIS COMPLETE.")
