"""PART B — forward-validate J's-data optimal STRIKE (B1) / HOLD (B2) / TP (B3) on OUR
2025-26 SPY data with REAL OPRA fills. PART A (j_param_tweaks_partA.py) defined the
candidate values from his Webull winners; this module tests whether each value actually
LIFTS the live edges' OOS expectancy — the anti-overfit guard. A value that is "optimal
on his data" with NO OOS lift here is DEAD, not a win.

DETECTORS (the two live/flip-ready edges this campaign tweaks):
  * gap_and_go            (LIVE bear) — detect_gap_and_go (infinite_ammo_discovery)
  * j_vwap_continuation   (flip-ready) — detect_j_vwap_continuation (j_daily_pattern_ratify)

FILLS: lib.simulator_real.simulate_trade_real — real OPRA bars, causal next-bar-open
entry, v15 exit stack, CHART-STOP ONLY (premium_stop=-0.99, the live first-strike
config per L51/L55/C2). We DO NOT rebuild fills.

SWEEPS (each isolates ONE knob; the other two held at the live baseline so the measured
lift is attributable to that knob alone):
  * B1 STRIKE  — strike target offset in {ITM1:-1, ATM:0, OTM1:+1, OTM2:+2} (the real-OPRA
                 cache is respected: _nearest_cached_strike only returns strikes that
                 actually traded). His-data optimal = OTM1/OTM2.
  * B2 HOLD    — time_stop_et in {11:00, 11:30, 12:00, 13:00, 15:40(baseline), 15:50}.
                 His-data optimal-hold band = ~30-60 min from a morning entry -> early
                 ceilings. Tests whether cutting the tail helps OUR edge.
  * B3 TP1 %   — tp1_premium_pct in {0.10, 0.15, 0.20, 0.30(baseline), 0.50}; tp1 qty
                 fraction held at prod 0.50. His-data median peak gain ~15% -> a LOWER
                 TP1 may bank more winners before the fade.

BASELINE (the live config we compare every sweep point against):
  strike=ATM(0), time_stop=15:40, tp1_pct=0.30, tp1_qty=0.50, runner=2.5x, chart-stop.
  (15:40 is the doctrine intraday flatten reference in the campaign brief; simulate's
  default is 15:50 — both reported for the time-stop sweep.)

VERDICT per (param x detector):
  SHIP  = candidate value beats baseline OOS expectancy AND OOS+ AND WF_median>=0.70 AND
          all-cuts-OOS+ AND DSR not-FAIL AND robust-drop-top5.
  WATCH = beats baseline OOS expectancy AND OOS+ but misses one structural gate (thin).
  DEAD  = no OOS expectancy lift over baseline (overfit to his data / no forward edge).

Pure, $0, read-only. Propose-only (Rule 9). Writes the per-detector/per-param grid into
analysis/recommendations/_j_param_partB.json (consumed by the deliverable builder).

Usage:
  backtest/.venv/Scripts/python.exe backtest/autoresearch/j_param_tweaks_partB.py
"""
from __future__ import annotations

import datetime as dt
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROJECT = REPO.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    load_spy, align_vix, build_day_contexts, detect_gap_and_go,
    _nearest_cached_strike, _quarter,
)
from autoresearch.j_daily_pattern_ratify import detect_j_vwap_continuation  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real, _strike_from_spot  # noqa: E402
from lib.validation.gate import evaluate_candidate  # noqa: E402

SPY = REPO / "data" / "spy_5m_2025-01-01_2026-06-16.csv"
VIX = REPO / "data" / "vix_5m_2025-01-01_2026-06-16.csv"
OUT = PROJECT / "analysis" / "recommendations" / "_j_param_partB.json"

CUT_FRACS = [0.60, 0.70, 0.80]
WF_GATE = 0.70
Q_POS_GATE = 0.60
N_TRIALS_DSR = 40
CHART_STOP = -0.99
PROD_TP1_QTY = 0.50
PROD_RUNNER = 2.5

# Baseline (live) param point. Every sweep compares its candidate values vs THIS.
BASE = {"offset": 0, "time_stop": dt.time(15, 40), "tp1_pct": 0.30}

# Sweep grids (one knob varied at a time)
B1_OFFSETS = {"ITM1": -1, "ATM": 0, "OTM1": 1, "OTM2": 2}
B2_TIMESTOPS = {"11:00": dt.time(11, 0), "11:30": dt.time(11, 30), "12:00": dt.time(12, 0),
                "13:00": dt.time(13, 0), "15:40": dt.time(15, 40), "15:50": dt.time(15, 50)}
B3_TP1 = {"0.10": 0.10, "0.15": 0.15, "0.20": 0.20, "0.30": 0.30, "0.50": 0.50}


def _sim(signals, spy, ribbon, vix, offset, time_stop, tp1_pct):
    rows, cov = [], Counter()
    for sg in signals:
        bar = spy.iloc[sg.bar_idx]
        d = bar["timestamp_et"].date()
        spot = float(bar["close"])
        atm = _strike_from_spot(spot)
        target = atm - offset if sg.side == "P" else atm + offset
        strike = _nearest_cached_strike(d, target, sg.side, 4)
        if strike is None:
            cov["cache_miss"] += 1
            continue
        ev = float(vix.iloc[sg.bar_idx]) if sg.bar_idx < len(vix) else 0.0
        f = simulate_trade_real(
            entry_bar_idx=sg.bar_idx, entry_bar=bar, spy_df=spy, ribbon_df=ribbon,
            rejection_level=sg.stop_level, triggers_fired=[sg.note or "d"], side=sg.side,
            qty=3, setup="JPARAM", strike_override=strike, entry_vix=ev,
            premium_stop_pct=CHART_STOP,
            time_stop_et=time_stop, tp1_premium_pct=tp1_pct,
            tp1_qty_fraction=PROD_TP1_QTY, runner_target_premium_pct=PROD_RUNNER,
        )
        if f is None or f.dollar_pnl is None:
            cov["sim_none"] += 1
            continue
        cov["filled"] += 1
        rows.append({"date": str(d), "side": sg.side, "pnl": round(float(f.dollar_pnl), 2),
                     "pct": round(float(f.pct_return_on_premium), 5),
                     "exit": f.exit_reason.name if f.exit_reason else "NONE"})
    return rows, dict(cov)


def _wf_norm(is_p, n_is, oos_p, n_oos):
    if n_is == 0 or n_oos == 0 or is_p == 0:
        return 0.0
    return (oos_p / n_oos) / (is_p / n_is)


def _metrics(rows, all_dates):
    if not rows:
        return {"n": 0, "exp_dollar": 0.0, "oos_exp_dollar": 0.0, "oos_n": 0,
                "median_wf_norm": 0.0, "all_cuts_oos_positive": False,
                "quarter_positive_fraction": 0.0, "both_dirs_positive": False,
                "robust_to_outliers": False, "dsr_verdict": "UNKNOWN",
                "oos_sign_stable": False, "wr_pct": 0.0, "total_dollar": 0.0}
    pnl = np.array([r["pnl"] for r in rows], float)
    pct = np.array([r["pct"] for r in rows], float)
    n = len(rows)
    wins = int((pnl > 0).sum())
    dated = sorted([(dt.date.fromisoformat(r["date"]), r) for r in rows], key=lambda x: x[0])

    cut70 = all_dates[int(len(all_dates) * 0.70)]
    is70 = [r["pnl"] for dd, r in dated if dd < cut70]
    oos70 = [r["pnl"] for dd, r in dated if dd >= cut70]
    is70p = [r["pct"] for dd, r in dated if dd < cut70]
    oos70p = [r["pct"] for dd, r in dated if dd >= cut70]

    wf_windows = []
    for frac in CUT_FRACS:
        cd = all_dates[int(len(all_dates) * frac)]
        isr = [r["pnl"] for dd, r in dated if dd < cd]
        oosr = [r["pnl"] for dd, r in dated if dd >= cd]
        wf = _wf_norm(sum(isr), len(isr), sum(oosr), len(oosr))
        wf_windows.append({"cut_frac": frac, "oos_n": len(oosr),
                           "oos_total": round(sum(oosr), 2),
                           "oos_exp": round(sum(oosr) / len(oosr), 2) if oosr else 0.0,
                           "wf_norm": round(wf, 3), "oos_positive": bool(sum(oosr) > 0)})
    wf_norms = [w["wf_norm"] for w in wf_windows]
    median_wf = round(statistics.median(wf_norms), 3) if wf_norms else 0.0
    all_oos_pos = all(w["oos_positive"] for w in wf_windows)

    by_q = {}
    for r in rows:
        by_q.setdefault(_quarter(r["date"]), []).append(r["pnl"])
    quarters = {q: round(sum(v) / len(v), 2) for q, v in sorted(by_q.items())}
    q_pos = sum(1 for v in quarters.values() if v > 0)
    q_frac = round(q_pos / len(quarters), 2) if quarters else 0.0

    by_side = {}
    for sd in ("C", "P"):
        s = [r["pnl"] for r in rows if r["side"] == sd]
        if s:
            by_side[sd] = round(sum(s) / len(s), 2)
    both_pos = bool(len(by_side) == 2 and all(v > 0 for v in by_side.values()))

    spnl = np.sort(pnl)
    drop5 = round(float(spnl[:-5].mean()), 2) if n > 5 else None

    dsr = {}
    try:
        if pct.std(ddof=0) > 0 and n >= 2:
            dsr = evaluate_candidate(pct, n_trials=N_TRIALS_DSR).to_dict()
    except Exception as e:  # noqa: BLE001
        dsr = {"verdict": "ERROR", "error": str(e)}

    is_exp_pct = float(np.mean(is70p)) if is70p else 0.0
    oos_exp_pct = float(np.mean(oos70p)) if oos70p else 0.0
    return {
        "n": n, "wins": wins, "wr_pct": round(100 * wins / n, 1),
        "exp_dollar": round(float(pnl.mean()), 2),
        "total_dollar": round(float(pnl.sum()), 2),
        "is_n": len(is70), "oos_n": len(oos70),
        "is_exp_dollar": round(float(np.mean(is70)), 2) if is70 else 0.0,
        "oos_exp_dollar": round(float(np.mean(oos70)), 2) if oos70 else 0.0,
        "oos_sign_stable": bool(is70 and oos70 and is_exp_pct > 0 and oos_exp_pct > 0),
        "wf_windows": wf_windows, "median_wf_norm": median_wf,
        "all_cuts_oos_positive": all_oos_pos,
        "quarters": quarters, "quarter_positive_fraction": q_frac,
        "by_side": by_side, "both_dirs_positive": both_pos,
        "drop_top5_mean_dollar": drop5,
        "robust_to_outliers": bool(n >= 10 and drop5 is not None and drop5 > 0),
        "dsr_verdict": dsr.get("verdict", "UNKNOWN"),
        "exit_hist": dict(Counter(r["exit"] for r in rows)),
    }


def _verdict(cand, base):
    """SHIP/WATCH/DEAD for a candidate value vs the baseline point."""
    lift = round(cand["oos_exp_dollar"] - base["oos_exp_dollar"], 2)
    beats = cand["oos_exp_dollar"] > base["oos_exp_dollar"] and cand["oos_exp_dollar"] > 0
    structural = (cand["median_wf_norm"] >= WF_GATE and cand["all_cuts_oos_positive"]
                  and cand["dsr_verdict"] not in ("FAIL", "ERROR", "UNKNOWN")
                  and cand["robust_to_outliers"]
                  and cand["quarter_positive_fraction"] >= Q_POS_GATE)
    if beats and structural:
        v = "SHIP"
    elif beats and cand["oos_sign_stable"]:
        v = "WATCH"
    else:
        v = "DEAD"
    return {"verdict": v, "oos_lift_vs_baseline_$": lift,
            "beats_baseline_oos": beats, "structural_gates_pass": structural}


DETECTORS = {
    "gap_and_go": lambda spy, ribbon, vix, days: detect_gap_and_go(spy, ribbon, vix, days),
    "j_vwap_continuation": lambda spy, ribbon, vix, days:
        detect_j_vwap_continuation(spy, ribbon, vix, days, breakout_only=False),
}


def main() -> int:
    spy = load_spy(str(SPY))
    vix = align_vix(spy, str(VIX))
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    days = build_day_contexts(spy)
    all_dates = [dc.date for dc in days]

    results = {}
    for dname, detect in DETECTORS.items():
        signals = detect(spy, ribbon, vix, days)
        sc = {"P": sum(1 for s in signals if s.side == "P"),
              "C": sum(1 for s in signals if s.side == "C")}

        # baseline point (shared reference for all three sweeps)
        base_rows, base_cov = _sim(signals, spy, ribbon, vix,
                                   BASE["offset"], BASE["time_stop"], BASE["tp1_pct"])
        base_m = _metrics(base_rows, all_dates)

        # B1 strike sweep (vary offset; hold time_stop+tp1 at baseline)
        b1 = {}
        for name, off in B1_OFFSETS.items():
            r, c = _sim(signals, spy, ribbon, vix, off, BASE["time_stop"], BASE["tp1_pct"])
            m = _metrics(r, all_dates)
            m["coverage"] = c
            m["vs_baseline"] = _verdict(m, base_m)
            b1[name] = m

        # B2 time-stop sweep (vary time_stop; hold offset+tp1 at baseline)
        b2 = {}
        for name, ts in B2_TIMESTOPS.items():
            r, c = _sim(signals, spy, ribbon, vix, BASE["offset"], ts, BASE["tp1_pct"])
            m = _metrics(r, all_dates)
            m["coverage"] = c
            m["vs_baseline"] = _verdict(m, base_m)
            b2[name] = m

        # B3 tp1 sweep (vary tp1_pct; hold offset+time_stop at baseline)
        b3 = {}
        for name, tp in B3_TP1.items():
            r, c = _sim(signals, spy, ribbon, vix, BASE["offset"], BASE["time_stop"], tp)
            m = _metrics(r, all_dates)
            m["coverage"] = c
            m["vs_baseline"] = _verdict(m, base_m)
            b3[name] = m

        results[dname] = {
            "signal_count": len(signals), "side_counts": sc,
            "baseline": {"params": {"offset": BASE["offset"],
                                    "time_stop": str(BASE["time_stop"]),
                                    "tp1_pct": BASE["tp1_pct"]},
                         "metrics": base_m, "coverage": base_cov},
            "B1_strike_sweep": b1,
            "B2_timestop_sweep": b2,
            "B3_tp1_sweep": b3,
        }

    out = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "purpose": "PART B — forward-validate J's-data param optima (strike/hold/TP) on OUR "
                   "SPY 2025-26, real OPRA fills. Each sweep isolates one knob vs the live "
                   "baseline. No OOS lift over baseline => DEAD (overfit).",
        "fills": "lib.simulator_real.simulate_trade_real (real OPRA, causal, chart-stop-only).",
        "baseline_point": {"strike": "ATM(0)", "time_stop": "15:40", "tp1_pct": 0.30,
                           "tp1_qty": PROD_TP1_QTY, "runner": PROD_RUNNER,
                           "premium_stop": CHART_STOP},
        "data": {"spy": SPY.name, "vix": VIX.name, "trading_days": len(all_dates),
                 "date_range": [str(all_dates[0]), str(all_dates[-1])]},
        "verdict_rule": "SHIP=beats-baseline-OOS & OOS+ & WF>=0.70 & all-cuts-OOS+ & DSR "
                        "not-FAIL & drop-top5-robust & q>=60%. WATCH=beats-baseline-OOS & "
                        "OOS-sign-stable but misses a structural gate. DEAD=no OOS lift.",
        "his_data_optima": {
            "B1_strike": "OTM1/OTM2 (sharpest multiple +$38-43/ct; see _j_param_partA.json)",
            "B2_hold": "median peak ~29 min; 50% by 30 min, 70% by 60 min",
            "B3_tp1": "median peak gain ~15%; only 44% reach +20%, 29% reach +30%",
        },
        "detectors": results,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, default=str))

    # ---- console ----
    for dname, db in results.items():
        bm = db["baseline"]["metrics"]
        print(f"\n=== {dname} (signals={db['signal_count']} "
              f"C={db['side_counts']['C']} P={db['side_counts']['P']}) ===")
        print(f"  BASELINE ATM/15:40/tp0.30: n={bm['n']} exp=${bm['exp_dollar']:+.1f} "
              f"WR={bm['wr_pct']}% OOSexp=${bm['oos_exp_dollar']:+.1f}(n={bm['oos_n']}) "
              f"medWF={bm['median_wf_norm']:+.2f} allOOS+={bm['all_cuts_oos_positive']} "
              f"DSR={bm['dsr_verdict']}")
        for label, sweep in (("B1 strike", db["B1_strike_sweep"]),
                             ("B2 time-stop", db["B2_timestop_sweep"]),
                             ("B3 tp1", db["B3_tp1_sweep"])):
            print(f"  [{label}]")
            for name, m in sweep.items():
                v = m["vs_baseline"]
                print(f"    {name:7} n={m['n']:>3} exp=${m['exp_dollar']:+6.1f} "
                      f"OOSexp=${m['oos_exp_dollar']:+6.1f} lift=${v['oos_lift_vs_baseline_$']:+6.1f} "
                      f"medWF={m['median_wf_norm']:+.2f} allOOS+={int(m['all_cuts_oos_positive'])} "
                      f"q+={m['quarter_positive_fraction']:.0%} DSR={m['dsr_verdict'][:4]} "
                      f"-> {v['verdict']}")
    print(f"\nWrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
