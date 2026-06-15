"""Sub-window stability test for a parameter set.

Evaluates a single param set across multiple historical sub-windows and
reports whether performance is stable across regimes (truly robust) or
concentrated in one regime (overfit).

Pass either a `--seed N` (params generated via random_eval.generate_params)
or a `--params-file <path>` to a JSON file containing a params dict.

Sub-windows tested by default:
    2025-Q1   (Jan 1  .. Mar 31, 2025)
    2025-Q2   (Apr 1  .. Jun 30, 2025)
    2025-Q3   (Jul 1  .. Sep 30, 2025)
    2025-Q4   (Oct 1  .. Dec 31, 2025)
    2026-VAL  (Feb 14 .. May 7,  2026)   # the production validate window

A robust candidate scores positive PnL on at least 3 of the 5 windows
AND a positive Sharpe on at least 3 of the 5 windows.

CLI:
    python -m autoresearch.sub_window_test --seed 6
    python -m autoresearch.sub_window_test --seed 9
    python -m autoresearch.sub_window_test --seeds 6 9 23 15 7
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from autoresearch import config, runner
from autoresearch.random_eval import generate_params

logger = logging.getLogger(__name__)
REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "autoresearch" / "_state" / "random_search"


SUB_WINDOWS: list[tuple[str, dt.date, dt.date]] = [
    ("2025-Q1", dt.date(2025, 1, 1),  dt.date(2025, 3, 31)),
    ("2025-Q2", dt.date(2025, 4, 1),  dt.date(2025, 6, 30)),
    ("2025-Q3", dt.date(2025, 7, 1),  dt.date(2025, 9, 30)),
    ("2025-Q4", dt.date(2025, 10, 1), dt.date(2025, 12, 31)),
    ("2026-VAL", dt.date(2026, 2, 14), dt.date(2026, 5, 7)),
]


def evaluate_window(
    label: str,
    params: dict[str, Any],
    spy_df: pd.DataFrame,
    vix_df: pd.DataFrame,
    start: dt.date,
    end: dt.date,
) -> dict[str, Any]:
    """Run a single sub-window backtest and return metrics + label."""
    _, m = runner.run_with_params(params, start, end, spy_df, vix_df)
    return {
        "window": label,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "metrics": m.to_dict(),
    }


def stability_summary(window_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Score how robust the candidate is across sub-windows.

    A robust candidate has positive PnL AND positive Sharpe on >= 3 of 5 windows.
    """
    n_pos_pnl = sum(1 for w in window_results if w["metrics"]["total_pnl"] > 0)
    n_pos_sharpe = sum(1 for w in window_results if w["metrics"]["sharpe_daily"] > 0)
    n_total = len(window_results)
    is_robust = n_pos_pnl >= 3 and n_pos_sharpe >= 3
    return {
        "n_total_windows": n_total,
        "n_positive_pnl": n_pos_pnl,
        "n_positive_sharpe": n_pos_sharpe,
        "is_robust": is_robust,
        "verdict": "ROBUST" if is_robust else (
            "REGIME-OVERFIT" if n_pos_pnl < 3 else "MARGINAL"
        ),
    }


def run_for_seed(seed: int, spy_df: pd.DataFrame, vix_df: pd.DataFrame) -> dict[str, Any]:
    """Evaluate seed `seed` across all sub-windows and return summary record."""
    params = generate_params(seed)
    logger.info("[seed=%d] evaluating %d sub-windows", seed, len(SUB_WINDOWS))

    window_results: list[dict[str, Any]] = []
    for label, start, end in SUB_WINDOWS:
        try:
            wr = evaluate_window(label, params, spy_df, vix_df, start, end)
            m = wr["metrics"]
            logger.info(
                "  [seed=%d] %s: pnl=$%+.0f wr=%.0f%% sh=%+.2f n=%d",
                seed, label,
                m["total_pnl"], m["win_rate"] * 100, m["sharpe_daily"], m["n_trades"],
            )
            window_results.append(wr)
        except Exception as exc:
            logger.exception("[seed=%d] %s FAILED: %s", seed, label, exc)
            window_results.append({"window": label, "error": repr(exc)})

    summary = stability_summary([w for w in window_results if "metrics" in w])
    return {
        "seed": seed,
        "params": params,
        "windows": window_results,
        "stability": summary,
        "evaluated_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }


def print_table(results: list[dict[str, Any]]) -> None:
    """Print a stability comparison table across seeds."""
    print()
    print("=" * 110)
    print("SUB-WINDOW STABILITY TABLE")
    print("=" * 110)

    seeds = [r["seed"] for r in results]
    header = f"{'Window':<10} {'Metric':<12} " + " ".join(f"{'seed=' + str(s):>14}" for s in seeds)
    print(header)
    print("-" * len(header))

    for label, _, _ in SUB_WINDOWS:
        for metric_label, key, fmt in [
            ("PnL$", "total_pnl", "{:+.0f}"),
            ("WR%", "win_rate", "{:.0%}"),
            ("Sharpe", "sharpe_daily", "{:+.2f}"),
            ("Trades", "n_trades", "{}"),
        ]:
            row = f"{label:<10} {metric_label:<12} "
            for r in results:
                wr = next((w for w in r["windows"] if w.get("window") == label), None)
                if wr and "metrics" in wr:
                    val = wr["metrics"].get(key, 0)
                    cell = fmt.format(val)
                else:
                    cell = "-"
                row += f"{cell:>14} "
            print(row.rstrip())
        print("-" * len(header))

    # Stability summary row
    print()
    print(f"{'Stability':<23} " + " ".join(
        f"{r['stability']['verdict']:>14}" for r in results
    ))
    print(f"{'+ PnL windows':<23} " + " ".join(
        f"{r['stability']['n_positive_pnl']:>4}/{r['stability']['n_total_windows']:<9}" for r in results
    ))
    print(f"{'+ Sharpe windows':<23} " + " ".join(
        f"{r['stability']['n_positive_sharpe']:>4}/{r['stability']['n_total_windows']:<9}" for r in results
    ))
    print()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, help="Single seed to test")
    ap.add_argument("--seeds", type=int, nargs="+", help="Multiple seeds to test")
    args = ap.parse_args()

    if args.seed is not None and args.seeds is not None:
        ap.error("pass --seed OR --seeds, not both")
    if args.seed is None and args.seeds is None:
        ap.error("must pass --seed or --seeds")

    seeds = args.seeds if args.seeds is not None else [args.seed]

    # Load data once for the full range.
    full_start = SUB_WINDOWS[0][1]
    full_end = SUB_WINDOWS[-1][2]
    logger.info("loading data %s..%s", full_start, full_end)
    spy_df, vix_df = runner.load_data(full_start, full_end)
    logger.info("loaded: %d SPY 5m bars, %d VIX 5m bars", len(spy_df), len(vix_df))

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    for seed in seeds:
        rec = run_for_seed(seed, spy_df, vix_df)
        results.append(rec)
        # Save per-seed result
        out_path = OUT_DIR / f"sub_window_seed{seed}.json"
        out_path.write_text(json.dumps(rec, indent=2), encoding="utf-8")

    print_table(results)

    # Save combined comparison
    combined_path = OUT_DIR / "sub_window_comparison.json"
    combined_path.write_text(
        json.dumps({"seeds": seeds, "results": results}, indent=2),
        encoding="utf-8",
    )
    print(f"Saved per-seed JSON to {OUT_DIR}\\sub_window_seed*.json")
    print(f"Saved comparison    to {combined_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
