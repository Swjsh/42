"""
SAFE NO_TRADE_WINDOW V2 SWEEP (2026-06-17)

Post-ENFORCED-4 follow-up:
  Baseline: ENFORCED-4 already gates signal bars 11:30-12:00 ET.
  Finding: 12:00-12:30 window still has IS n=3 avg=-$258 (100% stop), OOS n=1 avg=-$232.
  Both negative — NOT C22 inverted (same structural lunch-zone problem).

Candidates:
  A. (11:30, 12:30) — extend window by 30 min (block signals 12:00-12:30 additionally)
  B. (11:30, 13:00) — extend by 60 min (check if 12:30-13:00 also bad)
  C. (15:00, 15:30) — late gamma zone (OOS n=0 → WF=0, included for completeness)

Note: for candidates B+C, the no_trade_window kwarg only accepts one (start, end) tuple.
For testing multiple windows, we test them individually against the ENFORCED-4 baseline.

Baseline: SAFE params + no_trade_window=(11:30, 12:00) [ENFORCED-4]
All candidates replace/extend the window start/end.

Security: read-only. No Alpaca calls. No production writes.
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

IS_SUBWINDOWS = [
    ("W1 Jan-Jun 2025", dt.date(2025, 1, 2),  dt.date(2025, 6, 30)),
    ("W2 Jul-Dec 2025", dt.date(2025, 7, 1),  dt.date(2025, 12, 31)),
    ("W3 Jan-Mar 2026", dt.date(2026, 1, 2),  dt.date(2026, 3, 31)),
    ("W4 Apr-May 2026", dt.date(2026, 4, 1),  dt.date(2026, 5, 7)),
]

J_WINNERS = {dt.date(2026, 4, 29), dt.date(2026, 5, 1), dt.date(2026, 5, 4)}

# -----------------------------------------------------------------------
# ENFORCED-4 BASELINE (production since 2026-06-17)
# -----------------------------------------------------------------------
BASE_KW = dict(
    use_real_fills=True,
    no_trade_window=(dt.time(11, 30), dt.time(12, 0)),  # ENFORCED-4
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
    block_conf_lvl_rec_afternoon=True,
)
BASE_OVR = {"vix_bull_max": 18.0}

# Candidates (new window replacing ENFORCED-4's (11:30, 12:00))
CANDIDATES = [
    ("(11:30-12:30) extend 30min",  dt.time(11, 30), dt.time(12, 30)),
    ("(11:30-13:00) extend 60min",  dt.time(11, 30), dt.time(13, 0)),
    ("(15:00-15:30) late gamma",    dt.time(15, 0),  dt.time(15, 30)),
]


def _run(spy_df, vix_df, start, end, window):
    kw = dict(BASE_KW)
    kw["no_trade_window"] = window
    return run_backtest(spy_df, vix_df, start_date=start, end_date=end,
                        params_overrides=dict(BASE_OVR), **kw)


def _pnl(trades):
    return sum(t.dollar_pnl for t in trades)


def _by_date(trades):
    out = {}
    for t in trades:
        et = t.entry_time_et
        d = (et.replace(tzinfo=None) if getattr(et, "tzinfo", None) else et).date()
        out[d] = out.get(d, 0) + t.dollar_pnl
    return out


if __name__ == "__main__":
    print("Loading data...")
    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    # Baseline = ENFORCED-4
    print("\nRunning ENFORCED-4 baseline (11:30-12:00)...")
    base_is  = _run(spy_df, vix_df, IS_START, IS_END, (dt.time(11, 30), dt.time(12, 0)))
    base_oos = _run(spy_df, vix_df, OOS_START, OOS_END, (dt.time(11, 30), dt.time(12, 0)))
    base_is_pnl  = _pnl(base_is.trades)
    base_oos_pnl = _pnl(base_oos.trades)
    base_is_n  = len(base_is.trades)
    base_oos_n = len(base_oos.trades)
    print(f"  IS:  n={base_is_n} pnl={base_is_pnl:+,.0f}")
    print(f"  OOS: n={base_oos_n} pnl={base_oos_pnl:+,.0f}")

    all_results = []
    for label, w_start, w_end in CANDIDATES:
        print(f"\n{'='*60}")
        print(f"Testing: {label}")

        r_is  = _run(spy_df, vix_df, IS_START, IS_END, (w_start, w_end))
        r_oos = _run(spy_df, vix_df, OOS_START, OOS_END, (w_start, w_end))
        is_d  = _pnl(r_is.trades) - base_is_pnl
        oos_d = _pnl(r_oos.trades) - base_oos_pnl
        d_is_n  = base_is_n  - len(r_is.trades)
        d_oos_n = base_oos_n - len(r_oos.trades)

        print(f"  IS:  {base_is_n}->{len(r_is.trades)} (dropped {d_is_n}) delta={is_d:+,.0f}")
        print(f"  OOS: {base_oos_n}->{len(r_oos.trades)} (dropped {d_oos_n}) delta={oos_d:+,.0f}")

        if is_d <= 0:
            print(f"  L155 REJECT: IS_delta={is_d:+,.0f} <= 0")
            all_results.append({"window": label, "is_delta": round(is_d, 2), "oos_delta": round(oos_d, 2),
                                 "dropped_is": d_is_n, "dropped_oos": d_oos_n, "verdict": "REJECT_L155"})
            continue

        wf = (oos_d / base_oos_n) / (is_d / base_is_n)

        # Sub-window hurt check
        sw_hurt = 0
        sw_rows = []
        for sw_label, s, e in IS_SUBWINDOWS:
            r_sw  = _run(spy_df, vix_df, s, e, (w_start, w_end))
            r_swb = _run(spy_df, vix_df, s, e, (dt.time(11, 30), dt.time(12, 0)))
            sw_d  = _pnl(r_sw.trades) - _pnl(r_swb.trades)
            hurt  = sw_d < -500
            if hurt:
                sw_hurt += 1
            tag = " <-- HURT" if hurt else ""
            print(f"    {sw_label}: base={_pnl(r_swb.trades):+,.0f} cand={_pnl(r_sw.trades):+,.0f} delta={sw_d:+,.0f}{tag}")
            sw_rows.append({"label": sw_label, "delta": round(sw_d, 2), "hurt": hurt})

        # Anchor check
        base_by = _by_date(base_is.trades)
        cand_by = _by_date(r_is.trades)
        anchor_ok = all(cand_by.get(d, 0) >= base_by.get(d, 0) - 50 for d in J_WINNERS)

        oos_gate  = "PASS" if oos_d > 0 else "FAIL"
        wf_gate   = "PASS" if wf >= 0.70 else "FAIL"
        sw_gate   = "PASS" if sw_hurt <= 1 else "FAIL"
        anch_gate = "PASS" if anchor_ok else "FAIL"
        gates_all = all(g == "PASS" for g in [oos_gate, wf_gate, sw_gate, anch_gate])
        verdict = "AUTO-RATIFY" if gates_all else (
            "REJECT " + " ".join([
                "OOS_NEG" if oos_gate == "FAIL" else "",
                f"WF={wf:.3f}" if wf_gate == "FAIL" else "",
                f"SW_hurt={sw_hurt}" if sw_gate == "FAIL" else "",
                "ANCHOR_FAIL" if anch_gate == "FAIL" else "",
            ]).strip()
        )

        print(f"  WF={wf:.3f} SW_hurt={sw_hurt} ANCHOR={'PASS' if anchor_ok else 'FAIL'}")
        print(f"  VERDICT: {verdict}")

        all_results.append({
            "window": label, "win_start": str(w_start), "win_end": str(w_end),
            "is_n": len(r_is.trades), "oos_n": len(r_oos.trades),
            "dropped_is": d_is_n, "dropped_oos": d_oos_n,
            "is_delta": round(is_d, 2), "oos_delta": round(oos_d, 2),
            "wf_norm": round(wf, 3), "sw_hurt": sw_hurt,
            "anchor": anch_gate, "verdict": verdict.split()[0],
            "sub_windows": sw_rows,
        })

    print("\n\n=== SUMMARY (vs ENFORCED-4 baseline) ===")
    for r in all_results:
        wf = r.get("wf_norm", "L155")
        print(f"  {r['window']:<36} IS={r['is_delta']:>+8,.0f} OOS={r['oos_delta']:>+8,.0f} WF={wf} SW={r.get('sw_hurt','N/A')} -> {r['verdict']}")

    out = {
        "study": "Safe no_trade_window V2 sweep (vs ENFORCED-4 baseline)",
        "date": "2026-06-17",
        "motivation": "time_distribution_audit post-ENFORCED-4: 12:00-12:30 IS n=3 avg=-258 100%stop, OOS n=1 avg=-232. Structural lunch zone continues past 12:00.",
        "baseline": {
            "window": "11:30-12:00 (ENFORCED-4)",
            "is_n": base_is_n, "is_pnl": round(base_is_pnl, 2),
            "oos_n": base_oos_n, "oos_pnl": round(base_oos_pnl, 2),
        },
        "results": all_results,
    }
    out_path = ROOT / "analysis" / "recommendations" / "safe_no_trade_window_v2_sweep.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nSaved: {out_path}")
