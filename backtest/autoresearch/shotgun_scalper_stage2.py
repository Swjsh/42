"""SHOTGUN_SCALPER Stage 2 grinder — focused search after Stage 1 surfaced 0 keepers.

Stage 1 (2026-05-15) ran 939 of 2160 combos; 0 passed any gate. Knob clustering
in the top-50 by edge_capture showed clear winners on two dimensions:
  - stop_premium_pct = -0.25 (100% of top 50)
  - chandelier_arm_pct = 0.40 (80% of top 50)

Stage 2 extends those dimensions further in the winning direction and relaxes
gates to surface "least bad" combos that Stage 3 can refine. See
``docs/SHOTGUN-STAGE1-RESULTS-AND-STAGE2-PLAN.md`` for full analysis.

Grid: 3 × 3 × 3 × 3 × 3 × 6 = 1,458 combos.

CLI::

    python -m autoresearch.shotgun_scalper_stage2 --hours 6 --workers 4
    python -m autoresearch.shotgun_scalper_stage2 --smoke
"""

from __future__ import annotations

import sys
from pathlib import Path

# Import the Stage 1 grinder module — we monkey-patch its globals before
# invoking main(). This keeps the implementation in one place.
from autoresearch import shotgun_scalper_grinder as g

# ── Stage 2 grid: focused on the winning region from Stage 1 ────────────────
STAGE2_TP_PREMIUM_PCTS = [0.50, 0.75, 1.00, 1.50, 2.00, 3.00]
STAGE2_STOP_PREMIUM_PCTS = [-0.25, -0.30, -0.35]
STAGE2_TIME_STOP_MINS = [10, 12, 15]
STAGE2_STRIKE_OFFSETS = [-1, 1, 2]  # drop ATM (was dominated)
STAGE2_CHANDELIER_ARM_PCTS = [0.40, 0.50, 0.60]
STAGE2_VOL_RATIO_THRESHOLDS = [1.0, 1.2, 1.5]


# ── Relaxed Stage 2 gates ───────────────────────────────────────────────────
STAGE2_GATES = g.KeeperGates(
    min_sharpe=0.0,
    min_expectancy_per_trade=0.05,
    min_n_trades=30,
    max_drawdown_dollars=3000.0,
    min_edge_capture_pct=0.20,
    min_positive_quarters=2,
    max_top5_pct=0.6,
)


def _patch_module() -> None:
    """Monkey-patch the grinder module for Stage 2 run.

    Replaces the constants `_build_param_grid` reads from, swaps `OUT_DIR`
    and downstream output paths, and replaces the active KeeperGates.
    """
    g.TP_PREMIUM_PCTS = STAGE2_TP_PREMIUM_PCTS
    g.STOP_PREMIUM_PCTS = STAGE2_STOP_PREMIUM_PCTS
    g.TIME_STOP_MINS = STAGE2_TIME_STOP_MINS
    g.STRIKE_OFFSETS = STAGE2_STRIKE_OFFSETS
    g.CHANDELIER_ARM_PCTS = STAGE2_CHANDELIER_ARM_PCTS
    g.VOL_RATIO_THRESHOLDS = STAGE2_VOL_RATIO_THRESHOLDS

    # Swap output directory + the downstream paths under it
    new_out = g.REPO / "autoresearch" / "_state" / "shotgun_scalper_stage2"
    new_out.mkdir(parents=True, exist_ok=True)
    g.OUT_DIR = new_out
    g.PROGRESS = new_out / "progress.json"
    g.RESULTS = new_out / "results.jsonl"
    g.REJECTIONS = new_out / "rejections.jsonl"
    g.KEEPERS = new_out / "keepers.jsonl"
    g.PIDFILE = new_out / "runner.pid"
    g.LOGFILE = new_out / "grinder.log"

    # Final scorecard path (Stage 2 artefact)
    g.STAGE1_FINAL = g.REPO.parent / "analysis" / "recommendations" / "shotgun-scalper-stage2.json"

    # Active gates
    g.GATES = STAGE2_GATES


def main() -> int:
    _patch_module()
    return g.main()


if __name__ == "__main__":
    sys.exit(main())
