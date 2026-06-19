"""
Filter-6 spread threshold + VIX-escalating compound gate test.

Research question: filter-6@20c failed OOS because it opened low-quality early entries
on non-trending VIX days (4/29 11:50 trap, OOS 13:15 trap). Does adding a VIX-escalating
gate (prior_day_VIX >= prior_5d_avg_VIX) restore OOS validity?

Two-phase test:
  Phase 1 — VIX character audit: for each J anchor day and OOS day, compute whether
             VIX was escalating. Report which days would be gated on/off.
  Phase 2 — Anchor day simulation: run filter-6@20c only on VIX-escalating anchor days
             to see if EC improves without 4/29 trap.

USAGE (from backtest/):
    python autoresearch/f6_vix_escalating_compound.py
"""
from __future__ import annotations

import bisect
import datetime as dt
import json
import sys
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "backtest"))

import pandas as pd
from lib.orchestrator import run_backtest
from autoresearch import runner
from autoresearch.j_edge_tracker import V15_J_EDGE_OVERRIDES
from autoresearch.ribbon_flip_confirm_ab import build_kwargs

VIX_TREND_WINDOW = 5

J_DAYS = {
    "2026-04-29": {"type": "winner", "j_pnl": 342},
    "2026-05-01": {"type": "winner", "j_pnl": 470},
    "2026-05-04": {"type": "winner", "j_pnl": 730},
    "2026-05-05": {"type": "loser",  "j_pnl": -260},
    "2026-05-06": {"type": "loser",  "j_pnl": -300},
    "2026-05-07": {"type": "loser",  "j_pnl": -165},
}

OOS_START = dt.date(2026, 5, 8)
OOS_END   = dt.date(2026, 5, 22)


def _build_vix_maps(
    vix_df: pd.DataFrame,
    trade_dates: list[dt.date],
) -> tuple[dict[dt.date, float], dict[dt.date, float]]:
    vix_df = vix_df.copy()
    vix_df["timestamp_et"] = pd.to_datetime(vix_df["timestamp_et"], utc=True).dt.tz_convert(
        "America/New_York"
    ).dt.tz_localize(None)
    vix_by_date: dict[dt.date, float] = (
        vix_df.groupby(vix_df["timestamp_et"].dt.date)["close"].last().to_dict()
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


def _edge_capture(day_pnl: dict) -> float:
    winners = ["2026-04-29", "2026-05-01", "2026-05-04"]
    losers  = ["2026-05-05", "2026-05-06", "2026-05-07"]
    return (
        sum(day_pnl[d]["pnl"] for d in winners)
        - sum(max(0, -day_pnl[d]["pnl"]) for d in losers)
    )


def main() -> None:
    params_path = ROOT / "automation" / "state" / "params.json"
    params = json.loads(params_path.read_text(encoding="utf-8-sig"))
    params.update(V15_J_EDGE_OVERRIDES)

    # --- Phase 1: VIX character audit ---
    # Load wide data to build VIX maps
    wide_start = dt.date(2026, 3, 15)
    wide_end   = dt.date(2026, 5, 22)
    _, vix_wide = runner.load_data(wide_start, wide_end)

    anchor_dates = [dt.date.fromisoformat(d) for d in J_DAYS]
    oos_dates_raw = pd.bdate_range(
        start=OOS_START.isoformat(), end=OOS_END.isoformat()
    ).date.tolist()
    all_dates = anchor_dates + oos_dates_raw

    prior_close_map, prior_5d_avg_map = _build_vix_maps(vix_wide, all_dates)

    print("=" * 72)
    print("PHASE 1 — VIX Character Audit")
    print(f"{'Date':<12} {'DayType':<8} {'PriorVIX':>9} {'5dAvg':>7} {'Escalating':>11}")
    print("-" * 55)

    escalating: dict[dt.date, bool] = {}
    for d in all_dates:
        pv = prior_close_map[d]
        avg = prior_5d_avg_map[d]
        esc = pv >= avg
        escalating[d] = esc
        dtype = J_DAYS.get(d.isoformat(), {}).get("type", "oos")
        tag = "YES" if esc else "NO "
        marker = "  <-- TRAP" if (not esc and d in anchor_dates) else ""
        print(f"{d.isoformat():<12} {dtype:<8} {pv:>9.2f} {avg:>7.2f} {tag:>11}{marker}")

    print()

    # --- Phase 2: Anchor day simulation ---
    # Load anchor-day data
    min_d = dt.date(2026, 4, 29)
    max_d = dt.date(2026, 5, 7)
    spy_df, vix_df = runner.load_data(min_d, max_d)

    print("=" * 72)
    print("PHASE 2 — Anchor Day Simulation")
    print()

    def run_anchor(spread_threshold: int, vix_gate: bool) -> dict[str, dict]:
        label_parts = [f"spread>={spread_threshold}c"]
        if vix_gate:
            label_parts.append("VIX-escalating")
        label = " + ".join(label_parts)
        print(f"  Config: {label}")
        patched_params = dict(params)
        patched_params["ribbon_spread_min_cents"] = spread_threshold
        day_pnl: dict[str, dict] = {}
        for date_str, meta in J_DAYS.items():
            d = dt.date.fromisoformat(date_str)
            if vix_gate and not escalating.get(d, True):
                pnl = 0.0
                n = 0
                exits = []
            else:
                kwargs = build_kwargs(patched_params, d, d, spy_df, vix_df, False)
                with runner._patched_filter_constants(patched_params):
                    bt = run_backtest(**kwargs)
                trades = [t for t in bt.trades if t.entry_time_et.date() == d]
                pnl = sum(t.dollar_pnl for t in trades)
                n = len(trades)
                exits = [str(t.exit_reason) for t in trades]
            day_pnl[date_str] = {"pnl": pnl, "n": n}
            vix_state = "ESC" if escalating.get(d, True) else "FLAT"
            gate_note = " [GATED-OUT]" if (vix_gate and not escalating.get(d, True)) else ""
            print(f"    {date_str} ({meta['type']:6s}, VIX={vix_state}): "
                  f"pnl={pnl:+.0f}  n={n}  exits={exits}{gate_note}")
        ec = _edge_capture(day_pnl)
        print(f"    -> edge_capture={ec:+.0f}  (floor=771)")
        print()
        return day_pnl

    baseline_pnl  = run_anchor(30, False)
    f6_20c_pnl    = run_anchor(20, False)
    f6_20c_vix    = run_anchor(20, True)
    f6_15c_vix    = run_anchor(15, True)

    print("=" * 72)
    print("SUMMARY TABLE\n")
    header = f"{'Day':<12} {'J_pnl':>7}  {'Base(30c)':>10}  {'20c':>8}  {'20c+VIX':>9}  {'15c+VIX':>9}"
    print(header)
    print("-" * 65)
    for date_str, meta in J_DAYS.items():
        d = dt.date.fromisoformat(date_str)
        vix_state = "ESC" if escalating.get(d, True) else "FLAT"
        print(
            f"{date_str:<12} {meta['j_pnl']:>7}  "
            f"{baseline_pnl[date_str]['pnl']:>10.0f}  "
            f"{f6_20c_pnl[date_str]['pnl']:>8.0f}  "
            f"{f6_20c_vix[date_str]['pnl']:>9.0f}  "
            f"{f6_15c_vix[date_str]['pnl']:>9.0f}  "
            f"({vix_state})"
        )
    print("-" * 65)
    print(
        f"{'edge_capture':<12} {'':>7}  "
        f"{_edge_capture(baseline_pnl):>10.0f}  "
        f"{_edge_capture(f6_20c_pnl):>8.0f}  "
        f"{_edge_capture(f6_20c_vix):>9.0f}  "
        f"{_edge_capture(f6_15c_vix):>9.0f}"
    )
    print(f"{'floor=771'}")
    print()

    # --- Phase 3: OOS simulation ---
    print("=" * 72)
    print("PHASE 3 — OOS Simulation (filter-6@20c vs 20c+VIX-escalating)")
    print()

    oos_spy, oos_vix = runner.load_data(OOS_START, OOS_END)

    def run_oos(spread_threshold: int, vix_gate: bool) -> dict:
        patched_params = dict(params)
        patched_params["ribbon_spread_min_cents"] = spread_threshold
        total_pnl = 0.0
        wins = 0
        total = 0
        skipped_days = 0
        for d in oos_dates_raw:
            if vix_gate and not escalating.get(d, True):
                skipped_days += 1
                continue
            try:
                kwargs = build_kwargs(patched_params, d, d, oos_spy, oos_vix, False)
                with runner._patched_filter_constants(patched_params):
                    bt = run_backtest(**kwargs)
            except Exception:
                continue
            trades = [t for t in bt.trades if t.entry_time_et.date() == d]
            for t in trades:
                total += 1
                total_pnl += t.dollar_pnl
                if t.dollar_pnl > 0:
                    wins += 1
        wr = wins / total if total else 0
        label_parts = [f"spread>={spread_threshold}c"]
        if vix_gate:
            label_parts.append("VIX-escalating")
        label = " + ".join(label_parts)
        print(f"  {label}: n={total}  WR={wr:.1%}  total={total_pnl:+.0f}  "
              f"exp={total_pnl/total if total else 0:+.1f}/trade"
              f"  skipped_days={skipped_days}")
        return {"n": total, "wr": wr, "total": total_pnl, "skipped_days": skipped_days}

    oos_base  = run_oos(30, False)
    oos_20c   = run_oos(20, False)
    oos_20v   = run_oos(20, True)
    oos_15v   = run_oos(15, True)

    print()
    print("OOS GATE: candidate_pnl >= baseline_pnl * 0.90 (L92 guard)")
    for label, result in [("20c", oos_20c), ("20c+VIX", oos_20v), ("15c+VIX", oos_15v)]:
        delta = result["total"] - oos_base["total"]
        pct = result["total"] / oos_base["total"] if oos_base["total"] != 0 else float("inf")
        gate = "PASS" if result["total"] >= oos_base["total"] * 0.90 else "FAIL"
        print(f"  {label:<12}: OOS={result['total']:+.0f}  delta={delta:+.0f}  "
              f"ratio={pct:.3f}  gate={gate}")


if __name__ == "__main__":
    main()
