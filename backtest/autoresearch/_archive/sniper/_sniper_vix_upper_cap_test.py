"""SNIPER VIX upper-cap range test (18 <= VIX <= threshold).

MOTIVATION:
  The VIX>=18 grinder found the primary candidate has edge in high-VIX environments,
  but Q2-2026 (April-May tariff panic) is still -$1,274.  Q2-2026 VIX was very elevated
  (30-45 on some days), and those extreme-VIX days showed:
    1. Wider bid-ask spreads (option fill quality degrades)
    2. Violent intraday bounces (level breaks reverse aggressively)

  Hypothesis: filtering out EXTREME VIX days (VIX > 30 or VIX > 35) while keeping
  moderate-high VIX days (18-30 or 18-35) produces better P&L.

WHAT:
  Primary candidate: off=1, stp=-10%, tp1=30%, run=2.0, lk=5%/8%
  Tests: lower bound = 18 fixed, upper bound = {None, 30, 32, 35, 40}

  Output: comparison table showing pnl/WR/quarters per upper-cap threshold.

OUTPUT:
  Console table + autoresearch/_state/sniper_vix_upper_cap_results.json

CLI:
  python autoresearch/_sniper_vix_upper_cap_test.py
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

WIDE_START = dt.date(2025, 1, 1)
WIDE_END = dt.date(2026, 5, 22)

OUT_JSON = REPO / "autoresearch" / "_state" / "sniper_vix_upper_cap_results.json"

# Primary candidate from VIX18 grinder (best edge_capture, best drawdown)
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

VIX_LOWER = 18
VIX_UPPER_CAPS = [None, 40, 35, 32, 30]  # None = no upper cap (baseline)


def _build_vix_maps(vix_df: pd.DataFrame, trade_dates: list[dt.date]) -> dict[dt.date, float]:
    """Return {trade_date: prior_day_vix_close}."""
    import bisect
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


def _run_combo_with_cap(
    spy_full: pd.DataFrame,
    vix_prev_map: dict[dt.date, float],
    trade_dates: list[dt.date],
    combo_dict: dict,
    vix_lower: float,
    vix_upper: float | None,
) -> dict:
    """Run primary combo with VIX range filter: lower <= VIX < upper (if upper set)."""
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
    day_pnl_map: dict[dt.date, float] = defaultdict(float)
    quarter_pnl_map: dict[str, float] = defaultdict(float)
    skipped_low = 0
    skipped_high = 0

    for date_et in trade_dates:
        vix_prev = vix_prev_map.get(date_et, 15.0)
        if vix_prev < vix_lower:
            skipped_low += 1
            continue
        if vix_upper is not None and vix_prev >= vix_upper:
            skipped_high += 1
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
            continue

        pre_bars = spy_full[spy_full["timestamp_et"] < first_ts].tail(40).reset_index(drop=True)
        combined = pd.concat([pre_bars, day_bars], ignore_index=True)
        day_offset = len(pre_bars)
        ribbon_df = compute_ribbon(combined["close"]).reset_index(drop=True)

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

            trade_rec = {
                "date": date_et.isoformat(),
                "dollar_pnl": float(fill.dollar_pnl or 0.0),
                "vix_prev": round(vix_prev, 2),
            }
            all_trades.append(trade_rec)
            day_pnl_map[date_et] += trade_rec["dollar_pnl"]
            q = f"{date_et.year}-Q{(date_et.month - 1) // 3 + 1}"
            quarter_pnl_map[q] += trade_rec["dollar_pnl"]
            break  # one trade per day

    wide_pnl = round(sum(day_pnl_map.values()), 2)
    wide_n = len(all_trades)
    wide_winners = sum(1 for t in all_trades if t["dollar_pnl"] > 0)
    wide_wr = round(wide_winners / wide_n, 3) if wide_n else 0.0
    positive_quarters = sum(1 for v in quarter_pnl_map.values() if v > 0)
    quarter_count = len(quarter_pnl_map)

    cap_str = f"VIX {vix_lower}-{vix_upper}" if vix_upper else f"VIX >={vix_lower} (no cap)"
    return {
        "label": cap_str,
        "vix_lower": vix_lower,
        "vix_upper": vix_upper,
        "wide_pnl": wide_pnl,
        "wide_n_trades": wide_n,
        "wide_wr": wide_wr,
        "positive_quarters": positive_quarters,
        "quarter_count": quarter_count,
        "skipped_low": skipped_low,
        "skipped_high": skipped_high,
        "quarter_pnl": {k: round(v, 2) for k, v in sorted(quarter_pnl_map.items())},
    }


def main() -> None:
    from autoresearch import runner as _runner

    print("SNIPER VIX upper-cap range test")
    print(f"Combo: off=1, stp=-10%, tp1=30%, run=2.0, lk=5%/8%")
    print(f"Window: {WIDE_START} .. {WIDE_END}")
    print(f"Lower bound: VIX >= {VIX_LOWER} (fixed)")
    print(f"Upper caps tested: {VIX_UPPER_CAPS}")
    print()

    print("Loading SPY + VIX data...", end=" ", flush=True)
    spy_full, vix_full = _runner.load_data(WIDE_START, WIDE_END)
    import pytz
    for df in (spy_full, vix_full):
        df["timestamp_et"] = (
            pd.to_datetime(df["timestamp_et"], utc=True)
            .dt.tz_convert(pytz.timezone("US/Eastern"))
            .dt.tz_localize(None)
        )
    print("done")

    all_dates = sorted(set(spy_full["timestamp_et"].dt.date.unique()))
    trade_dates = [d for d in all_dates if WIDE_START <= d <= WIDE_END]
    vix_prev_map = _build_vix_maps(vix_full, trade_dates)
    print(f"Trade dates: {len(trade_dates)}")
    print()

    results = []
    print(f"{'label':<26}  {'n':>5}  {'pnl':>9}  {'wr':>6}  {'+q':>5}  {'skip-hi':>7}")
    print("-" * 65)

    for vix_upper in VIX_UPPER_CAPS:
        r = _run_combo_with_cap(spy_full, vix_prev_map, trade_dates, PRIMARY_COMBO, VIX_LOWER, vix_upper)
        results.append(r)
        print(
            f"{r['label']:<26}  {r['wide_n_trades']:>5}  "
            f"${r['wide_pnl']:>8,.0f}  {r['wide_wr']:>6.1%}  "
            f"{r['positive_quarters']:>2}/{r['quarter_count']:<2}  "
            f"{r['skipped_high']:>7}"
        )

    # Quarter breakdown
    print()
    print("Quarter breakdown by VIX cap:")
    all_quarters = sorted(set(q for r in results for q in r["quarter_pnl"].keys()))
    header = f"{'label':<26}" + "".join(f"  {q:>10}" for q in all_quarters)
    print(header)
    print("-" * len(header))
    for r in results:
        row = f"{r['label']:<26}"
        for q in all_quarters:
            v = r["quarter_pnl"].get(q, 0.0)
            row += f"  {v:>+10,.0f}"
        print(row)

    # Gate check
    print()
    print("Gate check (pnl>$2K, WR>=45%, +q>=4):")
    for r in results:
        gates = {
            "pnl": r["wide_pnl"] > 2000,
            "wr": r["wide_wr"] >= 0.45,
            "q": r["positive_quarters"] >= 4,
        }
        status = "PASS" if all(gates.values()) else f"FAIL ({[k for k,v in gates.items() if not v]})"
        print(f"  {r['label']:<26}: {status}  pnl=${r['wide_pnl']:,.0f}")

    # Save
    OUT_JSON.write_text(
        json.dumps({
            "run_at": dt.datetime.now().isoformat(),
            "combo": PRIMARY_COMBO,
            "vix_lower": VIX_LOWER,
            "upper_caps_tested": VIX_UPPER_CAPS,
            "window": {"start": WIDE_START.isoformat(), "end": WIDE_END.isoformat()},
            "results": results,
        }, indent=2),
        encoding="utf-8",
    )
    print(f"\nSaved to {OUT_JSON}")


if __name__ == "__main__":
    main()
