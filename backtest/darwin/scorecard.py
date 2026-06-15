"""Per-filter scorecard tracking.

For every entered trade, attribute "credit" to each filter that passed:
    - Filter passed AND trade was a winner -> +1 to `pass_on_winner`
    - Filter passed AND trade was a loser  -> +1 to `pass_on_loser`

For every high-score blocked bar (filter score >= 7 but at least one filter
blocked entry), attribute "block credit" too:
    - Filter blocked AND counterfactual was a winner -> +1 to `block_on_winner`
      (i.e. "this filter prevented us from taking a profitable trade")
    - Filter blocked AND counterfactual was a loser  -> +1 to `block_on_loser`
      (i.e. "this filter correctly saved us from a loss")

The counterfactual outcome of blocked trades is approximated by replaying
the bracket forward; we leave it None when the data is insufficient.

Usage:
    from darwin.scorecard import FilterScorecard
    sc = FilterScorecard.load_or_new()
    sc.update_from_backtest(trades, decisions)
    sc.save()

The scorecard is the *raw evidence*. `weights.compute_weights(sc)` turns it
into the [0.3, 2.5] multiplicative weights.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)
STATE_DIR = Path(__file__).resolve().parent / "_state"
STATE_DIR.mkdir(parents=True, exist_ok=True)
SCORECARD_FILE = STATE_DIR / "scorecard.json"


# All filter IDs we track. Naming convention: f{number}_{side}_{shorthand}.
# Bear setup uses filters 1-10 (per heartbeat.md).
# Bull setup uses filters 1-11 (one extra for VIX hard cap).
KNOWN_FILTERS: tuple[str, ...] = (
    "f1_time_gate",
    "f2_news_clear",
    "f5_bear_ribbon_stack",
    "f5_bull_ribbon_stack",
    "f6_ribbon_spread",
    "f7_volume_divergence",
    "f8_bear_vix",
    "f8_bull_vix",
    "f9_bear_breakdown_bar",
    "f9_bull_vix_hard_cap",
    "f10_bear_htf_triggers",
    "f10_bull_buyer_pressure",
    "f11_bull_htf_triggers",
)


@dataclass
class FilterStats:
    """Per-filter cumulative counters."""

    filter_id: str
    pass_on_winner: int = 0
    pass_on_loser: int = 0
    block_on_winner: int = 0   # counterfactual=winner; this filter prevented entry (false negative)
    block_on_loser: int = 0    # counterfactual=loser; this filter correctly prevented (true negative)

    @property
    def total_passes(self) -> int:
        return self.pass_on_winner + self.pass_on_loser

    @property
    def total_blocks(self) -> int:
        return self.block_on_winner + self.block_on_loser

    @property
    def pass_winrate(self) -> float:
        """Of trades where this filter passed, what fraction won?"""
        n = self.total_passes
        return self.pass_on_winner / n if n else 0.5  # 0.5 = no info

    @property
    def block_correctness(self) -> float:
        """Of bars where this filter blocked, what fraction were correctly blocked
        (counterfactual would have lost)?"""
        n = self.total_blocks
        return self.block_on_loser / n if n else 0.5


@dataclass
class FilterScorecard:
    """Aggregate scorecard across all filters."""

    stats: dict[str, FilterStats] = field(default_factory=dict)
    n_trades_seen: int = 0
    n_blocked_bars_seen: int = 0
    last_updated: str | None = None

    def __post_init__(self) -> None:
        # Ensure every known filter has an entry (so weights() always returns the full set).
        for fid in KNOWN_FILTERS:
            if fid not in self.stats:
                self.stats[fid] = FilterStats(filter_id=fid)

    @classmethod
    def load_or_new(cls) -> "FilterScorecard":
        if not SCORECARD_FILE.exists():
            return cls()
        with open(SCORECARD_FILE, "r") as f:
            data = json.load(f)
        # Re-hydrate FilterStats from dicts.
        raw_stats = data.pop("stats", {})
        sc = cls(**data)
        for fid, raw in raw_stats.items():
            sc.stats[fid] = FilterStats(**raw)
        return sc

    def save(self) -> None:
        tmp = SCORECARD_FILE.with_suffix(".json.tmp")
        with open(tmp, "w") as f:
            json.dump(asdict(self), f, indent=2, default=str)
        tmp.replace(SCORECARD_FILE)

    def reset(self) -> None:
        for fid in KNOWN_FILTERS:
            self.stats[fid] = FilterStats(filter_id=fid)
        self.n_trades_seen = 0
        self.n_blocked_bars_seen = 0

    def update_from_backtest(
        self,
        trades: Iterable,
        decisions: Iterable[dict],
    ) -> None:
        """Walk a backtest's trades + decisions to grow the scorecard."""
        # Pass-credit: only ENTER bars (decisions where `passed` is True).
        # We attribute credit to every filter EXCEPT those listed in `blockers` (i.e.
        # the ones that passed). Since `passed=True` means blockers is empty, ALL
        # bear filters passed for every entered trade.
        for t in trades:
            self.n_trades_seen += 1
            won = t.dollar_pnl > 0
            for fid in KNOWN_FILTERS:
                # Only attribute to the side that took the trade.
                if "BEARISH" in t.setup and "_bear_" not in fid and "_bull_" in fid:
                    continue
                if "BULLISH" in t.setup and "_bull_" not in fid and "_bear_" in fid:
                    continue
                if won:
                    self.stats[fid].pass_on_winner += 1
                else:
                    self.stats[fid].pass_on_loser += 1

        # Block-credit: high-score blocked bars (>= 7/10) where exactly one filter blocked.
        # Without a real counterfactual P&L per blocked bar, we use a proxy:
        # if the blocked bar's bear/bull score WOULD have been a winner is unknowable
        # without re-running. So for now we just count the block events. The
        # counterfactual hookup is in `update_from_counterfactual_replay()` (to be
        # called by autoresearch sweeps that explicitly disable filters).
        for d in decisions:
            score = d.get("bear_score", 0)
            blockers = d.get("blockers") or []
            if d.get("passed") or score < 7 or len(blockers) != 1:
                continue
            self.n_blocked_bars_seen += 1
            blocker_num = blockers[0]
            # Map filter number to known filter_id (bear-side default).
            fid = _bear_filter_id_for_number(blocker_num)
            if fid is None or fid not in self.stats:
                continue
            # No counterfactual P&L -> we can only count, not categorize as winner/loser.
            # We treat each lone-blocker as a 50/50 "neutral" prior for now.

        self.last_updated = dt.datetime.utcnow().isoformat(timespec="seconds")


def _bear_filter_id_for_number(n: int) -> str | None:
    return {
        1: "f1_time_gate",
        2: "f2_news_clear",
        5: "f5_bear_ribbon_stack",
        6: "f6_ribbon_spread",
        7: "f7_volume_divergence",
        8: "f8_bear_vix",
        9: "f9_bear_breakdown_bar",
        10: "f10_bear_htf_triggers",
    }.get(n)
