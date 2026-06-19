"""
ATR-Ratio Regime Conditional Chandelier - Safe account.

Motivation (L133, L134): VIX-based conditioning exhausted.
- vix_conditional_chandelier.py: VIX level overlaps (W1_median=19.2 vs W4_median=19.5)
- vix_roc_chandelier.py: VIX ROC is ~50% random in all sub-windows (40-59% rising)

Hypothesis (C5 fix path): Realized price volatility (SPY ATR) may discriminate where
implied vol (VIX) cannot. A prior-day high SPY range = choppy/fearful session ->
today may also be choppy -> chandelier ON for protection. Prior-day low range =
calm/trending session -> chandelier OFF to let trend run.

Key advantage over VIX: ATR measures what SPY is ACTUALLY DOING (realized), not
market fear sentiment (implied). W2_2025Q3 tech rally summer likely had genuinely
smaller daily SPY ranges than W1_2025H1 tariff uncertainty or W3_2025Q4 election chop.

Method:
  For each trade date:
    Compute prior_day_range = high - low of previous RTH session (09:30-16:00 ET)
    Compute ATR_N = median of prior N days' RTH ranges (rolling, no look-ahead)
    atr_ratio = prior_day_range / ATR_N
    If atr_ratio > threshold -> yesterday was high-range (choppy) -> chandelier ON today
    If atr_ratio <= threshold -> yesterday was calm (trending) -> chandelier OFF today

No look-ahead: prior_day_range and ATR_N are fully known before the trade session opens.

Tested: ATR windows [5, 10, 20] x thresholds [0.80, 1.00, 1.10, 1.20, 1.50]

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

ATR_WINDOWS = [5, 10, 20]
ATR_THRESHOLDS = [0.80, 1.00, 1.10, 1.20, 1.50]

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


def build_daily_rth_range(spy_df):
    """
    Compute prior-day RTH session high-low range for each trading day.
    Returns {date_str: range_dollars} dict.
    RTH = 09:30-16:00 ET.
    """
    by_date = {}
    for _, row in spy_df.iterrows():
        d = row["date"]
        t = row["time"]
        # Only RTH bars: 09:30 to 15:55 (last 5-min bar closing at 16:00)
        if "09:30" <= t <= "15:55":
            if d not in by_date:
                by_date[d] = (float(row["high"]), float(row["low"]))
            else:
                h, l = by_date[d]
                by_date[d] = (max(h, float(row["high"])), min(l, float(row["low"])))

    ranges = {d: (v[0] - v[1]) for d, v in by_date.items()}
    return ranges  # {date_str: range_dollars}


def get_atr_ratio(daily_ranges, trade_date, window):
    """
    Compute ratio of yesterday's range to rolling N-day median (prior N days).
    Returns ratio, or NaN if insufficient history.
    No look-ahead: uses only data prior to trade_date.
    """
    sorted_dates = sorted(daily_ranges.keys())
    today_str = trade_date.isoformat()

    # Find yesterday (prior trading day)
    if today_str not in sorted_dates:
        return float("nan"), float("nan")
    idx = sorted_dates.index(today_str)
    if idx < 1:
        return float("nan"), float("nan")

    yesterday_str = sorted_dates[idx - 1]
    yesterday_range = daily_ranges[yesterday_str]

    # ATR = median of prior N trading days (not including yesterday if we want look-back)
    # Use N days ending yesterday for ATR calculation
    atr_start_idx = max(0, idx - 1 - window)
    atr_end_idx   = idx  # exclusive
    prior_dates = sorted_dates[atr_start_idx:atr_end_idx]
    if len(prior_dates) < max(1, window // 2):
        return float("nan"), yesterday_range
    prior_ranges = [daily_ranges[d] for d in prior_dates]
    atr_n = sorted(prior_ranges)[len(prior_ranges) // 2]  # median

    if atr_n == 0:
        return float("nan"), yesterday_range

    return yesterday_range / atr_n, yesterday_range


def build_trade_pnl_by_date(params, spy_df, vix_df, start, end):
    """Run backtest and return {date: (dollar_pnl, entry_time_et)} dict."""
    result = run_backtest(spy_df, vix_df, start_date=start, end_date=end, **params)
    by_date = {}
    for trade in result.trades:
        d = trade.entry_time_et.date()
        prev_pnl = by_date.get(d, (0.0, trade.entry_time_et))[0]
        by_date[d] = (prev_pnl + trade.dollar_pnl, trade.entry_time_et)
    return by_date


def compute_atr_hybrid_pnl(on_by_date, off_by_date, daily_ranges, window, threshold, start, end):
    """
    For each trade date in [start, end]:
      if atr_ratio > threshold -> ON (high-range choppy yesterday)
      else -> OFF (calm trending yesterday)
    """
    all_dates = set(on_by_date) | set(off_by_date)
    dates_in_window = [d for d in all_dates if start <= d <= end]

    total = 0.0
    n = 0
    on_count = 0
    off_count = 0

    for d in sorted(dates_in_window):
        on_entry  = on_by_date.get(d)
        off_entry = off_by_date.get(d)

        atr_ratio, _ = get_atr_ratio(daily_ranges, d, window)
        use_on = (atr_ratio == atr_ratio) and atr_ratio > threshold  # NaN-safe

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


def print_atr_diagnostic(daily_ranges, trade_dates_by_window):
    """Print ATR range distribution per sub-window for each ATR window."""
    print("\n--- ATR range diagnostic per sub-window ---")
    sorted_dates = sorted(daily_ranges.keys())

    for wname, ws, we in SUBWINDOWS:
        sw_dates = [d for d in sorted_dates if ws.isoformat() <= d <= we.isoformat()]
        print(f"\n  {wname} ({ws} to {we}):")
        ranges_in_window = [daily_ranges[d] for d in sw_dates if d in daily_ranges]
        if ranges_in_window:
            s = sorted(ranges_in_window)
            n = len(s)
            med = s[n // 2]
            p25 = s[n // 4]
            p75 = s[3 * n // 4]
            print(f"    Daily range: median=${med:.2f}  p25=${p25:.2f}  p75=${p75:.2f}  n={n}")

        for window in ATR_WINDOWS:
            ratios = []
            for d_str in sw_dates:
                ratio, _ = get_atr_ratio(daily_ranges, dt.date.fromisoformat(d_str), window)
                if ratio == ratio:  # not NaN
                    ratios.append(ratio)
            if ratios:
                s = sorted(ratios)
                n = len(s)
                med = s[n // 2]
                p25 = s[n // 4]
                p75 = s[3 * n // 4]
                pct_above_1 = sum(1 for r in ratios if r > 1.0) / len(ratios) * 100
                print(f"    ATR_{window}d ratio: median={med:.2f}  p25={p25:.2f}  p75={p75:.2f}  pct>1.0={pct_above_1:.0f}%")


def analyze_atr_regime_conditional(spy_df, vix_df, daily_ranges):
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

    base_off_is_pnl  = sum(v[0] for v in off_is.values())
    base_off_oos_pnl = sum(v[0] for v in off_oos.values())
    base_off_is_n    = len(off_is)
    base_off_oos_n   = len(off_oos)

    print(f"Baseline OFF: IS n={base_off_is_n}  pnl=${base_off_is_pnl:+,.0f}  |  OOS n={base_off_oos_n}  pnl=${base_off_oos_pnl:+,.0f}")
    print(f"Baseline ON:  IS n={len(on_is)}  pnl=${sum(v[0] for v in on_is.values()):+,.0f}  |  OOS n={len(on_oos)}  pnl=${sum(v[0] for v in on_oos.values()):+,.0f}")

    print(f"\nATR-regime conditional: use ON when prior_day_ATR_ratio > threshold, else OFF")
    print(f"All comparisons vs OFF baseline (best absolute)")
    print(f"\n{'Win':>5}  {'Thr':>5}  {'IS_n':>5}  {'IS_pnl':>10}  {'IS_d':>8}  {'OOS_n':>5}  {'OOS_pnl':>10}  {'OOS_d':>8}  {'WF':>7}  {'ON%':>4}  {'SW_h':>4}  VERDICT")
    print("-" * 105)

    ratifiable = []

    for window in ATR_WINDOWS:
        for thr in ATR_THRESHOLDS:
            is_n, is_pnl, is_on, is_off = compute_atr_hybrid_pnl(
                on_is, off_is, daily_ranges, window, thr, IS_START, IS_END)
            oos_n, oos_pnl, oos_on, oos_off = compute_atr_hybrid_pnl(
                on_oos, off_oos, daily_ranges, window, thr, OOS_START, OOS_END)

            is_d  = is_pnl  - base_off_is_pnl
            oos_d = oos_pnl - base_off_oos_pnl

            n_is  = base_off_is_n  if base_off_is_n  else 1
            n_oos = base_off_oos_n if base_off_oos_n else 1
            wf = (oos_d / n_oos) / (is_d / n_is) if is_d != 0 else float("nan")

            sw_results = []
            sw_hurt = 0
            for wname, ws, we in SUBWINDOWS:
                sw_base = sum(v[0] for v in sw_off[wname].values())
                sw_n, sw_pnl, _, _ = compute_atr_hybrid_pnl(
                    sw_on[wname], sw_off[wname], daily_ranges, window, thr, ws, we)
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
            print(f"{window:>5}d  {thr:>5.2f}  {is_n:>5}  {is_pnl:>+10,.0f}  {is_d:>+8,.0f}  {oos_n:>5}  {oos_pnl:>+10,.0f}  {oos_d:>+8,.0f}  {wf_str:>7}  {on_pct:>3.0f}%  {sw_hurt:>4}  {verdict}")
            print(f"       SW: {' | '.join(sw_results)}")

    print()
    if ratifiable:
        best = max(ratifiable, key=lambda x: x[2])
        print(f"  *** RATIFIABLE: ATR_{best[0]}d ratio>{best[1]:.2f}  OOS_d={best[2]:+,.0f}  WF={best[3]:.3f} ***")
        print(f"  Action: implement prior_day_atr_ratio > {best[1]:.2f} chandelier switch in simulator + heartbeat")
    else:
        print(f"  No ratifiable ATR-regime threshold found.")
        print(f"  Conclusion: Realized price volatility (ATR) also cannot discriminate chandelier regimes.")
        print(f"  FINAL: chandelier ON (production Safe) is the confirmed local optimum.")
        print(f"  Research pivot: NLWB bullish setup or expanded IS period (add 2024 data).")


def main():
    print("Loading data...")
    spy_raw = pd.read_csv(MASTER_SPY)
    vix_raw = pd.read_csv(MASTER_VIX)
    print(f"SPY {len(spy_raw)} rows  VIX {len(vix_raw)} rows")

    # Normalize SPY timestamps to ET date/time strings
    spy_df = spy_raw.copy()
    ts_col = "timestamp_et" if "timestamp_et" in spy_df.columns else spy_df.columns[0]
    ts_parsed = pd.to_datetime(spy_df[ts_col], utc=True).dt.tz_convert("America/New_York")
    spy_df["date"] = ts_parsed.dt.date.astype(str)
    spy_df["time"] = ts_parsed.dt.strftime("%H:%M")

    # Normalize VIX timestamps
    vix_df = vix_raw.copy()
    ts_col_v = "timestamp_et" if "timestamp_et" in vix_df.columns else vix_df.columns[0]
    ts_parsed_v = pd.to_datetime(vix_df[ts_col_v], utc=True).dt.tz_convert("America/New_York")
    vix_df["date"] = ts_parsed_v.dt.date.astype(str)
    vix_df["time"] = ts_parsed_v.dt.strftime("%H:%M")

    print("\nATR-Regime Conditional Chandelier Analysis - Safe account")
    print("Hypothesis: prior_day_ATR_ratio > threshold -> choppy yesterday -> chandelier ON")
    print("            prior_day_ATR_ratio <= threshold -> calm yesterday -> chandelier OFF")
    print(f"Tested windows: {ATR_WINDOWS} days | Thresholds: {ATR_THRESHOLDS}")

    daily_ranges = build_daily_rth_range(spy_df)
    print(f"Daily RTH range series: {len(daily_ranges)} trading days")

    print_atr_diagnostic(daily_ranges, {})

    analyze_atr_regime_conditional(spy_df, vix_df, daily_ranges)

    print("\nDONE.")


if __name__ == "__main__":
    main()
