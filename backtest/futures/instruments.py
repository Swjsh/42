"""CME futures instrument specs for the 42 Futures Edition (verified vs CME, 2026-06).

Sources: CME Group contract specs; tick values confirmed via search 2026-06-14.
  ES  E-mini S&P 500       : $50 x index, tick 0.25 = $12.50
  MES Micro E-mini S&P 500 : $5  x index, tick 0.25 = $1.25   (1/10 ES)
  NQ  E-mini Nasdaq-100    : $20 x index, tick 0.25 = $5.00
  MNQ Micro E-mini Nasdaq  : $2  x index, tick 0.25 = $0.50   (1/10 NQ)

spy_to_index: multiplier to APPROXIMATE the index level from SPY price, for the
proxy backtest (SPY tracks S&P500/10, so S&P500 ~= SPY*10 ~= ES/MES index).
NASDAQ products have NO SPY proxy (different index) -> None; need real MNQ/NQ bars.

round_turn_usd: commissions + exchange/NFA fees per contract round-turn (retail IBKR-ish;
prop firms ~similar). Micros ~ $1.24 round-turn; minis ~ $4.00. Conservative.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Instrument:
    symbol: str
    name: str
    point_value: float          # $ per 1.00 index point per contract
    tick_size: float            # min increment (index points)
    tick_value: float           # $ per tick
    spy_to_index: Optional[float]  # SPY price * this ~= index level (proxy); None if no SPY proxy
    round_turn_usd: float       # commissions + fees per contract round-turn


ES  = Instrument("ES",  "E-mini S&P 500",        50.0, 0.25, 12.50, 10.0, 4.00)
MES = Instrument("MES", "Micro E-mini S&P 500",   5.0, 0.25,  1.25, 10.0, 1.24)
NQ  = Instrument("NQ",  "E-mini Nasdaq-100",      20.0, 0.25,  5.00, None, 4.00)
MNQ = Instrument("MNQ", "Micro E-mini Nasdaq-100", 2.0, 0.25,  0.50, None, 1.24)

BY_SYMBOL = {i.symbol: i for i in (ES, MES, NQ, MNQ)}


def get(symbol: str) -> Instrument:
    return BY_SYMBOL[symbol.upper()]


# --------------------------------------------------------------------------- #
# Tick alignment
#
# SCAR (2026-08-31): every bracket the TastytradeBroker lane tried to place was
# rejected with `invalid_price_increment: Price must be in increments of $0.25`
# -- e.g. stops at 7704.05, 7694.30, 7826.10. The signal generator emits raw
# dollar offsets (entry -/+ N points of ATR-ish distance) and nothing ever
# snapped them to the contract's tick, so the STOP leg was refused, which
# aborted the whole bracket and turned every entry into ENTER_REFUSED. The
# fill simulator has no such validation, so the sim lane traded happily while
# the real-broker lane sat at exactly its starting net_liq for 10 sessions and
# no alert fired. Root cause in one sentence: prices were never rounded to
# `Instrument.tick_size` before being sent to a broker that enforces it.
#
# DIRECTION MATTERS. `futures_trader_core` sizes the position from
# `stop_points = |entry - stop|` BEFORE placing. Widening a stop after sizing
# would make real risk exceed the risk the rails approved, so callers must
# round FIRST and then size off the rounded values. `snap_protective` rounds a
# protective level toward the entry (never wider => never more risk than
# sized); `snap` is plain nearest-tick for entries and targets.
# --------------------------------------------------------------------------- #

def snap(price: float, tick: float) -> float:
    """Nearest valid tick. Use for entry and profit targets."""
    if not tick or tick <= 0:
        return float(price)
    steps = round(float(price) / tick)
    # Re-round to kill binary float dust (7704.050000000001 -> 7704.05 -> 7704.0).
    return round(steps * tick, 10)


def snap_protective(price: float, tick: float, *, entry: float) -> float:
    """Snap a STOP toward `entry` -- tighter or equal, never wider.

    Never-wider is the safety property: the position was sized off this
    distance, so rounding away from entry would silently exceed the approved
    per-trade risk.
    """
    import math

    if not tick or tick <= 0:
        return float(price)
    price = float(price)
    entry = float(entry)
    steps = price / tick
    if price >= entry:          # stop above entry => a SHORT => round DOWN toward entry
        snapped = math.floor(steps + 1e-9) * tick
    else:                       # stop below entry => a LONG => round UP toward entry
        snapped = math.ceil(steps - 1e-9) * tick
    return round(snapped, 10)


def is_aligned(price: float, tick: float) -> bool:
    """True when `price` sits exactly on a tick boundary (float-dust tolerant)."""
    if not tick or tick <= 0:
        return True
    steps = float(price) / tick
    return abs(steps - round(steps)) < 1e-6
