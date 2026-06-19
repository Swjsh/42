"""OOS walk-forward validation for SNIPER VIX>=18 primary candidate.

PRIMARY CANDIDATE:
  strike_offset=1, premium_stop=-10%, tp1=30%, runner=2.0x, lk=5%/8%
  VIX>=18 pre-filter (skip day if prior_day_VIX_close < 18)

PROTOCOL (identical to v14_enhanced_grinder OOS):
  IS:  2025-01-01 .. 2025-10-31  (10 months — optimizer window)
  OOS: 2025-11-01 .. 2026-05-22  (6.5 months — true holdout)

  Gate:  OOS_Sharpe / IS_Sharpe >= 0.50 (WF_ratio gate)
  Secondary: OOS P&L > 0, OOS WR >= 45%

FOLD BREAKDOWN (for regime attribution):
  F1: 2025-11 .. 2025-12
  F2: 2026-01 .. 2026-02
  F3: 2026-03 .. 2026-04
  F4: 2026-05+

OUTPUT:
  Console table + autoresearch/_state/sniper_vix18_oos_results.json

CLI:
  python autoresearch/_oos_sniper_vix18.py
"""

from __future__ import annotations

import bisect
import datetime as dt
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

WIDE_START = dt.date(2025, 1, 1)
WIDE_END = dt.date(2026, 5, 22)

IS_START = dt.date(2025, 1, 1)
IS_END = dt.date(2025, 10, 31)
OOS_START = dt.date(2025, 11, 1)
OOS_END = dt.date(2026, 5, 22)

OUT_JSON = REPO / "autoresearch" / "_state" / "sniper_vix18_oos_results.json"

VIX_LOWER = 18

# Primary candidate from VIX18 grinder
PRIMARY_COMBO = {
    "vol_mult": 1.1,
    "body_min_cents": 0.02,
    "min_stars": 2,
    "strike_offset": 1,
    "premium_stop_pct": -0.10,
    "tp1_premium_pct": 0.30,
    "tp1_qty_fraction": 0.5,
    "runner_target_pct": 2.0,
    "profit_lock_threshold_pct": 0.05,
    "profit_lock_stop_offset_pct": 0.08,
    "qty": 10,
    "proximity_dollars": 1.5,
    "require_break_above_open": True,
}

# OOS folds for regime attribution
OOS_FOLDS = [
    ("F1 (2025-Q4)",  dt.date(2025, 11, 1),  dt.date(2025, 12, 31)),
    ("F2 (2026-Q1a)", dt.date(2026, 1, 1),   dt.date(2026, 2, 28)),
    ("F3 (2026-Q1b)", dt.date(2026, 3, 1),   dt.date(2026, 4, 30)),
    ("F4 (2026-Q2)",  dt.date(2026, 5, 1),   dt.date(2026, 5, 22)),
]


def _build_vix_prev_map(vix_df: pd.DataFrame, trade_dates: list[dt.date]) -> dict[dt.date, float]:
    """Return {trade_date: prior_day_vix_close} using bisect for O(n log n)."""
    vix_by_date = (
        vix_df.groupby(vix_df["timestamp_et"].dt.date)["close"]
        .last()
        .to_dict()
    )
    sorted_vix_days = sorted(vix_by_date.keys())
    result: dict[dt.date, float] = {}
    for trade_date in trade_dates:
        idx = bisect.bisect_left(sorted_vix_days, trade_date) - 1
        result[trade_date] = float(vix_by_date[sorted_vix_days[idx]]) if idx >= 0 else 15.0
    return result


def _sharpe(day_pnl_map: dict[dt.date, float]) -> float:
    """Daily Sharpe (annualized sqrt-252) from day -> pnl map.
    Includes zero-pnl VIX-filtered trade days to keep denominator honest."""
    vals = list(day_pnl_map.values())
    if len(vals) < 2:
        return 0.0
    mean = sum(vals) / len(vals)
    variance = sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)
    std = math.sqrt(variance)
    if std == 0:
        return 0.0
    return (mean / std) * math.sqrt(252)


def _run_window(
    spy_full: pd.DataFrame,
    vix_prev_map: dict[dt.date, float],
    trade_dates: list[dt.date],
    combo_dict: dict,
    window_start: dt.date,
    window_end: dt.date,
    label: str,
) -> dict:
    """Run primary combo with VIX>=18 filter on a date sub-window."""
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
    skipped_vix = 0

    for date_et in trade_dates:
        if date_et < window_start or date_et > window_end:
            continue
        vix_prev = vix_prev_map.get(date_et, 15.0)
        if vix_prev < VIX_LOWER:
            skipped_vix += 1
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

    # Max drawdown from daily cumulative
    cum = peak = max_dd = 0.0
    for d in sorted(day_pnl_map.keys()):
        cum += day_pnl_map[d]
        if cum > peak:
            peak = cum
        dd = peak - cum
        if dd > max_dd:
            max_dd = dd

    # Concentration: top 5 trade days
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
        "skipped_vix": skipped_vix,
        "quarter_pnl": {k: round(v, 2) for k, v in sorted(quarter_pnl_map.items())},
    }


def main() -> None:
    from autoresearch import runner as _runner
    import pytz

    print("=" * 70)
    print("SNIPER VIX>=18 OOS Walk-Forward Validation")
    print("=" * 70)
    print(f"Combo: off=1, stp=-10%, tp1=30%, run=2.0x, lk=5%/8%, VIX>={VIX_LOWER}")
    print(f"IS:  {IS_START} .. {IS_END}")
    print(f"OOS: {OOS_START} .. {OOS_END}")
    print(f"Gate: OOS_Sharpe / IS_Sharpe >= 0.50")
    print()

    print("Loading SPY + VIX data...", end=" ", flush=True)
    spy_full, vix_full = _runner.load_data(WIDE_START, WIDE_END)
    for df in (spy_full, vix_full):
        df["timestamp_et"] = (
            pd.to_datetime(df["timestamp_et"], utc=True)
            .dt.tz_convert(pytz.timezone("US/Eastern"))
            .dt.tz_localize(None)
        )
    print("done")

    all_dates = sorted(set(spy_full["timestamp_et"].dt.date.unique()))
    trade_dates = [d for d in all_dates if WIDE_START <= d <= WIDE_END]
    vix_prev_map = _build_vix_prev_map(vix_full, trade_dates)
    print(f"Total trade dates in window: {len(trade_dates)}")
    print()

    # ── Run IS + OOS ──
    print("Running IS window...", end=" ", flush=True)
    is_res = _run_window(spy_full, vix_prev_map, trade_dates,
                         PRIMARY_COMBO, IS_START, IS_END, "IS")
    print(f"done  n={is_res['wide_n_trades']}  pnl=${is_res['wide_pnl']:,.0f}  "
          f"wr={is_res['wide_wr']:.1%}  sharpe={is_res['sharpe']:.3f}")

    print("Running OOS window...", end=" ", flush=True)
    oos_res = _run_window(spy_full, vix_prev_map, trade_dates,
                          PRIMARY_COMBO, OOS_START, OOS_END, "OOS")
    print(f"done  n={oos_res['wide_n_trades']}  pnl=${oos_res['wide_pnl']:,.0f}  "
          f"wr={oos_res['wide_wr']:.1%}  sharpe={oos_res['sharpe']:.3f}")
    print()

    # ── WF gate ──
    is_sharpe = is_res["sharpe"]
    oos_sharpe = oos_res["sharpe"]
    wf_ratio = round(oos_sharpe / is_sharpe, 3) if is_sharpe != 0 else 0.0
    wf_pass = wf_ratio >= 0.50
    pnl_pass = oos_res["wide_pnl"] > 0
    wr_pass = oos_res["wide_wr"] >= 0.45

    print("=" * 70)
    print("WALK-FORWARD GATE CHECK")
    print("=" * 70)
    print(f"  IS  Sharpe : {is_sharpe:.3f}  (n={is_res['wide_n_trades']}, pnl=${is_res['wide_pnl']:,.0f}, wr={is_res['wide_wr']:.1%})")
    print(f"  OOS Sharpe : {oos_sharpe:.3f}  (n={oos_res['wide_n_trades']}, pnl=${oos_res['wide_pnl']:,.0f}, wr={oos_res['wide_wr']:.1%})")
    print(f"  WF ratio   : {wf_ratio:.3f}  ->  {'PASS' if wf_pass else 'FAIL'}  (gate: >=0.50)")
    print(f"  OOS P&L>0  : {'PASS' if pnl_pass else 'FAIL'}  (${oos_res['wide_pnl']:,.0f})")
    print(f"  OOS WR>=45%: {'PASS' if wr_pass else 'FAIL'}  ({oos_res['wide_wr']:.1%})")
    overall = wf_pass and pnl_pass and wr_pass
    print()
    print(f"  OVERALL: {'PASS' if overall else 'FAIL'}  ({'all 3 gates pass' if overall else 'at least 1 gate failed'})")
    print()

    # ── IS quarter breakdown ──
    print("IS Quarter Breakdown:")
    for q, v in sorted(is_res["quarter_pnl"].items()):
        bar = "+" if v >= 0 else "-"
        print(f"  {q}: {'+' if v >= 0 else ''}{v:,.0f}  [{bar}]")
    print()

    # ── OOS quarter breakdown ──
    print("OOS Quarter Breakdown:")
    for q, v in sorted(oos_res["quarter_pnl"].items()):
        bar = "+" if v >= 0 else "-"
        print(f"  {q}: {'+' if v >= 0 else ''}{v:,.0f}  [{bar}]")
    print()

    # ── OOS folds ──
    print("OOS Fold Breakdown:")
    print(f"  {'Fold':<18} {'n':>5}  {'pnl':>9}  {'wr':>6}  {'sharpe':>8}  {'VIX skip':>9}")
    print("  " + "-" * 60)
    fold_results = []
    for fold_label, fold_start, fold_end in OOS_FOLDS:
        fr = _run_window(spy_full, vix_prev_map, trade_dates,
                         PRIMARY_COMBO, fold_start, fold_end, fold_label)
        fold_results.append(fr)
        print(f"  {fold_label:<18} {fr['wide_n_trades']:>5}  "
              f"${fr['wide_pnl']:>8,.0f}  {fr['wide_wr']:>6.1%}  "
              f"{fr['sharpe']:>8.3f}  {fr['skipped_vix']:>9}")
    print()

    # ── Summary table ──
    print("Summary comparison:")
    print(f"  {'Window':<8} {'n':>5}  {'pnl':>9}  {'wr':>6}  {'sharpe':>8}  {'+q':>5}  {'top5%':>7}  {'maxdd':>8}")
    print("  " + "-" * 68)
    for res in [is_res, oos_res]:
        print(f"  {res['label']:<8} {res['wide_n_trades']:>5}  "
              f"${res['wide_pnl']:>8,.0f}  {res['wide_wr']:>6.1%}  "
              f"{res['sharpe']:>8.3f}  "
              f"{res['positive_quarters']:>2}/{res['quarter_count']:<2}  "
              f"{res['top5_pct']:>6.2f}x  "
              f"${res['max_drawdown']:>7,.0f}")
    print()

    # ── Interpretation ──
    print("Interpretation:")
    if wf_ratio >= 0.70:
        print("  WF ratio >= 0.70: Strategy generalizes WELL to OOS.")
    elif wf_ratio >= 0.50:
        print("  WF ratio 0.50-0.70: Mild overfit, still trade-worthy.")
    else:
        print("  WF ratio < 0.50: SERIOUS overfit. Do NOT trade.")
    print()

    # ── Save ──
    payload = {
        "run_at": dt.datetime.now().isoformat(),
        "combo": PRIMARY_COMBO,
        "vix_lower": VIX_LOWER,
        "window": {"full_start": WIDE_START.isoformat(), "full_end": WIDE_END.isoformat()},
        "is_result": is_res,
        "oos_result": oos_res,
        "fold_results": fold_results,
        "wf_ratio": wf_ratio,
        "wf_pass": wf_pass,
        "pnl_pass": pnl_pass,
        "wr_pass": wr_pass,
        "overall_pass": overall,
        "gates": {
            "wf_ratio_gate": 0.50,
            "oos_pnl_positive": True,
            "oos_wr_min": 0.45,
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Results saved to {OUT_JSON}")


if __name__ == "__main__":
    main()
