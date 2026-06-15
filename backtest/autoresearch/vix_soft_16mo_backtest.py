"""Full 16-month backtest comparing Config B (vix_soft) vs best Config E variant.

Purpose: verify that VIX relaxation configs that pass OP-16 don't create
large regressions on non-J days across the full Jan 2025 - May 2026 dataset.

OP-16 edge_capture on 6 J days is necessary but not sufficient — a config that
adds 100 bad trades/year while fixing 3 winner days may still hurt Sharpe.

Configs tested:
  A: baseline (current production)
  B: vix_soft_mode=True (safe, conservative relaxation)
  E_raw: vix_soft + allow_one_blocker (passes OP-16 at $1,179 but 4/29=-$427)
  F25: vix_soft + allow_one_blocker + min_spread=25c (from minspread sweep)

Metrics per config:
  - Total P&L (train Jan-Mar 2025, test Apr-May 2026)
  - Sharpe ratio
  - Win rate + trade count
  - Max drawdown
  - OP-16 edge_capture on 6 J days
  - Q1/Q2/Q3/Q4 2025 sub-window P&L (stability)
  - Concentration (top-5-days % of total)

Usage: python backtest/autoresearch/vix_soft_16mo_backtest.py [--config B|E_raw|F25|all]
Output: analysis/recommendations/vix_soft_16mo_backtest.json
Cost: $0 (pure Python)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
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
    "E_raw": {"vix_soft_mode": True, "allow_one_blocker": True},
    "F_minspread27": {"vix_soft_mode": True, "allow_one_blocker": True, "allow_one_blocker_min_spread_cents": 27},
    "F_minspread25": {"vix_soft_mode": True, "allow_one_blocker": True, "allow_one_blocker_min_spread_cents": 25},
    "F_minspread20": {"vix_soft_mode": True, "allow_one_blocker": True, "allow_one_blocker_min_spread_cents": 20},
}

# J's source-of-truth days for OP-16 gate
J_WINNER_DAYS = {"2026-04-29": 342, "2026-05-01": 470, "2026-05-04": 730}
J_LOSER_DAYS = {"2026-05-05": -260, "2026-05-06": -300, "2026-05-07": -165}
OP16_FLOOR = 771
MAX_EDGE = 1542

# Quarter boundaries for sub-window stability
QUARTERS = [
    ("Q1-2025", dt.date(2025, 1, 2), dt.date(2025, 3, 31)),
    ("Q2-2025", dt.date(2025, 4, 1), dt.date(2025, 6, 30)),
    ("Q3-2025", dt.date(2025, 7, 1), dt.date(2025, 9, 30)),
    ("Q4-2025", dt.date(2025, 10, 1), dt.date(2025, 12, 31)),
    ("Q1-2026", dt.date(2026, 1, 2), dt.date(2026, 3, 31)),
    ("Q2-2026-partial", dt.date(2026, 4, 1), dt.date(2026, 5, 15)),
]


def sharpe(daily_pnls: list[float], ann_factor: float = 252**0.5) -> float:
    if len(daily_pnls) < 2:
        return 0.0
    import statistics
    mu = sum(daily_pnls) / len(daily_pnls)
    sigma = statistics.stdev(daily_pnls)
    if sigma == 0:
        return 0.0
    return round(mu / sigma * ann_factor, 3)


def run_config(spy_df: pd.DataFrame, vix_df: pd.DataFrame,
               start: dt.date, end: dt.date, extra: dict) -> dict:
    kwargs = {**BASE_KWARGS, **extra}
    result = run_backtest(
        spy_df=spy_df[spy_df["timestamp_et"] <= f"{end.isoformat()}T23:59:59"].copy(),
        vix_df=vix_df[vix_df["timestamp_et"] <= f"{end.isoformat()}T23:59:59"].copy(),
        start_date=start,
        end_date=end,
        **kwargs,
    )
    return result


def analyze_result(result, label: str) -> dict:
    # Group trades by date
    daily: dict[str, float] = {}
    for t in result.trades:
        if t.entry_time_et:
            day = str(t.entry_time_et)[:10]
            daily[day] = daily.get(day, 0) + t.dollar_pnl

    daily_pnls = list(daily.values())
    total_pnl = sum(daily_pnls)
    n_trades = len(result.trades)
    n_days = len(daily)
    wins = sum(1 for v in daily_pnls if v > 0)
    wr = wins / n_days if n_days > 0 else 0
    sh = sharpe(daily_pnls)

    # Max drawdown
    running = 0.0
    peak = 0.0
    max_dd = 0.0
    for v in sorted(daily.keys()):
        running += daily[v]
        if running > peak:
            peak = running
        dd = peak - running
        if dd > max_dd:
            max_dd = dd

    # Concentration: top-5 days
    sorted_pnl = sorted(daily_pnls, reverse=True)
    top5 = sum(sorted_pnl[:5])
    concentration = round(top5 / total_pnl * 100, 1) if total_pnl > 0 else 0

    # OP-16 edge capture
    winner_total = sum(daily.get(d, 0) for d in J_WINNER_DAYS)
    loser_exposure = sum(max(0, -daily.get(d, 0)) for d in J_LOSER_DAYS)
    edge_capture = winner_total - loser_exposure

    return {
        "label": label,
        "total_pnl": round(total_pnl, 2),
        "n_trades": n_trades,
        "n_days_with_trade": n_days,
        "win_rate": round(wr, 3),
        "sharpe_annualized": sh,
        "max_drawdown": round(max_dd, 2),
        "top5_concentration_pct": concentration,
        "edge_capture": round(edge_capture, 2),
        "edge_capture_pct_of_max": round(edge_capture / MAX_EDGE * 100, 1),
        "op16_pass": edge_capture >= OP16_FLOOR,
        "j_days": {d: round(daily.get(d, 0), 2) for d in list(J_WINNER_DAYS) + list(J_LOSER_DAYS)},
        "daily_pnl": {k: round(v, 2) for k, v in sorted(daily.items())},
    }


def add_quarter_breakdown(result_dict: dict, result) -> dict:
    # Group trades by date
    daily: dict[str, float] = {}
    for t in result.trades:
        if t.entry_time_et:
            day = str(t.entry_time_et)[:10]
            daily[day] = daily.get(day, 0) + t.dollar_pnl

    quarters = {}
    for q_label, q_start, q_end in QUARTERS:
        q_pnl = sum(v for k, v in daily.items() if q_start.isoformat() <= k <= q_end.isoformat())
        q_days = [k for k in daily if q_start.isoformat() <= k <= q_end.isoformat()]
        q_wins = sum(1 for k in q_days if daily[k] > 0)
        quarters[q_label] = {
            "pnl": round(q_pnl, 2),
            "n_days": len(q_days),
            "win_rate": round(q_wins / len(q_days), 3) if q_days else 0,
            "positive": q_pnl > 0,
        }

    n_positive_quarters = sum(1 for v in quarters.values() if v["positive"])
    result_dict["quarters"] = quarters
    result_dict["positive_quarters"] = n_positive_quarters
    result_dict["positive_quarters_of_total"] = f"{n_positive_quarters}/{len(QUARTERS)}"
    return result_dict


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="all",
                        help="Config label to run (or 'all'). E.g. B_vix_soft")
    parser.add_argument("--start", default="2025-01-02",
                        help="Start date for backtest (YYYY-MM-DD)")
    parser.add_argument("--end", default="2026-05-15",
                        help="End date for backtest (YYYY-MM-DD)")
    args = parser.parse_args()

    start_date = dt.date.fromisoformat(args.start)
    end_date = dt.date.fromisoformat(args.end)

    configs_to_run = (
        CONFIGS if args.config == "all"
        else {args.config: CONFIGS[args.config]}
    )

    data_dir = REPO / "data"
    spy_path = data_dir / "spy_5m_2025-01-01_2026-05-15.csv"
    vix_path = data_dir / "vix_5m_2025-01-01_2026-05-15.csv"

    print(f"Loading {spy_path.name}...")
    spy_df = pd.read_csv(spy_path)
    vix_df = pd.read_csv(vix_path)
    print(f"Loaded {len(spy_df):,} SPY rows, {len(vix_df):,} VIX rows")
    print(f"Testing {start_date} to {end_date}\n")

    print(f"{'Config':>20}  {'PnL':>8}  {'Trades':>7}  {'WR':>5}  {'Sharpe':>7}  "
          f"{'MaxDD':>8}  {'Q+':>4}  {'EdgeCap':>9}  {'OP16':>5}")
    print("-" * 95)

    all_results = []

    for cfg_label, extra in configs_to_run.items():
        print(f"  Running {cfg_label}...")
        result = run_config(spy_df, vix_df, start_date, end_date, extra)
        stats = analyze_result(result, cfg_label)
        stats = add_quarter_breakdown(stats, result)

        print(f"{cfg_label:>20}  "
              f"{stats['total_pnl']:>8.0f}  "
              f"{stats['n_trades']:>7}  "
              f"{stats['win_rate']:>5.1%}  "
              f"{stats['sharpe_annualized']:>7.3f}  "
              f"{stats['max_drawdown']:>8.0f}  "
              f"{stats['positive_quarters']:>4}  "
              f"{stats['edge_capture']:>9.0f}  "
              f"{'PASS' if stats['op16_pass'] else 'fail':>5}")

        all_results.append(stats)

    # Find best Sharpe among OP-16 passers
    passers = [r for r in all_results if r["op16_pass"]]
    if passers:
        best = max(passers, key=lambda r: r["sharpe_annualized"])
        print(f"\nBest OP-16-passing config: {best['label']} (Sharpe {best['sharpe_annualized']:.3f})")
    else:
        best = max(all_results, key=lambda r: r["sharpe_annualized"])
        print(f"\nNo OP-16 passing config. Best Sharpe: {best['label']} ({best['sharpe_annualized']:.3f})")

    out = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "purpose": "16-month backtest comparing VIX relaxation configs for regression safety",
        "period": f"{start_date} → {end_date}",
        "op16_floor": OP16_FLOOR,
        "j_max_edge": MAX_EDGE,
        "best_label": best["label"],
        "results": all_results,
    }
    out_path = REPO.parent / "analysis" / "recommendations" / "vix_soft_16mo_backtest.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
