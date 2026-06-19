"""
Quality filter sweep — entry-time setup quality gates.

Unlike VIX/gap/TL-time regime gates (all C22-vulnerable), these params
measure quality AT THE MOMENT of entry, not backward-looking regime state.
They should be less susceptible to the IS-tariff-shock vs OOS-recovery flip.

Params tested:
1. filter_9_vol_multiplier: 0.5, 0.7(current), 0.9, 1.1
   -> Requires entry-bar volume >= X * 20-bar baseline. Higher = stricter.
2. wick_min_pct_of_range: 0.40, 0.50(current), 0.60, 0.70
   -> Upper wick must be >= X% of bar range for wick_rejection trigger.
3. wick_min_dollars: 0.10, 0.15(current), 0.20, 0.25
   -> Upper wick must be >= X dollars.
4. confluence_tolerance_dollars: 0.20, 0.30(current), 0.40, 0.50
   -> Multi-day touch within +-X of today's tested level = confluence.
5. ribbon_spread_min_cents: 20, 30(current), 40, 50
   -> Ribbon bull/bear EMAs must be >= X cents apart at entry.

For each, we test: (1) IS sub-window stability (HURT <= 1 of 4), (2) OOS delta.
A quality gate is non-C22 if its improvement is spread across all IS sub-windows,
not concentrated in W4_Apr26 (the tariff-shock window).

Corrected baseline (through Rank 35):
  IS n=128 pnl=+12838, OOS n=21 pnl=+3728
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

IS_S = dt.date(2025, 1, 2)
IS_E = dt.date(2026, 5, 7)
OOS_S = dt.date(2026, 5, 8)
OOS_E = dt.date(2026, 6, 16)

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

WINDOWS = [
    ("W1_2025H1", dt.date(2025, 1, 2), dt.date(2025, 6, 30)),
    ("W2_2025H2", dt.date(2025, 7, 1), dt.date(2025, 12, 31)),
    ("W3_Q12026", dt.date(2026, 1, 2), dt.date(2026, 3, 31)),
    ("W4_Apr26",  dt.date(2026, 4, 1), dt.date(2026, 5, 7)),
]


def run_with_override(spy_df, vix_df, start, end, param_key, value):
    """Run backtest with one params_overrides key changed."""
    kw = dict(BASE_KWARGS)
    po = dict(kw.get("params_overrides", {}))
    po[param_key] = value
    kw["params_overrides"] = po
    return run_backtest(spy_df, vix_df, start_date=start, end_date=end, **kw)


def sweep_param(spy_df, vix_df, param_key, values, current_val, label):
    """Sweep one param across values. Report IS delta, OOS delta, SW stability."""
    print(f"\n\n{'='*60}")
    print(f"PARAM: {label} (key={param_key})")
    print(f"  Current: {current_val}")
    print(f"{'='*60}")

    # Base IS and OOS
    is_base = run_backtest(spy_df, vix_df, start_date=IS_S, end_date=IS_E, **BASE_KWARGS)
    oos_base = run_backtest(spy_df, vix_df, start_date=OOS_S, end_date=OOS_E, **BASE_KWARGS)
    is_base_pnl = sum(t.dollar_pnl for t in is_base.trades)
    oos_base_pnl = sum(t.dollar_pnl for t in oos_base.trades)
    n_is = len(is_base.trades)
    n_oos = len(oos_base.trades)

    best_oos_candidate = None
    best_oos_delta = -99999

    for val in values:
        is_r = run_with_override(spy_df, vix_df, IS_S, IS_E, param_key, val)
        oos_r = run_with_override(spy_df, vix_df, OOS_S, OOS_E, param_key, val)
        is_pnl = sum(t.dollar_pnl for t in is_r.trades)
        oos_pnl = sum(t.dollar_pnl for t in oos_r.trades)
        is_delta = is_pnl - is_base_pnl
        oos_delta = oos_pnl - oos_base_pnl
        n_is_chg = n_is - len(is_r.trades)
        n_oos_chg = n_oos - len(oos_r.trades)

        # Sub-window stability
        hurt = 0
        sw_details = []
        for sw_name, ws, we in WINDOWS:
            sw_base_r = run_backtest(spy_df, vix_df, start_date=ws, end_date=we, **BASE_KWARGS)
            sw_cand_r = run_with_override(spy_df, vix_df, ws, we, param_key, val)
            sw_delta = sum(t.dollar_pnl for t in sw_cand_r.trades) - sum(t.dollar_pnl for t in sw_base_r.trades)
            verdict = "HELP" if sw_delta > 0 else "FLAT" if sw_delta == 0 else "HURT"
            if verdict == "HURT":
                hurt += 1
            sw_details.append(f"{sw_name}:{sw_delta:+.0f}({verdict})")

        wf = None
        if is_delta != 0 and oos_delta != 0 and len(is_r.trades) > 0:
            wf = (oos_delta / n_oos) / (is_delta / n_is)

        is_sign = "GOOD" if is_delta > 0 else "BAD"
        oos_sign = "GOOD" if oos_delta > 0 else "BAD"
        sw_ok = hurt <= 1

        # C22 check: Apr26 contribution to IS delta
        w4_base_r = run_backtest(spy_df, vix_df, start_date=dt.date(2026, 4, 1), end_date=dt.date(2026, 5, 7), **BASE_KWARGS)
        w4_cand_r = run_with_override(spy_df, vix_df, dt.date(2026, 4, 1), dt.date(2026, 5, 7), param_key, val)
        w4_delta = sum(t.dollar_pnl for t in w4_cand_r.trades) - sum(t.dollar_pnl for t in w4_base_r.trades)
        if is_delta != 0 and w4_delta != 0:
            apr26_contribution = w4_delta / is_delta * 100
        else:
            apr26_contribution = 0.0
        c22_risk = "HIGH-C22" if apr26_contribution > 50 else "LOW-C22" if apr26_contribution > 0 else "OK"

        wf_str = f"{wf:.3f}" if wf is not None else "N/A"
        print(f"\n  val={val}:")
        print(f"    IS: delta={is_delta:+.0f} n_chg={n_is_chg:+d} [{is_sign}]")
        print(f"    OOS: delta={oos_delta:+.0f} n_chg={n_oos_chg:+d} [{oos_sign}]")
        print(f"    WF={wf_str} SW_hurt={hurt}/4 [{('STABLE' if sw_ok else 'UNSTABLE')}]")
        print(f"    SW: {' | '.join(sw_details)}")
        print(f"    C22 check: Apr26 contribution={apr26_contribution:.0f}% [{c22_risk}]")

        if is_delta > 0 and oos_delta > best_oos_delta:
            best_oos_delta = oos_delta
            best_oos_candidate = {"param_key": param_key, "value": val,
                                   "is_delta": is_delta, "oos_delta": oos_delta,
                                   "wf": wf, "sw_hurt": hurt, "c22_risk": c22_risk}

    return best_oos_candidate


def main():
    print("Loading data...")
    spy = pd.read_csv(MASTER_SPY)
    vix = pd.read_csv(MASTER_VIX)
    print(f"SPY {len(spy)} rows, VIX {len(vix)} rows")

    candidates = []

    # 1. Filter-9 volume multiplier
    c = sweep_param(spy, vix,
                    "filter_9_vol_multiplier",
                    [0.5, 0.9, 1.1, 1.3],  # skip current (0.7)
                    0.7, "Filter-9 vol multiplier")
    if c:
        candidates.append(c)

    # 2. Wick min pct of range
    c = sweep_param(spy, vix,
                    "wick_min_pct_of_range",
                    [0.40, 0.60, 0.70],  # skip current (0.50)
                    0.50, "Wick min pct of range")
    if c:
        candidates.append(c)

    # 3. Wick min dollars
    c = sweep_param(spy, vix,
                    "wick_min_dollars",
                    [0.10, 0.20, 0.25, 0.30],  # skip current (0.15)
                    0.15, "Wick min dollars")
    if c:
        candidates.append(c)

    # 4. Confluence tolerance dollars
    c = sweep_param(spy, vix,
                    "confluence_tolerance_dollars",
                    [0.20, 0.40, 0.50],  # skip current (0.30)
                    0.30, "Confluence tolerance dollars")
    if c:
        candidates.append(c)

    # 5. Ribbon spread min cents
    c = sweep_param(spy, vix,
                    "ribbon_spread_min_cents",
                    [20, 40, 50],  # skip current (30)
                    30, "Ribbon spread min cents")
    if c:
        candidates.append(c)

    # Summary
    print("\n\n" + "="*60)
    print("SUMMARY: Best candidates per param (IS positive + OOS best)")
    print("="*60)
    for c in candidates:
        print(f"  {c['param_key']}={c['value']}: IS={c['is_delta']:+.0f} OOS={c['oos_delta']:+.0f} "
              f"WF={c['wf']:.3f if c['wf'] else 'N/A'} SW_hurt={c['sw_hurt']}/4 C22={c['c22_risk']}")

    print("\nFull quality gate sweep complete.")


if __name__ == "__main__":
    main()
