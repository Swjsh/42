"""
SAFE_RIBBON_FLIP_PRICE_CONFIRM

OOS exit breakdown shows 4/9 winners exit at 1.00x via ribbon flip (runner_exit == entry premium).
This means the runner was exited when ribbon flipped back, but price hadn't moved against entry.

ribbon_flip_price_confirm=True: require price to reverse past entry_spot before
EXIT_ALL_RIBBON_FLIP_BACK fires. For bear puts: SPY must rise ABOVE entry_spot.

Hypothesis: some ribbon-flip exits fire when ribbon reverses but price is still favorable.
Holding until price confirms the reversal would increase runner P&L on those trades.
Risk: if the ribbon correctly predicted the reversal, holding costs us.

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


def _run(spy_df, vix_df, start, end, price_confirm):
    return run_backtest(
        spy_df, vix_df,
        start_date=start, end_date=end,
        ribbon_flip_price_confirm=price_confirm,
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
    print("SAFE RIBBON_FLIP_PRICE_CONFIRM")
    print("OOS: 4/9 runners exit at 1.00x via ribbon flip. Does price confirm help?")
    print("=" * 100)

    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    # Baseline
    print(f"\n[Baseline: ribbon_flip_price_confirm=False]...")
    base_is  = _run(spy_df, vix_df, IS_START,  IS_END,  False)
    base_oos = _run(spy_df, vix_df, OOS_START, OOS_END, False)
    base_is_pnl  = _pnl(base_is.trades)
    base_oos_pnl = _pnl(base_oos.trades)
    n_is  = len(base_is.trades)
    n_oos = len(base_oos.trades)
    base_is_bd = _by_date(base_is.trades)
    print(f"  BASELINE: IS n={n_is} pnl={base_is_pnl:+,.0f} | OOS n={n_oos} pnl={base_oos_pnl:+,.0f}")

    # OOS exit breakdown at baseline
    print(f"\n  [OOS exit breakdown (baseline)]")
    by_exit = {}
    for t in base_oos.trades:
        k = str(getattr(t, "exit_reason", "?") or "?")
        by_exit.setdefault(k, []).append(t)
    for k, ts in sorted(by_exit.items(), key=lambda x: -len(x[1])):
        n = len(ts); wins = sum(1 for t in ts if t.dollar_pnl > 0); tot = sum(t.dollar_pnl for t in ts)
        rp_ratios = []
        for t in ts:
            ep = getattr(t, "entry_premium", None)
            rp = getattr(t, "runner_exit_premium", None)
            if ep and rp: rp_ratios.append(rp/ep)
        avg_ratio = f"{sum(rp_ratios)/len(rp_ratios):.2f}x" if rp_ratios else "N/A"
        print(f"    {k:40}  n={n:>3}  WR={wins/n:.1%}  avg_pnl={tot/n:>+.0f}  avg_runner_ratio={avg_ratio}")

    # Candidate
    print(f"\n[Candidate: ribbon_flip_price_confirm=True]...")
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

    # OOS exit breakdown at candidate
    print(f"\n  [OOS exit breakdown (candidate)]")
    by_exit_c = {}
    for t in cand_oos.trades:
        k = str(getattr(t, "exit_reason", "?") or "?")
        by_exit_c.setdefault(k, []).append(t)
    for k, ts in sorted(by_exit_c.items(), key=lambda x: -len(x[1])):
        n = len(ts); wins = sum(1 for t in ts if t.dollar_pnl > 0); tot = sum(t.dollar_pnl for t in ts)
        print(f"    {k:40}  n={n:>3}  WR={wins/n:.1%}  avg_pnl={tot/n:>+.0f}")

    # Trades changed
    cand_is_bd = _by_date(cand_is.trades)
    cand_oos_bd = _by_date(cand_oos.trades)
    changed_oos = []
    for t_base in base_oos.trades:
        for t_cand in cand_oos.trades:
            if t_base.entry_time_et == t_cand.entry_time_et and abs(t_base.dollar_pnl - t_cand.dollar_pnl) > 1:
                changed_oos.append((t_base, t_cand))
    print(f"\n  [OOS TRADES CHANGED BY PRICE CONFIRM: n={len(changed_oos)}]")
    for tb, tc in sorted(changed_oos, key=lambda x: x[1].dollar_pnl - x[0].dollar_pnl, reverse=True):
        print(f"    {_date(tb)}  base_pnl={tb.dollar_pnl:>+8.0f} ({getattr(tb,'exit_reason','?')}) → cand_pnl={tc.dollar_pnl:>+8.0f} ({getattr(tc,'exit_reason','?')})  delta={tc.dollar_pnl-tb.dollar_pnl:>+.0f}")

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
    print(f"[FINAL VERDICT] Safe ribbon_flip_price_confirm: False -> True")
    print(f"  OOS positive:      {oos_pos}  (delta={oos_delta:+,.0f})")
    print(f"  WF >= 0.70:        {wf_pass}  (WF={wf_s})")
    print(f"  Sub-window stable: {sw_pass}  (HURT={sub_hurts}/4)")
    print(f"  Anchor OK:         {anchor_ok}  (fails={anchor_fails or 'none'})")
    all_pass = oos_pos and wf_pass and sw_pass and anchor_ok
    print(f"\n  >>> {'PASS — AUTO-RATIFYING' if all_pass else 'FAIL — REJECT'} <<<")
    print(f"{'='*100}")

    if all_pass:
        scorecard_path = ROOT / "analysis" / "recommendations" / "safe-ribbon-flip-confirm.json"
        scorecard = {
            "rule_id": "safe-ribbon-flip-confirm",
            "param": "ribbon_flip_price_confirm",
            "baseline": False, "candidate": True,
            "account": "Gamma-Safe-2 (PA3S2PYAS2WQ)",
            "ratified_date": "2026-06-17",
            "is_n": n_is, "is_delta": is_delta,
            "oos_n": n_oos, "oos_delta": oos_delta,
            "wf_norm": round(wf, 4) if abs(wf) < 1000 else wf,
            "oos_positive": True, "sw_hurt": sub_hurts, "sw_pass": sw_pass,
            "anchor_ok": anchor_ok, "anchor_fails": anchor_fails, "all_gates_pass": True,
            "sub_windows": [{"label": l, "base_pnl": b, "cand_pnl": c, "delta": d, "verdict": v}
                            for l, b, c, d, v in sw_results],
        }
        scorecard_path.parent.mkdir(exist_ok=True)
        scorecard_path.write_text(json.dumps(scorecard, indent=2))
        print(f"\n[AUTO-RATIFY] Scorecard: {scorecard_path}")

        params_path = ROOT / "automation" / "state" / "params.json"
        params = json.loads(params_path.read_text())
        params["ribbon_flip_price_confirm"] = True
        params["_ribbon_flip_price_confirm_doc"] = (
            "RIBBON_FLIP_PRICE_CONFIRM (auto-ratified 2026-06-17): requires price to reverse "
            "past entry_spot before EXIT_ALL_RIBBON_FLIP_BACK fires. Prevents premature runner "
            "exits when ribbon flips but price hasn't moved against position. "
            "Scorecard: analysis/recommendations/safe-ribbon-flip-confirm.json."
        )
        params_path.write_text(json.dumps(params, indent=2))
        print(f"[AUTO-RATIFY] params.json updated: ribbon_flip_price_confirm=True")
    else:
        print(f"\n  ribbon_flip_price_confirm REJECTED. Baseline False stays.")

    print("\nANALYSIS COMPLETE.")
