"""
VIX daily-regime gate for BEAR entries.

Hypothesis: IS drag in "VIX 22-30 range" trades is classified by DAILY VIX close,
not intraday VIX at entry. Instantaneous vix_hard_cap_bear can't filter them
(intraday VIX at entry-bar stays below 24 even when daily VIX close is 22-30).

Correct approach: use prior_day_vix or vix_5d_avg as regime signal.

This script sweeps vix_yesterday_max_bear and vix_5d_avg_max_bear:
- Block BEAR entries when prior_day_VIX > threshold
- Block BEAR entries when 5d_avg_VIX > threshold

Key constraint: DO NOT remove OOS BEAR trades in VIX 17-20 (declining recovery regime).
OOS n=21, pnl=+3728 — OOS uses May-June 2026 when daily VIX was ~17-22 DECLINING.

Implementation note: orchestrator doesn't currently support vix_yesterday/vix_5d_avg
params, so this script must implement the filter externally by:
1. Run baseline backtest to get IS/OOS trade list with entry dates
2. For each trade, look up prior_day VIX close in VIX daily CSV
3. Filter trades that would be blocked by the regime gate
4. Recompute P&L from filtered trade set
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

# Production Safe post-Rank35 parameters
BASE_KWARGS = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=True,
    premium_stop_pct_bear=-0.10,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.50,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.30,
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
    params_overrides={"vix_bull_max": 18.0},
)


def build_vix_daily(vix_5m: pd.DataFrame) -> pd.DataFrame:
    """Build daily VIX close series from 5-min VIX data."""
    vix_5m = vix_5m.copy()
    ts_col = "timestamp_et" if "timestamp_et" in vix_5m.columns else "timestamp"
    vix_5m[ts_col] = pd.to_datetime(vix_5m[ts_col], utc=True)
    vix_5m["date"] = vix_5m[ts_col].dt.date
    # Daily close = last bar's close
    daily = vix_5m.groupby("date")["close"].last().reset_index()
    daily.columns = ["date", "vix_close"]
    return daily


def get_prior_day_vix(entry_date: dt.date, daily_vix: pd.DataFrame) -> float | None:
    """Return prior trading day's VIX close."""
    prior = daily_vix[daily_vix["date"] < entry_date]
    if prior.empty:
        return None
    return prior.iloc[-1]["vix_close"]


def get_vix_5d_avg(entry_date: dt.date, daily_vix: pd.DataFrame, n: int = 5) -> float | None:
    """Return n-day average VIX close prior to entry_date."""
    prior = daily_vix[daily_vix["date"] < entry_date].tail(n)
    if len(prior) < n:
        return None
    return prior["vix_close"].mean()


def filter_by_regime(trades, daily_vix: pd.DataFrame,
                     yesterday_thresh: float | None,
                     avg5d_thresh: float | None) -> list:
    """Remove BEAR trades where daily-VIX regime exceeds threshold."""
    kept = []
    for t in trades:
        if t.side != "P":  # keep all BULL trades
            kept.append(t)
            continue
        entry_dt = getattr(t, "entry_time_et", None)
        if entry_dt is None:
            kept.append(t)
            continue
        entry_date = entry_dt.date() if hasattr(entry_dt, "date") else entry_dt

        blocked = False
        if yesterday_thresh is not None:
            prev = get_prior_day_vix(entry_date, daily_vix)
            if prev is not None and prev > yesterday_thresh:
                blocked = True
        if not blocked and avg5d_thresh is not None:
            avg5 = get_vix_5d_avg(entry_date, daily_vix)
            if avg5 is not None and avg5 > avg5d_thresh:
                blocked = True

        if not blocked:
            kept.append(t)
    return kept


def run():
    print("Loading data...")
    spy = pd.read_csv(MASTER_SPY)
    vix = pd.read_csv(MASTER_VIX)
    print(f"SPY {len(spy)} rows, VIX {len(vix)} rows")

    daily_vix = build_vix_daily(vix)
    print(f"Daily VIX built: {len(daily_vix)} trading days")

    # Baseline
    print("\nRunning baseline...")
    is_r = run_backtest(spy, vix, start_date=IS_START, end_date=IS_END, **BASE_KWARGS)
    oos_r = run_backtest(spy, vix, start_date=OOS_START, end_date=OOS_END, **BASE_KWARGS)
    base_is_pnl = sum(t.dollar_pnl for t in is_r.trades)
    base_oos_pnl = sum(t.dollar_pnl for t in oos_r.trades)
    print(f"BASE: IS n={len(is_r.trades)} pnl={base_is_pnl:+,.0f} | OOS n={len(oos_r.trades)} pnl={base_oos_pnl:+,.0f}")

    # Show prior_day and 5d_avg distribution of IS BEAR trades
    print("\n=== VIX DAILY CLOSE DISTRIBUTION (IS BEAR trades) ===")
    bear_is = [t for t in is_r.trades if t.side == "P"]
    buckets = {"<17": 0, "17-20": 0, "20-23": 0, "23-25": 0, "25-30": 0, "30+": 0}
    for t in bear_is:
        entry_dt = getattr(t, "entry_time_et", None)
        if entry_dt is None:
            continue
        entry_date = entry_dt.date() if hasattr(entry_dt, "date") else entry_dt
        prev = get_prior_day_vix(entry_date, daily_vix)
        if prev is None:
            continue
        if prev < 17:
            buckets["<17"] += 1
        elif prev < 20:
            buckets["17-20"] += 1
        elif prev < 23:
            buckets["20-23"] += 1
        elif prev < 25:
            buckets["23-25"] += 1
        elif prev < 30:
            buckets["25-30"] += 1
        else:
            buckets["30+"] += 1
    print("  prior_day_VIX distribution:")
    for bkt, n in buckets.items():
        print(f"    {bkt}: n={n}")

    print("\n=== VIX DAILY REGIME GATE SWEEP ===")
    print(f"{'yesterday_thresh':>18} {'5d_avg_thresh':>14} {'IS_n':>6} {'IS_rm':>6} {'IS_dlt':>8} {'OOS_dlt':>8} {'WF':>8} {'verdict':>16}")
    print("-" * 95)

    # Sweep: yesterday threshold (block if prior_day_VIX > thresh)
    yesterday_thresholds = [22.0, 23.0, 24.0, 25.0, 27.0, 30.0, None]
    avg5d_thresholds = [None, 20.0, 22.0, 25.0]

    results = []
    for y_thresh in yesterday_thresholds:
        for a_thresh in avg5d_thresholds:
            if y_thresh is None and a_thresh is None:
                continue  # skip no-gate case (same as baseline)

            is_filtered = filter_by_regime(is_r.trades, daily_vix, y_thresh, a_thresh)
            oos_filtered = filter_by_regime(oos_r.trades, daily_vix, y_thresh, a_thresh)

            is_pnl = sum(t.dollar_pnl for t in is_filtered)
            oos_pnl = sum(t.dollar_pnl for t in oos_filtered)
            is_rm = len(is_r.trades) - len(is_filtered)
            oos_rm = len(oos_r.trades) - len(oos_filtered)
            is_dlt = is_pnl - base_is_pnl
            oos_dlt = oos_pnl - base_oos_pnl

            # WF_norm = (oos_delta/n_oos) / (is_delta/n_is)
            n_is = len(is_r.trades)
            n_oos = len(oos_r.trades)
            if abs(is_dlt) < 1:
                wf_str = "INERT"
                verdict = "INERT"
            elif is_dlt <= 0:
                wf_str = "IS_NEG"
                verdict = "REJECT"
            elif oos_dlt < 0:
                wf_str = "OOS_NEG"
                verdict = "REJECT"
            else:
                wf = (oos_dlt / n_oos) / (is_dlt / n_is)
                wf_str = f"{wf:.3f}"
                verdict = "PASS" if wf >= 0.70 else "FAIL"

            y_label = f"{y_thresh:.0f}" if y_thresh is not None else "off"
            a_label = f"{a_thresh:.0f}" if a_thresh is not None else "off"
            print(f"{y_label:>18} {a_label:>14} {len(is_filtered):>6} {is_rm:>6} {is_dlt:>+8.0f} {oos_dlt:>+8.0f} {wf_str:>8} {verdict:>16}")

            results.append({
                "y_thresh": y_thresh, "a_thresh": a_thresh,
                "is_rm": is_rm, "oos_rm": oos_rm,
                "is_dlt": is_dlt, "oos_dlt": oos_dlt,
                "verdict": verdict,
            })

    # Best candidates
    passing = [r for r in results if r["verdict"] == "PASS"]
    print(f"\nPASS candidates: {len(passing)}")
    for r in passing:
        y_label = f"{r['y_thresh']:.0f}" if r["y_thresh"] is not None else "off"
        a_label = f"{r['a_thresh']:.0f}" if r["a_thresh"] is not None else "off"
        print(f"  yesterday>{y_label} AND 5d_avg>{a_label}: IS_rm={r['is_rm']} OOS_rm={r['oos_rm']} IS_dlt={r['is_dlt']:+.0f} OOS_dlt={r['oos_dlt']:+.0f}")

    print("\nVIX daily regime filter sweep complete.")


if __name__ == "__main__":
    run()
