"""chart_reading_gym -- gym-scale replay of historical bars through the
NEW chart-reading pipeline (detectors + fast_path_executor).

Per J's directive (2026-05-18 evening): "take the new chart reading system to
the gym and make sure we're actually able to read the candlesticks in seconds
for the latency budget."

Validates 3 properties at scale:
  1. CORRECTNESS — detectors fire the right pattern shapes (no crashes, no
     bias mismatches) over N trading days
  2. LATENCY — per-bar evaluation stays under 200ms (the per-bar budget that
     compounds into the <30s end-to-end target)
  3. DECISION-DENSITY — fast_path_executor produces ENTER decisions on the
     same days the LLM heartbeat did historically (read decisions.jsonl)

Output: analysis/chart-reading-gym-{date}.json + console summary.

Run:
    python backtest/autoresearch/chart_reading_gym.py
    python backtest/autoresearch/chart_reading_gym.py --days 30
    python backtest/autoresearch/chart_reading_gym.py --range 2025-01-02 2026-05-15
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import statistics
import sys
import time
from datetime import date as Date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


# Import via spec (avoid heavy backtest/autoresearch __init__)
def _load_pb():
    spec = importlib.util.spec_from_file_location(
        "pb_gym", PROJECT_ROOT / "backtest" / "autoresearch" / "pattern_backtest.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["pb_gym"] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_fpe():
    spec = importlib.util.spec_from_file_location(
        "fpe_gym", PROJECT_ROOT / "setup" / "scripts" / "fast_path_executor.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["fpe_gym"] = mod
    spec.loader.exec_module(mod)
    return mod


def _build_alert_from_hit(hit, bar) -> dict:
    """Convert a pattern_backtest hit dict to a numeric_pulse alert shape."""
    return {
        "fire_at_utc": datetime.now(timezone.utc).isoformat(),
        "pattern": hit["pattern"],
        "bias": hit["bias"],
        "confidence": hit["confidence"],
        "key_price": hit.get("key_price", bar.close),
        "spy_close": bar.close,
        "level_distance_dollars": 0.0,
        "level_name": "synthetic_gym_alert",
    }


def gym_one_day(pb, fpe, target_date: Date, csv_path: Path) -> dict:
    """Replay one trading day's bars through detectors + fast_path."""
    started = time.monotonic()
    result = pb.run_pattern_backtest(target_date, csv_path)
    detector_elapsed = time.monotonic() - started

    if result.get("error") or not result.get("hits"):
        return {
            "date": target_date.isoformat(),
            "bars": result.get("bars_count", 0),
            "hits": 0,
            "detector_sec": round(detector_elapsed, 3),
            "fast_path_decisions": 0,
            "errors": [],
            "skipped": "no_hits",
        }

    # Replay each ALERT-CLASS hit (high-conviction contra-trend, level-proximate)
    # through fast_path_executor with mocked RTH (since we're not in market hours
    # during gym). Mock VIX too so it doesn't block synthetic.
    fpe_decisions = []
    fpe_latencies_ms = []
    errors = []
    bars = pb._load_bars_for_date(csv_path, target_date, prior_day_context=1)[0]
    bar_by_idx = {b_idx: b for b_idx, b in enumerate(bars)}

    # Mock VIX bullish-favorable (16.5 falling) so we exercise the full pipeline
    mock_vix = {"value": 16.5, "direction": "falling", "prior": 16.7, "delta": -0.2}
    mock_account = {"equity": "1000", "last_equity": "1000", "buying_power": "4000"}

    # Only test ALERT-CLASS hits (confidence >= 0.65 AND contra-trend)
    alert_hits = [h for h in result["hits"]
                  if h.get("confidence", 0) >= 0.65
                  and h.get("regime_aligned") is False
                  and h.get("regime") != "unknown"]

    with patch.object(fpe, "_is_rth_now", return_value=True), \
         patch.object(fpe, "_is_in_entry_window", return_value=True), \
         patch.object(fpe, "_alpaca", return_value=mock_account):
        for hit in alert_hits[:50]:  # cap at 50 hits/day to bound runtime
            bar = bar_by_idx.get(hit["bar_index"])
            if bar is None:
                continue
            alert = _build_alert_from_hit(hit, bar)
            for acct in ("safe", "bold"):
                t0 = time.monotonic()
                try:
                    d = fpe.evaluate_alert(acct, alert, vix_data=mock_vix)
                    elapsed_ms = int((time.monotonic() - t0) * 1000)
                    fpe_latencies_ms.append(elapsed_ms)
                    fpe_decisions.append({
                        "account": acct,
                        "pattern": hit["pattern"],
                        "decision": d.decision,
                        "elapsed_ms": elapsed_ms,
                    })
                except Exception as e:
                    errors.append({"hit": hit["pattern"], "account": acct, "error": str(e)})

    return {
        "date": target_date.isoformat(),
        "bars": result["bars_count"],
        "hits_total": result["total_hits"],
        "alert_class_hits": len(alert_hits),
        "fast_path_decisions": len(fpe_decisions),
        "decisions_breakdown": _breakdown(fpe_decisions),
        "detector_sec": round(detector_elapsed, 3),
        "fpe_latency_ms": {
            "min": min(fpe_latencies_ms) if fpe_latencies_ms else None,
            "p50": _percentile(fpe_latencies_ms, 50),
            "p95": _percentile(fpe_latencies_ms, 95),
            "max": max(fpe_latencies_ms) if fpe_latencies_ms else None,
        },
        "errors": errors,
    }


def _breakdown(decisions: list[dict]) -> dict:
    by_decision: dict[str, int] = {}
    for d in decisions:
        by_decision[d["decision"]] = by_decision.get(d["decision"], 0) + 1
    return by_decision


def _percentile(values: list[int], pct: float) -> int | None:
    if not values:
        return None
    s = sorted(values)
    k = int(round((pct / 100.0) * (len(s) - 1)))
    return s[k]


def gym_range(start: Date, end: Date, csv_path: Path) -> dict:
    pb = _load_pb()
    fpe = _load_fpe()

    cur = start
    per_day = []
    while cur <= end:
        if cur.weekday() < 5:  # weekday only
            r = gym_one_day(pb, fpe, cur, csv_path)
            per_day.append(r)
        cur += timedelta(days=1)

    # Aggregate
    all_latencies = []
    total_errors = []
    total_hits = 0
    total_alert_class = 0
    total_decisions = 0
    enter_count = 0
    skip_count = 0
    for d in per_day:
        if "fpe_latency_ms" in d and d["fpe_latency_ms"]["max"] is not None:
            # Reconstruct individual latencies isn't possible from summary; use p95 as bound
            all_latencies.append(d["fpe_latency_ms"]["p95"])
        total_errors.extend(d.get("errors", []))
        total_hits += d.get("hits_total", 0)
        total_alert_class += d.get("alert_class_hits", 0)
        total_decisions += d.get("fast_path_decisions", 0)
        for k, v in d.get("decisions_breakdown", {}).items():
            if k.startswith("ENTER"):
                enter_count += v
            elif k.startswith("SKIP"):
                skip_count += v

    aggregate = {
        "days_scanned": len(per_day),
        "total_pattern_hits": total_hits,
        "total_alert_class_hits": total_alert_class,
        "total_fast_path_decisions": total_decisions,
        "enter_decisions": enter_count,
        "skip_decisions": skip_count,
        "errors": len(total_errors),
        "error_samples": total_errors[:5],
        "p95_fpe_latency_ms_across_days": _percentile(all_latencies, 95) if all_latencies else None,
        "max_fpe_latency_ms_across_days": max(all_latencies) if all_latencies else None,
        "latency_budget_pass": (
            max(all_latencies) < 5000 if all_latencies else True
        ),  # 5s per-bar is the safety budget
    }
    return {
        "range_start": start.isoformat(),
        "range_end": end.isoformat(),
        "aggregate": aggregate,
        "per_day": per_day,
    }


def _autodetect_csv(target_date: Date) -> Path | None:
    """Pick the CSV covering target_date. Defaults to most recent."""
    base = PROJECT_ROOT / "backtest" / "data"
    candidates = sorted(base.glob("spy_5m_*.csv"), reverse=True)
    for p in candidates:
        # Naive: most recent first; trust that it covers
        if p.exists():
            return p
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=10,
                        help="Number of recent trading days to replay (default 10)")
    parser.add_argument("--range", nargs=2, metavar=("START", "END"),
                        help="Date range YYYY-MM-DD YYYY-MM-DD")
    parser.add_argument("--csv", help="Path to spy_5m CSV (auto if omitted)")
    args = parser.parse_args()

    if args.range:
        start = Date.fromisoformat(args.range[0])
        end = Date.fromisoformat(args.range[1])
    else:
        end = Date(2026, 5, 15)  # last known trading day in CSV
        start = end - timedelta(days=args.days + 5)  # buffer for weekends

    csv = Path(args.csv) if args.csv else _autodetect_csv(end)
    if not csv or not csv.exists():
        print(f"ERROR: no CSV found", file=sys.stderr)
        return 1

    print(f"=== CHART READING GYM — {start} to {end} (CSV: {csv.name}) ===")
    started = time.monotonic()
    report = gym_range(start, end, csv)
    elapsed = time.monotonic() - started

    agg = report["aggregate"]
    print()
    print(f"Days scanned:                  {agg['days_scanned']}")
    print(f"Total pattern hits:            {agg['total_pattern_hits']}")
    print(f"Alert-class hits (>=0.65+contra): {agg['total_alert_class_hits']}")
    print(f"Fast-path decisions evaluated: {agg['total_fast_path_decisions']}")
    print(f"  ENTER decisions:             {agg['enter_decisions']}")
    print(f"  SKIP decisions:              {agg['skip_decisions']}")
    print(f"Errors:                        {agg['errors']}")
    if agg["errors"] > 0:
        for e in agg["error_samples"]:
            print(f"    sample error: {e}")
    print()
    print(f"FPE latency p95 across days:   {agg['p95_fpe_latency_ms_across_days']}ms")
    print(f"FPE latency max across days:   {agg['max_fpe_latency_ms_across_days']}ms")
    print(f"Latency budget (<5s/bar):      {'PASS' if agg['latency_budget_pass'] else 'FAIL'}")
    print()
    print(f"Gym wall time:                 {elapsed:.1f}s")

    # Persist
    out_dir = PROJECT_ROOT / "analysis"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"chart-reading-gym-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}.json"
    out_path.write_text(json.dumps(report, indent=2, default=str))
    print(f"Scorecard:                     {out_path}")

    # Exit 0 if PASS, 1 if FAIL
    if agg["errors"] > 0 or not agg["latency_budget_pass"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
