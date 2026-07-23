"""backtest/tools/ribbon_scope_compare.py -- per-bar RTH-vs-ETH ribbon scope comparator.

RIBBON-SESSION-SCOPE-DIVERGENCE PART C (automation/overnight/queue.md 2026-07-23, "Lane-A
ship prep"): a small function `dojo/whisper.py` (or any other caller) can call at a given
(day, bar) to learn whether the RTH-scope ribbon (today's production/backtest scope --
`backtest/lib/ribbon.py` over the RTH-only close series) and the ETH-scope ribbon
(`backtest/tools/eth_ribbon.py`, validated in
analysis/recommendations/eth-ribbon-parity-2026-07-23.md: stack concordance vs TV 90% ETH
vs 43% RTH) AGREE on stack classification at that bar -- the calibration signal the Part-1
whisper/brief flag needs on gap mornings ("my ribbon differs from your chart's by $X here").

SCOPE: this module ONLY answers "do the two scopes agree here, and by how much". It does
NOT wire into the dojo whisper/brief itself (the orchestrator does that separately, per this
fire's Part C instruction: "the orchestrator wires the whisper/brief flag after"). No live
trading-path import, no broker import (guard-tested below, mirrors test_dojo_fence.py's
pattern for the rest of the dojo/backtest-tools family).

BOTH scopes are computed from the IDENTICAL underlying bar source
(`eth_ribbon.load_eth_frame()`) -- RTH is simply the 09:30-16:00 subset of that same frame --
so a disagreement between the two can ONLY be attributed to session scope, never to a data
source mismatch between the two calls (apples-to-apples by construction).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import time as dtime
from pathlib import Path
from typing import Optional

import pandas as pd

_ROOT = Path(__file__).resolve().parents[2]  # .../42
_BACKTEST_DIR = str(_ROOT / "backtest")
if _BACKTEST_DIR not in sys.path:
    sys.path.insert(0, _BACKTEST_DIR)

from lib.ribbon import compute_ribbon, RibbonState  # noqa: E402 -- reused verbatim
from tools.eth_ribbon import load_eth_frame, compute_eth_ribbon, ribbon_at_ts  # noqa: E402

RTH_OPEN = dtime(9, 30)
RTH_CLOSE = dtime(16, 0)


@dataclass(frozen=True)
class ScopeComparison:
    """Frozen contract: given a day + bar, {rth_stack, eth_stack, agree, max_ema_diff} plus
    the full states for callers that want the raw EMA levels too."""
    day: str
    bar_et: str
    rth_stack: "str | None"
    eth_stack: "str | None"
    agree: bool
    max_ema_diff: "float | None"   # max |fast/pivot/slow diff| between scopes; None if either
                                    # side is still WARMUP (insufficient bars for that EMA)
    rth_state: "RibbonState | None"
    eth_state: "RibbonState | None"

    def to_dict(self) -> dict:
        return {
            "day": self.day, "bar_et": self.bar_et,
            "rth_stack": self.rth_stack, "eth_stack": self.eth_stack,
            "agree": self.agree, "max_ema_diff": self.max_ema_diff,
        }


_CACHE: dict = {}  # module-level memo: ONE build per process (rebuilt only if cache cleared)


def _normalize_ts(bar_et) -> pd.Timestamp:
    ts = pd.Timestamp(bar_et)
    if ts.tzinfo is not None:
        ts = ts.tz_localize(None)
    return ts


def _ribbons_cached() -> "tuple[pd.DataFrame, pd.DataFrame]":
    """(rth_ribbon_df, eth_ribbon_df), each carrying timestamp_et + fast/pivot/slow/stack.
    Built ONCE per process from the SAME eth_ribbon.load_eth_frame() source (RTH is the
    09:30-16:00 subset of that identical frame) -- apples-to-apples by construction, never
    two independently-fetched series."""
    if "rth" not in _CACHE:
        frame = load_eth_frame()
        eth_df = compute_eth_ribbon(frame)
        rth_mask = ((frame["timestamp_et"].dt.time >= RTH_OPEN) &
                    (frame["timestamp_et"].dt.time < RTH_CLOSE))
        rth_frame = frame.loc[rth_mask].reset_index(drop=True)
        rth_df = compute_ribbon(rth_frame["close"])
        rth_df["timestamp_et"] = rth_frame["timestamp_et"].reset_index(drop=True)
        _CACHE["rth"] = rth_df
        _CACHE["eth"] = eth_df
    return _CACHE["rth"], _CACHE["eth"]


def clear_cache() -> None:
    """Test/dev hook -- forces the next compare_at() call to rebuild both frames (e.g. after
    the underlying cache files change)."""
    _CACHE.clear()


def latest_available_day(before: "str | None" = None) -> "str | None":
    """Most recent trading day with at least one non-WARMUP RTH ribbon stack in the cached
    frame, strictly before `before` (YYYY-MM-DD) if given, else the latest day overall.
    Callers (e.g. daily_brief.py's premarket morning-brief, which runs BEFORE today's own
    bars exist) use this to find the most recent day they CAN honestly report on -- never
    fabricates a day that has no data. Returns None if no such day exists."""
    rth_df, _eth_df = _ribbons_cached()
    valid = rth_df[rth_df["stack"] != "WARMUP"]
    if valid.empty:
        return None
    days = sorted({ts.date().isoformat() for ts in valid["timestamp_et"]})
    if before is not None:
        days = [d for d in days if d < before]
    return days[-1] if days else None


def compare_at(day: str, bar_et) -> ScopeComparison:
    """Given a trading day (str, informational -- not used to filter, `bar_et` alone
    resolves the row) and a specific RTH bar timestamp, return whether the RTH-scope and
    ETH-scope ribbon AGREE on stack classification at that bar, and the max EMA-level
    disagreement between the two scopes. Both `rth_stack`/`eth_stack` are None (agree=False)
    on a bar that hasn't warmed up yet in that scope -- never fabricated."""
    ts = _normalize_ts(bar_et)
    rth_df, eth_df = _ribbons_cached()
    rth_state = ribbon_at_ts(rth_df, ts)
    eth_state = ribbon_at_ts(eth_df, ts)

    rth_stack = rth_state.stack if rth_state else None
    eth_stack = eth_state.stack if eth_state else None
    agree = bool(rth_stack) and bool(eth_stack) and rth_stack == eth_stack

    max_diff: Optional[float] = None
    if rth_state and eth_state:
        max_diff = round(max(
            abs(rth_state.fast - eth_state.fast),
            abs(rth_state.pivot - eth_state.pivot),
            abs(rth_state.slow - eth_state.slow),
        ), 4)

    return ScopeComparison(
        day=day, bar_et=ts.isoformat(),
        rth_stack=rth_stack, eth_stack=eth_stack, agree=agree, max_ema_diff=max_diff,
        rth_state=rth_state, eth_state=eth_state,
    )


if __name__ == "__main__":
    # smoke: compare a known gap-morning bar from the Part-A validation set
    r = compare_at("2026-06-16", "2026-06-16 09:30:00")
    print(f"[ribbon_scope_compare] {r.to_dict()}")
