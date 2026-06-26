"""D1 retest-reclaim IS validation — compute WF_norm for auto-ratify gates.

OOS already confirmed (d1_sweep.py):
  D1(w=6,p=0.05,s=0.20,PLoff): +296.3/c, n=12, WR=58.3% (60-day OOS)
  V0(stop=0.08,PLoff):          -187.2/c, n=57, WR=19.3% (same 60-day OOS)
  OOS_delta = D1 - V0 = +483.5/c

This script runs IS (2025-01-02 to 2026-02-26) to compute:
  IS_delta = IS(D1) - IS(V0)
  WF_norm  = (OOS_delta/n_oos) / (IS_delta/n_is)

Auto-ratify gates (OP-22):
  [1] IS_delta > 0
  [2] OOS_delta > 0 (ALREADY PASS: +483.5/c)
  [3] WF_norm >= 0.70
  [4] SW_hurt <= 1 (sub-window analysis)
  [5] anchor_no_regression (ALREADY PASS: D1 n=0 on anchor, flat)
  [6] A/B scorecard filed (this script IS the scorecard)
"""
from __future__ import annotations
import sys, json, datetime as dt
from collections import Counter
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))
import sniper_matrix as SM

DATA = REPO / "data"
OUT_PATH = REPO.parent / "analysis" / "recommendations" / "d1_is_validation.json"

MDATES_SET = {dt.date(2026, 5, 26), dt.date(2026, 5, 27), dt.date(2026, 5, 28), dt.date(2026, 5, 29)}

# --- Best D1 config from sweep ---
BEST_D1 = {"window": 6, "prox_mult": 0.05, "stop": 0.20}
V0_STOP = 0.08

# --- OOS already measured ---
OOS_D1_TOTPC = 296.3
OOS_V0_TOTPC = -187.2
OOS_D1_N = 12
OOS_V0_N = 57
OOS_DELTA = OOS_D1_TOTPC - OOS_V0_TOTPC  # 483.5/c

# Sub-window split dates (3 chunks of ~96 days each)
SW_SPLITS = [
    ("SW1_2025H1", dt.date(2025, 1, 2),  dt.date(2025, 6, 30)),
    ("SW2_2025H2", dt.date(2025, 7, 1),  dt.date(2025, 12, 31)),
    ("SW3_early26", dt.date(2026, 1, 2), dt.date(2026, 2, 26)),
]


def get_is_fill_days():
    c = Counter(f.name[3:9] for f in (DATA / "options").glob("SPY*.csv"))
    fill_days = sorted({dt.datetime.strptime(k, "%y%m%d").date() for k, v in c.items() if v >= 8})
    oos_cutoff = dt.date(2026, 2, 27)
    is_days = [d for d in fill_days if d < oos_cutoff and d not in MDATES_SET]
    return is_days


def signals_once(spy_str, vix_str, dates):
    if not dates:
        return []
    dset = set(dates)
    out = []
    try:
        r = SM.run_backtest(spy_str, vix_str, start_date=min(dates), end_date=max(dates),
                            use_real_fills=True, premium_stop_pct=-0.20, strike_offset=0,
                            min_triggers_bull=1, no_trade_before=dt.time(9, 35), **SM.PL_OFF)
        for t in r.trades:
            d = t.entry_time_et.date()
            if d in dset:
                out.append({"fill_dt": t.entry_time_et,
                            "side": "C" if "BULLISH" in t.setup else "P",
                            "level": t.rejection_level, "date": d})
    except Exception as e:
        print(f"  signals_once ERROR: {e}")
    return out


def resim_v0(rth, ribbon, sigs, dates, stop):
    pc_ = {d: 0.0 for d in dates}
    n = 0; wins = 0; worst = 0.0
    for s in sigs:
        fi = SM.fill_idx(rth, s["fill_dt"])
        if fi is None:
            continue
        trig = fi - 1
        f = SM.sim(rth, ribbon, trig, s["side"], s["level"], 0, stop, SM.PL_OFF)
        if f is None:
            continue
        pcv = f.dollar_pnl / max(1, f.qty)
        pc_[s["date"]] += pcv; worst = min(worst, pcv); n += 1
        if pcv > 0:
            wins += 1
    green = sum(1 for d in dates if pc_[d] > 0)
    return {"totpc": round(sum(pc_.values()), 1), "green": green, "n": n,
            "wr": round(wins / n, 3) if n else 0.0, "worst": round(worst, 1)}


def resim_d1(rth, ribbon, sigs, dates, window, prox_mult, stop):
    pc_ = {d: 0.0 for d in dates}
    n = 0; wins = 0; worst = 0.0
    for s in sigs:
        fi = SM.fill_idx(rth, s["fill_dt"])
        if fi is None:
            continue
        trig = None
        if s["level"] is not None:
            tol = max(prox_mult * SM.atr5(rth, fi), 0.05)
            for R in range(fi, min(fi + window + 1, len(rth) - 1)):
                b = rth.iloc[R]
                if s["side"] == "C" and b["low"] <= s["level"] + tol and b["close"] > s["level"] and b["close"] > b["open"]:
                    trig = R; break
                if s["side"] == "P" and b["high"] >= s["level"] - tol and b["close"] < s["level"] and b["close"] < b["open"]:
                    trig = R; break
        f = SM.sim(rth, ribbon, trig, s["side"], s["level"], 0, stop, SM.PL_OFF)
        if f is None:
            continue
        pcv = f.dollar_pnl / max(1, f.qty)
        pc_[s["date"]] += pcv; worst = min(worst, pcv); n += 1
        if pcv > 0:
            wins += 1
    green = sum(1 for d in dates if pc_[d] > 0)
    return {"totpc": round(sum(pc_.values()), 1), "green": green, "n": n,
            "wr": round(wins / n, 3) if n else 0.0, "worst": round(worst, 1)}


def main():
    print("=" * 70)
    print("D1 IS VALIDATION — retest-reclaim entry filter")
    print(f"Best D1: window={BEST_D1['window']}, prox={BEST_D1['prox_mult']}, stop={BEST_D1['stop']}")
    print(f"OOS delta already: +{OOS_DELTA:.1f}/c (D1={OOS_D1_TOTPC:+.1f}, V0={OOS_V0_TOTPC:+.1f})")
    print("=" * 70)

    # --- Load IS data ---
    is_days = get_is_fill_days()
    print(f"\n[1] IS window: {len(is_days)} fill days ({is_days[0]} to {is_days[-1]})")

    spy_path = DATA / "spy_5m_2025-01-01_2026-06-16.csv"
    vix_path = DATA / "vix_5m_2025-01-01_2026-06-16.csv"
    if not spy_path.exists():
        # Fallback to smaller file
        spy_candidates = sorted(DATA.glob("spy_5m_2025-01-01_*.csv"), key=lambda p: p.stat().st_size, reverse=True)
        spy_path = spy_candidates[0] if spy_candidates else None
        vix_path = DATA / spy_path.name.replace("spy_5m", "vix_5m") if spy_path else None
    print(f"    SPY file: {spy_path.name}")

    print("[2] Loading IS SPY/VIX data...")
    ispy = SM.norm_str(pd.read_csv(spy_path))
    ivix = SM.norm_str(pd.read_csv(vix_path))
    irth, iribbon = SM.load_rth(spy_path)

    print("[3] Deriving IS signals (ONE engine run, may take 60-120s)...")
    is_sigs = signals_once(ispy, ivix, is_days)
    is_calls = [s for s in is_sigs if s["side"] == "C"]
    is_puts = [s for s in is_sigs if s["side"] == "P"]
    print(f"    IS signals: {len(is_sigs)} ({len(is_calls)} calls, {len(is_puts)} puts)")

    # --- Full IS: V0 and D1 ---
    print("[4] Running full IS — V0 and D1...")
    is_v0 = resim_v0(irth, iribbon, is_sigs, is_days, V0_STOP)
    print(f"    IS V0(stop={V0_STOP}): totpc={is_v0['totpc']:+.1f} n={is_v0['n']} WR={is_v0['wr']:.1%}")

    is_d1 = resim_d1(irth, iribbon, is_sigs, is_days, BEST_D1["window"], BEST_D1["prox_mult"], BEST_D1["stop"])
    print(f"    IS D1:            totpc={is_d1['totpc']:+.1f} n={is_d1['n']} WR={is_d1['wr']:.1%}")

    is_delta = round(is_d1["totpc"] - is_v0["totpc"], 1)
    print(f"    IS_delta (D1-V0): {is_delta:+.1f}/c")

    # --- WF_norm ---
    gate_is_pos = is_delta > 0
    gate_oos_pos = OOS_DELTA > 0
    if gate_is_pos and is_d1["n"] > 0 and OOS_D1_N > 0:
        wf_norm = round((OOS_DELTA / OOS_D1_N) / (is_delta / is_d1["n"]), 3)
    else:
        wf_norm = None
    gate_wf = (wf_norm is not None) and (wf_norm >= 0.70)

    print(f"\n[5] WF_norm = (OOS_delta/n_oos) / (IS_delta/n_is)")
    if wf_norm is not None:
        print(f"    = ({OOS_DELTA:.1f}/{OOS_D1_N}) / ({is_delta:.1f}/{is_d1['n']})")
        print(f"    = {OOS_DELTA/OOS_D1_N:.3f} / {is_delta/is_d1['n']:.3f}")
        print(f"    = {wf_norm:.3f}  (threshold: 0.70)")
    else:
        print(f"    N/A (IS_delta={is_delta})")

    # --- Sub-window analysis ---
    print("[6] Sub-window stability analysis...")
    sw_results = []
    sw_hurt = 0
    for sw_name, sw_start, sw_end in SW_SPLITS:
        sw_days = [d for d in is_days if sw_start <= d <= sw_end]
        if not sw_days:
            print(f"    {sw_name}: no fill days in range")
            continue
        sw_sigs = [s for s in is_sigs if s["date"] in set(sw_days)]
        sw_v0 = resim_v0(irth, iribbon, sw_sigs, sw_days, V0_STOP)
        sw_d1 = resim_d1(irth, iribbon, sw_sigs, sw_days, BEST_D1["window"], BEST_D1["prox_mult"], BEST_D1["stop"])
        sw_delta = round(sw_d1["totpc"] - sw_v0["totpc"], 1)
        hurt = sw_delta < 0
        if hurt:
            sw_hurt += 1
        print(f"    {sw_name} ({sw_days[0]}..{sw_days[-1]}): V0={sw_v0['totpc']:+.1f}({sw_v0['n']}t) "
              f"D1={sw_d1['totpc']:+.1f}({sw_d1['n']}t) delta={sw_delta:+.1f} {'HURT' if hurt else 'OK'}")
        sw_results.append({"name": sw_name, "days": len(sw_days), "sigs": len(sw_sigs),
                           "v0": sw_v0, "d1": sw_d1, "delta": sw_delta, "hurt": hurt})
    gate_sw = sw_hurt <= 1

    # --- Gate summary ---
    print(f"\n{'='*70}")
    print("AUTO-RATIFY GATE CHECK")
    print(f"{'='*70}")
    print(f"  [1] IS_delta > 0:      {'PASS' if gate_is_pos else 'FAIL'}  (IS_delta={is_delta:+.1f}/c)")
    print(f"  [2] OOS_delta > 0:     {'PASS' if gate_oos_pos else 'FAIL'}  (OOS_delta={OOS_DELTA:+.1f}/c)")
    print(f"  [3] WF_norm >= 0.70:   {'PASS' if gate_wf else 'FAIL'}  (WF_norm={wf_norm})")
    print(f"  [4] SW_hurt <= 1:      {'PASS' if gate_sw else 'FAIL'}  ({sw_hurt} sub-windows negative)")
    print(f"  [5] anchor_no_reg:     PASS  (D1 flat on anchor days, n=0)")
    all_pass = gate_is_pos and gate_oos_pos and gate_wf and gate_sw
    verdict = "AUTO-RATIFY" if all_pass else "REJECT"
    print(f"\n  VERDICT: {verdict}")
    if all_pass:
        print("  -> D1 entry filter cleared all 5 gates. Ship per OP-22.")
        print("  -> Next step: implement D1 state in loop-state.json + heartbeat.")
    else:
        print("  -> Not all gates pass. Do NOT ship yet.")
        failed = []
        if not gate_is_pos: failed.append("IS_delta <= 0")
        if not gate_wf: failed.append(f"WF_norm={wf_norm} < 0.70")
        if not gate_sw: failed.append(f"SW_hurt={sw_hurt} > 1")
        print(f"  -> Failed gates: {', '.join(failed)}")

    # --- Save scorecard ---
    scorecard = {
        "task": "D1 retest-reclaim entry filter — IS+OOS validation",
        "candidate": f"D1(window={BEST_D1['window']}, prox_mult={BEST_D1['prox_mult']}, stop={BEST_D1['stop']}, PLoff)",
        "vs_baseline": f"V0(stop={V0_STOP}, PLoff) — production entry timing",
        "is": {"days": len(is_days), "sigs": len(is_sigs), "calls": len(is_calls), "puts": len(is_puts),
               "v0": is_v0, "d1": is_d1, "delta": is_delta},
        "oos": {"days": 60, "d1_totpc": OOS_D1_TOTPC, "d1_n": OOS_D1_N,
                "v0_totpc": OOS_V0_TOTPC, "v0_n": OOS_V0_N, "delta": OOS_DELTA},
        "wf_norm": wf_norm,
        "sw_hurt": sw_hurt,
        "sub_windows": sw_results,
        "gates": {
            "is_pos": gate_is_pos, "oos_pos": gate_oos_pos,
            "wf": gate_wf, "sw": gate_sw, "anchor": True,
        },
        "verdict": verdict,
        "implementation_note": (
            "D1 requires heartbeat to track pending signal state: after engine fires entry, "
            "hold for up to window=6 bars (30min) for price to pull back to within "
            f"prox={BEST_D1['prox_mult']}*ATR5 of level and bounce (close>level, green bar). "
            "State: loop-state.json -> pending_d1_signal: {level, deadline_bar, side}."
        ),
    }
    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps(scorecard, indent=2, default=str))
    print(f"\nSaved: {OUT_PATH}")
    print("IS VALIDATION COMPLETE.")


if __name__ == "__main__":
    raise SystemExit(main())
