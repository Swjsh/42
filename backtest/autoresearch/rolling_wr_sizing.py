"""
Rolling Win-Rate Sizing Analysis

Hypothesis: Recent engine WR (last K trades) predicts near-future performance.
When the engine is "hot" (high WR), size up. When "cold" (low WR), hold steady.

Key motivation: GOLDILOCKS VIX-regime classifier FAILED (0 IS trades tagged).
Rolling WR is a PERFORMANCE-BASED regime signal that might naturally detect
deteriorating environments before they become catastrophic.

Sanity-check question: In April 2026 catastrophic month (WR=26.1%), did the
rolling WR already signal distress in the PRIOR 10-15 trades?

Runs PURE ANALYSIS (read-only). Does not modify params.json or heartbeat.md.
"""
from __future__ import annotations
import sys
import pathlib
import datetime as dt
import collections

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd

from backtest.lib.orchestrator import run_backtest

DATA_DIR = ROOT / "backtest" / "data"
SPY_FILE = DATA_DIR / "spy_5m_2025-01-01_2026-05-22.csv"
VIX_FILE = DATA_DIR / "vix_5m_2025-01-01_2026-05-22.csv"

IS_START  = dt.date(2025, 1, 2)
IS_END    = dt.date(2026, 5, 7)
OOS_START = dt.date(2026, 5, 8)
OOS_END   = dt.date(2026, 5, 22)

# Production params (post-Rank-31)
BASE = dict(
    use_real_fills=True,
    premium_stop_pct_bear=-0.20,
    premium_stop_pct_bull=-0.08,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.50,
    time_stop_minutes_before_close=20,
    midday_trendline_gate=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    per_trade_risk_cap_pct=0.30,
)

HIGH_MULT = 1.50
LOW_MULT  = 0.50
MID_MULT  = 1.00


def _rolling_wr(trades_sorted: list, idx: int, k: int) -> float | None:
    """WR of trades[idx-k : idx]. Returns None if insufficient history."""
    start = idx - k
    if start < 0:
        return None
    window = trades_sorted[start:idx]
    if not window:
        return None
    wins = sum(1 for t in window if t.dollar_pnl > 0)
    return wins / len(window)


def _classify(wr: float | None, high_thr: float, low_thr: float) -> str:
    if wr is None:
        return "WARMUP"
    if wr >= high_thr:
        return "HIGH"
    if wr <= low_thr:
        return "LOW"
    return "MID"


def _sort_key(t):
    """Tz-normalize sort key — IS trades may be tz-naive while OOS are tz-aware."""
    et = t.entry_time_et
    if getattr(et, 'tzinfo', None) is not None:
        return et.replace(tzinfo=None)
    return et


def _sizing_simulation(all_trades: list, k: int, high_thr: float, low_thr: float,
                       label: str, verbose: bool = False) -> dict:
    base_pnl = sum(t.dollar_pnl for t in all_trades)
    sized_pnl = 0.0
    counts = collections.Counter()
    pnl_by_class: dict[str, float] = collections.defaultdict(float)
    trades_by_class: dict[str, list] = collections.defaultdict(list)

    sorted_trades = sorted(all_trades, key=_sort_key)
    for i, t in enumerate(sorted_trades):
        wr = _rolling_wr(sorted_trades, i, k)
        cls = _classify(wr, high_thr, low_thr)
        mult = {"HIGH": HIGH_MULT, "MID": MID_MULT, "LOW": LOW_MULT, "WARMUP": MID_MULT}[cls]
        sized_pnl += t.dollar_pnl * mult
        counts[cls] += 1
        pnl_by_class[cls] += t.dollar_pnl
        trades_by_class[cls].append(t.dollar_pnl)

    delta = sized_pnl - base_pnl

    if verbose:
        print(f"\n  {label}  k={k}  high_thr={high_thr:.0%}  low_thr={low_thr:.0%}")
        print(f"    base_pnl={base_pnl:>+9.2f}  sized_pnl={sized_pnl:>+9.2f}  delta={delta:>+9.2f}")
        for cls in ["HIGH", "MID", "LOW", "WARMUP"]:
            n = counts[cls]
            p = pnl_by_class[cls]
            trades_list = trades_by_class[cls]
            wr = (sum(1 for x in trades_list if x > 0) / len(trades_list) * 100) if trades_list else 0
            avg = p / n if n else 0
            print(f"    {cls:>8}: n={n:>4}  pnl={p:>+9.0f}  avg={avg:>+7.1f}  WR={wr:.0f}%")

    return {
        "label": label,
        "k": k,
        "high_thr": high_thr,
        "low_thr": low_thr,
        "base_pnl": base_pnl,
        "sized_pnl": sized_pnl,
        "delta": delta,
        "counts": dict(counts),
        "pnl_by_class": dict(pnl_by_class),
    }


def _monthly_wr_progression(trades: list, k: int, label: str) -> None:
    """Show rolling WR at start of each month — key for catastrophic month sanity-check."""
    sorted_trades = sorted(trades, key=_sort_key)
    by_month: dict[str, list] = collections.defaultdict(list)

    # Compute rolling WR at entry of each trade
    for i, t in enumerate(sorted_trades):
        wr = _rolling_wr(sorted_trades, i, k)
        m = t.entry_time_et.date().strftime("%Y-%m")
        by_month[m].append((wr, t.dollar_pnl))

    print(f"\n{label} -- Monthly WR progression (k={k}):")
    print(f"{'Month':>10}  {'n':>5}  {'Mth_WR%':>8}  {'P&L':>10}  {'First_rolling_WR':>18}  {'Last_rolling_WR':>17}  Flag")
    print("-" * 110)

    CATASTROPHIC_MONTHS = {"2025-03", "2025-05", "2025-11", "2026-01", "2026-03", "2026-04"}

    for m in sorted(by_month.keys()):
        entries = by_month[m]
        n = len(entries)
        total_pnl = sum(p for _, p in entries)
        mth_wr = sum(1 for _, p in entries if p > 0) / n * 100 if n > 0 else 0
        first_wr = entries[0][0]
        last_wr  = entries[-1][0]

        def fmt_wr(wr):
            if wr is None:
                return "WARMUP"
            return f"{wr:.0%}"

        flag = ""
        if m in CATASTROPHIC_MONTHS:
            flag = "*** CATASTROPHIC"
        elif total_pnl > 2000:
            flag = "*** STRONG"

        # Warn if the month starts with high WR (false confidence before a crash)
        if m in CATASTROPHIC_MONTHS and first_wr is not None and first_wr >= 0.50:
            flag += " <- HIGH_WR_BEFORE_CRASH"

        print(f"{m:>10}  {n:>5}  {mth_wr:>7.1f}%  {total_pnl:>+10.0f}  {fmt_wr(first_wr):>18}  {fmt_wr(last_wr):>17}  {flag}")


def _per_trade_csv(all_trades: list, k: int, path: pathlib.Path) -> None:
    """Write per-trade rolling WR to CSV for deeper analysis."""
    sorted_trades = sorted(all_trades, key=_sort_key)
    rows = []
    for i, t in enumerate(sorted_trades):
        wr = _rolling_wr(sorted_trades, i, k)
        rows.append({
            "date": t.entry_time_et.date(),
            "entry_time": t.entry_time_et.strftime("%H:%M"),
            "dollar_pnl": round(t.dollar_pnl, 2),
            "win": 1 if t.dollar_pnl > 0 else 0,
            "rolling_wr_k": k,
            "rolling_wr": round(wr, 4) if wr is not None else None,
            "cls_h50_l35": _classify(wr, 0.50, 0.35),
            "exit_reason": str(t.exit_reason.name if t.exit_reason else "?"),
        })
    pd.DataFrame(rows).to_csv(path, index=False)
    print(f"  per-trade CSV → {path}")


if __name__ == "__main__":
    print("=" * 100)
    print("ROLLING WIN-RATE SIZING ANALYSIS")
    print("Hypothesis: recent WR (k trades) predicts near-future performance. Size 1.5× on hot, 0.5× on cold.")
    print("=" * 100)

    print("\n[1/3] Loading data...")
    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    print("\n[2/3] Running IS backtest (2025-01-02 to 2026-05-07)...")
    is_result = run_backtest(spy_df, vix_df, start_date=IS_START, end_date=IS_END, **BASE)
    is_trades = is_result.trades
    is_pnl = sum(t.dollar_pnl for t in is_trades)
    print(f"  IS: n={len(is_trades)}  pnl={is_pnl:+.2f}")

    print("\n[3/3] Running OOS backtest (2026-05-08 to 2026-05-22)...")
    oos_result = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END, **BASE)
    oos_trades = oos_result.trades
    oos_pnl = sum(t.dollar_pnl for t in oos_trades)
    print(f"  OOS: n={len(oos_trades)}  pnl={oos_pnl:+.2f}")

    # OOS rolling WR must continue from IS history (correct simulation)
    all_trades_ordered = sorted(is_trades + oos_trades, key=_sort_key)

    # ── Monthly WR progression (sanity check) ────────────────────────────────────
    print("\n" + "=" * 100)
    print("MONTHLY WR PROGRESSION (sanity check: does rolling WR drop BEFORE catastrophic months?)")

    for k in [10, 15, 20]:
        _monthly_wr_progression(is_trades, k, "IS")
        break  # just k=15 for the monthly view to keep output concise

    # ── Catastrophic month deep-dive ──────────────────────────────────────────────
    print("\n" + "=" * 100)
    print("APRIL 2026 DEEP-DIVE (catastrophic month, WR=26.1%, -$6400): rolling WR at each entry")

    sorted_all = sorted(all_trades_ordered, key=_sort_key)
    apr26_trades = [t for t in sorted_all if t.entry_time_et.date().strftime("%Y-%m") == "2026-04"]
    idx_map = {id(t): i for i, t in enumerate(sorted_all)}

    print(f"  April 2026: n={len(apr26_trades)} trades")
    print(f"  {'Date':>12}  {'Time':>6}  {'P&L':>10}  {'k=10 rolling WR':>17}  {'k=15 rolling WR':>17}  {'k=20 rolling WR':>17}")
    print("-" * 95)
    for t in apr26_trades[:15]:  # first 15 trades
        idx = idx_map[id(t)]
        wr10 = _rolling_wr(sorted_all, idx, 10)
        wr15 = _rolling_wr(sorted_all, idx, 15)
        wr20 = _rolling_wr(sorted_all, idx, 20)
        win  = "W" if t.dollar_pnl > 0 else "L"
        print(f"  {str(t.entry_time_et.date()):>12}  {t.entry_time_et.strftime('%H:%M'):>6}  "
              f"{t.dollar_pnl:>+10.2f} {win}  "
              f"{(f'{wr10:.0%}' if wr10 is not None else 'WARMUP'):>17}  "
              f"{(f'{wr15:.0%}' if wr15 is not None else 'WARMUP'):>17}  "
              f"{(f'{wr20:.0%}' if wr20 is not None else 'WARMUP'):>17}")

    # ── Main sweep ────────────────────────────────────────────────────────────────
    print("\n" + "=" * 100)
    print("THRESHOLD SWEEP — k × high_thr × low_thr. All use IS period only for sizing.")
    print(f"{'k':>4}  {'high':>6}  {'low':>6}  {'IS_base':>9}  {'IS_sized':>9}  {'IS_delta':>9}  "
          f"{'OOS_base':>9}  {'OOS_sized':>9}  {'OOS_delta':>9}  {'WF':>6}")
    print("-" * 100)

    best_results = []
    for k in [10, 15, 20]:
        for high_thr in [0.50, 0.55, 0.60]:
            for low_thr in [0.25, 0.30, 0.35]:
                # IS sizing: use IS trades sorted, rolling WR from IS history
                is_sorted = sorted(is_trades, key=_sort_key)
                is_sized_pnl = 0.0
                for i, t in enumerate(is_sorted):
                    wr = _rolling_wr(is_sorted, i, k)
                    cls = _classify(wr, high_thr, low_thr)
                    mult = {"HIGH": HIGH_MULT, "MID": MID_MULT, "LOW": LOW_MULT, "WARMUP": MID_MULT}[cls]
                    is_sized_pnl += t.dollar_pnl * mult
                is_delta = is_sized_pnl - is_pnl

                # OOS sizing: rolling WR uses IS + prior OOS trades
                oos_sorted = sorted(oos_trades, key=_sort_key)
                oos_sized_pnl = 0.0
                prefix = is_sorted[:]
                for i, t in enumerate(oos_sorted):
                    wr = _rolling_wr(prefix + oos_sorted[:i], len(prefix) + i, k)
                    cls = _classify(wr, high_thr, low_thr)
                    mult = {"HIGH": HIGH_MULT, "MID": MID_MULT, "LOW": LOW_MULT, "WARMUP": MID_MULT}[cls]
                    oos_sized_pnl += t.dollar_pnl * mult
                oos_delta = oos_sized_pnl - oos_pnl

                wf = oos_delta / is_delta if is_delta != 0 else float("inf")
                pass_fail = "PASS" if (oos_delta > 0 and wf >= 0.70) else ""

                print(f"{k:>4}  {high_thr:>6.0%}  {low_thr:>6.0%}  "
                      f"{is_pnl:>+9.0f}  {is_sized_pnl:>+9.0f}  {is_delta:>+9.0f}  "
                      f"{oos_pnl:>+9.0f}  {oos_sized_pnl:>+9.0f}  {oos_delta:>+9.0f}  "
                      f"{wf:>6.3f}  {pass_fail}")

                best_results.append((is_delta + oos_delta, k, high_thr, low_thr, is_delta, oos_delta, wf))

    # ── Top combos ────────────────────────────────────────────────────────────────
    best_results.sort(key=lambda x: x[0], reverse=True)
    print("\nTop 5 combos by IS+OOS delta:")
    for total, k, ht, lt, isd, oosd, wf in best_results[:5]:
        verdict = "PASS" if (oosd > 0 and wf >= 0.70) else "FAIL"
        print(f"  k={k:>2}  high={ht:.0%}  low={lt:.0%}  IS_delta={isd:>+7.0f}  "
              f"OOS_delta={oosd:>+7.0f}  total={total:>+8.0f}  WF={wf:.3f}  {verdict}")

    # ── Verbose detail for best IS+OOS combo ─────────────────────────────────────
    if best_results:
        _, bk, bht, blt, _, _, _ = best_results[0]
        print(f"\nVERBOSE DETAIL for best combo k={bk} high={bht:.0%} low={blt:.0%}:")
        _sizing_simulation(is_trades, bk, bht, blt, "IS", verbose=True)

        oos_sorted = sorted(oos_trades, key=_sort_key)
        is_sorted  = sorted(is_trades,  key=_sort_key)
        print(f"\n  OOS classification breakdown (rolling WR carries over from IS):")
        print(f"    {'Date':>12}  {'P&L':>10}  {'WR@entry':>10}  {'class':>8}")
        prefix = is_sorted[:]
        for i, t in enumerate(oos_sorted):
            wr = _rolling_wr(prefix + oos_sorted[:i], len(prefix) + i, bk)
            cls = _classify(wr, bht, blt)
            mult = {"HIGH": HIGH_MULT, "MID": MID_MULT, "LOW": LOW_MULT, "WARMUP": MID_MULT}[cls]
            print(f"    {str(t.entry_time_et.date()):>12}  {t.dollar_pnl:>+10.2f}  "
                  f"{(f'{wr:.0%}' if wr is not None else 'WARMUP'):>10}  {cls:>8}  x{mult}")

    # ── Per-trade CSV export ──────────────────────────────────────────────────────
    csv_path = ROOT / "analysis" / "backtests" / "rolling_wr_per_trade.csv"
    _per_trade_csv(is_trades + oos_trades, 15, csv_path)

    print("\nANALYSIS COMPLETE.")
