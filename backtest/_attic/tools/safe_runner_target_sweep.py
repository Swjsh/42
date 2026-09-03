"""SAFE runner_target_premium_pct IS sweep.

C30 compliance: audit exit-type FIRST (what % of exits actually hit runner target?).
If runner_target is a dead knob (almost never hit), sweeping it is pointless.

Sweep values: [1.5, 2.0, 2.5 (baseline), 3.0, 3.5, 4.0]
Report per value:
  - IS total/WR/Sharpe
  - % exits that hit runner_target vs time_stop vs stop_loss
  - edge_capture on anchor winners (4/29, 5/01, 5/04)

Auto-ratify if OOS delta > 0, WF >= 0.70, anchor no-regression, SW_hurt <= 1.
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
OUT_PATH = REPO.parent / "analysis" / "recommendations" / "safe_runner_sweep.json"

BASELINE_RUNNER = 2.5
SWEEP_RUNNERS = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
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
    premium_stop_pct_bear=-0.10, premium_stop_pct_bull=-0.08,
    tp1_premium_pct=0.50, tp1_qty_fraction=0.667,
    f9_vol_mult=0.7,
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
    return {"n": n, "wr": round(sum(p > 0 for p in pnls) / n, 3),
            "avg": round(mu, 1), "total": round(sum(pnls), 1), "sharpe": round(sharpe, 3)}


def exit_audit(ts):
    """Classify exits: runner_target, stop_loss, time_stop, tp1_only, other."""
    if not ts:
        return {}
    cats = Counter()
    for t in ts:
        exit_type = getattr(t, "exit_reason", None) or getattr(t, "exit_type", None)
        if exit_type is None:
            pnl = t.dollar_pnl
            entry_prem = getattr(t, "entry_premium", None) or getattr(t, "avg_entry_price", None)
            exit_prem  = getattr(t, "exit_premium", None)  or getattr(t, "avg_exit_price", None)
            if entry_prem and exit_prem and entry_prem != 0:
                mult = exit_prem / entry_prem
                if mult >= 2.0:
                    exit_type = "runner_target"
                elif pnl < 0:
                    exit_type = "stop_loss"
                else:
                    exit_type = "time_stop"
            else:
                exit_type = "other"
        cats[str(exit_type)] += 1
    total = sum(cats.values())
    return {k: {"n": v, "pct": round(v / total, 3)} for k, v in cats.most_common()}


def anchor_sum(ts):
    return round(sum(t.dollar_pnl for t in ts if t.entry_time_et.date() in ANCHOR_WINNERS), 1)


def main():
    print("=" * 70)
    print("SAFE RUNNER_TARGET_PREMIUM_PCT IS SWEEP  (C30 exit audit)")
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
    for runner in SWEEP_RUNNERS:
        label = f"runner_{int(runner*10):02d}"
        print(f"\nRunning runner={runner} IS...")
        r_is  = run_backtest(spy_df, vix_df, start_date=is_days[0], end_date=is_days[-1],
                             runner_target_premium_pct=runner, **SAFE_BASE)
        print(f"Running runner={runner} OOS...")
        r_oos = run_backtest(spy_df, vix_df, start_date=oos_days[0], end_date=oos_days[-1],
                             runner_target_premium_pct=runner, **SAFE_BASE)
        ea = exit_audit(r_is.trades)
        results[runner] = {
            "runner": runner, "label": label,
            "is": stats(r_is.trades), "oos": stats(r_oos.trades),
            "anchor": anchor_sum(r_oos.trades),
            "exit_audit": ea,
            "_is_trades": r_is.trades, "_oos_trades": r_oos.trades,
        }
        print(f"  IS n={results[runner]['is']['n']} WR={results[runner]['is']['wr']:.1%} "
              f"total={results[runner]['is']['total']:+.0f} sharpe={results[runner]['is']['sharpe']:.2f}")
        print(f"  OOS n={results[runner]['oos']['n']} WR={results[runner]['oos']['wr']:.1%} "
              f"total={results[runner]['oos']['total']:+.0f} sharpe={results[runner]['oos']['sharpe']:.2f}")
        print(f"  Anchor: {results[runner]['anchor']:+.0f}")
        if ea:
            print(f"  Exit types: {ea}")

    baseline = results[BASELINE_RUNNER]

    print("\n" + "=" * 70)
    print("C30 EXIT AUDIT (baseline -2.5x):")
    for k, v in baseline["exit_audit"].items():
        print(f"  {k}: n={v['n']} ({v['pct']:.1%})")

    print("\nGATE EVALUATION vs BASELINE runner=2.5")
    print(f"BASELINE: IS n={baseline['is']['n']} total={baseline['is']['total']:+.0f}  "
          f"OOS n={baseline['oos']['n']} total={baseline['oos']['total']:+.0f}")

    best_candidate = None
    best_oos_delta = -float("inf")
    gate_rows = []

    for runner, r in sorted(results.items()):
        if runner == BASELINE_RUNNER:
            continue
        is_delta  = round(r["is"]["total"]  - baseline["is"]["total"], 1)
        oos_delta = round(r["oos"]["total"] - baseline["oos"]["total"], 1)
        n_changed_is  = abs(baseline["is"]["n"]  - r["is"]["n"])
        n_changed_oos = abs(baseline["oos"]["n"] - r["oos"]["n"])

        if n_changed_is > 0 and is_delta != 0 and n_changed_oos > 0 and oos_delta != 0:
            per_is  = is_delta  / n_changed_is
            per_oos = oos_delta / n_changed_oos
            wf = round(per_oos / per_is, 3) if per_is != 0 else None
        else:
            wf = round(oos_delta / is_delta, 3) if is_delta != 0 else None

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
        print(f"\nrunner={runner}: IS_delta={is_delta:+.0f} OOS_delta={oos_delta:+.0f} "
              f"WF={wf_str} SW_hurt={sw_hurt} anchor={c_anch:+.0f}")
        print(f"  Gates G1={g1} G2={g2} G3={g3} G4={g4} G5={g5} => {'PASS' if passed else 'FAIL'}")

        gate_rows.append({
            "runner": runner, "is_delta": is_delta, "oos_delta": oos_delta,
            "wf": wf, "sw_hurt": sw_hurt, "anchor": c_anch,
            "g1": g1, "g2": g2, "g3": g3, "g4": g4, "g5": g5, "passed": passed,
            "is_stats": r["is"], "oos_stats": r["oos"],
            "exit_audit": r["exit_audit"],
        })

        if passed and oos_delta > best_oos_delta:
            best_oos_delta = oos_delta
            best_candidate = gate_rows[-1]

    print("\n" + "=" * 70)
    if best_candidate:
        print(f"BEST CANDIDATE: runner={best_candidate['runner']} OOS_delta={best_candidate['oos_delta']:+.0f}")
        print("AUTO-RATIFY: Updating automation/state/params.json")
        params_path = REPO.parent / "automation" / "state" / "params.json"
        params = json.loads(params_path.read_bytes().decode("utf-8", errors="replace"))
        old_runner = params.get("runner_target_premium_pct", None)
        params["runner_target_premium_pct"] = best_candidate["runner"]
        params_path.write_bytes(json.dumps(params, indent=2).encode("utf-8"))
        print(f"  params.json: runner_target_premium_pct {old_runner} -> {best_candidate['runner']}")
        verdict = "RATIFY"
    else:
        print("NO CANDIDATE PASSED ALL GATES — REJECT (baseline 2.5 stands)")
        verdict = "REJECT"

    # strip non-serializable before saving
    for r in results.values():
        r.pop("_is_trades", None)
        r.pop("_oos_trades", None)

    out = {
        "task": "fa1e568f-runner-target-sweep",
        "sweep_runners": SWEEP_RUNNERS,
        "baseline_runner": BASELINE_RUNNER,
        "baseline": {"is": baseline["is"], "oos": baseline["oos"], "anchor": baseline["anchor"],
                     "exit_audit": baseline["exit_audit"]},
        "gate_rows": gate_rows,
        "best_candidate": best_candidate,
        "verdict": verdict,
        "auto_ratified": best_candidate is not None,
        "c30_note": "C30: if runner_target almost never hit, sweeping it is pointless (dead knob). Check exit_audit for runner_target hit rate.",
    }
    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved: {OUT_PATH}")


if __name__ == "__main__":
    raise SystemExit(main())
