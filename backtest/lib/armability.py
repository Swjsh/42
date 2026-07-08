"""armability.py -- can an account afford the minimum position for a candidate edge?

G7 (2026-07-07 Fable gap-audit): chef kept promoting edges the live accounts cannot
trade -- an ITM-2 "best cell" whose min-3-lot cost exceeds the per-trade risk budget, a
2DTE cell that sizes to 1.6 lots < the 3-lot floor. No battery / promoter checked
cost-per-min-lot against the CURRENT risk budget, so unaffordable edges looked promotable.

This is the shared armability primitive. Given an entry premium (dollars per contract),
the account equity, and its per-trade risk fraction, it reports whether the MINIMUM
position (min_contracts lots) fits inside the per-trade risk budget, and how many lots the
budget actually affords. Pure, immutable, broker-free -- unit-testable on its own.

HONESTY NOTE: the entry premium is an INPUT. This module never fabricates a price. The
ratification artifacts do NOT currently persist a real average entry premium (verified
2026-07-07: promote scorecards carry expectancy/pnl/strike_offset but no $ premium), so the
promoter discloses a transparent premium SWEEP + a break-even premium rather than assert one
"true" price. Real per-cell premium capture is G8/G9; when it lands, feed the captured
average premium straight into armability() for an exact per-cell verdict.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

CONTRACT_MULTIPLIER = 100  # one US equity/ETF option contract = 100 shares

# A TRANSPARENT representative SPY option-premium sweep ($/contract). NOT a claim about any
# one cell's price -- it spans a deep-OTM 0DTE scalp (~$0.30) to a rich ITM / multi-DTE
# contract (~$3.00) so the reader sees the affordability boundary across the plausible range.
PREMIUM_SWEEP: Tuple[float, ...] = (0.30, 0.75, 1.50, 3.00)


@dataclass(frozen=True)
class Armability:
    """Immutable armability verdict for one (premium, equity, risk_frac, min_contracts)."""
    entry_premium: float      # option price per contract, dollars (0.75 -> $75/contract)
    equity: float             # account equity, dollars
    risk_frac: float          # per-trade risk cap fraction (0.30 Safe / 0.50 Bold)
    min_contracts: int        # position floor (Rule 6: 3 = 2 TP + 1 runner; 1 single-exit)
    budget: float             # equity * risk_frac -- the per-trade risk cap in $
    per_lot_cost: float       # entry_premium * contract_multiplier
    min_lot_cost: float       # min_contracts * per_lot_cost
    max_affordable_lots: int  # floor(budget / per_lot_cost)
    armable: bool             # min_lot_cost <= budget (can afford the floor)

    def disclose(self) -> str:
        verdict = "ARMABLE" if self.armable else "UNAFFORDABLE"
        return (f"{verdict}: min {self.min_contracts} lots @ ${self.entry_premium:.2f} "
                f"= ${self.min_lot_cost:,.0f} vs budget ${self.budget:,.0f} "
                f"(${self.equity:,.0f}x{self.risk_frac:.0%}); affords "
                f"{self.max_affordable_lots} lots")


def armability(entry_premium: float, equity: float, *, risk_frac: float,
               min_contracts: int = 3,
               contract_multiplier: int = CONTRACT_MULTIPLIER) -> Armability:
    """Whether the minimum position (min_contracts lots) fits the per-trade risk budget.

    entry_premium: option price per contract in dollars (e.g. 0.75 = $75/contract).
    equity: account equity in dollars. risk_frac: per-trade risk cap fraction (0.30 Safe).
    min_contracts: the position floor (Rule 6: 3 for split shapes, 1 for single-exit).
    Raises ValueError on non-positive equity/premium or risk_frac outside (0, 1] -- a caller
    passing garbage should fail loudly, not get a silently-wrong verdict.
    """
    if equity <= 0:
        raise ValueError(f"equity must be > 0, got {equity}")
    if entry_premium <= 0:
        raise ValueError(f"entry_premium must be > 0, got {entry_premium}")
    if not 0 < risk_frac <= 1:
        raise ValueError(f"risk_frac must be in (0, 1], got {risk_frac}")
    if min_contracts < 1:
        raise ValueError(f"min_contracts must be >= 1, got {min_contracts}")
    budget = equity * risk_frac
    per_lot = entry_premium * contract_multiplier
    min_lot_cost = min_contracts * per_lot
    max_lots = int(budget // per_lot)
    return Armability(
        entry_premium=entry_premium, equity=equity, risk_frac=risk_frac,
        min_contracts=min_contracts, budget=budget, per_lot_cost=per_lot,
        min_lot_cost=min_lot_cost, max_affordable_lots=max_lots,
        armable=min_lot_cost <= budget,
    )


def breakeven_premium(equity: float, *, risk_frac: float, min_contracts: int = 3,
                      contract_multiplier: int = CONTRACT_MULTIPLIER) -> float:
    """The MAX entry premium ($/contract) at which min_contracts lots still fit the budget.

    Above this the floor position blows the per-trade risk cap. This is the single most
    useful armability number for chef: 'at $2K x 30% = $600 budget, a 3-lot floor fits only
    if the contract is <= $2.00' -> an ITM-2 at ~$3 is structurally unaffordable.
    """
    if equity <= 0:
        raise ValueError(f"equity must be > 0, got {equity}")
    return (equity * risk_frac) / (min_contracts * contract_multiplier)


def account_armability_disclosure(accounts: Dict[str, Dict[str, float]], *,
                                  min_contracts: int = 3,
                                  premium_sweep: Tuple[float, ...] = PREMIUM_SWEEP) -> dict:
    """Per-account armability disclosure across a transparent premium sweep (JSON-ready).

    accounts: {alias: {"equity": float, "risk_frac": float}}.
    Returns a plain dict for the promote scorecard: per account the per-trade budget, the
    break-even premium for the min-lot floor, and the min-lot cost / armable verdict at each
    swept premium. Discloses -- never blocks (a fabricated premium must not veto a real edge).
    """
    out: dict = {
        "min_contracts": min_contracts,
        "premium_sweep": list(premium_sweep),
        "note": ("premium is a TRANSPARENT sweep, not a per-cell price; the break-even "
                 "premium is the real gate -- a cell whose contract exceeds it is "
                 "unaffordable at the floor. Real per-cell capture = G8/G9."),
        "accounts": {},
    }
    for alias, cfg in accounts.items():
        eq = float(cfg["equity"])
        rf = float(cfg["risk_frac"])
        rows = []
        for p in premium_sweep:
            a = armability(p, eq, risk_frac=rf, min_contracts=min_contracts)
            rows.append({"premium": p, "min_lot_cost": round(a.min_lot_cost, 2),
                         "armable": a.armable, "max_lots": a.max_affordable_lots})
        out["accounts"][alias] = {
            "equity": eq, "risk_frac": rf, "budget": round(eq * rf, 2),
            "max_affordable_premium_for_floor": round(
                breakeven_premium(eq, risk_frac=rf, min_contracts=min_contracts), 2),
            "sweep": rows,
        }
    return out
