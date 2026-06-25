"""Cold eval batch runner for shadow model evaluators.

Runs a matrix of (model, date) pairs sequentially, with proper inter-run delays
to avoid rate limiting on OpenRouter free tier.

Usage:
  python setup/scripts/run_cold_evals.py
  python setup/scripts/run_cold_evals.py --models hermes qwen --dates 2026-05-07 2026-05-19
  python setup/scripts/run_cold_evals.py --models hermes --clear
  python setup/scripts/run_cold_evals.py --dry-run  # show plan only

Rate limit strategy:
  - Within a run: shadow_model_eval.py sleeps sleep_s (90s for Qwen/Hermes) between DT calls.
    90s = 60s_RPM_window + 30s_retry_buffer (retries at +15s and +30s extend effective window to ~105s)
  - Between runs on the SAME model: INTER_RUN_SLEEP_S (120s default) ensures the RPM window
    clears before the next date's first call, even if the last DT had exhausted retries.
  - Between runs on DIFFERENT models: 10s is fine (separate per-model quotas confirmed).

A run = one (model, date) pair. Pairs are ordered model-by-model (all Hermes dates, then all
Qwen dates) so each model's inter-run sleep applies only within that model's burst.
"""

import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
EVAL_SCRIPT = REPO / "setup" / "scripts" / "shadow_model_eval.py"
PYTHON = REPO / "backtest" / ".venv" / "Scripts" / "python.exe"

# Target dates: ones with meaningful DT ticks that Nemotron has already been benchmarked on.
# Run --dry-run first to verify DT counts before committing API calls.
DEFAULT_DATES = [
    "2026-05-07",   # 3 DTs: HOLD_DEV monitoring ticks (originally hardest date for Nemotron)
    "2026-05-19",   # 2 DTs: ENTER + EXIT_STOP (clean win)
    "2026-05-20",   # 1 DT: EXIT_ALL → EXIT_STOP (legacy action test)
    "2026-06-24",   # 7 DTs: HOLD_DEV bear=8 (pure M1 unconditional threshold test)
]

DEFAULT_MODELS = ["hermes", "qwen"]

INTER_RUN_SLEEP_S = 120    # seconds between runs of same model; last DT may have retries (15s+30s=45s
                           # of extra window), so need 60s_window + 45s_retries + 15s_buffer = 120s
INTER_MODEL_SLEEP_S = 10   # seconds between runs of different models (confirmed separate quota buckets)


def run_eval(model: str, date: str, clear: bool = False, dry_run: bool = False) -> int:
    """Run shadow_model_eval.py for one (model, date) pair. Returns exit code."""
    cmd = [str(PYTHON), str(EVAL_SCRIPT), "--date", date, "--account", "safe", "--model", model, "--dt-only"]
    if clear:
        cmd.append("--clear")
    if dry_run:
        cmd.append("--dry-run")
    print(f"\n{'='*60}")
    print(f"RUN: {model} on {date}" + (" [CLEAR]" if clear else "") + (" [DRY-RUN]" if dry_run else ""))
    print(f"CMD: {' '.join(cmd)}")
    print(f"{'='*60}")
    sys.stdout.flush()
    result = subprocess.run(cmd, capture_output=False)
    return result.returncode


def main() -> None:
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--models", nargs="+", default=DEFAULT_MODELS, help="Models to evaluate")
    p.add_argument("--dates", nargs="+", default=DEFAULT_DATES, help="Dates to evaluate (YYYY-MM-DD)")
    p.add_argument("--clear", action="store_true", help="Pass --clear to each run (re-evals existing entries)")
    p.add_argument("--dry-run", action="store_true", help="Show plan and prompts, no API calls")
    p.add_argument("--inter-run-sleep", type=int, default=INTER_RUN_SLEEP_S,
                   help=f"Seconds between same-model runs (default {INTER_RUN_SLEEP_S})")
    args = p.parse_args()

    pairs = [(model, date) for model in args.models for date in args.dates]
    total = len(pairs)

    print(f"Cold eval batch: {len(args.models)} models × {len(args.dates)} dates = {total} runs")
    print(f"Models: {args.models}")
    print(f"Dates:  {args.dates}")
    print(f"Inter-run sleep (same model): {args.inter_run_sleep}s")
    print(f"Inter-model sleep: {INTER_MODEL_SLEEP_S}s")
    if args.dry_run:
        print("[DRY-RUN] — showing prompts only, no API calls")
    print()

    results: list[dict] = []
    prev_model: str | None = None

    for idx, (model, date) in enumerate(pairs):
        # Sleep between runs
        if idx > 0:
            same_model = (model == prev_model)
            sleep_s = args.inter_run_sleep if same_model else INTER_MODEL_SLEEP_S
            reason = "same-model RPM window" if same_model else "model switch"
            if not args.dry_run:
                print(f"\n[sleep {sleep_s}s before next run — {reason}]")
                sys.stdout.flush()
                time.sleep(sleep_s)

        rc = run_eval(model, date, clear=args.clear, dry_run=args.dry_run)
        results.append({"model": model, "date": date, "rc": rc})
        prev_model = model

    print("\n" + "="*60)
    print("BATCH COMPLETE")
    print("="*60)
    for r in results:
        status = "OK" if r["rc"] == 0 else f"FAIL(rc={r['rc']})"
        print(f"  {r['model']:12s} {r['date']}  {status}")

    failed = [r for r in results if r["rc"] != 0]
    if failed:
        print(f"\n{len(failed)} run(s) failed. Check output above.")
        sys.exit(1)
    else:
        print("\nAll runs completed successfully.")


if __name__ == "__main__":
    main()
