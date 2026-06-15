"""Walk-forward validation for Config F27 (vix_soft + allow_one_blocker + min_spread=27c).

OP-20 requirement #3: out-of-sample test with train <= T-1, test on held-out window.

Protocol:
  Train period: Jan 2025 - Dec 2025 (the "in-sample" period for parameter discovery)
  Test period:  Jan 2026 - May 2026 (the "out-of-sample" period, 2026 is a fresh regime)

The 27c threshold was derived from 3 specific Jan-May 2026 days (J's winner days).
If the parameter was overfit to those days, it may:
  (a) regress on Jan-Mar 2026 days not in the J set, or
  (b) show meaningfully different characteristics in the 2025 in-sample vs 2026 test periods

Metrics compared (train vs test):
  - Sharpe ratio
  - Win rate
  - Total P&L per trading day
  - Max drawdown

OP-20 pass criteria (all required):
  - Test Sharpe >= 0.5 (positive edge in out-of-sample period)
  - Test P&L/day >= Train P&L/day × 0.5 (test not more than 50% worse)
  - Test win_rate >= 40% (edge survives regime change)
  - Test max_drawdown <= Train max_drawdown × 1.5 (risk not blown up in OOS)

Usage: python backtest/autoresearch/vix_soft_walk_forward.py
Output: analysis/recommendations/vix_soft_walk_forward.json
Cost: $0 (pure Python)
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import statistics
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from lib.orchestrator import run_backtest

BASE_KWARGS = dict(
    use_real_fills=True,
    premium_stop_pct=-0.08,
    premium_stop_pct_bear=-0.08,
    premium_stop_pct_bull=-0.08,
    tp1_premium_pct=0.30,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.0,
    strike_offset=0,
    no_trade_before=dt.time(9, 35),
    no_trade_window=None,
    profit_lock_mode="trailing",
    profit_lock_threshold_pct=0.05,
    profit_lock_stop_offset_pct=0.10,
    profit_lock_trail_pct=0.20,
    f9_vol_mult=0.7,
)

CONFIGS = {
    "A_baseline": {},
    "B_vix_soft": {"vix_soft_mode": True},
    "F27": {"vix_soft_mode": True, "allow_one_blocker": True, "allow_one_blocker_min_spread_cents": 27},
}

TRAIN_START = dt.date(2025, 1, 2)
TRAIN_END = dt.date(2025, 12, 31)
TEST_START = dt.date(2026, 1, 2)
TEST_END = dt.date(2026, 5, 15)

# J's source-of-truth days (for OP-16 gate within test period)
J_WINNER_DAYS = {"2026-04-29": 342, "2026-05-01": 470, "2026-05-04": 730}
J_LOSER_DAYS = {"2026-05-05": -260, "2026-05-06": -300, "2026-05-07": -165}
OP16_FLOOR = 771
MAX_EDGE = 1542


def sharpe(daily_pnls: list[float], ann_factor: float = 252 ** 0.5) -> float:
    if len(daily_pnls) < 2:
        return 0.0
    mu = sum(daily_pnls) / len(daily_pnls)
    sigma = statistics.stdev(daily_pnls)
    return round(mu / sigma * ann_factor, 3) if sigma > 0 else 0.0


def max_drawdown(daily_pnls: list[float]) -> float:
    running = peak = 0.0
    max_dd = 0.0
    for v in daily_pnls:
        running += v
        if running > peak:
            peak = running
        dd = peak - running
        if dd > max_dd:
            max_dd = dd
    return round(max_dd, 2)


def get_daily(result) -> dict[str, float]:
    daily: dict[str, float] = {}
    for t in result.trades:
        if t.entry_time_et:
            day = str(t.entry_time_et)[:10]
            daily[day] = daily.get(day, 0) + t.dollar_pnl
    return daily


def window_stats(daily: dict[str, float], start: dt.date, end: dt.date) -> dict:
    window = {k: v for k, v in daily.items() if start.isoformat() <= k <= end.isoformat()}
    pnls = list(window.values())
    n = len(pnls)
    if n == 0:
        return {"n_days": 0, "total_pnl": 0, "pnl_per_day": 0, "win_rate": 0,
                "sharpe": 0, "max_drawdown": 0}
    wins = sum(1 for v in pnls if v > 0)
    return {
        "n_days": n,
        "total_pnl": round(sum(pnls), 2),
        "pnl_per_day": round(sum(pnls) / n, 2),
        "win_rate": round(wins / n, 3),
        "sharpe": sharpe(pnls),
        "max_drawdown": max_drawdown(pnls),
    }


def op16_stats(daily: dict[str, float]) -> dict:
    winner_total = sum(daily.get(d, 0) for d in J_WINNER_DAYS)
    loser_exposure = sum(max(0, -daily.get(d, 0)) for d in J_LOSER_DAYS)
    edge_capture = winner_total - loser_exposure
    return {
        "winner_total": round(winner_total, 2),
        "loser_exposure": round(loser_exposure, 2),
        "edge_capture": round(edge_capture, 2),
        "edge_capture_pct": round(edge_capture / MAX_EDGE * 100, 1),
        "op16_pass": edge_capture >= OP16_FLOOR,
        "j_days": {d: round(daily.get(d, 0), 2) for d in list(J_WINNER_DAYS) + list(J_LOSER_DAYS)},
    }


def main() -> int:
    data_dir = REPO / "data"
    spy_path = data_dir / "spy_5m_2025-01-01_2026-05-15.csv"
    vix_path = data_dir / "vix_5m_2025-01-01_2026-05-15.csv"

    print(f"Loading {spy_path.name}...")
    spy_df = pd.read_csv(spy_path)
    vix_df = pd.read_csv(vix_path)
    print(f"Loaded {len(spy_df):,} SPY rows, {len(vix_df):,} VIX rows")
    print(f"Train: {TRAIN_START} to {TRAIN_END}")
    print(f"Test:  {TEST_START} to {TEST_END}\n")

    all_results = []

    for cfg_label, extra in CONFIGS.items():
        print(f"  Running {cfg_label}...")
        kwargs = {**BASE_KWARGS, **extra}
        # Run full period (train + test together, then split by date)
        result = run_backtest(
            spy_df=spy_df[spy_df["timestamp_et"] <= f"{TEST_END.isoformat()}T23:59:59"].copy(),
            vix_df=vix_df[vix_df["timestamp_et"] <= f"{TEST_END.isoformat()}T23:59:59"].copy(),
            start_date=TRAIN_START,
            end_date=TEST_END,
            **kwargs,
        )
        daily = get_daily(result)
        train = window_stats(daily, TRAIN_START, TRAIN_END)
        test = window_stats(daily, TEST_START, TEST_END)
        op16 = op16_stats(daily)

        # Walk-forward pass/fail criteria
        wf_pass = (
            test["sharpe"] >= 0.5
            and (train["pnl_per_day"] <= 0 or test["pnl_per_day"] >= train["pnl_per_day"] * 0.5)
            and test["win_rate"] >= 0.40
            and (train["max_drawdown"] <= 0 or test["max_drawdown"] <= train["max_drawdown"] * 1.5)
        )

        print(f"  {cfg_label}:")
        print(f"    Train: Sharpe={train['sharpe']:.3f}  WR={train['win_rate']:.1%}  "
              f"P&L/day=${train['pnl_per_day']:.1f}  MaxDD=${train['max_drawdown']:.0f}  N={train['n_days']}")
        print(f"    Test:  Sharpe={test['sharpe']:.3f}  WR={test['win_rate']:.1%}  "
              f"P&L/day=${test['pnl_per_day']:.1f}  MaxDD=${test['max_drawdown']:.0f}  N={test['n_days']}")
        print(f"    OP-16: {op16['edge_capture']:.0f} ({'PASS' if op16['op16_pass'] else 'fail'})  WF: {'PASS' if wf_pass else 'FAIL'}\n")

        all_results.append({
            "label": cfg_label,
            "train": train,
            "test": test,
            "op16": op16,
            "walk_forward_pass": wf_pass,
            "wf_criteria": {
                "test_sharpe_ge_0.5": test["sharpe"] >= 0.5,
                "test_pnl_day_ge_50pct_train": (
                    True if train["pnl_per_day"] <= 0
                    else test["pnl_per_day"] >= train["pnl_per_day"] * 0.5
                ),
                "test_wr_ge_40pct": test["win_rate"] >= 0.40,
                "test_maxdd_le_150pct_train": (
                    True if train["max_drawdown"] <= 0
                    else test["max_drawdown"] <= train["max_drawdown"] * 1.5
                ),
            },
        })

    # Summary
    print("\n=== WALK-FORWARD SUMMARY ===")
    for r in all_results:
        status = "PASS" if r["walk_forward_pass"] else "FAIL"
        op16_status = "PASS" if r["op16"]["op16_pass"] else "fail"
        print(f"  {r['label']:>15}  WF={status}  OP16={op16_status}  "
              f"Test-Sharpe={r['test']['sharpe']:.3f}  Test-WR={r['test']['win_rate']:.1%}")

    f27 = next((r for r in all_results if r["label"] == "F27"), None)
    if f27:
        print(f"\nConfig F27 recommendation: {'RATIFY' if f27['walk_forward_pass'] and f27['op16']['op16_pass'] else 'NEEDS MORE WORK'}")
        if not f27["walk_forward_pass"]:
            failed = [k for k, v in f27["wf_criteria"].items() if not v]
            print(f"  Failed criteria: {failed}")

    out = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "purpose": "Walk-forward validation for Config F27 VIX relaxation",
        "train_period": f"{TRAIN_START} to {TRAIN_END}",
        "test_period": f"{TEST_START} to {TEST_END}",
        "op16_floor": OP16_FLOOR,
        "results": all_results,
    }
    out_path = REPO.parent / "analysis" / "recommendations" / "vix_soft_walk_forward.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
