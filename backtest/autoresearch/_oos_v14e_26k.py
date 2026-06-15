"""OOS walk-forward validation for v14_enhanced $26k best combo.

Splits wide window into IS (training) and OOS (holdout):
  IS:  2025-01-01 .. 2025-09-30  (~9 months)
  OOS: 2025-10-01 .. 2026-05-22  (~8 months)

Acceptance gate: OOS Sharpe / IS Sharpe >= 0.50 (consistent with existing WF methodology).
Secondary: OOS wide_pnl > 0, OOS +quarters >= IS +quarters / 2.

Also runs monthly breakdown to verify Q4-2025 ($8,244 quarter) isn't a single month.
"""
import datetime as dt
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from autoresearch import runner as _runner

params_path = REPO.parent / "automation" / "state" / "params.json"

BEST_COMBO = {
    "strike_offset_bear": 0,
    "min_triggers_bear": 1,
    "premium_stop_pct_bear": -0.2,
    "tp1_qty_fraction": 0.5,
    "no_trade_before": "09:35",
    "profit_lock_threshold_pct": 0.05,
    "profit_lock_stop_offset_pct": 0.1,
    "tp1_premium_pct": 0.3,
    "runner_target_premium_pct": 2.5,
}

IS_START = dt.date(2025, 1, 1)
IS_END = dt.date(2025, 9, 30)
OOS_START = dt.date(2025, 10, 1)
OOS_END = dt.date(2026, 5, 22)
FULL_START = IS_START
FULL_END = OOS_END


def _sharpe(trades):
    """Daily Sharpe (annualized) from trade list."""
    import math
    day_pnl = defaultdict(float)
    for t in trades:
        day_pnl[t.entry_time_et.date()] += t.dollar_pnl
    vals = list(day_pnl.values())
    if len(vals) < 2:
        return 0.0
    mean = sum(vals) / len(vals)
    std = (sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)) ** 0.5
    if std == 0:
        return 0.0
    return (mean / std) * math.sqrt(252)


def _stats(res, m, start_label):
    trades = res.trades
    day_pnl = defaultdict(float)
    quarter_pnl = defaultdict(float)
    month_pnl = defaultdict(float)
    for t in trades:
        d = t.entry_time_et.date()
        day_pnl[d] += t.dollar_pnl
        q = f"{d.year}-Q{(d.month - 1) // 3 + 1}"
        quarter_pnl[q] += t.dollar_pnl
        mo = f"{d.year}-{d.month:02d}"
        month_pnl[mo] += t.dollar_pnl
    sharpe = _sharpe(trades)
    pos_q = sum(1 for v in quarter_pnl.values() if v > 0)
    total_q = len(quarter_pnl)
    sorted_day_pnls = sorted(day_pnl.values(), reverse=True)
    top5 = sum(sorted_day_pnls[:5])
    top5_pct = round(top5 / m.total_pnl, 3) if m.total_pnl > 0 else 999.0
    return {
        "window": start_label,
        "n_trades": m.n_trades,
        "total_pnl": round(m.total_pnl, 2),
        "wr": round(m.n_winners / m.n_trades, 3) if m.n_trades else 0,
        "sharpe": round(sharpe, 3),
        "pos_q": pos_q,
        "total_q": total_q,
        "top5_pct": top5_pct,
        "quarter_pnl": {k: round(v, 2) for k, v in sorted(quarter_pnl.items())},
        "month_pnl": {k: round(v, 2) for k, v in sorted(month_pnl.items())},
    }


def main():
    params = json.loads(params_path.read_text(encoding="utf-8-sig"))
    params.update(BEST_COMBO)

    print("=" * 70)
    print("OOS Walk-Forward Validation — v14e $26K Combo")
    print(f"Combo: {BEST_COMBO}")
    print("=" * 70)
    print()

    # Load all data at once (covers full window)
    print("Loading data...", end=" ", flush=True)
    t0 = time.perf_counter()
    spy_all, vix_all = _runner.load_data(FULL_START, FULL_END)
    print(f"{time.perf_counter() - t0:.1f}s")
    print()

    windows = [
        ("FULL", FULL_START, FULL_END),
        ("IS  ", IS_START, IS_END),
        ("OOS ", OOS_START, OOS_END),
    ]

    results = {}
    for label, start, end in windows:
        t0 = time.perf_counter()
        res, m = _runner.run_with_params(params, start, end, spy_all, vix_all)
        elapsed = time.perf_counter() - t0
        stats = _stats(res, m, label)
        results[label.strip()] = stats
        print(f"[{label}] {start}..{end}  n={stats['n_trades']}  pnl=${stats['total_pnl']:,.0f}  "
              f"wr={stats['wr']:.1%}  sharpe={stats['sharpe']:.2f}  "
              f"+q={stats['pos_q']}/{stats['total_q']}  top5={stats['top5_pct']:.1%}  ({elapsed:.1f}s)")
        print()

    # Walk-forward gate check
    is_sharpe = results.get("IS", {}).get("sharpe", 0)
    oos_sharpe = results.get("OOS", {}).get("sharpe", 0)
    ratio = oos_sharpe / is_sharpe if is_sharpe != 0 else 0

    print("=" * 70)
    print("WALK-FORWARD GATE (>=0.50)")
    print(f"  IS Sharpe:  {is_sharpe:.3f}")
    print(f"  OOS Sharpe: {oos_sharpe:.3f}")
    print(f"  Ratio:      {ratio:.3f}  ->  {'PASS' if ratio >= 0.50 else 'FAIL'}")
    print()

    # Q4-2025 monthly breakdown (check if single month drives it)
    oos_months = results.get("OOS", {}).get("month_pnl", {})
    is_months = results.get("IS", {}).get("month_pnl", {})

    print("Monthly P&L breakdown:")
    all_months = {**is_months, **oos_months}
    for mo, pnl in sorted(all_months.items()):
        tag = " [IS]" if mo <= "2025-09" else " [OOS]"
        bar = "#" * int(abs(pnl) / 200) if abs(pnl) < 4000 else "#" * 20 + "+"
        sign = "+" if pnl >= 0 else ""
        print(f"  {mo}{tag}  {sign}${pnl:,.0f}  {bar}")
    print()

    # Save results
    out = REPO / "autoresearch" / "_state" / "v14e_oos_validation.json"
    out.write_text(json.dumps({
        "run_at": dt.datetime.now().isoformat(),
        "combo": BEST_COMBO,
        "results": results,
        "wf_ratio": round(ratio, 3),
        "wf_pass": ratio >= 0.50,
    }, indent=2), encoding="utf-8")
    print(f"Results saved to {out}")


if __name__ == "__main__":
    main()
