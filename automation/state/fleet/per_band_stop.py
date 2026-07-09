"""per_band_stop -- premium-band-conditional stop resolver (T-W4, exit-B's machinery).

THE GAP THIS CLOSES: `ExitState.from_entry` (exit_manager.py) freezes `premium_stop_pct`
at entry from a single scalar in the strategy's ExitShape. exit-B
(entry-exit-matrix-stop-a-preregistration.json `exit-B-perband-hybrid`) proposes a
STOP THAT DEPENDS ON THE ENTRY PREMIUM ITSELF (T2's per-band diagnostics: cheap contracts
need a moderate stop because a tight %-stop is only 1-2 ticks there; richer contracts can
take the wide -50% catastrophe cap). That is not expressible as one scalar.

THE FIX (this module): a PURE resolver, `resolve_stop_pct(entry_premium, band_table) ->
stop_pct`, called ONCE at entry time by BOTH lanes (fleet_executor's plan builder AND
heartbeat_core's `_execute`) BEFORE `ExitState.from_entry` -- one function, two call
sites, one guard. `from_entry` itself does not change: it still takes a single
`premium_stop_pct` field: the CALLER resolves the band first and passes the result in.

STATUS: SHADOW ONLY. No arm consumes this yet -- it is pure, unit-tested, unwired.
Wiring exit-B behind this resolver needs its own P5-survivor pass + STOP-B sign-off
(HANDOFF-2026-07-11-CONFIRM-AND-WIRE, WIRING MAP). The engine-contract card renders this
module's EXIT_B_BAND_TABLE explicitly labelled "not armed" (rule 17: a new knob must be
visible on the card the moment it exists, even before anything consumes it).
"""
from __future__ import annotations

from typing import NamedTuple, Sequence


class StopBand(NamedTuple):
    """One band: entry_premium < ceiling picks this band's stop_pct. The LAST band in a
    table must have ceiling=None (the catch-all ">=" band) -- bands are contiguous and
    sorted ascending, so only a ceiling is needed (the previous band's ceiling IS this
    band's implicit floor)."""
    ceiling: float | None
    stop_pct: float          # negative, e.g. -0.25


def resolve_stop_pct(entry_premium: float, band_table: Sequence[StopBand]) -> float:
    """Return the stop_pct for the band `entry_premium` falls into.

    band_table must be non-empty, sorted ascending by ceiling, with ONLY the last entry
    having ceiling=None. Raises ValueError on a malformed table (fail loud, never guess --
    this runs once at entry time, not on a hot per-tick path, so raising is cheap and safe).
    """
    if not band_table:
        raise ValueError("band_table must not be empty")
    for band in band_table[:-1]:
        if band.ceiling is None:
            raise ValueError("only the LAST band in band_table may have ceiling=None")
        if entry_premium < band.ceiling:
            return band.stop_pct
    last = band_table[-1]
    if last.ceiling is not None:
        raise ValueError("the LAST band in band_table must be the catch-all (ceiling=None)")
    return last.stop_pct


# exit-B's pre-registered band table (analysis/recommendations/
# entry-exit-matrix-stop-a-preregistration.json, candidate "exit-B-perband-hybrid"):
# <$0.20 -> -25% | $0.20-$0.50 -> -35% | >=$0.50 -> -50% (the exit-A catastrophe cap).
# NOT ARMED -- no arm/strategy consumes this table yet (see module docstring + T-W7/STOP-B).
EXIT_B_BAND_TABLE: tuple[StopBand, ...] = (
    StopBand(ceiling=0.20, stop_pct=-0.25),
    StopBand(ceiling=0.50, stop_pct=-0.35),
    StopBand(ceiling=None, stop_pct=-0.50),
)
