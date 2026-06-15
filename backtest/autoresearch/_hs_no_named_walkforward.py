"""H&S::no_named walk-forward investigation.

16-month data shows:
  near_named N=88,  WR=50.0% — coin flip (watcher flagged WATCH_FRAGILE)
  no_named   N=195, WR=55.4% — better without proximity filter

This script answers:
  1. Is the 55.4% WR stable across train/test split?
  2. Is the edge concentrated in a VIX regime?
  3. What time-of-day distribution do H&S signals have?

Methodology:
  - Train: 2025-01-02 → 2025-09-30 (first 9 months, ~188 trading days)
  - Test:  2025-10-01 → 2026-05-19 (last ~7 months, ~154 trading days)
  - Grading: next-5m-bar close direction (same as pattern_backtest.py)
  - No proximity filter for no_named — counts ALL H&S hits regardless of named level

Usage:
    cd C:\\Users\\jackw\\Desktop\\42
    python backtest/autoresearch/_hs_no_named_walkforward.py
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from datetime import date as Date, datetime, time, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT, ROOT / "backtest"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from crypto.lib.bar import Bar
from crypto.lib.chart_patterns import head_and_shoulders_detector, enrich_hit_with_proximity

# ── Config ────────────────────────────────────────────────────────────────────

SPY_CSV = ROOT / "backtest/data/spy_5m_2025-01-01_2026-05-19_merged.csv"
VIX_CSV = ROOT / "backtest/data/vix_5m_2025-01-01_2026-05-19_merged.csv"

TRAIN_END = Date(2025, 9, 30)   # inclusive train window end
TEST_START = Date(2025, 10, 1)  # inclusive test window start

WINDOW_BARS = 35   # H&S needs lookback=30; 35 gives 5-bar margin
LOOKBACK = 30
PROXIMITY_MAX = 0.50  # $0.50 for named-level proximity check

# Time gate: 09:40-13:30 ET (same as hs_near_named_level_watcher.py)
TIME_START = time(9, 40)
TIME_END = time(13, 30)

OUT_PATH = ROOT / "analysis/walk-forward-hs-no-named-2026-05-20.json"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_spy(csv_path: Path) -> dict[Date, list[Bar]]:
    """Load SPY 5m bars grouped by trading date (RTH only)."""
    by_date: dict[Date, list[Bar]] = defaultdict(list)
    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts_str = row["timestamp_et"]
            try:
                ts = datetime.fromisoformat(ts_str)
            except ValueError:
                continue
            d = ts.date()
            et_time = ts.time()
            if not (time(9, 30) <= et_time < time(16, 0)):
                continue
            by_date[d].append(Bar(
                open_time=ts.astimezone(timezone.utc),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
                granularity_seconds=300,
                source="csv",
            ))
    for d in by_date:
        by_date[d].sort(key=lambda b: b.open_time)
    return dict(by_date)


def _load_vix(csv_path: Path) -> dict[Date, list[tuple[time, float]]]:
    """Load VIX 5m closes grouped by trading date."""
    by_date: dict[Date, list[tuple[time, float]]] = defaultdict(list)
    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts_str = row["timestamp_et"]
            try:
                ts = datetime.fromisoformat(ts_str)
            except ValueError:
                continue
            d = ts.date()
            et_time = ts.time()
            if not (time(9, 30) <= et_time < time(16, 0)):
                continue
            close_col = next((k for k in row if k.lower() == "close"), None)
            if close_col is None:
                continue
            try:
                v = float(row[close_col])
            except ValueError:
                continue
            by_date[d].append((et_time, v))
    for d in by_date:
        by_date[d].sort(key=lambda x: x[0])
    return dict(by_date)


def _vix_at_bar(vix_day: list[tuple[time, float]], bar_time: time) -> float:
    """Return VIX close at or before bar_time (last available)."""
    val = 17.0
    for t, v in vix_day:
        if t <= bar_time:
            val = v
        else:
            break
    return val


def _derive_named_levels(prior_bars: list[Bar]) -> list[dict]:
    """Derive PDH/PDL named levels from prior-day bars (same as pattern_backtest.py)."""
    if not prior_bars:
        return []
    pdh = max(b.high for b in prior_bars)
    pdl = min(b.low for b in prior_bars)
    return [
        {"price": round(pdh, 2), "name": "PDH", "stars": 2},
        {"price": round(pdl, 2), "name": "PDL", "stars": 2},
    ]


def _vix_bucket(v: float) -> str:
    if v < 15:
        return "<15"
    elif v < 20:
        return "15-20"
    elif v < 25:
        return "20-25"
    else:
        return ">=25"


def _hour_bucket(t: time) -> str:
    if t < time(10, 0):
        return "09:30-09:59"
    elif t < time(11, 0):
        return "10:00-10:59"
    elif t < time(12, 0):
        return "11:00-11:59"
    elif t < time(13, 0):
        return "12:00-12:59"
    else:
        return "13:00-13:30"


# ── Main scan ─────────────────────────────────────────────────────────────────

def scan(spy_by_date: dict[Date, list[Bar]],
         vix_by_date: dict[Date, list[tuple[time, float]]]) -> list[dict]:
    """Walk all trading days, detect H&S, return per-signal rows."""
    sorted_dates = sorted(spy_by_date.keys())
    signals: list[dict] = []

    for day_idx, target_date in enumerate(sorted_dates):
        day_bars = spy_by_date[target_date]
        vix_day = vix_by_date.get(target_date, [])

        # Prior-day context: up to WINDOW_BARS from previous trading days
        prior_bars: list[Bar] = []
        j = day_idx - 1
        while j >= 0 and len(prior_bars) < WINDOW_BARS:
            prior_day = sorted_dates[j]
            prior_bars = spy_by_date[prior_day] + prior_bars
            j -= 1
        # Keep only the last WINDOW_BARS prior bars
        prior_bars = prior_bars[-WINDOW_BARS:]

        named_levels = _derive_named_levels(prior_bars)

        # Walk forward through today's bars
        full_bars = prior_bars + day_bars
        first_target_idx = len(prior_bars)

        for i in range(first_target_idx, len(full_bars)):
            bar = full_bars[i]
            # Time gate: 09:40-13:30 ET
            et_t = bar.open_time.astimezone(timezone(timedelta(hours=-4))).time()
            if et_t < TIME_START or et_t > TIME_END:
                continue

            # Minimum history for H&S detector
            window = full_bars[: i + 1]
            if len(window) < LOOKBACK:
                continue

            hit = head_and_shoulders_detector(window, lookback=LOOKBACK)
            if hit is None:
                continue
            # Only record hits that complete on THIS bar
            if hit.bar_index != i:
                continue
            if hit.bias != "bearish":
                continue

            # Grade: next bar direction
            if i + 1 >= len(full_bars):
                grade = "NEUTRAL"
            else:
                nc = full_bars[i + 1].close
                cc = full_bars[i].close
                grade = "WIN" if nc < cc else "LOSS"
            if grade == "NEUTRAL":
                continue

            # Proximity check: is neckline near named level?
            enriched = enrich_hit_with_proximity(hit, named_levels, max_distance=PROXIMITY_MAX)
            near_named = bool(enriched.notes.get("near_key_level"))

            vix = _vix_at_bar(vix_day, et_t)
            split = "train" if target_date <= TRAIN_END else "test"

            signals.append({
                "date": target_date.isoformat(),
                "time_et": et_t.strftime("%H:%M"),
                "near_named": near_named,
                "grade": grade,
                "vix": round(vix, 2),
                "confidence": float(hit.confidence),
                "split": split,
                "vix_bucket": _vix_bucket(vix),
                "hour_bucket": _hour_bucket(et_t),
            })

    return signals


def _stats(rows: list[dict]) -> dict:
    n = len(rows)
    wins = sum(1 for r in rows if r["grade"] == "WIN")
    return {"n": n, "wins": wins, "wr_pct": round(100 * wins / n, 1) if n else 0.0}


def main() -> None:
    print("Loading SPY CSV…")
    spy = _load_spy(SPY_CSV)
    print(f"  {len(spy)} trading days loaded")

    print("Loading VIX CSV…")
    vix = _load_vix(VIX_CSV)
    print(f"  {len(vix)} VIX days loaded")

    print("Scanning H&S patterns…")
    signals = scan(spy, vix)
    print(f"  {len(signals)} H&S bearish hits (after next-bar grading)")

    # ── Split into near_named vs no_named ────────────────────────────────────
    no_named = [s for s in signals if not s["near_named"]]
    near_named = [s for s in signals if s["near_named"]]

    print(f"\n=== H&S WALK-FORWARD RESULTS ===")
    print(f"All H&S (train+test):  {_stats(signals)}")
    print(f"near_named:            {_stats(near_named)}")
    print(f"no_named:              {_stats(no_named)}")

    # Train/test split for no_named
    nn_train = [s for s in no_named if s["split"] == "train"]
    nn_test  = [s for s in no_named if s["split"] == "test"]
    print(f"\nno_named train (Jan-Sep 2025): {_stats(nn_train)}")
    print(f"no_named test  (Oct 25-May 26): {_stats(nn_test)}")
    delta = _stats(nn_test)["wr_pct"] - _stats(nn_train)["wr_pct"]
    print(f"delta (test - train): {delta:+.1f}pp")
    if delta > -10:
        verdict = "STABLE" if abs(delta) < 10 else ("IMPROVED" if delta > 0 else "DEGRADED")
    else:
        verdict = "DEGRADED"
    print(f"Walk-forward verdict: {verdict}")

    # VIX stratification for no_named
    print("\n=== VIX STRATIFICATION (no_named) ===")
    vix_buckets: dict[str, list[dict]] = defaultdict(list)
    for s in no_named:
        vix_buckets[s["vix_bucket"]].append(s)
    for bucket in ["<15", "15-20", "20-25", ">=25"]:
        rows = vix_buckets.get(bucket, [])
        st = _stats(rows)
        print(f"  VIX {bucket}: N={st['n']} WR={st['wr_pct']}%")

    # Time-of-day for no_named
    print("\n=== TIME-OF-DAY (no_named) ===")
    tod: dict[str, list[dict]] = defaultdict(list)
    for s in no_named:
        tod[s["hour_bucket"]].append(s)
    for bucket in ["09:30-09:59", "10:00-10:59", "11:00-11:59", "12:00-12:59", "13:00-13:30"]:
        rows = tod.get(bucket, [])
        st = _stats(rows)
        print(f"  {bucket}: N={st['n']} WR={st['wr_pct']}%")

    # Confidence breakdown for no_named
    print("\n=== CONFIDENCE BREAKDOWN (no_named) ===")
    conf_buckets = {"low(0.3-0.5)": [], "mid(0.5-0.7)": [], "high(0.7+)": []}
    for s in no_named:
        c = s["confidence"]
        if c < 0.5:
            conf_buckets["low(0.3-0.5)"].append(s)
        elif c < 0.7:
            conf_buckets["mid(0.5-0.7)"].append(s)
        else:
            conf_buckets["high(0.7+)"].append(s)
    for label, rows in conf_buckets.items():
        st = _stats(rows)
        print(f"  {label}: N={st['n']} WR={st['wr_pct']}%")

    # ── Output JSON ─────────────────────────────────────────────────────────
    result = {
        "meta": {
            "run_date": datetime.now().isoformat(),
            "spy_csv": str(SPY_CSV),
            "train_window": f"2025-01-02 to {TRAIN_END.isoformat()}",
            "test_window": f"{TEST_START.isoformat()} to 2026-05-19",
            "time_gate": f"{TIME_START} to {TIME_END} ET",
            "proximity_max_distance": PROXIMITY_MAX,
        },
        "aggregate": {
            "all_hs": _stats(signals),
            "near_named": _stats(near_named),
            "no_named": _stats(no_named),
        },
        "walk_forward": {
            "no_named_train": _stats(nn_train),
            "no_named_test": _stats(nn_test),
            "delta_pp": round(delta, 1),
            "verdict": verdict,
        },
        "vix_stratification": {
            bucket: _stats(vix_buckets.get(bucket, []))
            for bucket in ["<15", "15-20", "20-25", ">=25"]
        },
        "time_of_day": {
            bucket: _stats(tod.get(bucket, []))
            for bucket in ["09:30-09:59", "10:00-10:59", "11:00-11:59", "12:00-12:59", "13:00-13:30"]
        },
        "confidence_breakdown": {
            label: _stats(rows)
            for label, rows in conf_buckets.items()
        },
        "signals": signals,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nOutput: {OUT_PATH}")

    # Walk-forward recommendation
    print("\n=== RECOMMENDATION ===")
    nn_test_stats = _stats(nn_test)
    nn_train_stats = _stats(nn_train)
    if nn_test_stats["n"] >= 30 and nn_test_stats["wr_pct"] >= 55.0 and abs(delta) <= 15:
        print("WATCH-STABLE: walk-forward holds. Build hs_watcher.py (no proximity gate).")
    elif nn_test_stats["n"] >= 15 and nn_test_stats["wr_pct"] >= 52.0:
        print("WATCH-MARGINAL: small test N or borderline WR. Build watcher but mark WATCH_FRAGILE.")
    else:
        print(f"NO_EDGE or DEGRADED: test WR={nn_test_stats['wr_pct']}% N={nn_test_stats['n']}. Do not build watcher.")
    print(f"  train: N={nn_train_stats['n']} WR={nn_train_stats['wr_pct']}%")
    print(f"  test:  N={nn_test_stats['n']} WR={nn_test_stats['wr_pct']}%")


if __name__ == "__main__":
    main()
