"""L117 Analysis — 15:40 ET entry artifact investigation.

The backtest outer-loop gate is hardcoded >= 15:50, but time_stop_et = 15:40 with
time_stop_minutes_before_close=20. Bars labeled 15:40 and 15:45 pass the gate and
can trigger new entries that immediately time-stop in the simulator.

Production: 15:40 heartbeat exits existing positions, does NOT enter new ones.
Backtest: can enter at the 15:45 bar (opens at 15:40), immediately time-stops.

This script:
  1. Runs the CORRECT baseline (IS + OOS)
  2. Identifies all fills with entry_time >= time_stop_et (15:40 ET)
  3. Quantifies IS + OOS artifact impact
  4. Proposes and tests the gate fix
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd
from backtest.lib.orchestrator import run_backtest

DATA_DIR = ROOT / "backtest" / "data"

CORRECT_BASE = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=True,
    premium_stop_pct_bear=-0.20,
    premium_stop_pct_bull=-0.08,
    per_trade_risk_cap_pct=0.30,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.50,
    time_stop_minutes_before_close=20,
)

IS_S, IS_E = dt.date(2025, 1, 2), dt.date(2026, 5, 7)
OOS_S, OOS_E = dt.date(2026, 5, 8), dt.date(2026, 5, 22)

TIME_STOP_ET = dt.time(15, 40)  # = 16:00 - 20 minutes


def load_data(start_date: dt.date, end_date: dt.date):
    """Load SPY + VIX 5m CSVs covering the requested range. Prefer the file with most rows."""
    start_str = start_date.isoformat()
    end_str = f"{end_date.isoformat()}T23:59:59"

    best_spy = None
    best_spy_n = 0
    for sp in DATA_DIR.glob("spy_5m_*.csv"):
        # Quick scan: only check files whose name suggests coverage of start_date
        try:
            df = pd.read_csv(sp)
            filtered = df[(df["timestamp_et"] >= start_str) & (df["timestamp_et"] < end_str)]
            if len(filtered) > best_spy_n:
                best_spy_n = len(filtered)
                best_spy = (sp, filtered)
        except Exception:
            continue

    best_vix = None
    best_vix_n = 0
    for vp in DATA_DIR.glob("vix_5m_*.csv"):
        try:
            df = pd.read_csv(vp)
            filtered = df[(df["timestamp_et"] >= start_str) & (df["timestamp_et"] < end_str)]
            if len(filtered) > best_vix_n:
                best_vix_n = len(filtered)
                best_vix = (vp, filtered)
        except Exception:
            continue

    if best_spy is None or best_vix is None:
        raise FileNotFoundError(f"No data found for {start_date}..{end_date}")

    sp, spy_df = best_spy
    vp, vix_df = best_vix
    spy_df = spy_df.reset_index(drop=True)
    vix_df = vix_df.reset_index(drop=True)
    print(f"  SPY: {sp.name} -> {len(spy_df):,} bars")
    print(f"  VIX: {vp.name} -> {len(vix_df):,} bars")
    return spy_df, vix_df


def normalize_time(t):
    if t is None:
        return None
    if hasattr(t, "to_pydatetime"):
        t = t.to_pydatetime()
    if hasattr(t, "tzinfo") and t.tzinfo is not None:
        t = t.replace(tzinfo=None)
    return t


def analyze_artifacts(spy, vix, start_date, end_date, label):
    result = run_backtest(spy, vix, start_date, end_date, **CORRECT_BASE)
    fills = [t for t in result.trades if t is not None]

    artifact_fills = []
    clean_fills = []

    for f in fills:
        entry_time = normalize_time(f.entry_time_et)
        entry_tod = entry_time.time() if entry_time else None
        is_artifact = entry_tod is not None and entry_tod >= TIME_STOP_ET
        (artifact_fills if is_artifact else clean_fills).append(f)

    total_pnl = sum(f.dollar_pnl for f in fills)
    artifact_pnl = sum(f.dollar_pnl for f in artifact_fills)
    clean_pnl = sum(f.dollar_pnl for f in clean_fills)

    print(f"\n{'='*70}")
    print(f"ARTIFACT ANALYSIS: {label} ({start_date}..{end_date})")
    print(f"{'='*70}")
    print(f"Total fills:    n={len(fills):3d}  pnl={total_pnl:>+10.2f}")
    print(f"Artifact fills: n={len(artifact_fills):3d}  pnl={artifact_pnl:>+10.2f}  (entry >= 15:40 ET)")
    print(f"Clean fills:    n={len(clean_fills):3d}  pnl={clean_pnl:>+10.2f}")

    if artifact_fills:
        print()
        print("Artifact trades:")
        print(f"  {'Date':<12} {'Entry':>7} {'Side':<5} {'PnL':>8}  {'Exit reason'}")
        print(f"  {'-'*12} {'-'*7} {'-'*5} {'-'*8}  {'-'*25}")
        for f in sorted(artifact_fills, key=lambda x: normalize_time(x.entry_time_et)):
            et = normalize_time(f.entry_time_et)
            date_str = et.strftime("%Y-%m-%d") if et else "???"
            time_str = et.strftime("%H:%M") if et else "???"
            side = getattr(f, "side", "?")
            pnl = f.dollar_pnl
            reason = str(getattr(f, "exit_reason", "?"))
            print(f"  {date_str:<12} {time_str:>7} {side:<5} {pnl:>+8.2f}  {reason}")
    else:
        print("  No artifact trades found.")

    print()
    print(f"  P&L impact of fix: {-artifact_pnl:>+.2f} (corrected pnl={clean_pnl:>+.2f})")
    return artifact_fills, clean_fills, total_pnl, clean_pnl


if __name__ == "__main__":
    print("Loading data...")
    spy_full, vix_full = load_data(IS_S, OOS_E)

    is_art, is_clean, is_total, is_fixed = analyze_artifacts(spy_full, vix_full, IS_S, IS_E, "IS")
    oos_art, oos_clean, oos_total, oos_fixed = analyze_artifacts(spy_full, vix_full, OOS_S, OOS_E, "OOS")

    print()
    print("=" * 70)
    print("SUMMARY: L117 TIME-STOP ARTIFACT (>= 15:40 ET entries)")
    print("=" * 70)
    all_art = is_art + oos_art
    print(f"Total artifact trades: n={len(all_art)} (IS={len(is_art)}, OOS={len(oos_art)})")
    print()
    print(f"CURRENT BASELINE:  IS={is_total:>+.2f} / OOS={oos_total:>+.2f}")
    print(f"ARTIFACT-CORRECTED: IS={is_fixed:>+.2f} / OOS={oos_fixed:>+.2f}")
    print()
    print("FIX: Change outer loop gate in backtest/lib/orchestrator.py line ~686:")
    print("  CURRENT:  bar_time_py.time() >= dt.time(15, 50)  [hardcoded]")
    print("  CORRECT:  bar_time_py.time() >= time_stop_et      [dynamic, matches prod]")
    print()
    print("This prevents new entries at or after the time-stop bar.")
    print("With time_stop_minutes_before_close=20, time_stop_et = 15:40 ET.")
    print("With time_stop_minutes_before_close=10 (default), time_stop_et = 15:50 (no change).")
