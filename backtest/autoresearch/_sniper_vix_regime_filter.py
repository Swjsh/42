"""SNIPER VIX regime filter calibration.

PROBLEM (confirmed by grinder + per-quarter analysis):
  SNIPER best combo wide_pnl=-$91 (real-fills). Per-quarter breakdown:
    2025-Q1: +$963   (high-VIX, trending)
    2025-Q2: -$1,062 (low-VIX, choppy summer)
    2025-Q3: -$1,875 (low-VIX, summer doldrums)
    2025-Q4: -$549   (moderate, mixed)
    2026-Q1: +$3,701 (very high-VIX, tariff volatility spike)
    2026-Q2: -$1,270 (mixed, post-spike mean reversion)

HYPOTHESIS:
  SNIPER level-break entries only have edge when VIX is elevated (trending
  environment, genuine breakouts). When VIX is low, level breaks are false
  breakouts (choppy price rotates back through the level immediately).

  If we SKIP days when the prior-day VIX close < threshold, we eliminate
  the false-breakout drag and keep only the regime-appropriate entries.

TEST:
  Best combo: strike_offset=2, stop=-10%, lock=5%/5%, tp1=50%, runner=2.0
  VIX thresholds tested: 14, 16, 18, 20, 22 (skip day if VIX_prev_close < threshold)
  Baseline: no filter (threshold=0)

ACCEPTANCE GATE:
  - wide_pnl > $2,000 (real-fills)
  - positive_quarters >= 4/6
  - WR >= 45%

OUTPUT:
  backtest/autoresearch/_state/sniper_vix_regime_results.json
  Console table: threshold | n_trades | wide_pnl | WR | +quarters

CLI:
  .venv\\Scripts\\python.exe autoresearch/_sniper_vix_regime_filter.py
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

WIDE_START = dt.date(2025, 1, 1)
WIDE_END = dt.date(2026, 5, 22)

OUT_DIR = REPO / "autoresearch" / "_state"
OUT_JSON = OUT_DIR / "sniper_vix_regime_results.json"

# Best real-fills combo from sniper grinder
BEST_COMBO = {
    "vol_mult": 1.1,
    "body_min_cents": 0.02,
    "min_stars": 2,
    "strike_offset": 2,
    "premium_stop_pct": -0.10,
    "tp1_premium_pct": 0.50,
    "tp1_qty_fraction": 0.5,
    "runner_target_pct": 2.0,
    "profit_lock_threshold_pct": 0.05,
    "profit_lock_stop_offset_pct": 0.05,
    "qty": 10,
    "proximity_dollars": 1.5,
    "require_break_above_open": True,
}

VIX_THRESHOLDS = [0, 14, 16, 18, 20, 22]   # 0 = no filter (baseline)


# ── Per-day real-fills runner ─────────────────────────────────────────────────


def _run_sniper_day_real_filtered(
    date_et: dt.date,
    spy_full: pd.DataFrame,
    combo_dict: dict,
    vix_prev_close: float,
    vix_threshold: float,
) -> list[dict]:
    """Run SNIPER on one day with VIX regime filter.

    Skips the day entirely if vix_prev_close < vix_threshold.
    Otherwise delegates to the per-day real-fills runner.
    """
    if vix_threshold > 0 and vix_prev_close < vix_threshold:
        return []

    from autoresearch.sniper_evaluator import SniperCombo
    from lib.ribbon import compute_ribbon
    from lib.simulator_real import simulate_trade_real
    from lib.sniper_detector import SniperParams, compute_levels, detect_sniper_break

    combo = SniperCombo(**{
        k: v for k, v in combo_dict.items()
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

    day_bars = spy_full[
        (spy_full["timestamp_et"].dt.date == date_et)
        & (spy_full["timestamp_et"].dt.time >= dt.time(9, 30))
        & (spy_full["timestamp_et"].dt.time < dt.time(16, 0))
    ].reset_index(drop=True)
    if day_bars.empty:
        return []

    first_ts = day_bars["timestamp_et"].iloc[0]
    levels = compute_levels(spy_full, first_ts, params)
    if not levels:
        return []

    pre_bars = spy_full[spy_full["timestamp_et"] < first_ts].tail(40).reset_index(drop=True)
    combined = pd.concat([pre_bars, day_bars], ignore_index=True)
    day_offset = len(pre_bars)
    ribbon_df = compute_ribbon(combined["close"]).reset_index(drop=True)

    out = []
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
            out.append({
                "date": date_et.isoformat(),
                "dollar_pnl": 0.0,
                "winner": False,
                "opra_missing": True,
                "vix_prev": round(vix_prev_close, 2),
            })
            break

        out.append({
            "date": date_et.isoformat(),
            "entry_time": bar["timestamp_et"].strftime("%H:%M"),
            "dollar_pnl": fill.dollar_pnl,
            "winner": fill.dollar_pnl > 0,
            "opra_missing": False,
            "vix_prev": round(vix_prev_close, 2),
        })
        break  # max 1 trade per day

    return out


# ── VIX lookup helper ─────────────────────────────────────────────────────────


def _build_vix_prev_close_map(
    vix_df: pd.DataFrame,
    trade_dates: list[dt.date],
) -> dict[dt.date, float]:
    """Return {trade_date: prior_day_vix_close} for all trade dates.

    Uses the last bar of each calendar day in vix_df as the close.
    """
    # Collect last VIX bar per date
    vix_dates: dict[dt.date, float] = {}
    for _, row in vix_df.iterrows():
        d = row["timestamp_et"].date() if hasattr(row["timestamp_et"], "date") else row["timestamp_et"].date()
        vix_dates[d] = float(row["close"])

    result: dict[dt.date, float] = {}
    sorted_vix_days = sorted(vix_dates.keys())

    for trade_date in trade_dates:
        # Find the last VIX day strictly before this trade date
        prior = [d for d in sorted_vix_days if d < trade_date]
        if prior:
            result[trade_date] = vix_dates[prior[-1]]
        else:
            result[trade_date] = 15.0  # fallback if no prior data
    return result


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    from autoresearch import runner as _runner
    import pytz

    print("SNIPER VIX regime filter calibration")
    print(f"Combo: strike_offset=2, stop=-10%, lock=5%/5%, tp1=50%, runner=2.0")
    print(f"Window: {WIDE_START} .. {WIDE_END}")
    print()

    t0 = time.perf_counter()
    print("Loading SPY + VIX data...", end=" ", flush=True)
    spy_full, vix_full = _runner.load_data(WIDE_START, WIDE_END)

    # Normalize timestamps
    if hasattr(spy_full.columns, "levels"):
        spy_full.columns = spy_full.columns.droplevel(1)
    for df in (spy_full, vix_full):
        # Force datetime parse before tz operations (avoids .dt accessor on object/str columns)
        df["timestamp_et"] = pd.to_datetime(df["timestamp_et"], utc=True)
        df["timestamp_et"] = df["timestamp_et"].dt.tz_convert(pytz.timezone("US/Eastern"))
    print(f"done ({time.perf_counter()-t0:.1f}s)")

    # Get all trade dates
    trade_dates = sorted(set(
        spy_full[spy_full["timestamp_et"].dt.date >= WIDE_START]["timestamp_et"].dt.date
    ))
    print(f"Trade dates: {len(trade_dates)}")

    # Build VIX prior-close map
    print("Building VIX prior-close map...", end=" ", flush=True)
    vix_map = _build_vix_prev_close_map(vix_full, trade_dates)
    vix_values = [vix_map.get(d, 15.0) for d in trade_dates]
    print(f"done. VIX range: {min(vix_values):.1f} - {max(vix_values):.1f}")
    print()

    results: list[dict] = []

    print(f"{'threshold':<12}  {'n_trades':>8}  {'wide_pnl':>10}  {'wr':>6}  {'+q':>6}  {'skipped':>7}")
    print("-" * 62)

    for threshold in VIX_THRESHOLDS:
        t_start = time.perf_counter()
        all_trades: list[dict] = []
        skipped_days = 0

        for date_et in trade_dates:
            vix_prev = vix_map.get(date_et, 15.0)
            trades = _run_sniper_day_real_filtered(
                date_et, spy_full, BEST_COMBO, vix_prev, threshold
            )
            if threshold > 0 and vix_prev < threshold:
                skipped_days += 1
                continue
            all_trades.extend(t for t in trades if not t.get("opra_missing", False))

        # Aggregate
        total_pnl = sum(t["dollar_pnl"] for t in all_trades)
        n_trades = len(all_trades)
        wr = sum(1 for t in all_trades if t.get("winner")) / n_trades if n_trades else 0

        quarter_pnl: dict[str, float] = defaultdict(float)
        for t in all_trades:
            d = dt.date.fromisoformat(t["date"])
            q = f"{d.year}-Q{(d.month - 1) // 3 + 1}"
            quarter_pnl[q] += t["dollar_pnl"]
        positive_q = sum(1 for v in quarter_pnl.values() if v > 0)
        total_q = len(quarter_pnl)

        elapsed = time.perf_counter() - t_start
        label = f"vix>={threshold}" if threshold > 0 else "no_filter"
        print(
            f"{label:<12}  {n_trades:>8}  ${total_pnl:>9.2f}  "
            f"{wr:>6.3f}  {positive_q:>3}/{total_q}  {skipped_days:>6}d"
            f"  ({elapsed:.1f}s)"
        )

        results.append({
            "threshold": threshold,
            "label": label,
            "n_trades": n_trades,
            "wide_pnl": round(total_pnl, 2),
            "wr": round(wr, 3),
            "positive_quarters": positive_q,
            "total_quarters": total_q,
            "skipped_days": skipped_days,
            "quarter_pnl": {k: round(v, 2) for k, v in sorted(quarter_pnl.items())},
        })

    # Quarter breakdown for each threshold
    print()
    print("=== Quarter breakdown by threshold ===")
    all_quarters = sorted(set(
        q for r in results for q in r["quarter_pnl"].keys()
    ))
    header = f"{'threshold':<12}" + "".join(f"  {q:>10}" for q in all_quarters)
    print(header)
    print("-" * len(header))
    for r in results:
        row = f"{r['label']:<12}"
        for q in all_quarters:
            v = r["quarter_pnl"].get(q, 0.0)
            row += f"  {v:>+10.0f}"
        print(row)

    # Save results
    OUT_JSON.write_text(json.dumps({
        "run_at": dt.datetime.now().isoformat(),
        "combo": BEST_COMBO,
        "window": {"start": WIDE_START.isoformat(), "end": WIDE_END.isoformat()},
        "thresholds": VIX_THRESHOLDS,
        "results": results,
    }, indent=2), encoding="utf-8")
    print(f"\nResults saved to {OUT_JSON}")

    # Recommendation
    print()
    best = max(results, key=lambda r: r["wide_pnl"])
    print(f"Best threshold: {best['label']}  wide_pnl=${best['wide_pnl']:,.0f}  "
          f"WR={best['wr']:.1%}  +q={best['positive_quarters']}/{best['total_quarters']}")
    if best["threshold"] == 0:
        print("NOTE: No regime filter beats baseline — SNIPER may not be salvageable via VIX alone.")
    else:
        print(f"GATE CHECK: pnl>${best['wide_pnl']:.0f} vs $2,000 gate: "
              f"{'PASS' if best['wide_pnl'] > 2000 else 'FAIL'}")
        print(f"            WR {best['wr']:.1%} vs 45% gate: "
              f"{'PASS' if best['wr'] >= 0.45 else 'FAIL'}")
        print(f"            +q {best['positive_quarters']}/{best['total_quarters']} vs 4/6 gate: "
              f"{'PASS' if best['positive_quarters'] >= 4 else 'FAIL'}")
    print()
    print("Done.")


if __name__ == "__main__":
    main()
