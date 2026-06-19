"""
PROFIT LOCK SWEEP (2026-06-17)

Tests whether enabling profit_lock_threshold_pct=0.05, mode='trailing', trail_pct=0.20
(v15 production config per params.json v15_* fields) improves backtest performance
vs the current off-state baseline.

Context: _params_to_kwargs() has no mapping for v15_profit_lock_* keys, so all
backtests run with profit_lock=off even though heartbeat.md describes this rule.
Original T50 test (2026-05-13) showed trailing 20% barely beats (+0.5%) but that
was pre-ENFORCED baseline. Current post-ENFORCED-5 baseline may differ.

Candidates tested:
  1. baseline: off (threshold=0.0)
  2. v15 production: threshold=0.05, mode='trailing', trail=0.20
  3. aggressive trail:  threshold=0.05, mode='trailing', trail=0.15
  4. conservative:      threshold=0.10, mode='trailing', trail=0.20
  5. pure trail (no threshold): threshold=0.0, mode='trailing', trail=0.20

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

CANDIDATES = [
    # (name, profit_lock kwargs)
    # Heartbeat spec: arm=+5%, initial floor=+10%, trail=20% off HWM
    ("OFF (baseline)",
     {"profit_lock_threshold_pct": 0.0,  "profit_lock_stop_offset_pct": 0.0,
      "profit_lock_mode": "fixed",    "profit_lock_trail_pct": 0.0}),
    ("v15 prod: thr=0.05 floor=0.10 trail=0.20",
     {"profit_lock_threshold_pct": 0.05, "profit_lock_stop_offset_pct": 0.10,
      "profit_lock_mode": "trailing", "profit_lock_trail_pct": 0.20}),
    ("trail tighter: thr=0.05 floor=0.10 trail=0.15",
     {"profit_lock_threshold_pct": 0.05, "profit_lock_stop_offset_pct": 0.10,
      "profit_lock_mode": "trailing", "profit_lock_trail_pct": 0.15}),
    ("threshold higher: thr=0.10 floor=0.10 trail=0.20",
     {"profit_lock_threshold_pct": 0.10, "profit_lock_stop_offset_pct": 0.10,
      "profit_lock_mode": "trailing", "profit_lock_trail_pct": 0.20}),
    ("pure trail no threshold: thr=0 floor=0 trail=0.20",
     {"profit_lock_threshold_pct": 0.0,  "profit_lock_stop_offset_pct": 0.0,
      "profit_lock_mode": "trailing", "profit_lock_trail_pct": 0.20}),
]


def _run(spy_df, vix_df, start, end, kw, ovr, pl_kw):
    k = dict(kw)
    k.update(pl_kw)
    return run_backtest(spy_df, vix_df, start_date=start, end_date=end,
                        params_overrides=dict(ovr), **k)


def _pnl(trades):
    return sum(t.dollar_pnl for t in trades)


def _by_date(trades):
    out = {}
    for t in trades:
        et = t.entry_time_et
        d = (et.replace(tzinfo=None) if getattr(et, "tzinfo", None) else et).date()
        out[d] = out.get(d, 0) + t.dollar_pnl
    return out


def _sweep_account(spy_df, vix_df, label, kw, ovr):
    print(f"\n{'='*70}")
    print(f"  {label}")
    print(f"{'='*70}")

    base_pl_kw = CANDIDATES[0][1]
    base_is  = _run(spy_df, vix_df, IS_START, IS_END, kw, ovr, base_pl_kw)
    base_oos = _run(spy_df, vix_df, OOS_START, OOS_END, kw, ovr, base_pl_kw)
    base_is_pnl = _pnl(base_is.trades)
    base_oos_pnl = _pnl(base_oos.trades)
    base_is_n = len(base_is.trades)
    base_oos_n = len(base_oos.trades)
    base_by = _by_date(base_is.trades)
    print(f"  Baseline OFF: IS n={base_is_n} pnl={base_is_pnl:+,.0f} | OOS n={base_oos_n} pnl={base_oos_pnl:+,.0f}")

    results = []
    for cname, pl_kw in CANDIDATES[1:]:
        cand_is  = _run(spy_df, vix_df, IS_START, IS_END, kw, ovr, pl_kw)
        cand_oos = _run(spy_df, vix_df, OOS_START, OOS_END, kw, ovr, pl_kw)
        is_d  = _pnl(cand_is.trades) - base_is_pnl
        oos_d = _pnl(cand_oos.trades) - base_oos_pnl

        wf = (oos_d / base_oos_n) / (is_d / base_is_n) if is_d > 0 else float("nan")
        wf_str = f"{wf:.3f}" if wf == wf else "NaN"

        sw_hurts = 0
        sw_results = []
        for sw_label, s, e in IS_SUBWINDOWS:
            b_sw = _run(spy_df, vix_df, s, e, kw, ovr, base_pl_kw)
            c_sw = _run(spy_df, vix_df, s, e, kw, ovr, pl_kw)
            sw_d = _pnl(c_sw.trades) - _pnl(b_sw.trades)
            sw_v = "HURT" if sw_d < -500 else ("HELP" if sw_d > 100 else "neutral")
            if sw_v == "HURT":
                sw_hurts += 1
            sw_results.append((sw_label, _pnl(b_sw.trades), _pnl(c_sw.trades), sw_d, sw_v))

        cand_by = _by_date(cand_is.trades)
        anchor_fails = []
        for d in sorted(J_WINNERS):
            bp = base_by.get(d, 0.0)
            cp = cand_by.get(d, 0.0)
            if bp > 0 and cp < bp * 0.90:
                anchor_fails.append(str(d))

        oos_pos = oos_d > 0
        wf_pass = wf >= 0.70 if wf == wf else False
        sw_pass = sw_hurts <= 1
        anc_ok  = len(anchor_fails) == 0
        l155_ok = is_d > 0

        if not l155_ok:
            gate = "L155"
        elif not oos_pos:
            gate = "OOS_NEG"
        elif not wf_pass:
            gate = "WF_LOW"
        elif not sw_pass:
            gate = "SW_HURT"
        elif not anc_ok:
            gate = "ANCHOR_FAIL"
        else:
            gate = "PASS"

        print(f"  {cname:40} IS_d={is_d:>+9,.0f} OOS_d={oos_d:>+9,.0f} WF={wf_str:>7} SW={sw_hurts}/4 anc={'OK' if anc_ok else 'FAIL'} -> {gate}")
        for sw in sw_results:
            print(f"    {sw[0]:22}  base={sw[1]:>+10,.0f}  cand={sw[2]:>+10,.0f}  d={sw[3]:>+8,.0f}  {sw[4]}")

        results.append({
            "name": cname,
            "pl_kw": {k: round(v, 4) if isinstance(v, float) else v for k, v in pl_kw.items()},
            "is_pnl": round(_pnl(cand_is.trades), 2),
            "oos_pnl": round(_pnl(cand_oos.trades), 2),
            "is_delta": round(is_d, 2),
            "oos_delta": round(oos_d, 2),
            "wf_norm": round(wf, 3) if wf == wf else "NaN",
            "sw_hurt": sw_hurts,
            "anchor_fails": anchor_fails,
            "gate": gate,
        })

    return {
        "account": label,
        "baseline_is_pnl": round(base_is_pnl, 2),
        "baseline_oos_pnl": round(base_oos_pnl, 2),
        "candidates": results,
    }


if __name__ == "__main__":
    print("Loading data...")
    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    account_results = []
    account_results.append(_sweep_account(spy_df, vix_df, "SAFE (post-ENFORCED-4)", SAFE_KW, SAFE_OVR))
    account_results.append(_sweep_account(spy_df, vix_df, "AGG  (post-ENFORCED-5)", AGG_KW, AGG_OVR))

    out = {
        "study": "profit_lock_sweep",
        "date": "2026-06-17",
        "motivation": (
            "v15 params.json has v15_profit_lock_threshold_pct=0.05, mode='trailing', trail=0.20 "
            "but _params_to_kwargs has no mapping — all backtests run with profit_lock=off. "
            "Original T50 test pre-dates ENFORCED gates. This sweep checks post-ENFORCED baselines."
        ),
        "results": account_results,
    }
    out_path = ROOT / "analysis" / "recommendations" / "profit_lock_sweep.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nSaved: {out_path}")
