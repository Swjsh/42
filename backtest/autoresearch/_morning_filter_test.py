"""Test morning-only SNIPER filter vs all-day.

Hypothesis: Restricting SNIPER entries to before 11:00 ET removes afternoon
false breakouts and improves WR + wide_pnl.

Tests the best current combo (strike_offset=2, premium_stop=-0.10, profit_lock=0.05)
across three no_trade_after windows: 10:30, 11:00, 12:00, 15:50 (all-day baseline).
"""
import datetime as dt
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from collections import defaultdict

WIDE_START = dt.date(2025, 1, 1)
WIDE_END = dt.date(2026, 5, 22)

# Best combo from the real-fills keepers
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

NO_TRADE_AFTER_TIMES = [
    dt.time(10, 30),
    dt.time(11, 0),
    dt.time(12, 0),
    dt.time(15, 50),  # baseline (all-day)
]


def _run_sniper_day_real_filtered(date_et, spy_full, combo_dict, no_trade_after):
    """Run SNIPER on one day with specified no_trade_after cutoff."""
    from autoresearch.sniper_evaluator import SniperCombo
    from lib.option_pricing_real import option_symbol
    from lib.ribbon import compute_ribbon
    from lib.simulator_real import simulate_trade_real
    from lib.sniper_detector import SniperParams, compute_levels, detect_sniper_break
    import pandas as pd

    combo = SniperCombo(**{k: combo_dict[k] for k in combo_dict if k in SniperCombo.__dataclass_fields__})
    params = SniperParams(
        vol_mult=combo.vol_mult,
        body_min_cents=combo.body_min_cents,
        min_stars=combo.min_stars,
        proximity_dollars=combo.proximity_dollars,
        no_trade_before=dt.time(9, 30),
        no_trade_after=no_trade_after,
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

        side = "P"
        entry_spot = float(signal.entry_price)
        strike = round(entry_spot) + combo.strike_offset

        fill = simulate_trade_real(
            entry_bar_idx=bar_idx,
            entry_bar=bar,
            spy_df=combined,
            ribbon_df=ribbon_df,
            rejection_level=signal.level.price,
            triggers_fired=["sniper_level_break"],
            side=side,
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
            out.append({"date": date_et.isoformat(), "dollar_pnl": 0.0, "opra_missing": True})
            break
        entry_time = bar["timestamp_et"]
        out.append({
            "date": date_et.isoformat(),
            "entry_time": entry_time.strftime("%H:%M"),
            "dollar_pnl": fill.dollar_pnl,
            "winner": fill.dollar_pnl > 0,
            "opra_missing": False,
        })
        break  # max 1 trade per day
    return out


def run_sweep(no_trade_after):
    from autoresearch.sniper_real_fills_grinder import _run_sniper_day_real  # noqa
    import pandas as pd
    import numpy as np

    # Load data once — data starts 2025-01-01; no pre-2025 CSV available
    _start = dt.date(2025, 1, 1)
    spy_full, _ = __import__("autoresearch.runner", fromlist=["runner"]).load_data(_start, WIDE_END)
    if hasattr(spy_full, "columns") and isinstance(spy_full.columns, pd.MultiIndex):
        spy_full.columns = spy_full.columns.droplevel(1)
    if spy_full["timestamp_et"].dt.tz is None:
        import pytz
        spy_full["timestamp_et"] = spy_full["timestamp_et"].dt.tz_localize(pytz.timezone("US/Eastern"))
    else:
        import pytz
        spy_full["timestamp_et"] = spy_full["timestamp_et"].dt.tz_convert(pytz.timezone("US/Eastern"))

    all_trades = []
    trade_dates = sorted(set(spy_full[spy_full["timestamp_et"].dt.date >= WIDE_START]["timestamp_et"].dt.date))

    for date_et in trade_dates:
        trades = _run_sniper_day_real_filtered(date_et, spy_full, BEST_COMBO, no_trade_after)
        all_trades.extend([t for t in trades if not t.get("opra_missing", False)])

    if not all_trades:
        return {"n_trades": 0, "wide_pnl": 0.0, "wr": 0.0}

    total_pnl = sum(t["dollar_pnl"] for t in all_trades)
    n_trades = len(all_trades)
    wr = sum(1 for t in all_trades if t.get("winner")) / n_trades if n_trades else 0

    # Quarter breakdown
    quarter_pnl = defaultdict(float)
    for t in all_trades:
        d = dt.date.fromisoformat(t["date"])
        q = f"{d.year}-Q{(d.month - 1) // 3 + 1}"
        quarter_pnl[q] += t["dollar_pnl"]
    positive_quarters = sum(1 for v in quarter_pnl.values() if v > 0)

    return {
        "n_trades": n_trades,
        "wide_pnl": round(total_pnl, 2),
        "wr": round(wr, 3),
        "positive_quarters": positive_quarters,
        "quarter_pnl": {k: round(v, 2) for k, v in sorted(quarter_pnl.items())},
    }


if __name__ == "__main__":
    print("SNIPER morning-filter calibration")
    print(f"Combo: strike_offset=2, stop=-10%, lock=5%/5%, tp1=50%, runner=2.0")
    print(f"Window: {WIDE_START} .. {WIDE_END}")
    print()
    print(f"{'no_trade_after':<16}  {'n_trades':>8}  {'wide_pnl':>10}  {'wr':>6}  {'+q':>4}")
    print("-" * 55)

    from autoresearch import runner as _runner
    _start = dt.date(2025, 1, 1)  # data starts 2025-01-01; no pre-2025 CSV
    print("Loading SPY data...", end=" ", flush=True)
    t0 = time.perf_counter()
    spy_full, _ = _runner.load_data(_start, WIDE_END)
    import pandas as pd
    if hasattr(spy_full, "columns") and isinstance(spy_full.columns, pd.MultiIndex):
        spy_full.columns = spy_full.columns.droplevel(1)
    if "timestamp_et" in spy_full.columns:
        import pytz
        spy_full["timestamp_et"] = pd.to_datetime(spy_full["timestamp_et"], utc=True)
        spy_full["timestamp_et"] = spy_full["timestamp_et"].dt.tz_convert(pytz.timezone("US/Eastern"))
    print(f"done ({time.perf_counter()-t0:.1f}s)")

    from autoresearch.sniper_real_fills_grinder import _run_sniper_day_real as _dummy
    trade_dates = sorted(set(spy_full[spy_full["timestamp_et"].dt.date >= WIDE_START]["timestamp_et"].dt.date))

    for no_trade_after in NO_TRADE_AFTER_TIMES:
        t0 = time.perf_counter()
        all_trades = []
        for date_et in trade_dates:
            trades = _run_sniper_day_real_filtered(date_et, spy_full, BEST_COMBO, no_trade_after)
            all_trades.extend([t for t in trades if not t.get("opra_missing", False)])

        total_pnl = sum(t["dollar_pnl"] for t in all_trades)
        n_trades = len(all_trades)
        wr = sum(1 for t in all_trades if t.get("winner")) / n_trades if n_trades else 0

        quarter_pnl = defaultdict(float)
        for t in all_trades:
            d = dt.date.fromisoformat(t["date"])
            q = f"{d.year}-Q{(d.month - 1) // 3 + 1}"
            quarter_pnl[q] += t["dollar_pnl"]
        positive_q = sum(1 for v in quarter_pnl.values() if v > 0)

        elapsed = time.perf_counter() - t0
        label = f"before {no_trade_after.strftime('%H:%M')}"
        print(f"{label:<16}  {n_trades:>8}  ${total_pnl:>9.2f}  {wr:>6.3f}  {positive_q:>4}/{len(quarter_pnl)}")

    print()
    print("Done.")
