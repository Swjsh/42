"""
SAFE WICK_MIN_PCT_OF_RANGE SWEEP (2026-06-17)

Tests whether tightening or loosening the wick rejection quality threshold changes edge.

Current: WICK_MIN_PCT_OF_RANGE = 0.50 (wick must be >= 50% of bar range)
This controls the minimum size of the upper wick relative to the full bar range
for wick_rejection_bearish trigger to fire.

Hypothesis: Stricter wick % (0.60-0.70) may be a STRUCTURAL quality gate:
  - Bigger wicks signal stronger rejection in both IS and OOS regimes
  - Not C22-blocked because quality of the bar, not regime-behavioral
  - Risk: fewer signals, might not remove enough IS losers to improve net

Baseline: ENFORCED-4 active (no_trade_window=11:30-12:00). All 3 enforced gates.

Security: read-only. No Alpaca calls. Free-tier only.
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

# Safe production params — ENFORCED-4 now active (no_trade_window=11:30-12:00)
SAFE_KW = dict(
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
# Current production value — baseline
SAFE_OVR_BASE = {"vix_bull_max": 18.0}

# Wick pct sweep candidates
WICK_PCT_CANDIDATES = [0.30, 0.40, 0.50, 0.60, 0.70]
CURRENT_WICK_PCT = 0.50


def _run(spy_df, vix_df, start, end, wick_pct=CURRENT_WICK_PCT):
    ovr = dict(SAFE_OVR_BASE, wick_min_pct_of_range=wick_pct)
    return run_backtest(spy_df, vix_df, start_date=start, end_date=end,
                        params_overrides=ovr, **SAFE_KW)


def _pnl(trades):
    return sum(t.dollar_pnl for t in trades)


def _by_date(trades):
    out = {}
    for t in trades:
        et = t.entry_time_et
        d = (et.replace(tzinfo=None) if getattr(et, "tzinfo", None) else et).date()
        out[d] = t.dollar_pnl
    return out


if __name__ == "__main__":
    print("Loading data...")
    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    print(f"\nRunning Safe baseline (wick_min_pct={CURRENT_WICK_PCT}, ENFORCED-4 active)...")
    r_is  = _run(spy_df, vix_df, IS_START, IS_END)
    r_oos = _run(spy_df, vix_df, OOS_START, OOS_END)
    base_is_pnl  = _pnl(r_is.trades)
    base_oos_pnl = _pnl(r_oos.trades)
    base_is_n    = len(r_is.trades)
    base_oos_n   = len(r_oos.trades)
    print(f"IS:  n={base_is_n} pnl={base_is_pnl:+,.0f}")
    print(f"OOS: n={base_oos_n} pnl={base_oos_pnl:+,.0f}")

    print(f"\n{'wick_pct':<12} {'IS_d':>8} {'OOS_d':>8} {'WF':>8} {'SW':>4} {'ANC':>5} Verdict")
    print("-" * 70)

    all_results = []
    for wick_pct in WICK_PCT_CANDIDATES:
        if abs(wick_pct - CURRENT_WICK_PCT) < 0.001:
            print(f"\n  {wick_pct:.2f} (current — baseline, skip)")
            continue

        r_is_c  = _run(spy_df, vix_df, IS_START, IS_END, wick_pct=wick_pct)
        r_oos_c = _run(spy_df, vix_df, OOS_START, OOS_END, wick_pct=wick_pct)
        is_pnl  = _pnl(r_is_c.trades)
        oos_pnl = _pnl(r_oos_c.trades)
        is_d    = is_pnl - base_is_pnl
        oos_d   = oos_pnl - base_oos_pnl

        dropped_is  = base_is_n  - len(r_is_c.trades)
        dropped_oos = base_oos_n - len(r_oos_c.trades)
        print(f"\n  wick_pct={wick_pct:.2f}")
        print(f"  IS:  n={base_is_n} -> {len(r_is_c.trades)} (dropped {dropped_is}) pnl={base_is_pnl:+,.0f} -> {is_pnl:+,.0f} delta={is_d:+,.0f}")
        print(f"  OOS: n={base_oos_n} -> {len(r_oos_c.trades)} (dropped {dropped_oos}) pnl={base_oos_pnl:+,.0f} -> {oos_pnl:+,.0f} delta={oos_d:+,.0f}")

        if is_d <= 0:
            print(f"  IS_delta={is_d:+,.0f} <= 0: REJECT (L155)")
            print(f"{wick_pct:<12.2f} {is_d:>+8,.0f} {oos_d:>+8,.0f} {'L155':>8} {'N/A':>4} {'N/A':>5} REJECT(IS_delta<=0)")
            all_results.append({"wick_pct": wick_pct, "is_delta": round(is_d, 2), "oos_delta": round(oos_d, 2), "verdict": "REJECT_L155"})
            continue

        wf_norm = (oos_d / base_oos_n) / (is_d / base_is_n)

        sw_hurt = 0
        for sw_label, s, e in IS_SUBWINDOWS:
            r_sw  = _run(spy_df, vix_df, s, e, wick_pct=wick_pct)
            r_swb = _run(spy_df, vix_df, s, e)
            sw_d  = _pnl(r_sw.trades) - _pnl(r_swb.trades)
            tag   = " <-- HURT" if sw_d < -500 else ""
            print(f"    {sw_label}: base={_pnl(r_swb.trades):+,.0f} cand={_pnl(r_sw.trades):+,.0f} delta={sw_d:+,.0f}{tag}")
            if sw_d < -500:
                sw_hurt += 1

        base_by = _by_date(r_is.trades)
        cand_by = _by_date(r_is_c.trades)
        anchor_ok = all(cand_by.get(d, 0) >= base_by.get(d, 0) - 50 for d in J_WINNERS)

        oos_gate  = "PASS" if oos_pnl > 0 else "FAIL"
        wf_gate   = "PASS" if wf_norm >= 0.70 else "FAIL"
        sw_gate   = "PASS" if sw_hurt <= 1 else "FAIL"
        anch_gate = "PASS" if anchor_ok else "FAIL"

        gates = [oos_gate, wf_gate, sw_gate, anch_gate]
        if all(g == "PASS" for g in gates):
            verdict = "AUTO-RATIFY"
        else:
            fails = []
            if oos_gate == "FAIL": fails.append("OOS_NEG")
            if wf_gate  == "FAIL": fails.append(f"WF={wf_norm:.3f}")
            if sw_gate  == "FAIL": fails.append(f"SW_hurt={sw_hurt}")
            if anch_gate == "FAIL": fails.append("ANCHOR_FAIL")
            verdict = "REJECT " + " ".join(fails)

        print(f"  ANCHOR: {'PASS' if anchor_ok else 'FAIL'}")
        print(f"  GATES: OOS={oos_gate} WF={wf_gate}({wf_norm:.3f}) SW={sw_gate}({sw_hurt}) ANCHOR={anch_gate}")
        print(f"  VERDICT: {verdict}")
        print(f"{wick_pct:<12.2f} {is_d:>+8,.0f} {oos_d:>+8,.0f} {wf_norm:>8.3f} {sw_hurt:>4} {anch_gate:>5} {verdict}")

        all_results.append({
            "wick_pct": wick_pct, "dropped_is": dropped_is, "dropped_oos": dropped_oos,
            "is_n": len(r_is_c.trades), "oos_n": len(r_oos_c.trades),
            "is_pnl": round(is_pnl, 2), "oos_pnl": round(oos_pnl, 2),
            "is_delta": round(is_d, 2), "oos_delta": round(oos_d, 2),
            "wf_norm": round(wf_norm, 3), "sw_hurt": sw_hurt,
            "anchor": anch_gate, "verdict": verdict.split()[0],
        })

    print("\n\n=== SUMMARY ===")
    for r in all_results:
        p, d_is, d_oos = r["wick_pct"], r["is_delta"], r["oos_delta"]
        wf = r.get("wf_norm", "L155")
        v  = r["verdict"]
        print(f"  wick_pct={p:.2f}  IS={d_is:+,.0f} OOS={d_oos:+,.0f} WF={wf} -> {v}")

    out = {
        "study": "Safe wick_min_pct_of_range sweep",
        "date": "2026-06-17",
        "baseline_active_gates": "ENFORCED-4 no_trade_window=11:30-12:00, ENFORCED-1 block_conf_lvl_rec_afternoon, midday_trendline_gate",
        "current_value": CURRENT_WICK_PCT,
        "candidates": WICK_PCT_CANDIDATES,
        "baseline": {"is_n": base_is_n, "is_pnl": round(base_is_pnl, 2),
                     "oos_n": base_oos_n, "oos_pnl": round(base_oos_pnl, 2)},
        "results": all_results,
    }
    out_path = ROOT / "analysis" / "recommendations" / "safe_wick_pct_sweep.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nSaved: {out_path}")
