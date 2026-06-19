"""Sweep bull buyer-pressure filter_10 vol_mult (0.3 to 0.9) over 17-month history.

Near-miss outcome audit (2026-06-16) identified filter_10 as BLOCK_COSTLY:
2/3 blocked bull entries moved favorably, avg +$0.94 SPY. Current vol_mult=0.7.
This sweep quantifies the tradeoff of loosening the threshold.

SECURITY: Read-only on production state. Writes output to analysis/recommendations/.
COST: Free tier only. This script uses only local backtest engine, no API calls.
"""
from __future__ import annotations
import sys
import json
import datetime as dt
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "autoresearch"))

from lib.orchestrator import run_backtest

# Load data using the same logic as other sweep scripts
DATA = REPO / "data"


def load_data(start: dt.date, end: dt.date):
    import pandas as pd

    def _dedupe(df):
        df = df.copy()
        df["_ts"] = pd.to_datetime(df["timestamp_et"], utc=True, errors="coerce")
        df = df.dropna(subset=["_ts"])
        df = df.sort_values("_ts").drop_duplicates(subset=["_ts"], keep="first")
        df = df.reset_index(drop=True)
        return df.drop(columns=["_ts"])

    # Try merged master files first
    candidates = [
        (dt.date(2025, 1, 1), dt.date(2026, 5, 22)),
        (dt.date(2025, 1, 1), dt.date(2026, 5, 15)),
    ]
    for cs, ce in candidates:
        if cs > start or ce < end:
            continue
        sp = DATA / f"spy_5m_{cs}_{ce}.csv"
        vp = DATA / f"vix_5m_{cs}_{ce}.csv"
        if sp.exists() and vp.exists():
            return _dedupe(pd.read_csv(sp)), _dedupe(pd.read_csv(vp))

    # Try exact match or OOS extension
    for suffix_end in [dt.date(2026, 6, 15), end]:
        sp = DATA / f"spy_5m_{dt.date(2025,1,1)}_{suffix_end}.csv"
        vp = DATA / f"vix_5m_{dt.date(2025,1,1)}_{suffix_end}.csv"
        if sp.exists() and vp.exists():
            return _dedupe(pd.read_csv(sp)), _dedupe(pd.read_csv(vp))

    # Concat master + extension
    import pandas as pd
    master_sp = DATA / "spy_5m_2025-01-01_2026-05-22.csv"
    ext_sp = DATA / "spy_5m_2026-05-19_2026-06-15.csv"
    master_vp = DATA / "vix_5m_2025-01-01_2026-05-22.csv"
    ext_vp = DATA / "vix_5m_2026-05-19_2026-06-15.csv"
    if master_sp.exists() and ext_sp.exists():
        spy = pd.concat([pd.read_csv(master_sp), pd.read_csv(ext_sp)], ignore_index=True)
        vix = pd.concat([pd.read_csv(master_vp), pd.read_csv(ext_vp)], ignore_index=True)
        return _dedupe(spy), _dedupe(vix)
    raise FileNotFoundError("No SPY/VIX data found")

OUT = REPO.parent / "analysis" / "recommendations"
OUT.mkdir(parents=True, exist_ok=True)

START = dt.date(2025, 1, 1)
END = dt.date(2026, 6, 15)

# vol_mult values to sweep — 0.7 is production baseline
VOL_MULTS = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.5, 2.0]

# J anchor days for regression check
J_WINNER_DATES = [dt.date(2026, 4, 29), dt.date(2026, 5, 1), dt.date(2026, 5, 4)]
J_LOSER_DATES = [dt.date(2026, 5, 5), dt.date(2026, 5, 6), dt.date(2026, 5, 7)]


def run_combo(spy, vix, vol_mult: float) -> dict:
    """Run 17-month backtest with given vol_mult for bear filter 9 + bull filter 10.

    Note: filter_9_vol_multiplier controls BOTH bearish breakdown_bar_bearish vol check
    (filter 9) AND bullish buyer_pressure_bar vol check (filter 10) — they share f9_vol_mult.
    """
    r = run_backtest(
        spy, vix,
        start_date=START,
        end_date=END,
        use_real_fills=False,
        params_overrides={
            "filter_9_vol_multiplier": vol_mult,
        }
    )
    trades = r.trades
    total_pnl = sum(t.dollar_pnl for t in trades)
    n_bull = sum(1 for t in trades if "BULLISH" in getattr(t, "setup", "").upper() or
                 getattr(t, "setup", "").upper().startswith("BULL"))
    n_bear = len(trades) - n_bull

    # WR by side
    wins = [t for t in trades if t.dollar_pnl > 0]
    wr = len(wins) / len(trades) * 100 if trades else 0

    # Per anchor day check
    anchor_pnl = {}
    for d in J_WINNER_DATES + J_LOSER_DATES:
        day_trades = [t for t in trades if t.entry_time_et.date() == d]
        anchor_pnl[str(d)] = round(sum(t.dollar_pnl for t in day_trades), 2)

    return {
        "vol_mult": vol_mult,
        "n_trades": len(trades),
        "n_bull": n_bull,
        "n_bear": n_bear,
        "total_pnl": round(total_pnl, 2),
        "wr_pct": round(wr, 1),
        "anchor_pnl": anchor_pnl,
    }


def main():
    print(f"Loading data {START} -> {END}...")
    spy, vix = load_data(START, END)
    print(f"  SPY: {len(spy):,} bars, VIX: {len(vix):,} bars")

    results = []
    baseline = None
    print("\nvol_mult | n_trades | n_bull | n_bear | total_pnl | WR%")
    print("-" * 65)
    for vm in VOL_MULTS:
        r = run_combo(spy, vix, vm)
        results.append(r)
        if abs(vm - 0.7) < 0.001:
            baseline = r
        marker = " <-- BASELINE" if abs(vm - 0.7) < 0.001 else ""
        print(f"  {vm:.1f}    |   {r['n_trades']:4d}   |  {r['n_bull']:4d}  | {r['n_bear']:4d}   | ${r['total_pnl']:8.2f} | {r['wr_pct']:4.1f}%{marker}")

    print("\n=== ANCHOR DAY REGRESSION CHECK (vs baseline vol_mult=0.7) ===")
    if baseline:
        print(f"Date       | Baseline pnl | Delta by vol_mult")
        print("-" * 70)
        for d in J_WINNER_DATES + J_LOSER_DATES:
            ds = str(d)
            baseline_pnl = baseline["anchor_pnl"][ds]
            deltas = [f"{r['vol_mult']:.1f}:{r['anchor_pnl'][ds]-baseline_pnl:+.0f}"
                      for r in results if abs(r["vol_mult"] - 0.7) > 0.001]
            marker = "J-WIN" if d in J_WINNER_DATES else "J-LOSE"
            print(f"  {ds} [{marker}] | ${baseline_pnl:7.2f}      | {' | '.join(deltas)}")

    output = {
        "sweep": "bull_filter10_vol_mult",
        "date_range": f"{START}..{END}",
        "generated": dt.datetime.now().isoformat(),
        "baseline_vol_mult": 0.7,
        "near_miss_finding": "filter_10 BLOCK_COSTLY: 2/3 blocked entries moved favorably avg +$0.94 SPY (2026-06-16 audit)",
        "results": results,
    }
    out_path = OUT / "bull-filter10-vol-sweep.json"
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"\nWrote: {out_path}")

    # Verdict
    if baseline and results:
        best = min(results, key=lambda r: -(r["total_pnl"] - baseline["total_pnl"]))
        best_delta = best["total_pnl"] - baseline["total_pnl"]
        print(f"\nBest vol_mult: {best['vol_mult']:.1f} (pnl delta vs baseline: {best_delta:+.2f})")
        if best_delta > 0:
            print("  >> IMPROVEMENT found — verify anchor day regressions before promoting")
        else:
            print("  >> No improvement vs baseline — filter 10 at 0.7 is already optimal")

    return 0


if __name__ == "__main__":
    sys.exit(main())
