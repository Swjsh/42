"""conductor_outcome.py — per-fire outcome metric for the autonomous conductor.

Phase 4 of the autonomy plan. The conductor (`automation/prompts/conductor.md`)
fires once per wake, picks ONE bounded task, and ships or flags it. Until now
"always-improving" was *asserted* in prose (OP-22) but never *measured*: there was
no structured record of what each fire actually accomplished, so net improvement
across fires could not be computed.

This module closes that gap with two pure-stdlib functions + a thin CLI:

  1. record(...)  -> appends one JSON line to conductor-outcomes.jsonl (best-effort,
     never throws — a failure to journal must never crash a conductor fire).
  2. compute_metric(window) -> folds the last N outcome rows into a rolling
     net-improvement scorecard written to autonomy-metric.json.

The metric is deliberately simple and explainable (see compute_metric docstring
for the net_improvement formula + thrash heuristic). It is a *signal* for J and the
conductor, not a reward function the conductor optimizes against.

STDLIB ONLY. Anchor everything to the repo root via __file__ so it is correct no
matter the cwd of the scheduled task that invokes it.

CLI:
  python setup/scripts/conductor_outcome.py record --task-id X --cost 1.50 \
      --drained 1 --added 0 --lessons 1 --tests-delta 7 --regressions 0 --note "..."
  python setup/scripts/conductor_outcome.py metric [--window N]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# --- Path anchoring (cwd-independent) ---------------------------------------
# setup/scripts/conductor_outcome.py -> parents[2] == repo root.
REPO = Path(__file__).resolve().parents[2]
STATE_DIR = REPO / "automation" / "state"
OUTCOMES_FILE = STATE_DIR / "conductor-outcomes.jsonl"
METRIC_FILE = STATE_DIR / "autonomy-metric.json"

DEFAULT_WINDOW = 20

# Numeric outcome fields and their defaults (strings default to "").
_NUMERIC_FIELDS = (
    "cost_usd",
    "items_drained",
    "items_added",
    "lessons_shipped",
    "tests_delta",
    "regressions",
)


def _utc_now_iso() -> str:
    """Current UTC time as an ISO8601 string (seconds precision, 'Z' suffix)."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# --- 1) RECORD ---------------------------------------------------------------
def record(
    task_id: str = "",
    *,
    cost_usd: float = 0.0,
    items_drained: int = 0,
    items_added: int = 0,
    lessons_shipped: int = 0,
    tests_delta: int = 0,
    regressions: int = 0,
    note: str = "",
    fired_at: str | None = None,
    outcomes_file: Path | None = None,
) -> dict[str, Any] | None:
    """Append one structured fire-outcome row to conductor-outcomes.jsonl.

    Best-effort and NEVER throws: a failure to journal an outcome must never crash
    a conductor fire. On any error we swallow it (returning None) rather than
    propagate. Missing dirs/file are created on demand.

    Returns the row dict that was written, or None if the append failed.
    """
    path = outcomes_file or OUTCOMES_FILE
    row: dict[str, Any] = {
        "fired_at": fired_at or _utc_now_iso(),
        "task_id": str(task_id or ""),
        "cost_usd": float(cost_usd or 0.0),
        "items_drained": int(items_drained or 0),
        "items_added": int(items_added or 0),
        "lessons_shipped": int(lessons_shipped or 0),
        "tests_delta": int(tests_delta or 0),
        "regressions": int(regressions or 0),
        "note": str(note or ""),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
        return row
    except Exception:
        # Journaling is non-critical — never let it take down the caller.
        return None


# --- helpers for COMPUTE -----------------------------------------------------
def _read_outcomes(path: Path) -> list[dict[str, Any]]:
    """Read all well-formed outcome rows. Robust to missing/empty/torn files.

    A torn (truncated/partial) final line — or any malformed line — is skipped
    silently rather than raising. Returns rows in file (chronological) order.
    """
    rows: list[dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return rows
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue  # torn / malformed line — skip
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def _num(row: dict[str, Any], key: str) -> float:
    """Coerce a row field to a number, treating missing/garbage as 0."""
    try:
        return float(row.get(key, 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def _net_improvement(rows: list[dict[str, Any]]) -> int:
    """net_improvement = sum(items_drained) - sum(regressions) - thrash_penalty.

    thrash_penalty heuristic (kept deliberately simple + explainable):
      A "thrash" is a fire that undid prior progress. We count, per fire (in
      chronological order), +1 of penalty when EITHER:
        (a) the fire reports regressions > 0  (it broke something), OR
        (b) the fire RE-ADDS a task_id that an EARLIER fire had drained
            (items_added > 0 on a task that was previously cleared — i.e. churn:
             work that came back after being marked done).
      The two conditions are OR'd but counted at most once per fire, so a single
      bad fire contributes at most 1 to the penalty. This rewards monotonic
      progress (drain and stay drained) and penalizes churn/breakage without
      letting one fire dominate the metric.
    """
    drained_total = 0
    regressions_total = 0
    thrash = 0
    seen_drained_task_ids: set[str] = set()

    for row in rows:
        d = int(_num(row, "items_drained"))
        a = int(_num(row, "items_added"))
        r = int(_num(row, "regressions"))
        tid = str(row.get("task_id", "") or "")

        drained_total += d
        regressions_total += r

        readded = a > 0 and tid != "" and tid in seen_drained_task_ids
        if r > 0 or readded:
            thrash += 1

        # Record this fire's drained task AFTER the re-add check, so a fire that
        # both drains and re-adds the same id is not flagged against itself.
        if d > 0 and tid != "":
            seen_drained_task_ids.add(tid)

    return int(drained_total - regressions_total - thrash)


def _trend(rows: list[dict[str, Any]]) -> str:
    """Compare net_improvement of the recent half vs the older half of the window.

    Returns "improving" | "flat" | "regressing". With fewer than 2 rows there is
    no basis for a trend -> "flat".
    """
    n = len(rows)
    if n < 2:
        return "flat"
    mid = n // 2
    older = rows[:mid]
    recent = rows[mid:]
    older_ni = _net_improvement(older)
    recent_ni = _net_improvement(recent)
    if recent_ni > older_ni:
        return "improving"
    if recent_ni < older_ni:
        return "regressing"
    return "flat"


# --- 2) COMPUTE --------------------------------------------------------------
def compute_metric(
    window: int = DEFAULT_WINDOW,
    *,
    outcomes_file: Path | None = None,
    metric_file: Path | None = None,
    write: bool = True,
) -> dict[str, Any]:
    """Fold the last `window` outcome rows into a rolling net-improvement metric.

    Robust to a missing/empty/torn outcomes file -> all-zero metric, trend "flat".
    Writes the result to autonomy-metric.json (unless write=False) and returns it.
    """
    out_path = outcomes_file or OUTCOMES_FILE
    met_path = metric_file or METRIC_FILE
    window = max(1, int(window or DEFAULT_WINDOW))

    all_rows = _read_outcomes(out_path)
    rows = all_rows[-window:]  # last N (chronological order preserved)

    total_cost = round(sum(_num(r, "cost_usd") for r in rows), 4)
    total_drained = int(sum(_num(r, "items_drained") for r in rows))
    total_regressions = int(sum(_num(r, "regressions") for r in rows))
    fires_counted = len(rows)
    cost_per_drained = round(total_cost / max(1, total_drained), 4)

    metric: dict[str, Any] = {
        "computed_at": _utc_now_iso(),
        "window": window,
        "net_improvement": _net_improvement(rows),
        "total_drained": total_drained,
        "total_regressions": total_regressions,
        "total_cost_usd": total_cost,
        "cost_per_drained_usd": cost_per_drained,
        "fires_counted": fires_counted,
        "trend": _trend(rows),
    }

    if write:
        try:
            met_path.parent.mkdir(parents=True, exist_ok=True)
            met_path.write_text(json.dumps(metric, indent=2) + "\n", encoding="utf-8")
        except Exception:
            # Writing the metric is best-effort too; still return it to the caller.
            pass

    return metric


# --- CLI ---------------------------------------------------------------------
def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="conductor_outcome",
        description="Record per-fire conductor outcomes and compute the rolling "
        "net-improvement autonomy metric.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    rec = sub.add_parser("record", help="Append one fire-outcome row.")
    rec.add_argument("--task-id", default="", help="Task id this fire worked on.")
    rec.add_argument("--cost", type=float, default=0.0, help="USD spent this fire.")
    rec.add_argument("--drained", type=int, default=0, help="Queue items cleared.")
    rec.add_argument("--added", type=int, default=0, help="Queue items added.")
    rec.add_argument("--lessons", type=int, default=0, help="Lessons shipped.")
    rec.add_argument("--tests-delta", type=int, default=0, help="Net new tests.")
    rec.add_argument("--regressions", type=int, default=0, help="Regressions caused.")
    rec.add_argument("--note", default="", help="Free-form note.")
    rec.add_argument("--fired-at", default=None, help="ISO8601 override (default now).")

    met = sub.add_parser("metric", help="Compute + write autonomy-metric.json.")
    met.add_argument(
        "--window", type=int, default=DEFAULT_WINDOW, help="Rows to fold (default 20)."
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.cmd == "record":
        row = record(
            task_id=args.task_id,
            cost_usd=args.cost,
            items_drained=args.drained,
            items_added=args.added,
            lessons_shipped=args.lessons,
            tests_delta=args.tests_delta,
            regressions=args.regressions,
            note=args.note,
            fired_at=args.fired_at,
        )
        if row is None:
            print("record: FAILED to append outcome (swallowed, non-fatal)", file=sys.stderr)
            return 1
        print(json.dumps(row))
        return 0

    if args.cmd == "metric":
        metric = compute_metric(window=args.window)
        print(json.dumps(metric, indent=2))
        return 0

    return 2  # unreachable: subparser is required


if __name__ == "__main__":
    raise SystemExit(main())
