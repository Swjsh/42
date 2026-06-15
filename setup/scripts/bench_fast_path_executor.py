"""bench_fast_path_executor -- exercise the FULL filter pipeline + measure latency.

The default --benchmark in fast_path_executor.py short-circuits on RTH outside
market hours. This bench monkeypatches RTH=True so all 6 filters run +
real network calls happen (VIX fetch + Alpaca account fetch). Measures whether
the production hot-path stays under 30s budget.

Run:
    python setup/scripts/bench_fast_path_executor.py
    python setup/scripts/bench_fast_path_executor.py --iterations 5
    python setup/scripts/bench_fast_path_executor.py --account safe
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


def _load_fpe():
    # Register module before exec_module to satisfy dataclass __module__ lookup
    # (Python 3.13 dataclass internals walk sys.modules; without registration
    # the @dataclass decorator raises AttributeError).
    spec = importlib.util.spec_from_file_location(
        "fpe", Path(__file__).parent / "fast_path_executor.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["fpe"] = mod
    spec.loader.exec_module(mod)
    return mod


def benchmark_once(fpe, account: str, alert: dict, vix_data: dict | None) -> dict:
    started = time.monotonic()
    # Force RTH=True + entry-window=True to exercise full pipeline
    with patch.object(fpe, "_is_rth_now", return_value=True), \
         patch.object(fpe, "_is_in_entry_window", return_value=True):
        d = fpe.evaluate_alert(account, alert, vix_data=vix_data)
    elapsed_ms = int((time.monotonic() - started) * 1000)
    return {
        "account": account,
        "decision": d.decision,
        "reason": d.reason,
        "elapsed_ms": elapsed_ms,
        "internal_ms": d.elapsed_ms,
        "filters": d.filter_results,
        "strike": d.proposed_strike,
        "qty": d.proposed_qty,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--account", choices=["safe", "bold", "both"], default="both")
    parser.add_argument("--cold-vix", action="store_true",
                        help="Re-fetch VIX every iteration (cold path; slowest)")
    parser.add_argument("--json", action="store_true",
                        help="Output JSON only")
    args = parser.parse_args()

    fpe = _load_fpe()
    alert = {
        "fire_at_utc": datetime.now(timezone.utc).isoformat(),
        "pattern": "failed_breakdown_wick::contra_regime",
        "bias": "bullish",
        "confidence": 0.75,
        "key_price": 735.0,
        "spy_close": 735.40,
        "level_distance_dollars": 0.10,
        "level_name": "PML",
    }
    accounts = ["safe", "bold"] if args.account == "both" else [args.account]

    # Warm VIX cache (typical production usage: pulse pre-fetches VIX once)
    print("=== fast_path_executor benchmark ===")
    print(f"  iterations: {args.iterations}  accounts: {accounts}  cold_vix: {args.cold_vix}")
    print()

    # Initial VIX fetch (will be reused across iterations unless --cold-vix)
    print("Fetching VIX...")
    vix_start = time.monotonic()
    vix_data = fpe._fetch_vix_quick()
    vix_ms = int((time.monotonic() - vix_start) * 1000)
    print(f"  vix_data: {vix_data}  ({vix_ms}ms)")
    print()

    all_results = []
    iter_totals = []
    for it in range(args.iterations):
        iter_start = time.monotonic()
        if args.cold_vix and it > 0:
            vix_start = time.monotonic()
            vix_data = fpe._fetch_vix_quick()
            vix_ms = int((time.monotonic() - vix_start) * 1000)
        for a in accounts:
            r = benchmark_once(fpe, a, alert, vix_data)
            all_results.append({**r, "iteration": it})
            print(f"  iter {it+1}/{args.iterations} {a}: {r['decision']:14s} "
                  f"elapsed={r['elapsed_ms']:4d}ms internal={r['internal_ms']:4d}ms  "
                  f"reason: {r['reason']}")
        iter_total_ms = int((time.monotonic() - iter_start) * 1000)
        iter_totals.append(iter_total_ms)

    print()
    avg_iter = sum(iter_totals) / len(iter_totals)
    max_iter = max(iter_totals)
    avg_elapsed = sum(r["elapsed_ms"] for r in all_results) / len(all_results)
    max_elapsed = max(r["elapsed_ms"] for r in all_results)

    # Cold-path = VIX fetch + per-account
    cold_path_ms = vix_ms + max_elapsed  # pessimistic upper bound for one account
    print("=== SUMMARY ===")
    print(f"  per-account avg: {avg_elapsed:.0f}ms")
    print(f"  per-account max: {max_elapsed}ms")
    print(f"  per-iteration (all accounts) avg: {avg_iter:.0f}ms")
    print(f"  per-iteration max: {max_iter}ms")
    print(f"  VIX fetch (cold): {vix_ms}ms")
    print(f"  COLD-PATH end-to-end (VIX fetch + 1 account): {cold_path_ms}ms")
    print()

    target_ms = 30000
    pass_30s = max_iter < target_ms and cold_path_ms < target_ms
    status = "PASS" if pass_30s else "FAIL"
    print(f"  <30s target: {status}  (max_iter={max_iter}ms cold_path={cold_path_ms}ms)")

    if args.json:
        print()
        print(json.dumps({
            "results": all_results,
            "summary": {
                "avg_elapsed_ms": avg_elapsed,
                "max_elapsed_ms": max_elapsed,
                "vix_fetch_ms": vix_ms,
                "cold_path_ms": cold_path_ms,
                "pass_30s_target": pass_30s,
            }
        }, indent=2))

    return 0 if pass_30s else 1


if __name__ == "__main__":
    sys.exit(main())
