"""
VIX-Conditional Chandelier Analysis - Safe account.

Motivation: chandelier_sweep.py found no ratifiable static chandelier parameter.
chandelier ON helps in choppy markets (W1_2025H1, W3_2025Q4) but hurts in
trending markets (W2_2025Q3, W4_2026H1). SW_hurt=2 for OFF candidate.

Hypothesis: activating chandelier only when VIX > threshold would preserve
protection in high-VIX choppy regimes while allowing trends to run in low-VIX.

Method (post-processing, no simulator changes needed):
  1. Run chandelier ON backtest -> per-trade P&L with entry_time_et
  2. Run chandelier OFF backtest -> per-trade P&L with entry_time_et
  3. For each threshold in VIX_THRESHOLDS:
     - Match ON/OFF trades by date (same entries, different exits)
     - For each trade: if VIX at entry_time > threshold -> take ON result
     - Aggregate hybrid P&L, compute IS/OOS/sub-window stats vs OFF baseline
     - Apply ratification gates: OOS_positive AND WF>=0.70 AND SW_hurt<=1

Security note: read-only on production state. Never imports Alpaca tools.
Cost ceiling: $0 (free tier, no OpenRouter calls in this script).
"""
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backtest"))

import pandas as pd
from lib.orchestrator import run_backtest

MASTER_SPY = ROOT / "backtest" / "data" / "spy_5m_2025-01-01_2026-06-16.csv"
MASTER_VIX = ROOT / "backtest" / "data" / "vix_5m_2025-01-01_2026-06-16.csv"

IS_START  = dt.date(2025, 1, 2)
IS_END    = dt.date(2026, 5, 7)
OOS_START = dt.date(2026, 5, 8)
OOS_END   = dt.date(2026, 6, 16)

SUBWINDOWS = [
    ("W1_2025H1",  dt.date(2025, 1, 2),  dt.date(2025, 6, 30)),
    ("W2_2025Q3",  dt.date(2025, 7, 1),  dt.date(2025, 9, 30)),
    ("W3_2025Q4",  dt.date(2025, 10, 1), dt.date(2025, 12, 31)),
    ("W4_2026H1",  dt.date(2026, 1, 2),  dt.date(2026, 5, 7)),
]

VIX_THRESHOLDS = [15.0, 17.5, 18.0, 20.0, 22.0, 25.0, 30.0]

SAFE_COMMON = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=True,
    midday_trendline_gate_start_minutes=690,
    premium_stop_pct_bear=-0.10,
    tp1_qty_fraction=0.667,
    tp1_premium_pct=0.50,
    runner_target_premium_pct=2.5,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.30,
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
    params_overrides={"vix_bull_max": 18.0},
)

SAFE_ON = dict(**SAFE_COMMON,
    profit_lock_threshold_pct=0.05,
    profit_lock_stop_offset_pct=0.10,
    profit_lock_mode="trailing",
    profit_lock_trail_pct=0.20,
)

SAFE_OFF = dict(**SAFE_COMMON,
    profit_lock_threshold_pct=0.0,
    profit_lock_stop_offset_pct=0.0,
    profit_lock_mode="fixed",
    profit_lock_trail_pct=0.0,
)


def build_trade_pnl_by_date(params, spy_df, vix_df, start, end):
    """Run backtest and return {date: (dollar_pnl, entry_time_et)} dict."""
    result = run_backtest(spy_df, vix_df, start_date=start, end_date=end, **params)
    by_date = {}
    for trade in result.trades:
        d = trade.entry_time_et.date()
        prev_pnl = by_date.get(d, (0.0, trade.entry_time_et))[0]
        by_date[d] = (prev_pnl + trade.dollar_pnl, trade.entry_time_et)
    return by_date  # {date: (total_pnl, entry_time_et)}


def get_vix_at_time(vix_df, trade_time):
    """Return VIX close nearest to trade_time (tz-naive ET datetime)."""
    date_str = trade_time.date().isoformat()
    time_str = trade_time.strftime("%H:%M")
    mask = (vix_df["date"] == date_str) & (vix_df["time"] == time_str)
    rows = vix_df[mask]["close"]
    if len(rows) > 0:
        return float(rows.iloc[0])
    # Fallback: median of 09:30-10:30 ET window
    mask2 = (
        (vix_df["date"] == date_str) &
        (vix_df["time"] >= "09:30") &
        (vix_df["time"] <= "10:30")
    )
    rows2 = vix_df[mask2]["close"]
    if len(rows2) > 0:
        return float(rows2.median())
    # Last fallback: any bar that day
    day_mask = vix_df["date"] == date_str
    rows3 = vix_df[day_mask]["close"]
    return float(rows3.median()) if len(rows3) > 0 else float("nan")


def compute_hybrid_pnl(on_by_date, off_by_date, vix_df, vix_threshold, start, end):
    """
    For each trade date in [start, end], pick ON result if VIX > threshold, else OFF.
    on_by_date / off_by_date: {date: (total_pnl, entry_time_et)}
    Returns (n_trades, total_hybrid_pnl).
    """
    all_dates = set(on_by_date) | set(off_by_date)
    dates_in_window = [d for d in all_dates if start <= d <= end]

    total = 0.0
    n = 0
    for d in sorted(dates_in_window):
        on_entry  = on_by_date.get(d)
        off_entry = off_by_date.get(d)

        if on_entry is not None and off_entry is not None:
            vix = get_vix_at_time(vix_df, off_entry[1])
            if not (vix != vix) and vix > vix_threshold:
                total += on_entry[0]
            else:
                total += off_entry[0]
            n += 1
        elif off_entry is not None:
            # Trade only in OFF run (entries should match — shouldn't happen often)
            total += off_entry[0]
            n += 1
        elif on_entry is not None:
            # Trade only in ON run
            vix = get_vix_at_time(vix_df, on_entry[1])
            if not (vix != vix) and vix > vix_threshold:
                total += on_entry[0]
            n += 1
    return n, total


def analyze_vix_conditional(spy_df, vix_df):
    """Run the VIX-conditional chandelier analysis."""
    print("\nRunning baseline backtests (ON and OFF)...")

    # IS runs
    on_is  = build_trade_pnl_by_date(SAFE_ON,  spy_df, vix_df, IS_START,  IS_END)
    off_is = build_trade_pnl_by_date(SAFE_OFF, spy_df, vix_df, IS_START,  IS_END)
    # OOS runs
    on_oos  = build_trade_pnl_by_date(SAFE_ON,  spy_df, vix_df, OOS_START, OOS_END)
    off_oos = build_trade_pnl_by_date(SAFE_OFF, spy_df, vix_df, OOS_START, OOS_END)
    # Sub-window runs
    sw_on  = {}
    sw_off = {}
    for wname, ws, we in SUBWINDOWS:
        sw_on[wname]  = build_trade_pnl_by_date(SAFE_ON,  spy_df, vix_df, ws, we)
        sw_off[wname] = build_trade_pnl_by_date(SAFE_OFF, spy_df, vix_df, ws, we)

    base_is_pnl  = sum(v[0] for v in off_is.values())
    base_oos_pnl = sum(v[0] for v in off_oos.values())
    base_is_n    = len(off_is)
    base_oos_n   = len(off_oos)

    print(f"Baseline OFF:  IS n={base_is_n}  pnl=${base_is_pnl:+,.0f}  |  OOS n={base_oos_n}  pnl=${base_oos_pnl:+,.0f}")
    on_is_pnl  = sum(v[0] for v in on_is.values())
    on_oos_pnl = sum(v[0] for v in on_oos.values())
    print(f"Baseline ON:   IS n={len(on_is)}  pnl=${on_is_pnl:+,.0f}  |  OOS n={len(on_oos)}  pnl=${on_oos_pnl:+,.0f}")
    print()
    print("VIX-conditional hybrid: use ON when VIX > threshold, else OFF")
    print("All comparisons vs OFF baseline (production chandelier-OFF = best absolute)")
    print()
    hdr = "  VIX>  IS_n  IS_pnl     IS_d  OOS_n  OOS_pnl     OOS_d      WF  SW_h  VERDICT"
    print(hdr)
    print("-" * len(hdr))

    ratifiable = []
    for threshold in VIX_THRESHOLDS:
        h_is_n,  h_is_pnl  = compute_hybrid_pnl(on_is,  off_is,  vix_df, threshold, IS_START,  IS_END)
        h_oos_n, h_oos_pnl = compute_hybrid_pnl(on_oos, off_oos, vix_df, threshold, OOS_START, OOS_END)

        is_d  = h_is_pnl  - base_is_pnl
        oos_d = h_oos_pnl - base_oos_pnl

        n_is  = base_is_n  if base_is_n  else 1
        n_oos = base_oos_n if base_oos_n else 1
        wf = (oos_d / n_oos) / (is_d / n_is) if is_d != 0 else float("nan")

        sw_results = []
        sw_hurt = 0
        for wname, ws, we in SUBWINDOWS:
            h_sw_n, h_sw_pnl = compute_hybrid_pnl(sw_on[wname], sw_off[wname], vix_df, threshold, ws, we)
            base_sw_pnl = sum(v[0] for v in sw_off[wname].values())
            sw_d = h_sw_pnl - base_sw_pnl
            tag = "HELP" if sw_d > 50 else ("HURT" if sw_d < -50 else "FLAT")
            if tag == "HURT":
                sw_hurt += 1
            sw_results.append(f"{wname}:{tag}({sw_d:+,.0f})")

        oos_pos = oos_d > 0
        wf_ok   = (wf == wf) and wf >= 0.70
        sw_ok   = sw_hurt <= 1

        if oos_pos and wf_ok and sw_ok:
            verdict = "RATIFIABLE"
            ratifiable.append((threshold, oos_d, wf))
        elif not oos_pos:
            verdict = "OOS_NEG"
        elif not wf_ok:
            verdict = f"WF_FAIL({wf:.3f})"
        else:
            verdict = f"SW_FAIL(hurt={sw_hurt})"

        wf_str = f"{wf:.3f}" if wf == wf else "  nan"
        print(f"  {threshold:>4.1f}  {h_is_n:>4}  {h_is_pnl:>+9,.0f}  {is_d:>+7,.0f}  {h_oos_n:>5}  {h_oos_pnl:>+9,.0f}  {oos_d:>+8,.0f}  {wf_str:>7}  {sw_hurt:>4}  {verdict}")
        print(f"         SW: {' | '.join(sw_results)}")

    print()
    if ratifiable:
        best = max(ratifiable, key=lambda x: x[1])
        print(f"  *** BEST RATIFIABLE: VIX>{best[0]:.1f}  OOS_d={best[1]:+,.0f}  WF={best[2]:.3f} ***")
    else:
        print("  No ratifiable VIX threshold found.")
        print("  Conclusion: VIX-conditional chandelier does not pass gates.")
        print("  Safe chandelier ON (production) is at a local optimum vs available params.")

    # Print VIX distribution per sub-window (diagnostic)
    print("\n--- VIX diagnostic per sub-window ---")
    for wname, ws, we in SUBWINDOWS:
        mask = (vix_df["date"] >= ws.isoformat()) & (vix_df["date"] <= we.isoformat())
        vix_vals = vix_df[mask]["close"]
        if len(vix_vals) > 0:
            print(f"  {wname}: VIX median={vix_vals.median():.1f}  p25={vix_vals.quantile(0.25):.1f}  p75={vix_vals.quantile(0.75):.1f}  max={vix_vals.max():.1f}")
        else:
            print(f"  {wname}: no VIX data")


def main():
    print("Loading data...")
    spy_df = pd.read_csv(MASTER_SPY)
    vix_df = pd.read_csv(MASTER_VIX)

    # Normalize VIX date/time columns for lookup.
    # timestamp_et may be timezone-aware (UTC-5 or UTC-4 depending on DST).
    # Convert to tz-naive ET by using utc=True then tz_convert.
    import pytz
    ts_col = "timestamp_et" if "timestamp_et" in vix_df.columns else vix_df.columns[0]
    ts_parsed = pd.to_datetime(vix_df[ts_col], utc=True).dt.tz_convert("America/New_York")
    vix_df["date"] = ts_parsed.dt.date.astype(str)
    vix_df["time"] = ts_parsed.dt.strftime("%H:%M")

    if "close" not in vix_df.columns:
        close_candidates = [c for c in vix_df.columns if "close" in c.lower()]
        if close_candidates:
            vix_df["close"] = vix_df[close_candidates[0]]
        else:
            raise ValueError(f"No close column in VIX df. Columns: {list(vix_df.columns)}")

    print(f"SPY {len(spy_df)} rows  VIX {len(vix_df)} rows")
    print()
    print("VIX-Conditional Chandelier Analysis - Safe account")
    print("Hypothesis: chandelier ON when VIX > threshold catches choppy-market protection")
    print("while letting trends run in low-VIX regimes.")
    print()

    analyze_vix_conditional(spy_df, vix_df)

    print("\nDONE.")


if __name__ == "__main__":
    main()
