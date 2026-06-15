"""Aggregate random_eval batch results across all batches.

Reads every `batch_*.jsonl` in `_state/random_search/`, ranks all seeds by
validate P&L (with sharpe + train health as secondary sorts), prints a
top-N table and writes `random_search_summary.json` for the dashboard.

Run after batches complete (or while they're still running — JSONL is
read-only here so it's safe).

CLI:
    python -m autoresearch.aggregate_random
    python -m autoresearch.aggregate_random --top 20
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from autoresearch import config

logger = logging.getLogger(__name__)
REPO = Path(__file__).resolve().parent.parent
SEARCH_DIR = REPO / "autoresearch" / "_state" / "random_search"


def _safe_load(path: Path) -> list[dict[str, Any]]:
    """Load all valid JSON lines from a JSONL file. Skips malformed lines."""
    out: list[dict[str, Any]] = []
    if not path.exists():
        return out
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def collect_all_results() -> list[dict[str, Any]]:
    """Read every batch_*.jsonl in SEARCH_DIR and return all records."""
    if not SEARCH_DIR.exists():
        return []
    all_recs: list[dict[str, Any]] = []
    for path in sorted(SEARCH_DIR.glob("batch_*.jsonl")):
        batch_id = path.stem.replace("batch_", "")
        for rec in _safe_load(path):
            rec["batch_id"] = batch_id
            all_recs.append(rec)
    return all_recs


def rank_robust(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Score and rank records.

    Robust score = validate_pnl × sign(train_sharpe) × min(1, n_train / 30).
    The sign(train_sharpe) penalty kills regime-overfit candidates that
    only work on the validate window. The trade-count term penalises
    sparse-firing candidates so we don't ratify another n=4 strict mode.
    """
    scored: list[dict[str, Any]] = []
    for rec in records:
        if "error" in rec or "validate_metrics" not in rec:
            continue
        vm = rec["validate_metrics"]
        tm = rec["train_metrics"]
        val_pnl = float(vm.get("total_pnl", 0))
        train_sh = float(tm.get("sharpe_daily", 0))
        n_train = int(tm.get("n_trades", 0))
        n_val = int(vm.get("n_trades", 0))

        train_sign = 1.0 if train_sh > 0 else (-1.0 if train_sh < 0 else 0.0)
        n_factor = min(1.0, n_val / 30.0)
        robust_score = val_pnl * train_sign * n_factor

        rec_with_score = dict(rec)
        rec_with_score["robust_score"] = round(robust_score, 2)
        scored.append(rec_with_score)

    scored.sort(key=lambda r: (
        r["robust_score"],
        float(r["validate_metrics"].get("sharpe_daily", 0)),
        float(r["validate_metrics"].get("total_pnl", 0)),
    ), reverse=True)
    return scored


def print_top(ranked: list[dict[str, Any]], top: int = 10) -> None:
    """Pretty-print the top N candidates."""
    if not ranked:
        print("No completed records found in random_search/.")
        return

    print()
    print("=" * 110)
    print(f"TOP {top} CANDIDATES BY ROBUST SCORE (val_pnl x sign(train_sharpe) x min(1, n_val/30))")
    print("=" * 110)
    header = f"{'rank':>4} {'batch':>5} {'seed':>4} {'score':>8} {'val_pnl':>9} {'val_wr':>7} {'val_sh':>7} {'val_n':>5} {'train_sh':>9} {'train_n':>7} {'max_dd':>8}"
    print(header)
    print("-" * 110)
    for i, rec in enumerate(ranked[:top], 1):
        vm = rec["validate_metrics"]
        tm = rec["train_metrics"]
        print(
            f"{i:>4} {rec['batch_id']:>5} {rec['seed']:>4} "
            f"{rec['robust_score']:>8.0f} "
            f"${vm.get('total_pnl', 0):>+8.0f} "
            f"{vm.get('win_rate', 0)*100:>6.0f}% "
            f"{vm.get('sharpe_daily', 0):>+7.2f} "
            f"{vm.get('n_trades', 0):>5} "
            f"{tm.get('sharpe_daily', 0):>+9.2f} "
            f"{tm.get('n_trades', 0):>7} "
            f"${vm.get('max_drawdown', 0):>+7.0f}"
        )
    print("-" * 110)


def write_summary(ranked: list[dict[str, Any]], out_path: Path, top: int = 20) -> None:
    """Write top-N + aggregate stats to JSON for the dashboard / synthesis."""
    n_total = len(ranked)
    n_positive_val = sum(1 for r in ranked if r["validate_metrics"].get("total_pnl", 0) > 0)
    n_positive_train = sum(1 for r in ranked if r["train_metrics"].get("sharpe_daily", 0) > 0)
    n_robust = sum(
        1 for r in ranked
        if r["validate_metrics"].get("total_pnl", 0) > 0
        and r["train_metrics"].get("sharpe_daily", 0) > 0
        and r["validate_metrics"].get("n_trades", 0) >= 30
    )

    summary = {
        "generated_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "n_total_records": n_total,
        "n_positive_validate_pnl": n_positive_val,
        "n_positive_train_sharpe": n_positive_train,
        "n_robust_candidates": n_robust,
        "top_candidates": ranked[:top],
    }
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=10, help="Top N to print (default 10)")
    args = ap.parse_args()

    records = collect_all_results()
    if not records:
        logger.warning("no records found in %s", SEARCH_DIR)
        return 1

    ranked = rank_robust(records)
    n_total = len(records)
    n_completed = len(ranked)
    n_failed = n_total - n_completed
    n_positive = sum(1 for r in ranked if r["validate_metrics"].get("total_pnl", 0) > 0)

    print(f"\nLoaded {n_total} records ({n_completed} successful, {n_failed} errored)")
    print(f"Records with positive validate P&L: {n_positive} ({n_positive/n_completed:.0%})" if n_completed else "")

    print_top(ranked, args.top)

    out_path = SEARCH_DIR / "random_search_summary.json"
    write_summary(ranked, out_path)
    print(f"\nSummary written to: {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
