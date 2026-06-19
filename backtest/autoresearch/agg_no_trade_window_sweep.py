"""
AGG NO_TRADE_WINDOW SWEEP (2026-06-17)

Mirror of safe_no_trade_window_sweep.py for AGG account.
SAFE ENFORCED-4 found 11:30-12:00 AUTO-RATIFY (WF=247.282, IS+$10, OOS+$424).
Question: Does the same structural pattern hold for AGG (ITM-2 strikes, different distribution)?

AGG baseline includes all 3 enforced gates:
  - block_conf_lvl_rec_afternoon=True  (ENFORCED-2)
  - block_conf_lvl_rej_midday_afternoon=True  (ENFORCED-3)
  - midday_trendline_gate=True

Candidates (same windows as Safe sweep):
  1. 11:30-12:00: hypothesis — same structural bad zone
  2. 15:00-15:30: IS n=? avg=? — check if AGG has same late-session pattern
  3. 11:30-13:00: wider lunch block (expected L155)
  4. 11:00-12:00: pre+early lunch (expected L155)

Autorate gates: L155 guard, OOS_positive, WF_norm>=0.70, SW_hurt<=1, ANCHOR PASS.

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

# AGG production params — all 3 enforced gates active, no_trade_window=None (disabled)
AGG_KW = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=True,
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
    block_conf_lvl_rec_afternoon=True,
    block_conf_lvl_rej_midday_afternoon=True,
)
AGG_OVR = {"vix_bull_max": 30.0, "vix_bear_threshold": 15.0, "strike_offset_itm": 2}

CANDIDATES = [
    ("11:30-12:00 (early lunch zone)", dt.time(11, 30), dt.time(12, 0)),
    ("15:00-15:30 (late gamma zone)",  dt.time(15, 0),  dt.time(15, 30)),
    ("11:30-13:00 (full lunch zone)",  dt.time(11, 30), dt.time(13, 0)),
    ("11:00-12:00 (pre+early lunch)",  dt.time(11, 0),  dt.time(12, 0)),
]


def _run(spy_df, vix_df, start, end, no_trade_window=None):
    kw = dict(AGG_KW)
    kw["no_trade_window"] = no_trade_window
    return run_backtest(spy_df, vix_df, start_date=start, end_date=end,
                        params_overrides=dict(AGG_OVR), **kw)


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

    print("\nRunning AGG baseline (all 3 enforced gates, no_trade_window=None)...")
    r_is  = _run(spy_df, vix_df, IS_START, IS_END)
    r_oos = _run(spy_df, vix_df, OOS_START, OOS_END)
    base_is_pnl  = _pnl(r_is.trades)
    base_oos_pnl = _pnl(r_oos.trades)
    base_is_n    = len(r_is.trades)
    base_oos_n   = len(r_oos.trades)
    print(f"IS:  n={base_is_n} pnl={base_is_pnl:+,.0f}")
    print(f"OOS: n={base_oos_n} pnl={base_oos_pnl:+,.0f}")

    print(f"\n{'Window':<36} {'IS_d':>8} {'OOS_d':>8} {'WF':>8} {'SW':>4} {'ANC':>5} Verdict")
    print("-" * 80)

    all_results = []
    for label, win_start, win_end in CANDIDATES:
        r_is_c  = _run(spy_df, vix_df, IS_START, IS_END, no_trade_window=(win_start, win_end))
        r_oos_c = _run(spy_df, vix_df, OOS_START, OOS_END, no_trade_window=(win_start, win_end))
        is_pnl  = _pnl(r_is_c.trades)
        oos_pnl = _pnl(r_oos_c.trades)
        is_d    = is_pnl - base_is_pnl
        oos_d   = oos_pnl - base_oos_pnl

        dropped_is  = base_is_n  - len(r_is_c.trades)
        dropped_oos = base_oos_n - len(r_oos_c.trades)
        print(f"\n  Window: {label}")
        print(f"  IS:  base n={base_is_n} pnl={base_is_pnl:+,.0f} | cand n={len(r_is_c.trades)} pnl={is_pnl:+,.0f} delta={is_d:+,.0f}")
        print(f"  OOS: base n={base_oos_n} pnl={base_oos_pnl:+,.0f} | cand n={len(r_oos_c.trades)} pnl={oos_pnl:+,.0f} delta={oos_d:+,.0f}")
        print(f"  Dropped IS n={dropped_is} | Dropped OOS n={dropped_oos}")

        if is_d <= 0:
            print(f"  IS_delta={is_d:+,.0f} <= 0: REJECT (L155)")
            print(f"{label:<36} {is_d:>+8,.0f} {oos_d:>+8,.0f} {'L155':>8} {'N/A':>4} {'N/A':>5} REJECT(IS_delta<=0)")
            all_results.append({"window": label, "is_delta": round(is_d, 2), "oos_delta": round(oos_d, 2), "verdict": "REJECT_L155"})
            continue

        wf_norm = (oos_d / base_oos_n) / (is_d / base_is_n)

        sw_hurt = 0
        for sw_label, s, e in IS_SUBWINDOWS:
            r_sw  = _run(spy_df, vix_df, s, e, no_trade_window=(win_start, win_end))
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
        print(f"{label:<36} {is_d:>+8,.0f} {oos_d:>+8,.0f} {wf_norm:>8.3f} {sw_hurt:>4} {anch_gate:>5} {verdict}")

        all_results.append({
            "window": label, "win_start": str(win_start), "win_end": str(win_end),
            "dropped_is": dropped_is, "dropped_oos": dropped_oos,
            "is_n": len(r_is_c.trades), "oos_n": len(r_oos_c.trades),
            "is_pnl": round(is_pnl, 2), "oos_pnl": round(oos_pnl, 2),
            "is_delta": round(is_d, 2), "oos_delta": round(oos_d, 2),
            "wf_norm": round(wf_norm, 3), "sw_hurt": sw_hurt,
            "anchor": anch_gate, "verdict": verdict.split()[0],
        })

    print("\n\n=== SUMMARY ===")
    for r in all_results:
        w, d_is, d_oos = r["window"], r["is_delta"], r["oos_delta"]
        wf = r.get("wf_norm", "L155")
        v  = r["verdict"]
        print(f"  {w:<36} IS={d_is:+,.0f} OOS={d_oos:+,.0f} WF={wf} -> {v}")

    out = {
        "study": "AGG no_trade_window sweep",
        "date": "2026-06-17",
        "motivation": "SAFE ENFORCED-4 found 11:30-12:00 AUTO-RATIFY (WF=247.282). Testing if AGG (ITM-2) shows same structural pattern.",
        "baseline": {"is_n": base_is_n, "is_pnl": round(base_is_pnl, 2),
                     "oos_n": base_oos_n, "oos_pnl": round(base_oos_pnl, 2)},
        "results": all_results,
    }
    out_path = ROOT / "analysis" / "recommendations" / "agg_no_trade_window_sweep.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nSaved: {out_path}")
