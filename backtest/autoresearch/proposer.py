"""Proposer — picks the next modification to try.

Two modes:
    SINGLE-KNOB (default): adjacent step on ONE parameter at a time. Round-robin
        through allowed knobs (filtered by experiment), respecting the recent-
        modification cooldown.
    MULTI-KNOB: combines TWO single-knob proposals into one candidate. Activated
        per-iteration via a probability (default 30%) once the proposer has
        warmed up (>= MULTI_KNOB_WARMUP iters).

The set of allowed knobs is filtered by the experiment name on the State
(state.experiment ∈ {lean, entries, exits, full, kitchen_sink}). Knobs not
in the experiment's allowlist are NEVER proposed.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from typing import Any

from . import config
from .state import State

logger = logging.getLogger(__name__)


# After this many iterations, the proposer can start trying 2-knob combos.
MULTI_KNOB_WARMUP = 8
# Probability per iteration of trying a 2-knob combo (after warmup).
MULTI_KNOB_PROBABILITY = 0.30


@dataclass(frozen=True)
class Proposal:
    """One concrete proposed modification (1 or 2 knobs)."""

    changes: list[tuple[str, Any, Any]]   # [(param, old, new), ...]
    rationale: str

    @property
    def is_multi(self) -> bool:
        return len(self.changes) > 1

    @property
    def param(self) -> str:
        """Primary parameter (for cooldown tracking). For multi-knob, joined."""
        return "+".join(c[0] for c in self.changes)

    @property
    def old_value(self) -> Any:
        return self.changes[0][1] if len(self.changes) == 1 else [c[1] for c in self.changes]

    @property
    def new_value(self) -> Any:
        return self.changes[0][2] if len(self.changes) == 1 else [c[2] for c in self.changes]

    def to_dict(self) -> dict:
        return {
            "param": self.param,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "rationale": self.rationale,
            "is_multi": self.is_multi,
            "changes": [{"param": c[0], "old": c[1], "new": c[2]} for c in self.changes],
        }


def _candidate_steps(param: str, current: Any) -> list[Any]:
    space = config.SEARCH_SPACE.get(param)
    if not space:
        return []
    if current not in space:
        return [v for v in space if v != current]
    idx = space.index(current)
    out: list[Any] = []
    if idx > 0:
        out.append(space[idx - 1])
    if idx < len(space) - 1:
        out.append(space[idx + 1])
    return out


def _allowed_knobs(state: State) -> set[str]:
    """Knobs allowed for this experiment. Empty experiment → all knobs."""
    exp = getattr(state, "experiment", None) or "full"
    if exp not in config.EXPERIMENTS:
        logger.warning("unknown experiment '%s'; using 'full'", exp)
        exp = "full"
    return config.EXPERIMENTS[exp]


def _build_single_knob_options(state: State) -> list[tuple[str, Any, str]]:
    """List of (param, new_value, rationale) for every adjacent-step move
    from the current state, filtered by experiment + cooldown."""
    cooldown = set(state.recently_modified[: config.PARAM_COOLDOWN_ITERATIONS])
    allowed = _allowed_knobs(state)
    options: list[tuple[str, Any, str]] = []
    for param in config.SEARCH_SPACE:
        if param not in allowed:
            continue
        if param in cooldown:
            continue
        current = state.current_params.get(param)
        for nv in _candidate_steps(param, current):
            if nv == current:
                continue
            options.append((param, nv, f"adjacent step ({current} -> {nv})"))
    if options:
        return options
    # Cooldown exhausted — relax it.
    for param in config.SEARCH_SPACE:
        if param not in allowed:
            continue
        current = state.current_params.get(param)
        for nv in _candidate_steps(param, current):
            if nv == current:
                continue
            options.append((param, nv, f"cooldown-relaxed step ({current} -> {nv})"))
    return options


def propose(state: State, rng: random.Random | None = None) -> Proposal | None:
    """Pick the next modification (single or multi-knob)."""
    rng = rng or random.Random(state.iteration)
    options = _build_single_knob_options(state)
    if not options:
        logger.warning("no proposals available — search space exhausted")
        return None

    # Try multi-knob if warmed up and dice roll says so.
    enable_multi = (
        state.iteration >= MULTI_KNOB_WARMUP
        and rng.random() < MULTI_KNOB_PROBABILITY
        and len(options) >= 4
    )
    if enable_multi:
        # Pick two non-overlapping knobs.
        idx_a = state.iteration % len(options)
        idx_b = (state.iteration * 7 + 3) % len(options)
        a = options[idx_a]
        b = options[idx_b]
        if a[0] != b[0]:  # different params
            return Proposal(
                changes=[
                    (a[0], state.current_params.get(a[0]), a[1]),
                    (b[0], state.current_params.get(b[0]), b[1]),
                ],
                rationale=f"multi-knob: {a[2]} + {b[2]}",
            )
        # Fallback to single

    # Single-knob round-robin.
    pick = options[state.iteration % len(options)]
    return Proposal(
        changes=[(pick[0], state.current_params.get(pick[0]), pick[1])],
        rationale=pick[2],
    )
