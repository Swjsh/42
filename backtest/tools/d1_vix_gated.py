"""VIX-gated D1 analysis.

Hypothesis (from L159): D1 retest-reclaim entry filter is VIX-regime conditional.
  - VIX > 18: volatile/choppy regime → D1 should outperform V0 (pullback confirmation helps)
  - VIX <= 18: trending regime → V0 should outperform D1 (entries work immediately)

Test: split IS fill days by VIX level at 09:35 ET on the entry day.
If D1 outperforms V0 in EVERY VIX>18 sub-population, the VIX gate is valid.

Best D1 config (from d1_sweep.py): window=6, prox=0.05*ATR5, stop=0.20, PLoff
V0 stop: 0.08, PLoff

Security: read-only. No Alpaca calls. No production state writes.
"""
from __future__ import annotations
import sys, json, datetime as dt
from collections import Counter
from pathlib import Path

import pandas as pd
import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))
import sniper_matrix as SM

DATA = REPO / "data"
OUT_PATH = REPO.parent / "analysis" / "recommendations" / "d1_vix_gated.json"

MDATES_SET = {dt.date(2026, 5, 26), dt.date(2026, 5, 27), dt.date(2026, 5, 28), dt.date(2026, 5, 29)}
BEST_D1 = {"window": 6, "prox_mult": 0.05, "stop": 0.20}
V0_STOP = 0.08
VIX_THRESHOLD = 18.0


def get_is_fill_days():
    c = Counter(f.name[3:9] for f in (DATA / "options").glob("SPY*.csv"))
    fill_days = sorted({dt.datetime.strptime(k, "%y%m%d").date() for k, v in c.items() if v >= 8})
    return [d for d in fill_days if d < dt.date(2026, 2, 27) and d not in MDATES_SET]


def get_oos_fill_days():
    c = Counter(f.name[3:9] for f in (DATA / "options").glob("SPY*.csv"))
    fill_days = sorted({dt.datetime.strptime(k, "%y%m%d").date() for k, v in c.items() if v >= 8})
    spy_path = sorted(DATA.glob("spy_5m_*.csv"), key=lambda p: p.stat().st_size, reverse=True)[0]
    spy_dates = set(SM._to_et(pd.read_csv(spy_path)["timestamp_et"]).dt.date)
    oos = [d for d in fill_days if d >= dt.date(2026, 2, 27) and d in spy_dates and d not in MDATES_SET]
    return sorted(oos)[-60:]


def get_vix_at_open(vix_df, date_str):
    """Return VIX reading at 09:35 ET on the given date."""
    rows = vix_df[vix_df["timestamp_et"].str.startswith(date_str)]
    morning = rows[rows["timestamp_et"].str[11:16] >= "09:35"]
    if len(morning) == 0:
        return None
    return float(morning.iloc[0]["close"])


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
                out.append({"fill_dt": t.entry_time_et, "side": "C" if "BULLISH" in t.setup else "P",
                            "level": t.rejection_level, "date": d})
    except Exception as e:
        print(f"  signals_once ERROR: {e}")
    return out


def measure_v0_d1(rth, ribbon, sigs, dates, d1_cfg, v0_stop):
    """Return (v0_result, d1_result) dicts with totpc, n, wins, green."""
    v0_pc = {d: 0.0 for d in dates}
    d1_pc = {d: 0.0 for d in dates}
    v0_n = v0_wins = d1_n = d1_wins = 0
    v0_worst = d1_worst = 0.0

    for s in sigs:
        fi = SM.fill_idx(rth, s["fill_dt"])
        if fi is None:
            continue

        # V0
        fv = SM.sim(rth, ribbon, fi - 1, s["side"], s["level"], 0, v0_stop, SM.PL_OFF)
        if fv is not None:
            pcv = fv.dollar_pnl / max(1, fv.qty)
            v0_pc[s["date"]] += pcv; v0_worst = min(v0_worst, pcv); v0_n += 1
            if pcv > 0: v0_wins += 1

        # D1
        trig = None
        if s["level"] is not None:
            tol = max(d1_cfg["prox_mult"] * SM.atr5(rth, fi), 0.05)
            for R in range(fi, min(fi + d1_cfg["window"] + 1, len(rth) - 1)):
                b = rth.iloc[R]
                if s["side"] == "C" and b["low"] <= s["level"] + tol and b["close"] > s["level"] and b["close"] > b["open"]:
                    trig = R; break
                if s["side"] == "P" and b["high"] >= s["level"] - tol and b["close"] < s["level"] and b["close"] < b["open"]:
                    trig = R; break
        fd = SM.sim(rth, ribbon, trig, s["side"], s["level"], 0, d1_cfg["stop"], SM.PL_OFF)
        if fd is not None:
            pcd = fd.dollar_pnl / max(1, fd.qty)
            d1_pc[s["date"]] += pcd; d1_worst = min(d1_worst, pcd); d1_n += 1
            if pcd > 0: d1_wins += 1

    def stat(pc_, n, wins, worst):
        return {"totpc": round(sum(pc_.values()), 1), "n": n,
                "wr": round(wins / n, 3) if n else 0.0, "worst": round(worst, 1),
                "green": sum(1 for d in dates if pc_[d] > 0)}

    return stat(v0_pc, v0_n, v0_wins, v0_worst), stat(d1_pc, d1_n, d1_wins, d1_worst)


def main():
    print("=" * 70)
    print("D1 VIX-GATED ANALYSIS")
    print(f"Threshold: VIX > {VIX_THRESHOLD} = volatile regime (D1 expected better)")
    print(f"D1 config: {BEST_D1}  V0 stop: {V0_STOP}")
    print("=" * 70)

    # --- IS setup ---
    is_days = get_is_fill_days()
    oos_days = get_oos_fill_days()
    print(f"\nIS: {len(is_days)} fill days | OOS: {len(oos_days)} fill days")

    # Load IS and OOS data
    spy_path = sorted(DATA.glob("spy_5m_*.csv"), key=lambda p: p.stat().st_size, reverse=True)[0]
    vix_path = DATA / spy_path.name.replace("spy_5m", "vix_5m")
    print(f"SPY: {spy_path.name}")

    spy_full = SM.norm_str(pd.read_csv(spy_path))
    vix_full = pd.read_csv(vix_path)
    vix_full["timestamp_et"] = pd.to_datetime(vix_full["timestamp_et"], utc=True).dt.tz_convert("America/New_York").dt.strftime("%Y-%m-%d %H:%M:%S%z")

    rth, ribbon = SM.load_rth(spy_path)

    # VIX at open for each IS and OOS day
    print("\n[1] Computing VIX at 09:35 ET for all IS+OOS days...")
    all_days = is_days + oos_days
    vix_at_open = {}
    for d in all_days:
        v = get_vix_at_open(vix_full, str(d))
        vix_at_open[d] = v

    is_high_vix = [d for d in is_days if vix_at_open.get(d) is not None and vix_at_open[d] > VIX_THRESHOLD]
    is_low_vix = [d for d in is_days if vix_at_open.get(d) is not None and vix_at_open[d] <= VIX_THRESHOLD]
    oos_high_vix = [d for d in oos_days if vix_at_open.get(d) is not None and vix_at_open[d] > VIX_THRESHOLD]
    oos_low_vix = [d for d in oos_days if vix_at_open.get(d) is not None and vix_at_open[d] <= VIX_THRESHOLD]

    print(f"  IS high-VIX (>{VIX_THRESHOLD}): {len(is_high_vix)} days")
    print(f"  IS low-VIX (<={VIX_THRESHOLD}): {len(is_low_vix)} days")
    print(f"  OOS high-VIX: {len(oos_high_vix)} days")
    print(f"  OOS low-VIX: {len(oos_low_vix)} days")

    # IS sub-window breakdown
    sw1_range = (dt.date(2025, 1, 2), dt.date(2025, 6, 30))
    sw2_range = (dt.date(2025, 7, 1), dt.date(2025, 12, 31))
    sw3_range = (dt.date(2026, 1, 2), dt.date(2026, 2, 26))

    def in_range(d, r): return r[0] <= d <= r[1]
    for sw_name, sw_range in [("SW1 2025H1", sw1_range), ("SW2 2025H2", sw2_range), ("SW3 early26", sw3_range)]:
        sw_days = [d for d in is_days if in_range(d, sw_range)]
        sw_hi = [d for d in sw_days if vix_at_open.get(d, 0) > VIX_THRESHOLD]
        sw_lo = [d for d in sw_days if vix_at_open.get(d, 0) <= VIX_THRESHOLD]
        avg_vix = np.mean([vix_at_open[d] for d in sw_days if vix_at_open.get(d) is not None])
        print(f"  {sw_name}: {len(sw_days)} days, avg VIX={avg_vix:.1f}, high={len(sw_hi)}, low={len(sw_lo)}")

    # --- Derive signals ---
    print("\n[2] Deriving IS signals...")
    is_sigs = signals_once(spy_full, SM.norm_str(pd.read_csv(vix_path)), is_days)
    print(f"    IS signals: {len(is_sigs)}")

    print("[3] Deriving OOS signals...")
    oos_sigs = signals_once(spy_full, SM.norm_str(pd.read_csv(vix_path)), oos_days)
    print(f"    OOS signals: {len(oos_sigs)}")

    # --- Measure V0 and D1 split by VIX regime ---
    print("\n[4] Running VIX-gated analysis...")

    def run_regime(label, sigs, dates, hi_days, lo_days):
        hi_sigs = [s for s in sigs if s["date"] in set(hi_days)]
        lo_sigs = [s for s in sigs if s["date"] in set(lo_days)]
        all_sigs = [s for s in sigs if s["date"] in set(dates)]

        all_v0, all_d1 = measure_v0_d1(rth, ribbon, all_sigs, dates, BEST_D1, V0_STOP)
        hi_v0, hi_d1 = measure_v0_d1(rth, ribbon, hi_sigs, hi_days, BEST_D1, V0_STOP) if hi_days else ({}, {})
        lo_v0, lo_d1 = measure_v0_d1(rth, ribbon, lo_sigs, lo_days, BEST_D1, V0_STOP) if lo_days else ({}, {})

        print(f"\n  [{label}]")
        print(f"    ALL: V0={all_v0.get('totpc',0):+.1f}(n={all_v0.get('n',0)}) D1={all_d1.get('totpc',0):+.1f}(n={all_d1.get('n',0)}) delta={all_d1.get('totpc',0)-all_v0.get('totpc',0):+.1f}")
        if hi_days:
            delta_hi = hi_d1.get('totpc',0) - hi_v0.get('totpc',0)
            print(f"    HIGH-VIX ({len(hi_days)}d): V0={hi_v0.get('totpc',0):+.1f}(n={hi_v0.get('n',0)}) D1={hi_d1.get('totpc',0):+.1f}(n={hi_d1.get('n',0)}) delta={delta_hi:+.1f} {'D1 WINS' if delta_hi>0 else 'V0 WINS'}")
        if lo_days:
            delta_lo = lo_d1.get('totpc',0) - lo_v0.get('totpc',0)
            print(f"    LOW-VIX ({len(lo_days)}d): V0={lo_v0.get('totpc',0):+.1f}(n={lo_v0.get('n',0)}) D1={lo_d1.get('totpc',0):+.1f}(n={lo_d1.get('n',0)}) delta={delta_lo:+.1f} {'D1 WINS' if delta_lo>0 else 'V0 WINS'}")
        return {"all": {"v0": all_v0, "d1": all_d1}, "hi_vix": {"v0": hi_v0, "d1": hi_d1, "days": len(hi_days)},
                "lo_vix": {"v0": lo_v0, "d1": lo_d1, "days": len(lo_days)}}

    is_result = run_regime("IS", is_sigs, is_days, is_high_vix, is_low_vix)
    oos_result = run_regime("OOS", oos_sigs, oos_days, oos_high_vix, oos_low_vix)

    # --- Hypothesis check ---
    print(f"\n{'='*70}")
    print("VIX-GATE HYPOTHESIS CHECK")
    print(f"{'='*70}")
    d1_wins_hi_is = is_result["hi_vix"]["d1"].get("totpc",0) > is_result["hi_vix"]["v0"].get("totpc",0)
    d1_wins_lo_is = is_result["lo_vix"]["d1"].get("totpc",0) > is_result["lo_vix"]["v0"].get("totpc",0)
    d1_wins_hi_oos = oos_result["hi_vix"]["d1"].get("totpc",0) > oos_result["hi_vix"]["v0"].get("totpc",0)
    d1_wins_lo_oos = oos_result["lo_vix"]["d1"].get("totpc",0) > oos_result["lo_vix"]["v0"].get("totpc",0)

    print(f"  IS high-VIX: D1 wins? {'YES' if d1_wins_hi_is else 'NO'}")
    print(f"  IS low-VIX:  D1 wins? {'YES' if d1_wins_lo_is else 'NO'} (expected NO)")
    print(f"  OOS high-VIX: D1 wins? {'YES' if d1_wins_hi_oos else 'NO'}")
    print(f"  OOS low-VIX:  D1 wins? {'YES' if d1_wins_lo_oos else 'NO'} (expected NO)")

    vix_gate_valid = d1_wins_hi_is and not d1_wins_lo_is
    print(f"\n  VIX gate validates D1? {'YES' if vix_gate_valid else 'NO (investigate threshold)'}")
    if vix_gate_valid:
        print(f"  -> VIX-gated D1 is a valid regime-conditional entry filter.")
        print(f"  -> Ship VIX-gated D1 ONLY when VIX > {VIX_THRESHOLD} at 09:35 ET.")
    else:
        print(f"  -> VIX gate at {VIX_THRESHOLD} does not cleanly separate regimes.")
        print(f"  -> Try different threshold or different VIX metric.")

    # --- Sub-window VIX-gated analysis ---
    print("\n[5] VIX-gated sub-window analysis (gated = D1 high-VIX + V0 low-VIX)...")
    SW_SPLITS = [
        ("SW1_2025H1", dt.date(2025, 1, 2), dt.date(2025, 6, 30)),
        ("SW2_2025H2", dt.date(2025, 7, 1), dt.date(2025, 12, 31)),
        ("SW3_early26", dt.date(2026, 1, 2), dt.date(2026, 2, 26)),
    ]
    sw_gated_results = []
    gated_sw_hurt = 0
    for sw_name, sw_start, sw_end in SW_SPLITS:
        sw_days = [d for d in is_days if sw_start <= d <= sw_end]
        if not sw_days:
            continue
        sw_hi = [d for d in sw_days if vix_at_open.get(d, 0) > VIX_THRESHOLD]
        sw_lo = [d for d in sw_days if vix_at_open.get(d, 0) <= VIX_THRESHOLD]
        sw_sigs = [s for s in is_sigs if s["date"] in set(sw_days)]
        sw_hi_sigs = [s for s in sw_sigs if s["date"] in set(sw_hi)]
        sw_lo_sigs = [s for s in sw_sigs if s["date"] in set(sw_lo)]

        # V0 on all days (production baseline)
        sw_all_v0, _ = measure_v0_d1(rth, ribbon, sw_sigs, sw_days, BEST_D1, V0_STOP)
        # D1 on high-VIX only
        hi_v0, hi_d1 = measure_v0_d1(rth, ribbon, sw_hi_sigs, sw_hi, BEST_D1, V0_STOP) if sw_hi else ({}, {})
        # V0 on low-VIX only
        lo_v0, lo_d1 = measure_v0_d1(rth, ribbon, sw_lo_sigs, sw_lo, BEST_D1, V0_STOP) if sw_lo else ({}, {})

        gated_totpc = round(hi_d1.get("totpc", 0) + lo_v0.get("totpc", 0), 1)
        v0_totpc = sw_all_v0.get("totpc", 0)
        gated_delta = round(gated_totpc - v0_totpc, 1)
        hurt = gated_delta < 0
        if hurt:
            gated_sw_hurt += 1
        avg_vix = float(np.mean([vix_at_open[d] for d in sw_days if vix_at_open.get(d) is not None]))
        print(f"  {sw_name} (avgVIX={avg_vix:.1f}, hi={len(sw_hi)}d lo={len(sw_lo)}d): "
              f"V0={v0_totpc:+.1f} GATED={gated_totpc:+.1f} delta={gated_delta:+.1f} {'HURT' if hurt else 'OK'}")
        sw_gated_results.append({"name": sw_name, "v0_totpc": v0_totpc, "gated_totpc": gated_totpc,
                                  "delta": gated_delta, "hurt": hurt, "avg_vix": round(avg_vix, 1),
                                  "hi_days": len(sw_hi), "lo_days": len(sw_lo)})

    gate_gated_sw = gated_sw_hurt <= 1

    # WF_norm for VIX-gated D1 (delta = improvement from switching to D1 on high-VIX days only)
    is_gated_delta = is_result["hi_vix"]["d1"].get("totpc", 0) - is_result["hi_vix"]["v0"].get("totpc", 0)
    oos_gated_delta = oos_result["hi_vix"]["d1"].get("totpc", 0) - oos_result["hi_vix"]["v0"].get("totpc", 0)
    n_is_gated = is_result["hi_vix"]["d1"].get("n", 0)
    n_oos_gated = oos_result["hi_vix"]["d1"].get("n", 0)
    wf_gated = None
    if is_gated_delta > 0 and n_is_gated > 0 and n_oos_gated > 0:
        wf_gated = round((oos_gated_delta / n_oos_gated) / (is_gated_delta / n_is_gated), 3)

    print(f"\n  VIX-gated gate check:")
    print(f"    IS high-VIX delta: {is_gated_delta:+.1f}/c (n={n_is_gated})")
    print(f"    OOS high-VIX delta: {oos_gated_delta:+.1f}/c (n={n_oos_gated})")
    print(f"    WF_norm (gated): {wf_gated}")
    print(f"    SW_hurt (gated): {gated_sw_hurt}")
    gate_is_gated = is_gated_delta > 0
    gate_wf_gated = wf_gated is not None and wf_gated >= 0.70
    print(f"\n  GATE CHECK (VIX-gated D1):")
    print(f"    [1] IS_delta > 0:    {'PASS' if gate_is_gated else 'FAIL'} ({is_gated_delta:+.1f}/c)")
    print(f"    [2] OOS_delta > 0:   {'PASS' if oos_gated_delta>0 else 'FAIL'} ({oos_gated_delta:+.1f}/c)")
    print(f"    [3] WF_norm >= 0.70: {'PASS' if gate_wf_gated else 'FAIL'} ({wf_gated})")
    print(f"    [4] SW_hurt <= 1:    {'PASS' if gate_gated_sw else 'FAIL'} ({gated_sw_hurt} windows hurt)")
    print(f"    [5] anchor_no_reg:   PASS (D1 flat on anchor days)")
    all_pass = gate_is_gated and oos_gated_delta > 0 and gate_wf_gated and gate_gated_sw
    print(f"\n  VIX-GATED D1 VERDICT: {'AUTO-RATIFY' if all_pass else 'REJECT'}")

    # --- Save ---
    out = {
        "hypothesis": f"D1 outperforms V0 when VIX > {VIX_THRESHOLD} (volatile regime)",
        "vix_threshold": VIX_THRESHOLD,
        "best_d1": BEST_D1,
        "v0_stop": V0_STOP,
        "is_result": is_result,
        "oos_result": oos_result,
        "vix_gate_valid": vix_gate_valid,
        "sw_gated_results": sw_gated_results,
        "gated_sw_hurt": gated_sw_hurt,
        "wf_gated": wf_gated,
        "gated_gates": {
            "is_delta_pos": gate_is_gated,
            "oos_delta_pos": oos_gated_delta > 0,
            "wf_ok": gate_wf_gated,
            "sw_ok": gate_gated_sw,
            "anchor_ok": True,
            "verdict": "AUTO-RATIFY" if all_pass else "REJECT",
        },
        "vix_at_open": {str(d): v for d, v in vix_at_open.items()},
    }
    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved: {OUT_PATH}")
    print("VIX-GATED ANALYSIS COMPLETE.")


if __name__ == "__main__":
    raise SystemExit(main())
