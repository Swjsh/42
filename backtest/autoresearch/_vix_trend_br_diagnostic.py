"""VIX-trend regime diagnostic for BEARISH_REJECTION_RIDE_THE_RIBBON.

Mirrors _sniper_vix_trend_filter.py but for the V14E production combo.
Tests whether the same VIX CHARACTER (escalating vs spike-and-revert)
discriminator that fixed SNIPER OOS also improves BEARISH_REJECTION WR.

HYPOTHESIS: If VIX is escalating (VIX > 5d_avg) on BEARISH_REJECTION entry
days, WR should be higher than on VIX-declining days, for the same reason as
SNIPER: escalating VIX → genuine directional conviction → level breaks hold.

PRIMARY COMBO (V14E_PARAM_SWEEP best):
  stop=-0.20, tp1=0.30, runner=2.5x, profit_lock=0.05/0.10, no_trade_before=09:35

WHAT THIS PRODUCES:
  1. Trade-by-trade VIX regime tags (ESCALATING / DECLINING / LOW-VIX)
  2. P&L / WR split by regime
  3. IS/OOS comparison with and without VIX-trend filter
  4. Actionable verdict: does adding VIX-trend filter improve OOS WR?

OUTPUT:
  Console table + autoresearch/_state/vix_trend_br_diagnostic.json

CLI:
  python autoresearch/_vix_trend_br_diagnostic.py
"""

from __future__ import annotations

import bisect
import datetime as dt
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

WIDE_START = dt.date(2025, 1, 1)
WIDE_END = dt.date(2026, 5, 22)
IS_START = dt.date(2025, 1, 1)
IS_END = dt.date(2025, 10, 31)
OOS_START = dt.date(2025, 11, 1)
OOS_END = dt.date(2026, 5, 22)

OUT_JSON = REPO / "autoresearch" / "_state" / "vix_trend_br_diagnostic.json"

VIX_LOWER = 17.30  # Production VIX_BEAR_THRESHOLD
VIX_TREND_WINDOW = 5

# V14E best combo (RATIFICATION_READY per leaderboard #12)
V14E_BEST = {
    "strike_offset_bear": 0,
    "min_triggers_bear": 1,
    "premium_stop_pct_bear": -0.20,
    "tp1_qty_fraction": 0.5,
    "no_trade_before": "09:35",
    "profit_lock_threshold_pct": 0.05,
    "profit_lock_stop_offset_pct": 0.10,
    "tp1_premium_pct": 0.30,
    "runner_target_premium_pct": 2.5,
}


def _build_vix_maps(
    vix_df: pd.DataFrame, trade_dates: list[dt.date]
) -> tuple[dict[dt.date, float], dict[dt.date, float]]:
    """Return (prior_close_map, prior_5d_avg_map) per trade date."""
    vix_by_date = (
        vix_df.groupby(vix_df["timestamp_et"].dt.date)["close"]
        .last()
        .to_dict()
    )
    sorted_vix_days = sorted(vix_by_date.keys())
    vix_sorted_vals = [vix_by_date[d] for d in sorted_vix_days]

    prior_close: dict[dt.date, float] = {}
    prior_5d_avg: dict[dt.date, float] = {}

    for trade_date in trade_dates:
        idx = bisect.bisect_left(sorted_vix_days, trade_date) - 1
        if idx < 0:
            prior_close[trade_date] = 15.0
            prior_5d_avg[trade_date] = 15.0
            continue
        prior_close[trade_date] = float(vix_sorted_vals[idx])
        start_idx = max(0, idx - VIX_TREND_WINDOW + 1)
        window_vals = vix_sorted_vals[start_idx : idx + 1]
        prior_5d_avg[trade_date] = float(mean(window_vals)) if window_vals else 15.0

    return prior_close, prior_5d_avg


def _sharpe(day_pnl_list: list[float]) -> float:
    if len(day_pnl_list) < 2:
        return 0.0
    m = sum(day_pnl_list) / len(day_pnl_list)
    var = sum((v - m) ** 2 for v in day_pnl_list) / (len(day_pnl_list) - 1)
    std = math.sqrt(var)
    return (m / std) * math.sqrt(252) if std > 0 else 0.0


def main() -> None:
    from autoresearch import runner as _runner
    import pytz

    print("=" * 70)
    print("BEARISH_REJECTION V14E — VIX-TREND Regime Diagnostic")
    print(f"Filter tested: VIX>{VIX_LOWER} (existing) AND VIX > prior_{VIX_TREND_WINDOW}d_avg (new)")
    print(f"Window: {WIDE_START} .. {WIDE_END}")
    print("=" * 70)

    print("\nLoading data...", end=" ", flush=True)
    spy_full, vix_full = _runner.load_data(WIDE_START, WIDE_END)
    tz_et = pytz.timezone("US/Eastern")
    for df in (spy_full, vix_full):
        df["timestamp_et"] = (
            pd.to_datetime(df["timestamp_et"], utc=True)
            .dt.tz_convert(tz_et)
            .dt.tz_localize(None)
        )
    print("done")

    all_dates = sorted(set(spy_full["timestamp_et"].dt.date.unique()))
    trade_dates = [d for d in all_dates if WIDE_START <= d <= WIDE_END]
    prior_close_map, prior_5d_avg_map = _build_vix_maps(vix_full, trade_dates)
    print(f"Trade dates: {len(trade_dates)}")

    print("\nRunning V14E best combo (full window)...", end=" ", flush=True)
    result, metrics = _runner.run_with_params(V14E_BEST, WIDE_START, WIDE_END, spy_full, vix_full)
    trades = result.trades
    print(f"done  n={len(trades)}  pnl=${sum(t.dollar_pnl for t in trades):,.0f}  "
          f"wr={sum(1 for t in trades if t.dollar_pnl > 0)/len(trades):.1%}")

    # ── Tag each trade by VIX regime ──
    by_regime: dict[str, list[float]] = {"ESCALATING": [], "DECLINING": [], "LOW_VIX": []}
    for t in trades:
        entry_date = t.entry_time_et.date() if hasattr(t.entry_time_et, 'date') else t.entry_time_et
        if isinstance(entry_date, str):
            entry_date = dt.date.fromisoformat(entry_date[:10])
        vix_prev = prior_close_map.get(entry_date, 15.0)
        vix_5d = prior_5d_avg_map.get(entry_date, 15.0)
        if vix_prev < VIX_LOWER:
            regime = "LOW_VIX"
        elif vix_prev > vix_5d:
            regime = "ESCALATING"
        else:
            regime = "DECLINING"
        by_regime[regime].append(t.dollar_pnl)

    # ── Regime stats ──
    print("\n" + "=" * 70)
    print("REGIME STRATIFICATION (full window)")
    print("=" * 70)
    print(f"  {'Regime':<15} {'n':>5}  {'P&L':>9}  {'WR':>7}  {'avg/trade':>10}")
    print("  " + "-" * 50)
    for regime in ["ESCALATING", "DECLINING", "LOW_VIX"]:
        pnls = by_regime[regime]
        if not pnls:
            continue
        wr = sum(1 for p in pnls if p > 0) / len(pnls)
        total = sum(pnls)
        avg = total / len(pnls)
        print(f"  {regime:<15} {len(pnls):>5}  ${total:>8,.0f}  {wr:>7.1%}  ${avg:>9,.0f}")

    # ── Counterfactual: P&L if we only trade ESCALATING days ──
    esc = by_regime["ESCALATING"]
    dec = by_regime["DECLINING"]
    print(f"\n  If VIX-trend filter applied (only ESCALATING trades):")
    if esc:
        esc_pnl = sum(esc)
        esc_wr = sum(1 for p in esc if p > 0) / len(esc)
        print(f"    n={len(esc)}, P&L=${esc_pnl:,.0f}, WR={esc_wr:.1%}")
        print(f"    P&L change: ${esc_pnl - sum(esc+dec):+,.0f} vs all VIX>{VIX_LOWER} trades")
        print(f"    WR change: {esc_wr - sum(1 for p in esc+dec if p>0)/len(esc+dec):+.1%}")

    # ── IS/OOS split ──
    trades_is = [t for t in trades if (
        t.entry_time_et.date() if hasattr(t.entry_time_et, 'date') else dt.date.fromisoformat(str(t.entry_time_et)[:10])
    ) <= IS_END]
    trades_oos = [t for t in trades if (
        t.entry_time_et.date() if hasattr(t.entry_time_et, 'date') else dt.date.fromisoformat(str(t.entry_time_et)[:10])
    ) >= OOS_START]

    def _regime(t):
        d = t.entry_time_et.date() if hasattr(t.entry_time_et, 'date') else dt.date.fromisoformat(str(t.entry_time_et)[:10])
        vix_prev = prior_close_map.get(d, 15.0)
        vix_5d = prior_5d_avg_map.get(d, 15.0)
        if vix_prev < VIX_LOWER:
            return "LOW_VIX"
        return "ESCALATING" if vix_prev > vix_5d else "DECLINING"

    print("\n" + "=" * 70)
    print("IS/OOS SPLIT — with and without VIX-trend filter")
    print("=" * 70)

    for window_label, window_trades in [("IS (2025-01..2025-10)", trades_is), ("OOS (2025-11..2026-05)", trades_oos)]:
        all_pnls = [t.dollar_pnl for t in window_trades]
        esc_pnls = [t.dollar_pnl for t in window_trades if _regime(t) == "ESCALATING"]
        dec_pnls = [t.dollar_pnl for t in window_trades if _regime(t) == "DECLINING"]

        def _fmt(pnls, label):
            if not pnls:
                return f"  {label}: n=0 (no trades)"
            wr = sum(1 for p in pnls if p > 0) / len(pnls)
            return (f"  {label}: n={len(pnls)}, P&L=${sum(pnls):,.0f}, "
                    f"WR={wr:.1%}, Sharpe={_sharpe(pnls):.2f}")

        print(f"\n{window_label}:")
        print(_fmt(all_pnls, "All VIX trades"))
        print(_fmt(esc_pnls, "VIX-escalating  "))
        print(_fmt(dec_pnls, "VIX-declining   "))

    # ── Verdict ──
    esc = by_regime["ESCALATING"]
    dec = by_regime["DECLINING"]
    if esc and dec:
        esc_wr = sum(1 for p in esc if p > 0) / len(esc)
        dec_wr = sum(1 for p in dec if p > 0) / len(dec)
        combined_wr = sum(1 for p in esc+dec if p > 0) / len(esc+dec)
        wr_improvement = esc_wr - combined_wr
        print("\n" + "=" * 70)
        print("VERDICT")
        print("=" * 70)
        if wr_improvement >= 0.05:
            print(f"  MATERIAL IMPROVEMENT: VIX-trend filter raises WR {combined_wr:.1%} -> {esc_wr:.1%} (+{wr_improvement:.1%})")
            print("  ACTION: Build VIX-trend BR grinder (same as sniper_vix_trend_grinder but for V14E)")
        elif wr_improvement >= 0.02:
            print(f"  MARGINAL: WR {combined_wr:.1%} -> {esc_wr:.1%} (+{wr_improvement:.1%})")
            print("  ACTION: Investigate further -- not conclusive but worth testing in grinder")
        else:
            print(f"  MINIMAL: WR {combined_wr:.1%} -> {esc_wr:.1%} (+{wr_improvement:.1%})")
            print("  ACTION: VIX character is NOT a meaningful discriminator for BEARISH_REJECTION")
            print("  REASON: Unlike SNIPER, BEARISH_REJECTION relies on ribbon trigger quality, not VIX level")

    # ── Save ──
    result_payload = {
        "run_at": dt.datetime.now().isoformat(),
        "combo": V14E_BEST,
        "vix_lower": VIX_LOWER,
        "vix_trend_window": VIX_TREND_WINDOW,
        "full_window_n": len(trades),
        "full_window_pnl": round(sum(t.dollar_pnl for t in trades), 2),
        "full_window_wr": round(sum(1 for t in trades if t.dollar_pnl > 0)/len(trades), 3) if trades else 0,
        "by_regime": {
            regime: {
                "n": len(pnls),
                "pnl": round(sum(pnls), 2),
                "wr": round(sum(1 for p in pnls if p > 0)/len(pnls), 3) if pnls else 0,
                "sharpe": round(_sharpe(pnls), 3),
            }
            for regime, pnls in by_regime.items() if pnls
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result_payload, indent=2), encoding="utf-8")
    print(f"\nResults saved to {OUT_JSON}")


if __name__ == "__main__":
    main()
