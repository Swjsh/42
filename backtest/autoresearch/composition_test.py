"""
COMPOSITION TEST: tighter_stop (-0.10) + vix_rising_deadband=0.15

Both candidates individually PASS all gates:
  1. tighter_stop (premium_stop_pct_bear=-0.10 vs -0.20): IS_delta=+8705, OOS_delta=+1802, WF=3.37
  2. vix_rising_deadband=0.15: IS_delta=+689, OOS_delta=+865, WF=20.4

Question: do they compose independently? Does applying BOTH produce OOS_delta ~= +2667?
If yes: combined candidate is stronger evidence for ratification.
If effects overlap: OOS improvement less than additive (some deadband entries are also the stop entries).

Security: read-only. No Alpaca calls. Free-tier only.
"""
from __future__ import annotations
import sys
import pathlib
import datetime as dt

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd
from backtest.lib.orchestrator import run_backtest

DATA_DIR = ROOT / "backtest" / "data"
SPY_FILE  = DATA_DIR / "spy_5m_2025-01-01_2026-05-22.csv"
VIX_FILE  = DATA_DIR / "vix_5m_2025-01-01_2026-05-22.csv"

IS_START  = dt.date(2025, 1, 2)
IS_END    = dt.date(2026, 5, 7)
OOS_START = dt.date(2026, 5, 8)
OOS_END   = dt.date(2026, 5, 22)

J_WINNERS = {dt.date(2026, 4, 29), dt.date(2026, 5, 1), dt.date(2026, 5, 4)}

BASE = dict(
    use_real_fills=True,
    premium_stop_pct_bear=-0.20,
    premium_stop_pct_bull=-0.08,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.50,
    time_stop_minutes_before_close=20,
    midday_trendline_gate=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    per_trade_risk_cap_pct=0.30,
)

TIGHTER_STOP = dict(BASE, premium_stop_pct_bear=-0.10)
DEADBAND_15  = BASE.copy()     # use params_overrides for filter const
COMBINED     = dict(TIGHTER_STOP)  # both tighter stop + deadband

DEADBAND_OVERRIDE = {"vix_rising_deadband": 0.15}


def _pnl(trades):
    return sum(t.dollar_pnl for t in trades)


def _date(t):
    et = t.entry_time_et
    d = et.replace(tzinfo=None) if getattr(et, "tzinfo", None) else et
    return d.date()


def _by_date(trades):
    result = {}
    for t in trades:
        d = _date(t)
        result[d] = result.get(d, 0.0) + t.dollar_pnl
    return result


def _anchor_ok(by_date, base_bd):
    for d in J_WINNERS:
        bp = base_bd.get(d, 0.0)
        cp = by_date.get(d, 0.0)
        if bp > 0 and cp < bp * 0.90:
            return False
    return True


def _run(spy, vix, start, end, params, overrides=None):
    kw = params.copy()
    if overrides:
        return run_backtest(spy, vix, start_date=start, end_date=end,
                            params_overrides=overrides, **kw)
    return run_backtest(spy, vix, start_date=start, end_date=end, **kw)


if __name__ == "__main__":
    print("=" * 90)
    print("COMPOSITION TEST: tighter_stop + vix_rising_deadband=0.15")
    print("=" * 90)

    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    # Baseline
    is_base  = _run(spy_df, vix_df, IS_START, IS_END, BASE)
    oos_base = _run(spy_df, vix_df, OOS_START, OOS_END, BASE)
    is_bp  = _pnl(is_base.trades)
    oos_bp = _pnl(oos_base.trades)
    is_bd  = _by_date(is_base.trades)
    n_is   = len(is_base.trades)
    n_oos  = len(oos_base.trades)
    print(f"\n[BASELINE] IS n={n_is} pnl={is_bp:+.0f}  OOS n={n_oos} pnl={oos_bp:+.0f}")

    # Tighter stop only
    is_ts  = _run(spy_df, vix_df, IS_START, IS_END, TIGHTER_STOP)
    oos_ts = _run(spy_df, vix_df, OOS_START, OOS_END, TIGHTER_STOP)
    is_ts_pnl  = _pnl(is_ts.trades)
    oos_ts_pnl = _pnl(oos_ts.trades)
    ts_is_d  = is_ts_pnl - is_bp
    ts_oos_d = oos_ts_pnl - oos_bp
    ts_wf = (ts_oos_d / n_oos) / (ts_is_d / n_is) if ts_is_d != 0 else 0.0
    ts_anchor = _anchor_ok(_by_date(is_ts.trades), is_bd)
    print(f"\n[TIGHTER STOP only]  IS delta={ts_is_d:+.0f}  OOS delta={ts_oos_d:+.0f}  WF={ts_wf:.3f}  anchor={'OK' if ts_anchor else 'FAIL'}")

    # Deadband=0.15 only
    is_db  = _run(spy_df, vix_df, IS_START, IS_END, BASE, DEADBAND_OVERRIDE)
    oos_db = _run(spy_df, vix_df, OOS_START, OOS_END, BASE, DEADBAND_OVERRIDE)
    is_db_pnl  = _pnl(is_db.trades)
    oos_db_pnl = _pnl(oos_db.trades)
    db_is_d  = is_db_pnl - is_bp
    db_oos_d = oos_db_pnl - oos_bp
    db_wf = (db_oos_d / n_oos) / (db_is_d / n_is) if db_is_d != 0 else 0.0
    db_anchor = _anchor_ok(_by_date(is_db.trades), is_bd)
    print(f"[DEADBAND=0.15 only]  IS n={len(is_db.trades)} delta={db_is_d:+.0f}  OOS n={len(oos_db.trades)} delta={db_oos_d:+.0f}  WF={db_wf:.3f}  anchor={'OK' if db_anchor else 'FAIL'}")

    # Combined: tighter stop + deadband
    is_comb  = _run(spy_df, vix_df, IS_START, IS_END, TIGHTER_STOP, DEADBAND_OVERRIDE)
    oos_comb = _run(spy_df, vix_df, OOS_START, OOS_END, TIGHTER_STOP, DEADBAND_OVERRIDE)
    is_comb_pnl  = _pnl(is_comb.trades)
    oos_comb_pnl = _pnl(oos_comb.trades)
    comb_is_d  = is_comb_pnl - is_bp
    comb_oos_d = oos_comb_pnl - oos_bp
    comb_wf = (comb_oos_d / n_oos) / (comb_is_d / n_is) if comb_is_d != 0 else 0.0
    comb_anchor = _anchor_ok(_by_date(is_comb.trades), is_bd)
    print(f"[COMBINED]            IS n={len(is_comb.trades)} delta={comb_is_d:+.0f}  OOS delta={comb_oos_d:+.0f}  WF={comb_wf:.3f}  anchor={'OK' if comb_anchor else 'FAIL'}")

    # Expected additive
    expected_is  = ts_is_d + db_is_d
    expected_oos = ts_oos_d + db_oos_d
    overlap_is   = expected_is - comb_is_d
    overlap_oos  = expected_oos - comb_oos_d
    print(f"\n[ADDITIVITY CHECK]")
    print(f"  Expected (additive sum): IS {expected_is:+.0f}  OOS {expected_oos:+.0f}")
    print(f"  Actual   (combined):     IS {comb_is_d:+.0f}  OOS {comb_oos_d:+.0f}")
    print(f"  Overlap (IS loss from non-additivity): {overlap_is:+.0f}")
    print(f"  Overlap (OOS loss from non-additivity): {overlap_oos:+.0f}")
    if abs(overlap_oos) < 200:
        print(f"  -> NEAR-INDEPENDENT: effects are approximately additive")
    else:
        print(f"  -> INTERACTION: effects are NOT additive (overlap = {overlap_oos:+.0f})")

    # Final verdict
    all_pass = comb_oos_d > 0 and comb_wf >= 0.70 and comb_anchor
    print(f"\n[COMBINED CANDIDATE VERDICT]")
    print(f"  OOS positive: {comb_oos_d > 0}")
    print(f"  WF >= 0.70: {comb_wf:.3f}")
    print(f"  Anchor OK: {comb_anchor}")
    print(f"  STATUS: {'PASS — combined candidate is viable' if all_pass else 'FAIL'}")
    if all_pass:
        print(f"\n  Deploy both changes together:")
        print(f"    1. premium_stop_pct_bear = -0.10 (in params.json + aggressive/params.json)")
        print(f"    2. vix_rising_deadband = 0.15 (in params.json + aggressive/params.json)")

    print("\nANALYSIS COMPLETE.")
