"""Convert per-filter scorecard data into multiplicative Darwinian weights.

Mapping (ATLAS pattern):
    pass_winrate < 0.40  -> bottom quartile -> weight *= 0.95
    pass_winrate > 0.60  -> top quartile    -> weight *= 1.05
    otherwise            -> middle          -> weight unchanged

Bounds: weight is clamped to [0.3, 2.5]. The asymmetric clamp matches ATLAS:
a "bad" filter never disappears entirely (0.3 floor) but a "great" filter
caps influence (2.5 ceiling).

The weights are ADVISORY by default. They show up in:
    1. autoresearch.proposer (low-weight filters get higher modification priority)
    2. dashboard / journal as analytics
    3. heartbeat live engine (NOT YET — would replace `bear_score >= N` logic)
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .scorecard import KNOWN_FILTERS, FilterScorecard

logger = logging.getLogger(__name__)
STATE_DIR = Path(__file__).resolve().parent / "_state"
STATE_DIR.mkdir(parents=True, exist_ok=True)
WEIGHTS_FILE = STATE_DIR / "weights.json"


# Bounds + step sizes, ATLAS-style.
WEIGHT_FLOOR = 0.3
WEIGHT_CEILING = 2.5
INITIAL_WEIGHT = 1.0
UP_MULTIPLIER = 1.05
DOWN_MULTIPLIER = 0.95
TOP_QUARTILE_WINRATE = 0.60
BOTTOM_QUARTILE_WINRATE = 0.40
MIN_PASSES_FOR_WEIGHT_CHANGE = 5  # don't move weights on tiny samples


@dataclass
class FilterWeights:
    """Persistent weight table."""

    weights: dict[str, float] = field(default_factory=dict)
    updated_at: str | None = None
    n_updates: int = 0

    def __post_init__(self) -> None:
        for fid in KNOWN_FILTERS:
            self.weights.setdefault(fid, INITIAL_WEIGHT)

    @classmethod
    def load_or_new(cls) -> "FilterWeights":
        if not WEIGHTS_FILE.exists():
            return cls()
        with open(WEIGHTS_FILE, "r") as f:
            return cls(**json.load(f))

    def save(self) -> None:
        tmp = WEIGHTS_FILE.with_suffix(".json.tmp")
        with open(tmp, "w") as f:
            json.dump(asdict(self), f, indent=2, default=str)
        tmp.replace(WEIGHTS_FILE)

    def reset(self) -> None:
        self.weights = {fid: INITIAL_WEIGHT for fid in KNOWN_FILTERS}
        self.n_updates = 0
        self.updated_at = None


def update_from_scorecard(
    fw: FilterWeights, sc: FilterScorecard, *, dry_run: bool = False
) -> dict[str, tuple[float, float, str]]:
    """One Darwinian step. Returns {filter_id: (old, new, reason)}.

    A filter only moves if it has at least MIN_PASSES_FOR_WEIGHT_CHANGE
    pass observations in the scorecard (avoid moving on noise).
    """
    changes: dict[str, tuple[float, float, str]] = {}
    for fid, stats in sc.stats.items():
        old = fw.weights.get(fid, INITIAL_WEIGHT)
        new = old
        reason = "no-change"
        if stats.total_passes < MIN_PASSES_FOR_WEIGHT_CHANGE:
            reason = f"too few passes ({stats.total_passes}<{MIN_PASSES_FOR_WEIGHT_CHANGE})"
        else:
            wr = stats.pass_winrate
            if wr >= TOP_QUARTILE_WINRATE:
                new = min(WEIGHT_CEILING, old * UP_MULTIPLIER)
                reason = f"top quartile (wr={wr:.2f}, n={stats.total_passes})"
            elif wr <= BOTTOM_QUARTILE_WINRATE:
                new = max(WEIGHT_FLOOR, old * DOWN_MULTIPLIER)
                reason = f"bottom quartile (wr={wr:.2f}, n={stats.total_passes})"
            else:
                reason = f"middle (wr={wr:.2f}, n={stats.total_passes})"
        if abs(new - old) > 1e-9:
            changes[fid] = (old, new, reason)
            if not dry_run:
                fw.weights[fid] = new

    if not dry_run:
        fw.updated_at = dt.datetime.utcnow().isoformat(timespec="seconds")
        fw.n_updates += 1
    return changes


def low_weight_filters(fw: FilterWeights, threshold: float = 0.7) -> list[str]:
    """Filters whose weight has drifted below `threshold` — candidates for
    autoresearch attention. Returned sorted by weight ascending."""
    items = [(fid, w) for fid, w in fw.weights.items() if w < threshold]
    items.sort(key=lambda x: x[1])
    return [fid for fid, _ in items]


def high_weight_filters(fw: FilterWeights, threshold: float = 1.3) -> list[str]:
    """Filters with weight > `threshold` — known-good signal sources."""
    items = [(fid, w) for fid, w in fw.weights.items() if w > threshold]
    items.sort(key=lambda x: -x[1])
    return [fid for fid, _ in items]


def weighted_setup_score(passing_filter_ids: list[str], fw: FilterWeights) -> float:
    """Sum of weights for passing filters. Used by the (optional) weighted-entry mode."""
    return sum(fw.weights.get(fid, INITIAL_WEIGHT) for fid in passing_filter_ids)
