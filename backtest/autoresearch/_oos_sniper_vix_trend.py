"""OOS walk-forward validation for the SNIPER VIX-trend grinder best combo.

FILTER:  VIX>=18 AND prior_day_VIX > prior_5d_avg_VIX (escalating regime)
PURPOSE: Verify whether the best VIX-trend combo clears the WF gate that
         the VIX18 baseline failed (WF ratio=-0.224) and the single-combo
         diagnostic only partially cleared (0.353, IS-concentration effect).

PROTOCOL:
  IS:  2025-01-01 .. 2025-10-31  (10 months — optimizer window)
  OOS: 2025-11-01 .. 2026-05-22  (6.5 months — true holdout)

  PRIMARY GATE:   OOS_Sharpe / IS_Sharpe >= 0.50 (WF_ratio)
  SECONDARY:      OOS P&L > 0, OOS WR >= 45%

FOLD BREAKDOWN:
  F1: 2025-11 .. 2025-12  (spike-and-revert era, problem zone for VIX18)
  F2: 2026-01 .. 2026-02  (spike-and-revert era)
  F3: 2026-03 .. 2026-04  (tariff crash — trending high-VIX, should work)
  F4: 2026-05+            (current)

CLI:
  # auto-select best combo from grinder results:
  python autoresearch/_oos_sniper_vix_trend.py

  # test a specific combo (uses grinder default params except these overrides):
  python autoresearch/_oos_sniper_vix_trend.py --off 2 --stp -0.10 --tp1 0.5 --run 1.25 --lk 0.05 --lk-offset 0.08

  # compare top-N ratification candidates from grinder:
  python autoresearch/_oos_sniper_vix_trend.py --top-n 3

OUTPUT:
  Console table + autoresearch/_state/sniper_vix_trend_oos_results.json
"""

from __future__ import annotations

import argparse
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

GRINDER_DIR = REPO / "autoresearch" / "_state" / "sniper_vix_trend_stage1"
OUT_JSON = REPO / "autoresearch" / "_state" / "sniper_vix_trend_oos_results.json"

VIX_LOWER = 18
VIX_TREND_WINDOW = 5

# Fixed params shared by all grinder combos
FIXED_PARAMS = {
    "vol_mult": 1.1,
    "body_min_cents": 0.02,
    "min_stars": 2,
    "tp1_qty_fraction": 0.5,
    "qty": 10,
    "proximity_dollars": 1.5,
    "require_break_above_open": True,
}

OOS_FOLDS = [
    ("F1 (Nov-Dec 2025)",  dt.date(2025, 11, 1),  dt.date(2025, 12, 31)),
    ("F2 (Jan-Feb 2026)",  dt.date(2026, 1, 1),   dt.date(2026, 2, 28)),
    ("F3 (Mar-Apr 2026)",  dt.date(2026, 3, 1),   dt.date(2026, 4, 30)),
    ("F4 (May 2026)",      dt.date(2026, 5, 1),   dt.date(2026, 5, 22)),
]


def _load_grinder_results() -> list[dict]:
    """Load and deduplicate results from the VIX-trend grinder."""
    results_file = GRINDER_DIR / "results.jsonl"
    if not results_file.exists():
        return []
    rows = []
    seen: set[str] = set()
    for line in results_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
            key = json.dumps(r.get("combo", {}), sort_keys=True)
            if key not in seen:
                seen.add(key)
                rows.append(r)
        except json.JSONDecodeError:
            pass
    return rows


def _build_vix_maps(
    vix_df: pd.DataFrame, trade_dates: list[dt.date]
) -> tuple[dict[dt.date, float], dict[dt.date, float]]:
    """Return (prior_close_map, prior_5d_avg_map) for each trade date."""
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


def _sharpe(day_pnl_map: dict[dt.date, float]) -> float:
    """Daily Sharpe annualized with sqrt(252). Includes zero-P&L VIX-skipped days."""
    vals = list(day_pnl_map.values())
    if len(vals) < 2:
        return 0.0
    m = sum(vals) / len(vals)
    variance = sum((v - m) ** 2 for v in vals) / (len(vals) - 1)
    std = math.sqrt(variance)
    return (m / std) * math.sqrt(252) if std > 0 else 0.0


def _run_window(
    spy_full: pd.DataFrame,
    prior_close_map: dict[dt.date, float],
    prior_5d_avg_map: dict[dt.date, float],
    trade_dates: list[dt.date],
    combo_dict: dict,
    window_start: dt.date,
    window_end: dt.date,
    label: str,
) -> dict:
    """Run SNIPER with joint VIX filter (>=18 AND > 5d_avg) on a date sub-window."""
    from autoresearch.sniper_evaluator import SniperCombo
    from lib.ribbon import compute_ribbon
    from lib.simulator_real import simulate_trade_real
    from lib.sniper_detector import SniperParams, compute_levels, detect_sniper_break

    combo = SniperCombo(**{
        k: combo_dict[k] for k in combo_dict
        if k in SniperCombo.__dataclass_fields__
    })
    params = SniperParams(
        vol_mult=combo.vol_mult,
        body_min_cents=combo.body_min_cents,
        min_stars=combo.min_stars,
        proximity_dollars=combo.proximity_dollars,
        no_trade_before=dt.time(9, 30),
        no_trade_after=dt.time(15, 50),
        require_break_above_open=combo.require_break_above_open,
    )

    all_trades: list[dict] = []
    day_pnl_map: dict[dt.date, float] = {}
    quarter_pnl_map: dict[str, float] = defaultdict(float)
    skipped_low = skipped_trend = 0

    for date_et in trade_dates:
        if date_et < window_start or date_et > window_end:
            continue

        vix_prev = prior_close_map.get(date_et, 15.0)
        vix_5d = prior_5d_avg_map.get(date_et, 15.0)

        if vix_prev < VIX_LOWER:
            skipped_low += 1
            continue
        if vix_prev <= vix_5d:
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
            if signal is None:
                continue
            if signal.direction != "short":
                continue

            entry_spot = float(signal.entry_price)
            strike = round(entry_spot) + combo.strike_offset

            fill = simulate_trade_real(
                entry_bar_idx=bar_idx,
                entry_bar=bar,
                spy_df=combined,
                ribbon_df=ribbon_df,
                rejection_level=signal.level.price,
                triggers_fired=["sniper_level_break"],
                side="P",
                qty=combo.qty,
                setup="SNIPER_LEVEL_BREAK",
                levels_active=[L.price for L in levels if L.tier == "Active"],
                levels_carry=[L.price for L in levels if L.tier == "Carry"],
                use_tiered_exits=True,
                strike_override=int(strike),
                premium_stop_pct=combo.premium_stop_pct,
                profit_lock_threshold_pct=combo.profit_lock_threshold_pct,
                profit_lock_stop_offset_pct=combo.profit_lock_stop_offset_pct,
            )
            if fill is None:
                break

            trade_pnl = float(fill.dollar_pnl or 0.0)
            all_trades.append({
                "date": date_et.isoformat(),
                "dollar_pnl": trade_pnl,
                "vix_prev": round(vix_prev, 2),
                "vix_5d_avg": round(vix_5d, 2),
            })
            day_trade_pnl += trade_pnl
            fired = True
            break  # one trade per day

        day_pnl_map[date_et] = day_trade_pnl
        if fired:
            q = f"{date_et.year}-Q{(date_et.month - 1) // 3 + 1}"
            quarter_pnl_map[q] += day_trade_pnl

    wide_pnl = round(sum(t["dollar_pnl"] for t in all_trades), 2)
    wide_n = len(all_trades)
    wide_winners = sum(1 for t in all_trades if t["dollar_pnl"] > 0)
    wide_wr = round(wide_winners / wide_n, 3) if wide_n else 0.0
    positive_quarters = sum(1 for v in quarter_pnl_map.values() if v > 0)
    sharpe = _sharpe(day_pnl_map)

    cum = peak = max_dd = 0.0
    for d in sorted(day_pnl_map.keys()):
        cum += day_pnl_map[d]
        if cum > peak:
            peak = cum
        dd = peak - cum
        if dd > max_dd:
            max_dd = dd

    sorted_day_pnls = sorted(day_pnl_map.values(), reverse=True)
    top5_sum = sum(sorted_day_pnls[:5])
    top5_pct = round(top5_sum / wide_pnl, 2) if wide_pnl > 0 else 0.0

    return {
        "label": label,
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "wide_pnl": wide_pnl,
        "wide_n_trades": wide_n,
        "wide_wr": wide_wr,
        "sharpe": round(sharpe, 3),
        "positive_quarters": positive_quarters,
        "quarter_count": len(quarter_pnl_map),
        "max_drawdown": round(max_dd, 2),
        "top5_pct": top5_pct,
        "skipped_low": skipped_low,
        "skipped_trend": skipped_trend,
        "quarter_pnl": {k: round(v, 2) for k, v in sorted(quarter_pnl_map.items())},
        "trades": all_trades,
    }


def _wf_check(is_res: dict, oos_res: dict) -> dict:
    is_sharpe = is_res["sharpe"]
    oos_sharpe = oos_res["sharpe"]
    wf_ratio = round(oos_sharpe / is_sharpe, 3) if is_sharpe != 0 else 0.0
    return {
        "wf_ratio": wf_ratio,
        "wf_pass": wf_ratio >= 0.50,
        "pnl_pass": oos_res["wide_pnl"] > 0,
        "wr_pass": oos_res["wide_wr"] >= 0.45,
        "overall_pass": wf_ratio >= 0.50 and oos_res["wide_pnl"] > 0 and oos_res["wide_wr"] >= 0.45,
    }


def _print_window(label: str, res: dict) -> None:
    print(f"\n{label}:")
    print(f"  n={res['wide_n_trades']}  pnl=${res['wide_pnl']:,.0f}  "
          f"wr={res['wide_wr']:.1%}  sharpe={res['sharpe']:.3f}  "
          f"+q={res['positive_quarters']}/{res['quarter_count']}  "
          f"dd=${res['max_drawdown']:,.0f}  top5%={res['top5_pct']:.2f}x  "
          f"skipped_low={res['skipped_low']}  skipped_trend={res['skipped_trend']}")
    for q, v in sorted(res["quarter_pnl"].items()):
        print(f"    {q}: {'+' if v >= 0 else ''}${v:,.0f}  [{'PASS' if v >= 0 else 'FAIL'}]")


def _run_combo(
    combo_dict: dict,
    spy_full: pd.DataFrame,
    prior_close_map: dict,
    prior_5d_avg_map: dict,
    trade_dates: list,
    label_prefix: str,
    run_folds: bool = True,
) -> dict:
    """Run IS + OOS + optional fold breakdown for one combo. Returns full result dict."""
    print(f"\n{'='*70}")
    c = combo_dict
    print(f"COMBO: off={c.get('strike_offset')} stp={c.get('premium_stop_pct')} "
          f"tp1={c.get('tp1_premium_pct')} run={c.get('runner_target_pct')} "
          f"lk={c.get('profit_lock_threshold_pct')}/{c.get('profit_lock_stop_offset_pct')}")
    print(f"{'='*70}")

    print("  Running IS...", end=" ", flush=True)
    is_res = _run_window(spy_full, prior_close_map, prior_5d_avg_map,
                         trade_dates, combo_dict, IS_START, IS_END, "IS")
    print(f"n={is_res['wide_n_trades']} pnl=${is_res['wide_pnl']:,.0f} "
          f"wr={is_res['wide_wr']:.1%} sharpe={is_res['sharpe']:.3f}")

    print("  Running OOS...", end=" ", flush=True)
    oos_res = _run_window(spy_full, prior_close_map, prior_5d_avg_map,
                          trade_dates, combo_dict, OOS_START, OOS_END, "OOS")
    print(f"n={oos_res['wide_n_trades']} pnl=${oos_res['wide_pnl']:,.0f} "
          f"wr={oos_res['wide_wr']:.1%} sharpe={oos_res['sharpe']:.3f}")

    gates = _wf_check(is_res, oos_res)
    wf_label = "PASS" if gates["overall_pass"] else "FAIL"
    print(f"\n  WF ratio: {gates['wf_ratio']:.3f} -> {wf_label}  "
          f"(OOS P&L: {'PASS' if gates['pnl_pass'] else 'FAIL'}  "
          f"OOS WR: {'PASS' if gates['wr_pass'] else 'FAIL'})")

    _print_window("IS detail", is_res)
    _print_window("OOS detail", oos_res)

    fold_results = []
    if run_folds:
        print("\n  OOS Fold Breakdown:")
        print(f"  {'Fold':<22} {'n':>4}  {'pnl':>9}  {'wr':>6}  {'sharpe':>8}  {'skip_low':>9}  {'skip_trend':>11}")
        print("  " + "-" * 74)
        for fold_label, fold_start, fold_end in OOS_FOLDS:
            fr = _run_window(spy_full, prior_close_map, prior_5d_avg_map,
                             trade_dates, combo_dict, fold_start, fold_end, fold_label)
            fold_results.append(fr)
            print(f"  {fold_label:<22} {fr['wide_n_trades']:>4}  "
                  f"${fr['wide_pnl']:>8,.0f}  {fr['wide_wr']:>6.1%}  "
                  f"{fr['sharpe']:>8.3f}  {fr['skipped_low']:>9}  {fr['skipped_trend']:>11}")

    return {
        "combo": combo_dict,
        "is_result": is_res,
        "oos_result": oos_res,
        "fold_results": fold_results,
        **gates,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="OOS walk-forward for SNIPER VIX-trend best combo")
    parser.add_argument("--off", type=int, default=None, help="strike_offset override")
    parser.add_argument("--stp", type=float, default=None, help="premium_stop_pct override")
    parser.add_argument("--tp1", type=float, default=None, help="tp1_premium_pct override")
    parser.add_argument("--run", type=float, default=None, help="runner_target_pct override")
    parser.add_argument("--lk", type=float, default=None, help="profit_lock_threshold_pct override")
    parser.add_argument("--lk-offset", type=float, default=None, help="profit_lock_stop_offset_pct override")
    parser.add_argument("--top-n", type=int, default=1,
                        help="Number of top-ranked grinder combos to test (default: 1=best)")
    parser.add_argument("--no-folds", action="store_true", help="Skip fold breakdown (faster)")
    args = parser.parse_args()

    print("=" * 70)
    print("SNIPER VIX-TREND OOS Walk-Forward Validation")
    print(f"Filter: VIX>={VIX_LOWER} AND VIX > prior_{VIX_TREND_WINDOW}d_avg")
    print(f"IS:  {IS_START} .. {IS_END}")
    print(f"OOS: {OOS_START} .. {OOS_END}")
    print("Gate: WF_ratio (OOS_Sharpe/IS_Sharpe) >= 0.50 AND OOS_pnl>0 AND OOS_WR>=45%")
    print("=" * 70)

    # ── Load data ──
    from autoresearch import runner as _runner
    import pytz

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
    prior_close_map, prior_5d_avg_map = _build_vix_maps(vix_full, trade_dates)
    print(f"Trade dates: {len(trade_dates)} | VIX-escalating days (>= {VIX_LOWER} AND > 5d_avg): "
          f"{sum(1 for d in trade_dates if prior_close_map.get(d,0) >= VIX_LOWER and prior_close_map.get(d,0) > prior_5d_avg_map.get(d,0))}")

    # ── Determine combos to test ──
    combos_to_test: list[tuple[str, dict]] = []

    if any(v is not None for v in [args.off, args.stp, args.tp1, args.run, args.lk, args.lk_offset]):
        # Manual override mode
        manual_combo = {
            **FIXED_PARAMS,
            "strike_offset": args.off if args.off is not None else 1,
            "premium_stop_pct": args.stp if args.stp is not None else -0.10,
            "tp1_premium_pct": args.tp1 if args.tp1 is not None else 0.30,
            "runner_target_pct": args.run if args.run is not None else 2.0,
            "profit_lock_threshold_pct": args.lk if args.lk is not None else 0.05,
            "profit_lock_stop_offset_pct": args.lk_offset if args.lk_offset is not None else 0.08,
        }
        combos_to_test.append(("manual", manual_combo))
    else:
        # Auto-select from grinder results
        results = _load_grinder_results()
        if not results:
            print("\nERROR: No grinder results found in sniper_vix_trend_stage1/results.jsonl")
            print("Run sniper_vix_trend_grinder.py first.")
            return 1

        # Filter to ratification candidates, sort by pnl
        ratif = [r for r in results if r.get("is_ratification_candidate")]
        if not ratif:
            print(f"\nNo ratification candidates yet ({len(results)} results total). "
                  "Grinder may still be running.")
            ratif = sorted(results, key=lambda r: r.get("wide_pnl", 0), reverse=True)
            print(f"Using top {min(args.top_n, len(ratif))} by pnl from all results.")

        ratif.sort(key=lambda r: r.get("wide_pnl", 0), reverse=True)
        top_ratif = ratif[:args.top_n]

        grinder_prog_file = GRINDER_DIR / "progress.json"
        if grinder_prog_file.exists():
            prog = json.loads(grinder_prog_file.read_text(encoding="utf-8"))
            print(f"\nGrinder status: {prog.get('status')} | "
                  f"{prog.get('completed')}/{prog.get('total_combos')} combos | "
                  f"{len(ratif)} ratif candidates")

        for i, r in enumerate(top_ratif, 1):
            c = r.get("combo", {})
            full_combo = {
                **FIXED_PARAMS,
                "strike_offset": c.get("strike_offset", 1),
                "premium_stop_pct": c.get("premium_stop_pct", -0.10),
                "tp1_premium_pct": c.get("tp1_premium_pct", 0.30),
                "runner_target_pct": c.get("runner_target_pct", 2.0),
                "profit_lock_threshold_pct": c.get("profit_lock_threshold_pct", 0.05),
                "profit_lock_stop_offset_pct": c.get("profit_lock_stop_offset_pct", 0.08),
            }
            grinder_pnl = r.get("wide_pnl", 0)
            grinder_wr = r.get("wide_wr", 0)
            grinder_q = r.get("positive_quarters", 0)
            label = (f"rank{i}_off{c.get('strike_offset')}_"
                     f"pnl{int(grinder_pnl)}_wr{int(grinder_wr*100)}")
            print(f"\nRank {i}: pnl=${grinder_pnl:,.0f} wr={grinder_wr:.1%} "
                  f"+q={grinder_q}/{r.get('quarter_count',0)} "
                  f"ec=${r.get('edge_capture',0):+,.0f}  <- {label}")
            combos_to_test.append((label, full_combo))

    # ── Run each combo ──
    all_results: list[dict] = []
    for label, combo_dict in combos_to_test:
        result = _run_combo(
            combo_dict, spy_full, prior_close_map, prior_5d_avg_map,
            trade_dates, label, run_folds=not args.no_folds
        )
        result["grinder_label"] = label
        all_results.append(result)

    # ── Summary table ──
    print("\n\n" + "=" * 70)
    print("OOS VALIDATION SUMMARY")
    print("=" * 70)
    print(f"{'Combo':<40} {'IS_pnl':>8}  {'IS_shr':>7}  {'OOS_pnl':>8}  {'OOS_shr':>7}  {'WF_ratio':>9}  {'VERDICT':>8}")
    print("-" * 100)
    for res in all_results:
        combo_label = res["grinder_label"][:38]
        is_r = res["is_result"]
        oos_r = res["oos_result"]
        verdict = "PASS" if res["overall_pass"] else "FAIL"
        print(f"  {combo_label:<38}  ${is_r['wide_pnl']:>7,.0f}  {is_r['sharpe']:>7.3f}  "
              f"${oos_r['wide_pnl']:>7,.0f}  {oos_r['sharpe']:>7.3f}  "
              f"{res['wf_ratio']:>9.3f}  {verdict:>8}")

    # ── Interpretation ──
    print()
    best = max(all_results, key=lambda r: r["wf_ratio"])
    best_wf = best["wf_ratio"]
    if best_wf >= 0.70:
        print("Best WF ratio >= 0.70: Strategy generalizes WELL to OOS. Ready for J review.")
    elif best_wf >= 0.50:
        print("Best WF ratio 0.50-0.70: Mild overfit. Trade-worthy with sizing caution.")
    elif best_wf >= 0.30:
        print("Best WF ratio 0.30-0.50: Significant overfit. More data needed.")
    else:
        print("Best WF ratio < 0.30: SERIOUS overfit. Do NOT trade this regime filter alone.")

    # Context vs baseline
    print(f"\nBaselines (for context):")
    print(f"  VIX18 only (off=1):              WF ratio = -0.224  FAIL")
    print(f"  VIX-trend single-combo (off=1):  WF ratio =  0.353  FAIL (IS-concentration)")
    print(f"  This run best:                   WF ratio = {best_wf:.3f}  {'PASS' if best_wf >= 0.50 else 'FAIL'}")

    # ── Save ──
    payload = {
        "run_at": dt.datetime.now().isoformat(),
        "filter": f"VIX>={VIX_LOWER} AND VIX>prior_{VIX_TREND_WINDOW}d_avg",
        "window": {"is_start": IS_START.isoformat(), "is_end": IS_END.isoformat(),
                   "oos_start": OOS_START.isoformat(), "oos_end": OOS_END.isoformat()},
        "gates": {"wf_ratio_min": 0.50, "oos_pnl_positive": True, "oos_wr_min": 0.45},
        "results": all_results,
        "best_wf_ratio": best_wf,
        "best_combo_label": best["grinder_label"],
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    # Strip trade lists from saved JSON (can be large)
    for r in payload["results"]:
        for window_key in ("is_result", "oos_result"):
            r[window_key].pop("trades", None)
        for fr in r.get("fold_results", []):
            fr.pop("trades", None)
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nResults saved to {OUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
