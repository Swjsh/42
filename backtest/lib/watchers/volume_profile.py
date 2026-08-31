"""VOLUME_PROFILE — a stateless, look-ahead-safe rolling volume-profile shelf engine.

PURPOSE (chef R&D, 2026-08-31, from strategy/candidates/_chef-inbox/
2026-07-10-prospector-volume_shelf_tv_vp.md — J-directed prospector idea, 2026-07-09):
  TradingView's Volume Profile (Visible Range) study buckets traded volume into
  horizontal price bins over a lookback window. High-Volume Nodes (HVN, "shelves")
  mark prices where the market spent the most time/volume — the thesis (independent
  of Gamma's trendline/swing-pivot LEVEL_MEMORY engine, see level_memory.py) is that
  price pauses, rejects, or accelerates through these nodes.

  This module computes the SAME structural idea directly from cached SPY 5m OHLCV+
  volume bars (no TradingView MCP dependency — confirmed unavailable to a
  conductor-class session, see the 2026-07-23 chef-inbox note) and is null-tested
  the IDENTICAL way LEVEL_MEMORY was (see volume_profile_null_test.py): H1 vs a
  random-price null and a random-entry null, C25/C27 discipline (does a stronger
  node predict a bigger reaction, or is "high volume" a hindsight label?).

DESIGN CONTRACT (mirrors level_memory.py exactly):
  - STATELESS: no persisted state. Given a DataFrame of 5m bars, `.shelves_at(i)` and
    `.snapshot(i)` derive everything from bars <= i only.
  - LOOK-AHEAD-SAFE: the profile at bar i is built ONLY from bars with index <= i,
    within a trailing `lookback_days`-day window. A planted-future bar's volume MUST
    NOT be visible at an earlier bar. Guard: test_volume_profile_shelf_2026_08_31.py.
  - Volume is assigned to price bins via the bar's TYPICAL PRICE ((h+l+c)/3), NOT a
    tick-level split — this repo has no intrabar tick/quote data, so this is the
    standard OHLCV-only approximation (matches the "volume-weighted price histogram"
    framing in the chef-inbox item, not exact intrabar VAP but the same signal class).
  - A SHELF (HVN) is a local-maximum bin: its volume exceeds both neighbor bins.
    Its "strength" is the bin's share of total window volume (0..1). The single
    highest-volume bin in the window is the POC (Point of Control).

This module returns SPY-PRICE structure only — options P&L is a separate C3
question, established AFTER a price-structure edge is proven (same discipline as
level_memory.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

# ── Tunable structural constants (documented, not magic) ─────────────────────

# Trailing lookback for the rolling profile — long enough to build a real
# volume histogram, short enough to stay "recent structure" not all-time.
DEFAULT_LOOKBACK_DAYS: int = 10

# Bin width in dollars. ~0.30% of SPY at $750 = $2.25; use a fixed $0.50 bin,
# comparable granularity to LEVEL_MEMORY's CLUSTER_TOL=0.35 but coarser since a
# volume histogram (unlike swing-pivot clustering) needs bins wide enough to
# accumulate meaningful volume mass per bin over ~10 days of 5m bars.
BIN_WIDTH: float = 0.50

# Touch/reject tolerance in dollars — a bar "interacts" with a shelf if its
# high/low comes within this of the shelf's price. Matches level_memory.TOUCH_TOL.
TOUCH_TOL: float = 0.20

# A bin must hold at least this fraction of the window's total volume to count
# as an HVN shelf (filters out noise bins in a mostly-flat histogram).
MIN_SHELF_SHARE: float = 0.015

# Cap on shelves returned per snapshot (highest-strength first) — keeps the
# nearest-shelf lookup cheap and avoids flagging every minor local max as a shelf.
MAX_SHELVES: int = 8


@dataclass(frozen=True)
class Shelf:
    """A high-volume-node price shelf, as seen at a given eval bar."""
    price: float          # bin center
    strength: float       # this bin's volume / window total volume (0..1)
    is_poc: bool          # True iff this is the single highest-volume bin in window
    window_start_idx: int
    window_end_idx: int


@dataclass(frozen=True)
class ShelfInteraction:
    """The current bar's interaction (if any) with the nearest-touched shelf."""
    kind: str  # "touch" | "reject" | "break" | "none"
    shelf: Optional[Shelf]
    distance: float  # signed: close - shelf.price
    detail: str = ""


@dataclass(frozen=True)
class VPSnapshot:
    idx: int
    timestamp_et: pd.Timestamp
    close: float
    shelves: tuple[Shelf, ...]
    interaction: ShelfInteraction


def _typical_price(row) -> float:
    return float((row["high"] + row["low"] + row["close"]) / 3.0)


class VolumeProfile:
    """Stateless rolling volume-profile shelf engine over a 5m OHLCV+volume frame.

    Usage:
        vp = VolumeProfile(df)                 # df: timestamp_et,open,high,low,close,volume
        snap = vp.snapshot(i)                  # everything at bar i, causal
        shelves = vp.shelves_at(i, lookback_days)
    """

    def __init__(self, df: pd.DataFrame):
        d = df.copy().reset_index(drop=True)
        if "timestamp_et" in d.columns:
            d["timestamp_et"] = pd.to_datetime(d["timestamp_et"], utc=True).dt.tz_convert("America/New_York")
        for col in ("open", "high", "low", "close", "volume"):
            d[col] = pd.to_numeric(d[col], errors="coerce")
        self.df = d

    def _lookback_start_idx(self, up_to_idx: int, lookback_days: int) -> int:
        """First bar index within `lookback_days` calendar trading days of bar up_to_idx.
        Identical convention to LevelMemory._lookback_start_idx (causal by construction)."""
        dates_series = self.df["timestamp_et"].dt.date
        unique_days = sorted(set(dates_series.iloc[: up_to_idx + 1]))
        keep_days = set(unique_days[-lookback_days:]) if lookback_days > 0 else set(unique_days)
        mask = dates_series.iloc[: up_to_idx + 1].isin(keep_days)
        first = mask[mask].index.min()
        return int(first)

    def shelves_at(
        self, up_to_idx: int, lookback_days: int = DEFAULT_LOOKBACK_DAYS, bin_width: float = BIN_WIDTH,
    ) -> list[Shelf]:
        """Return HVN shelves visible at bar up_to_idx, using ONLY bars <= up_to_idx."""
        start = self._lookback_start_idx(up_to_idx, lookback_days)
        window = self.df.iloc[start : up_to_idx + 1]
        if len(window) < 3:
            return []

        typical = (window["high"] + window["low"] + window["close"]) / 3.0
        vol = window["volume"].values
        total_vol = float(vol.sum())
        if total_vol <= 0:
            return []

        lo = float(typical.min())
        hi = float(typical.max())
        if hi - lo < bin_width:
            return []

        n_bins = max(3, int(np.ceil((hi - lo) / bin_width)))
        edges = lo + np.arange(n_bins + 1) * bin_width
        bin_idx = np.clip(np.digitize(typical.values, edges) - 1, 0, n_bins - 1)

        bin_vol = np.zeros(n_bins)
        for b, v in zip(bin_idx, vol):
            bin_vol[b] += v

        bin_centers = edges[:-1] + bin_width / 2.0
        bin_share = bin_vol / total_vol

        poc_bin = int(np.argmax(bin_vol))

        shelves: list[Shelf] = []
        for b in range(n_bins):
            if bin_share[b] < MIN_SHELF_SHARE:
                continue
            # local maximum: strictly >= both neighbors (edge bins compare to the
            # one neighbor they have) — a plateau's first bin counts once.
            left_ok = (b == 0) or (bin_vol[b] >= bin_vol[b - 1])
            right_ok = (b == n_bins - 1) or (bin_vol[b] >= bin_vol[b + 1])
            if not (left_ok and right_ok):
                continue
            shelves.append(
                Shelf(
                    price=round(float(bin_centers[b]), 2),
                    strength=float(bin_share[b]),
                    is_poc=(b == poc_bin),
                    window_start_idx=start,
                    window_end_idx=up_to_idx,
                )
            )

        shelves.sort(key=lambda s: s.strength, reverse=True)
        return shelves[:MAX_SHELVES]

    @staticmethod
    def _interaction_for_shelf(row, shelf: Shelf, ref_close_prior: float) -> ShelfInteraction:
        """Classify how the CURRENT bar interacted with ONE shelf.

        Directionality (role) is inferred causally from where the PRIOR close sat
        relative to the shelf (no look-ahead: never uses the current bar's own
        close to decide which side we're approaching from) — mirrors
        level_memory.py's role-from-close-side convention, but recomputed fresh
        each bar since a volume shelf (unlike a swing-pivot level) carries no
        persistent role/role-flip history of its own.
        """
        hi, lo, cl = row["high"], row["low"], row["close"]
        sp = shelf.price
        dist = float(cl - sp)
        interacted = (lo - TOUCH_TOL) <= sp <= (hi + TOUCH_TOL)
        if not interacted:
            return ShelfInteraction(kind="none", shelf=shelf, distance=dist, detail="no contact")

        approaching_from_below = ref_close_prior < sp
        if approaching_from_below:
            # shelf acts like resistance: expect a reject DOWN
            if hi > sp + 1e-9 and cl < sp - 1e-9:
                kind, detail = "reject", f"wicked above shelf {sp:.2f}, closed below"
            elif cl >= sp + TOUCH_TOL:
                kind, detail = "break", f"closed above shelf {sp:.2f}"
            else:
                kind, detail = "touch", f"touched shelf {sp:.2f} from below"
        else:
            # shelf acts like support: expect a reject UP
            if lo < sp - 1e-9 and cl > sp + 1e-9:
                kind, detail = "reject", f"wicked below shelf {sp:.2f}, closed above"
            elif cl <= sp - TOUCH_TOL:
                kind, detail = "break", f"closed below shelf {sp:.2f}"
            else:
                kind, detail = "touch", f"touched shelf {sp:.2f} from above"

        return ShelfInteraction(kind=kind, shelf=shelf, distance=dist, detail=detail)

    def snapshot(
        self, up_to_idx: int, lookback_days: int = DEFAULT_LOOKBACK_DAYS, bin_width: float = BIN_WIDTH,
    ) -> VPSnapshot:
        """Full causal snapshot at bar up_to_idx: shelves + the most salient interaction."""
        shelves = self.shelves_at(up_to_idx, lookback_days, bin_width)
        row = self.df.iloc[up_to_idx]

        best: Optional[ShelfInteraction] = None
        if up_to_idx > 0 and shelves:
            prior_close = float(self.df["close"].iloc[up_to_idx - 1])
            _RANK = {"reject": 3, "break": 2, "touch": 1, "none": 0}
            for shelf in shelves:
                inter = self._interaction_for_shelf(row, shelf, prior_close)
                if inter.kind == "none":
                    continue
                if best is None or _RANK[inter.kind] > _RANK[best.kind] or (
                    _RANK[inter.kind] == _RANK[best.kind] and shelf.strength > best.shelf.strength
                ):
                    best = inter

        if best is None:
            best = ShelfInteraction(kind="none", shelf=None, distance=0.0)

        return VPSnapshot(
            idx=up_to_idx,
            timestamp_et=row["timestamp_et"],
            close=float(row["close"]),
            shelves=tuple(shelves),
            interaction=best,
        )
