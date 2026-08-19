"""trigger.py -- the weekly-lane entry trigger: zone return + structure shift AT the zone.

J's stated market philosophy (memory: feedback_j_market_philosophy_2026_07_28):
"supply/demand zones + wait for the return + STRUCTURE SHIFT at the zone;
never chase candles." This module is the mechanical form of that sentence,
applied on the 1H timeframe against the zones zones.py already computed from
daily bars:

  1. A market-structure event (BOS or CHoCH -- crypto.lib.market_structure)
     must be CONFIRMED on the LATEST closed 1H bar. Requiring the break on
     the newest bar (not "somewhere in the last N bars") IS the "never chase
     candles" rule in code -- a shift that happened three bars ago is stale,
     not a trigger.
  2. That same bar's close must sit INSIDE a zone's [price-width, price+width]
     band -- the shift must happen AT the level, not merely nearby. This is
     "wait for the return" plus "structure shift at the zone" collapsed into
     one check: if the break bar isn't inside any zone, there is no return.
  3. The touched zone's CONFLUENCE (how many DIFFERENT zone families overlap
     its price band) must meet MIN_ZONE_CONFLUENCE.

Direction comes directly from the structure event (bullish BOS/CHoCH -> call
bias, bearish -> put bias) -- NOT re-derived from the zone's role. A bullish
break confirmed at a support zone (price returned down into support, then
reversed up through it) is exactly the "wait for the return" case J
describes, and is a valid bullish signal even though the zone's role label is
"support"; re-deriving direction from role would incorrectly veto it.

NO ORDER IS PLACED HERE OR ANYWHERE IN STAGE A. This returns a WeeklySignal
for the (not-yet-built) shadow ledger to log -- shadow/paper-only per the
program doc and the house rule for this build.

Tunables: SWING_WINDOW_1H, MIN_ZONE_CONFLUENCE (both from
automation/state/weekly/params.json#signal) -- the other two of the lane's
4-tunable cap (ZONE_WIDTH_ATR_MULT, SWING_WINDOW_DAILY) belong to zones.py.
No 5th tunable is introduced anywhere in this module.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[2]  # weekly/lib/trigger.py -> weekly/lib -> weekly -> 42/
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from crypto.lib.bar import Bar  # noqa: E402
from crypto.lib.market_structure import analyze_structure  # noqa: E402

from weekly.lib.zones import Zone, load_weekly_params  # noqa: E402

Direction = Literal["bullish", "bearish"]


@dataclass(frozen=True, slots=True)
class WeeklySignal:
    symbol: str
    direction: Direction
    zone: Zone
    trigger_bar_index: int
    confluence_count: int
    # Soft, logged-only fields (params.json#signal.soft_logged_only) -- NEVER
    # a hard AND-gate here. Left None; a later module fills them in before
    # the shadow ledger write. Making these gates would add tunables beyond
    # the 4-cap and risk the L199 gate-cascade class of failure
    # (6 arms / 700 signals / 0 trades from stacked hard gates).
    iv_rank: float | None
    sector_heat_rs: float | None


def _confluence_count(zones: Sequence[Zone], target: Zone) -> int:
    """Number of DISTINCT zone families whose band overlaps `target`'s band."""
    lo, hi = target.price - target.width, target.price + target.width
    families = set()
    for z in zones:
        z_lo, z_hi = z.price - z.width, z.price + z.width
        if z_lo <= hi and z_hi >= lo:
            families.add(z.family)
    return len(families)


def detect_trigger(
    symbol: str,
    zones: Sequence[Zone],
    hourly_bars: Sequence[Bar],
    *,
    params: dict | None = None,
) -> WeeklySignal | None:
    """Return a WeeklySignal if the trigger fires on the LATEST closed 1H
    bar, else None. `hourly_bars` must already be closed-only (weekly.lib.
    bars.fetch_hourly + dataframe_to_bars) -- this function does not re-check
    closedness, it only reads structure off whatever bars it is given.
    """
    if not hourly_bars:
        return None
    if params is None:
        params = load_weekly_params()
    sig = params["signal"]
    window = int(sig["SWING_WINDOW_1H"])
    min_confluence = int(sig["MIN_ZONE_CONFLUENCE"])

    read = analyze_structure(hourly_bars, window=window)
    if not read.events:
        return None  # zone(s) may have been touched, but no structure shift at all -- no trigger

    last_event = read.events[-1]
    if last_event.break_index != len(hourly_bars) - 1:
        return None  # the shift is stale (not on the newest bar) -- "never chase candles"

    break_bar = hourly_bars[last_event.break_index]
    touched = [z for z in zones if (z.price - z.width) <= break_bar.close <= (z.price + z.width)]
    if not touched:
        return None  # structure shift happened, but not AT a zone -- no "return to zone"

    zone = min(touched, key=lambda z: abs(z.price - break_bar.close))
    confluence = _confluence_count(zones, zone)
    if confluence < min_confluence:
        return None

    direction: Direction = "bullish" if last_event.direction == "bullish" else "bearish"
    return WeeklySignal(
        symbol=symbol,
        direction=direction,
        zone=zone,
        trigger_bar_index=last_event.break_index,
        confluence_count=confluence,
        iv_rank=None,
        sector_heat_rs=None,
    )
