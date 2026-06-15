"""strike_selection — per-tier OTM/ITM strike math (v15 doctrine).

Production source-of-truth (`automation/state/params.json`):

  v15_strike_offset_per_tier (Bold/base config):
    $0-$2K   : strike_offset = -3   (OTM-3)
    $2K-$10K : strike_offset = -2   (OTM-2)
    $10K-$25K: strike_offset = -1   (OTM-1)
    $25K+    : strike_offset = +2   (ITM-2)

  Account-specific overrides (params_safe.json):
    Safe is uniform ATM (0) under $10K, then slight ITM.

Canonical formula (per `automation/prompts/heartbeat.md` line 254):
  BEAR puts:  strike = round(spot) + strike_offset   (positive = ITM, negative = OTM)
  BULL calls: strike = round(spot) - strike_offset   (mirror)

Sanity invariants any strike-selection must hold:
  For calls: ITM iff strike < spot; OTM iff strike > spot.
  For puts:  ITM iff strike > spot; OTM iff strike < spot.

Validator confirms both the tier lookup AND the sign convention via these
invariants. Drift between this file's table and params.json is a sync event
per Operating Principle 4.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True, slots=True)
class StrikeTier:
    equity_min: float
    equity_max: float
    strike_offset: int
    label: str


# v15 Bold/base tier table — mirror of params.json#v15_strike_offset_per_tier
V15_BOLD_TIERS: tuple[StrikeTier, ...] = (
    StrikeTier(0.0,        2_000.0,     -3, "OTM-3"),
    StrikeTier(2_000.0,    10_000.0,    -2, "OTM-2"),
    StrikeTier(10_000.0,   25_000.0,    -1, "OTM-1"),
    StrikeTier(25_000.0,   999_999_999.0, +2, "ITM-2"),
)

# v15 Safe tier table — mirror of params_safe.json#v15_strike_offset_per_tier
V15_SAFE_TIERS: tuple[StrikeTier, ...] = (
    StrikeTier(0.0,        2_000.0,     0, "ATM"),
    StrikeTier(2_000.0,    10_000.0,    0, "ATM"),
    StrikeTier(10_000.0,   25_000.0,    1, "Slight ITM"),
    StrikeTier(25_000.0,   999_999_999.0, +2, "ITM-2"),
)


def atm_strike(spot: float) -> int:
    """ATM strike = round(spot) to nearest dollar (matches simulator)."""
    return int(round(spot))


def pick_tier(equity: float, tiers: Sequence[StrikeTier] = V15_BOLD_TIERS) -> StrikeTier:
    """Find the tier where equity is in [equity_min, equity_max).

    Last tier acts as equity_min..infinity (inclusive both ends).
    Raises ValueError if equity is negative or no tier matches.
    """
    if equity < 0:
        raise ValueError(f"equity must be >= 0, got {equity}")
    for i, t in enumerate(tiers):
        is_last = i == len(tiers) - 1
        if t.equity_min <= equity < t.equity_max or (is_last and equity >= t.equity_min):
            return t
    raise ValueError(f"no tier matched equity={equity} (table covers $0-${tiers[-1].equity_max})")


def pick_strike(
    spot: float,
    equity: float,
    side: str,
    tiers: Sequence[StrikeTier] = V15_BOLD_TIERS,
) -> int:
    """Return the (integer) strike per the v15 tier-based formula.

    Args:
      spot: current SPY spot price
      equity: current account equity
      side: "C" for bullish calls, "P" for bearish puts
      tiers: tier table (V15_BOLD_TIERS or V15_SAFE_TIERS)

    Formula (per heartbeat.md line 254):
      BEAR puts:  strike = round(spot) + strike_offset
      BULL calls: strike = round(spot) - strike_offset
    """
    if side not in ("C", "P"):
        raise ValueError(f"side must be 'C' or 'P', got {side!r}")
    if spot <= 0:
        raise ValueError(f"spot must be positive, got {spot}")
    tier = pick_tier(equity, tiers)
    atm = atm_strike(spot)
    if side == "P":
        return atm + tier.strike_offset
    return atm - tier.strike_offset


def moneyness(strike: int, spot: float, side: str) -> str:
    """Classify strike as 'ITM' | 'ATM' | 'OTM' relative to spot, given side.

    ATM iff strike == round(spot).
    """
    atm = atm_strike(spot)
    if strike == atm:
        return "ATM"
    if side == "C":
        return "ITM" if strike < atm else "OTM"
    return "ITM" if strike > atm else "OTM"
