"""Truncation-artifact cross-check — a graduated guard for real-fills strategy hunts.

LESSON L171 (2026-06-20, IBS mean-reversion new-hunt). A tight premium stop can
MANUFACTURE a positive per-trade average by mechanically truncating losers at the
stop while a handful of fast winners run — with NO underlying signal edge. The
tell is a SIGN INVERSION across the stop axis: the chosen (positive) grid cell
sits at a tight premium stop, yet the SAME signal on the SAME strike at
chart-stop-only (``premium_stop_pct == -0.99``) is materially NEGATIVE. If
removing the truncation flips the sign, the "edge" was the stop, not the signal.

Worked example (IBS): best cell ``strike_offset=-1`` / stop ``-8%`` -> +$5.3/trade
at WR 26% (the published IBS thesis is a ~70%-WR edge — the WR collapse is itself a
tell), while the same strike at chart-stop-only is -$19.6/trade. clears_bar=false.

This module GRADUATES that cross-check — which shipped inline in
``backtest/autoresearch/_newhunt_ibs_mean_reversion.py`` as ``is_truncation_artifact``
— into a reusable gate, so every ``backtest/autoresearch/_newhunt_*.py`` and
``*_real_fills_validate.py`` self-verify can include it by default instead of
re-deriving it inline. Pure Python, no third-party deps, $0.

Doctrine cross-refs: CLAUDE.md C2 (first-strike entries: chart-stop only,
premium-stop disabled — L51/L55/L64), C4 (a positive average is NOT automatically
a per-trade edge), C3/L58 (SPY-direction edge != option edge). Guarded by
``backtest/tests/test_truncation_guard.py``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

# Defaults mirror the IBS reference implementation exactly.
CHART_STOP_ONLY_PCT = -0.99      # the "no premium truncation" reference cell
TIGHT_STOP_THRESHOLD = -0.30     # a stop tighter (closer to 0) than this is "tight"


def is_truncation_artifact(
    *,
    best_per_trade: float | None,
    chart_stop_only_per_trade: float | None,
    best_premium_stop_pct: float | None,
    tight_stop_threshold: float = TIGHT_STOP_THRESHOLD,
) -> bool:
    """Return True iff the chosen cell's positive expectancy is a stop artifact.

    Artifact when ALL hold:

      * the chosen cell is positive            (``best_per_trade > 0``), AND
      * the same-strike chart-stop-only cell is negative
                                               (``chart_stop_only_per_trade < 0``), AND
      * the chosen cell relies on a TIGHT stop
                                               (``best_premium_stop_pct > tight_stop_threshold``,
                                               i.e. closer to zero than -0.30).

    Returns False (cannot disprove) when the chart-stop-only datapoint or the
    chosen stop is missing — the diagnostic fails OPEN, so a missing reference
    cell never silently *blesses* a candidate; the outer candidate gate still
    governs. A ``None`` per-trade is treated as 0 (not positive -> not an
    artifact), matching the ``(avg or 0) > 0`` guard in the reference impl.
    """
    if chart_stop_only_per_trade is None or best_premium_stop_pct is None:
        return False
    best_pt = best_per_trade if best_per_trade is not None else 0.0
    return (
        best_pt > 0
        and chart_stop_only_per_trade < 0
        and best_premium_stop_pct > tight_stop_threshold
    )


@dataclass(frozen=True)
class TruncationVerdict:
    """Immutable result of cross-checking a chosen grid cell against chart-stop-only."""

    is_artifact: bool
    best_strike_offset: Any
    best_premium_stop_pct: float | None
    best_per_trade: float | None
    chart_stop_only_per_trade: float | None
    chart_stop_pct: float
    reason: str

    @property
    def passes(self) -> bool:
        """True when the cell is NOT a truncation artifact (gate PASS)."""
        return not self.is_artifact


def cross_check_grid(
    grid_results: Iterable[Mapping[str, Any]],
    best_cell: Mapping[str, Any],
    *,
    chart_stop_pct: float = CHART_STOP_ONLY_PCT,
    tight_stop_threshold: float = TIGHT_STOP_THRESHOLD,
    per_trade_key: str = "avg_pnl",
    overall_key: str = "overall",
    strike_key: str = "strike_offset",
    stop_key: str = "premium_stop_pct",
) -> TruncationVerdict:
    """Cross-check ``best_cell`` against the SAME-strike chart-stop-only cell.

    ``grid_results`` is the list of swept cells; each cell is a mapping with
    ``strike_key``, ``stop_key``, and an ``overall_key`` sub-mapping carrying
    ``per_trade_key``. ``best_cell`` is the chosen cell (same shape). Returns a
    :class:`TruncationVerdict`; ``.passes`` is True when the cell is a genuine
    edge (not a stop artifact).

    The defaults match the IBS reference layout (cells keyed by ``strike_offset``
    / ``premium_stop_pct`` with an ``overall`` report carrying ``avg_pnl``); pass
    the ``*_key`` overrides to adapt other ``_newhunt_*`` / ``*_real_fills_validate``
    grid shapes.
    """
    best_so = best_cell.get(strike_key)
    best_ps = best_cell.get(stop_key)
    best_pt = (best_cell.get(overall_key) or {}).get(per_trade_key)

    lookup = {(c.get(strike_key), c.get(stop_key)): c for c in grid_results}
    loose_cell = lookup.get((best_so, chart_stop_pct))
    loose_pt = (
        (loose_cell.get(overall_key) or {}).get(per_trade_key)
        if loose_cell is not None
        else None
    )

    artifact = is_truncation_artifact(
        best_per_trade=best_pt,
        chart_stop_only_per_trade=loose_pt,
        best_premium_stop_pct=best_ps,
        tight_stop_threshold=tight_stop_threshold,
    )

    if loose_cell is None:
        reason = (
            f"no chart-stop-only ({chart_stop_pct}) cell at strike_offset={best_so} "
            f"to cross-check against — truncation NOT disproved; the outer candidate "
            f"gate still governs"
        )
    elif artifact:
        reason = (
            f"TRUNCATION ARTIFACT: chosen cell (strike={best_so}, stop={best_ps}) is "
            f"+${best_pt}/trade but the SAME strike at chart-stop-only ({chart_stop_pct}) "
            f"is ${loose_pt}/trade — sign inverts, so the edge is the tight stop cutting "
            f"losers, not the signal"
        )
    else:
        reason = (
            f"not a truncation artifact: chart-stop-only ({chart_stop_pct}) at "
            f"strike={best_so} is ${loose_pt}/trade (sign holds vs chosen ${best_pt}/trade)"
        )

    return TruncationVerdict(
        is_artifact=artifact,
        best_strike_offset=best_so,
        best_premium_stop_pct=best_ps,
        best_per_trade=best_pt,
        chart_stop_only_per_trade=loose_pt,
        chart_stop_pct=chart_stop_pct,
        reason=reason,
    )
