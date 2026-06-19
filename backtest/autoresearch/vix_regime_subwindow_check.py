"""
Sub-window stability check for vix_daily_regime candidate:
  Gate: block BEAR entries when 5-day avg prior VIX close > 20.0

Expected: improvement concentrated in W4_Apr26 (tariff shock). If so -> NOT sub-window stable -> REJECT.
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

IS_SUBWINDOWS = [
    ("W1_2025H1", dt.date(2025, 1, 2),  dt.date(2025, 6, 30)),
    ("W2_2025H2", dt.date(2025, 7, 1),  dt.date(2025, 12, 31)),
    ("W3_Q12026", dt.date(2026, 1, 1),  dt.date(2026, 3, 31)),
    ("W4_Apr26",  dt.date(2026, 4, 1),  dt.date(2026, 5, 7)),
]
OOS_SUBWINDOWS = [
    ("OOS_W1",   dt.date(2026, 5, 8),   dt.date(2026, 5, 22)),
    ("OOS_W2",   dt.date(2026, 5, 23),  dt.date(2026, 6, 16)),
]


def build_vix_daily(vix_5m: pd.DataFrame) -> pd.DataFrame:
    vix_5m = vix_5m.copy()
    ts_col = "timestamp_et" if "timestamp_et" in vix_5m.columns else "timestamp"
    vix_5m[ts_col] = pd.to_datetime(vix_5m[ts_col], utc=True)
    vix_5m["date"] = vix_5m[ts_col].dt.date
    daily = vix_5m.groupby("date")["close"].last().reset_index()
    daily.columns = ["date", "vix_close"]
    return daily


def get_vix_5d_avg(entry_date: dt.date, daily_vix: pd.DataFrame) -> float | None:
    prior = daily_vix[daily_vix["date"] < entry_date].tail(5)
    if len(prior) < 5:
        return None
    return prior["vix_close"].mean()


def filter_5d_avg(trades, daily_vix: pd.DataFrame, threshold: float = 20.0) -> list:
    kept = []
    for t in trades:
        if getattr(t, "side", "P") != "P":
            kept.append(t)
            continue
        entry_dt = getattr(t, "entry_time_et", None)
        if entry_dt is None:
            kept.append(t)
            continue
        entry_date = entry_dt.date() if hasattr(entry_dt, "date") else entry_dt
        avg5 = get_vix_5d_avg(entry_date, daily_vix)
        if avg5 is None or avg5 <= threshold:
            kept.append(t)
    return kept


def run():
    print("Loading data...")
    spy = pd.read_csv(MASTER_SPY)
    vix = pd.read_csv(MASTER_VIX)
    daily_vix = build_vix_daily(vix)
    print(f"Daily VIX: {len(daily_vix)} trading days")

    print("\n=== FULL IS/OOS BASELINE vs GATE ===")
    is_r = run_backtest(spy, vix, start_date=IS_START, end_date=IS_END, **BASE_KWARGS)
    oos_r = run_backtest(spy, vix, start_date=OOS_START, end_date=OOS_END, **BASE_KWARGS)

    base_is = sum(t.dollar_pnl for t in is_r.trades)
    base_oos = sum(t.dollar_pnl for t in oos_r.trades)

    filt_is = filter_5d_avg(is_r.trades, daily_vix)
    filt_oos = filter_5d_avg(oos_r.trades, daily_vix)

    gate_is = sum(t.dollar_pnl for t in filt_is)
    gate_oos = sum(t.dollar_pnl for t in filt_oos)

    is_rm = len(is_r.trades) - len(filt_is)
    oos_rm = len(oos_r.trades) - len(filt_oos)
    is_dlt = gate_is - base_is
    oos_dlt = gate_oos - base_oos

    print(f"BASE:  IS n={len(is_r.trades)} pnl={base_is:+,.0f}  |  OOS n={len(oos_r.trades)} pnl={base_oos:+,.0f}")
    print(f"GATE:  IS n={len(filt_is)} rm={is_rm} pnl={gate_is:+,.0f} dlt={is_dlt:+,.0f}  |  OOS n={len(filt_oos)} rm={oos_rm} pnl={gate_oos:+,.0f} dlt={oos_dlt:+,.0f}")
    if abs(is_dlt) > 0:
        wf = (oos_dlt / len(oos_r.trades)) / (is_dlt / len(is_r.trades))
        print(f"WF={wf:.3f}")

    # Show WHICH IS trades are blocked (the 22 removed trades)
    blocked_is = [t for t in is_r.trades if t not in filt_is]
    if blocked_is:
        print(f"\n=== BLOCKED IS TRADES (n={len(blocked_is)}) ===")
        for t in blocked_is:
            entry_dt = getattr(t, "entry_time_et", None)
            entry_date = entry_dt.date() if hasattr(entry_dt, "date") else None
            avg5 = get_vix_5d_avg(entry_date, daily_vix) if entry_date else None
            vix_now = getattr(t, "entry_vix", None)
            pnl = t.dollar_pnl
            print(f"  {entry_dt} | 5d_avg_VIX={avg5:.1f} | intraday_VIX={vix_now:.1f} | pnl={pnl:+.0f}")

    print("\n=== IS SUB-WINDOW STABILITY ===")
    print(f"{'Window':>12} {'base_n':>7} {'base_pnl':>10} {'gate_n':>7} {'gate_pnl':>10} {'delta':>8} {'rm':>4} {'verdict':>8}")
    print("-" * 80)
    hurt = 0
    for name, ws, we in IS_SUBWINDOWS:
        sw_r = run_backtest(spy, vix, start_date=ws, end_date=we, **BASE_KWARGS)
        sw_f = filter_5d_avg(sw_r.trades, daily_vix)
        base_p = sum(t.dollar_pnl for t in sw_r.trades)
        gate_p = sum(t.dollar_pnl for t in sw_f)
        delta = gate_p - base_p
        rm = len(sw_r.trades) - len(sw_f)
        verdict = "HELP" if delta >= 0 else "HURT"
        if delta < 0:
            hurt += 1
        print(f"{name:>12} {len(sw_r.trades):>7} {base_p:>+10.0f} {len(sw_f):>7} {gate_p:>+10.0f} {delta:>+8.0f} {rm:>4} {verdict:>8}")

    print(f"\nIS sub-windows HURT: {hurt}/4 (gate: 0 for PASS, <=1 for MARGINAL)")

    print("\n=== OOS SUB-WINDOW BREAKDOWN ===")
    print(f"{'Window':>12} {'base_n':>7} {'base_pnl':>10} {'gate_n':>7} {'gate_pnl':>10} {'delta':>8} {'rm':>4}")
    print("-" * 65)
    for name, ws, we in OOS_SUBWINDOWS:
        sw_r = run_backtest(spy, vix, start_date=ws, end_date=we, **BASE_KWARGS)
        sw_f = filter_5d_avg(sw_r.trades, daily_vix)
        base_p = sum(t.dollar_pnl for t in sw_r.trades)
        gate_p = sum(t.dollar_pnl for t in sw_f)
        delta = gate_p - base_p
        rm = len(sw_r.trades) - len(sw_f)
        print(f"{name:>12} {len(sw_r.trades):>7} {base_p:>+10.0f} {len(sw_f):>7} {gate_p:>+10.0f} {delta:>+8.0f} {rm:>4}")

    print("\nVIX daily regime 5d_avg>20 sub-window check complete.")


if __name__ == "__main__":
    run()
