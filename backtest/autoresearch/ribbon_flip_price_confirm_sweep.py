"""
RIBBON_FLIP_PRICE_CONFIRM EXIT GATE SWEEP (2026-06-17)

Gate: When ribbon flips to opposite stack (spread>=30c), require SPY to also
have moved $0.50 past the entry spot before firing EXIT_ALL_RIBBON_FLIP_BACK.
Default=False (current production). True = hold through premature flip-backs.

Motivation (L128/5/01 anchor): 5/01 engine exited flat at +$3 when ribbon
flipped to BULL while SPY was at 722.84 (only $0.03 above 722.81 entry).
J held to +$470. With price_confirm=True and $0.50 buffer, engine would hold
until SPY >= 722.81+0.50=723.31 — never reached, so position held to +$470.

Hypothesis: gate is regime-agnostic (both bull and volatile regimes show
premature ribbon flip-backs on intraday congestion bars). C22-bypass expected
because this is an exit quality improvement, not an entry filter.

Tested on both accounts:
  SAFE baseline: IS n=123 pnl=+$16,540 | OOS n=20 pnl=+$6,325
  AGG baseline:  IS n=109 pnl=+$19,080 | OOS n=18 pnl=+$3,833
  (ENFORCED-5 baselines, post-all-gates)

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

# SAFE baseline (post-ENFORCED-4, all gates)
SAFE_KW = dict(
    use_real_fills=True,
    no_trade_window=(dt.time(11, 30), dt.time(12, 0)),
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=True,
    premium_stop_pct_bear=-0.10,
    tp1_premium_pct=0.50,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.5,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.30,
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
    block_conf_lvl_rec_afternoon=True,
)
SAFE_OVR = {"vix_bull_max": 18.0}

# AGG baseline (post-ENFORCED-5, all gates)
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
    require_bearish_fill_bar=True,
)
AGG_OVR = {"vix_bull_max": 30.0, "vix_bear_threshold": 15.0, "strike_offset_itm": 2}


def _run(spy_df, vix_df, start, end, kw, ovr, price_confirm):
    kw2 = dict(kw)
    kw2["ribbon_flip_price_confirm"] = price_confirm
    return run_backtest(spy_df, vix_df, start_date=start, end_date=end,
                        params_overrides=dict(ovr), **kw2)


def _pnl(trades):
    return sum(t.dollar_pnl for t in trades)


def _by_date(trades):
    out = {}
    for t in trades:
        et = t.entry_time_et
        d = (et.replace(tzinfo=None) if getattr(et, "tzinfo", None) else et).date()
        out[d] = out.get(d, 0) + t.dollar_pnl
    return out


def _run_account(spy_df, vix_df, label, kw, ovr):
    print(f"\n{'='*70}")
    print(f"  {label}")
    print(f"{'='*70}")

    base_is  = _run(spy_df, vix_df, IS_START, IS_END, kw, ovr, False)
    base_oos = _run(spy_df, vix_df, OOS_START, OOS_END, kw, ovr, False)
    base_is_pnl  = _pnl(base_is.trades)
    base_oos_pnl = _pnl(base_oos.trades)
    base_is_n    = len(base_is.trades)
    base_oos_n   = len(base_oos.trades)
    print(f"  Baseline IS:  n={base_is_n} pnl={base_is_pnl:+,.0f}")
    print(f"  Baseline OOS: n={base_oos_n} pnl={base_oos_pnl:+,.0f}")

    cand_is  = _run(spy_df, vix_df, IS_START, IS_END, kw, ovr, True)
    cand_oos = _run(spy_df, vix_df, OOS_START, OOS_END, kw, ovr, True)
    is_d  = _pnl(cand_is.trades) - base_is_pnl
    oos_d = _pnl(cand_oos.trades) - base_oos_pnl
    print(f"  Candidate IS:  n={len(cand_is.trades)} pnl={_pnl(cand_is.trades):+,.0f} delta={is_d:+,.0f}")
    print(f"  Candidate OOS: n={len(cand_oos.trades)} pnl={_pnl(cand_oos.trades):+,.0f} delta={oos_d:+,.0f}")

    if is_d <= 0:
        print(f"  L155 REJECT: IS_delta={is_d:+,.0f} <= 0")
        return {"account": label, "is_delta": round(is_d, 2), "oos_delta": round(oos_d, 2),
                "verdict": "REJECT_L155"}

    wf = (oos_d / base_oos_n) / (is_d / base_is_n)

    sw_hurt = 0
    sw_rows = []
    for sw_label, s, e in IS_SUBWINDOWS:
        r_sw  = _run(spy_df, vix_df, s, e, kw, ovr, True)
        r_swb = _run(spy_df, vix_df, s, e, kw, ovr, False)
        sw_d = _pnl(r_sw.trades) - _pnl(r_swb.trades)
        hurt = sw_d < -500
        if hurt:
            sw_hurt += 1
        tag = " <-- HURT" if hurt else ""
        print(f"    {sw_label}: base={_pnl(r_swb.trades):+,.0f} cand={_pnl(r_sw.trades):+,.0f} delta={sw_d:+,.0f}{tag}")
        sw_rows.append({"label": sw_label, "delta": round(sw_d, 2), "hurt": hurt})

    base_by = _by_date(base_is.trades)
    cand_by = _by_date(cand_is.trades)
    anchor_ok = all(cand_by.get(d, 0) >= base_by.get(d, 0) - 50 for d in J_WINNERS)

    oos_gate  = "PASS" if oos_d > 0 else "FAIL"
    wf_gate   = "PASS" if wf >= 0.70 else "FAIL"
    sw_gate   = "PASS" if sw_hurt <= 1 else "FAIL"
    anch_gate = "PASS" if anchor_ok else "FAIL"
    gates_all = all(g == "PASS" for g in [oos_gate, wf_gate, sw_gate, anch_gate])

    verdict_parts = []
    if oos_gate == "FAIL": verdict_parts.append("OOS_NEG")
    if wf_gate == "FAIL":  verdict_parts.append(f"WF={wf:.3f}<0.70")
    if sw_gate == "FAIL":  verdict_parts.append(f"SW_hurt={sw_hurt}")
    if anch_gate == "FAIL": verdict_parts.append("ANCHOR_FAIL")
    verdict = "AUTO-RATIFY" if gates_all else ("REJECT " + " ".join(verdict_parts))

    print(f"  WF={wf:.3f} SW_hurt={sw_hurt}/4 ANCHOR={'PASS' if anchor_ok else 'FAIL'}")
    print(f"  VERDICT: {verdict}")

    # J winner P&L on 5/01 specifically (the anchor motivation for this gate)
    may1_base = base_by.get(dt.date(2026, 5, 1), 0)
    may1_cand = cand_by.get(dt.date(2026, 5, 1), 0)
    print(f"  5/01 P&L: baseline={may1_base:+,.0f} candidate={may1_cand:+,.0f} delta={may1_cand-may1_base:+,.0f}")

    return {
        "account": label,
        "is_n": len(cand_is.trades),
        "oos_n": len(cand_oos.trades),
        "is_delta": round(is_d, 2),
        "oos_delta": round(oos_d, 2),
        "wf_norm": round(wf, 3),
        "sw_hurt": sw_hurt,
        "anchor": anch_gate,
        "verdict": verdict.split()[0],
        "may1_baseline": may1_base,
        "may1_candidate": may1_cand,
        "sub_windows": sw_rows,
    }


if __name__ == "__main__":
    print("Loading data...")
    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    results = []
    results.append(_run_account(spy_df, vix_df, "SAFE (post-ENFORCED-4 baseline)", SAFE_KW, SAFE_OVR))
    results.append(_run_account(spy_df, vix_df, "AGG  (post-ENFORCED-5 baseline)", AGG_KW, AGG_OVR))

    print("\n\n=== SUMMARY ===")
    for r in results:
        wf = r.get("wf_norm", "L155")
        print(f"  {r['account']:<45} IS={r['is_delta']:>+8,.0f} OOS={r['oos_delta']:>+8,.0f} WF={wf} -> {r['verdict']}")

    out = {
        "study": "ribbon_flip_price_confirm exit gate sweep",
        "date": "2026-06-17",
        "motivation": (
            "5/01 anchor day: engine exited flat +$3 via EXIT_ALL_RIBBON_FLIP_BACK when "
            "ribbon flipped BULL while SPY only $0.03 above entry (722.84 vs 722.81). "
            "J held to +$470. Gate: require SPY to move $0.50 past entry before ribbon "
            "flip-back exit fires. Hypothesis: regime-agnostic improvement."
        ),
        "gate": "ribbon_flip_price_confirm=True (SPY must move $0.50 past entry before EXIT_ALL_RIBBON_FLIP_BACK)",
        "results": results,
    }
    out_path = ROOT / "analysis" / "recommendations" / "ribbon_flip_price_confirm_sweep.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nSaved: {out_path}")
