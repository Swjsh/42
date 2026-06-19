"""
AGG POST-ENFORCED-5 NO_TRADE_WINDOW SWEEP (2026-06-17)

KEY INSIGHT: ENFORCED-5 (fill bar gate) changed the character of the AGG lunch zone.
BEFORE ENFORCED-5: 11:30-12:00 AGG = IS_delta=-261 when blocked (trades were profitable)
AFTER ENFORCED-5:  11:30-12:00 AGG = IS n=10 avg=-$48 total=-$484 (now losses!)

The fill bar gate removed the bullish-fill-bar trades that made lunch profitable.
Now a lunch-zone no_trade_window gate might pass for AGG.

Baseline: ENFORCED-5 (all 5 gates including require_bearish_fill_bar=True)
  IS n=109 pnl=+$19,080 | OOS n=18 pnl=+$3,833

Candidates (each adds a no_trade_window on top of ENFORCED-5 baseline):
  A. (11:30, 12:00) — exact ENFORCED-4 analog (IS n=10 avg=-48 were losses after fill-bar gate)
  B. (11:30, 13:00) — extended lunch zone (IS n=14 total=-1358, OOS n=1 avg=-232)
  C. (12:30, 13:00) — just the 12:30-13:00 window (IS n=2 avg=-105, OOS n=1 avg=-232 BOTH BAD)
  D. (15:00, 15:30) — late gamma (IS n=10 avg=-72, OOS n=1 avg=+34)

L155 guard: if IS_delta <= 0 → REJECT immediately.
WF_norm formula: (OOS_delta/n_oos) / (IS_delta/n_is) — only valid when IS_delta > 0.
Autorate gates: OOS_positive AND WF>=0.70 AND SW_hurt<=1 AND anchor_no_regression.

Security: read-only, no Alpaca calls, no production writes.
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

# ENFORCED-5 baseline (all 5 gates)
BASE_KW = dict(
    use_real_fills=True,
    no_trade_window=None,            # baseline has no lunch blackout
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
    require_bearish_fill_bar=True,   # ENFORCED-5
)
BASE_OVR = {"vix_bull_max": 30.0, "vix_bear_threshold": 15.0, "strike_offset_itm": 2}

CANDIDATES = [
    ("(11:30-12:00) ENFORCED-4 analog", dt.time(11, 30), dt.time(12, 0)),
    ("(11:30-13:00) extended lunch",    dt.time(11, 30), dt.time(13, 0)),
    ("(12:30-13:00) post-lunch dip",    dt.time(12, 30), dt.time(13, 0)),
    ("(15:00-15:30) late gamma",        dt.time(15, 0),  dt.time(15, 30)),
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

    print("\nRunning ENFORCED-5 baseline...")
    base_is  = run_backtest(spy_df, vix_df, IS_START, IS_END,
                            params_overrides=dict(BASE_OVR), **BASE_KW)
    base_oos = run_backtest(spy_df, vix_df, OOS_START, OOS_END,
                            params_overrides=dict(BASE_OVR), **BASE_KW)
    base_is_pnl  = _pnl(base_is.trades)
    base_oos_pnl = _pnl(base_oos.trades)
    base_is_n    = len(base_is.trades)
    base_oos_n   = len(base_oos.trades)
    print(f"  IS:  n={base_is_n} pnl={base_is_pnl:+,.0f}")
    print(f"  OOS: n={base_oos_n} pnl={base_oos_pnl:+,.0f}")

    all_results = []
    for label, w_start, w_end in CANDIDATES:
        print(f"\n{'='*65}")
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
            all_results.append({
                "window": label,
                "is_delta": round(is_d, 2),
                "oos_delta": round(oos_d, 2),
                "dropped_is": d_is_n,
                "dropped_oos": d_oos_n,
                "verdict": "REJECT_L155",
            })
            continue

        wf = (oos_d / base_oos_n) / (is_d / base_is_n)

        # Sub-window hurt check
        sw_hurt = 0
        sw_rows = []
        for sw_label, s, e in IS_SUBWINDOWS:
            r_sw  = _run(spy_df, vix_df, s, e, (w_start, w_end))
            r_swb = run_backtest(spy_df, vix_df, start_date=s, end_date=e,
                                 params_overrides=dict(BASE_OVR), **BASE_KW)
            sw_d = _pnl(r_sw.trades) - _pnl(r_swb.trades)
            hurt = sw_d < -500
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

        verdict_parts = []
        if oos_gate == "FAIL":
            verdict_parts.append("OOS_NEG")
        if wf_gate == "FAIL":
            verdict_parts.append(f"WF={wf:.3f}<0.70")
        if sw_gate == "FAIL":
            verdict_parts.append(f"SW_hurt={sw_hurt}")
        if anch_gate == "FAIL":
            verdict_parts.append("ANCHOR_FAIL")
        verdict = "AUTO-RATIFY" if gates_all else ("REJECT " + " ".join(verdict_parts))

        print(f"  WF={wf:.3f} SW_hurt={sw_hurt}/4 ANCHOR={'PASS' if anchor_ok else 'FAIL'}")
        print(f"  VERDICT: {verdict}")

        all_results.append({
            "window": label,
            "win_start": str(w_start),
            "win_end": str(w_end),
            "is_n": len(r_is.trades),
            "oos_n": len(r_oos.trades),
            "dropped_is": d_is_n,
            "dropped_oos": d_oos_n,
            "is_delta": round(is_d, 2),
            "oos_delta": round(oos_d, 2),
            "wf_norm": round(wf, 3),
            "sw_hurt": sw_hurt,
            "anchor": anch_gate,
            "verdict": verdict.split()[0],
            "sub_windows": sw_rows,
        })

    print("\n\n=== SUMMARY (vs ENFORCED-5 baseline) ===")
    for r in all_results:
        wf = r.get("wf_norm", "L155")
        print(f"  {r['window']:<35} IS={r['is_delta']:>+8,.0f} OOS={r['oos_delta']:>+8,.0f} WF={wf} SW={r.get('sw_hurt','N/A')} -> {r['verdict']}")

    out = {
        "study": "AGG no_trade_window sweep post-ENFORCED-5",
        "date": "2026-06-17",
        "motivation": (
            "ENFORCED-5 fill bar gate changed AGG 11:30-12:00 from profitable to negative. "
            "Pre-ENFORCED-5: blocking 11:30-12:00 gave IS_delta=-261 (REJECT L155). "
            "Post-ENFORCED-5: 11:30-12:00 IS n=10 avg=-48 total=-484. "
            "Testing whether lunch-zone gate now passes autorate criteria."
        ),
        "baseline": {
            "label": "ENFORCED-5 (all 5 AGG gates including require_bearish_fill_bar)",
            "is_n": base_is_n, "is_pnl": round(base_is_pnl, 2),
            "oos_n": base_oos_n, "oos_pnl": round(base_oos_pnl, 2),
        },
        "results": all_results,
    }
    out_path = ROOT / "analysis" / "recommendations" / "agg_post_enforced5_ntw_sweep.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nSaved: {out_path}")
