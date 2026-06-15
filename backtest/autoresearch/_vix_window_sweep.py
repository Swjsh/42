"""VIX rolling average window size sweep for SNIPER VIX-trend filter.

Tests VIX_TREND_WINDOW = 3, 5, 7, 10 days against the same IS/OOS split
to find the optimal window for the VIX-escalating regime filter.

The 5-day window produced WF=0.983 (off=2 primary candidate).
This sweep answers: is 5 days optimal, or could 3d/7d/10d be better?

PROTOCOL:
  IS:  2025-01-01 .. 2025-10-31
  OOS: 2025-11-01 .. 2026-05-22
  Combo: off=2, stp=-0.10, tp1=0.50, run=1.25, lk=0.05/0.08 (recommended candidate)

OUTPUT:
  Console table + autoresearch/_state/vix_window_sweep_results.json

CLI:
  python autoresearch/_vix_window_sweep.py
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

OUT_JSON = REPO / "autoresearch" / "_state" / "vix_window_sweep_results.json"

VIX_LOWER = 18
WINDOWS_TO_TEST = [3, 5, 7, 10, 15]

# Primary candidate: off=2, stp=-0.10, tp1=0.50, run=1.25, lk=0.05/0.08
CANDIDATE_COMBO = {
    "vol_mult": 1.1,
    "body_min_cents": 0.02,
    "min_stars": 2,
    "strike_offset": 2,
    "premium_stop_pct": -0.10,
    "tp1_premium_pct": 0.50,
    "tp1_qty_fraction": 0.5,
    "runner_target_pct": 1.25,
    "profit_lock_threshold_pct": 0.05,
    "profit_lock_stop_offset_pct": 0.08,
    "qty": 10,
    "proximity_dollars": 1.5,
    "require_break_above_open": True,
}


def _build_vix_maps(
    vix_df: pd.DataFrame,
    trade_dates: list[dt.date],
    window: int,
) -> tuple[dict[dt.date, float], dict[dt.date, float]]:
    vix_by_date = (
        vix_df.groupby(vix_df["timestamp_et"].dt.date)["close"]
        .last()
        .to_dict()
    )
    sorted_vix_days = sorted(vix_by_date.keys())
    vix_sorted_vals = [vix_by_date[d] for d in sorted_vix_days]

    prior_close: dict[dt.date, float] = {}
    prior_avg: dict[dt.date, float] = {}

    for trade_date in trade_dates:
        idx = bisect.bisect_left(sorted_vix_days, trade_date) - 1
        if idx < 0:
            prior_close[trade_date] = 15.0
            prior_avg[trade_date] = 15.0
            continue
        prior_close[trade_date] = float(vix_sorted_vals[idx])
        start_idx = max(0, idx - window + 1)
        window_vals = vix_sorted_vals[start_idx : idx + 1]
        prior_avg[trade_date] = float(mean(window_vals)) if window_vals else 15.0

    return prior_close, prior_avg


def _sharpe(pnl_list: list[float]) -> float:
    if len(pnl_list) < 2:
        return 0.0
    m = sum(pnl_list) / len(pnl_list)
    var = sum((v - m) ** 2 for v in pnl_list) / (len(pnl_list) - 1)
    std = math.sqrt(var)
    return (m / std) * math.sqrt(252) if std > 0 else 0.0


def _run_window(
    spy_full: pd.DataFrame,
    prior_close_map: dict[dt.date, float],
    prior_avg_map: dict[dt.date, float],
    trade_dates: list[dt.date],
    combo_dict: dict,
    window_start: dt.date,
    window_end: dt.date,
) -> dict:
    from autoresearch.sniper_evaluator import SniperCombo
    from lib.ribbon import compute_ribbon
    from lib.simulator_real import simulate_trade_real
    from lib.sniper_detector import SniperParams, compute_levels, detect_sniper_break

    combo = SniperCombo(**{k: combo_dict[k] for k in combo_dict if k in SniperCombo.__dataclass_fields__})
    params = SniperParams(
        vol_mult=combo.vol_mult,
        body_min_cents=combo.body_min_cents,
        min_stars=combo.min_stars,
        proximity_dollars=combo.proximity_dollars,
        no_trade_before=dt.time(9, 30),
        no_trade_after=dt.time(15, 50),
        require_break_above_open=combo.require_break_above_open,
    )

    all_trades: list[float] = []
    day_pnl_map: dict[dt.date, float] = {}
    skipped_low = skipped_trend = 0

    for date_et in trade_dates:
        if date_et < window_start or date_et > window_end:
            continue
        vix_prev = prior_close_map.get(date_et, 15.0)
        vix_avg = prior_avg_map.get(date_et, 15.0)
        if vix_prev < VIX_LOWER:
            skipped_low += 1
            continue
        if vix_prev <= vix_avg:
            skipped_trend += 1
            continue

        day_bars = spy_full[
            (spy_full["timestamp_et"].dt.date == date_et)
            & (spy_full["timestamp_et"].dt.time >= dt.time(9, 30))
            & (spy_full["timestamp_et"].dt.time < dt.time(16, 0))
        ].reset_index(drop=True)
        if day_bars.empty:
            continue

        first_ts = day_bars["timestamp_et"].iloc[0]
        levels = compute_levels(spy_full, first_ts, params)
        if not levels:
            day_pnl_map[date_et] = 0.0
            continue

        pre_bars = spy_full[spy_full["timestamp_et"] < first_ts].tail(40).reset_index(drop=True)
        combined = pd.concat([pre_bars, day_bars], ignore_index=True)
        day_offset = len(pre_bars)
        ribbon_df = compute_ribbon(combined["close"]).reset_index(drop=True)

        day_trade_pnl = 0.0
        fired = False
        for i in range(len(day_bars)):
            bar_idx = day_offset + i
            bar = combined.iloc[bar_idx]
            signal = detect_sniper_break(bar, bar_idx, combined, levels, params)
            if signal is None or signal.direction != "short":
                continue
            entry_spot = float(signal.entry_price)
            strike = round(entry_spot) + combo.strike_offset
            fill = simulate_trade_real(
                entry_bar_idx=bar_idx, entry_bar=bar, spy_df=combined, ribbon_df=ribbon_df,
                rejection_level=signal.level.price, triggers_fired=["sniper_level_break"],
                side="P", qty=combo.qty, setup="SNIPER_LEVEL_BREAK",
                levels_active=[L.price for L in levels if L.tier == "Active"],
                levels_carry=[L.price for L in levels if L.tier == "Carry"],
                use_tiered_exits=True, strike_override=int(strike),
                premium_stop_pct=combo.premium_stop_pct,
                profit_lock_threshold_pct=combo.profit_lock_threshold_pct,
                profit_lock_stop_offset_pct=combo.profit_lock_stop_offset_pct,
            )
            if fill is None:
                break
            trade_pnl = float(fill.dollar_pnl or 0.0)
            all_trades.append(trade_pnl)
            day_trade_pnl += trade_pnl
            fired = True
            break

        day_pnl_map[date_et] = day_trade_pnl

    n = len(all_trades)
    total_pnl = round(sum(all_trades), 2)
    wr = round(sum(1 for p in all_trades if p > 0) / n, 3) if n else 0.0
    sharpe = _sharpe(list(day_pnl_map.values()))
    return {
        "n": n, "pnl": total_pnl, "wr": wr, "sharpe": round(sharpe, 3),
        "skipped_low": skipped_low, "skipped_trend": skipped_trend,
    }


def main() -> None:
    from autoresearch import runner as _runner
    import pytz

    print("=" * 70)
    print("VIX ROLLING WINDOW SIZE SWEEP — SNIPER off=2 Primary Candidate")
    print(f"Testing windows: {WINDOWS_TO_TEST} days")
    print(f"IS={IS_START}..{IS_END}  OOS={OOS_START}..{OOS_END}")
    print("=" * 70)

    print("\nLoading SPY + VIX data...", end=" ", flush=True)
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

    results = []
    print(f"\n{'Window':>8}  {'IS_n':>5}  {'IS_pnl':>8}  {'IS_shr':>7}  {'OOS_n':>5}  {'OOS_pnl':>8}  {'OOS_shr':>7}  {'WF_ratio':>9}  {'PASS':>5}")
    print("-" * 80)

    for window in WINDOWS_TO_TEST:
        prior_close_map, prior_avg_map = _build_vix_maps(vix_full, trade_dates, window)
        active_days = sum(
            1 for d in trade_dates
            if prior_close_map.get(d, 0) >= VIX_LOWER
            and prior_close_map.get(d, 0) > prior_avg_map.get(d, 0)
        )
        print(f"  Window={window}d ({active_days} active days)...", end=" ", flush=True)

        is_r = _run_window(spy_full, prior_close_map, prior_avg_map, trade_dates,
                           CANDIDATE_COMBO, IS_START, IS_END)
        oos_r = _run_window(spy_full, prior_close_map, prior_avg_map, trade_dates,
                            CANDIDATE_COMBO, OOS_START, OOS_END)

        wf_ratio = round(oos_r["sharpe"] / is_r["sharpe"], 3) if is_r["sharpe"] != 0 else 0.0
        wf_pass = wf_ratio >= 0.50 and oos_r["pnl"] > 0 and oos_r["wr"] >= 0.45
        print("done")
        print(f"  {window:>7}d  {is_r['n']:>5}  ${is_r['pnl']:>7,.0f}  {is_r['sharpe']:>7.3f}"
              f"  {oos_r['n']:>5}  ${oos_r['pnl']:>7,.0f}  {oos_r['sharpe']:>7.3f}"
              f"  {wf_ratio:>9.3f}  {'PASS' if wf_pass else 'FAIL':>5}")

        results.append({
            "window": window, "active_days": active_days,
            "is": is_r, "oos": oos_r, "wf_ratio": wf_ratio, "wf_pass": wf_pass,
        })

    print()
    print("SUMMARY: WF ratio by window size")
    print(f"  {'Window':>8}  {'WF_ratio':>9}  {'OOS_pnl':>8}  {'OOS_WR':>7}  {'VERDICT':>8}")
    best = max(results, key=lambda r: r["wf_ratio"])
    for r in results:
        marker = " <-- BEST" if r == best else ("  <- original" if r["window"] == 5 else "")
        print(f"  {r['window']:>7}d  {r['wf_ratio']:>9.3f}  ${r['oos']['pnl']:>7,.0f}"
              f"  {r['oos']['wr']:>7.1%}  {'PASS' if r['wf_pass'] else 'FAIL':>8}{marker}")

    print()
    print(f"Recommended window: {best['window']}d (WF={best['wf_ratio']:.3f})")
    if best["window"] != 5:
        print(f"Note: original 5d window WF={next(r for r in results if r['window']==5)['wf_ratio']:.3f}")

    # Save
    payload = {
        "run_at": dt.datetime.now().isoformat(),
        "combo": CANDIDATE_COMBO,
        "vix_lower": VIX_LOWER,
        "windows_tested": WINDOWS_TO_TEST,
        "results": results,
        "best_window": best["window"],
        "best_wf_ratio": best["wf_ratio"],
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nSaved to {OUT_JSON}")


if __name__ == "__main__":
    main()
