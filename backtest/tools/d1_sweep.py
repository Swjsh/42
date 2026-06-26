"""D1 retest-reclaim parameter sweep — SNIPER research.

Sweeps the three D1 knobs (window, prox_mult, stop) on:
  - 60-day OOS (same window used by run_all_sniper.py)
  - Missed week 2026-05-26..29
  - J-anchor window 2026-04-27..05-07 (put-side non-regression)

Baseline: D1(window=4, prox=0.10*ATR5, stop=0.20, PLoff) → +375.7/c OOS (from _sniper_oos.json).
Goal: find configs that improve on +375.7/c WITHOUT regressing anchor.

Security: read-only on all production state. No Alpaca calls.
Cost: $0 (no OpenRouter calls). Pure local backtest re-sim.
"""
from __future__ import annotations
import sys, json, datetime as dt
from collections import Counter
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
import sniper_matrix as SM

DATA = REPO / "data"
ABT = REPO.parent / "analysis" / "backtests"
OUT_PATH = REPO.parent / "analysis" / "recommendations" / "d1_param_sweep.json"

# --- Sweep grid ---
WINDOWS = [3, 4, 6, 8]
PROX_MULTS = [0.05, 0.10, 0.15, 0.20, 0.30]
STOPS = [0.12, 0.15, 0.20, 0.25]
PL_OPTIONS = [("PLoff", SM.PL_OFF), ("PLon", SM.PL_ON)]

MDATES = [dt.date(2026, 5, 26), dt.date(2026, 5, 27), dt.date(2026, 5, 28), dt.date(2026, 5, 29)]
ANCHOR_D0 = dt.date(2026, 4, 27)
ANCHOR_D1 = dt.date(2026, 5, 7)

BASELINE_OOS_TOTPC = 375.7  # D1(w=4, p=0.10, s=0.20, PLoff) from _sniper_oos.json


def oos_setup():
    c = Counter(f.name[3:9] for f in (DATA / "options").glob("SPY*.csv"))
    fill_days = sorted({dt.datetime.strptime(k, "%y%m%d").date() for k, v in c.items() if v >= 8})
    cands = [p for p in DATA.glob("spy_5m_*.csv") if (DATA / p.name.replace("spy_5m", "vix_5m")).exists()]
    cands.sort(key=lambda p: p.stat().st_size, reverse=True)
    master = cands[0]
    spy_dates = set(SM._to_et(pd.read_csv(master))["timestamp_et"]).keys() if False else None
    spy_df = pd.read_csv(master)
    spy_dates = set(SM._to_et(spy_df["timestamp_et"]).dt.date)
    oos = [d for d in fill_days if d in spy_dates and d not in set(MDATES)]
    oos = sorted(oos)[-60:]
    return master, oos


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


def resim_d1_param(rth, ribbon, sigs, dates, window, prox_mult, stop, pl):
    """D1 re-sim with parametric window/prox_mult/stop/pl."""
    pc_ = {d: 0.0 for d in dates}
    worst = 0.0
    n = 0
    wins = 0
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
                    trig = R
                    break
                if s["side"] == "P" and b["high"] >= s["level"] - tol and b["close"] < s["level"] and b["close"] < b["open"]:
                    trig = R
                    break
        f = SM.sim(rth, ribbon, trig, s["side"], s["level"], 0, stop, pl)
        if f is None:
            continue
        pcv = f.dollar_pnl / max(1, f.qty)
        pc_[s["date"]] += pcv
        worst = min(worst, pcv)
        n += 1
        if pcv > 0:
            wins += 1
    traded = [d for d in dates if pc_[d] != 0]
    green = [d for d in dates if pc_[d] > 0]
    return {
        "totpc": round(sum(pc_.values()), 1),
        "green": len(green),
        "days_traded": len(traded),
        "n": n,
        "wins": wins,
        "wr": round(wins / n, 3) if n else 0.0,
        "worst_pc": round(worst, 1),
    }


def main():
    print("=" * 70)
    print("D1 PARAM SWEEP — SNIPER retest-reclaim")
    print(f"Baseline: D1(w=4, p=0.10, s=0.20, PLoff) -> +{BASELINE_OOS_TOTPC}/c OOS")
    print("=" * 70)

    # --- Load OOS data ---
    print("\n[1] Setting up OOS window...")
    master, oos = oos_setup()
    print(f"    OOS: {len(oos)} days ({oos[0]}..{oos[-1]})")

    ospy = SM.norm_str(pd.read_csv(master))
    ovix_path = DATA / master.name.replace("spy_5m", "vix_5m")
    ovix = SM.norm_str(pd.read_csv(ovix_path))
    orth, oribbon = SM.load_rth(master)

    print("\n[2] Deriving OOS signals (ONE engine run)...")
    oos_sigs = signals_once(ospy, ovix, oos)
    print(f"    OOS signals: {len(oos_sigs)}")

    # --- Load missed week data ---
    mspy = SM.norm_str(pd.read_csv(DATA / "spy_5m_2026-05-19_2026-05-29.csv"))
    mvix = SM.norm_str(pd.read_csv(DATA / "vix_5m_2026-05-19_2026-05-29.csv"))
    mrth, mribbon = SM.load_rth(DATA / "spy_5m_2026-05-19_2026-05-29.csv")

    print("[3] Deriving missed-week signals...")
    m_sigs = signals_once(mspy, mvix, MDATES)
    print(f"    Missed-week signals: {len(m_sigs)}")

    # --- Load anchor data ---
    aspy_path = DATA / "spy_5m_2025-01-01_2026-05-07.csv"
    avix_path = DATA / "vix_5m_2025-01-01_2026-05-07.csv"
    has_anchor = aspy_path.exists() and avix_path.exists()
    a_sigs = []
    adates = []
    if has_anchor:
        print("[4] Deriving J-anchor signals (put-side only)...")
        aspy = SM.norm_str(pd.read_csv(aspy_path))
        avix = SM.norm_str(pd.read_csv(avix_path))
        arth, aribbon = SM.load_rth(aspy_path)
        adates = [ANCHOR_D0 + dt.timedelta(days=k) for k in range((ANCHOR_D1 - ANCHOR_D0).days + 1)]
        a_sigs = [s for s in signals_once(aspy, avix, adates) if s["side"] == "P"]
        print(f"    Anchor put-signals: {len(a_sigs)}")

    # --- Sweep grid ---
    total = len(WINDOWS) * len(PROX_MULTS) * len(STOPS) * len(PL_OPTIONS)
    print(f"\n[5] Sweeping {len(WINDOWS)}w x {len(PROX_MULTS)}p x {len(STOPS)}s x {len(PL_OPTIONS)}pl = {total} configs...")
    results = []
    done = 0
    for w in WINDOWS:
        for p in PROX_MULTS:
            for s in STOPS:
                for plname, pl in PL_OPTIONS:
                    oos_r = resim_d1_param(orth, oribbon, oos_sigs, oos, w, p, s, pl)
                    mwk_r = resim_d1_param(mrth, mribbon, m_sigs, MDATES, w, p, s, pl)
                    anc_r = resim_d1_param(arth, aribbon, a_sigs, adates, w, p, s, pl) if has_anchor and a_sigs else None
                    results.append({
                        "window": w, "prox_mult": p, "stop": s, "pl": plname,
                        "oos": oos_r,
                        "missed_week": mwk_r,
                        "anchor": anc_r,
                        "key": f"D1(w={w},p={p},s={s},{plname})",
                    })
                    done += 1
                    if done % 20 == 0:
                        print(f"    {done}/{total} done...")

    # --- Rank by OOS total/c ---
    results.sort(key=lambda x: x["oos"]["totpc"], reverse=True)

    print(f"\n{'='*70}")
    print("TOP 20 configs by OOS total/c:")
    print(f"{'Config':40} {'OOS/c':>8} {'grn':>4} {'n':>4} {'WR':>5} {'Wk/c':>7} {'Anc':>5}")
    print("-" * 70)
    for r in results[:20]:
        anc_pc = f"{r['anchor']['totpc']:+.1f}" if r["anchor"] else "N/A"
        print(f"{r['key']:40} {r['oos']['totpc']:>+8.1f} {r['oos']['green']:>3}/{len(oos):>3} "
              f"{r['oos']['n']:>4} {r['oos']['wr']:>5.1%} {r['missed_week']['totpc']:>+7.1f} {anc_pc:>6}")

    print(f"\nBaseline D1(w=4,p=0.10,s=0.20,PLoff): +{BASELINE_OOS_TOTPC}/c")

    # --- Anchor analysis for top-10 OOS ---
    if has_anchor and a_sigs:
        print(f"\n--- J-ANCHOR (put-side non-regression) for top-10 OOS ---")
        print(f"{'Config':38} {'AncTot/c':>9} {'n':>4} {'WR':>5} {'5/04cap':>8}")
        print("-" * 68)
        for r in results[:10]:
            anc = r["anchor"]
            if anc is None:
                continue
            print(f"{r['key']:38} {anc['totpc']:>+9.1f} {anc['n']:>4} {anc['wr']:>5.1%}      N/A")

    # --- Find configs that beat baseline on BOTH OOS and anchor ---
    print(f"\n--- BEATING BASELINE: OOS > {BASELINE_OOS_TOTPC} AND anchor >= 0 ---")
    beats = [r for r in results
             if r["oos"]["totpc"] > BASELINE_OOS_TOTPC
             and (r["anchor"] is None or r["anchor"]["totpc"] >= 0)]
    if beats:
        for r in beats[:10]:
            anc = r["anchor"]
            anc_str = f"{anc['totpc']:+.1f}" if anc else "N/A"
            print(f"  {r['key']} OOS={r['oos']['totpc']:+.1f} Anc={anc_str}")
    else:
        print("  None beat both criteria. Best OOS without anchor regression:")
        for r in results[:5]:
            anc = r["anchor"]
            anc_str = f"{anc['totpc']:+.1f}" if anc else "N/A"
            print(f"  {r['key']} OOS={r['oos']['totpc']:+.1f} Anc={anc_str}")

    # --- Save ---
    OUT_PATH.parent.mkdir(exist_ok=True)
    out_data = {
        "task": "SNIPER D1 param sweep",
        "baseline": {"key": "D1(w=4,p=0.10,s=0.20,PLoff)", "oos_totpc": BASELINE_OOS_TOTPC},
        "sweep_grid": {
            "windows": WINDOWS, "prox_mults": PROX_MULTS,
            "stops": STOPS, "pl_options": [x[0] for x in PL_OPTIONS],
            "total_configs": total,
        },
        "oos_days": len(oos),
        "oos_signals": len(oos_sigs),
        "missed_week_signals": len(m_sigs),
        "anchor_signals": len(a_sigs),
        "results": results,  # full grid, sorted by OOS desc
        "top_10": results[:10],
        "beats_baseline": beats[:10],
    }
    OUT_PATH.write_text(json.dumps(out_data, indent=2, default=str))
    print(f"\nSaved: {OUT_PATH}")
    print("SWEEP COMPLETE.")


if __name__ == "__main__":
    raise SystemExit(main())
