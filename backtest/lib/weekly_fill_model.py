"""Spread-aware fill model for the weekly lane's multi-day backtest.

WHY THIS EXISTS SEPARATELY FROM THE SPY FILL MODEL
--------------------------------------------------
The SPY 0DTE path models fills against 1-minute OPRA bars with real quotes. The weekly lane
has neither: its cached history is DAILY bars (backtest/data/weekly-options/), which carry
OHLCV but no bid/ask at all. Pretending otherwise is how a backtest invents money.

So the spread is modeled EXPLICITLY as a fraction of premium rather than measured, and every
result that uses this model must carry `spread_pct_assumed` so no reader mistakes a modeled
cost for an observed one.

A marketable order crosses the full spread on a round trip: you buy at the ask and sell at the
bid. Treating the bar price as the mid, entry pays +half-spread and exit receives -half-spread.

DEFAULT SOURCE: params.json entry.liquidity_gate.max_spread_pct_of_premium is the WIDEST
spread the live gate would accept (5%). Using it as the default here is deliberately
pessimistic -- the modeled cost is the worst spread we would ever have traded, not the average
one. Backtests that want the realistic case must pass a measured value and say where it came
from. Being wrong in the pessimistic direction is survivable; the optimistic direction is how
a losing strategy ships.
"""

from __future__ import annotations

from dataclasses import dataclass

# The live gate's ceiling, used as a pessimistic default. Not a tunable: callers pass an
# explicit value when they have a measured one.
DEFAULT_SPREAD_PCT = 0.05


class FillModelError(ValueError):
    """Raised on nonsense inputs so a bad backtest fails loud instead of returning a price."""


@dataclass(frozen=True)
class Fill:
    price: float
    mid: float
    spread_pct: float
    side: str  # "buy" | "sell"

    @property
    def slippage(self) -> float:
        """Signed cost vs the mid. Positive = paid more / received less than mid."""
        return abs(self.price - self.mid)


def _validate(mid: float, spread_pct: float) -> None:
    if mid is None or mid <= 0:
        raise FillModelError(f"mid must be > 0 (got {mid!r})")
    if spread_pct is None or spread_pct < 0 or spread_pct >= 2:
        raise FillModelError(
            f"spread_pct must be a fraction in [0, 2) (got {spread_pct!r}); "
            f"pass 0.05 for 5%, not 5"
        )


def buy_fill(mid: float, spread_pct: float = DEFAULT_SPREAD_PCT) -> Fill:
    """Entry: pay the ask = mid * (1 + spread/2)."""
    _validate(mid, spread_pct)
    return Fill(price=mid * (1.0 + spread_pct / 2.0), mid=mid, spread_pct=spread_pct, side="buy")


def sell_fill(mid: float, spread_pct: float = DEFAULT_SPREAD_PCT) -> Fill:
    """Exit: receive the bid = mid * (1 - spread/2), floored at zero."""
    _validate(mid, spread_pct)
    return Fill(
        price=max(0.0, mid * (1.0 - spread_pct / 2.0)),
        mid=mid,
        spread_pct=spread_pct,
        side="sell",
    )


def round_trip_cost_pct(spread_pct: float = DEFAULT_SPREAD_PCT) -> float:
    """Total spread drag on a round trip, as a fraction of entry mid.

    This is the number that makes the weekly lane's hurdle explicit: at a 5% spread the trade
    must gain ~5% just to break even before theta. Report it next to any expectancy figure.
    """
    _validate(1.0, spread_pct)
    return spread_pct
