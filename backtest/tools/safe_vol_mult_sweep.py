"""f9_vol_mult IS sweep: 1.8, 1.9, 1.95 (task 13ee2df6).

Current production: f9_vol_mult=0.7.
Task asks to test 1.8, 1.9, 1.95 — all are extremely restrictive.

Predicting REJECT: from entry quality miner, vol_ratio<2.0 trades are all positive EV.
Running formally to close task with data.
"""
from __future__ import annotations
import sys, json, datetime as dt
from pathlib import Path
from collections import Counter

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from lib.orchestrator import run_backtest  # noqa
from sniper_matrix import norm_str  # noqa

DATA = REPO / "data"
OUT_PATH = REPO.parent / "analysis" / "recommendations" / "safe_vol_mult_sweep.json"
IS_CUTOFF = dt.date(2026, 2, 27)
MDATES    = {dt.date(2026,5,26), dt.date(2026,5,27), dt.date(2026,5,28), dt.date(2026,5,29)}
ANCHOR_WINNERS = {dt.date(2026,4,29), dt.date(2026,5,1), dt.date(2026,5,4)}
SWEEP_MULTS = [0.7, 1.0, 1.5, 1.8, 1.9, 1.95]
BASELINE_MULT = 0.7

SW_SPLITS = [
    ("SW1_2025H1", dt.date(2025,1,2),  dt.date(2025,6,30)),
    ("SW2_2025H2", dt.date(2025,7,1),  dt.date(2025,12,31)),
    ("SW3_early26",dt.date(2026,1,2),  dt.date(2026,2,26)),
]

SAFE_BASE = dict(
    use_real_fills=True, strike_offset=-2,
    premium_stop_pct_bear=-0.10, premium_stop_pct_bull=-0.08,
    tp1_premium_pct=0.50, tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.5,
    min_triggers_bear=1, min_triggers_bull=2,
    no_trade_before=dt.time(9, 35), no_trade_window=(dt.time(11, 30), dt.time(12, 0)),
    block_level_rejection=True, block_conf_lvl_rec_afternoon=True,
    midday_trendline_gate=True, block_elite_bull=True,
    block_elite_bull_vix_low=15.0, block_elite_bull_vix_high=17.5,
    time_stop_minutes_before_close=20, per_trade_risk_cap_pct=0.3, enable_bullish=True,
    params_overrides={"vix_bear_threshold": 17.3, "vix_bull_hard_cap": 18.0},
)


def stats(ts):
    if not ts:
        return {"n": 0, "wr": 0.0, "avg": 0.0, "total": 0.0}
    pnls = [t.dollar_pnl for t in ts]
    return {"n": len(ts), "wr": round(sum(p > 0 for p in pnls) / len(ts), 3),
            "avg": round(sum(pnls) / len(ts), 1), "total": round(sum(pnls), 1)}


def main():
    print("=" * 70)
    print("SAFE F9_VOL_MULT SWEEP (0.7, 1.0, 1.5, 1.8, 1.9, 1.95)")
    print("=" * 70)

    spy_path = sorted(DATA.glob("spy_5m_2025-01-01_*.csv"),
                      key=lambda p: p.stat().st_size, reverse=True)[0]
    vix_path = DATA / spy_path.name.replace("spy_5m", "vix_5m")
    spy_df = norm_str(pd.read_csv(spy_path))
    vix_df = norm_str(pd.read_csv(vix_path))

    c = Counter(f.name[3:9] for f in (DATA / "options").glob("SPY*.csv"))
    all_fill = sorted({dt.datetime.strptime(k, "%y%m%d").date() for k, v in c.items() if v >= 8})
    spy_dates = set(pd.to_datetime(spy_df["timestamp_et"].str[:10]).dt.date)
    is_days  = [d for d in all_fill if d < IS_CUTOFF and d not in MDATES]
    oos_days = [d for d in all_fill if d >= IS_CUTOFF and d not in MDATES and d in spy_dates]
    print(f"IS: {len(is_days)} days | OOS: {len(oos_days)} days")

    results = {}
    for mult in SWEEP_MULTS:
        print(f"\nRunning f9_vol_mult={mult} IS/OOS...")
        r_is  = run_backtest(spy_df, vix_df, start_date=is_days[0], end_date=is_days[-1],
                             f9_vol_mult=mult, **SAFE_BASE)
        r_oos = run_backtest(spy_df, vix_df, start_date=oos_days[0], end_date=oos_days[-1],
                             f9_vol_mult=mult, **SAFE_BASE)
        anch = round(sum(t.dollar_pnl for t in r_oos.trades if t.entry_time_et.date() in ANCHOR_WINNERS), 1)
        results[mult] = {
            "mult": mult, "is": stats(r_is.trades), "oos": stats(r_oos.trades),
            "anchor": anch, "_is_trades": r_is.trades, "_oos_trades": r_oos.trades,
        }
        print(f"  IS n={results[mult]['is']['n']} WR={results[mult]['is']['wr']:.1%} total={results[mult]['is']['total']:+.0f}")
        print(f"  OOS n={results[mult]['oos']['n']} WR={results[mult]['oos']['wr']:.1%} total={results[mult]['oos']['total']:+.0f} anchor={anch:+.0f}")

    baseline = results[BASELINE_MULT]
    print("\n" + "=" * 70)
    print("GATE EVALUATION vs baseline 0.7")
    gate_rows = []
    best = None
    best_oos = -float("inf")

    for mult, r in sorted(results.items()):
        if mult == BASELINE_MULT:
            continue
        is_d  = round(r["is"]["total"]  - baseline["is"]["total"], 1)
        oos_d = round(r["oos"]["total"] - baseline["oos"]["total"], 1)
        n_rem = baseline["is"]["n"] - r["is"]["n"]

        wf = None
        if n_rem > 0 and is_d != 0:
            n_rem_oos = baseline["oos"]["n"] - r["oos"]["n"]
            if n_rem_oos > 0 and oos_d != 0:
                wf = round((oos_d / n_rem_oos) / (is_d / n_rem), 3) if (is_d / n_rem) != 0 else None

        sw_hurt = 0
        for _, sw_s, sw_e in SW_SPLITS:
            b_sw = sum(t.dollar_pnl for t in baseline["_is_trades"] if sw_s <= t.entry_time_et.date() <= sw_e)
            c_sw = sum(t.dollar_pnl for t in r["_is_trades"] if sw_s <= t.entry_time_et.date() <= sw_e)
            if c_sw < b_sw:
                sw_hurt += 1

        b_anch, c_anch = baseline["anchor"], r["anchor"]
        tol = abs(b_anch) * 0.10 if b_anch != 0 else 0
        g5 = c_anch >= b_anch - tol if b_anch != 0 else c_anch >= 0

        g1, g2, g3, g4 = is_d >= 0, oos_d > 0, wf is not None and wf >= 0.70, sw_hurt <= 1
        passed = g1 and g2 and g3 and g4 and g5
        wf_str = f"{wf:.3f}" if wf is not None else "N/A"
        print(f"\nmult={mult}: IS_delta={is_d:+.0f} OOS_delta={oos_d:+.0f} WF={wf_str} SW_hurt={sw_hurt} anchor={c_anch:+.0f}")
        print(f"  G1={g1} G2={g2} G3={g3} G4={g4} G5={g5} => {'PASS' if passed else 'FAIL'}")
        gate_rows.append({"mult": mult, "is_delta": is_d, "oos_delta": oos_d, "wf": wf,
                          "sw_hurt": sw_hurt, "anchor": c_anch, "passed": passed,
                          "is_stats": r["is"], "oos_stats": r["oos"]})
        if passed and oos_d > best_oos:
            best_oos = oos_d; best = gate_rows[-1]

    print("\n" + "=" * 70)
    verdict = "RATIFY" if best else "REJECT"
    print(f"VERDICT: {verdict}")
    if best:
        print(f"  Best: f9_vol_mult={best['mult']} OOS_delta={best['oos_delta']:+.0f}")

    for r in results.values():
        r.pop("_is_trades", None); r.pop("_oos_trades", None)

    out = {"task": "13ee2df6-vol-mult-sweep", "sweep_mults": SWEEP_MULTS,
           "baseline_mult": BASELINE_MULT,
           "baseline": {"is": baseline["is"], "oos": baseline["oos"], "anchor": baseline["anchor"]},
           "gate_rows": gate_rows, "best_candidate": best, "verdict": verdict}
    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved: {OUT_PATH}")


if __name__ == "__main__":
    raise SystemExit(main())
