"""futures_risk_rails.py -- the futures analogue of Rules 5 and 6, in DOLLARS.

WHY THIS EXISTS (2026-08-09, FUTURES-FIRST-PLAN WS-F7). Every risk rail this project
owns was written for long options, where the premium paid IS the maximum loss and a
stop is a PERCENTAGE of premium. Neither assumption survives contact with futures:

  * A futures loss is NOT capped by what you posted. Margin is a good-faith deposit;
    P&L runs on the full notional (MARGIN-LEVERAGE-RISK.md). One MES at index 7,780
    is ~$38,900 of notional controlled on a few hundred dollars of day margin.
  * A "-50% catastrophe cap" is meaningless here -- there is no premium to halve.
    Futures stops are POINTS, and points convert to dollars through point_value.
  * Options cannot margin-call you. Futures can, and the broker liquidates at the
    worst moment plus fees.

So these rails are all denominated in DOLLARS and POINTS, never percent-of-premium.
They are deliberately TIGHTER than any broker margin call -- our stop must always
fire before the broker's does, which is the `liquidation distance` assertion below
and the single most important rail in this file.

DEFAULTS are the ones already written down in MARGIN-LEVERAGE-RISK.md sec "Kill-switch
floor" for sandbox account 5WW73759: $2,000 start, $1,600 floor (-20%), -$200/day.
Contract cap starts at 1 MES per the plan ("max contracts=1 MES to start") -- this is
a starting posture, not a discovered optimum, and raising it is a ratification event
with a scorecard, not an edit.

FAIL-CLOSED FOR ENTRIES, FAIL-OPEN FOR EXITS. Every rail here can block a NEW entry.
None of them can block an EXIT or a flatten -- a risk system that can trap you in a
position is a bigger risk than the one it manages.
"""
from __future__ import annotations

import calendar
import datetime as dt
from dataclasses import dataclass, field
from typing import Optional

from futures.futures_session import (
    MAINTENANCE_START, RTH_END, RTH_START, is_rth, is_session_open, session_phase,
)

# ── defaults (MARGIN-LEVERAGE-RISK.md "Kill-switch floor") ────────────────────
DEFAULT_START_EQUITY = 2_000.0
DEFAULT_ACCOUNT_FLOOR = 1_600.0        # -20% of start: the account is dead below this
DEFAULT_SESSION_LOSS_CAP = 200.0       # -$/session: Rule 5 analogue
DEFAULT_PER_TRADE_RISK_CAP = 100.0     # -$/trade at a full stop: Rule 6 analogue
DEFAULT_MAX_CONTRACTS = 1              # 1 MES to start (plan WS-F7)

# Conservative day-margin per micro contract. Deliberately HIGH: overestimating the
# broker's requirement makes the liquidation-distance rail stricter, and the doc is
# explicit that the real number moves with volatility ("always confirm live").
DEFAULT_DAY_MARGIN_PER_CONTRACT = 500.0

# No new entry inside this many minutes of the 17:00 ET settlement/maintenance stop.
# Day margin only applies if you are flat before the session-end cutoff; carrying a
# day-margin position past it snaps the full overnight requirement back and can
# trigger auto-liquidation on a $2K account.
MINUTES_BEFORE_MAINTENANCE_BLOCK = 30
# Force-flatten this many minutes before the maintenance stop.
MINUTES_BEFORE_MAINTENANCE_FLATTEN = 10

# Rollover: liquidity migrates to the back month ~8 days before expiry
# ("Rollover Thursday", SESSIONS-ROLLOVER-TAX.md sec 2). Don't open new risk in a
# thinning contract.
ROLLOVER_BLOCK_DAYS = 8


@dataclass(frozen=True)
class RiskVerdict:
    """Result of a rail check. `allow` is the only field a caller may act on."""
    allow: bool
    reason: str
    rail: str = ""
    detail: dict = field(default_factory=dict)

    def __bool__(self) -> bool:
        return self.allow


ALLOW = RiskVerdict(True, "all rails clear", "none")


# ── rollover calendar ─────────────────────────────────────────────────────────

def third_friday(year: int, month: int) -> dt.date:
    """Expiration date for a quarterly equity-index contract."""
    cal = calendar.monthcalendar(year, month)
    fridays = [w[calendar.FRIDAY] for w in cal if w[calendar.FRIDAY] != 0]
    return dt.date(year, month, fridays[2])


def front_month_expiry(on: dt.date) -> dt.date:
    """Expiry of the contract that is front month on `on` (Mar/Jun/Sep/Dec cycle)."""
    for month in (3, 6, 9, 12):
        if month >= on.month:
            exp = third_friday(on.year, month)
            if exp >= on:
                return exp
    return third_friday(on.year + 1, 3)


def days_to_expiry(on: dt.date) -> int:
    return (front_month_expiry(on) - on).days


# ── the rails ─────────────────────────────────────────────────────────────────

@dataclass
class FuturesRiskRails:
    """Dollar-denominated rails for one futures arm. Stateless w.r.t. the broker --
    equity and realized P&L are passed in, so the same object can be asked
    hypothetical questions without mutating anything."""

    start_equity: float = DEFAULT_START_EQUITY
    account_floor: float = DEFAULT_ACCOUNT_FLOOR
    session_loss_cap: float = DEFAULT_SESSION_LOSS_CAP
    per_trade_risk_cap: float = DEFAULT_PER_TRADE_RISK_CAP
    max_contracts: int = DEFAULT_MAX_CONTRACTS
    day_margin_per_contract: float = DEFAULT_DAY_MARGIN_PER_CONTRACT
    rth_only: bool = True

    # ---- individual rails (each returns a RiskVerdict; all are independently testable)

    def check_contract_cap(self, qty: int) -> RiskVerdict:
        if qty < 1:
            return RiskVerdict(False, f"qty {qty} is not a tradeable size", "contract_cap")
        if qty > self.max_contracts:
            return RiskVerdict(
                False, f"qty {qty} exceeds max_contracts {self.max_contracts}",
                "contract_cap", {"qty": qty, "cap": self.max_contracts})
        return ALLOW

    def check_per_trade_risk(self, stop_points: float, qty: int, instrument) -> RiskVerdict:
        """A full stop must not cost more than the per-trade dollar cap."""
        if stop_points <= 0:
            return RiskVerdict(False, "stop_points must be > 0 -- an entry with no "
                                      "defined stop violates Rule 3", "per_trade_risk")
        risk = stop_points * instrument.point_value * qty
        if risk > self.per_trade_risk_cap:
            return RiskVerdict(
                False,
                f"full stop risks ${risk:.2f} > per-trade cap ${self.per_trade_risk_cap:.2f}",
                "per_trade_risk",
                {"risk_usd": risk, "cap": self.per_trade_risk_cap,
                 "stop_points": stop_points, "qty": qty})
        return ALLOW

    def check_session_loss(self, session_realized_pnl: float,
                           prospective_loss: float = 0.0) -> RiskVerdict:
        """Rule 5 analogue: the session's realized losses plus this trade's worst case."""
        projected = session_realized_pnl - abs(prospective_loss)
        if -projected >= self.session_loss_cap:
            return RiskVerdict(
                False,
                f"session P&L ${session_realized_pnl:.2f} with a ${abs(prospective_loss):.2f} "
                f"worst case reaches the ${self.session_loss_cap:.2f} session loss cap",
                "session_loss_cap",
                {"session_realized_pnl": session_realized_pnl,
                 "prospective_loss": prospective_loss, "cap": self.session_loss_cap})
        return ALLOW

    def check_account_floor(self, equity: float, prospective_loss: float = 0.0) -> RiskVerdict:
        projected = equity - abs(prospective_loss)
        if projected <= self.account_floor:
            return RiskVerdict(
                False,
                f"equity ${equity:.2f} less a ${abs(prospective_loss):.2f} worst case "
                f"breaches the ${self.account_floor:.2f} floor",
                "account_floor",
                {"equity": equity, "projected": projected, "floor": self.account_floor})
        return ALLOW

    def check_liquidation_distance(self, equity: float, stop_points: float, qty: int,
                                   instrument) -> RiskVerdict:
        """THE load-bearing rail: our stop must fire before the broker's margin call.

        Free equity above the posted day margin is the cushion the position can lose
        before maintenance is breached. If a full stop costs MORE than that cushion,
        the broker liquidates us first -- at its price, not our stop's, plus fees.
        """
        margin_posted = self.day_margin_per_contract * qty
        cushion = equity - margin_posted
        stop_cost = stop_points * instrument.point_value * qty
        if cushion <= 0:
            return RiskVerdict(
                False,
                f"equity ${equity:.2f} cannot post ${margin_posted:.2f} day margin for {qty} contract(s)",
                "liquidation_distance",
                {"equity": equity, "margin_posted": margin_posted})
        if stop_cost >= cushion:
            return RiskVerdict(
                False,
                f"stop costs ${stop_cost:.2f} but only ${cushion:.2f} sits above day margin -- "
                f"a margin call fires INSIDE the stop",
                "liquidation_distance",
                {"stop_cost_usd": stop_cost, "cushion_usd": cushion,
                 "margin_posted": margin_posted, "equity": equity})
        return ALLOW

    def check_session_window(self, now_et: dt.datetime) -> RiskVerdict:
        """No entries when closed, in maintenance, near the settlement stop, or --
        while `rth_only` -- outside the window our evidence actually covers."""
        if not is_session_open(now_et):
            return RiskVerdict(False, f"CME session is {session_phase(now_et)}",
                               "session_window", {"phase": session_phase(now_et)})
        minutes_to_stop = (
            dt.datetime.combine(now_et.date(), MAINTENANCE_START) - now_et
        ).total_seconds() / 60.0
        if 0 <= minutes_to_stop <= MINUTES_BEFORE_MAINTENANCE_BLOCK:
            return RiskVerdict(
                False,
                f"{minutes_to_stop:.0f}m to the 17:00 ET settlement stop -- inside the "
                f"{MINUTES_BEFORE_MAINTENANCE_BLOCK}m no-new-entry window",
                "session_window", {"minutes_to_stop": minutes_to_stop})
        if self.rth_only and not is_rth(now_et):
            return RiskVerdict(
                False,
                f"outside RTH {RTH_START}-{RTH_END} and no overnight edge is validated",
                "session_window", {"phase": session_phase(now_et)})
        return ALLOW

    def check_rollover(self, now_et: dt.datetime) -> RiskVerdict:
        dte = days_to_expiry(now_et.date())
        if dte <= ROLLOVER_BLOCK_DAYS:
            return RiskVerdict(
                False,
                f"{dte}d to expiry {front_month_expiry(now_et.date())} -- inside the "
                f"{ROLLOVER_BLOCK_DAYS}d rollover window, liquidity is leaving this contract",
                "rollover", {"days_to_expiry": dte})
        return ALLOW

    def check_data_freshness(self, freshness_verdict: str) -> RiskVerdict:
        """Never-blind: only a GREEN feed may authorize a new entry."""
        if freshness_verdict != "GREEN":
            return RiskVerdict(
                False, f"bar feed is {freshness_verdict}, not GREEN -- entering on a "
                       f"feed we cannot vouch for is trading blind",
                "data_freshness", {"freshness": freshness_verdict})
        return ALLOW

    # ---- the composite gate ---------------------------------------------------

    def check_entry(self, *, now_et: dt.datetime, equity: float,
                    session_realized_pnl: float, stop_points: float, qty: int,
                    instrument, freshness_verdict: str = "GREEN") -> RiskVerdict:
        """Run every entry rail. Returns the FIRST failure, or ALLOW.

        Order is cheapest-and-most-categorical first so the logged reason names the
        most fundamental problem rather than an incidental one.
        """
        prospective_loss = stop_points * instrument.point_value * qty
        for verdict in (
            self.check_session_window(now_et),
            self.check_rollover(now_et),
            self.check_data_freshness(freshness_verdict),
            self.check_contract_cap(qty),
            self.check_per_trade_risk(stop_points, qty, instrument),
            self.check_session_loss(session_realized_pnl, prospective_loss),
            self.check_account_floor(equity, prospective_loss),
            self.check_liquidation_distance(equity, stop_points, qty, instrument),
        ):
            if not verdict.allow:
                return verdict
        return ALLOW

    def must_flatten(self, now_et: dt.datetime) -> RiskVerdict:
        """Should an OPEN position be closed right now regardless of its thesis?

        Note the inverted polarity: `allow=True` here means "yes, flatten". This is
        the one place in the file where the rails force an action rather than block
        one, so it never gates an exit -- it demands one.
        """
        minutes_to_stop = (
            dt.datetime.combine(now_et.date(), MAINTENANCE_START) - now_et
        ).total_seconds() / 60.0
        if 0 <= minutes_to_stop <= MINUTES_BEFORE_MAINTENANCE_FLATTEN:
            return RiskVerdict(
                True,
                f"{minutes_to_stop:.0f}m to the 17:00 ET settlement stop -- day margin "
                f"reverts to overnight and a $2K account cannot carry it",
                "flatten_before_maintenance", {"minutes_to_stop": minutes_to_stop})
        if self.rth_only and is_session_open(now_et) and not is_rth(now_et):
            return RiskVerdict(
                True, "RTH window closed and the arm holds no overnight mandate",
                "flatten_after_rth", {"phase": session_phase(now_et)})
        return RiskVerdict(False, "no forced-flatten condition", "none")

    def max_qty_for(self, *, equity: float, stop_points: float, instrument) -> int:
        """Largest size that clears EVERY sizing rail. 0 means 'do not trade'."""
        for qty in range(self.max_contracts, 0, -1):
            checks = (
                self.check_per_trade_risk(stop_points, qty, instrument),
                self.check_liquidation_distance(equity, stop_points, qty, instrument),
                self.check_account_floor(equity, stop_points * instrument.point_value * qty),
            )
            if all(c.allow for c in checks):
                return qty
        return 0


DEFAULT_RAILS = FuturesRiskRails()

__all__ = [
    "FuturesRiskRails", "RiskVerdict", "DEFAULT_RAILS",
    "third_friday", "front_month_expiry", "days_to_expiry",
    "ROLLOVER_BLOCK_DAYS", "MINUTES_BEFORE_MAINTENANCE_BLOCK",
    "MINUTES_BEFORE_MAINTENANCE_FLATTEN",
]
