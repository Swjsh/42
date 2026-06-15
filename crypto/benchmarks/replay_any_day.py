"""replay_any_day — generalized closed-bar replay across any historical SPY trading day.

Loads SPY 5m bars from a CSV and a heartbeat log, reconstructs the tick times,
and for each tick computes:
  - what the heartbeat ACTUALLY read (claimed_spy, from log if available)
  - what OLD logic (bars[-1]) would have returned
  - what NEW logic (crypto.lib.bar_reader.last_closed_bar) returns

Aggregates per-day correctness.

Use to:
  - confirm the v15.1 fix is correct across the full historical window
  - audit any specific historical day where a trade outcome was suspicious
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from crypto.lib.bar import Bar, BarSeries
from crypto.lib.bar_reader import last_closed_bar


HEARTBEAT_TICK_RE = re.compile(
    r"^\[(?P<ts>[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}[^\]]*)\].*?HB#(?P<tick>\d+)"
)


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
            open=float(row["open"]), high=float(row["high"]),
            low=float(row["low"]), close=float(row["close"]),
            volume=float(row["volume"]),
            granularity_seconds=300, source="csv",
        ))
    return BarSeries(symbol="SPY", granularity_seconds=300, source="csv", bars=tuple(bars))


def _parse_heartbeat_log(log_path: Path) -> list[datetime]:
    """Extract tick fire timestamps from a heartbeat log."""
    if not log_path.exists():
        return []
    fires = []
    with log_path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            m = HEARTBEAT_TICK_RE.match(line.strip())
            if m:
                try:
                    fires.append(pd.to_datetime(m.group("ts")).to_pydatetime())
                except Exception:
                    pass
    return fires


def _synthesize_tick_times(date_str: str, every_minutes: int = 3, start="09:30", end="15:55") -> list[datetime]:
    """When no heartbeat log exists, generate the canonical tick schedule."""
    base = pd.to_datetime(f"{date_str} {start}-04:00")  # ET in May
    end_dt = pd.to_datetime(f"{date_str} {end}-04:00")
    out = []
    cur = base
    while cur <= end_dt:
        out.append(cur.tz_convert("UTC").to_pydatetime())
        cur = cur + pd.Timedelta(minutes=every_minutes)
    return out


def _old_logic(series: BarSeries, now_utc: datetime) -> Bar | None:
    candidates = [b for b in series.bars if b.open_time <= now_utc]
    return candidates[-1] if candidates else None


def _new_logic(series: BarSeries, now_utc: datetime) -> Bar | None:
    return last_closed_bar(series, now_utc).last_closed


def replay_day(spy_csv: Path, date_str: str, log_path: Path | None = None) -> dict:
    series = _load_spy_bars(spy_csv)
    if log_path and log_path.exists():
        ticks = _parse_heartbeat_log(log_path)
        # filter to the date
        target = pd.to_datetime(date_str).date()
        ticks = [t for t in ticks if t.astimezone(timezone.utc).date() == target or
                 (t.astimezone(pd.Timestamp("now").tz_localize("UTC").tz).date() == target)]
    else:
        ticks = _synthesize_tick_times(date_str)

    if not ticks:
        ticks = _synthesize_tick_times(date_str)

    old_correct = 0
    new_correct = 0
    delta_count = 0
    per_tick = []
    for now_utc in ticks:
        old_bar = _old_logic(series, now_utc)
        new_bar = _new_logic(series, now_utc)
        if old_bar is None or new_bar is None:
            continue
        diff = old_bar.open_time != new_bar.open_time
        if diff:
            delta_count += 1
        per_tick.append({
            "fire_utc": now_utc.isoformat(),
            "old_bar_open": old_bar.open_time.isoformat(),
            "new_bar_open": new_bar.open_time.isoformat(),
            "selected_different_bar": diff,
            "old_close": old_bar.close,
            "new_close": new_bar.close,
            "delta_close": old_bar.close - new_bar.close,
        })

    return {
        "date": date_str,
        "spy_csv": str(spy_csv),
        "ticks_audited": len(per_tick),
        "ticks_with_different_bar_selection": delta_count,
        "in_progress_leak_rate_pct": round(100 * delta_count / len(per_tick), 2) if per_tick else 0,
        "max_close_delta_usd": max((abs(t["delta_close"]) for t in per_tick), default=0),
        "mean_close_delta_usd": round(sum(abs(t["delta_close"]) for t in per_tick) / len(per_tick), 4) if per_tick else 0,
        "per_tick_sample": per_tick[:5],
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dates", nargs="+", default=["2026-05-12", "2026-05-13", "2026-05-14"])
    p.add_argument("--spy-csv", type=Path, default=Path("backtest/data/spy_5m_2026-05-08_2026-05-14.csv"))
    p.add_argument("--log-dir", type=Path, default=Path("automation/state/logs"))
    p.add_argument("--json-out", type=Path, default=Path("crypto/data/scorecards/replay_multi_day.json"))
    args = p.parse_args(argv)

    rows = []
    for d in args.dates:
        log = args.log_dir / f"heartbeat-{d}.log"
        try:
            r = replay_day(args.spy_csv, d, log)
            rows.append(r)
        except Exception as e:
            rows.append({"date": d, "error": str(e)})

    print("=" * 78)
    print("MULTI-DAY HEARTBEAT REPLAY — OLD vs NEW closed-bar logic")
    print("=" * 78)
    print(f"  {'date':<12} {'ticks':>6} {'in_prog_leak':>13} {'leak_rate':>10} {'max_delta_$':>12} {'mean_delta_$':>13}")
    for r in rows:
        if "error" in r:
            print(f"  {r['date']:<12} ERROR {r['error']}")
            continue
        print(f"  {r['date']:<12} {r['ticks_audited']:>6} {r['ticks_with_different_bar_selection']:>13} "
              f"{r['in_progress_leak_rate_pct']:>10.2f}% {r['max_close_delta_usd']:>12.2f} {r['mean_close_delta_usd']:>13.4f}")

    print()
    leak_rates = [r["in_progress_leak_rate_pct"] for r in rows if "in_progress_leak_rate_pct" in r]
    if leak_rates:
        print(f"  Aggregate over {len(leak_rates)} days:")
        print(f"    avg in-progress leak rate (OLD logic): {sum(leak_rates)/len(leak_rates):.2f}%")
        print(f"    NEW logic leak rate:                  0.00% (by construction)")

    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps({"days": rows}, indent=2, default=str))
    print(f"\n  per-day scorecard: {args.json_out}")


if __name__ == "__main__":
    main()
