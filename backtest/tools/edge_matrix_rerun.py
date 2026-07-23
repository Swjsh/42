"""edge_matrix_rerun.py -- STUB + protocol notes for the standing "infinite backtesting" loop.

STATUS: STUB (2026-07-23). Orchestration skeleton + frozen protocol. The per-family
--incremental flag does not exist yet in the runners; until it does, --refresh re-runs each
family full-population (hours, weekend-grade) rather than appending. The protocol below is
the contract any future edit must keep.

GOAL
----
One command that keeps the 2026-07-23 EDGE MATRIX (markdown/research/EDGE-MATRIX-2026-07-23.md)
alive as new trading days accrue, WITHOUT ever re-tuning:

    python backtest/tools/edge_matrix_rerun.py --refresh        # full standing refresh
    python backtest/tools/edge_matrix_rerun.py --status         # watermark + pending-day count only

THE FROZEN CONTRACT (violating any of these = a NEW dated prereg, not a rerun)
------------------------------------------------------------------------------
1. GRIDS ARE FROZEN. The 98 cells (6 families) are exactly the ones in
   analysis/edge-matrix/prereg-*-2026-07-23.json. No knob, band, gate, seed, or axis changes.
2. THE ORIGINAL SPLIT IS FROZEN. Tuning (2025-01-02..2026-02-24) and held-out
   (2026-02-25..2026-07-17) stay exactly as the day inventory froze them. Reruns NEVER
   re-shuffle the split.
3. NEW DAYS = FORWARD SEGMENT ONLY. Every OPRA day after the inventory's last held-out day
   accrues to a third segment, "forward" -- pure post-registration out-of-sample. Per cell,
   reruns append: forward_total, forward_n_fills, forward_day_wr. Tuning metrics are never
   recomputed with forward data mixed in.
4. BH IS MATRIX-WIDE. After each refresh, recompute Benjamini-Hochberg across ALL 98 cells
   (and any cells added by future preregs) in one pool. Per-family BH is forbidden.
5. DECISION RULE (pre-stated): a cell graduates to verification only when
   (a) its ORIGINAL 4 gates pass, AND (b) forward_n_fills >= 15 with forward_total > 0,
   AND (c) matrix-wide positive-edge q <= 0.10. Anything else keeps accruing silently.
   Special case premarket family: forward-only evidence is the ONLY usable evidence
   (tuning era has no premarket bars) -- judge it on segment (b)+(c) alone, disclosed.
6. AFTER-HOURS ONLY (heartbeat shares the Max pool); no live wiring, no params edits,
   no commits from inside the loop.

PIPELINE (what --refresh runs, in order)
----------------------------------------
Step 1: day inventory forward-extend
    python backtest/tools/build_day_inventory.py --extend  (rebuild = same frozen rules:
    TRUE-ET frame, per-day source dedupe, OPRA coverage census, heldout list UNTOUCHED)
    -> writes analysis/edge-matrix/day-inventory-<today>.json with the ORIGINAL heldout_days
       carried verbatim + new key forward_days.
Step 2: per-family incremental run (frozen grids)
    for runner in:
        backtest/tools/edge_matrix_bear_level_rejection.py      (18 cells)
        backtest/tools/edge_matrix_bull_level_reclaim_quality.py (16)
        backtest/tools/edge_matrix_break_retest_continuation.py  (16)
        backtest/tools/edge_matrix_range_pingpong.py             (16)
        backtest/tools/edge_matrix_sr_flip_retest.py             (16)
        backtest/tools/edge_matrix_premarket_level_interaction.py(16)
    invoke with --days-after <watermark> (TODO: add flag to each runner; until then full rerun).
    Each runner loads its existing episodes JSON, computes episodes for new days only
    (LevelMemory/ribbon context windows are per-day lookbacks, so incremental is exact,
    not approximate), appends, and updates a "forward" block per cell in its results file.
Step 3: matrix-wide BH + doc delta
    Recompute q over all cells (raw-p pool AND the unified one-sided positive-edge pool).
    Append a dated "## Rerun delta <date>" section to markdown/research/EDGE-MATRIX-2026-07-23.md:
    per family, forward P&L / n / day-WR deltas, any cell newly meeting rule 5, honest nulls.
Step 4: watermark
    Write analysis/edge-matrix/rerun-watermark.json:
    {last_day_processed, ran_at, n_forward_days, families_ok, families_failed}.
    Failures are LOUD (STATUS.md "Known broken") -- silent success is failure (C7).

COST: $0 / pure-Python / backtest/.venv interpreter (its pythonw is $EXEMPT_DAEMONS-safe for
long grinds -- see CLAUDE.md debugging section; run as ONE task, never 3 concurrent on OPRA cache).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EM_DIR = REPO / "analysis" / "edge-matrix"
WATERMARK = EM_DIR / "rerun-watermark.json"
INVENTORY_ORIGINAL = EM_DIR / "day-inventory-2026-07-23.json"

FAMILY_RUNNERS = [
    "edge_matrix_bear_level_rejection.py",
    "edge_matrix_bull_level_reclaim_quality.py",
    "edge_matrix_break_retest_continuation.py",
    "edge_matrix_range_pingpong.py",
    "edge_matrix_sr_flip_retest.py",
    "edge_matrix_premarket_level_interaction.py",
]


def _load_watermark() -> dict:
    if WATERMARK.exists():
        return json.loads(WATERMARK.read_text(encoding="utf-8"))
    # Bootstrap: last day the 2026-07-23 matrix consumed.
    return {"last_day_processed": "2026-07-22", "ran_at": None, "n_forward_days": 0}


def cmd_status() -> int:
    wm = _load_watermark()
    print(json.dumps(wm, indent=2))
    print(f"today: {date.today().isoformat()}")
    print("NOTE: STUB -- pending-day census requires the forward-extended inventory (Step 1).")
    return 0


def cmd_refresh() -> int:
    print("edge_matrix_rerun: STUB -- incremental flags not yet wired into family runners.")
    print("Frozen protocol lives in this file's docstring. Until --days-after exists, a full")
    print("standing refresh is a weekend-grade full re-run of each family runner:")
    for r in FAMILY_RUNNERS:
        print(f"  {sys.executable} {REPO / 'backtest' / 'tools' / r}")
    print("Refusing to fire them implicitly from a stub (hours of grind; run deliberately).")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Standing edge-matrix rerun loop (STUB)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--refresh", action="store_true", help="forward-extend + rerun + BH + doc delta")
    g.add_argument("--status", action="store_true", help="show watermark / pending days")
    args = ap.parse_args()
    if args.status:
        return cmd_status()
    return cmd_refresh()


if __name__ == "__main__":
    raise SystemExit(main())
