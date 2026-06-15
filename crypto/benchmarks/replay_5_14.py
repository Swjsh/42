"""replay_5_14 — replay 2026-05-14 SPY heartbeat ticks with OLD vs NEW bar-reading logic.

THE HEADLINE BENCHMARK. Quantifies the gain from the crypto/lib/bar_reader.py
closed-bar primitive against the production foot-gun that bit 5/46 live ticks
on 2026-05-14 (OP 25 / L34 / R4).

Inputs:
  backtest/data/spy_5m_2026-05-08_2026-05-14.csv     # the actual SPY bars
  automation/state/r4-tick-divergence-2026-05-14.csv # the per-tick audit

For each live-trading tick (ALIGNED / MISALIGNED-BENIGN / MISALIGNED-CRITICAL):
  1. OLD logic: read TV-equivalent `bars[-1]` (which is the in-progress bar)
  2. NEW logic: apply crypto.lib.bar_reader.last_closed_bar(now=fire_at)
  3. Compare both against the ground-truth closed-bar open time

Outputs:
  crypto/data/scorecards/replay_5_14.json — per-tick + aggregate summary
  Console table summarizing OLD vs NEW correctness rates
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from crypto.lib.bar import Bar, BarSeries
from crypto.lib.bar_reader import last_closed_bar

ET = "America/New_York"


def _load_spy_bars(csv_path: Path) -> BarSeries:
    df = pd.read_csv(csv_path)
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"])
    df = df.sort_values("timestamp_et").reset_index(drop=True)
    bars = []
    for _, row in df.iterrows():
        ts_et = row["timestamp_et"]
        ts_utc = ts_et.tz_convert("UTC") if ts_et.tzinfo is not None else ts_et.tz_localize("UTC")
        bars.append(Bar(
            open_time=ts_utc.to_pydatetime(),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row["volume"]),
            granularity_seconds=300,
            source="spy_5m_csv",
        ))
    return BarSeries(symbol="SPY", granularity_seconds=300, source="spy_5m_csv", bars=tuple(bars))


def _old_logic_select(series: BarSeries, now_utc: datetime) -> Bar | None:
    """OLD heartbeat behavior: take whatever bar is at `bars[-1]` whose open <= now.

    This emulates the pre-v15.1 prompt that trusted TV's bars[-1] as 'just-closed'
    without computing close_time. The in-progress bar leaks in.
    """
    candidates = [b for b in series.bars if b.open_time <= now_utc]
    return candidates[-1] if candidates else None


def _new_logic_select(series: BarSeries, now_utc: datetime) -> Bar | None:
    return last_closed_bar(series, now_utc).last_closed


def replay(spy_csv: Path, r4_csv: Path) -> dict:
    series = _load_spy_bars(spy_csv)
    df = pd.read_csv(r4_csv)

    per_tick = []
    counts_old = {"correct": 0, "in_progress_leak": 0, "stale": 0, "no_data": 0}
    counts_new = {"correct": 0, "in_progress_leak": 0, "stale": 0, "no_data": 0}

    # The R4 CSV already classified ticks; we use its ground truth
    live_trading = df[df["classification"].isin(["ALIGNED", "MISALIGNED-BENIGN", "MISALIGNED-CRITICAL"])]

    for _, row in live_trading.iterrows():
        # fire_at is HH:MM:SS ET on 2026-05-14
        fire_str = f"2026-05-14 {row['fire_at']}-04:00"  # ET is UTC-4 in May
        fire_et = pd.to_datetime(fire_str)
        fire_utc = fire_et.tz_convert("UTC").to_pydatetime()

        # ground truth: per-tick row says what the correct closed bar's open was
        gt_open_et_str = row.get("last_closed_bar_open", None)
        if pd.isna(gt_open_et_str) or gt_open_et_str is None:
            continue

        old_bar = _old_logic_select(series, fire_utc)
        new_bar = _new_logic_select(series, fire_utc)

        gt_open_et = pd.to_datetime(f"2026-05-14 {gt_open_et_str}:00-04:00").tz_convert("UTC")

        old_correct = old_bar is not None and old_bar.open_time == gt_open_et.to_pydatetime()
        new_correct = new_bar is not None and new_bar.open_time == gt_open_et.to_pydatetime()

        # OHLC delta for the OLD-selected bar vs ground truth (quantifies foot-gun cost)
        old_close = old_bar.close if old_bar else None
        new_close = new_bar.close if new_bar else None
        # Find the ground-truth closed bar to compare prices
        gt_bar = next((b for b in series.bars if b.open_time == gt_open_et.to_pydatetime()), None)
        gt_close = gt_bar.close if gt_bar else None

        per_tick.append({
            "tick_id": int(row["tick_id"]),
            "fire_at_et": row["fire_at"],
            "decision": row["decision"],
            "classification_r4": row["classification"],
            "ground_truth_bar_open_et": gt_open_et_str,
            "ground_truth_close": gt_close,
            "old_logic_bar_open": old_bar.open_time.isoformat() if old_bar else None,
            "old_logic_close": old_close,
            "old_logic_correct": old_correct,
            "new_logic_bar_open": new_bar.open_time.isoformat() if new_bar else None,
            "new_logic_close": new_close,
            "new_logic_correct": new_correct,
            "old_close_delta_vs_gt": (old_close - gt_close) if (old_close is not None and gt_close is not None) else None,
            "new_close_delta_vs_gt": (new_close - gt_close) if (new_close is not None and gt_close is not None) else None,
        })

        if old_correct:
            counts_old["correct"] += 1
        else:
            counts_old["in_progress_leak"] += 1
        if new_correct:
            counts_new["correct"] += 1
        else:
            counts_new["in_progress_leak"] += 1

    total = len(per_tick)
    old_err = counts_old["in_progress_leak"]
    new_err = counts_new["in_progress_leak"]

    # critical-decision ticks for headline
    crit = [t for t in per_tick if t["classification_r4"] == "MISALIGNED-CRITICAL"]
    old_crit_caught = sum(1 for t in crit if not t["old_logic_correct"])
    new_crit_caught = sum(1 for t in crit if not t["new_logic_correct"])

    return {
        "date": "2026-05-14",
        "total_live_trading_ticks": total,
        "OLD_logic": {
            "correct": counts_old["correct"],
            "in_progress_leak": counts_old["in_progress_leak"],
            "error_rate_pct": round(100 * old_err / total, 2) if total else 0,
        },
        "NEW_logic_crypto_bar_reader": {
            "correct": counts_new["correct"],
            "in_progress_leak": counts_new["in_progress_leak"],
            "error_rate_pct": round(100 * new_err / total, 2) if total else 0,
        },
        "critical_decisions_misread_by_old": old_crit_caught,
        "critical_decisions_misread_by_new": new_crit_caught,
        "improvement_multiplier": (old_err / new_err) if new_err > 0 else "INF (NEW logic 0 errors)",
        "per_tick": per_tick,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--spy-csv", type=Path, default=Path("backtest/data/spy_5m_2026-05-08_2026-05-14.csv"))
    p.add_argument("--r4-csv", type=Path, default=Path("automation/state/r4-tick-divergence-2026-05-14.csv"))
    p.add_argument("--json-out", type=Path, default=Path("crypto/data/scorecards/replay_5_14.json"))
    args = p.parse_args(argv)

    sc = replay(args.spy_csv, args.r4_csv)

    print("=" * 70)
    print(f"5/14 HEARTBEAT REPLAY — OLD vs NEW closed-bar logic")
    print("=" * 70)
    print(f"  live-trading ticks audited: {sc['total_live_trading_ticks']}")
    print()
    print(f"  OLD logic (bars[-1] without close-time filter — pre-v15.1):")
    print(f"    correct:        {sc['OLD_logic']['correct']}")
    print(f"    in-progress leak: {sc['OLD_logic']['in_progress_leak']}")
    print(f"    error rate:     {sc['OLD_logic']['error_rate_pct']}%")
    print()
    print(f"  NEW logic (crypto.lib.bar_reader.last_closed_bar — v15.1+):")
    print(f"    correct:        {sc['NEW_logic_crypto_bar_reader']['correct']}")
    print(f"    in-progress leak: {sc['NEW_logic_crypto_bar_reader']['in_progress_leak']}")
    print(f"    error rate:     {sc['NEW_logic_crypto_bar_reader']['error_rate_pct']}%")
    print()
    print(f"  Critical-decision ticks misread (5 expected from R4 analysis):")
    print(f"    by OLD:   {sc['critical_decisions_misread_by_old']}")
    print(f"    by NEW:   {sc['critical_decisions_misread_by_new']}")
    print()
    print(f"  Improvement multiplier: {sc['improvement_multiplier']}")

    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(sc, indent=2, default=str))
    print(f"\nfull per-tick scorecard: {args.json_out}")
    print("=" * 70)

    return 0 if sc["NEW_logic_crypto_bar_reader"]["in_progress_leak"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
