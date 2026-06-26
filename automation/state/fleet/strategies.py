"""The SHARED strategy set — the validated edges every fleet account trades.

Architecture (J's model, 2026-06-25): an account is NOT a strategy. An account is a
(gate-strictness x contract-sizing) profile. EVERY validated strategy runs on EVERY
account; the account only decides *how selective* the entry gate is and *how big* the
position is. So strategies live here, once, and the executor applies each account's
gate + sizing to all of them.

A STRATEGY = an entry edge + its proven exit shape (stop / TP1 / runner). The exit is a
property of the strategy (the grind proved it), NOT the account. Strike selection and
contract count are the ACCOUNT's sizing axis, so they are deliberately absent here.

Add a validated edge by appending one Strategy. `fired(side_block)` maps a shared-signal
side-block to the strategies that triggered this tick (by setup-name match); the executor
then gates + sizes each. Pure functions, no I/O — unit-tested in test_strategies.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence


@dataclass(frozen=True)
class ExitShape:
    """The strategy's proven bracket (fractions, not strikes/qty — those are account sizing).

    The 4 leading fields define the scale-out the live exit_manager realizes (partial TP1 +
    runner + profit-lock). The 3 trailing fields (defaulted to production constants so every
    existing 4-arg ExitShape literal stays valid) make the runner ride fully self-describing:
    where the runner targets, how tight the chandelier trails, and when profit-lock arms."""
    premium_stop_pct: float      # e.g. -0.20  (negative = stop at (1+pct)*entry)
    tp1_premium_pct: float       # e.g. 1.5    (+150% take-profit-1 level)
    tp1_qty_fraction: float      # e.g. 0.8    (sell 80% at TP1, rest rides)
    profit_lock_mode: str        # "fixed" | "trailing"
    runner_target_pct: float = 2.5       # runner exits at entry*(1+this) (CLAUDE.md 2.5x)
    trail_pct: float = 0.125             # chandelier: floor = HWM*(1-this) (WP-6 0.125)
    profit_lock_arm_pct: float = 0.05    # arm the profit-lock at +5% favorable (CLAUDE.md)

    def to_dict(self) -> dict:
        """The exit-shape dict the executor/live paths thread through (kept in sync with
        fleet_executor._exit_shape_dict + exit_manager.ExitState.from_entry keys)."""
        return {
            "premium_stop_pct": self.premium_stop_pct,
            "tp1_premium_pct": self.tp1_premium_pct,
            "tp1_qty_fraction": self.tp1_qty_fraction,
            "profit_lock_mode": self.profit_lock_mode,
            "runner_target_pct": self.runner_target_pct,
            "trail_pct": self.trail_pct,
            "profit_lock_arm_pct": self.profit_lock_arm_pct,
        }


@dataclass(frozen=True)
class Strategy:
    name: str
    # setup_name(s) (from the shared signal's side block) that mean THIS strategy fired.
    entry_setups: Sequence[str]
    exit: ExitShape
    note: str = ""
    # Strategies are direction-agnostic by construction — the side comes from which
    # side-block (bull/bear) fired. No per-strategy direction lock (that was the bug).


# --- The validated set (extend by appending) ------------------------------------------
# ribbon_ride: the mass-grind funnel winner (2026-06-25). Tight-stop directional ride on
# the ribbon rejection/reclaim edge; grind-proven exit = -20% stop / +150% TP1 / sell 80%.
RIBBON_RIDE = Strategy(
    name="ribbon_ride",
    entry_setups=("BEARISH_REJECTION_RIDE_THE_RIBBON", "BULLISH_RECLAIM_RIDE_THE_RIBBON"),
    exit=ExitShape(premium_stop_pct=-0.20, tp1_premium_pct=1.5, tp1_qty_fraction=0.8, profit_lock_mode="fixed"),
    note="mass-grind funnel P4 elite; WF 1.80, qpf 1.0, beats random-entry null by +$167/tr.",
)

# vwap_continuation: the previously-live edge. Its proven exit is the tight -8% stop.
VWAP_CONTINUATION = Strategy(
    name="vwap_continuation",
    entry_setups=("VWAP_CONTINUATION", "vwap_continuation"),
    exit=ExitShape(premium_stop_pct=-0.08, tp1_premium_pct=0.3, tp1_qty_fraction=0.667, profit_lock_mode="trailing"),
    note="prior live edge; ITM-2/-8% tight stop, OOS +$105/tr.",
)

REGISTRY: tuple[Strategy, ...] = (RIBBON_RIDE, VWAP_CONTINUATION)


def _setup_of(side_block: Mapping[str, object]) -> str:
    return str(side_block.get("setup_name") or side_block.get("setup") or "").strip()


def fired(side_block: Mapping[str, object]) -> list[Strategy]:
    """Strategies whose entry setup matches this fired side-block (>=1 trigger).

    Selectivity (how many triggers / what quality) is the ACCOUNT's gate, applied later —
    here we only answer 'did this edge's entry pattern appear this tick'."""
    if side_block.get("passed") is not True:
        return []
    triggers = side_block.get("triggers_fired") or []
    if not triggers:
        return []
    setup = _setup_of(side_block).upper()
    out = []
    for strat in REGISTRY:
        if any(setup == s.upper() for s in strat.entry_setups):
            out.append(strat)
    return out


def by_name(name: str) -> Strategy | None:
    for s in REGISTRY:
        if s.name == name:
            return s
    return None
