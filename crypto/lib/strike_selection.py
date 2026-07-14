"""strike_selection — per-tier OTM/ITM strike math (v15 doctrine).

Live source-of-truth (THIS file, `V15_SAFE_TIERS` / `V15_BOLD_TIERS` below):
  `setup/scripts/heartbeat_core.py` (the live core-Safe/Bold engine) calls
  `pick_strike()` against these hardcoded tables directly — it does NOT read
  `automation/state/params.json` for strike tiers. This has been true since
  2026-06-18 (commit 5da0da2), when the old account-specific `params_safe.json`
  / `params_bold.json` ladder files were retired in favor of these constants.

  V15_BOLD_TIERS (mirrors params.json#v15_strike_offset_per_tier, Bold/base):
    $0-$2K   : strike_offset = -3   (OTM-3)
    $2K-$10K : strike_offset = -2   (OTM-2)
    $10K-$25K: strike_offset = -1   (OTM-1)
    $25K+    : strike_offset = +2   (ITM-2)

  V15_SAFE_TIERS: ATM (0) under $10K, then slight ITM, then ITM-2 at $25K+.

Sim-lane source-of-truth (`automation/state/params.json#v15_strike_offset_per_tier`):
  `backtest/lib/orchestrator.py`'s `_apply_param_overrides` genuinely reads this
  key (T-09 per-tier equity-based strike selection) when a backtest supplies
  `account_equity` — it is a REAL, live consumer on the sim/backtest lane, not
  a dead knob, even though the live core path above no longer reads it. The two
  tables can drift; reconcile per Operating Principle 4 if they do. See
  analysis/deep-research/2026-07-11-strike-tier-reconciliation.md for the full
  three-way doc-drift writeup this docstring was corrected from.

Canonical formula (per `automation/prompts/heartbeat.md` line 254):
  BEAR puts:  strike = round(spot) + strike_offset   (positive = ITM, negative = OTM)
  BULL calls: strike = round(spot) - strike_offset   (mirror)

Sanity invariants any strike-selection must hold:
  For calls: ITM iff strike < spot; OTM iff strike > spot.
  For puts:  ITM iff strike > spot; OTM iff strike < spot.

Validator confirms both the tier lookup AND the sign convention via these
invariants.
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
