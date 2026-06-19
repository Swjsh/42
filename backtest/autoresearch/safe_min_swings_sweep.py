"""
SAFE MIN_SWINGS SWEEP (2026-06-17)

Hypothesis: Requiring more trendline touch points filters weak trendlines.
Current: TRENDLINE_MIN_SWINGS=3 (3 descending highs required).
Test: 2 (looser), 3 (baseline), 4, 5 (stricter).

Trendline quality is a structural signal-strength filter, not a direction filter.
May bypass C22 regime split if stronger trendlines are regime-stable.
With midday_trendline_gate=True, only morning trendlines (09:35-11:29) qualify.

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
J_LOSERS  = {dt.date(2026, 5, 5), dt.date(2026, 5, 6)}

SAFE_KW = dict(
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
    block_conf_lvl_rec_afternoon=True,
)
SAFE_OVR = {"vix_bull_max": 18.0}


def _run(spy_df, vix_df, start, end, min_swings=3):
    ovr = dict(SAFE_OVR)
    ovr["trendline_min_swings"] = min_swings
    return run_backtest(spy_df, vix_df, start_date=start, end_date=end,
                        params_overrides=ovr, **SAFE_KW)


def _date(t):
    et = t.entry_time_et
    return (et.replace(tzinfo=None) if getattr(et, "tzinfo", None) else et).date()


def _pnl(trades):
    return sum(t.dollar_pnl for t in trades)


if __name__ == "__main__":
    print("Loading data...")
    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    # Baseline (min_swings=3)
    print("\nBaseline (min_swings=3)...")
    r_is  = _run(spy_df, vix_df, IS_START, IS_END, min_swings=3)
    r_oos = _run(spy_df, vix_df, OOS_START, OOS_END, min_swings=3)
    base_is_pnl  = _pnl(r_is.trades)
    base_oos_pnl = _pnl(r_oos.trades)
    base_is_n    = len(r_is.trades)
    base_oos_n   = len(r_oos.trades)
    print(f"IS:  n={base_is_n} pnl={base_is_pnl:+,.0f}")
    print(f"OOS: n={base_oos_n} pnl={base_oos_pnl:+,.0f}")

    print(f"\n{'Swings':>8} {'IS_n':>5} {'IS_pnl':>9} {'IS_d':>8} {'OOS_n':>5} {'OOS_pnl':>9} {'OOS_d':>8} {'WF':>7} {'SW_hurt':>8} {'Verdict'}")
    print("-" * 90)

    results = []
    for ms in [2, 3, 4, 5]:
        r_is_c  = _run(spy_df, vix_df, IS_START, IS_END, min_swings=ms)
        r_oos_c = _run(spy_df, vix_df, OOS_START, OOS_END, min_swings=ms)
        is_pnl  = _pnl(r_is_c.trades)
        oos_pnl = _pnl(r_oos_c.trades)
        is_d    = is_pnl - base_is_pnl
        oos_d   = oos_pnl - base_oos_pnl
        oos_pos = oos_pnl > 0

        tag = " <-- baseline" if ms == 3 else ""
        if is_d == 0:
            wf_str = "N/A"
            sw_hurt = 0
            verdict = "BASELINE" if ms == 3 else "NO_CHANGE"
        elif is_d <= 0:
            wf_str = "L155"
            sw_hurt = 0
            verdict = "REJECT(IS_delta<=0)"
        else:
            wf_norm = (oos_d / base_oos_n) / (is_d / base_is_n)
            wf_str = f"{wf_norm:.3f}"
            sw_hurt = 0
            for sw_label, s, e in IS_SUBWINDOWS:
                r_sw = _run(spy_df, vix_df, s, e, min_swings=ms)
                r_sw_base = _run(spy_df, vix_df, s, e, min_swings=3)
                sw_d = _pnl(r_sw.trades) - _pnl(r_sw_base.trades)
                if sw_d < -500:
                    sw_hurt += 1
            # Check anchor
            base_by = {_date(t): t.dollar_pnl for t in r_is.trades}
            cand_by = {_date(t): t.dollar_pnl for t in r_is_c.trades}
            anchor_ok = all(cand_by.get(d, 0) >= base_by.get(d, 0) - 50 for d in J_WINNERS)
            oos_gate = "PASS" if oos_pos else "FAIL"
            wf_gate  = "PASS" if wf_norm >= 0.70 else "FAIL"
            sw_gate  = "PASS" if sw_hurt <= 1 else "FAIL"
            anch_gate = "PASS" if anchor_ok else "FAIL"
            if all(g == "PASS" for g in [oos_gate, wf_gate, sw_gate, anch_gate]):
                verdict = "AUTO-RATIFY"
            else:
                parts = [f"OOS={oos_gate}", f"WF={wf_gate}({wf_norm:.3f})", f"SW={sw_gate}({sw_hurt})", f"ANC={anch_gate}"]
                verdict = "REJECT " + " ".join(p for p in parts if "FAIL" in p)

        print(f"{ms:>8} {len(r_is_c.trades):>5} {is_pnl:>+9,.0f} {is_d:>+8,.0f} "
              f"{len(r_oos_c.trades):>5} {oos_pnl:>+9,.0f} {oos_d:>+8,.0f} "
              f"{wf_str:>7} {sw_hurt:>8} {verdict}{tag}")

        results.append({"min_swings": ms, "is_n": len(r_is_c.trades), "is_pnl": round(is_pnl, 2),
                        "is_delta": round(is_d, 2), "oos_n": len(r_oos_c.trades), "oos_pnl": round(oos_pnl, 2),
                        "oos_delta": round(oos_d, 2), "sw_hurt": sw_hurt,
                        "verdict": verdict.split()[0]})

    # Sub-window detail for interesting candidates
    print("\n[SUB-WINDOW DETAIL for min_swings=4 and min_swings=5]")
    for ms in [4, 5]:
        print(f"\n  min_swings={ms}:")
        for sw_label, s, e in IS_SUBWINDOWS:
            r_sw = _run(spy_df, vix_df, s, e, min_swings=ms)
            r_sw_base = _run(spy_df, vix_df, s, e, min_swings=3)
            sw_d = _pnl(r_sw.trades) - _pnl(r_sw_base.trades)
            tag = " <-- HURT" if sw_d < -500 else ""
            print(f"    {sw_label}: base={_pnl(r_sw_base.trades):+,.0f} cand={_pnl(r_sw.trades):+,.0f} delta={sw_d:+,.0f}{tag}")

    out = {"study": "Safe min_swings sweep", "date": "2026-06-17",
           "baseline": {"is_n": base_is_n, "is_pnl": round(base_is_pnl, 2),
                        "oos_n": base_oos_n, "oos_pnl": round(base_oos_pnl, 2)},
           "results": results}
    out_path = ROOT / "analysis" / "recommendations" / "safe_min_swings_sweep.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nSaved: {out_path}")
