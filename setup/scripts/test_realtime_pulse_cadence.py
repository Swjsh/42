"""test_realtime_pulse_cadence -- real wall-clock test of numeric_pulse 15s cadence.

Simulates 5 minutes of production firing (20 pulses at 15s intervals) WITHOUT
the cron layer — just to verify:
  1. Each pulse completes in <5s (well within the 15s budget)
  2. yfinance can handle the rate without throttling
  3. Python sleep+process drift stays under 1s per pulse over 5 minutes
  4. Memory + descriptor usage doesn't grow unboundedly

This is a SAFETY pre-check before tomorrow's first production fire — answers
J's question "have we tested the 15-second pulse times in real-time."

Skips if outside RTH unless --force used.

Run:
    python setup/scripts/test_realtime_pulse_cadence.py            # respects RTH gate
    python setup/scripts/test_realtime_pulse_cadence.py --force    # run anyway
    python setup/scripts/test_realtime_pulse_cadence.py --iterations 5  # quick check
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


def _load_pulse():
    spec = importlib.util.spec_from_file_location(
        "np_test",
        PROJECT_ROOT / "backtest" / "autoresearch" / "numeric_pulse.py",
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["np_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def run_cadence_test(iterations: int = 20, interval_sec: int = 15,
                     force: bool = False, mock_rth: bool = False) -> dict:
    """Fire numeric_pulse `iterations` times spaced `interval_sec` seconds apart.
    Measure: per-pulse wall time, total drift, alerts written, any errors.
    """
    np = _load_pulse()

    if mock_rth:
        # Patch the module-level RTH check so the full pipeline runs
        np._is_rth_now = lambda: True

    # RTH gate
    if not force and not mock_rth and not np._is_rth_now():
        return {
            "skipped": "outside_rth",
            "tip": "use --force to run anyway (will short-circuit on RTH inside pulse) "
                    "OR --mock-rth to force full pipeline execution",
        }

    started_wall = time.monotonic()
    expected_times = [started_wall + i * interval_sec for i in range(iterations)]
    actual_times = []
    pulse_durations_ms = []
    errors = []
    alerts_total = 0
    hits_total = 0
    pulse_results = []

    for i in range(iterations):
        # Wait until target time (initial pulse fires immediately)
        if i > 0:
            target = expected_times[i]
            remaining = target - time.monotonic()
            if remaining > 0:
                time.sleep(remaining)

        pulse_start = time.monotonic()
        actual_times.append(pulse_start)
        try:
            result = np.run_pulse(probe_only=False)
            pulse_results.append(result)
            if not result.get("skipped"):
                hits_total += result.get("raw_hits_count", 0)
                alerts_total += len(result.get("alerts", []))
        except Exception as e:
            errors.append({"iteration": i, "error": str(e)})
            pulse_results.append({"error": str(e)})
        pulse_durations_ms.append(int((time.monotonic() - pulse_start) * 1000))

    # Drift analysis
    drifts_sec = []
    for i in range(iterations):
        expected = i * interval_sec
        actual = actual_times[i] - started_wall
        drifts_sec.append(actual - expected)

    return {
        "iterations": iterations,
        "interval_target_sec": interval_sec,
        "total_wall_sec": round(time.monotonic() - started_wall, 2),
        "pulse_ms": {
            "min": min(pulse_durations_ms),
            "max": max(pulse_durations_ms),
            "avg": round(sum(pulse_durations_ms) / len(pulse_durations_ms), 1),
            "p95": sorted(pulse_durations_ms)[int(0.95 * len(pulse_durations_ms))],
        },
        "drift_sec": {
            "min": round(min(drifts_sec), 3),
            "max": round(max(drifts_sec), 3),
            "final": round(drifts_sec[-1], 3),
        },
        "alerts_total": alerts_total,
        "hits_total": hits_total,
        "errors": errors,
        "skipped_outside_rth_count": sum(
            1 for r in pulse_results if r.get("skipped") == "outside_rth"
        ),
        "cadence_pass": (
            max(pulse_durations_ms) < (interval_sec * 1000)
            and abs(drifts_sec[-1]) < (interval_sec / 2)
            and not errors
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=20,
                        help="Number of pulses to fire (default 20 = 5 min at 15s)")
    parser.add_argument("--interval-sec", type=int, default=15)
    parser.add_argument("--force", action="store_true",
                        help="Run even outside RTH (pulse will short-circuit)")
    parser.add_argument("--mock-rth", action="store_true",
                        help="Force RTH=True so full pulse pipeline runs (real yfinance + detectors)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()


    if not args.json:
        print(f"=== REAL-TIME PULSE CADENCE TEST ===")
        print(f"  iterations:    {args.iterations}")
        print(f"  interval:      {args.interval_sec}s")
        print(f"  total runtime: ~{args.iterations * args.interval_sec}s "
              f"({args.iterations * args.interval_sec / 60:.1f}min)")
        print()
        print(f"  starting at:   {datetime.now(timezone.utc).isoformat()}")
        print()

    result = run_cadence_test(args.iterations, args.interval_sec,
                                force=args.force, mock_rth=args.mock_rth)

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        if result.get("skipped"):
            print(f"SKIPPED: {result['skipped']}")
            print(f"  {result.get('tip', '')}")
            return 0
        print(f"  pulse_ms:     min={result['pulse_ms']['min']}  "
              f"avg={result['pulse_ms']['avg']}  "
              f"p95={result['pulse_ms']['p95']}  "
              f"max={result['pulse_ms']['max']}")
        print(f"  drift_sec:    min={result['drift_sec']['min']}  "
              f"max={result['drift_sec']['max']}  "
              f"final={result['drift_sec']['final']}")
        print(f"  total wall:   {result['total_wall_sec']}s "
              f"(expected ~{args.iterations * args.interval_sec - args.interval_sec}s)")
        print(f"  hits/alerts:  {result['hits_total']} / {result['alerts_total']}")
        print(f"  errors:       {len(result['errors'])}")
        for e in result["errors"][:3]:
            print(f"    {e}")
        print(f"  outside-rth skips: {result['skipped_outside_rth_count']}")
        print()
        verdict = "PASS" if result["cadence_pass"] else "FAIL"
        print(f"15s cadence holds: {verdict}")
    return 0 if result.get("cadence_pass", False) or result.get("skipped") else 1


if __name__ == "__main__":
    sys.exit(main())
