"""ssr_instruments.py -- GC/MGC contract specs for the SSR battery (Builder 2).

NEW local specs, NOT edits to the shared backtest/futures/instruments.py
registry -- per SSR-battery/DESIGN.md section 3 ("Fills/costs"): "NEW local
specs (not edits to shared instruments.py): GC point $100/tick 0.1/round-turn
$6.00; MGC point $10/tick 0.1/round-turn $3.00."

    GC  = COMEX Gold (100 troy oz) -- point_value $100/pt, tick 0.1, tick_value $10, round-turn $6.00
    MGC = Micro Gold (10 troy oz)  -- point_value $10/pt,  tick 0.1, tick_value $1,  round-turn $3.00

spy_to_index: N/A for a commodity future (no SPY-proxy relationship exists,
same reasoning backtest/futures/instruments.py already applies to NQ/MNQ) --
set to None.

get_ssr(symbol): checks this module's local GC/MGC registry first, then
falls back to the shared backtest.futures.instruments.BY_SYMBOL registry
(ES/MES/NQ/MNQ) so callers get ONE lookup function across both registries.
Raises KeyError (never a silent None -- C7) if the symbol is in neither.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from backtest.futures.instruments import BY_SYMBOL as _SHARED_BY_SYMBOL  # noqa: E402
from backtest.futures.instruments import Instrument  # noqa: E402

GC = Instrument(
    symbol="GC",
    name="COMEX Gold (100 oz)",
    point_value=100.0,
    tick_size=0.1,
    tick_value=10.0,
    spy_to_index=None,
    round_turn_usd=6.00,
)

MGC = Instrument(
    symbol="MGC",
    name="Micro Gold (10 oz)",
    point_value=10.0,
    tick_size=0.1,
    tick_value=1.0,
    spy_to_index=None,
    round_turn_usd=3.00,
)

BY_SYMBOL: dict[str, Instrument] = {GC.symbol: GC, MGC.symbol: MGC}


def get_ssr(symbol: str) -> Instrument:
    """GC/MGC first (this module's local registry), then fall back to the
    shared ES/MES/NQ/MNQ registry in backtest.futures.instruments.BY_SYMBOL.
    Raises KeyError with the full known set if the symbol is in neither --
    never a silent None (C7)."""
    key = symbol.upper()
    if key in BY_SYMBOL:
        return BY_SYMBOL[key]
    if key in _SHARED_BY_SYMBOL:
        return _SHARED_BY_SYMBOL[key]
    raise KeyError(
        f"get_ssr: unknown instrument symbol {symbol!r}. "
        f"Known SSR-local symbols: {sorted(BY_SYMBOL)}; "
        f"known shared symbols: {sorted(_SHARED_BY_SYMBOL)}."
    )


__all__ = ["GC", "MGC", "BY_SYMBOL", "get_ssr"]
