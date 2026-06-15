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
