"""SAFE premium_stop_pct_bear sweep: -0.12 to -0.05.

Current production: -0.10. AGG found -0.07 RATIFIABLE.
Hypothesis: tighter stop improves WR for OTM-2 strikes (lower delta, less room to run).

Sweep values: -0.12, -0.10 (baseline), -0.09, -0.08, -0.07, -0.06, -0.05
For each candidate vs -0.10 baseline, evaluate OP-22 gates.

Auto-ratify the BEST candidate if ALL gates pass.
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
OUT_PATH = REPO.parent / "analysis" / "recommendations" / "safe_stop_sweep.json"
BASELINE_STOP = -0.10
SWEEP_STOPS = [-0.12, -0.10, -0.09, -0.08, -0.07, -0.06, -0.05]

IS_CUTOFF    = dt.date(2026, 2, 27)
MDATES_SET   = {dt.date(2026,5,26), dt.date(2026,5,27), dt.date(2026,5,28), dt.date(2026,5,29)}
ANCHOR_WINNERS = {dt.date(2026,4,29), dt.date(2026,5,1), dt.date(2026,5,4)}

SW_SPLITS = [
    ("SW1_2025H1", dt.date(2025,1,2),  dt.date(2025,6,30)),
    ("SW2_2025H2", dt.date(2025,7,1),  dt.date(2025,12,31)),
    ("SW3_early26",dt.date(2026,1,2),  dt.date(2026,2,26)),
]

SAFE_BASE = dict(
    use_real_fills=True, strike_offset=-2,
    premium_stop_pct_bull=-0.08,
    tp1_premium_pct=0.50, tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.5, f9_vol_mult=0.7,
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
        return {"n": 0, "wr": 0.0, "avg": 0.0, "total": 0.0, "sharpe": 0.0}
    pnls = [t.dollar_pnl for t in ts]
    n = len(pnls)
    mu = sum(pnls) / n
    if n > 1:
        var = sum((p - mu) ** 2 for p in pnls) / (n - 1)
        std = var ** 0.5
        sharpe = (mu / std) * (252 ** 0.5) if std > 0 else 0.0
    else:
        sharpe = 0.0
    return {
        "n": n,
        "wr": round(sum(p > 0 for p in pnls) / n, 3),
        "avg": round(mu, 1),
        "total": round(sum(pnls), 1),
        "sharpe": round(sharpe, 3),
    }


def anchor_sum(ts):
    return round(sum(t.dollar_pnl for t in ts if t.entry_time_et.date() in ANCHOR_WINNERS), 1)


def main():
    print("=" * 70)
    print("SAFE PREMIUM_STOP_PCT_BEAR SWEEP")
    print("=" * 70)

    spy_path = sorted(DATA.glob("spy_5m_2025-01-01_*.csv"),
                      key=lambda p: p.stat().st_size, reverse=True)[0]
    vix_path = DATA / spy_path.name.replace("spy_5m", "vix_5m")
    spy_df = norm_str(pd.read_csv(spy_path))
    vix_df = norm_str(pd.read_csv(vix_path))

    c = Counter(f.name[3:9] for f in (DATA / "options").glob("SPY*.csv"))
    all_fill = sorted({dt.datetime.strptime(k, "%y%m%d").date() for k, v in c.items() if v >= 8})
    spy_dates = set(pd.to_datetime(spy_df["timestamp_et"].str[:10]).dt.date)
    is_days  = [d for d in all_fill if d < IS_CUTOFF and d not in MDATES_SET]
    oos_days = [d for d in all_fill if d >= IS_CUTOFF and d not in MDATES_SET and d in spy_dates]
    print(f"IS: {len(is_days)} days | OOS: {len(oos_days)} days")

    results = {}
    for stop in SWEEP_STOPS:
        label = f"stop_{abs(int(stop*100)):02d}"
        print(f"\nRunning stop={stop} IS...")
        r_is  = run_backtest(spy_df, vix_df, start_date=is_days[0], end_date=is_days[-1],
                             premium_stop_pct_bear=stop, **SAFE_BASE)
        print(f"Running stop={stop} OOS...")
        r_oos = run_backtest(spy_df, vix_df, start_date=oos_days[0], end_date=oos_days[-1],
                             premium_stop_pct_bear=stop, **SAFE_BASE)
        results[stop] = {
            "stop": stop, "label": label,
            "is": stats(r_is.trades), "oos": stats(r_oos.trades),
            "anchor": anchor_sum(r_oos.trades),
            "_is_trades": r_is.trades, "_oos_trades": r_oos.trades,
        }
        print(f"  IS n={results[stop]['is']['n']} WR={results[stop]['is']['wr']:.1%} "
              f"total={results[stop]['is']['total']:+.0f} sharpe={results[stop]['is']['sharpe']:.2f}")
        print(f"  OOS n={results[stop]['oos']['n']} WR={results[stop]['oos']['wr']:.1%} "
              f"total={results[stop]['oos']['total']:+.0f} sharpe={results[stop]['oos']['sharpe']:.2f}")
        print(f"  Anchor: {results[stop]['anchor']:+.0f}")

    baseline = results[BASELINE_STOP]

    print("\n" + "=" * 70)
    print("GATE EVALUATION vs BASELINE stop=-0.10")
    print("=" * 70)
    print(f"BASELINE: IS n={baseline['is']['n']} WR={baseline['is']['wr']:.1%} "
          f"total={baseline['is']['total']:+.0f}  OOS n={baseline['oos']['n']} "
          f"WR={baseline['oos']['wr']:.1%} total={baseline['oos']['total']:+.0f}")
    print(f"  Anchor: {baseline['anchor']:+.0f}")

    best_candidate = None
    best_oos_delta = -float("inf")

    gate_rows = []
    for stop, r in sorted(results.items()):
        if stop == BASELINE_STOP:
            continue
        is_delta  = round(r["is"]["total"]  - baseline["is"]["total"], 1)
        oos_delta = round(r["oos"]["total"] - baseline["oos"]["total"], 1)
        n_lost_is  = baseline["is"]["n"]  - r["is"]["n"]
        n_lost_oos = baseline["oos"]["n"] - r["oos"]["n"]

        if n_lost_is > 0 and is_delta != 0 and n_lost_oos > 0 and oos_delta != 0:
            per_is  = is_delta  / n_lost_is
            per_oos = oos_delta / n_lost_oos
            wf = round(per_oos / per_is, 3) if per_is != 0 else None
        else:
            wf = None

        sw_hurt = 0
        for _, sw_s, sw_e in SW_SPLITS:
            b_sw = sum(t.dollar_pnl for t in baseline["_is_trades"]
                       if sw_s <= t.entry_time_et.date() <= sw_e)
            c_sw = sum(t.dollar_pnl for t in r["_is_trades"]
                       if sw_s <= t.entry_time_et.date() <= sw_e)
            if c_sw < b_sw:
                sw_hurt += 1

        b_anch = baseline["anchor"]
        c_anch = r["anchor"]
        tol = abs(b_anch) * 0.10 if b_anch != 0 else 0
        g5 = c_anch >= b_anch - tol if b_anch != 0 else c_anch >= 0

        g1 = is_delta >= 0
        g2 = oos_delta > 0
        g3 = wf is not None and wf >= 0.70
        g4 = sw_hurt <= 1
        passed = g1 and g2 and g3 and g4 and g5

        wf_str = f"{wf:.3f}" if wf is not None else "N/A"
        print(f"\nstop={stop}: IS_delta={is_delta:+.0f} OOS_delta={oos_delta:+.0f} "
              f"WF={wf_str} SW_hurt={sw_hurt} anchor={c_anch:+.0f}")
        print(f"  Gates G1={g1} G2={g2} G3={g3} G4={g4} G5={g5} => {'PASS' if passed else 'FAIL'}")

        gate_rows.append({
            "stop": stop, "is_delta": is_delta, "oos_delta": oos_delta,
            "wf": wf, "sw_hurt": sw_hurt, "anchor": c_anch,
            "g1": g1, "g2": g2, "g3": g3, "g4": g4, "g5": g5, "passed": passed,
            "is_stats": r["is"], "oos_stats": r["oos"],
        })

        if passed and oos_delta > best_oos_delta:
            best_oos_delta = oos_delta
            best_candidate = gate_rows[-1]

    print("\n" + "=" * 70)
    if best_candidate:
        print(f"BEST CANDIDATE: stop={best_candidate['stop']} OOS_delta={best_candidate['oos_delta']:+.0f}")
        print("AUTO-RATIFY: Updating automation/state/params.json")
        params_path = REPO.parent / "automation" / "state" / "params.json"
        params = json.loads(params_path.read_bytes().decode("utf-8", errors="replace"))
        old_stop = params.get("premium_stop_pct_bear", params.get("premium_stop", None))
        params["premium_stop_pct_bear"] = best_candidate["stop"]
        params_path.write_bytes(json.dumps(params, indent=2).encode("utf-8"))
        print(f"  params.json: premium_stop_pct_bear {old_stop} -> {best_candidate['stop']}")
        verdict = "RATIFY"
    else:
        print("NO CANDIDATE PASSED ALL GATES — REJECT")
        verdict = "REJECT"

    # clean up non-serializable _*_trades
    for r in results.values():
        r.pop("_is_trades", None)
        r.pop("_oos_trades", None)

    out = {
        "task": "2dc133a8-safe-stop-sweep",
        "sweep_stops": SWEEP_STOPS,
        "baseline_stop": BASELINE_STOP,
        "baseline": {"is": baseline["is"], "oos": baseline["oos"], "anchor": baseline["anchor"]},
        "gate_rows": gate_rows,
        "best_candidate": best_candidate,
        "verdict": verdict,
        "auto_ratified": best_candidate is not None,
        "ratify_action": (f"premium_stop_pct_bear set to {best_candidate['stop']} in automation/state/params.json"
                          if best_candidate else None),
    }
    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved: {OUT_PATH}")


if __name__ == "__main__":
    raise SystemExit(main())
