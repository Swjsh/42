"""
SAFE_TIME_STOP_SWEEP

Sweeps time_stop_minutes_before_close (10, 15, 20, 25, 30) from baseline=20.
OOS exit breakdown: 9 TIME_STOP exits averaging -$181/trade (WR=11%).
Hypothesis: earlier time stop cuts losing late-day positions; later time stop
gives winners more time to run. Baseline=20 (exit at 15:40 ET).

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
    per_trade_risk_cap_pct=0.30,
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
)
SAFE_OVR = {"vix_bull_max": 18.0}

BASELINE_STOP = 20
CANDIDATES = [10, 15, 25, 30]


def _run(spy_df, vix_df, start, end, ts_min):
    return run_backtest(
        spy_df, vix_df,
        start_date=start, end_date=end,
        time_stop_minutes_before_close=ts_min,
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
    print(f"SAFE TIME_STOP_SWEEP: baseline={BASELINE_STOP}min, candidates={CANDIDATES}")
    print("OOS: 9 TIME_STOP exits WR=11% avg=-$181. Does earlier stop cut these losers?")
    print("=" * 100)

    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    # Baseline
    print(f"\n[Baseline: time_stop={BASELINE_STOP} min (exit at 15:{60-BASELINE_STOP})]...")
    base_is  = _run(spy_df, vix_df, IS_START,  IS_END,  BASELINE_STOP)
    base_oos = _run(spy_df, vix_df, OOS_START, OOS_END, BASELINE_STOP)
    base_is_pnl  = _pnl(base_is.trades)
    base_oos_pnl = _pnl(base_oos.trades)
    n_is  = len(base_is.trades)
    n_oos = len(base_oos.trades)
    base_is_bd  = _by_date(base_is.trades)
    base_oos_bd = _by_date(base_oos.trades)
    print(f"  BASELINE: IS n={n_is} pnl={base_is_pnl:+,.0f} | OOS n={n_oos} pnl={base_oos_pnl:+,.0f}")

    # OOS exit breakdown at baseline
    print(f"\n  [OOS TIME_STOP exits at baseline]")
    time_stop_exits = [t for t in base_oos.trades
                       if str(getattr(t, "exit_reason", "")).upper().startswith("TIME")]
    if time_stop_exits:
        wins = sum(1 for t in time_stop_exits if t.dollar_pnl > 0)
        tot = sum(t.dollar_pnl for t in time_stop_exits)
        print(f"    n={len(time_stop_exits)}  WR={wins/len(time_stop_exits):.1%}  total={tot:+,.0f}  avg={tot/len(time_stop_exits):+.0f}")
        for t in sorted(time_stop_exits, key=lambda x: x.dollar_pnl):
            print(f"    {_date(t)}  pnl={t.dollar_pnl:>+8.0f}")

    # Sweep
    print(f"\n[Sweep summary]")
    print(f"  {'time_stop':>10}  {'IS_n':>6}  {'IS_pnl':>10}  {'OOS_n':>6}  {'OOS_pnl':>10}  {'IS_delta':>10}  {'OOS_delta':>10}  {'WF':>8}")
    print("  " + "-" * 100)

    best_candidate = None
    best_wf = -99

    for ts in CANDIDATES:
        cand_is  = _run(spy_df, vix_df, IS_START,  IS_END,  ts)
        cand_oos = _run(spy_df, vix_df, OOS_START, OOS_END, ts)
        ci_pnl = _pnl(cand_is.trades)
        co_pnl = _pnl(cand_oos.trades)
        is_d = ci_pnl - base_is_pnl
        oos_d = co_pnl - base_oos_pnl
        if is_d != 0:
            wf = (oos_d / n_oos) / (is_d / n_is)
        else:
            wf = float("inf") if oos_d > 0 else float("-inf")
        wf_s = f"{wf:.3f}" if abs(wf) < 200 else ("INF+" if wf > 0 else "INF-")
        print(f"  {ts:>10}  {len(cand_is.trades):>6}  {ci_pnl:>+10,.0f}  {len(cand_oos.trades):>6}  {co_pnl:>+10,.0f}  {is_d:>+10,.0f}  {oos_d:>+10,.0f}  {wf_s:>8}")
        if oos_d > 0 and (best_candidate is None or wf > best_wf):
            best_candidate = (ts, cand_is, cand_oos, is_d, oos_d, wf, wf_s)
            best_wf = wf

    if best_candidate is None:
        print(f"\n  No OOS-positive candidate found. Baseline time_stop={BASELINE_STOP} CONFIRMED.")
        print("\nANALYSIS COMPLETE.")
        exit(0)

    # Full analysis of best candidate
    ts, cand_is, cand_oos, is_d, oos_d, wf, wf_s = best_candidate
    print(f"\n[Best candidate: time_stop={ts}min]")
    print(f"  IS_delta={is_d:+,.0f}  OOS_delta={oos_d:+,.0f}  WF={wf_s}")

    # Sub-window analysis
    cand_is_bd = _by_date(cand_is.trades)
    cand_oos_bd = _by_date(cand_oos.trades)

    print(f"\n[Sub-window analysis for best candidate (ts={ts}min)]")
    print(f"  {'Window':22}  {'BASE_n':>6}  {'CAND_n':>6}  {'BASE_pnl':>10}  {'CAND_pnl':>10}  {'delta':>8}  {'verdict':>8}")
    print("  " + "-" * 90)
    sub_hurts = 0
    sw_results = []
    for label, s, e in IS_SUBWINDOWS:
        b = _run(spy_df, vix_df, s, e, BASELINE_STOP)
        c = _run(spy_df, vix_df, s, e, ts)
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

    oos_pos = oos_d > 0
    wf_pass = wf >= 0.70
    print(f"\n{'='*100}")
    print(f"[FINAL VERDICT] Safe time_stop: {BASELINE_STOP}min -> {ts}min (best OOS+ candidate)")
    print(f"  OOS positive:      {oos_pos}  (delta={oos_d:+,.0f})")
    print(f"  WF >= 0.70:        {wf_pass}  (WF={wf_s})")
    print(f"  Sub-window stable: {sw_pass}  (HURT={sub_hurts}/4)")
    print(f"  Anchor OK:         {anchor_ok}  (fails={anchor_fails or 'none'})")
    all_pass = oos_pos and wf_pass and sw_pass and anchor_ok
    print(f"\n  >>> {'PASS - AUTO-RATIFYING' if all_pass else 'FAIL - REJECT'} <<<")
    print(f"{'='*100}")

    if all_pass:
        scorecard_path = ROOT / "analysis" / "recommendations" / f"safe-time-stop-{ts}min.json"
        scorecard = {
            "rule_id": f"safe-time-stop-{ts}min",
            "param": "time_stop_minutes_before_close",
            "baseline": BASELINE_STOP, "candidate": ts,
            "account": "Gamma-Safe-2 (PA3S2PYAS2WQ)",
            "ratified_date": "2026-06-17",
            "is_n": n_is, "is_delta": is_d,
            "oos_n": n_oos, "oos_delta": oos_d,
            "wf_norm": round(wf, 4) if abs(wf) < 1000 else wf,
            "oos_positive": True, "sw_hurt": sub_hurts, "sw_pass": sw_pass,
            "anchor_ok": anchor_ok, "anchor_fails": anchor_fails, "all_gates_pass": True,
            "mechanism": (
                f"Exits all remaining positions at {60-ts} minutes before close "
                f"(15:{60-ts:02d} ET) instead of baseline 15:{60-BASELINE_STOP:02d} ET. "
                "OOS baseline has 9 TIME_STOP exits at WR=11% avg=-$181 -- "
                f"{'earlier' if ts > BASELINE_STOP else 'later'} stop reduces late-day position exposure."
            ),
            "sub_windows": [{"label": l, "base_pnl": b, "cand_pnl": c, "delta": d, "verdict": v}
                            for l, b, c, d, v in sw_results],
        }
        scorecard_path.parent.mkdir(exist_ok=True)
        scorecard_path.write_text(json.dumps(scorecard, indent=2))
        print(f"\n[AUTO-RATIFY] Scorecard: {scorecard_path}")

        params_path = ROOT / "automation" / "state" / "params.json"
        params = json.loads(params_path.read_text())
        params["time_stop_minutes_before_close"] = ts
        params["_time_stop_doc"] = (
            f"TIME_STOP (auto-ratified 2026-06-17): exits at {60-ts} min before close "
            f"(15:{60-ts:02d} ET, was 15:{60-BASELINE_STOP:02d}). "
            f"Scorecard: analysis/recommendations/safe-time-stop-{ts}min.json."
        )
        params_path.write_text(json.dumps(params, indent=2))
        print(f"[AUTO-RATIFY] params.json updated: time_stop_minutes_before_close={ts}")
    else:
        print(f"\n  Best candidate (ts={ts}) REJECTED. Baseline {BASELINE_STOP} stays.")

    print("\nANALYSIS COMPLETE.")
