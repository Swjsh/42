"""TBR_HIGH_VOL VIX regime filter analysis.

Tests whether adding VIX >= 18 AND VIX > 5d_avg (escalating) to TBR_HIGH_VOL
ITM-2 stop=-35% reduces the single-quarter P&L concentration observed in the
plain WF run (IS Q2-2025=85.4%, OOS Q1-2026=90.6%).

Hypothesis (from SNIPER L73 precedent):
  The concentrated quarters (IS Q2-2025, OOS Q1-2026) correspond to
  high-VIX / escalating VIX regimes (tariff uncertainty, rate-hike fear).
  Filtering to VIX-escalating days should:
    (a) Preserve edge in those quarters (where TBR fires cleanly)
    (b) Remove noise trades in calm VIX quarters (Q1/Q3-2025, Q4-2025)
    (c) Potentially reduce concentration IF the good P&L is from the
        VIX-escalating DAYS within the good quarter, not all days.

Logic: Post-filter trades from full WF run by VIX regime.
  Since _run_tbr_hv_real_fills processes each day independently, post-
  filtering by date is equivalent to skipping those days in-loop.

CLI::

    python -m autoresearch.tbr_hv_vix_filter
    python -m autoresearch.tbr_hv_vix_filter --threshold 18 --window 5
    python -m autoresearch.tbr_hv_vix_filter --out analysis/recommendations/tbr_hv_vix_filter.json
"""
from __future__ import annotations

import argparse
import bisect
import datetime as dt
import json
import sys
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path
from statistics import mean

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from autoresearch.runner import load_data
from autoresearch.tbr_hv_real_fills_val import (
    DEFAULT_COMBO,
    _report,
    _run_tbr_hv_real_fills,
)

# Matching the SNIPER VIX-trend filter params (L73, window uniquely optimal)
VIX_THRESHOLD = 18
VIX_TREND_WINDOW = 5

IS_START = dt.date(2025, 1, 1)
IS_END = dt.date(2025, 9, 30)
OOS_START = dt.date(2025, 10, 1)
OOS_END = dt.date(2026, 5, 22)

BEST_COMBO = replace(DEFAULT_COMBO, strike_offset=-2, stop_premium_pct=-0.35)


def _build_vix_maps(
    start: dt.date,
    end: dt.date,
    threshold: int = VIX_THRESHOLD,
    window: int = VIX_TREND_WINDOW,
) -> dict[dt.date, bool]:
    """Return {date: vix_passes} — True if VIX>=threshold AND VIX>5d_avg."""
    import pandas as pd

    # Load IS/OOS window only. Days lacking 5 prior VIX bars (e.g. IS first week)
    # default to prior_close=15.0 which is below threshold -> those days get skipped.
    spy_df, vix_df = load_data(start, end)

    # Normalise VIX timestamps — use utc=True to handle mixed-tz CSVs (FutureWarning fix)
    vix_df = vix_df.copy()
    vix_df["timestamp_et"] = (
        pd.to_datetime(vix_df["timestamp_et"], utc=True)
        .dt.tz_convert("America/New_York")
        .dt.tz_localize(None)
    )

    # Normalise SPY timestamps for trade_dates extraction
    spy_df = spy_df.copy()
    spy_df["timestamp_et"] = (
        pd.to_datetime(spy_df["timestamp_et"], utc=True)
        .dt.tz_convert("America/New_York")
        .dt.tz_localize(None)
    )

    # Daily close per VIX date
    vix_by_date: dict[dt.date, float] = (
        vix_df.groupby(vix_df["timestamp_et"].dt.date)["close"]
        .last()
        .to_dict()
    )
    sorted_vix_days = sorted(vix_by_date.keys())
    vix_sorted_vals = [vix_by_date[d] for d in sorted_vix_days]

    trade_dates = sorted(set(spy_df["timestamp_et"].dt.date.unique()))
    trade_dates = [d for d in trade_dates if start <= d <= end]

    passes: dict[dt.date, bool] = {}
    for trade_date in trade_dates:
        idx = bisect.bisect_left(sorted_vix_days, trade_date) - 1
        if idx < 0:
            passes[trade_date] = False
            continue
        prior_close = float(vix_sorted_vals[idx])
        start_idx = max(0, idx - window + 1)
        window_vals = vix_sorted_vals[start_idx : idx + 1]
        prior_5d_avg = float(mean(window_vals)) if window_vals else 15.0

        passes[trade_date] = prior_close >= threshold and prior_close > prior_5d_avg

    return passes


def _report_split(
    trades: list[dict],
    label: str,
    vix_passes: dict[dt.date, bool],
) -> tuple[dict, dict]:
    """Report both unfiltered and VIX-filtered results. Return (unfiltered, filtered) summaries."""
    filtered = [
        t for t in trades
        if vix_passes.get(dt.date.fromisoformat(t["date"]), False)
    ]

    n_pass = sum(1 for d, p in vix_passes.items() if p)
    n_total = len(vix_passes)
    print(f"\n  VIX filter: {n_pass}/{n_total} trading days pass "
          f"(VIX>={VIX_THRESHOLD} AND escalating)")
    print(f"  Unfiltered trades: {len(trades)}  ->  Filtered: {len(filtered)}")

    print(f"\n  --- Unfiltered ---")
    summ_unfilt = _report(trades, f"{label} [UNFILTERED]")

    print(f"\n  --- VIX-filtered (>={VIX_THRESHOLD} AND escalating) ---")
    summ_filt = _report(filtered, f"{label} [VIX-FILTERED]")

    # Concentration analysis
    for name, t_list, summ in [
        ("UNFILTERED", trades, summ_unfilt),
        ("VIX-FILTERED", filtered, summ_filt),
    ]:
        if not t_list:
            continue
        total = summ.get("total_pnl", 0.0)
        qpnl: dict = defaultdict(float)
        for t in t_list:
            d = dt.date.fromisoformat(t["date"])
            q = f"{d.year}-Q{(d.month-1)//3+1}"
            qpnl[q] += t["pnl"]
        if total != 0.0:
            max_q = max(qpnl, key=lambda q: abs(qpnl[q]))
            max_pct = qpnl[max_q] / total * 100
            print(f"  [{name}] Concentration: max quarter = {max_q} "
                  f"({qpnl[max_q]:+.2f} = {max_pct:.1f}% of total)")
        else:
            print(f"  [{name}] Concentration: total P&L = $0")

    return summ_unfilt, summ_filt


def run_vix_filter_analysis(
    threshold: int = VIX_THRESHOLD,
    window: int = VIX_TREND_WINDOW,
    out_path: Path | None = None,
) -> dict:
    print("=== TBR_HIGH_VOL ITM-2 VIX Regime Filter Analysis ===")
    print(f"Combo: strike_offset=-2, stop=-35% (best from WF PASS run)")
    print(f"VIX filter: VIX >= {threshold} AND VIX > prior {window}d avg (escalating)")
    print(f"IS : {IS_START} to {IS_END}")
    print(f"OOS: {OOS_START} to {OOS_END}")
    print()

    # Build VIX pass maps for IS and OOS
    print("Building VIX regime maps...")
    is_vix = _build_vix_maps(IS_START, IS_END, threshold, window)
    oos_vix = _build_vix_maps(OOS_START, OOS_END, threshold, window)

    print(f"\nLoading IS trades ({IS_START} to {IS_END})...")
    is_trades = _run_tbr_hv_real_fills(IS_START, IS_END, combo=BEST_COMBO)

    print(f"\nLoading OOS trades ({OOS_START} to {OOS_END})...")
    oos_trades = _run_tbr_hv_real_fills(OOS_START, OOS_END, combo=BEST_COMBO)

    print("\n" + "=" * 60)
    print("IS RESULTS")
    is_summ_unfilt, is_summ_filt = _report_split(is_trades, f"IS ({IS_START}->{IS_END})", is_vix)

    print("\n" + "=" * 60)
    print("OOS RESULTS")
    oos_summ_unfilt, oos_summ_filt = _report_split(oos_trades, f"OOS ({OOS_START}->{OOS_END})", oos_vix)

    # WF ratios
    def _wf(is_s: dict, oos_s: dict, label: str) -> float:
        is_exp = is_s.get("exp", 0.0)
        oos_exp = oos_s.get("exp", 0.0)
        ratio = (oos_exp / is_exp) if is_exp != 0.0 else float("inf")
        gate = ratio >= 0.50 and oos_s.get("passes", False)
        print(f"  [{label}] WF ratio = {ratio:.3f}  IS_exp={is_exp:+.2f}  "
              f"OOS_exp={oos_exp:+.2f}  n_oos={oos_s.get('n', 0)}  "
              f"OOS_WR={oos_s.get('wr', 0):.1%}  Gate: {'PASS' if gate else 'FAIL'}")
        return ratio

    print("\n" + "=" * 60)
    print("WALK-FORWARD SUMMARY")
    ratio_unfilt = _wf(is_summ_unfilt, oos_summ_unfilt, "UNFILTERED")
    ratio_filt = _wf(is_summ_filt, oos_summ_filt, "VIX-FILTERED")

    print()
    if ratio_filt >= 0.50 and oos_summ_filt.get("passes", False):
        print("  VIX-FILTERED: WF PASS — regime filter preserves edge")
    else:
        print("  VIX-FILTERED: WF FAIL or gate miss")

    result = {
        "run_date": dt.date.today().isoformat(),
        "vix_threshold": threshold,
        "vix_window": window,
        "is_unfiltered": {"start": str(IS_START), "end": str(IS_END), **is_summ_unfilt},
        "oos_unfiltered": {"start": str(OOS_START), "end": str(OOS_END), **oos_summ_unfilt},
        "is_filtered": {"start": str(IS_START), "end": str(IS_END), **is_summ_filt},
        "oos_filtered": {"start": str(OOS_START), "end": str(OOS_END), **oos_summ_filt},
        "wf_ratio_unfiltered": round(ratio_unfilt, 4) if ratio_unfilt != float("inf") else None,
        "wf_ratio_filtered": round(ratio_filt, 4) if ratio_filt != float("inf") else None,
    }

    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, default=str)
        print(f"\nResults written to {out_path}")

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="TBR high-vol VIX regime filter analysis")
    parser.add_argument("--threshold", type=int, default=VIX_THRESHOLD,
                        help="VIX lower bound (default 18)")
    parser.add_argument("--window", type=int, default=VIX_TREND_WINDOW,
                        help="Rolling VIX avg window in days (default 5)")
    parser.add_argument("--out", default=None, help="Write JSON results to this path")
    args = parser.parse_args()

    result = run_vix_filter_analysis(
        threshold=args.threshold,
        window=args.window,
        out_path=Path(args.out) if args.out else None,
    )
    filt_pass = (
        result.get("wf_ratio_filtered", 0) is not None
        and result["wf_ratio_filtered"] >= 0.50
        and result["oos_filtered"].get("passes", False)
    )
    return 0 if filt_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
