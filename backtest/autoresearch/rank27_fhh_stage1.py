"""
Rank 27: FIRST_HOUR_RTH_HIGH_LEVEL — Stage-1 OOS backtest.
Question: does include_first_hour_high=True add harmful entries across IS/OOS?

Key checks:
1. N new entries added (via fhh_level_rejection trigger)
2. Net IS/OOS P&L delta
3. Anchor day impact (must not hurt 4/29, 5/01, 5/04)
4. Sub-window stability
5. FHH specifically: does 5/01 11:50 fire? (Expected: NO due to filter_5 ribbon=BULL hard block)
"""
import sys
import datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd
from backtest.lib.orchestrator import run_backtest

DATA_DIR  = ROOT / "backtest" / "data"
SPY_FILE  = DATA_DIR / "spy_5m_2025-01-01_2026-05-22.csv"
VIX_FILE  = DATA_DIR / "vix_5m_2025-01-01_2026-05-22.csv"

IS_START  = dt.date(2025, 1, 2)
IS_END    = dt.date(2026, 5, 7)
OOS_START = dt.date(2026, 5, 8)
OOS_END   = dt.date(2026, 5, 22)

J_WINNERS = {dt.date(2026, 4, 29), dt.date(2026, 5, 1), dt.date(2026, 5, 4)}

BASE = dict(
    use_real_fills=True,
    premium_stop_pct_bear=-0.10,
    premium_stop_pct_bull=-0.08,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.50,
    time_stop_minutes_before_close=20,
    midday_trendline_gate=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    per_trade_risk_cap_pct=0.30,
    block_level_rejection=True,
)


def get_entry_date(t):
    et = t.entry_time_et
    if hasattr(et, "date"):
        return et.date()
    return dt.date.fromisoformat(str(et)[:10])


def pnl_window(trades, start, end):
    return sum(t.dollar_pnl for t in trades if start <= get_entry_date(t) <= end)


def main():
    print("Loading data...")
    spy = pd.read_csv(SPY_FILE)
    vix = pd.read_csv(VIX_FILE)

    print("Running IS BASE + CANDIDATE...")
    is_base = run_backtest(spy, vix, start_date=IS_START, end_date=IS_END, **BASE)
    is_cand = run_backtest(spy, vix, start_date=IS_START, end_date=IS_END,
                           **BASE, include_first_hour_high=True)

    print("Running OOS BASE + CANDIDATE...")
    oos_base = run_backtest(spy, vix, start_date=OOS_START, end_date=OOS_END, **BASE)
    oos_cand = run_backtest(spy, vix, start_date=OOS_START, end_date=OOS_END,
                            **BASE, include_first_hour_high=True)

    is_base_pnl = sum(t.dollar_pnl for t in is_base.trades)
    is_cand_pnl = sum(t.dollar_pnl for t in is_cand.trades)
    oos_base_pnl = sum(t.dollar_pnl for t in oos_base.trades)
    oos_cand_pnl = sum(t.dollar_pnl for t in oos_cand.trades)

    is_delta  = is_cand_pnl - is_base_pnl
    oos_delta = oos_cand_pnl - oos_base_pnl

    print(f"\n{'='*72}")
    print("RANK 27: include_first_hour_high=True")
    print(f"{'='*72}")
    print(f"  IS:  base n={len(is_base.trades):4d} pnl={is_base_pnl:+,.0f}  "
          f"cand n={len(is_cand.trades):4d} pnl={is_cand_pnl:+,.0f}  delta={is_delta:+,.0f}")
    print(f"  OOS: base n={len(oos_base.trades):4d} pnl={oos_base_pnl:+,.0f}  "
          f"cand n={len(oos_cand.trades):4d} pnl={oos_cand_pnl:+,.0f}  delta={oos_delta:+,.0f}")

    n_is_base, n_oos_base = len(is_base.trades), len(oos_base.trades)
    if is_delta != 0 and n_is_base > 0 and n_oos_base > 0:
        wf = (oos_delta / n_oos_base) / (is_delta / n_is_base)
        print(f"  WF_norm = {wf:.3f}  ({'PASS' if wf >= 0.70 and oos_delta > 0 else 'FAIL'})")
    else:
        print(f"  WF_norm = N/A (IS_delta={is_delta})")

    # Anchor check
    print(f"\n  J anchor days:")
    for d in sorted(J_WINNERS):
        b_is = pnl_window(is_base.trades, d, d)
        c_is = pnl_window(is_cand.trades, d, d)
        b_oos = pnl_window(oos_base.trades, d, d)
        c_oos = pnl_window(oos_cand.trades, d, d)
        pnl = b_is if b_is != 0 else b_oos
        cand_pnl = c_is if c_is != 0 else c_oos
        delta = cand_pnl - pnl
        status = "OK" if delta >= 0 else "HURT"
        print(f"    {d}  base={pnl:+,.0f}  cand={cand_pnl:+,.0f}  delta={delta:+,.0f}  {status}")

    # 5/01 specifically: does 11:50 fire?
    print(f"\n  5/01 trades in CANDIDATE (fhh_level_rejection check):")
    may1 = dt.date(2026, 5, 1)
    for t in is_cand.trades:
        if get_entry_date(t) == may1:
            print(f"    {t.entry_time_et}  pnl={t.dollar_pnl:+,.0f}  trigs={t.triggers_fired}")
    for t in oos_cand.trades:
        if get_entry_date(t) == may1:
            print(f"    {t.entry_time_et}  pnl={t.dollar_pnl:+,.0f}  trigs={t.triggers_fired}")

    # FHH entries added (new trades that have fhh_level_rejection in triggers)
    print(f"\n  New IS trades with fhh_level_rejection (in CANDIDATE, not in BASE):")
    base_is_times = {str(t.entry_time_et)[:16] for t in is_base.trades}
    fhh_is_new = [t for t in is_cand.trades
                   if "fhh_level_rejection" in (t.triggers_fired or [])
                   and str(t.entry_time_et)[:16] not in base_is_times]

    if fhh_is_new:
        for t in fhh_is_new[:10]:
            d = get_entry_date(t)
            print(f"    {d} {str(t.entry_time_et)[11:16]}  pnl={t.dollar_pnl:+,.0f}  "
                  f"trigs={t.triggers_fired}  vix={t.entry_vix:.1f}")
        if len(fhh_is_new) > 10:
            print(f"    ... +{len(fhh_is_new)-10} more")
        fhh_is_pnl = sum(t.dollar_pnl for t in fhh_is_new)
        wr = sum(1 for t in fhh_is_new if t.dollar_pnl > 0) / len(fhh_is_new)
        print(f"    Total fhh_level_rejection IS new trades: n={len(fhh_is_new)}, "
              f"pnl={fhh_is_pnl:+,.0f}, WR={wr:.1%}")
    else:
        print("    (none)")

    # OOS fhh entries
    base_oos_times = {str(t.entry_time_et)[:16] for t in oos_base.trades}
    fhh_oos_new = [t for t in oos_cand.trades
                    if "fhh_level_rejection" in (t.triggers_fired or [])
                    and str(t.entry_time_et)[:16] not in base_oos_times]
    print(f"\n  New OOS trades with fhh_level_rejection: n={len(fhh_oos_new)}")
    for t in fhh_oos_new:
        d = get_entry_date(t)
        print(f"    {d} {str(t.entry_time_et)[11:16]}  pnl={t.dollar_pnl:+,.0f}  "
              f"trigs={t.triggers_fired}  vix={t.entry_vix:.1f}")

    print("\n[ANALYSIS COMPLETE]")


if __name__ == "__main__":
    main()
