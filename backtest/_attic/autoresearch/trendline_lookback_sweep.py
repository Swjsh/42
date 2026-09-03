"""
Trendline Quality Sweep -- lookback_bars and min_swings.

Hypothesis (cook queue task 84a8a9d0):
  Fresh trendlines (shorter lookback) may give better WR than stale ones.
  More swing points required (higher min_swings) may improve quality.

Current production:
  TRENDLINE_LOOKBACK_BARS = 60  (look back 300 min = 5 hours for swing highs)
  TRENDLINE_MIN_SWINGS = 3     (need 3 swing highs for valid trendline)

Security note: read-only. No Alpaca tools. $0 cost.
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

IS_S  = dt.date(2025, 1, 2)
IS_E  = dt.date(2026, 5, 7)
OOS_S = dt.date(2026, 5, 8)
OOS_E = dt.date(2026, 6, 16)

SUBWINDOWS = [
    ("W1_2025H1", dt.date(2025, 1, 2),  dt.date(2025, 6, 30)),
    ("W2_2025Q3", dt.date(2025, 7, 1),  dt.date(2025, 9, 30)),
    ("W3_2025Q4", dt.date(2025, 10, 1), dt.date(2025, 12, 31)),
    ("W4_2026H1", dt.date(2026, 1, 2),  dt.date(2026, 5, 7)),
]

SAFE_BASE = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=True,
    premium_stop_pct_bear=-0.10,
    tp1_premium_pct=0.50,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.5,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.30,
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
    params_overrides={"vix_bull_max": 18.0},
    profit_lock_threshold_pct=0.05,
    profit_lock_stop_offset_pct=0.10,
    profit_lock_mode="trailing",
    profit_lock_trail_pct=0.20,
)

LOOKBACK_VALUES = [30, 40, 60, 80, 100]
MINSWINGS_VALUES = [2, 3, 4, 5]


def run_with_overrides(spy, vix, start, end, tl_lookback=60, tl_min_swings=3):
    params = dict(SAFE_BASE)
    overrides = dict(params.get("params_overrides", {}))
    overrides["trendline_lookback_bars"] = tl_lookback
    overrides["trendline_min_swings"]    = tl_min_swings
    params["params_overrides"] = overrides
    return run_backtest(spy, vix, start_date=start, end_date=end, **params)


def total_pnl(result):
    return sum(t.dollar_pnl for t in result.trades)


def wf_norm(oos_d, n_oos, is_d, n_is):
    if is_d == 0 or n_is == 0 or n_oos == 0:
        return float("nan")
    return (oos_d / n_oos) / (is_d / n_is)


def main():
    out_path = ROOT / "backtest" / "autoresearch" / "results" / "trendline_lookback_sweep.txt"
    lines = []

    def emit(s=""):
        lines.append(s)
        print(s)

    emit("Loading data...")
    spy = pd.read_csv(MASTER_SPY)
    vix = pd.read_csv(MASTER_VIX)
    emit(f"SPY {len(spy)} rows  VIX {len(vix)} rows")

    emit("=" * 70)
    emit("Trendline Quality Sweep -- SAFE account (current production params)")
    emit("Baseline: lookback=60 bars, min_swings=3")
    emit("=" * 70)

    emit("Running baseline (lookback=60, min_swings=3)...")
    b_is   = run_with_overrides(spy, vix, IS_S,  IS_E)
    b_oos  = run_with_overrides(spy, vix, OOS_S, OOS_E)
    b_is_pnl  = total_pnl(b_is)
    b_oos_pnl = total_pnl(b_oos)
    n_is  = len(b_is.trades)
    n_oos = len(b_oos.trades)
    emit(f"Baseline: IS n={n_is}  pnl={b_is_pnl:+,.0f}  |  OOS n={n_oos}  pnl={b_oos_pnl:+,.0f}")

    def sweep_param(param_name, values, baseline_val, kw_name):
        emit()
        emit("-" * 70)
        emit(f"SWEEP: {param_name} (other params at baseline)")
        hdr = f"  {param_name[:8]:>8} {'IS_n':>5} {'IS_pnl':>10} {'IS_d':>8} {'OOS_n':>6} {'OOS_pnl':>10} {'OOS_d':>8} {'WF':>8} {'SW_h':>5} VERDICT"
        emit(hdr)
        emit("  " + "-" * 82)
        ratifiable = []
        for val in values:
            kwargs = {kw_name: val}
            r_is  = run_with_overrides(spy, vix, IS_S,  IS_E,  **kwargs)
            r_oos = run_with_overrides(spy, vix, OOS_S, OOS_E, **kwargs)
            is_pnl  = total_pnl(r_is)
            oos_pnl = total_pnl(r_oos)
            is_d  = is_pnl  - b_is_pnl
            oos_d = oos_pnl - b_oos_pnl
            wf    = wf_norm(oos_d, n_oos, is_d, n_is)
            wf_s  = f"{wf:.3f}" if wf == wf else "  nan"
            sw_hurt = 0
            sw_tags = []
            for wname, ws, we in SUBWINDOWS:
                sw_base = run_with_overrides(spy, vix, ws, we, **{kw_name: baseline_val})
                sw_cand = run_with_overrides(spy, vix, ws, we, **kwargs)
                sw_d = total_pnl(sw_cand) - total_pnl(sw_base)
                tag = "H" if sw_d > 50 else ("X" if sw_d < -50 else "F")
                if tag == "X":
                    sw_hurt += 1
                sw_tags.append(f"{wname[:6]}:{sw_d:+.0f}")
            oos_pos = oos_d > 0
            wf_ok   = wf == wf and wf >= 0.70
            sw_ok   = sw_hurt <= 1
            if val == baseline_val:
                verdict = "BASELINE"
            elif oos_pos and wf_ok and sw_ok:
                verdict = "RATIFIABLE"
                ratifiable.append((val, oos_d, wf))
            elif not oos_pos:
                verdict = "OOS_NEG"
            elif not wf_ok:
                verdict = f"WF_FAIL({wf_s})"
            else:
                verdict = f"SW_FAIL({sw_hurt})"
            emit(f"  {val:>8} {len(r_is.trades):>5} {is_pnl:>+10,.0f} {is_d:>+8,.0f} {len(r_oos.trades):>6} {oos_pnl:>+10,.0f} {oos_d:>+8,.0f} {wf_s:>8} {sw_hurt:>5} {verdict}")
            emit(f"           SW: {' | '.join(sw_tags)}")
        if ratifiable:
            best = max(ratifiable, key=lambda x: x[1])
            emit(f"  *** BEST RATIFIABLE: {param_name}={best[0]}  OOS_d={best[1]:+,.0f}  WF={best[2]:.3f} ***")
        else:
            emit(f"  No ratifiable {param_name} found. Baseline confirmed.")

    sweep_param("lookback_bars", LOOKBACK_VALUES, 60, "tl_lookback")
    sweep_param("min_swings",    MINSWINGS_VALUES,  3, "tl_min_swings")

    emit()
    emit("DONE.")
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nResults written to {out_path}")


if __name__ == "__main__":
    main()
