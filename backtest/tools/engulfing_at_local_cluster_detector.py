"""engulfing_at_local_cluster_detector.py -- grid adapter for the SHIPPED
`engulfing_at_local_cluster` pattern-grammar rule (backtest/lib/patterns/registry.py,
13th entry, commit 8aed997a), built to run the item's own named NEXT STEP:

    "a frozen pre-reg (<=16 cells) + real-fills replay through exit_manager_walk over
    the 386-day history, standing gates + BH, confirming the winning cell still fires
    on both anchor bars." (automation/overnight/queue.md ENGULFING-AT-STRUCTURE-TRIGGER)

ZERO-FORK BY CONSTRUCTION (C34 -- one implementation, not a fork): this module does
NOT re-derive the cluster/engulfing geometry. It imports the exact two generic,
already-tested predicate factories the shipped registry rule composes --
`backtest.lib.patterns.predicates.engulfing` and `...local_extreme_cluster` -- and
grid-sweeps their existing parameters (n_touches / tolerance) plus the registry rule's
own MIN_BODY_DOLLARS floor. The shipped/anchor-verified config
(min_touches=3, min_body_dollars=0.40, tolerance=0.20, lookback=8,
level_proximity=0.30 -- registry.py LOCAL_CLUSTER_* constants) is CELL
`touch3|body0.40|tol0.20` in this grid -- if this module disagrees with the registry
predicate at that exact cell, that is a bug in this module, not a new finding (guarded
by `backtest/tests/test_engulfing_at_local_cluster.py::test_shipped_cell_matches_registry_predicate`).

lookback (8 bars) and level_proximity ($0.30) are held STRUCTURAL, not swept -- same
convention Lane-B's engulfing_at_structure_detector.py used for its own non-tuned
constants (EXTREME_SIDE_WINDOW/SHELF_LOOKBACK_BARS): they are shared conventions across
every registry rule (LEVEL_PROXIMITY_DOLLARS matches level_strength.py's
CONFLUENCE_PROXIMITY_USD), not this item's own tuning knobs.

PatternContext CONVENTION (deliberately matched, not re-decided): built ONCE over the
FULL stitched multi-day RTH bar sequence, exactly as backtest/tools/pattern_prescreen.py
and backtest/tools/pattern_anchor_verify.py already do for every registry rule
(including the anchor-fire check that originally verified this exact rule on
2026-07-23). A bar-index adjacency across a day boundary (bar 0 of Tuesday sitting 1
index after the prior Friday's last bar) is this framework's STANDING convention, not a
new decision introduced here -- see backtest/lib/patterns/context.py's own C6 docstring.

NO WIRING: pure research module, not imported by the live engine. Consumed by
backtest/tools/edge_matrix_engulfing_at_local_cluster.py (the real-fills replay
runner) and its own guard tests only.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[2]  # .../42
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backtest.lib.patterns.context import PatternContext  # noqa: E402
from backtest.lib.patterns.predicates import engulfing, local_extreme_cluster  # noqa: E402
from crypto.lib.bar import Bar  # noqa: E402

# ── structural constants (disclosed, NOT tuned grid knobs) -- matches
# backtest/lib/patterns/registry.py's LOCAL_CLUSTER_LOOKBACK_BARS / LEVEL_PROXIMITY_DOLLARS ──
LOOKBACK_BARS = 8
LEVEL_PROXIMITY_DOLLARS = 0.30

DIRECTIONS: tuple[str, ...] = ("bullish", "bearish")


@dataclass(frozen=True)
class Cell:
    """One pre-registered grid cell. `min_touches`/`min_body_dollars`/`tolerance` are
    the 3 tuned numeric knobs -- direction is NOT a 4th grid axis (structurally matched
    by construction: bearish engulfing only ever pairs with a HIGH cluster -> put;
    bullish only with a LOW cluster -> call, same convention as every sibling rule in
    this registry family)."""
    min_touches: int
    min_body_dollars: float
    tolerance: float

    def cell_id(self) -> str:
        return f"touch{self.min_touches}|body{self.min_body_dollars:.2f}|tol{self.tolerance:.2f}"

    def to_dict(self) -> dict:
        return {"min_touches": self.min_touches, "min_body_dollars": self.min_body_dollars,
                "tolerance": self.tolerance, "lookback_bars": LOOKBACK_BARS,
                "level_proximity_dollars": LEVEL_PROXIMITY_DOLLARS}

    def is_shipped_config(self) -> bool:
        """True for the exact registry.py LOCAL_CLUSTER_* constants (touch3|body0.40|tol0.20)."""
        return self.min_touches == 3 and abs(self.min_body_dollars - 0.40) < 1e-9 and abs(self.tolerance - 0.20) < 1e-9


def build_grid(axes: dict) -> list[Cell]:
    return [
        Cell(min_touches=int(n), min_body_dollars=float(b), tolerance=float(t))
        for n in axes["min_touches"]
        for b in axes["min_body_dollars"]
        for t in axes["tolerance"]
    ]


def build_context(bars: tuple[Bar, ...]) -> PatternContext:
    """Built ONCE, reused across every grid cell (cells only vary predicate PARAMETERS,
    never the bar sequence itself -- structure/vwap/bandwidth are unused by this rule
    but PatternContext.build computes them regardless; still a single O(n) pass total,
    not per-cell)."""
    return PatternContext.build(bars)


def detect_bar(ctx: PatternContext, t: int, cell: Cell) -> Optional[dict]:
    """Mirrors backtest/lib/patterns/registry.py::_engulfing_at_local_cluster_predicate
    EXACTLY, with the registry's frozen LOCAL_CLUSTER_* constants replaced by this
    cell's grid values. Same bias-branch order, same `engulfed_body_dollars` floor
    field, same wick-vs-close proximity convention (checked against the reacting bar's
    LOW/HIGH, not its close -- see registry.py's own inline note on why)."""
    # Merge order EXACTLY matches registry.py::_engulfing_at_local_cluster_predicate
    # (`{"bias":..., **cluster, **bull}`) -- bull/bear's own `trigger_level` (the
    # engulfing predicate's prior-bar extreme) intentionally OVERWRITES cluster's
    # trigger_level (the cluster mean) in the returned dict; only the proximity CHECK
    # below uses cluster's trigger_level, matching the registry rule's own behavior
    # field-for-field (verified byte-identical against the live registry predicate in
    # test_engulfing_at_local_cluster.py::test_shipped_cell_matches_registry_predicate).
    bar = ctx.bars[t]
    bull = engulfing(direction="bullish")(ctx, t)
    if bull is not None and bull["engulfed_body_dollars"] >= cell.min_body_dollars:
        cluster = local_extreme_cluster(
            kind="low", n_touches=cell.min_touches, tolerance=cell.tolerance, lookback=LOOKBACK_BARS,
        )(ctx, t)
        if cluster is not None and abs(bar.low - cluster["trigger_level"]) <= LEVEL_PROXIMITY_DOLLARS:
            return {"bias": "bullish", **cluster, **bull}
    bear = engulfing(direction="bearish")(ctx, t)
    if bear is not None and bear["engulfed_body_dollars"] >= cell.min_body_dollars:
        cluster = local_extreme_cluster(
            kind="high", n_touches=cell.min_touches, tolerance=cell.tolerance, lookback=LOOKBACK_BARS,
        )(ctx, t)
        if cluster is not None and abs(bar.high - cluster["trigger_level"]) <= LEVEL_PROXIMITY_DOLLARS:
            return {"bias": "bearish", **cluster, **bear}
    return None


def detect_cell_day(ctx: PatternContext, gidxs, cell: Cell) -> list[dict]:
    """One day, one cell (day-local index list; gidxs maps local index -> global ctx.bars
    index). Mirrors edge_matrix_engulfing_at_structure.py::detect_cell_day's per-day
    convention -- local_i=0 (the day's first RTH bar) is skipped (engulfing() needs
    t>=1 anyway; the registry's own PatternContext.build never segments per day, so
    t>=1 here still permits the day's 2nd bar to read the day's 1st bar as `prev`,
    the same standing convention every other registry rule already uses)."""
    out: list[dict] = []
    n = len(gidxs)
    for i in range(1, n):
        g = int(gidxs[i])
        hit = detect_bar(ctx, g, cell)
        if hit is not None:
            out.append({"local_i": i, "gidx": g, **hit})
    return out
