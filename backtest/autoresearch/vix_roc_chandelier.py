"""
VIX Rate-of-Change Conditional Chandelier - Safe account.

Motivation (L133): vix_conditional_chandelier.py tested 7 VIX LEVEL thresholds and
found none ratifiable. Root cause: W1_choppy (VIX median=19.2) and W4_trending
(VIX median=19.5) are nearly identical in VIX level -- tariff-shock recovery
trended bullishly while VIX remained elevated. VIX level can't discriminate.

Hypothesis (C5): VIX *direction* is more discriminatory than VIX level. Rising VIX
indicates fear escalation -> choppy regime -> chandelier ON for protection. Falling
or stable VIX indicates relief rally or calm trend -> chandelier OFF to let trend run.

Method (same post-processing approach as vix_conditional_chandelier.py):
  For each trade date:
    Compute VIX_ROC(window) = (VIX_today - VIX_N_days_ago) / VIX_N_days_ago
    If ROC > roc_threshold -> ON (VIX rising -> fear escalating)
    If ROC <= roc_threshold -> OFF (VIX falling/stable -> trend running)

Tested: ROC windows [1, 2, 5] x thresholds [-0.05, 0.0, +0.05, +0.10]

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

ROC_WINDOWS = [1, 2, 5]
ROC_THRESHOLDS = [-0.05, 0.0, 0.05, 0.10]

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


def build_vix_daily_close(vix_df):
    """
    Build {date_str: vix_close} using the last bar of each trading day.
    Returns a sorted list of (date, vix_close) tuples.
    """
    by_date = {}
    for _, row in vix_df.iterrows():
        d = row["date"]
        c = row["close"]
        # Keep last close of each day (latest time wins)
        if d not in by_date or row["time"] > by_date[d][0]:
            by_date[d] = (row["time"], float(c))
    # Return as dict {date_str: close}
    return {d: v[1] for d, v in by_date.items()}


def get_vix_roc(vix_daily, trade_date, window):
    """
    Compute VIX N-day ROC for trade_date.
    vix_daily: {date_str: close}
    Returns (VIX_today - VIX_N_ago) / VIX_N_ago, or NaN if unavailable.
    """
    sorted_dates = sorted(vix_daily.keys())
    today_str = trade_date.isoformat()
    if today_str not in sorted_dates:
        return float("nan")
    idx = sorted_dates.index(today_str)
    if idx < window:
        return float("nan")
    vix_today = vix_daily[today_str]
    vix_prev = vix_daily[sorted_dates[idx - window]]
    if vix_prev == 0:
        return float("nan")
    return (vix_today - vix_prev) / vix_prev


def build_trade_pnl_by_date(params, spy_df, vix_df, start, end):
    """Run backtest and return {date: (dollar_pnl, entry_time_et)} dict."""
    result = run_backtest(spy_df, vix_df, start_date=start, end_date=end, **params)
    by_date = {}
    for trade in result.trades:
        d = trade.entry_time_et.date()
        prev_pnl = by_date.get(d, (0.0, trade.entry_time_et))[0]
        by_date[d] = (prev_pnl + trade.dollar_pnl, trade.entry_time_et)
    return by_date


def compute_roc_hybrid_pnl(on_by_date, off_by_date, vix_daily, window, threshold, start, end):
    """
    For each trade date in [start, end], pick ON if VIX_ROC(window) > threshold, else OFF.
    """
    all_dates = set(on_by_date) | set(off_by_date)
    dates_in_window = [d for d in all_dates if start <= d <= end]

    total = 0.0
    n = 0
    on_count = 0
    off_count = 0
    for d in sorted(dates_in_window):
        on_entry = on_by_date.get(d)
        off_entry = off_by_date.get(d)

        roc = get_vix_roc(vix_daily, d, window)
        use_on = (roc == roc) and roc > threshold  # NaN-safe check

        if on_entry is not None and off_entry is not None:
            if use_on:
                total += on_entry[0]
                on_count += 1
            else:
                total += off_entry[0]
                off_count += 1
            n += 1
        elif off_entry is not None:
            total += off_entry[0]
            off_count += 1
            n += 1
        elif on_entry is not None:
            if use_on:
                total += on_entry[0]
                on_count += 1
                n += 1

    return n, total, on_count, off_count


def print_roc_diagnostic(vix_daily, spy_df, vix_df):
    """Print VIX ROC distribution per sub-window for all windows tested."""
    print("\n--- VIX ROC diagnostic per sub-window ---")
    sorted_dates = sorted(vix_daily.keys())

    for wname, ws, we in SUBWINDOWS:
        sw_dates = [d for d in sorted_dates if ws.isoformat() <= d <= we.isoformat()]
        print(f"\n  {wname} ({ws} to {we}):")
        for window in ROC_WINDOWS:
            rocs = []
            for d_str in sw_dates:
                idx = sorted_dates.index(d_str)
                if idx >= window:
                    vix_today = vix_daily[d_str]
                    vix_prev = vix_daily[sorted_dates[idx - window]]
                    if vix_prev > 0:
                        rocs.append((vix_today - vix_prev) / vix_prev * 100)
            if rocs:
                s = sorted(rocs)
                n = len(s)
                med = s[n // 2]
                p25 = s[n // 4]
                p75 = s[3 * n // 4]
                pct_rising = sum(1 for r in rocs if r > 0) / len(rocs) * 100
                print(f"    ROC_{window}d: median={med:+.1f}%  p25={p25:+.1f}%  p75={p75:+.1f}%  pct_rising={pct_rising:.0f}%")


def analyze_vix_roc_conditional(spy_df, vix_df, vix_daily):
    print("\nRunning baseline backtests (ON and OFF)...")

    on_is   = build_trade_pnl_by_date(SAFE_ON,  spy_df, vix_df, IS_START,  IS_END)
    off_is  = build_trade_pnl_by_date(SAFE_OFF, spy_df, vix_df, IS_START,  IS_END)
    on_oos  = build_trade_pnl_by_date(SAFE_ON,  spy_df, vix_df, OOS_START, OOS_END)
    off_oos = build_trade_pnl_by_date(SAFE_OFF, spy_df, vix_df, OOS_START, OOS_END)

    sw_on  = {}
    sw_off = {}
    for wname, ws, we in SUBWINDOWS:
        sw_on[wname]  = build_trade_pnl_by_date(SAFE_ON,  spy_df, vix_df, ws, we)
        sw_off[wname] = build_trade_pnl_by_date(SAFE_OFF, spy_df, vix_df, ws, we)

    # Aggregate baseline totals
    base_off_is_pnl  = sum(v[0] for v in off_is.values())
    base_off_oos_pnl = sum(v[0] for v in off_oos.values())
    base_off_is_n    = len(off_is)
    base_off_oos_n   = len(off_oos)

    print(f"Baseline OFF: IS n={base_off_is_n}  pnl=${base_off_is_pnl:+,.0f}  |  OOS n={base_off_oos_n}  pnl=${base_off_oos_pnl:+,.0f}")
    print(f"Baseline ON:  IS n={len(on_is)}  pnl=${sum(v[0] for v in on_is.values()):+,.0f}  |  OOS n={len(on_oos)}  pnl=${sum(v[0] for v in on_oos.values()):+,.0f}")

    print(f"\nVIX-ROC conditional: use ON when VIX_ROC(window) > threshold, else OFF")
    print(f"All comparisons vs OFF baseline (best absolute)")
    print(f"\n{'Win':>6}  {'Thr%':>5}  {'IS_n':>5}  {'IS_pnl':>10}  {'IS_d':>8}  {'OOS_n':>5}  {'OOS_pnl':>10}  {'OOS_d':>8}  {'WF':>7}  {'ON%':>4}  {'SW_h':>4}  VERDICT")
    print("-" * 105)

    ratifiable = []

    for window in ROC_WINDOWS:
        for thr in ROC_THRESHOLDS:
            # IS hybrid
            is_n, is_pnl, is_on, is_off = compute_roc_hybrid_pnl(
                on_is, off_is, vix_daily, window, thr, IS_START, IS_END)
            # OOS hybrid
            oos_n, oos_pnl, oos_on, oos_off = compute_roc_hybrid_pnl(
                on_oos, off_oos, vix_daily, window, thr, OOS_START, OOS_END)

            is_d  = is_pnl  - base_off_is_pnl
            oos_d = oos_pnl - base_off_oos_pnl

            n_is  = base_off_is_n  if base_off_is_n  else 1
            n_oos = base_off_oos_n if base_off_oos_n else 1
            wf = (oos_d / n_oos) / (is_d / n_is) if is_d != 0 else float("nan")

            sw_results = []
            sw_hurt = 0
            for wname, ws, we in SUBWINDOWS:
                sw_base = sum(v[0] for v in sw_off[wname].values())
                sw_n, sw_pnl, _, _ = compute_roc_hybrid_pnl(
                    sw_on[wname], sw_off[wname], vix_daily, window, thr, ws, we)
                sw_d = sw_pnl - sw_base
                tag = "HELP" if sw_d > 50 else ("HURT" if sw_d < -50 else "FLAT")
                if tag == "HURT":
                    sw_hurt += 1
                sw_results.append(f"{wname}:{tag}({sw_d:+,.0f})")

            oos_pos = oos_d > 0
            wf_ok   = (wf == wf) and wf >= 0.70
            sw_ok   = sw_hurt <= 1

            on_pct = (is_on + oos_on) / max(is_n + oos_n, 1) * 100

            if oos_pos and wf_ok and sw_ok:
                verdict = "RATIFIABLE"
                ratifiable.append((window, thr, oos_d, wf))
            elif not oos_pos:
                verdict = "OOS_NEG"
            elif not wf_ok:
                verdict = f"WF_FAIL({wf:.3f})"
            else:
                verdict = f"SW_FAIL(hurt={sw_hurt})"

            wf_str = f"{wf:.3f}" if wf == wf else "   nan"
            thr_pct = f"{thr*100:+.0f}%"
            print(f"{window:>6}d  {thr_pct:>5}  {is_n:>5}  {is_pnl:>+10,.0f}  {is_d:>+8,.0f}  {oos_n:>5}  {oos_pnl:>+10,.0f}  {oos_d:>+8,.0f}  {wf_str:>7}  {on_pct:>3.0f}%  {sw_hurt:>4}  {verdict}")
            print(f"        SW: {' | '.join(sw_results)}")

    print()
    if ratifiable:
        best = max(ratifiable, key=lambda x: x[2])
        print(f"  *** RATIFIABLE: ROC_{best[0]}d threshold={best[1]:+.2f}  OOS_d={best[2]:+,.0f}  WF={best[3]:.3f} ***")
        print(f"  Action: implement VIX_ROC({best[0]}) > {best[1]:.2f} gate in params.json + heartbeat.md + simulator")
    else:
        print(f"  No ratifiable ROC-conditional threshold found.")
        print(f"  Conclusion: chandelier regime split not solvable by VIX ROC conditioning either.")
        print(f"  Next: Accept chandelier ON (production) as local optimum. Pivot to NLWB setup or ATR-based regime.")


def main():
    print("Loading data...")
    spy_df = pd.read_csv(MASTER_SPY)
    raw_vix = pd.read_csv(MASTER_VIX)
    print(f"SPY {len(spy_df)} rows  VIX {len(raw_vix)} rows")

    # Normalize VIX timestamps to ET date/time strings (same logic as vix_conditional_chandelier.py)
    vix_df = raw_vix.copy()
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

    print("\nVIX-ROC Conditional Chandelier Analysis - Safe account")
    print("Hypothesis: rising VIX (VIX_ROC > threshold) -> choppy -> chandelier ON")
    print("            falling VIX (VIX_ROC <= threshold) -> trending -> chandelier OFF")
    print(f"Tested windows: {ROC_WINDOWS} days | Thresholds: {[f'{t:+.0%}' for t in ROC_THRESHOLDS]}")

    vix_daily = build_vix_daily_close(vix_df)
    print(f"VIX daily close series: {len(vix_daily)} trading days")

    print_roc_diagnostic(vix_daily, spy_df, vix_df)

    analyze_vix_roc_conditional(spy_df, vix_df, vix_daily)

    print("\nDONE.")


if __name__ == "__main__":
    main()
