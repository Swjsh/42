"""End-to-end latency test: alert -> numeric_pulse -> fast_path -> decision.

Validates the sub-30s budget by running the full in-process chain with a
synthetic high-conviction alert. Real network calls happen (yfinance + Alpaca
REST) so this is a true wall-time measurement.

Run:
    python setup/scripts/test_end_to_end_latency.py
    python setup/scripts/test_end_to_end_latency.py --json
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
    spec = importlib.util.spec_from_file_location(
        "fpe", PROJECT_ROOT / "setup" / "scripts" / "fast_path_executor.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["fpe"] = mod
    spec.loader.exec_module(mod)
    return mod


def run_e2e_test() -> dict:
    """Simulate: bar closes -> pulse fetches VIX -> evaluate -> persist.

    Returns timing breakdown dict.
    """
    fpe = _load_fpe()

    # --- T+0: alert is "in flight" ---
    bar_close_at = time.monotonic()
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

    # --- VIX fetch (this is the only slow step) ---
    vix_start = time.monotonic()
    vix_data = fpe._fetch_vix_quick()
    vix_elapsed = time.monotonic() - vix_start

    # --- Decision: Safe + Bold both ---
    decision_start = time.monotonic()
    decisions = []
    with patch.object(fpe, "_is_rth_now", return_value=True), \
         patch.object(fpe, "_is_in_entry_window", return_value=True):
        for acct in ("safe", "bold"):
            d_start = time.monotonic()
            d = fpe.evaluate_alert(acct, alert, vix_data=vix_data)
            d_elapsed = time.monotonic() - d_start
            decisions.append({
                "account": acct,
                "decision": d.decision,
                "reason": d.reason,
                "elapsed_sec": round(d_elapsed, 3),
                "strike": d.proposed_strike,
                "qty": d.proposed_qty,
                "stop_premium": d.proposed_stop_premium,
                "tp1_premium": d.proposed_tp1_premium,
            })
    decision_elapsed = time.monotonic() - decision_start
    total_elapsed = time.monotonic() - bar_close_at

    return {
        "vix_fetch_sec": round(vix_elapsed, 3),
        "decision_pipeline_sec": round(decision_elapsed, 3),
        "total_sec": round(total_elapsed, 3),
        "under_30s_target": total_elapsed < 30,
        "under_5s_aggressive_target": total_elapsed < 5,
        "decisions": decisions,
        "vix": vix_data,
    }


def run_repeated_e2e(n: int = 5) -> dict:
    """Run E2E n times to capture distribution + cache-warming effects."""
    runs = []
    for i in range(n):
        run = run_e2e_test()
        runs.append(run)

    totals = [r["total_sec"] for r in runs]
    vixes = [r["vix_fetch_sec"] for r in runs]
    decisions = [r["decision_pipeline_sec"] for r in runs]
    return {
        "n_runs": n,
        "total_sec": {"min": min(totals), "avg": sum(totals)/n, "max": max(totals)},
        "vix_fetch_sec": {"min": min(vixes), "avg": sum(vixes)/n, "max": max(vixes)},
        "decision_pipeline_sec": {"min": min(decisions), "avg": sum(decisions)/n, "max": max(decisions)},
        "all_under_30s": all(t < 30 for t in totals),
        "runs": runs,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-n", "--iterations", type=int, default=5)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run_repeated_e2e(args.iterations)

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(f"=== END-TO-END LATENCY TEST ({args.iterations} iterations) ===")
        print()
        for i, r in enumerate(report["runs"]):
            d_safe = next((d for d in r["decisions"] if d["account"] == "safe"), {})
            d_bold = next((d for d in r["decisions"] if d["account"] == "bold"), {})
            print(f"  iter {i+1}: total={r['total_sec']}s  vix={r['vix_fetch_sec']}s  "
                  f"pipeline={r['decision_pipeline_sec']}s  "
                  f"SAFE={d_safe.get('decision')} BOLD={d_bold.get('decision')}")
        print()
        print("DISTRIBUTION:")
        for k in ("total_sec", "vix_fetch_sec", "decision_pipeline_sec"):
            s = report[k]
            print(f"  {k:25s}  min={s['min']:.3f}s  avg={s['avg']:.3f}s  max={s['max']:.3f}s")
        print()
        verdict = "PASS" if report["all_under_30s"] else "FAIL"
        print(f"<30s budget on ALL runs: {verdict}")
        print()
        # Sample first iteration's full decision
        first = report["runs"][0]["decisions"]
        for d in first:
            print(f"  {d['account']}: {d['decision']}  strike={d['stop_premium'] and d.get('strike')}  "
                  f"qty={d['qty']}  stop=${d['stop_premium']}  tp1=${d['tp1_premium']}")

    return 0 if report["all_under_30s"] else 1


if __name__ == "__main__":
    sys.exit(main())
