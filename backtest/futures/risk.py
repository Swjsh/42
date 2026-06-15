"""Prop-firm risk layer for the 42 Futures Edition.

Encodes the two dominant funded-futures drawdown models (verified 2026-06):
  - Topstep:  END-OF-DAY trailing that LOCKS at the starting floor once hit; effectively a
              static floor after enough profit. Fixed $ loss limit set at account creation.
  - Apex:     INTRADAY trailing drawdown that ratchets up on unrealized profit and never
              moves down -> a routine pullback can violate it. (Apex v4.0 2026 also offers EOD.)
  - MyFundedFutures: EOD (Core) or intraday (Rapid).

This is the futures analog of the engine's per-account kill-switch + sizing rules. The
heartbeat for futures checks `would_violate()` before every entry and refuses if true.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal

DrawdownType = Literal["intraday_trailing", "eod_trailing", "static"]


@dataclass
class PropAccount:
    name: str
    starting_balance: float
    max_drawdown: float                 # $ trailing/static loss allowance
    drawdown_type: DrawdownType
    profit_target: float                 # $ to pass eval
    max_contracts: int                   # firm hard cap (micros)
    daily_loss_limit: float | None = None
    # runtime state
    peak_equity: float = field(default=0.0)
    eod_peak_equity: float = field(default=0.0)
    day_start_equity: float = field(default=0.0)

    def __post_init__(self):
        self.peak_equity = self.starting_balance
        self.eod_peak_equity = self.starting_balance
        self.day_start_equity = self.starting_balance

    def floor(self) -> float:
        """Current loss floor (account is blown if equity drops to/below this)."""
        if self.drawdown_type == "static":
            return self.starting_balance - self.max_drawdown
        ref = self.peak_equity if self.drawdown_type == "intraday_trailing" else self.eod_peak_equity
        floor = ref - self.max_drawdown
        # Topstep-style lock: floor never exceeds (start) i.e. once you've banked the buffer it freezes
        return min(floor, self.starting_balance)

    def would_violate(self, prospective_equity: float) -> bool:
        if prospective_equity <= self.floor():
            return True
        if self.daily_loss_limit is not None:
            if (self.day_start_equity - prospective_equity) >= self.daily_loss_limit:
                return True
        return False

    def update(self, equity: float):
        self.peak_equity = max(self.peak_equity, equity)

    def roll_eod(self, equity: float):
        self.eod_peak_equity = max(self.eod_peak_equity, equity)
        self.day_start_equity = equity


# Reference accounts (micros). Verify exact numbers at signup — firms change them.
TOPSTEP_50K = PropAccount("Topstep-50K", 50_000, 2_000, "eod_trailing", 3_000, max_contracts=5)
APEX_50K    = PropAccount("Apex-50K",    50_000, 2_500, "intraday_trailing", 3_000, max_contracts=10)


def size_contracts(account_equity: float, risk_per_trade_usd: float,
                   stop_points: float, instrument, hard_cap: int) -> int:
    """Contracts so that a full stop loses ~risk_per_trade_usd. stop_points in INDEX points."""
    if stop_points <= 0:
        return 1
    per_contract_risk = stop_points * instrument.point_value
    if per_contract_risk <= 0:
        return 1
    n = int(risk_per_trade_usd // per_contract_risk)
    return max(1, min(n, hard_cap))
